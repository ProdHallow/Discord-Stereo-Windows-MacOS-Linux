#!/usr/bin/env python3
"""
Discord Voice Node Offset Finder v5.0
=======================================
Cross-platform offset discovery for discord_voice.node (PE/Mach-O/ELF).
Automatically discovers all 22 patch offsets using tiered signature scanning,
chained derivation, sliding-window recovery, and structural heuristics.

Platform support:
  Windows (PE64)  — full signature scanning + derivation
  Linux   (ELF)   — symbol table + targeted instruction scanning + Clang patterns
  macOS   (Mach-O) — symbol table + Clang alternates + stereo mic patch finder (x86_64+arm64)

Resolution pipeline (each tier is attempted only if the previous one failed):
  Tier 0 — ELF/Mach-O symbol table lookup (debug symbols present on Linux; partial on macOS)
  Tier 0b — Targeted instruction scanning within symbol-bounded functions (Linux/macOS)
  Tier 1 — Primary byte-pattern signatures (9 anchors)
  Tier 2 — Relaxed alternate signatures (broader wildcards)
  Tier 2c — Clang/platform-specific alternate patterns (macOS/Linux)
  Tier 3 — Patched-binary fallback patterns
  Tier 4 — Topologically-sorted relative derivation (9 chained offsets)
  Tier 5 — Sliding-window derivation recovery (±128 bytes around expected)
  Tier 6 — Structural heuristic scanning (Opus constants, imul patterns)

macOS stereo mic patch finder: scans fat/universal Mach-O for 28 stereo patches
  across both x86_64 and arm64 slices using dedicated signature sets.

Cross-validation verifies consistency between independently-found offsets.

Expected byte verification uses three-layer overrides:
  - Base:       EXPECTED_ORIGINALS (Windows/MSVC defaults)
  - Clang:      EXPECTED_ORIGINALS_CLANG (universal Clang differences, macOS+Linux)
  - Linux-only: EXPECTED_ORIGINALS_LINUX_ONLY (logic inversions specific to Linux)
  - macOS-only: EXPECTED_ORIGINALS_MACHO_ONLY (prologue differences specific to macOS)

Signature stability verified across:
  - December 2025 build (9219)
  - February 2026 build (Feb 9, 2026)
  - Linux ELF binary (Aug 2025, Clang)
  - macOS fat binary (Feb 2026, x86_64+arm64)

Usage:
  python discord_voice_node_offset_finder.py <path_to_discord_voice.node>
  python discord_voice_node_offset_finder.py  (auto-detects Discord install)
  python discord_voice_node_offset_finder.py --json <path>   (print only JSON to stdout)
  python discord_voice_node_offset_finder.py --export <path> <node_path>  (write JSON to file)

Requirements: Python 3.6+ (stdlib only)
Optional:     networkx + matplotlib (for dependency graph PNG)
"""

import sys
import os
import struct
import json
import hashlib
import platform
import glob as _glob
from datetime import datetime, timezone
from pathlib import Path
from io import StringIO

try:
    import networkx as nx
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    VIZ_AVAILABLE = True
except ImportError:
    VIZ_AVAILABLE = False

VERSION = "5.0"


# region Configuration

# Relative offset derivation map.
# Format: derived_name -> [(anchor_name, delta), ...] (tried in order)
# Multiple paths provide chained fallback: if the first anchor isn't found,
# the next path is attempted.  This is critical for DuplicateEmulateBitrateModified
# which chains through EmulateBitrateModified (itself derived).
DERIVATIONS = {
    "EmulateStereoSuccess2": [
        ("EmulateStereoSuccess1", 0xC),     # Windows delta
        ("EmulateStereoSuccess1", 0x1),     # Linux delta (je immediately after cmp byte)
    ],
    "Emulate48Khz": [
        ("EmulateStereoSuccess1", 0x168),   # Windows delta
    ],
    "EmulateBitrateModified": [
        ("EmulateStereoSuccess1", 0x45F),   # Windows delta
    ],
    "HighPassFilter": [
        ("EmulateStereoSuccess1", 0xC275),  # Windows delta
    ],
    "SetsBitrateBitwiseOr": [
        ("SetsBitrateBitrateValue", 0x8),   # Same on both platforms
    ],
    "AudioEncoderOpusConfigIsOk": [
        ("AudioEncoderOpusConfigSetChannels", 0x29C),  # Windows delta
        ("AudioEncoderOpusConfigSetChannels", 0x19B),  # Linux delta
        ("AudioEncoderOpusConfigSetChannels", 0x30B),  # macOS delta
    ],
    "DcReject": [
        ("HighpassCutoffFilter", 0x1E0),    # Windows delta
        ("HighpassCutoffFilter", 0x1B0),    # Linux delta
    ],
    "EncoderConfigInit1": [
        ("AudioEncoderOpusConfigSetChannels", 0xA),  # Same on both platforms
    ],
    "DuplicateEmulateBitrateModified": [
        ("EmulateBitrateModified", 0x4EE6),           # primary: chained via derived anchor
        ("EmulateStereoSuccess1", 0x45F + 0x4EE6),    # fallback: direct from root anchor
    ],
}

# Sliding window parameters for derivation recovery.
# When exact delta fails byte verification, scan this many bytes in each
# direction for the expected original bytes.
SLIDING_WINDOW_DEFAULT = 128
SLIDING_WINDOW_OVERRIDES = {
    # Single-byte expected values get a tighter window to reduce false positives
    "EmulateStereoSuccess2": 48,     # expected: 0x75 (jne)
    "EncoderConfigInit1": 48,        # expected: 00 7D 00 00 (distinctive 4-byte)
}

# endregion Configuration


# region Signature Definitions

class Signature:
    """Defines a byte pattern signature with optional relaxed alternates."""

    def __init__(self, name, pattern_hex, target_offset, description,
                 expected_original=None, patch_bytes=None, patch_len=None,
                 disambiguator=None, alt_patterns=None):
        self.name = name
        self.pattern_hex = pattern_hex
        self.pattern = self._parse(pattern_hex)
        self.target_offset = target_offset
        self.description = description
        self.expected_original = expected_original
        self.patch_bytes = patch_bytes
        self.patch_len = patch_len
        self.disambiguator = disambiguator
        self.alt_patterns = []
        if alt_patterns:
            for alt_hex, alt_off in alt_patterns:
                self.alt_patterns.append((self._parse(alt_hex), alt_off))

    @staticmethod
    def _parse(hex_str):
        return [None if b == '??' else int(b, 16) for b in hex_str.split()]

    def __repr__(self):
        return f"Signature({self.name})"


def _mono_downmixer_disambiguator(data, match_offset):
    """Select the correct MonoDownmixer by checking for REX.R movzx (44 0F B6)
    after the jg branch.  Uses a broad 70-byte window so the match survives
    if the compiler inserts extra instructions between the jg and the movzx."""
    jg_pos = match_offset + 19
    if jg_pos + 6 > len(data):
        return False
    # Tight window first (high confidence, fast)
    if b'\x44\x0f\xb6' in data[jg_pos + 6 : jg_pos + 18]:
        return True
    # Broad window (survives extra compiler-inserted instructions)
    if b'\x44\x0f\xb6' in data[jg_pos + 6 : jg_pos + 70]:
        return True
    return False


# 9 independent anchor signatures with relaxed alternates.
# Primary patterns are exact; alt_patterns wildcard bytes the compiler may vary.
SIGNATURES = [
    Signature(
        name="EmulateStereoSuccess1",
        pattern_hex="E8 ?? ?? ?? ?? BD ?? 00 00 00 80 BC 24 80 01 00 00 01",
        target_offset=6,
        description="Stereo channel count: call <rel>; mov ebp, CHANNELS; cmp byte [rsp+0x180], 1",
        expected_original="01",
        patch_bytes="02",
        alt_patterns=[
            # Stack offset 0x180 might change with MSVC version bump
            ("E8 ?? ?? ?? ?? BD ?? 00 00 00 80 BC 24 ?? ?? 00 00 01", 6),
            # Even broader: just the mov ebp + cmp structure
            ("BD ?? 00 00 00 80 BC 24 ?? ?? 00 00 01", 1),
        ],
    ),

    Signature(
        name="AudioEncoderOpusConfigSetChannels",
        pattern_hex="48 B9 14 00 00 00 80 BB 00 00 48 89 08 48 C7 40 08 ?? 00 00 00",
        target_offset=17,
        description="Opus config: mov rcx, {48000<<32|20}; mov [rax],rcx; mov qword [rax+8], CHANNELS",
        expected_original="01",
        patch_bytes="02",
        alt_patterns=[
            # Wildcard the [rax+8] offset in case struct layout shifts
            ("48 B9 14 00 00 00 80 BB 00 00 48 89 08 48 C7 40 ?? ?? 00 00 00", 17),
            # Wildcard the store register too
            ("48 B9 14 00 00 00 80 BB 00 00 48 89 ?? 48 C7 ?? ?? ?? 00 00 00", 17),
        ],
    ),

    Signature(
        name="MonoDownmixer",
        pattern_hex="48 89 F9 E8 ?? ?? ?? ?? 84 C0 74 0D 83 BE ?? ?? 00 00 09 0F 8F",
        target_offset=8,
        description="Mono downmix gate: mov rcx,rdi; call; test al,al; jz +0xD; cmp [rsi+??], 9; jg",
        expected_original="84 C0 74 0D",
        patch_bytes="90 90 90 90 90 90 90 90 90 90 90 90 E9",
        patch_len=13,
        disambiguator=_mono_downmixer_disambiguator,
        alt_patterns=[
            # Compiler might use different register for mov rcx,rdi
            ("48 89 ?? E8 ?? ?? ?? ?? 84 C0 ?? ?? 83 ?? ?? ?? 00 00 09 0F 8F", 8),
        ],
    ),

    Signature(
        name="SetsBitrateBitrateValue",
        pattern_hex="89 F8 48 B9 ?? ?? ?? ?? 01 00 00 00 48 09 C1 48 89 4E 1C",
        target_offset=4,
        description="Bitrate setter: mov eax,edi; mov rcx,imm64; or rcx,rax; mov [rsi+0x1C],rcx",
        expected_original=None,
        alt_patterns=[
            # Struct offset 0x1C might change
            ("89 F8 48 B9 ?? ?? ?? ?? 01 00 00 00 48 09 C1 48 89 ?? ??", 4),
            # Source register might change
            ("89 ?? 48 B9 ?? ?? ?? ?? 01 00 00 00 48 09 C1 48 89 ?? ??", 4),
        ],
    ),

    Signature(
        name="ThrowError",
        pattern_hex="56 56 57 53 48 81 EC C8 00 00 00 0F 29 B4 24 B0 00 00 00 4C 89 CE 4C 89 C7 89 D3",
        target_offset=-1,
        description="Error handler: push rsi;rdi;rbx; sub rsp,0xC8; movaps [rsp+0xB0],xmm6; ...",
        expected_original="41",
        patch_bytes="C3",
        alt_patterns=[
            # Stack frame size and SSE save offset might change together
            ("56 56 57 53 48 81 EC ?? ?? 00 00 0F 29 B4 24 ?? ?? 00 00 4C 89 CE 4C 89 C7 89 D3", -1),
        ],
    ),

    Signature(
        name="DownmixFunc",
        pattern_hex="57 41 56 41 55 41 54 56 57 55 53 48 83 EC 10 48 89 0C 24 45 85 C0",
        target_offset=-1,
        description="Downmix function: push r15..r12,rsi,rdi,rbp,rbx; sub rsp,0x10; ...",
        expected_original="41",
        patch_bytes="C3",
        alt_patterns=[
            # Sub rsp size might change
            ("57 41 56 41 55 41 54 56 57 55 53 48 83 EC ?? 48 89 0C 24 45 85 C0", -1),
            # Even more relaxed: just the 8 push sequence
            ("57 41 56 41 55 41 54 56 57 55 53 48 83 EC ?? 48 89 0C 24", -1),
        ],
    ),

    Signature(
        name="CreateAudioFrameStereo",
        pattern_hex="B8 80 BB 00 00 BD 00 7D 00 00 0F 43 E8",
        target_offset=31,
        description="Audio frame: mov eax,48000; mov ebp,32000; cmovae ebp,eax; ... second cmov",
        expected_original="4C 0F 43 E8",
        patch_bytes="49 89 C5 90",
        alt_patterns=[
            # cmov encoding might vary (0F 43 is cmovae, could be 0F 42 cmovb)
            ("B8 80 BB 00 00 BD 00 7D 00 00 0F ?? E8", 31),
        ],
    ),

    Signature(
        name="HighpassCutoffFilter",
        pattern_hex="56 48 83 EC 30 44 0F 29 44 24 20 0F 29 7C 24 10 0F 29 34 24",
        target_offset=0,
        description="HP cutoff filter: push rsi; sub rsp,0x30; SSE saves (xmm8,xmm7,xmm6)",
        expected_original="56 48 83 EC 30",
        patch_bytes=None,
        patch_len=0x100,
        alt_patterns=[
            # Sub rsp size and SSE save offsets might shift together
            ("56 48 83 EC ?? 44 0F 29 44 24 ?? 0F 29 7C 24 ?? 0F 29 34 24", 0),
        ],
    ),

    Signature(
        name="EncoderConfigInit2",
        pattern_hex="48 B9 ?? ?? ?? ?? ?? ?? ?? ?? 48 89 48 10 66 C7 40 18 00 00 C6 40 1A 00",
        target_offset=6,
        description="Encoder config constructor 2: mov rcx,packed_qword; mov [rax+0x10],rcx; ...",
        expected_original="00 7D 00 00",
        patch_bytes="00 D0 07 00",
        patch_len=4,
        alt_patterns=[
            # Struct member offsets might shift
            ("48 B9 ?? ?? ?? ?? ?? ?? ?? ?? 48 89 48 ?? 66 C7 40 ?? 00 00 C6 40 ?? 00", 6),
        ],
    ),
]

# endregion Signature Definitions


# region Clang Alternate Patterns

# Clang/GCC codegen differences from MSVC:
#   - Different register allocation (e.g., rdi/rsi for first args instead of rcx/rdx)
#   - Different prologue sequences (push rbp; mov rbp,rsp vs sub rsp)
#   - endbr64 prefix (0xF3 0x0F 0x1E 0xFA) on CET-enabled Linux builds
#   - Different conditional branch encodings
#   - Different stack alignment padding
#
# These patterns are tried AFTER the primary MSVC patterns fail.
# Each entry: (sig_name, pattern_hex, target_offset)
CLANG_ALT_PATTERNS = [
    # EmulateStereoSuccess1 — Clang might use edi instead of ebp for channel count
    # and different comparison structure
    ("EmulateStereoSuccess1",
     "E8 ?? ?? ?? ?? BF ?? 00 00 00 80 ?? 24 ?? ?? 00 00 01", 6),
    # Broader: just the channel count mov + cmp [rsp+??], 1
    ("EmulateStereoSuccess1",
     "?? ?? 00 00 00 80 ?? 24 ?? ?? 00 00 01", 1),

    # AudioEncoderOpusConfigSetChannels — Clang may reorder the stores
    # or use a different mov encoding for the packed constant
    ("AudioEncoderOpusConfigSetChannels",
     "48 B8 14 00 00 00 80 BB 00 00 48 89 ?? 48 C7 ?? ?? ?? 00 00 00", 17),
    # movabs with different register
    ("AudioEncoderOpusConfigSetChannels",
     "48 ?? 14 00 00 00 80 BB 00 00 48 89 ?? ?? 48 C7 ?? ?? ?? 00 00 00", 18),

    # MonoDownmixer — Clang uses rdi for first arg (SysV ABI) not rcx
    ("MonoDownmixer",
     "48 89 FF E8 ?? ?? ?? ?? 84 C0 74 ?? 83 ?? ?? ?? 00 00 09 0F 8F", 8),
    # With endbr64 prefix
    ("MonoDownmixer",
     "F3 0F 1E FA ?? 89 ?? E8 ?? ?? ?? ?? 84 C0 74 ?? 83 ?? ?? ?? 00 00 09 0F 8F", 12),

    # SetsBitrateBitrateValue — Clang may use different src register (edi on SysV)
    ("SetsBitrateBitrateValue",
     "89 F8 48 ?? ?? ?? ?? ?? 01 00 00 00 48 09 ?? 48 89 ?? ??", 4),
    ("SetsBitrateBitrateValue",
     "89 ?? 48 B8 ?? ?? ?? ?? 01 00 00 00 48 09 ?? 48 89 ?? ??", 4),

    # ThrowError — Clang prologue often starts with push rbp; mov rbp,rsp
    ("ThrowError",
     "55 48 89 E5 41 57 41 56 41 55 41 54 53 48 ?? EC ?? ?? 00 00", -1),
    # endbr64 + standard prologue
    ("ThrowError",
     "F3 0F 1E FA 55 48 89 E5 41 57 41 56 41 55 41 54 53", 3),

    # DownmixFunc — Clang may use different push order
    ("DownmixFunc",
     "55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 EC ?? 45 85 C0", -1),
    # endbr64 prefix
    ("DownmixFunc",
     "F3 0F 1E FA 55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 EC ??", 3),
    # SysV ABI: different register for first param
    ("DownmixFunc",
     "41 57 41 56 41 55 41 54 55 53 48 83 EC ?? 49 89 ?? 45 85 ??", -1),

    # CreateAudioFrameStereo — constant loading may differ
    ("CreateAudioFrameStereo",
     "B8 80 BB 00 00 ?? ?? 00 7D 00 00 0F ?? ??", 31),

    # HighpassCutoffFilter — Clang SSE saves may use different registers/offsets
    ("HighpassCutoffFilter",
     "55 48 89 E5 ?? ?? EC ?? 0F 29 ?? ?? ?? 0F 29 ?? ?? ?? 0F 29", 0),
    ("HighpassCutoffFilter",
     "F3 0F 1E FA 56 48 83 EC ?? ?? 0F 29 ?? ?? ?? 0F 29 ?? ?? ?? 0F 29", 4),

    # EncoderConfigInit2 — same packed constant, different struct offsets
    ("EncoderConfigInit2",
     "48 ?? ?? ?? ?? ?? ?? ?? ?? ?? 48 89 ?? ?? 66 C7 ?? ?? 00 00 C6 ?? ?? 00", 6),

    # ── Linux-specific patterns (SysV ABI / Clang codegen) ──────────────

    # SetsBitrateBitrateValue — Linux uses rcx (B9) and different mov target
    # mov reg, reg; movabs rcx, 0x100000000; or rcx, rax; <anything>
    ("SetsBitrateBitrateValue",
     "89 ?? 48 B9 00 00 00 00 01 00 00 00 48 09 C1", 4),

    # CreateAudioFrameStereo — Linux: mov eax,48000 then 4C 0F 43 (cmovnb r12,rax)
    # wider search for the 64-bit channel cmov after the frequency pair
    ("CreateAudioFrameStereo",
     "B8 80 BB 00 00 41 BD 00 7D 00 00 44 0F 43 E8", 31),
    # Even broader: just mov eax, 48000 near a 4C 0F 43
    ("CreateAudioFrameStereo",
     "B8 80 BB 00 00 41 ?? 00 7D 00 00 ?? 0F 43 ??", 31),
]

# endregion Clang Alternate Patterns


# region PE Parser

def parse_pe(data):
    """Extract PE info and compute file offset adjustment dynamically from .text section."""
    if len(data) < 0x40 or data[:2] != b'MZ':
        return None

    pe_offset = struct.unpack_from('<I', data, 0x3C)[0]
    if pe_offset + 4 > len(data) or data[pe_offset:pe_offset+4] != b'PE\x00\x00':
        return None

    coff = pe_offset + 4
    num_sections = struct.unpack_from('<H', data, coff + 2)[0]
    timestamp = struct.unpack_from('<I', data, coff + 4)[0]
    opt_header_size = struct.unpack_from('<H', data, coff + 16)[0]

    opt = coff + 20
    magic = struct.unpack_from('<H', data, opt)[0]

    if magic == 0x20B:  # PE32+
        image_base = struct.unpack_from('<Q', data, opt + 24)[0]
    else:  # PE32
        image_base = struct.unpack_from('<I', data, opt + 28)[0]

    sections = []
    sec_offset = opt + opt_header_size
    for i in range(num_sections):
        s = sec_offset + i * 40
        name = data[s:s+8].rstrip(b'\x00').decode('ascii', errors='replace')
        vsize = struct.unpack_from('<I', data, s + 8)[0]
        vaddr = struct.unpack_from('<I', data, s + 12)[0]
        raw_size = struct.unpack_from('<I', data, s + 16)[0]
        raw_offset = struct.unpack_from('<I', data, s + 20)[0]
        sections.append({
            'name': name, 'vsize': vsize, 'vaddr': vaddr,
            'raw_size': raw_size, 'raw_offset': raw_offset
        })

    # Dynamic adjustment: .text VA - .text raw offset
    # Falls back to first executable section, then to hardcoded 0xC00
    file_offset_adjustment = None
    text_section = None
    for sec in sections:
        if sec['name'] == '.text':
            text_section = sec
            file_offset_adjustment = sec['vaddr'] - sec['raw_offset']
            break

    if file_offset_adjustment is None:
        for sec in sections:
            if sec['vaddr'] > 0 and sec['raw_offset'] > 0:
                file_offset_adjustment = sec['vaddr'] - sec['raw_offset']
                text_section = sec
                break

    if file_offset_adjustment is None:
        file_offset_adjustment = 0xC00  # hardcoded fallback
        text_section = sections[0] if sections else None

    build_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)

    return {
        'image_base': image_base,
        'timestamp': timestamp,
        'build_time': build_time,
        'sections': sections,
        'pe_offset': pe_offset,
        'text_section': text_section,
        'file_offset_adjustment': file_offset_adjustment,
    }

# endregion PE Parser


# region ELF Parser

# Mapping from our offset names to likely ELF symbol substrings.
# Linux builds ship with debug symbols — function names are present in .symtab/.dynsym.
# Each entry is a list of candidate symbol substrings (tried in order).
# Entries with target_within=True mean the offset is INSIDE the function, not at its start.
ELF_SYMBOL_MAP = {
    # ── Function-start offsets (symbol address IS the offset) ──────────────
    # Verified against Linux discord_voice.node (Aug 2025 build)

    "ThrowError": {
        # discord::node_api::Environment::Throw<const char*>
        # First byte 0x41 (push r14), patched to 0xC3 (ret)
        "patterns": ["Environment5ThrowIJPKcEE", "Environment5Throw", "throw_error"],
        "at_start": True,
        "prefer_smallest": True,  # Pick the smallest overload (single-arg)
    },
    "DownmixFunc": {
        # downmix_and_resample — standalone function
        # Linux first byte 0x55 (push rbp), patched to 0xC3 (ret)
        "patterns": ["downmix_and_resample"],
        "at_start": True,
    },
    "HighpassCutoffFilter": {
        # hp_cutoff — standalone function in Opus codec
        "patterns": ["hp_cutoff"],
        "at_start": True,
    },
    "DcReject": {
        # dc_reject — standalone function in Opus codec
        "patterns": ["dc_reject"],
        "at_start": True,
    },
    "HighPassFilter": {
        # webrtc::AudioProcessingImpl::InitializeHighPassFilter
        "patterns": ["InitializeHighPassFilter"],
        "at_start": True,
    },

    # ── Instruction-level offsets (symbol gives function range) ────────────

    "EmulateStereoSuccess1": {
        # discord::media::LocalUser::CommitAudioCodec (NOT lambda invokers)
        # Contains stereo emulation check: cmp byte [rbx+0x3BB], 0 ; je
        # Target: the comparison value byte (0x00 on Linux, 0x01 on Windows)
        "patterns": ["LocalUser16CommitAudioCodecEv"],
        "at_start": False,
        "linux_scan": "stereo_cmp_byte",
        "prefer_largest": True,  # Lambda wrappers are ~31 bytes; real function is ~2020
    },
    "CreateAudioFrameStereo": {
        # discord::media::EngineAudioTransport::CreateAudioFrameToProcess
        # Contains cmovnb for channel count: 4C 0F 43 E0 (Linux) vs E8 (Windows)
        "patterns": ["CreateAudioFrameToProcess", "CreateAudioFrame"],
        "at_start": False,
        "linux_scan": "channel_cmov",
    },
    "AudioEncoderOpusConfigSetChannels": {
        # webrtc::AudioEncoderOpusConfig::AudioEncoderOpusConfig() [constructor]
        # Contains channels=1 byte at +0x15: mov qword [rdi+8], 1
        "patterns": ["AudioEncoderOpusConfigC1Ev", "AudioEncoderOpusConfigC2Ev",
                     "OpusConfigC1", "OpusConfigC2"],
        "at_start": False,
        "linux_scan": "opus_config_channels",
    },
    "SetsBitrateBitrateValue": {
        # NOT in any named audio function — found via global pattern scan.
        # Pattern: mov reg1, reg2; movabs rcx, 0x100000000; or rcx, rax
        # Symbol resolution won't help here; rely on CLANG_ALT_PATTERNS + global scan.
        "patterns": [],  # Empty = skip symbol resolution, use signature scan only
        "at_start": False,
        "linux_scan": "bitrate_movabs_or",
    },
    "EncoderConfigInit2": {
        # Same constructor as SetChannels — the 32000 (0x7D00) packed constant
        "patterns": ["AudioEncoderOpusConfigC1Ev", "AudioEncoderOpusConfigC2Ev"],
        "at_start": False,
        "linux_scan": "opus_config_bitrate",
    },
    "MonoDownmixer": {
        # In discord::media::CapturedAudioProcessor::Process
        # test al,al ; je +0x0D ; cmp dword [rbx+off], 9 ; jg
        "patterns": ["CapturedAudioProcessor7Process"],
        "at_start": False,
        "linux_scan": "mono_downmix_test",
    },
}


def parse_elf(data):
    """Parse ELF binary and extract section info, adjustment, and symbol table.

    Linux discord_voice.node ships with debug symbols (not stripped), so we
    can resolve function addresses directly from .symtab/.dynsym.
    """
    if len(data) < 64:
        return None

    # ELF magic
    if data[:4] != b'\x7fELF':
        return None

    ei_class = data[4]   # 1=32-bit, 2=64-bit
    ei_data = data[5]    # 1=LE, 2=BE
    if ei_class != 2 or ei_data != 1:
        # We only handle 64-bit little-endian (x86-64)
        if ei_class == 2 and ei_data == 2:
            return None  # Big-endian, not x86
        if ei_class == 1:
            return None  # 32-bit, unlikely for discord_voice.node

    # ELF64 header
    e_type = struct.unpack_from('<H', data, 16)[0]
    e_machine = struct.unpack_from('<H', data, 18)[0]
    e_entry = struct.unpack_from('<Q', data, 24)[0]
    e_shoff = struct.unpack_from('<Q', data, 40)[0]       # Section header table offset
    e_shentsize = struct.unpack_from('<H', data, 58)[0]   # Section header entry size
    e_shnum = struct.unpack_from('<H', data, 60)[0]       # Number of section headers
    e_shstrndx = struct.unpack_from('<H', data, 62)[0]    # Section name string table index

    if e_shoff == 0 or e_shnum == 0:
        return None

    # Parse section headers
    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        if off + e_shentsize > len(data):
            break
        sh_name_idx = struct.unpack_from('<I', data, off)[0]
        sh_type = struct.unpack_from('<I', data, off + 4)[0]
        sh_flags = struct.unpack_from('<Q', data, off + 8)[0]
        sh_addr = struct.unpack_from('<Q', data, off + 16)[0]
        sh_offset = struct.unpack_from('<Q', data, off + 24)[0]
        sh_size = struct.unpack_from('<Q', data, off + 32)[0]
        sh_link = struct.unpack_from('<I', data, off + 40)[0]
        sh_entsize = struct.unpack_from('<Q', data, off + 56)[0]
        sections.append({
            'name_idx': sh_name_idx, 'type': sh_type, 'flags': sh_flags,
            'vaddr': sh_addr, 'raw_offset': sh_offset, 'raw_size': sh_size,
            'link': sh_link, 'entsize': sh_entsize, 'index': i,
            'name': '',  # filled in below
        })

    # Resolve section names from .shstrtab
    if e_shstrndx < len(sections):
        strtab = sections[e_shstrndx]
        strtab_off = strtab['raw_offset']
        strtab_end = strtab_off + strtab['raw_size']
        for sec in sections:
            idx = sec['name_idx']
            name_off = strtab_off + idx
            if name_off < strtab_end:
                end = data.find(b'\x00', name_off, strtab_end)
                if end < 0:
                    end = strtab_end
                sec['name'] = data[name_off:end].decode('ascii', errors='replace')

    # Find .text section for adjustment
    text_section = None
    file_offset_adjustment = 0
    for sec in sections:
        if sec['name'] == '.text':
            text_section = sec
            file_offset_adjustment = sec['vaddr'] - sec['raw_offset']
            break

    # Fallback: first executable section
    if text_section is None:
        SHF_EXECINSTR = 0x4
        for sec in sections:
            if sec['flags'] & SHF_EXECINSTR and sec['vaddr'] > 0 and sec['raw_offset'] > 0:
                text_section = sec
                file_offset_adjustment = sec['vaddr'] - sec['raw_offset']
                break

    # Parse symbol tables (.symtab and .dynsym)
    symbols = []
    SHT_SYMTAB = 2
    SHT_DYNSYM = 11
    for sec in sections:
        if sec['type'] not in (SHT_SYMTAB, SHT_DYNSYM):
            continue
        if sec['entsize'] == 0:
            continue
        # String table for this symbol table
        if sec['link'] >= len(sections):
            continue
        sym_strtab = sections[sec['link']]
        sym_strtab_off = sym_strtab['raw_offset']
        sym_strtab_end = sym_strtab_off + sym_strtab['raw_size']

        num_syms = sec['raw_size'] // sec['entsize']
        for j in range(num_syms):
            sym_off = sec['raw_offset'] + j * sec['entsize']
            if sym_off + 24 > len(data):
                break
            st_name = struct.unpack_from('<I', data, sym_off)[0]
            st_info = data[sym_off + 4]
            st_shndx = struct.unpack_from('<H', data, sym_off + 6)[0]
            st_value = struct.unpack_from('<Q', data, sym_off + 8)[0]
            st_size = struct.unpack_from('<Q', data, sym_off + 16)[0]

            # Resolve symbol name
            name_off = sym_strtab_off + st_name
            sym_name = ''
            if name_off < sym_strtab_end:
                end = data.find(b'\x00', name_off, min(name_off + 512, sym_strtab_end))
                if end < 0:
                    end = min(name_off + 512, sym_strtab_end)
                sym_name = data[name_off:end].decode('ascii', errors='replace')

            if sym_name and st_value > 0:
                STT_FUNC = 2
                sym_type = st_info & 0xF
                symbols.append({
                    'name': sym_name,
                    'value': st_value,
                    'size': st_size,
                    'type': sym_type,
                    'is_func': sym_type == STT_FUNC,
                    'section': st_shndx,
                })

    # Build a quick-access dict of function symbols by name
    func_symbols = {}
    for sym in symbols:
        if sym['is_func'] and sym['value'] > 0:
            func_symbols[sym['name']] = sym

    arch = 'x86_64' if e_machine == 0x3E else f'machine_{e_machine}'

    return {
        'format': 'elf',
        'image_base': 0,  # ELF PIE — typically 0 for shared objects
        'file_offset_adjustment': file_offset_adjustment,
        'text_section': text_section,
        'sections': [{'name': s['name'], 'vaddr': s['vaddr'],
                       'raw_size': s['raw_size'], 'raw_offset': s['raw_offset']}
                      for s in sections if s['name']],
        'symbols': symbols,
        'func_symbols': func_symbols,
        'has_symbols': len(func_symbols) > 50,  # sanity: real symbol table is large
        'arch': arch,
        'entry': e_entry,
    }

# endregion ELF Parser


# region Mach-O Parser

def parse_macho(data):
    """Parse Mach-O binary (including fat/universal) for macOS discord_voice.node.

    Extracts __TEXT,__text section info for adjustment computation.
    macOS builds are typically stripped, so no symbol shortcut.
    """
    if len(data) < 32:
        return None

    magic = struct.unpack_from('<I', data, 0)[0]

    # Fat/universal binary — find x86_64 slice
    FAT_MAGIC = 0xBEBAFECA   # 0xCAFEBABE as LE
    FAT_MAGIC_64 = 0xBFBAFECA
    if magic in (FAT_MAGIC, FAT_MAGIC_64):
        return _parse_fat_macho(data)

    MH_MAGIC_64 = 0xFEEDFACF
    MH_MAGIC_64_BE = 0xCFFAEDFE  # big-endian read as LE

    if magic == MH_MAGIC_64:
        return _parse_macho_slice(data, 0)
    elif magic == MH_MAGIC_64_BE:
        return None  # big-endian Mach-O, not x86_64
    elif struct.unpack_from('>I', data, 0)[0] in (0xCAFEBABE, 0xCAFEBABF):
        return _parse_fat_macho(data)

    return None


def _parse_fat_macho(data):
    """Parse fat/universal Mach-O, extract x86_64 slice."""
    nfat_arch = struct.unpack_from('>I', data, 4)[0]
    if nfat_arch > 20:
        return None  # sanity

    CPU_TYPE_X86_64 = 0x01000007
    CPU_TYPE_ARM64 = 0x0100000C

    for i in range(nfat_arch):
        off = 8 + i * 20
        if off + 20 > len(data):
            break
        cputype = struct.unpack_from('>I', data, off)[0]
        cpusubtype = struct.unpack_from('>I', data, off + 4)[0]
        offset = struct.unpack_from('>I', data, off + 8)[0]
        size = struct.unpack_from('>I', data, off + 12)[0]

        if cputype == CPU_TYPE_X86_64:
            if offset + size <= len(data):
                result = _parse_macho_slice(data, offset)
                if result:
                    result['fat_offset'] = offset
                    result['fat_size'] = size
                    return result

    # No x86_64 slice — check for arm64 and note it
    for i in range(nfat_arch):
        off = 8 + i * 20
        cputype = struct.unpack_from('>I', data, off)[0]
        if cputype == CPU_TYPE_ARM64:
            return {'format': 'macho', 'arch': 'arm64',
                    'note': 'arm64 Mach-O detected — signature patterns are x86_64 only, '
                            'falling back to heuristics. Consider building arm64 signatures.',
                    'file_offset_adjustment': 0, 'image_base': 0, 'text_section': None,
                    'sections': [], 'symbols': {}, 'func_symbols': {}, 'has_symbols': False}

    return None


def _parse_macho_slice(data, base_offset):
    """Parse a single Mach-O 64 slice starting at base_offset."""
    magic = struct.unpack_from('<I', data, base_offset)[0]
    if magic != 0xFEEDFACF:
        return None

    cputype = struct.unpack_from('<I', data, base_offset + 4)[0]
    ncmds = struct.unpack_from('<I', data, base_offset + 16)[0]
    sizeofcmds = struct.unpack_from('<I', data, base_offset + 20)[0]

    CPU_TYPE_X86_64 = 0x01000007
    arch = 'x86_64' if cputype == CPU_TYPE_X86_64 else f'cpu_{cputype:#x}'

    # Walk load commands
    LC_SEGMENT_64 = 0x19
    LC_SYMTAB = 0x02

    sections = []
    text_section = None
    file_offset_adjustment = 0
    cmd_offset = base_offset + 32  # past mach_header_64

    symtab_off = 0
    symtab_nsyms = 0
    strtab_off = 0
    strtab_size = 0

    for _ in range(ncmds):
        if cmd_offset + 8 > len(data):
            break
        cmd = struct.unpack_from('<I', data, cmd_offset)[0]
        cmdsize = struct.unpack_from('<I', data, cmd_offset + 4)[0]
        if cmdsize < 8:
            break

        if cmd == LC_SEGMENT_64 and cmd_offset + 72 <= len(data):
            segname = data[cmd_offset + 8:cmd_offset + 24].rstrip(b'\x00').decode('ascii', errors='replace')
            vm_addr = struct.unpack_from('<Q', data, cmd_offset + 24)[0]
            vm_size = struct.unpack_from('<Q', data, cmd_offset + 32)[0]
            file_off = struct.unpack_from('<Q', data, cmd_offset + 40)[0]
            file_size = struct.unpack_from('<Q', data, cmd_offset + 48)[0]
            nsects = struct.unpack_from('<I', data, cmd_offset + 64)[0]

            # Parse sections within segment
            sec_base = cmd_offset + 72
            for s in range(nsects):
                sec_off = sec_base + s * 80
                if sec_off + 80 > len(data):
                    break
                sectname = data[sec_off:sec_off + 16].rstrip(b'\x00').decode('ascii', errors='replace')
                seg_of_sect = data[sec_off + 16:sec_off + 32].rstrip(b'\x00').decode('ascii', errors='replace')
                s_addr = struct.unpack_from('<Q', data, sec_off + 32)[0]
                s_size = struct.unpack_from('<Q', data, sec_off + 40)[0]
                s_offset = struct.unpack_from('<I', data, sec_off + 48)[0]

                sections.append({
                    'name': f"{seg_of_sect},{sectname}",
                    'vaddr': s_addr,
                    'raw_size': s_size,
                    'raw_offset': s_offset + base_offset,
                })

                if seg_of_sect == '__TEXT' and sectname == '__text':
                    text_section = sections[-1]
                    file_offset_adjustment = s_addr - (s_offset + base_offset)

        elif cmd == LC_SYMTAB and cmd_offset + 24 <= len(data):
            symtab_off = struct.unpack_from('<I', data, cmd_offset + 8)[0] + base_offset
            symtab_nsyms = struct.unpack_from('<I', data, cmd_offset + 12)[0]
            strtab_off = struct.unpack_from('<I', data, cmd_offset + 16)[0] + base_offset
            strtab_size = struct.unpack_from('<I', data, cmd_offset + 20)[0]

        cmd_offset += cmdsize

    # Parse symbols if present
    func_symbols = {}
    symbols = []
    NLIST_64_SIZE = 16
    if symtab_nsyms > 0 and symtab_off + symtab_nsyms * NLIST_64_SIZE <= len(data):
        strtab_end = strtab_off + strtab_size
        for i in range(min(symtab_nsyms, 200000)):  # cap for sanity
            noff = symtab_off + i * NLIST_64_SIZE
            if noff + NLIST_64_SIZE > len(data):
                break
            n_strx = struct.unpack_from('<I', data, noff)[0]
            n_type = data[noff + 4]
            n_sect = data[noff + 5]
            n_value = struct.unpack_from('<Q', data, noff + 8)[0]

            name_off = strtab_off + n_strx
            sym_name = ''
            if name_off < strtab_end:
                end = data.find(b'\x00', name_off, min(name_off + 512, strtab_end))
                if end < 0:
                    end = min(name_off + 512, strtab_end)
                sym_name = data[name_off:end].decode('ascii', errors='replace')

            if sym_name and n_value > 0:
                # N_SECT (0x0e) and external check
                is_defined = (n_type & 0x0e) == 0x0e
                sym = {'name': sym_name, 'value': n_value, 'is_func': is_defined and n_sect > 0, 'size': 0}
                symbols.append(sym)
                if sym['is_func']:
                    func_symbols[sym_name] = sym

    has_symbols = len(func_symbols) > 50

    return {
        'format': 'macho',
        'image_base': 0,
        'file_offset_adjustment': file_offset_adjustment,
        'text_section': text_section,
        'sections': sections,
        'symbols': symbols,
        'func_symbols': func_symbols,
        'has_symbols': has_symbols,
        'arch': arch,
    }

# endregion Mach-O Parser


# region macOS Stereo Patch Finder

def _parse_fat_macho_slices(data):
    """Parse fat Mach-O, return list of {arch, fat_offset, fat_size, data} for both slices."""
    if len(data) < 32:
        return []
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic not in (0xBEBAFECA, 0xBFBAFECA):
        return []
    nfat = struct.unpack_from(">I", data, 4)[0]
    if nfat > 20:
        return []
    CPU_X86_64, CPU_ARM64 = 0x01000007, 0x0100000C
    slices = []
    for i in range(nfat):
        off = 8 + i * 20
        if off + 20 > len(data):
            break
        cputype = struct.unpack_from(">I", data, off)[0]
        slice_off = struct.unpack_from(">I", data, off + 8)[0]
        slice_size = struct.unpack_from(">I", data, off + 12)[0]
        if cputype == CPU_X86_64 and slice_off + slice_size <= len(data):
            slices.append({"arch": "x86_64", "fat_offset": slice_off, "fat_size": slice_size,
                          "data": data[slice_off : slice_off + slice_size]})
        elif cputype == CPU_ARM64 and slice_off + slice_size <= len(data):
            slices.append({"arch": "arm64", "fat_offset": slice_off, "fat_size": slice_size,
                          "data": data[slice_off : slice_off + slice_size]})
    return slices


def _parse_hex_bytes(s):
    return bytes([int(b, 16) for b in s.split() if b])


# macOS stereo mic patch signatures (x86_64)
_X86_STEREO = [
    {"n": "MultiChannelOpusConfig_channels", "p": "C7 07 14 00 00 00 48 C7 47 08 01 00 00 00", "t": 10, "o": "01", "x": "02"},
    {"n": "MultiChannelOpusConfig_bitrate", "p": "48 B8 00 00 00 00 00 7D 00 00 48 89 47 10 66 C7 47 18", "t": 7, "o": "7D 00", "x": "D0 07"},
    {"n": "OpusConfig_channels", "p": "48 B8 14 00 00 00 80 BB 00 00 48 89 07 48 C7 47 08 01 00 00 00", "t": 17, "o": "01", "x": "02"},
    {"n": "OpusConfig_bitrate", "p": "48 B8 00 00 00 00 00 7D 00 00 48 89 47 10 C6 47 18 01", "t": 7, "o": "7D 00", "x": "D0 07"},
    {"n": "StereoDownmixChannels", "p": "66 0F 1F 44 00 00 55 48 89 E5 41 57 41 56 41 54 53 48 89 F3 48 8B 46 28 48 83 F8 02", "t": 6, "o": "55", "x": "C3"},
    {"n": "StereoDownMixFrame", "p": "84 C0 74 18 49 8B 76 18", "t": 2, "o": "74 18", "x": "90 90"},
    {"n": "StereoApplyAudioNetworkAdaptor", "p": "80 7D D8 01 0F 84 9F 00 00 00", "t": 4, "o": "0F 84 9F 00 00 00", "x": "90 90 90 90 90 90"},
    {"n": "SdpToConfig_channels", "p": "41 BF 01 00 00 00 80 7D C8 01 75", "t": 2, "o": "01", "x": "02"},
    {"n": "SdpToConfig_jne", "p": "41 BF ?? ?? ?? ?? 80 7D C8 01 75", "t": 10, "o": "75", "x": "EB"},
]

# macOS stereo mic patch signatures (arm64) — symbol-table-based lookup.
# Each entry specifies a C++ symbol substring to locate the function, then
# either patches the function entry (at_start) or scans within the function
# for a specific instruction.
_ARM64_STEREO_SYMBOLS = [
    {
        "name": "MultiChannelOpusConfig_channels",
        "symbol": "AudioEncoderMultiChannelOpusConfigC1Ev",
        "search_insn": b"\x28\x00\x80\x52",   # mov w8, #1
        "occurrence": 1, "scan_range": 64,
        "orig": "28", "patch": "48",           # mov w8, #2
    },
    {
        "name": "OpusConfig_channels",
        "symbol": "AudioEncoderOpusConfigC1Ev",
        "search_insn": b"\x28\x00\x80\x52",
        "occurrence": 1, "scan_range": 64,
        "orig": "28", "patch": "48",
    },
    {
        "name": "StereoDownmixChannels",
        "symbol": "AudioFrameOperations15DownmixChannelsEmPNS_10AudioFrameE",
        "at_start": True,
        "orig": "F6 57 BD A9", "patch": "C0 03 5F D6",  # prologue → ret
    },
    {
        "name": "StereoDownMixFrame",
        "symbol": "12DownMixFrameERKNS_10AudioFrameE",
        "search_insn": b"\x20\x01\x00\x34",   # cbz w0, #+0x24
        "occurrence": 1, "scan_range": 64,
        "orig": "20 01 00 34", "patch": "1F 20 03 D5",  # nop
    },
    {
        "name": "StereoApplyAudioNetworkAdaptor",
        "symbol": "AudioEncoderOpusImpl24ApplyAudioNetworkAdaptor",
        "search_insn": b"\x41\x01\x00\x54",   # b.ne #+0x28
        "occurrence": 1, "scan_range": 512,
        "orig": "41 01 00 54", "patch": "0A 00 00 14",  # b #+0x28 (unconditional)
    },
    {
        "name": "SdpToConfig_cinc1",
        "symbol": "AudioEncoderOpusImpl11SdpToConfig",
        "search_insn": b"\x15\x15\x88\x9A",   # csinc x21, x8, x21, ne
        "occurrence": 1, "scan_range": 512,
        "orig": "15 15 88 9A", "patch": "55 00 80 52",  # mov w21, #2
    },
    {
        "name": "SdpToConfig_mov1",
        "symbol": "AudioEncoderOpusImpl11SdpToConfig",
        "search_insn": b"\x35\x00\x80\x52",   # mov w21, #1
        "occurrence": 1, "scan_range": 512,
        "orig": "35", "patch": "55",           # mov w21, #2
    },
    {
        "name": "SdpToConfig_cinc2",
        "symbol": "AudioEncoderOpusImpl11SdpToConfig",
        "search_insn": b"\x15\x15\x88\x9A",
        "occurrence": 2, "scan_range": 512,
        "orig": "15 15 88 9A", "patch": "55 00 80 52",
    },
    {
        "name": "SdpToConfig_mov2",
        "symbol": "AudioEncoderOpusImpl11SdpToConfig",
        "search_insn": b"\x35\x00\x80\x52",
        "occurrence": 2, "scan_range": 512,
        "orig": "35", "patch": "55",
    },
    # --- v0.0.26: Critical new patches for stereo activation ---
    {
        "name": "CommitAudioCodec_stereo_force",
        "symbol": "LocalUser16CommitAudioCodecEv",
        "search_insn": b"\x61\x01\x00\x54",   # b.ne #+0x2C (stereo check)
        "occurrence": 1, "scan_range": 128,
        "orig": "61 01 00 54", "patch": "1F 20 03 D5",  # nop — always take stereo path
    },
    {
        "name": "CommitAudioCodec_stereo_force2",
        "symbol": "LocalUser16CommitAudioCodecEv",
        "search_insn": b"\xE1\x00\x00\x54",   # b.ne #+0x1C (secondary stereo check)
        "occurrence": 1, "scan_range": 768,
        "orig": "E1 00 00 54", "patch": "1F 20 03 D5",  # nop
    },
    {
        "name": "OpusConfig_IsOk",
        "symbol": "AudioEncoderOpusConfig4IsOkEv",
        "at_start": True,
        "orig": "08 00 40 B9 A9 99 99 52",
        "patch": "20 00 80 52 C0 03 5F D6",  # mov w0, #1; ret — force valid
    },
    {
        "name": "MultiChannelOpusConfig_IsOk",
        "symbol": "AudioEncoderMultiChannelOpusConfig4IsOkEv",
        "at_start": True,
        "orig": "FF 03 01 D1 F4 4F 02 A9",
        "patch": "20 00 80 52 C0 03 5F D6",  # mov w0, #1; ret — force valid
    },
    {
        "name": "CreateAudioFrame_channels1",
        "symbol": "CreateAudioFrameToProcess",
        "search_insn": b"\x3B\x00\x80\x52",   # mov w27, #1
        "occurrence": 1, "scan_range": 256,
        "orig": "3B", "patch": "5B",           # mov w27, #2
    },
    {
        "name": "CreateAudioFrame_channels2",
        "symbol": "CreateAudioFrameToProcess",
        "search_insn": b"\x3B\x00\x80\x52",
        "occurrence": 2, "scan_range": 256,
        "orig": "3B", "patch": "5B",
    },
    {
        "name": "InitializeHighPassFilter_bypass",
        "symbol": "InitializeHighPassFilterEb",
        "at_start": True,
        "orig": "F6 57 BD A9", "patch": "C0 03 5F D6",  # prologue → ret
    },
    # --- v0.0.27: Force stereo through the AudioProcessing pipeline ---
    {
        "name": "NumProcChannels_force_stereo",
        "symbol": "AudioProcessingImpl17num_proc_channelsEv",
        "at_start": True,
        "orig": "08 B4 45 39 1F 05 00 71",
        "patch": "40 00 80 52 C0 03 5F D6",  # mov w0, #2; ret — force 2-channel processing
    },
    {
        "name": "DownmixInterleavedToMono_bypass",
        "symbol": "DownmixInterleavedToMonoIsE",
        "at_start": True,
        "orig": "48 7C 40 93", "patch": "C0 03 5F D6",  # ret — prevent mono downmix
    },
    # --- v0.0.28: Bypass mono-only Discord processing to preserve stereo ---
    {
        "name": "NoiseCanceller_bypass",
        "symbol": "NoiseCanceller7ProcessEPsmmmj",
        "at_start": True,
        "orig": "FF 03 02 D1", "patch": "C0 03 5F D6",  # ret — bypass mono noise cancellation
    },
    {
        "name": "CustomCapturePostproc_bypass",
        "symbol": "DiscordCustomAudioCapturePostproc7ProcessE",
        "at_start": True,
        "orig": "A1 00 00 B4", "patch": "C0 03 5F D6",  # ret — bypass mono custom postprocessor
    },
    {
        "name": "VoiceFilters_bypass",
        "symbol": "VoiceFilters7ProcessEPsmmmj",
        "at_start": True,
        "orig": "FF 03 04 D1", "patch": "C0 03 5F D6",  # ret — bypass mono voice filters
    },
    {
        "name": "ProcessStream_bypass",
        "symbol": "AudioProcessingImpl13ProcessStreamEPKs",
        "at_start": True,
        "orig": "FF 43 02 D1 FA 67 04 A9",
        "patch": "00 00 80 52 C0 03 5F D6",  # mov w0, #0; ret — bypass mono AudioBuffer pipeline
    },
]

MIN_ARM64_VA = 0x4000


def _find_stereo_x86(slice_info, out):
    d, fo = slice_info["data"], slice_info["fat_offset"]
    seen = {}
    for s in _X86_STEREO:
        pat = Signature._parse(s["p"])
        ms = scan_pattern(d, pat)
        if len(ms) < 1:
            continue
        m = ms[0]
        po = m + s["t"]
        orig = _parse_hex_bytes(s["o"])
        if d[po : po + len(orig)] != orig:
            continue
        key = (s["n"], 0)
        if key in seen:
            continue
        seen[key] = True
        out.append({"arch": "x86_64", "va": po, "fat_offset": fo + po, "orig": s["o"], "patch": s["x"], "name": s["n"]})


def _find_stereo_arm64(slice_info, full_data, out):
    """Find ARM64 stereo patch locations using the Mach-O symbol table.

    Instead of scanning the entire slice for short patterns (which match
    thousands of locations), we look up each target function by its C++
    mangled symbol name, then scan only within that function's code.
    """
    d = slice_info["data"]
    fo = slice_info["fat_offset"]

    arm64_info = _parse_macho_slice(full_data, fo)
    if not arm64_info or not arm64_info.get("has_symbols"):
        return

    func_syms = arm64_info["func_symbols"]
    sym_cache = {}

    def _lookup_symbol(pattern):
        if pattern in sym_cache:
            return sym_cache[pattern]
        for sym_name, sym in func_syms.items():
            if pattern in sym_name:
                sym_cache[pattern] = sym
                return sym
        sym_cache[pattern] = None
        return None

    for spec in _ARM64_STEREO_SYMBOLS:
        name = spec["name"]
        sym = _lookup_symbol(spec["symbol"])
        if sym is None:
            continue

        func_va = sym["value"]
        orig = _parse_hex_bytes(spec["orig"])
        patch_bytes = _parse_hex_bytes(spec["patch"])

        if spec.get("at_start"):
            po = func_va
            if po + len(orig) > len(d):
                continue
            current = d[po : po + len(orig)]
            if current == orig:
                out.append({"arch": "arm64", "va": po, "fat_offset": fo + po,
                            "orig": spec["orig"], "patch": spec["patch"], "name": name})
            elif current == patch_bytes:
                out.append({"arch": "arm64", "va": po, "fat_offset": fo + po,
                            "orig": spec["orig"], "patch": spec["patch"], "name": name,
                            "already_patched": True})
            continue

        search_insn = spec["search_insn"]
        scan_range = spec.get("scan_range", 256)
        occurrence = spec.get("occurrence", 1)
        insn_len = len(search_insn)

        func_end = min(func_va + scan_range, len(d))
        hit = 0
        found = False
        for off in range(func_va, func_end - insn_len + 1, 4):
            if d[off : off + insn_len] == search_insn:
                hit += 1
                if hit == occurrence:
                    po = off
                    current = d[po : po + len(orig)]
                    if current == orig:
                        out.append({"arch": "arm64", "va": po, "fat_offset": fo + po,
                                    "orig": spec["orig"], "patch": spec["patch"], "name": name})
                    elif current == patch_bytes:
                        out.append({"arch": "arm64", "va": po, "fat_offset": fo + po,
                                    "orig": spec["orig"], "patch": spec["patch"], "name": name,
                                    "already_patched": True})
                    found = True
                    break

        if not found and len(orig) == len(patch_bytes):
            hit = 0
            for off in range(func_va, func_end - insn_len + 1, 4):
                patched_insn = bytearray(search_insn)
                for i, b in enumerate(patch_bytes):
                    if i < insn_len:
                        patched_insn[i] = b
                if d[off : off + insn_len] == bytes(patched_insn):
                    hit += 1
                    if hit == occurrence:
                        po = off
                        out.append({"arch": "arm64", "va": po, "fat_offset": fo + po,
                                    "orig": spec["orig"], "patch": spec["patch"], "name": name,
                                    "already_patched": True})
                        break


def find_macos_stereo_patches(data):
    """Run macOS stereo microphone patch finder on Mach-O fat binary.
    Returns list of {arch, va, fat_offset, orig, patch, name} or [] if not applicable."""
    slices = _parse_fat_macho_slices(data)
    if not slices:
        return []
    out = []
    for sl in slices:
        if sl["arch"] == "x86_64":
            _find_stereo_x86(sl, out)
        else:
            _find_stereo_arm64(sl, data, out)
    return out

# endregion macOS Stereo Patch Finder


# region Format Detection

def detect_binary_format(data):
    """Try PE → Mach-O → ELF → raw scan fallback.
    Returns a pe_info-compatible dict with 'format' key."""

    # Try PE first (Windows)
    pe = parse_pe(data)
    if pe:
        pe['format'] = 'pe'
        pe['arch'] = 'x86_64'
        pe['has_symbols'] = False
        pe['func_symbols'] = {}
        pe['symbols'] = []
        return pe

    # Try Mach-O (macOS)
    macho = parse_macho(data)
    if macho:
        return macho

    # Try ELF (Linux)
    elf = parse_elf(data)
    if elf:
        return elf

    # Fallback: raw scan with adj=0
    return {
        'format': 'raw',
        'image_base': 0,
        'file_offset_adjustment': 0,
        'text_section': None,
        'sections': [],
        'arch': 'unknown',
        'has_symbols': False,
        'func_symbols': {},
        'symbols': [],
        'note': 'Could not detect binary format. Using raw scan with adjustment=0.',
    }


def _linux_scan_within_function(data, func_start, func_size, scan_type, adj):
    """Scan within a known function range for a specific instruction pattern.

    Each scan_type encodes the knowledge of what bytes to look for inside
    a particular function on a Clang/Linux build.

    Returns the CONFIG offset (file offset + adj) or None.
    """
    import struct as _st

    end = min(func_start + func_size, len(data))
    func = data[func_start:end]
    flen = len(func)

    if scan_type == "opus_config_channels":
        # AudioEncoderOpusConfig constructor: packed movabs then channels=1
        # 48 B8 14 00 00 00 80 BB 00 00  (movabs rax, packed 20|48000)
        # 48 89 07                        (mov [rdi], rax)
        # 48 C7 47 08 01 00 00 00         (mov qword [rdi+8], 1) ← target byte is the 01
        for i in range(flen - 24):
            if (func[i:i+2] == b'\x48\xb8'
                    and func[i+2] == 0x14 and func[i+6:i+10] == b'\x80\xbb\x00\x00'):
                # Found the packed movabs — channels byte is at +0x15
                ch_off = i + 0x15
                if ch_off < flen and func[ch_off] in (0x01, 0x02):
                    return func_start + ch_off + adj
        return None

    if scan_type == "opus_config_bitrate":
        # Same constructor: the 32000 (0x7D00) packed in second movabs
        # 48 B8 00 00 00 00 00 7D 00 00  (movabs rax, 0x7D00_0000_0000)
        for i in range(flen - 10):
            if (func[i:i+2] == b'\x48\xb8'
                    and func[i+2:i+7] == b'\x00\x00\x00\x00\x00'
                    and func[i+7:i+10] == b'\x7d\x00\x00'):
                # Target: the "00 7D 00 00" starting at +5
                target_off = i + 5
                if func[target_off:target_off+4] == b'\x00\x7d\x00\x00':
                    return func_start + target_off + adj
        return None

    if scan_type == "stereo_cmp_byte":
        # CommitAudioCodec: cmp byte [rbx+0x3BB], 0 ; je
        # Pattern: 80 BB BB 03 00 00 00 74
        # Target: the comparison value byte (the 00)
        for i in range(flen - 8):
            if (func[i] == 0x80 and func[i+1] == 0xBB
                    and func[i+6] in (0x00, 0x01)
                    and func[i+7] in (0x74, 0x75)):
                # First hit with short offset < 0x1000 is likely the stereo check
                member_off = _st.unpack_from('<I', func, i+2)[0]
                if 0x100 < member_off < 0x1000:
                    return func_start + i + 6 + adj  # the comparison value byte
        return None

    if scan_type == "channel_cmov":
        # CreateAudioFrameToProcess: two cmovnb instructions after mov eax, 48000
        # 1st: 44 0F 43 E8 — frequency cmovnb r13d, eax (32-bit, skip this)
        # 2nd: 4C 0F 43 E0 — channel  cmovnb r12, rax  (64-bit, TARGET)
        # The channel cmov uses REX.WR (4C) for 64-bit operands
        for i in range(flen - 40):
            if func[i:i+5] == b'\xb8\x80\xbb\x00\x00':  # mov eax, 48000
                # Search forward for the 64-bit cmovnb (4C 0F 43) within 40 bytes
                for j in range(5, 40):
                    if i+j+4 <= flen and func[i+j:i+j+3] == b'\x4c\x0f\x43':
                        return func_start + i + j + adj
        return None

    if scan_type == "bitrate_movabs_or":
        # movabs rcx, 0x100000000 ; or rcx, rax ; mov [reg+off], rcx
        # 48 B9 00 00 00 00 01 00 00 00 48 09 C1
        for i in range(flen - 16):
            if (func[i:i+2] == b'\x48\xb9'
                    and func[i+6:i+10] == b'\x01\x00\x00\x00'
                    and func[i+10:i+13] == b'\x48\x09\xc1'):
                return func_start + i + 2 + adj  # the immediate bytes
        # Also search full .text if function didn't contain it
        return None

    if scan_type == "mono_downmix_test":
        # test al,al ; je +0x0D ; cmp dword [rbx+off], 9 ; jg
        # 84 C0 74 0D 83 BB xx xx 00 00 09 0F 8F
        for i in range(flen - 14):
            if (func[i:i+4] == b'\x84\xc0\x74\x0d'
                    and func[i+4] == 0x83 and func[i+10] == 0x09
                    and func[i+11:i+13] == b'\x0f\x8f'):
                return func_start + i + adj
        return None

    return None


def _resolve_elf_symbols(bin_info, data):
    """Use ELF/Mach-O symbol table to resolve offsets directly.

    For function-start offsets, the symbol address is the offset.
    For instruction-level offsets, we find the containing function then
    do a targeted instruction scan within that function's range.

    Returns (dict of {name: config_offset}, list of detail tuples).
    """
    if not bin_info.get('has_symbols') or not bin_info.get('func_symbols'):
        return {}, []

    func_syms = bin_info['func_symbols']
    adj = bin_info['file_offset_adjustment']
    resolved = {}
    details = []

    for offset_name, mapping in ELF_SYMBOL_MAP.items():
        candidates = []
        for pattern in mapping['patterns']:
            for sym_name, sym in func_syms.items():
                if pattern.lower() in sym_name.lower():
                    candidates.append(sym)

        if not candidates:
            continue

        # Prefer smallest function (most specific overload) if requested
        if mapping.get('prefer_smallest'):
            candidates.sort(key=lambda c: c.get('size', 0x10000))
        # Prefer largest function (real impl over lambda wrappers) if requested
        elif mapping.get('prefer_largest'):
            candidates.sort(key=lambda c: c.get('size', 0), reverse=True)

        # Prefer exact name match over substring
        best = candidates[0]
        for c in candidates:
            if any(p.lower() == c['name'].lower().rstrip('_') for p in mapping['patterns']):
                best = c
                break

        sym_addr = best['value']

        if mapping['at_start']:
            # Function start — symbol address IS the config offset
            file_off = sym_addr - adj
            if 0 <= file_off < len(data):
                resolved[offset_name] = sym_addr
                details.append((offset_name, sym_addr, best['name'], 'symbol-direct'))
        else:
            # Instruction-level — scan within the function for exact target
            func_size = best.get('size', 0)
            if func_size == 0 or func_size > 0x10000:
                func_size = 0x2000

            func_file_start = sym_addr - adj
            if func_file_start < 0:
                func_file_start = 0

            linux_scan = mapping.get('linux_scan')
            if linux_scan:
                result = _linux_scan_within_function(
                    data, func_file_start, func_size, linux_scan, adj)
                if result is not None:
                    resolved[offset_name] = result
                    details.append((offset_name, result, best['name'], 'symbol+scan'))
                else:
                    # Store hint for fallback scanning
                    func_file_end = min(func_file_start + func_size, len(data))
                    resolved[f"_symhint_{offset_name}"] = (
                        func_file_start, func_file_end, best['name'])
                    details.append((offset_name, sym_addr, best['name'],
                                    'symbol-range-hint'))
            else:
                func_file_end = min(func_file_start + func_size, len(data))
                resolved[f"_symhint_{offset_name}"] = (
                    func_file_start, func_file_end, best['name'])
                details.append((offset_name, sym_addr, best['name'],
                                'symbol-range-hint'))

    return resolved, details

# endregion Format Detection


# region Signature Scanner

def scan_pattern(data, pattern, limit=0, start=0, end=None):
    """Fast pattern scanner using bytes.find() for initial candidate skip.

    Instead of checking every byte position (O(n*m) in Python), this finds
    the first non-wildcard byte using C-speed bytes.find(), then verifies
    the full pattern only at candidate positions.  ~100x faster than pure
    Python loop on a 14MB binary.
    """
    matches = []
    pat_len = len(pattern)
    if end is None:
        end = len(data)

    # Find first non-wildcard byte for the fast skip
    first_fixed = None
    for i, b in enumerate(pattern):
        if b is not None:
            first_fixed = (i, b)
            break

    if first_fixed is None:
        return matches  # all wildcards = meaningless

    skip_to, first_byte = first_fixed
    needle = bytes([first_byte])
    pos = start

    while pos <= end - pat_len:
        idx = data.find(needle, pos + skip_to, end)
        if idx < 0:
            break

        candidate = idx - skip_to
        if candidate < start:
            pos = idx + 1
            continue

        if candidate + pat_len > end:
            break

        # Full pattern check at candidate
        match = True
        for j, p in enumerate(pattern):
            if p is not None and data[candidate + j] != p:
                match = False
                break

        if match:
            matches.append(candidate)
            if 0 < limit <= len(matches):
                return matches

        pos = candidate + 1

    return matches


def find_offset(data, sig, text_start=0, text_end=None):
    """Find offset using tiered pattern matching: primary -> relaxed alternates.
    Returns (file_offset, error_or_None, tier_string)."""

    tiers = [(sig.pattern, sig.target_offset, "primary")]
    for i, (p, o) in enumerate(sig.alt_patterns):
        tiers.append((p, o, f"relaxed-{i+1}"))

    for pattern, target_off, tier in tiers:
        matches = scan_pattern(data, pattern, start=text_start, end=text_end)

        if len(matches) == 0:
            continue

        if len(matches) == 1:
            file_offset = matches[0] + target_off
            if 0 <= file_offset < len(data):
                return file_offset, None, tier

        # Multiple matches — resolve via disambiguator then byte validation
        resolved = list(matches)

        if sig.disambiguator and len(resolved) > 1:
            valid = [m for m in resolved if sig.disambiguator(data, m)]
            if len(valid) >= 1:
                resolved = valid

        if len(resolved) > 1 and sig.expected_original:
            expected = bytes.fromhex(sig.expected_original.replace(' ', ''))
            valid = []
            for m in resolved:
                tf = m + target_off
                if 0 <= tf and tf + len(expected) <= len(data):
                    if data[tf:tf+len(expected)] == expected:
                        valid.append(m)
            if len(valid) >= 1:
                resolved = valid

        if len(resolved) > 1 and sig.patch_bytes and not sig.patch_bytes.startswith('<'):
            # Also check if any match shows already-patched bytes (still valid)
            patched = bytes.fromhex(sig.patch_bytes.replace(' ', ''))
            valid = []
            for m in resolved:
                tf = m + target_off
                if 0 <= tf and tf + len(patched) <= len(data):
                    if data[tf:tf+len(patched)] == patched:
                        valid.append(m)
            if len(valid) >= 1:
                resolved = valid

        if len(resolved) == 1:
            file_offset = resolved[0] + target_off
            if 0 <= file_offset < len(data):
                return file_offset, None, tier
        elif len(resolved) > 1:
            # For relaxed tiers, accept first match with a warning flag
            if tier != "primary":
                file_offset = resolved[0] + target_off
                if 0 <= file_offset < len(data):
                    return file_offset, None, f"{tier}(ambig:{len(resolved)})"

    return None, f"no matches across {len(tiers)} tier(s)", "none"

# endregion Signature Scanner


# region Offset Discovery Engine

def _topo_sort_derivations(derivations):
    """Sort derivation keys so parents resolve before children.

    This ensures EmulateBitrateModified resolves before
    DuplicateEmulateBitrateModified which depends on it."""
    all_derived = set(derivations.keys())
    order = []
    visited = set()

    def visit(name):
        if name in visited:
            return
        visited.add(name)
        if name in derivations:
            for anchor, _delta in derivations[name]:
                if anchor in all_derived:
                    visit(anchor)
        order.append(name)

    for name in derivations:
        visit(name)
    return order


def _all_offset_names():
    """Complete ordered list of all 18 offset names in the exact required order."""
    return [
        "CreateAudioFrameStereo",
        "AudioEncoderOpusConfigSetChannels",
        "MonoDownmixer",
        "EmulateStereoSuccess1",
        "EmulateStereoSuccess2",
        "EmulateBitrateModified",
        "SetsBitrateBitrateValue",
        "SetsBitrateBitwiseOr",
        "Emulate48Khz",
        "HighPassFilter",
        "HighpassCutoffFilter",
        "DcReject",
        "DownmixFunc",
        "AudioEncoderOpusConfigIsOk",
        "ThrowError",
        "DuplicateEmulateBitrateModified",
        "EncoderConfigInit1",
        "EncoderConfigInit2",
    ]


def _sliding_window_recover(data, anchor_config, delta, name, adj, bin_fmt='pe'):
    """When exact derivation delta fails byte verification, scan nearby.

    The compiler sometimes inserts or removes a few bytes between the anchor
    and the target due to instruction scheduling or alignment changes.  This
    scans ±WINDOW bytes around the expected position looking for the known
    original bytes at that offset.

    Returns (config_offset, slide_distance) or (None, 0).
    """
    # Merge platform-specific expected bytes
    exp_map = _build_expected_map(bin_fmt)

    if name not in exp_map:
        return None, 0

    exp_hex, exp_len = exp_map[name]
    if not exp_hex:
        return None, 0

    expected = bytes.fromhex(exp_hex.replace(' ', ''))
    if len(expected) < 2:
        # Single-byte expected values are too common for safe sliding
        # (e.g., 0x01, 0x41) — only allow tiny window
        window = min(SLIDING_WINDOW_OVERRIDES.get(name, 16), 16)
    else:
        window = SLIDING_WINDOW_OVERRIDES.get(name, SLIDING_WINDOW_DEFAULT)

    exact_file = anchor_config + delta - adj

    # Check exact position first
    if 0 <= exact_file and exact_file + len(expected) <= len(data):
        if data[exact_file:exact_file + len(expected)] == expected:
            return anchor_config + delta, 0

    # Scan window, preferring closer matches
    for dist in range(1, window + 1):
        for direction in (+1, -1):
            candidate = exact_file + (dist * direction)
            if 0 <= candidate and candidate + len(expected) <= len(data):
                if data[candidate:candidate + len(expected)] == expected:
                    config_off = candidate + adj
                    return config_off, dist * direction

    return None, 0


def _run_heuristic_scan(data, missing_names, adj, text_start, text_end):
    """Last-resort structural search for missing offsets near known constants.

    Searches for instruction patterns that are functionally tied to each offset,
    even if the surrounding code has changed enough to break the primary signature.
    """
    hints = []

    # --- Bitrate imul patterns: search for `imul reg, reg/rm, 0x7D00` (32000) ---
    if "EmulateBitrateModified" in missing_names or "DuplicateEmulateBitrateModified" in missing_names:
        imul_pat = Signature._parse("69 ?? 00 7D 00 00")
        matches = scan_pattern(data, imul_pat, start=text_start, end=text_end)
        for m in matches:
            candidate_file = m + 2
            reason = f"imul *,32000 @file:0x{m:X}"
            if "EmulateBitrateModified" in missing_names:
                hints.append(("EmulateBitrateModified", candidate_file, reason))
            if "DuplicateEmulateBitrateModified" in missing_names:
                hints.append(("DuplicateEmulateBitrateModified", candidate_file, reason))

    # --- 48000/32000 constant pair for CreateAudioFrameStereo ---
    if "CreateAudioFrameStereo" in missing_names:
        pair_pat = Signature._parse("B8 80 BB 00 00 BD 00 7D 00 00")
        matches = scan_pattern(data, pair_pat, start=text_start, end=text_end, limit=5)
        for m in matches:
            # Scan forward for the second cmovae (4C 0F 43 E8)
            for off in range(20, 60):
                pos = m + off
                if pos + 4 <= len(data) and data[pos:pos+4] == b'\x4C\x0F\x43\xE8':
                    hints.append(("CreateAudioFrameStereo", pos, f"48k/32k pair + cmovae @file:0x{m:X}"))
                    break

    # --- Opus packed config constant {48000<<32 | 20} = 0xBB80_0000_0014 ---
    if "AudioEncoderOpusConfigSetChannels" in missing_names:
        bb80_pat = Signature._parse("48 B9 14 00 00 00 80 BB 00 00")
        matches = scan_pattern(data, bb80_pat, start=text_start, end=text_end, limit=5)
        for m in matches:
            # Scan forward for mov qword [rax+N], imm (48 C7 40 NN)
            for scan in range(12, 40):
                pos = m + scan
                if pos + 5 <= len(data) and data[pos] == 0x48 and data[pos+1] == 0xC7:
                    target = pos + 4
                    if target < len(data):
                        hints.append(("AudioEncoderOpusConfigSetChannels", target,
                                     f"Opus config struct @file:0x{m:X}"))
                    break

    # --- Opus string proximity: search near "Opus" strings in binary ---
    if missing_names:
        opus_positions = []
        search_start = text_start
        while True:
            pos = data.find(b'Opus', search_start, text_end)
            if pos < 0:
                break
            opus_positions.append(pos)
            search_start = pos + 1
            if len(opus_positions) >= 20:
                break

        if opus_positions:
            for name in missing_names:
                # Only use this for Opus-related offsets
                if "Encoder" not in name and "Config" not in name:
                    continue
                for opus_pos in opus_positions[:10]:
                    window_start = max(text_start, opus_pos - 0x400)
                    window_end = min(text_end, opus_pos + 0x400)
                    # Look for the packed Opus constant nearby
                    const_pat = Signature._parse("80 BB 00 00")  # 48000 as dword
                    sub_matches = scan_pattern(data, const_pat, start=window_start, end=window_end)
                    for sm in sub_matches[:3]:
                        hints.append((name, sm, f"near Opus string @file:0x{opus_pos:X}"))

    return hints[:15]


def _cross_validate(results, adj, data, tiers_used=None):
    """Cross-validate independently found offsets for internal consistency.

    Checks:
      1. Derivation pairs: if both anchor and derived are found independently,
         verify their distance matches the expected delta.
      2. Encoder config pair: EncoderConfigInit1 and EncoderConfigInit2 should
         be in different functions but have the same patched field structure.
      3. Bitrate offsets: all bitrate-related offsets should contain the same
         default bitrate value (32000 = 0x7D00).
    """
    warnings = []
    tiers = tiers_used or {}

    # Check derivation distances
    for derived_name, paths in DERIVATIONS.items():
        if derived_name not in results:
            continue
        # Skip delta check if the derived offset was found by symbol table
        # (the symbol gives the true address; the Windows delta is irrelevant)
        derived_tier = tiers.get(derived_name, '')
        if derived_tier.startswith('symbol'):
            continue
        # Check ALL paths — only warn if NONE match (handles Linux vs Windows deltas)
        matched_any = False
        checked_any = False
        mismatch_msg = None
        for anchor_name, expected_delta in paths:
            if anchor_name not in results:
                continue
            checked_any = True
            actual_delta = results[derived_name] - results[anchor_name]
            if actual_delta == expected_delta:
                matched_any = True
                break
            mismatch_msg = (
                f"Delta mismatch: {derived_name} - {anchor_name} = "
                f"0x{actual_delta:X} (expected deltas: "
                f"{', '.join(f'0x{d:X}' for _, d in paths)})"
            )
        if checked_any and not matched_any and mismatch_msg:
            warnings.append(mismatch_msg)

    # Check EncoderConfigInit pair consistency
    if "EncoderConfigInit1" in results and "EncoderConfigInit2" in results:
        for name in ["EncoderConfigInit1", "EncoderConfigInit2"]:
            f = results[name] - adj
            if 0 <= f and f + 4 <= len(data):
                val = data[f:f+4]
                if val != b'\x00\x7D\x00\x00' and val != b'\x00\xD0\x07\x00':
                    warnings.append(f"{name}: unexpected config bytes {val.hex(' ')} "
                                    f"(expected 00 7D 00 00 or 00 D0 07 00)")

    # Check bitrate consistency (only reliable on PE where both are imul immediates)
    bitrate_names = ["EmulateBitrateModified", "DuplicateEmulateBitrateModified"]
    # Skip if either was derived via delta — only compare independently-found offsets
    both_independent = all(
        not tiers.get(n, '').startswith('derived') for n in bitrate_names
    )
    if both_independent:
        bitrate_vals = {}
        for name in bitrate_names:
            if name in results:
                f = results[name] - adj
                if 0 <= f and f + 3 <= len(data):
                    bitrate_vals[name] = data[f:f+3]

        if len(bitrate_vals) == 2:
            vals = list(bitrate_vals.values())
            if vals[0] != vals[1]:
                warnings.append(
                    f"Bitrate mismatch: {bitrate_names[0]}={vals[0].hex(' ')} vs "
                    f"{bitrate_names[1]}={vals[1].hex(' ')}"
                )

    return warnings


def discover_offsets(data, bin_info):
    """Run full offset discovery pipeline with tiered fallback.
    Accepts unified bin_info dict (from detect_binary_format).
    Returns (results_dict, errors_list, adjustment, tiers_used_dict)."""
    results = {}
    errors = []
    tiers_used = {}

    fmt = bin_info.get('format', 'raw') if bin_info else 'raw'
    adj = bin_info.get('file_offset_adjustment', 0) if bin_info else 0xC00
    if adj is None:
        adj = 0xC00 if fmt == 'pe' else 0

    text_start = 0
    text_end = len(data)
    if bin_info and bin_info.get('text_section'):
        ts = bin_info['text_section']
        text_start = ts['raw_offset']
        text_end = text_start + ts['raw_size']

    # ─── Phase 0: ELF Symbol Table Shortcut (Linux) ────────────────
    sym_hints = {}  # {name: (func_file_start, func_file_end, sym_name)}
    if bin_info and bin_info.get('has_symbols') and fmt in ('elf', 'macho'):
        print("\n" + "=" * 65)
        print("  PHASE 0: Symbol Table Resolution")
        print("=" * 65)

        try:
            sym_resolved, sym_details = _resolve_elf_symbols(bin_info, data)
        except Exception as e:
            sym_resolved = {}
            sym_details = []
            print(f"  [WARN] Symbol resolution failed: {e}")

        for offset_name, config_off, sym_name, method in sym_details:
            if method == 'symbol-direct':
                # Verify by checking expected bytes
                file_off = config_off - adj
                accept = True
                _exp_sym = _build_expected_map(fmt)
                if offset_name in _exp_sym:
                    exp_hex, exp_len = _exp_sym[offset_name]
                    if exp_hex:
                        expected = bytes.fromhex(exp_hex.replace(' ', ''))
                        if 0 <= file_off and file_off + len(expected) <= len(data):
                            actual = data[file_off:file_off + len(expected)]
                            if actual != expected:
                                print(f"  [SKIP] {offset_name:45s} symbol '{sym_name}' @0x{config_off:X} — bytes don't match")
                                accept = False

                if accept:
                    results[offset_name] = config_off
                    tiers_used[offset_name] = f"symbol({sym_name})"
                    print(f"  [SYM ] {offset_name:45s} = 0x{config_off:X}  (file 0x{file_off:X})  [{sym_name}]")

            elif method == 'symbol+scan':
                # Symbol found + targeted instruction scan succeeded
                results[offset_name] = config_off
                tiers_used[offset_name] = f"symbol+scan({sym_name})"
                file_off = config_off - adj
                print(f"  [SCAN] {offset_name:45s} = 0x{config_off:X}  (file 0x{file_off:X})  [via {sym_name}]")

            elif method == 'symbol-range-hint':
                # Store hint for targeted scanning in Phase 1
                hint_key = f"_symhint_{offset_name}"
                if hint_key in sym_resolved:
                    sym_hints[offset_name] = sym_resolved[hint_key]
                    print(f"  [HINT] {offset_name:45s} function '{sym_name}' — will do targeted scan")

        if not sym_details:
            print("  No symbol matches found — falling through to signature scanning")

    # ─── Phase 1: Primary + Relaxed Signatures ─────────────────────
    print("\n" + "=" * 65)
    print("  PHASE 1: Signature Scanning (primary + relaxed)")
    print("=" * 65)

    for sig in SIGNATURES:
        if sig.name in results:
            print(f"  [SKIP] {sig.name:45s} already resolved via symbol table")
            continue

        # If we have a symbol hint, narrow the scan window
        scan_start = text_start
        scan_end = text_end
        if sig.name in sym_hints:
            hint_start, hint_end, hint_sym = sym_hints[sig.name]
            # Use a wider window around the symbol to be safe
            scan_start = max(text_start, hint_start - 0x200)
            scan_end = min(text_end, hint_end + 0x200)

        file_off, err, tier = find_offset(data, sig, scan_start, scan_end)

        # If narrowed scan failed, try full range
        if err and sig.name in sym_hints:
            file_off, err, tier = find_offset(data, sig, text_start, text_end)

        if err:
            print(f"  [FAIL] {sig.name}: {err}")
            errors.append((sig.name, err))
        else:
            config_off = file_off + adj
            tag = "OK" if tier == "primary" else "ALT"
            print(f"  [{tag:4s}] {sig.name:45s} = 0x{config_off:X}  (file 0x{file_off:X})  [{tier}]")

            if sig.expected_original:
                expected = bytes.fromhex(sig.expected_original.replace(' ', ''))
                actual = data[file_off:file_off+len(expected)]
                if actual != expected:
                    print(f"         WARNING: Expected {expected.hex(' ')} but found {actual.hex(' ')}")

            results[sig.name] = config_off
            tiers_used[sig.name] = tier

    # ─── Phase 1c: Clang Alternate Patterns (non-PE platforms) ─────
    if fmt != 'pe':
        still_missing = [sig.name for sig in SIGNATURES if sig.name not in results]
        if still_missing:
            print("\n" + "=" * 65)
            print("  PHASE 1c: Clang/Platform-Specific Alternates")
            print("=" * 65)

            for sig_name, pat_hex, target_off in CLANG_ALT_PATTERNS:
                if sig_name not in still_missing:
                    continue
                if sig_name in results:
                    continue

                pattern = Signature._parse(pat_hex)
                matches = scan_pattern(data, pattern, start=text_start, end=text_end)

                if len(matches) == 0:
                    continue

                # Try to disambiguate
                resolved = matches
                # Find the original Signature for expected_original / disambiguator
                orig_sig = None
                for s in SIGNATURES:
                    if s.name == sig_name:
                        orig_sig = s
                        break

                if orig_sig and orig_sig.disambiguator and len(resolved) > 1:
                    valid = [m for m in resolved if orig_sig.disambiguator(data, m)]
                    if valid:
                        resolved = valid

                if orig_sig and orig_sig.expected_original and len(resolved) > 1:
                    expected = bytes.fromhex(orig_sig.expected_original.replace(' ', ''))
                    valid = []
                    for m in resolved:
                        tf = m + target_off
                        if 0 <= tf and tf + len(expected) <= len(data):
                            if data[tf:tf+len(expected)] == expected:
                                valid.append(m)
                    if valid:
                        resolved = valid

                if len(resolved) >= 1:
                    file_off = resolved[0] + target_off
                    if 0 <= file_off < len(data):
                        config_off = file_off + adj
                        ambig = f"(ambig:{len(resolved)})" if len(resolved) > 1 else ""
                        tier = f"clang-alt{ambig}"
                        print(f"  [CLNG] {sig_name:45s} = 0x{config_off:X}  (file 0x{file_off:X})  [{tier}]")
                        results[sig_name] = config_off
                        tiers_used[sig_name] = tier
                        still_missing = [n for n in still_missing if n != sig_name]

            if still_missing:
                print(f"  Still missing after Clang alts: {', '.join(still_missing)}")

    # ─── Phase 1b: Patched Binary Fallbacks ────────────────────────
    patched_fallbacks = []

    if "MonoDownmixer" not in results:
        fb_pat = Signature._parse("48 89 F9 E8 ?? ?? ?? ?? 90 90 90 90 90 90 90 90 90 90 90 90 E9")
        matches = scan_pattern(data, fb_pat, start=text_start, end=text_end)
        if len(matches) > 1:
            matches = [m for m in matches if _mono_downmixer_disambiguator(data, m)]
        if len(matches) == 1:
            config_off = matches[0] + 8 + adj
            results["MonoDownmixer"] = config_off
            tiers_used["MonoDownmixer"] = "patched-fallback"
            patched_fallbacks.append("MonoDownmixer")
            print(f"  [FALL] MonoDownmixer{' ':30s} = 0x{config_off:X}  [patched NOP sled]")

    if "SetsBitrateBitrateValue" not in results:
        for fb_hex in [
            "89 F8 48 B9 ?? ?? ?? ?? ?? ?? ?? ?? 90 90 90 48 89 4E 1C",
            "89 ?? 48 B9 ?? ?? ?? ?? ?? ?? ?? ?? 90 90 90 48 89 ?? ??",
        ]:
            fb_pat = Signature._parse(fb_hex)
            matches = scan_pattern(data, fb_pat, start=text_start, end=text_end)
            if len(matches) == 1:
                config_off = matches[0] + 4 + adj
                results["SetsBitrateBitrateValue"] = config_off
                tiers_used["SetsBitrateBitrateValue"] = "patched-fallback"
                patched_fallbacks.append("SetsBitrateBitrateValue")
                print(f"  [FALL] SetsBitrateBitrateValue{' ':20s} = 0x{config_off:X}  [patched or->NOP]")
                break

    if "HighpassCutoffFilter" not in results:
        hp_key = "HighPassFilter"
        if hp_key not in results and "EmulateStereoSuccess1" in results:
            results[hp_key] = results["EmulateStereoSuccess1"] + 0xC275
        if hp_key in results:
            hp_file = results[hp_key] - adj
            if (0 <= hp_file and hp_file + 11 <= len(data) and
                data[hp_file] == 0x48 and data[hp_file+1] == 0xB8 and data[hp_file+10] == 0xC3):
                hpc_va = struct.unpack_from('<Q', data, hp_file + 2)[0]
                if fmt == 'pe' and bin_info:
                    hpc_config = hpc_va - bin_info['image_base']
                    if 0 < hpc_config < len(data):
                        results["HighpassCutoffFilter"] = hpc_config
                        tiers_used["HighpassCutoffFilter"] = "patched-stub-extract"
                        patched_fallbacks.append("HighpassCutoffFilter")
                        print(f"  [FALL] HighpassCutoffFilter{' ':23s} = 0x{hpc_config:X}  [from HP stub VA=0x{hpc_va:X}]")
                elif fmt in ('elf', 'macho'):
                    # On ELF/Mach-O the stub VA is already relative (PIE, image_base=0)
                    if 0 < hpc_va < len(data) + adj:
                        results["HighpassCutoffFilter"] = hpc_va
                        tiers_used["HighpassCutoffFilter"] = "patched-stub-extract"
                        patched_fallbacks.append("HighpassCutoffFilter")
                        print(f"  [FALL] HighpassCutoffFilter{' ':23s} = 0x{hpc_va:X}  [from HP stub VA]")

    if patched_fallbacks:
        print(f"\n  NOTE: Binary appears already patched. Fallback used for: {', '.join(patched_fallbacks)}")

    # ─── Phase 2: Derivation (topologically sorted, chain-aware) ───
    print("\n" + "=" * 65)
    print("  PHASE 2: Relative Offset Derivation (chain-aware)")
    print("=" * 65)

    for derived_name in _topo_sort_derivations(DERIVATIONS):
        if derived_name in results:
            continue

        paths = DERIVATIONS[derived_name]
        found = False
        for anchor_name, delta in paths:
            if anchor_name not in results:
                continue

            config_off = results[anchor_name] + delta
            file_off = config_off - adj

            if file_off < 0 or file_off >= len(data):
                continue

            # Verify expected bytes at exact delta
            verified_exact = True
            _exp_drv = _build_expected_map(fmt)
            if derived_name in _exp_drv:
                exp_hex, _ = _exp_drv[derived_name]
                if exp_hex:
                    expected = bytes.fromhex(exp_hex.replace(' ', ''))
                    actual = data[file_off:file_off+len(expected)]
                    if actual != expected:
                        verified_exact = False

            if verified_exact:
                print(f"  [ OK ] {derived_name:45s} = 0x{config_off:X}  (from {anchor_name} + 0x{delta:X})")
                results[derived_name] = config_off
                tiers_used[derived_name] = f"derived({anchor_name}+0x{delta:X})"
                found = True
                break

        # If exact delta didn't verify, try sliding window
        if not found:
            for anchor_name, delta in paths:
                if anchor_name not in results:
                    continue
                slid_off, slide_dist = _sliding_window_recover(
                    data, results[anchor_name], delta, derived_name, adj,
                    bin_fmt=fmt
                )
                if slid_off is not None and slide_dist != 0:
                    sign = "+" if slide_dist > 0 else ""
                    print(f"  [SLID] {derived_name:45s} = 0x{slid_off:X}  "
                          f"(from {anchor_name} + 0x{delta:X} {sign}{slide_dist})")
                    results[derived_name] = slid_off
                    tiers_used[derived_name] = f"sliding({anchor_name}+0x{delta:X}{sign}{slide_dist})"
                    found = True
                    break

        # If exact worked without verification (no expected bytes), accept it
        if not found:
            for anchor_name, delta in paths:
                if anchor_name not in results:
                    continue
                config_off = results[anchor_name] + delta
                file_off = config_off - adj
                if 0 <= file_off < len(data):
                    print(f"  [ OK ] {derived_name:45s} = 0x{config_off:X}  (from {anchor_name} + 0x{delta:X})  [unverified]")
                    results[derived_name] = config_off
                    tiers_used[derived_name] = f"derived-unverified({anchor_name}+0x{delta:X})"
                    found = True
                    break

        if not found:
            tried = ", ".join(a for a, _ in paths)
            print(f"  [FAIL] {derived_name}: no anchor available (tried: {tried})")
            errors.append((derived_name, f"no anchor available (tried: {tried})"))

    # ─── Phase 2b: Heuristic Recovery ──────────────────────────────
    missing = [n for n in _all_offset_names() if n not in results]
    if missing:
        print("\n" + "=" * 65)
        print("  PHASE 2b: Heuristic Recovery")
        print("=" * 65)

        hints = _run_heuristic_scan(data, missing, adj, text_start, text_end)
        if hints:
            for name, file_off, reason in hints:
                if name in results:
                    continue
                config_off = file_off + adj
                # Verify expected bytes before accepting heuristic result
                _exp_map = _build_expected_map(fmt)
                if name in _exp_map:
                    exp_hex, exp_len = _exp_map[name]
                    if exp_hex:
                        expected = bytes.fromhex(exp_hex.replace(' ', ''))
                        actual = data[file_off:file_off+len(expected)]
                        if actual != expected:
                            continue  # silently skip non-matching candidates
                print(f"  [HEUR] {name:45s} = 0x{config_off:X}  [{reason}]")
                results[name] = config_off
                tiers_used[name] = f"heuristic({reason})"
        else:
            print(f"  No heuristic candidates for: {', '.join(missing)}")

    errors = [(n, e) for n, e in errors if n not in results]
    return results, errors, adj, tiers_used

# endregion Offset Discovery Engine


# region Validation

# Expected original bytes at each patch site (for verification)
# Format: (hex_string_or_None, byte_length)
EXPECTED_ORIGINALS = {
    "EmulateStereoSuccess1":    ("01", 1),
    "EmulateStereoSuccess2":    ("75", 1),
    "Emulate48Khz":             ("0F 42 C1", 3),
    "EmulateBitrateModified":   (None, 3),      # variable imul immediate
    "SetsBitrateBitrateValue":  (None, 5),      # variable immediate
    "SetsBitrateBitwiseOr":     ("48 09 C1", 3),
    "HighPassFilter":           (None, 11),      # variable prologue
    "CreateAudioFrameStereo":   (None, 4),       # cmov variant
    "AudioEncoderOpusConfigSetChannels": ("01", 1),
    "AudioEncoderOpusConfigIsOk": ("8B 11 31 C0", 4),
    "MonoDownmixer":            ("84 C0 74 0D", 4),
    "ThrowError":               ("41", 1),
    "DownmixFunc":              ("41", 1),
    "HighpassCutoffFilter":     (None, 0x100),   # full function body
    "DcReject":                 (None, 0x1B6),   # full function body
    "DuplicateEmulateBitrateModified": (None, 3), # variable imul immediate
    "EncoderConfigInit1":       ("00 7D 00 00", 4),
    "EncoderConfigInit2":       ("00 7D 00 00", 4),
}

# Linux/Clang builds have different prologue and instruction encodings.
# When binary format is ELF, these override EXPECTED_ORIGINALS.
EXPECTED_ORIGINALS_CLANG = {
    # Universal Clang differences from MSVC (apply to BOTH macOS and Linux):
    "DownmixFunc":              ("55", 1),       # push rbp (not push r14)
    "AudioEncoderOpusConfigIsOk": ("55 48 89 E5", 4),  # push rbp; mov rbp,rsp
    "Emulate48Khz":             (None, 3),       # Clang uses different encoding (no cmovb here)
    "HighpassCutoffFilter":     (None, 0x100),   # Clang prologue differs
    "DcReject":                 (None, 0x1B6),   # Clang prologue differs
}

# Linux-ONLY differences from both Windows AND macOS.
# These are logic inversions specific to the Linux build, not just Clang vs MSVC.
EXPECTED_ORIGINALS_LINUX_ONLY = {
    "EmulateStereoSuccess1":    ("00", 1),       # cmp byte[...], 0 (inverted from Win/macOS)
    "EmulateStereoSuccess2":    ("74", 1),       # je (not jne as on Win/macOS)
    "CreateAudioFrameStereo":   ("4C 0F 43", 4), # cmovnb r12, rax (E0 not E8)
}

# macOS-ONLY differences (where macOS diverges from BOTH Windows and Linux).
EXPECTED_ORIGINALS_MACHO_ONLY = {
    "ThrowError":               ("55", 1),       # push rbp (macOS); Linux/Win both use 0x41
}


def _build_expected_map(fmt):
    """Build the expected-bytes map for a given binary format."""
    m = dict(EXPECTED_ORIGINALS)
    if fmt in ('elf', 'macho'):
        m.update(EXPECTED_ORIGINALS_CLANG)
    if fmt == 'elf':
        m.update(EXPECTED_ORIGINALS_LINUX_ONLY)
    if fmt == 'macho':
        m.update(EXPECTED_ORIGINALS_MACHO_ONLY)
    return m

# Patch bytes for each offset (for already-patched detection)
PATCH_INFO = {
    "EmulateStereoSuccess1":    ("02", "Channel count 1->2"),
    "EmulateStereoSuccess2":    ("EB", "jne->jmp (force stereo)"),
    "Emulate48Khz":             ("90 90 90", "cmovb->NOPs (force 48kHz)"),
    "EmulateBitrateModified":   ("00 D0 07", "imul 32000->512000 bps"),
    "SetsBitrateBitrateValue":  ("00 D0 07 00 00", "512000 in imm64"),
    "SetsBitrateBitwiseOr":     ("90 90 90", "or rcx,rax->NOPs"),
    "HighPassFilter":           ("<dynamic: mov rax, IMAGE_BASE+HPC; ret>", "Redirect to HPC"),
    "CreateAudioFrameStereo":   ("49 89 C5 90", "cmovae->mov r13,rax; nop"),
    "AudioEncoderOpusConfigSetChannels": ("02", "Channel count 1->2"),
    "AudioEncoderOpusConfigIsOk": ("48 C7 C0 01 00 00 00 C3", "return 1"),
    "MonoDownmixer":            ("90 90 90 90 90 90 90 90 90 90 90 90 E9", "NOP sled + jmp"),
    "ThrowError":               ("C3", "ret (disable throws)"),
    "DownmixFunc":              ("C3", "ret (disable downmix)"),
    "HighpassCutoffFilter":     ("<injected: hp_cutoff>", "Custom HP cutoff + gain"),
    "DcReject":                 ("<injected: dc_reject>", "Custom DC reject + gain"),
    "DuplicateEmulateBitrateModified": ("00 D0 07", "Dup imul 32000->512000"),
    "EncoderConfigInit1":       ("00 D0 07 00", "Config qword: 32000->512000"),
    "EncoderConfigInit2":       ("00 D0 07 00", "Config qword: 32000->512000"),
}


def validate_offsets(data, results, adj, bin_fmt='pe', quiet=False):
    """Validate discovered offsets against expected byte patterns."""
    if not quiet:
        print("\n" + "=" * 65)
        print("  PHASE 3: Byte Verification")
        print("=" * 65)

    verified = 0
    warnings = 0

    # Merge platform-specific overrides
    expected_map = _build_expected_map(bin_fmt)

    for name, config_off in sorted(results.items(), key=lambda x: x[1]):
        file_off = config_off - adj

        if file_off < 0 or file_off >= len(data):
            if not quiet:
                print(f"  [FAIL] {name:45s} offset 0x{config_off:X} out of bounds")
            warnings += 1
            continue

        if name in expected_map:
            expected_hex, length = expected_map[name]
            actual = data[file_off:file_off+length]

            if expected_hex:
                expected = bytes.fromhex(expected_hex.replace(' ', ''))
                if actual[:len(expected)] == expected:
                    if not quiet:
                        print(f"  [PASS] {name:45s} original bytes: {actual[:len(expected)].hex(' ')}")
                    verified += 1
                else:
                    # Check if already patched
                    patch_hex = PATCH_INFO.get(name, (None,))[0]
                    if patch_hex and not patch_hex.startswith('<'):
                        try:
                            patched = bytes.fromhex(patch_hex.replace(' ', ''))
                            if actual[:len(patched)] == patched:
                                if not quiet:
                                    print(f"  [WARN] {name:45s} ALREADY PATCHED: {actual[:len(patched)].hex(' ')}")
                                warnings += 1
                                continue
                        except ValueError:
                            pass
                    if not quiet:
                        print(f"  [WARN] {name:45s} unexpected: {actual[:len(expected)].hex(' ')} (expected {expected_hex})")
                    warnings += 1
            else:
                if not quiet:
                    print(f"  [INFO] {name:45s} bytes: {actual[:min(8,length)].hex(' ')} (no fixed expected)")
                verified += 1

    return verified, warnings


def check_injection_sites(data, results, adj, quiet=False):
    """Verify injection sites have enough room (scan for function padding)."""
    if not quiet:
        print("\n" + "=" * 65)
        print("  PHASE 4: Injection Site Capacity")
        print("=" * 65)

    for name, inject_size, desc in [("HighpassCutoffFilter", 0x100, "hp_cutoff"), ("DcReject", 0x1B6, "dc_reject")]:
        if name not in results:
            if not quiet:
                print(f"  [SKIP] {name}: not found")
            continue

        file_off = results[name] - adj
        func_end = None

        # Scan for function end: 0xCC padding (MSVC) or ret+NOP alignment (Clang)
        for i in range(file_off, min(file_off + 0x400, len(data) - 3)):
            # MSVC: int3 padding
            if data[i:i+4] == b'\xcc\xcc\xcc\xcc':
                func_end = i
                break
            # Clang: ret followed by NOP sled or alignment (66 2E 0F 1F / 0F 1F / 90)
            if data[i] == 0xC3 and i > file_off + 8:
                nop_run = 0
                for j in range(i+1, min(i+17, len(data))):
                    if data[j] in (0x90, 0x66, 0x0F, 0x1F, 0x2E, 0x84, 0x00, 0x40):
                        nop_run += 1
                    else:
                        break
                if nop_run >= 4:
                    func_end = i + 1  # after the ret
                    break

        if func_end is None:
            # Use symbol size as fallback
            if not quiet:
                print(f"  [INFO] {name}: no padding found; using symbol size for capacity")
            continue

        available = func_end - file_off
        margin = available - inject_size
        status = "OK" if margin >= 0 else "OVER"
        if not quiet:
            print(f"  [{status:4s}] {name:30s}  available={available} (0x{available:X})  "
                  f"needed={inject_size} (0x{inject_size:X})  margin={margin:+d} bytes")

# endregion Validation


# region Output Formatters

def format_powershell_config(results, bin_info=None, file_path=None, file_size=None):
    """Generate PowerShell offset table — copy-paste directly into patcher."""
    lines = []
    fmt = bin_info.get('format', 'raw') if bin_info else 'pe'

    if bin_info and file_path and file_size:
        md5 = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
        build_str = ''
        if fmt == 'pe' and 'build_time' in bin_info:
            build_str = bin_info['build_time'].strftime('%b %d %Y')
        else:
            build_str = f'{fmt.upper()} binary'
        lines.append(f"    # Auto-generated by discord_voice_node_offset_finder.py v{VERSION}")
        lines.append(f"    # Build: {build_str} | Size: {file_size} | MD5: {md5}")
        if fmt != 'pe':
            lines.append(f"    # Format: {fmt.upper()} | Arch: {bin_info.get('arch', '?')}")
            lines.append(f"    # Note: on macOS and Linux use the 'file_offset' values below for direct binary patching")

    lines.append("    Offsets = @{")
    ordered = _all_offset_names()
    max_len = max(len(n) for n in ordered)
    adj = bin_info.get('file_offset_adjustment', 0) if bin_info else 0

    for name in ordered:
        pad = " " * (max_len - len(name))
        if name in results:
            if fmt != 'pe':
                file_off = results[name] - adj
                lines.append(f"        {name}{pad} = 0x{results[name]:X}  # file_offset=0x{file_off:X}")
            else:
                lines.append(f"        {name}{pad} = 0x{results[name]:X}")
        else:
            lines.append(f"        {name}{pad} = 0x0  # NOT FOUND")

    lines.append("    }")
    return "\n".join(lines)


def format_cpp_namespace(results):
    """Generate C++ namespace block for reference."""
    lines = ["namespace Offsets {"]
    for name in sorted(results.keys()):
        lines.append(f"    constexpr uint32_t {name} = 0x{results[name]:X};")
    lines.append("};")
    return "\n".join(lines)


def format_json(results, bin_info, file_path, file_size, adj, tiers_used, expected_map=None):
    """Generate machine-readable JSON output for patchers.
    If expected_map is provided (name -> (expected_hex, length)), adds a 'patches' array
    with name, file_offset, expected_original, and length for each offset.
    """
    fmt = bin_info.get('format', 'raw') if bin_info else 'pe'
    out = {
        "tool": "discord_voice_node_offset_finder",
        "version": VERSION,
        "file": str(file_path),
        "file_size": file_size,
        "md5": hashlib.md5(open(file_path, 'rb').read()).hexdigest(),
        "format": fmt,
        "arch": bin_info.get('arch', 'unknown') if bin_info else 'unknown',
        "file_offset_adjustment": hex(adj),
        "offsets": {name: hex(off) for name, off in sorted(results.items())},
        "resolution_tiers": tiers_used,
        "total_found": len(results),
        "total_expected": 18,
    }

    if fmt == 'pe' and bin_info:
        out["pe_timestamp"] = bin_info.get('timestamp')
        out["pe_build_time"] = bin_info['build_time'].isoformat() if 'build_time' in bin_info else None
        out["image_base"] = hex(bin_info.get('image_base', 0))
    elif fmt in ('elf', 'macho') and bin_info:
        out["image_base"] = hex(bin_info.get('image_base', 0))
        out["has_symbols"] = bin_info.get('has_symbols', False)
        # Include file offsets for direct patching (add fat_offset when fat binary)
        fat_off = bin_info.get('fat_offset') or 0
        out["file_offsets"] = {name: hex(off - adj + fat_off) for name, off in sorted(results.items())}
        if fat_off:
            out["fat_offset_x86_64"] = fat_off

    # Patch spec for adaptive patcher: name, file_offset, expected_original, length
    if expected_map is None:
        expected_map = _build_expected_map(fmt)
    fat_off = (bin_info or {}).get('fat_offset') or 0
    patches = []
    for name in _all_offset_names():
        if name not in results:
            continue
        file_off = results[name] - adj + fat_off
        expected_hex, length = expected_map.get(name, (None, 0))
        patches.append({
            "name": name,
            "file_offset": file_off,
            "file_offset_hex": hex(file_off),
            "expected_original": expected_hex.replace(' ', '') if expected_hex else None,
            "length": length,
        })
    out["patches"] = patches

    # Injection sites for hp_cutoff / dc_reject (offset and size)
    if fmt in ('elf', 'macho'):
        inject = []
        for name, size in [("HighpassCutoffFilter", 0x100), ("DcReject", 0x1B6)]:
            if name in results:
                file_off = results[name] - adj + fat_off
                inject.append({
                    "name": name,
                    "file_offset": file_off,
                    "file_offset_hex": hex(file_off),
                    "inject_size": size,
                })
        out["injection_sites"] = inject

    # macOS stereo mic patches (when applicable)
    if fmt == 'macho' and 'stereo_patches' in bin_info:
        out["stereo_patches"] = bin_info["stereo_patches"]

    return json.dumps(out, indent=2)

# endregion Output Formatters


# region Visualization

def generate_viz_graph(results, out_dir):
    """Generate dependency graph PNG (requires networkx + matplotlib)."""
    if not VIZ_AVAILABLE:
        return None
    try:
        G = nx.DiGraph()
        sig_names = {s.name for s in SIGNATURES}
        for name in results:
            color = '#5865F2' if name in sig_names else '#ED4245'
            G.add_node(name, color=color)
        for derived, paths in DERIVATIONS.items():
            if derived not in results:
                continue
            for anchor, delta in paths:
                if anchor in results:
                    G.add_edge(anchor, derived, label=f"+0x{delta:X}")
                    break
        if len(G.nodes) == 0:
            return None

        plt.figure(figsize=(14, 9))
        pos = nx.spring_layout(G, k=2.5, iterations=60, seed=42)
        colors = [G.nodes[n].get('color', '#99AAB5') for n in G.nodes()]
        nx.draw(G, pos, with_labels=True, node_color=colors, node_size=2800,
                font_size=7, font_weight='bold', arrows=True, edge_color='#72767D',
                arrowsize=15, font_color='white', edgecolors='#2C2F33', linewidths=1.5)
        edge_labels = nx.get_edge_attributes(G, 'label')
        nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=7, font_color='#B9BBBE')
        plt.title("Offset Derivation Graph", fontsize=14, fontweight='bold', color='#FFFFFF')
        plt.gca().set_facecolor('#36393F')
        plt.gcf().set_facecolor('#2C2F33')
        plt.axis('off')

        viz_path = out_dir / 'offsets_graph.png'
        plt.savefig(viz_path, dpi=150, bbox_inches='tight', facecolor='#2C2F33')
        plt.close()
        return viz_path
    except Exception:
        try:
            plt.close()
        except Exception:
            pass
        return None

# endregion Visualization


# region Auto-Detection

def find_discord_node():
    """Try to find discord_voice.node in standard install locations.

    Supports Windows, macOS, and Linux (including Flatpak, Snap, AppImage).
    """
    clients = ['discord', 'discordcanary', 'discordptb', 'discorddevelopment']
    clients_cap = ['Discord', 'DiscordCanary', 'DiscordPTB', 'DiscordDevelopment']

    def _search_modules_dirs(base):
        """Search for discord_voice.node in a Discord install directory tree."""
        if not base.exists():
            return None
        for app_dir in sorted(base.glob('app-*'), reverse=True):
            modules = app_dir / 'modules'
            if not modules.exists():
                continue
            for vd in modules.glob('discord_voice*'):
                for candidate in [vd / 'discord_voice' / 'discord_voice.node', vd / 'discord_voice.node']:
                    if candidate.exists():
                        return candidate
        # Also check direct modules/ without app-* (some layouts)
        modules = base / 'modules'
        if modules.exists():
            for vd in modules.glob('discord_voice*'):
                for candidate in [vd / 'discord_voice' / 'discord_voice.node', vd / 'discord_voice.node']:
                    if candidate.exists():
                        return candidate
        return None

    def _search_recursive(base, max_depth=5):
        """Recursively search for discord_voice.node under a base path."""
        if not base.exists():
            return None
        for candidate in base.rglob('discord_voice.node'):
            # Limit depth to avoid scanning entire filesystem
            try:
                rel = candidate.relative_to(base)
                if len(rel.parts) <= max_depth:
                    return candidate
            except ValueError:
                pass
        return None

    # ─── Windows ──────────────────────────────────────────────────
    if sys.platform == 'win32':
        localappdata = os.environ.get('LOCALAPPDATA', '')
        if localappdata:
            for client in clients_cap:
                found = _search_modules_dirs(Path(localappdata) / client)
                if found:
                    return found

    # ─── macOS ────────────────────────────────────────────────────
    elif sys.platform == 'darwin':
        home = Path.home()

        # /Applications/Discord*.app/Contents/Resources/app-*/modules/...
        for app_name in ['Discord', 'Discord Canary', 'Discord PTB', 'Discord Development']:
            app_path = Path(f'/Applications/{app_name}.app/Contents/Resources')
            if app_path.exists():
                found = _search_modules_dirs(app_path)
                if found:
                    return found
                # Also check Frameworks directory
                found = _search_recursive(app_path.parent / 'Frameworks', max_depth=6)
                if found:
                    return found

        # ~/Library/Application Support/discord*/...
        app_support = home / 'Library' / 'Application Support'
        for client in clients:
            found = _search_modules_dirs(app_support / client)
            if found:
                return found

        # Homebrew cask installs
        for cask_dir in [Path('/usr/local/Caskroom'), Path('/opt/homebrew/Caskroom')]:
            if cask_dir.exists():
                for d in cask_dir.glob('discord*'):
                    found = _search_recursive(d, max_depth=8)
                    if found:
                        return found

        print("  Typical macOS locations:")
        print("    /Applications/Discord.app/Contents/Resources/app-*/modules/discord_voice*/")
        print("    ~/Library/Application Support/discord/*/modules/discord_voice*/")

    # ─── Linux ────────────────────────────────────────────────────
    else:
        home = Path.home()

        # Standard config: ~/.config/discord*/...
        config_dir = home / '.config'
        for client in clients:
            found = _search_modules_dirs(config_dir / client)
            if found:
                return found

        # Flatpak: ~/.var/app/com.discordapp.Discord/...
        flatpak_base = home / '.var' / 'app'
        for flatpak_id in ['com.discordapp.Discord', 'com.discordapp.DiscordCanary']:
            flatpak = flatpak_base / flatpak_id
            if flatpak.exists():
                # Search config dir within flatpak
                for sub in ['config/discord', 'config/discordcanary', '.config/discord', '.config/discordcanary']:
                    found = _search_modules_dirs(flatpak / sub)
                    if found:
                        return found
                # Recursive fallback
                found = _search_recursive(flatpak, max_depth=8)
                if found:
                    return found

        # Snap: /snap/discord/current/... or ~/snap/discord/...
        for snap_base in [Path('/snap'), home / 'snap']:
            for client in ['discord', 'discord-canary']:
                snap_dir = snap_base / client
                if snap_dir.exists():
                    found = _search_recursive(snap_dir, max_depth=8)
                    if found:
                        return found

        # System installs: /opt/discord*, /usr/share/discord*, /usr/lib/discord*
        for sys_base in ['/opt', '/usr/share', '/usr/lib']:
            for pattern in ['discord*', 'Discord*']:
                for d in Path(sys_base).glob(pattern):
                    if d.is_dir():
                        found = _search_recursive(d, max_depth=6)
                        if found:
                            return found

        # AppImage extracted directories
        for d in home.glob('.discord*'):
            found = _search_recursive(d, max_depth=6)
            if found:
                return found

        # /tmp AppImage mounts
        for d in Path('/tmp').glob('.mount_Discord*'):
            found = _search_recursive(d, max_depth=6)
            if found:
                return found

        print("  Typical Linux locations:")
        print("    ~/.config/discord/*/modules/discord_voice*/")
        print("    ~/.var/app/com.discordapp.Discord/config/discord/*/modules/discord_voice*/  (Flatpak)")
        print("    /snap/discord/current/usr/share/discord/modules/discord_voice*/  (Snap)")
        print("    /opt/discord/modules/discord_voice*/  (deb/rpm)")

    return None

# endregion Auto-Detection


# region Main

def main():
    # Parse --json and --export (optional)
    json_only = False
    export_path = None
    args = [a for a in sys.argv[1:] if a not in ('--json', '--export')]
    for i, a in enumerate(sys.argv[1:], start=0):
        if a == '--json':
            json_only = True
        elif a == '--export' and i + 2 <= len(sys.argv):
            export_path = sys.argv[i + 2]
    if '--export' in sys.argv:
        idx = sys.argv.index('--export')
        if idx + 1 < len(sys.argv):
            export_path = sys.argv[idx + 1]
    file_arg = None
    for a in sys.argv[1:]:
        if a in ('--json', '--export'):
            continue
        if a.startswith('-'):
            continue
        file_arg = a
        break

    if not json_only:
        print("=" * 65)
        print(f"  Discord Voice Node Offset Finder v{VERSION}")
        print("  Cross-platform tiered scanning with chain-aware derivation")
        print("=" * 65)

    if file_arg:
        file_path = Path(file_arg)
    else:
        if json_only:
            print("Error: --json requires a file path (or use without --json to auto-detect)", file=sys.stderr)
            sys.exit(1)
        print("\nNo file specified, searching for Discord install...")
        file_path = find_discord_node()
        if file_path:
            print(f"  Found: {file_path}")
        else:
            print("  Not found. Usage: python discord_voice_node_offset_finder.py <path>")
            sys.exit(1)

    if not file_path.exists():
        print(f"\nERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    # When --json, suppress all stdout until we print JSON
    saved_stdout = None
    if json_only:
        saved_stdout = sys.stdout
        sys.stdout = StringIO()

    data = file_path.read_bytes()
    file_size = len(data)
    if not json_only:
        print(f"\n  File: {file_path}")
        print(f"  Size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
        print(f"  MD5:  {hashlib.md5(data).hexdigest()}")

    # ─── Format detection ──────────────────────────────────────────
    bin_info = detect_binary_format(data)
    fmt = bin_info.get('format', 'raw')
    adj = bin_info.get('file_offset_adjustment', 0)
    arch = bin_info.get('arch', 'unknown')

    if not json_only:
        print(f"\n  Binary Format:       {fmt.upper()}")
        print(f"  Architecture:        {arch}")

    if not json_only and bin_info.get('note'):
        print(f"  NOTE: {bin_info['note']}")

    if not json_only and fmt == 'pe':
        print(f"  PE Image Base:       0x{bin_info['image_base']:X}")
        if 'build_time' in bin_info:
            print(f"  PE Timestamp:        {bin_info['build_time'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        ts = bin_info.get('text_section')
        if ts:
            print(f"  Offset Adjustment:   0x{adj:X}  (.text VA 0x{ts['vaddr']:X} - raw 0x{ts['raw_offset']:X})")
        else:
            print(f"  Offset Adjustment:   0x{adj:X}  (fallback)")
        for s in bin_info.get('sections', []):
            print(f"    {s['name']:8s}  VA=0x{s['vaddr']:08X}  Size=0x{s['raw_size']:08X}  Raw=0x{s['raw_offset']:08X}")

    elif not json_only and fmt == 'elf':
        ts = bin_info.get('text_section')
        if ts:
            print(f"  Offset Adjustment:   0x{adj:X}  (.text VA 0x{ts['vaddr']:X} - raw 0x{ts['raw_offset']:X})")
        else:
            print(f"  Offset Adjustment:   0x{adj:X}")
        n_func = len(bin_info.get('func_symbols', {}))
        has_sym = bin_info.get('has_symbols', False)
        print(f"  Symbol Table:        {'YES' if has_sym else 'NO'} ({n_func} function symbols)")
        if has_sym:
            print(f"  NOTE: Debug symbols present — using symbol table shortcut for offset resolution")

    elif not json_only and fmt == 'macho':
        ts = bin_info.get('text_section')
        if ts:
            print(f"  Offset Adjustment:   0x{adj:X}  (__TEXT,__text VA 0x{ts['vaddr']:X} - raw 0x{ts['raw_offset']:X})")
        else:
            print(f"  Offset Adjustment:   0x{adj:X}")
        if bin_info.get('fat_offset'):
            print(f"  Fat Binary:          x86_64 slice at offset 0x{bin_info['fat_offset']:X} ({bin_info.get('fat_size', 0):,} bytes)")
        has_sym = bin_info.get('has_symbols', False)
        if has_sym:
            n_func = len(bin_info.get('func_symbols', {}))
            print(f"  Symbol Table:        YES ({n_func} function symbols)")

    elif not json_only and fmt == 'raw':
        print(f"  WARNING: Could not parse binary format — using raw scan (adj=0)")

    # ─── Backward compat: create pe_info alias for functions that expect it ──
    pe_info = bin_info if fmt == 'pe' else None

    # ─── macOS Stereo Patch Finder (fat binary only) ────────────────────────
    stereo_patches = []
    if fmt == 'macho':
        stereo_patches = find_macos_stereo_patches(data)
        if stereo_patches:
            bin_info["stereo_patches"] = stereo_patches

    # ─── Run pipeline ──────────────────────────────────────────────
    results, errors, adj, tiers_used = discover_offsets(data, bin_info)
    verified, warnings = validate_offsets(data, results, adj, bin_fmt=fmt, quiet=json_only)
    check_injection_sites(data, results, adj, quiet=json_only)

    # ─── JSON export (--json or --export) ──────────────────────────
    expected_map = _build_expected_map(fmt)
    json_str = format_json(results, bin_info, file_path, file_size, adj, tiers_used, expected_map=expected_map)
    if json_only:
        if saved_stdout is not None:
            sys.stdout = saved_stdout
        print(json_str)
        return 0 if len(results) >= 15 else 1
    if export_path:
        Path(export_path).write_text(json_str, encoding='utf-8')
        print(f"\n  JSON exported to: {export_path}")

    # ─── Cross-validation ──────────────────────────────────────────
    xval_warnings = _cross_validate(results, adj, data, tiers_used=tiers_used)
    if xval_warnings:
        print("\n" + "=" * 65)
        print("  PHASE 5: Cross-Validation")
        print("=" * 65)
        for w in xval_warnings:
            print(f"  [XVAL] {w}")

    # ─── Visualization ─────────────────────────────────────────────
    if len(results) >= 10:
        viz_path = generate_viz_graph(results, file_path.parent)
        if viz_path:
            print(f"\n  Dependency graph saved: {viz_path}")

    # ─── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  RESULTS SUMMARY")
    print("=" * 65)
    print(f"  Format:           {fmt.upper()} ({arch})")
    print(f"  Offsets found:    {len(results)} / 18")
    print(f"  Bytes verified:   {verified}")
    print(f"  Warnings:         {warnings}")
    print(f"  Cross-validation: {len(xval_warnings)} issue(s)" if xval_warnings else "  Cross-validation: clean")
    print(f"  Errors:           {len(errors)}")

    # Show resolution tier breakdown
    tier_counts = {}
    for name, tier in tiers_used.items():
        bucket = tier.split('(')[0].split('-')[0]
        tier_counts[bucket] = tier_counts.get(bucket, 0) + 1
    if tier_counts:
        print(f"  Resolution:       {', '.join(f'{k}: {v}' for k, v in sorted(tier_counts.items()))}")

    if errors:
        print(f"\n  Failed offsets:")
        for name, err in errors:
            print(f"    {name}: {err}")

    # ─── Results Table (dual offset for non-PE) ────────────────────
    if results and fmt != 'pe':
        print("\n" + "=" * 65)
        print("  OFFSET TABLE (config VA / file offset)")
        print("=" * 65)
        print(f"  {'Name':<45s} {'config_va':>12s} {'file_offset':>12s}  tier")
        print(f"  {'─'*45} {'─'*12} {'─'*12}  {'─'*20}")
        for name in _all_offset_names():
            if name in results:
                config_off = results[name]
                file_off = config_off - adj
                tier = tiers_used.get(name, '?')
                print(f"  {name:<45s} 0x{config_off:>08X}  0x{file_off:>08X}  [{tier}]")
            else:
                print(f"  {name:<45s} {'NOT FOUND':>12s}")
        print(f"\n  # Note: on macOS/Linux use the 'file_offset' values for direct binary patching")

    # ─── Output ────────────────────────────────────────────────────
    if results:
        ps_config = format_powershell_config(results, bin_info, file_path, file_size)
        print("\n" + "=" * 65)
        print("  PATCHER OFFSET TABLE (copy-paste into patcher)")
        print("=" * 65)
        print(ps_config)

        # Non-PE: also show file offsets block
        if fmt != 'pe':
            print("\n    # File offsets for direct binary patching (hex editor):")
            print("    FileOffsets = @{")
            for name in _all_offset_names():
                pad = " " * (max(len(n) for n in _all_offset_names()) - len(name))
                if name in results:
                    file_off = results[name] - adj
                    print(f"        {name}{pad} = 0x{file_off:X}")
                else:
                    print(f"        {name}{pad} = 0x0  # NOT FOUND")
            print("    }")

        stub_line = ""
        if fmt == 'pe' and bin_info and "HighpassCutoffFilter" in results:
            hpc_va = bin_info['image_base'] + results["HighpassCutoffFilter"]
            va_bytes = struct.pack('<Q', hpc_va)
            stub = b'\x48\xB8' + va_bytes + b'\xC3'
            stub_line = f"\n  HighPassFilter stub: {stub.hex(' ')}\n    mov rax, 0x{hpc_va:X}; ret"
            print(stub_line)

        # ─── macOS Stereo Patch Table (when applicable) ─────────────────
        if fmt == 'macho' and stereo_patches:
            print("\n" + "=" * 65)
            print("  macOS STEREO MIC PATCH TABLE (x86_64 + arm64)")
            print("=" * 65)
            print(f"  {'#':<3} {'Arch':<8} {'Fat Offset':<14} {'Orig->Patch':<30} {'Name'}")
            print(f"  {'-'*3} {'-'*8} {'-'*14} {'-'*30} {'-'*30}")
            for i, p in enumerate(stereo_patches, 1):
                print(f"  {i:<3} {p['arch']:<8} 0x{p['fat_offset']:08X}     {p['orig']}->{p['patch']:<20} {p['name']}")
            print(f"\n  Total: {len(stereo_patches)} stereo patches (fat_offset = direct file offset for patching)")

                # Save offsets.txt
        script_dir = Path(__file__).resolve().parent
        file_content = [ps_config]
        if fmt != 'pe':
            file_content.append("\n# File offsets for direct binary patching:")
            for name in _all_offset_names():
                if name in results:
                    file_content.append(f"# {name} = file:0x{results[name] - adj:X}  config:0x{results[name]:X}")

        for try_dir in [script_dir, file_path.parent, Path.cwd()]:
            try:
                out_path = try_dir / "offsets.txt"
                out_path.write_text("\n".join(file_content))
                print(f"\n  Offset file saved: {out_path}")
                break
            except Exception:
                continue

        try:
            json_path = file_path.with_suffix('.offsets.json')
            json_path.write_text(format_json(results, bin_info, file_path, file_size, adj, tiers_used, expected_map=_build_expected_map(fmt)))
            print(f"  JSON saved: {json_path}")
        except Exception:
            pass

    # ─── Exit code ─────────────────────────────────────────────────
    if len(results) == 18:
        print("\n  *** ALL 18 OFFSETS FOUND SUCCESSFULLY ***")
        return 0
    elif len(results) >= 15:
        print(f"\n  *** PARTIAL SUCCESS: {len(results)}/18 offsets found ***")
        return 1
    else:
        print(f"\n  *** INSUFFICIENT RESULTS: {len(results)}/18 offsets found ***")
        return 2


if __name__ == '__main__':
    code = main()
    if sys.stdin.isatty() and sys.platform == 'win32':
        input("\n  Press Enter to close...")
    sys.exit(code)

# endregion Main
