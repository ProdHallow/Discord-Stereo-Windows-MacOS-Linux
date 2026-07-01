#!/usr/bin/env python3

import sys
import os
import io
import atexit
import struct
import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    import networkx as nx
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    VIZ_AVAILABLE = True
except ImportError:
    VIZ_AVAILABLE = False

VERSION = "5.12.0"

TARGET_BITRATE_BPS = 248000
_BITRATE_LE = TARGET_BITRATE_BPS.to_bytes(4, "little")
BITRATE_PATCH_3 = " ".join(f"{b:02X}" for b in _BITRATE_LE[:3])
BITRATE_PATCH_4 = " ".join(f"{b:02X}" for b in _BITRATE_LE)
BITRATE_PATCH_5 = BITRATE_PATCH_4 + " 00"
STOCK_MAX_BITRATE_LE = (512048).to_bytes(4, "little")
TIER_EBP_IMMS = (0x2EE0, 0x4E20, 0x7D00)
TIER_R8D_IMMS = (32000, 48000, 60000)
FLAT_EBP248K_PATCH = "BD C0 C8 03 00 90"
FLAT_R8D248K_PATCH = "41 B8 C0 C8 03 00 90"

DERIVATIONS = {
    "CommitAudioCodec_SuccessBranch_Jmp": [
        ("CommitAudioCodec_ChannelCount_Imm02", 0xC),
        ("CommitAudioCodec_ChannelCount_Imm02", 0x1),
    ],
    "SelectSampleRate_Cmov48k_Nop3": [
        ("CommitAudioCodec_ChannelCount_Imm02", 0x168),
    ],
    "ApplySettings_BitrateCalcLow_Channels_Mov248k": [
        ("CommitAudioCodec_ChannelCount_Imm02", 0x42B),
    ],
    "ApplySettings_BitrateCalcMid_Channels_Mov248k": [
        ("ApplySettings_BitrateCalcLow_Channels_Mov248k", 0x1D),
    ],
    "ApplySettings_BitrateCalcHigh_Channels_Mov248k": [
        ("ApplySettings_BitrateCalcLow_Channels_Mov248k", 0x32),
    ],
    "ApplySettings_MaxAvgBitrateClamp248k_Cmp": [
        ("ApplySettings_BitrateCalcLow_Channels_Mov248k", 0x10A),
    ],
    "ApplySettings_MaxAvgBitrateClamp248k_Mov": [
        ("ApplySettings_MaxAvgBitrateClamp248k_Cmp", 0x6),
    ],
    "RecreateEncoder_BitrateCalcLow_Channels_Mov248k": [
        ("ApplySettings_BitrateCalcLow_Channels_Mov248k", 0x4EE6),
    ],
    "RecreateEncoder_BitrateCalcMid_Channels_Mov248k": [
        ("RecreateEncoder_BitrateCalcLow_Channels_Mov248k", 0x1D),
    ],
    "RecreateEncoder_BitrateCalcHigh_Channels_Mov248k": [
        ("RecreateEncoder_BitrateCalcLow_Channels_Mov248k", 0x32),
    ],
    "SetBitrateClamp_Max248k_Cmp": [
        ("RecreateEncoder_BitrateCalcHigh_Channels_Mov248k", 0xD8),
    ],
    "SetBitrateClamp_Max248k_Mov": [
        ("SetBitrateClamp_Max248k_Cmp", 0x6),
    ],
    "GetMultipliedBitrate_Entry_IdentityRet": [
        ("GetMultipliedBitrate_Mulss_Nop7", -0x3D),
    ],
    "SetTargetBitrate_Mulss_Nop6": [
        ("SetBitrate_Imm64_Imm248k", 0x40),
    ],
    "SetTargetBitrate_ClampMax248k_Cmp": [
        ("SetBitrate_Imm64_Imm248k", -0x3C),
        ("SetTargetBitrate_Mulss_Nop6", -0x7C),
    ],
    "SetTargetBitrate_ClampMax248k_Mov": [
        ("SetTargetBitrate_ClampMax248k_Cmp", 0x6),
        ("SetTargetBitrate_Mulss_Nop6", -0x76),
    ],
    "EncoderOpusImpl_RelayClamp248k_Cmp": [
        ("SetTargetBitrate_Mulss_Nop6", 0x2FB),
    ],
    "EncoderOpusImpl_RelayClamp248k_Mov": [
        ("EncoderOpusImpl_RelayClamp248k_Cmp", 0x5),
    ],
    "WebRtcSplHighPass_Dispatch_MovRet": [
        ("CommitAudioCodec_ChannelCount_Imm02", 0xC275),
    ],
    "SetBitrate_OrMask_Nop3": [
        ("SetBitrate_Imm64_Imm248k", 0x8),
    ],
    "AudioEncoderOpusConfig_IsOK_MovTrueRet": [
        ("AudioEncoderOpusConfig_Ctor_Channels_Imm02", 0x29C),
        ("AudioEncoderOpusConfig_Ctor_Channels_Imm02", 0x19B),
        ("AudioEncoderOpusConfig_Ctor_Channels_Imm02", 0x30B),
    ],
    "dc_reject_Callback_InjectShellcode": [
        ("hp_cutoff_Callback_InjectShellcode", 0x1E0),
        ("hp_cutoff_Callback_InjectShellcode", 0x1B0),
    ],
    "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k": [
        ("AudioEncoderOpusConfig_Ctor_Channels_Imm02", 0xA),
    ],
    "AudioEncoderOpusConfig_Ctor_FrameMs_Imm10": [
        ("AudioEncoderOpusConfig_Ctor_Channels_Imm02", -0xF),
    ],
    "AudioEncoderOpusConfig_Ctor_Application_ImmAudio": [
        ("AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k", 0xB),
    ],
}

_PHASE2_SKIP_CLANG = frozenset({
    "ApplySettings_BitrateCalcLow_Channels_Mov248k",
    "ApplySettings_BitrateCalcMid_Channels_Mov248k",
    "ApplySettings_BitrateCalcHigh_Channels_Mov248k",
    "RecreateEncoder_BitrateCalcLow_Channels_Mov248k",
    "RecreateEncoder_BitrateCalcMid_Channels_Mov248k",
    "RecreateEncoder_BitrateCalcHigh_Channels_Mov248k",
    "AudioBitrateAdaptorCalc32k_Channels_Mov248k",
    "AudioBitrateAdaptorCalc48k_Channels_Mov248k",
    "AudioBitrateAdaptorCalc60k_Channels_Mov248k",
})

SLIDING_WINDOW_DEFAULT = 128
SLIDING_WINDOW_OVERRIDES = {
    "CommitAudioCodec_SuccessBranch_Jmp": 48,
    "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k": 48,
    "ApplySettings_BitrateCalcLow_Channels_Mov248k": 0x1000,
}

class Signature:

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


def _celt_default_mode_disambiguator(data, match_offset):
    # The default `st->mode = 1001` (0x3E9) store appears in three libopus init
    # routines (opus_encoder_init, opus_multistream..., celt variant). Only
    # opus_encoder_init also writes `user_forced_mode = -1000`
    # (REX.W C7 /0 [reg+0x88], 0xFFFFFC18) a short distance before it. Anchor on
    # that globally-unique store so we pick the real opus_encoder_init site.
    start = max(0, match_offset - 0x200)
    tail = b"\x88\x00\x00\x00\x18\xFC\xFF\xFF"
    pos = data.find(tail, start, match_offset)
    while pos != -1:
        if pos >= 3 and data[pos - 3] == 0x48 and data[pos - 2] == 0xC7:
            return True
        pos = data.find(tail, pos + 1, match_offset)
    return False


def _mono_downmixer_disambiguator(data, match_offset):
    if match_offset + 8 + 13 <= len(data):
        if data[match_offset + 8:match_offset + 8 + 13] == b'\x90' * 13:
            return False
    jg_pos = match_offset + 19
    if jg_pos + 6 > len(data):
        return False
    if b'\x44\x0f\xb6' in data[jg_pos + 6 : jg_pos + 18]:
        return True
    if b'\x44\x0f\xb6' in data[jg_pos + 6 : jg_pos + 70]:
        return True
    return False


def _ess1_no_duplicate_cmp_in_next_24(data, match_offset):
    if match_offset + 18 + 24 > len(data):
        return True
    chunk = data[match_offset + 18 : match_offset + 18 + 24]
    pos = 0
    while pos <= len(chunk) - 8:
        if chunk[pos:pos+3] == b'\x80\xBC\x24' and chunk[pos+7] == 0x01:
            return False
        pos += 1
    return True


def has_nearby_stereo_setter(data, file_offset, window=120):
    if not isinstance(data, (bytes, bytearray)) or file_offset < 0:
        return False
    start = max(0, file_offset - window)
    end = min(len(data) - 8, file_offset + window)
    for pos in range(start, end):
        if data[pos:pos + 3] != b'\xC6\x84\x24':
            continue
        disp = struct.unpack_from('<I', data, pos + 3)[0]
        imm = data[pos + 7]
        if imm in (0, 1, 2) and 0x140 <= disp <= 0x1C0:
            return True
    return False


SIGNATURES = [
    Signature(
        name="CommitAudioCodec_ChannelCount_Imm02",
        pattern_hex="E8 ?? ?? ?? ?? BD ?? 00 00 00 80 BC 24 80 01 00 00 01",
        target_offset=6,
        description="Stereo channel count: call <rel>; mov ebp, CHANNELS; cmp byte [rsp+0x180], 1",
        expected_original="01",
        patch_bytes="02",
        alt_patterns=[
            ("E8 ?? ?? ?? ?? BD ?? 00 00 00 80 BC 24 ?? ?? 00 00 01", 6),
            ("BD ?? 00 00 00 80 BC 24 ?? ?? 00 00 01", 1),
        ],
    ),

    Signature(
        name="AudioEncoderOpusConfig_Ctor_Channels_Imm02",
        pattern_hex="48 B9 14 00 00 00 80 BB 00 00 48 89 08 48 C7 40 08 ?? 00 00 00",
        target_offset=17,
        description="Opus config: mov rcx, {48000<<32|20}; mov [rax],rcx; mov qword [rax+8], CHANNELS",
        expected_original="01",
        patch_bytes="02",
        alt_patterns=[
            ("48 B9 14 00 00 00 80 BB 00 00 48 89 08 48 C7 40 ?? ?? 00 00 00", 17),
            ("48 B9 14 00 00 00 80 BB 00 00 48 89 ?? 48 C7 ?? ?? ?? 00 00 00", 17),
        ],
    ),

    Signature(
        name="CapturedAudioProcessor_MonoDownmix_NopJmp",
        pattern_hex="48 89 F9 E8 ?? ?? ?? ?? 84 C0 74 0D 83 BE ?? ?? 00 00 09 0F 8F",
        target_offset=8,
        description="Mono downmix gate: mov rcx,rdi; call; test al,al; jz +0xD; cmp [rsi+??], 9; jg",
        expected_original="84 C0 74 0D",
        patch_bytes="90 90 90 90 90 90 90 90 90 90 90 90 E9",
        patch_len=13,
        disambiguator=_mono_downmixer_disambiguator,
        alt_patterns=[
            ("48 89 ?? E8 ?? ?? ?? ?? 84 C0 ?? ?? 83 ?? ?? ?? 00 00 09 0F 8F", 8),
            ("4C 89 ?? E8 ?? ?? ?? ?? 84 C0 74 ?? 83 7B ?? 09 0F 8F", 8),
            ("4C 89 ?? E8 ?? ?? ?? ?? 84 C0 74 ?? 83 7B ?? 09 7F", 8),
        ],
    ),

    Signature(
        name="SetBitrate_Imm64_Imm248k",
        pattern_hex="89 F8 48 B9 ?? ?? ?? ?? 01 00 00 00 48 09 C1 48 89 4E 1C",
        target_offset=4,
        description="Bitrate setter: mov eax,edi; mov rcx,imm64; or rcx,rax; mov [rsi+0x1C],rcx",
        expected_original=None,
        alt_patterns=[
            ("89 F8 48 B9 ?? ?? ?? ?? 01 00 00 00 48 09 C1 48 89 ?? ??", 4),
            ("89 ?? 48 B9 ?? ?? ?? ?? 01 00 00 00 48 09 C1 48 89 ?? ??", 4),
        ],
    ),

    Signature(
        name="SetTargetBitrate_Mulss_Nop6",
        pattern_hex="F3 0F 2A C7 F3 0F 59 44 81 EC",
        target_offset=4,
        description="SetTargetBitrate: cvtsi2ss xmm0,edi; mulss xmm0,[rcx+rax*4-14h] (actual encode rate scale)",
        expected_original="F3 0F 59 44 81 EC",
        patch_bytes="90 90 90 90 90 90",
        patch_len=6,
        alt_patterns=[
            ("F3 0F 59 44 81 EC", 0),
        ],
    ),

    Signature(
        name="GetMultipliedBitrate_Mulss_Nop7",
        pattern_hex="F3 0F 2A C0 F3 41 0F 59 44 88 EC",
        target_offset=4,
        description="GetMultipliedBitrate (PE): cvtsi2ss xmm0,eax; mulss xmm0,[r8+rcx*4-14h]",
        expected_original="F3 41 0F 59 44 88 EC",
        patch_bytes="90 90 90 90 90 90 90",
        patch_len=7,
        alt_patterns=[
            ("F3 0F 2A C7 F3 0F 59 44 81 EC", 5),
            ("F3 0F 59 44 81 EC", 0),
            ("F3 41 0F 59 44 88 EC", 0),
        ],
    ),

    Signature(
        name="GetMultipliedBitrate_Entry_IdentityRet",
        pattern_hex="89 C8 48 63 C9 48 69 C9 ?? ?? ?? ??",
        target_offset=0,
        description="GetMultipliedBitrate entry: mov eax,ecx; movsxd rcx,eax; imul rcx,rdx,...",
        expected_original="89 C8",
        patch_bytes="8B C1 C3",
        patch_len=3,
        alt_patterns=[
            ("8B C1 48 63 C9", 0),
        ],
    ),

    Signature(
        name="CodecMismatchThrow_Entry_Ret",
        pattern_hex="56 56 57 53 48 81 EC C8 00 00 00 0F 29 B4 24 B0 00 00 00 4C 89 CE 4C 89 C7 89 D3",
        target_offset=-1,
        description="Error handler: push rsi;rdi;rbx; sub rsp,0xC8; movaps [rsp+0xB0],xmm6; ...",
        expected_original="41",
        patch_bytes="C3",
        alt_patterns=[
            ("56 56 57 53 48 81 EC ?? ?? 00 00 0F 29 B4 24 ?? ?? 00 00 4C 89 CE 4C 89 C7 89 D3", -1),
        ],
    ),

    Signature(
        name="ChannelDownmix_Entry_Ret",
        pattern_hex="57 41 56 41 55 41 54 56 57 55 53 48 83 EC 10 48 89 0C 24 45 85 C0",
        target_offset=-1,
        description="Downmix function: push r15..r12,rsi,rdi,rbp,rbx; sub rsp,0x10; ...",
        expected_original="41",
        patch_bytes="C3",
        alt_patterns=[
            ("57 41 56 41 55 41 54 56 57 55 53 48 83 EC ?? 48 89 0C 24 45 85 C0", -1),
            ("57 41 56 41 55 41 54 56 57 55 53 48 83 EC ?? 48 89 0C 24", -1),
        ],
    ),

    Signature(
        name="CreateAudioFrame_ChannelAssign_Mov",
        pattern_hex="B8 80 BB 00 00 BD 00 7D 00 00 0F 43 E8",
        target_offset=31,
        description="Audio frame: mov eax,48000; mov ebp,32000; cmovae ebp,eax; ... second cmov",
        expected_original="4C 0F 43 E8",
        patch_bytes="49 89 C5 90",
        alt_patterns=[
            ("B8 80 BB 00 00 BD 00 7D 00 00 0F ?? E8", 31),
        ],
    ),

    Signature(
        name="hp_cutoff_Callback_InjectShellcode",
        pattern_hex="56 48 83 EC 30 44 0F 29 44 24 20 0F 29 7C 24 10 0F 29 34 24",
        target_offset=0,
        description="HP cutoff filter: push rsi; sub rsp,0x30; SSE saves (xmm8,xmm7,xmm6)",
        expected_original="56 48 83 EC 30",
        patch_bytes=None,
        patch_len=0x100,
        alt_patterns=[
            ("56 48 83 EC ?? 44 0F 29 44 24 ?? 0F 29 7C 24 ?? 0F 29 34 24", 0),
        ],
    ),
    Signature(
        name="AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k",
        pattern_hex="48 B9 ?? ?? ?? ?? ?? ?? ?? ?? 48 89 48 10 66 C7 40 18 00 00 C6 40 1A 00",
        target_offset=6,
        description="Encoder config constructor 2: mov rcx,packed_qword; mov [rax+0x10],rcx; ...",
        expected_original="00 7D 00 00",
        patch_bytes=BITRATE_PATCH_4,
        patch_len=4,
        alt_patterns=[
            ("48 B9 ?? ?? ?? ?? ?? ?? ?? ?? 48 89 48 ?? 66 C7 40 ?? 00 00 C6 40 ?? 00", 6),
        ],
    ),

    Signature(
        name="AudioEncoderOpusConfig_Ctor_FrameMs_Imm10",
        pattern_hex="48 B9 14 00 00 00 80 BB 00 00 48 89 08 48 C7 40 08",
        target_offset=2,
        description="Opus config ctor: mov rcx,{48000|20ms}; frame_size_ms imm 20->10",
        expected_original="14",
        patch_bytes="0A",
        patch_len=1,
    ),

    Signature(
        name="AudioEncoderOpusConfig_Ctor_Application_ImmAudio",
        pattern_hex="C6 40 18 01 66 C7 40 1C 00 00",
        target_offset=3,
        description="Opus config ctor: mov byte [rax+18h],application; force kAudio=1",
        expected_original="01",
        patch_bytes="01",
        patch_len=1,
        alt_patterns=[
            ("C6 40 18 00 66 C7 40 1C 00 00", 3),
        ],
    ),

    Signature(
        name="CELT_Force",
        pattern_hex="48 C7 ?? 88 00 00 00 18 FC FF FF",
        target_offset=7,
        description="opus_encoder_init: mov [reg+0x88],user_forced_mode=-1000; force CELT_ONLY(1002). Globally unique store.",
        expected_original="18 FC FF FF",
        patch_bytes="EA 03 00 00",
        patch_len=4,
    ),

    Signature(
        name="CELT_DefaultMode",
        pattern_hex="C7 ?? 94 37 00 00 E9 03 00 00",
        target_offset=6,
        description="opus_encoder_init: mov dword [reg+0x3794],default mode=1001(HYBRID); force CELT_ONLY(1002).",
        expected_original="E9 03 00 00",
        patch_bytes="EA 03 00 00",
        patch_len=4,
        disambiguator=_celt_default_mode_disambiguator,
    ),
]

CLANG_ALT_PATTERNS = [
    ("CommitAudioCodec_ChannelCount_Imm02",
     "E8 ?? ?? ?? ?? BF ?? 00 00 00 80 ?? 24 ?? ?? 00 00 01", 6),
    ("CommitAudioCodec_ChannelCount_Imm02",
     "?? ?? 00 00 00 80 ?? 24 ?? ?? 00 00 01", 1),
    ("AudioEncoderOpusConfig_Ctor_Channels_Imm02",
     "48 B8 14 00 00 00 80 BB 00 00 48 89 ?? 48 C7 ?? ?? ?? 00 00 00", 17),
    ("AudioEncoderOpusConfig_Ctor_Channels_Imm02",
     "48 ?? 14 00 00 00 80 BB 00 00 48 89 ?? ?? 48 C7 ?? ?? ?? 00 00 00", 18),
    ("CapturedAudioProcessor_MonoDownmix_NopJmp",
     "48 89 FF E8 ?? ?? ?? ?? 84 C0 74 ?? 83 ?? ?? ?? 00 00 09 0F 8F", 8),
    ("CapturedAudioProcessor_MonoDownmix_NopJmp",
     "F3 0F 1E FA ?? 89 ?? E8 ?? ?? ?? ?? 84 C0 74 ?? 83 ?? ?? ?? 00 00 09 0F 8F", 12),
    ("CapturedAudioProcessor_MonoDownmix_NopJmp",
     "4C 89 ?? E8 ?? ?? ?? ?? 84 C0 74 ?? 83 7B ?? 09 0F 8F", 8),
    ("CapturedAudioProcessor_MonoDownmix_NopJmp",
     "4C 89 ?? E8 ?? ?? ?? ?? 84 C0 74 ?? 83 7B ?? 09 7F", 8),
    ("SetBitrate_Imm64_Imm248k",
     "89 F8 48 ?? ?? ?? ?? ?? 01 00 00 00 48 09 ?? 48 89 ?? ??", 4),
    ("SetBitrate_Imm64_Imm248k",
     "89 ?? 48 B8 ?? ?? ?? ?? 01 00 00 00 48 09 ?? 48 89 ?? ??", 4),
    ("CodecMismatchThrow_Entry_Ret",
     "55 48 89 E5 41 57 41 56 41 55 41 54 53 48 ?? EC ?? ?? 00 00", -1),
    ("CodecMismatchThrow_Entry_Ret",
     "F3 0F 1E FA 55 48 89 E5 41 57 41 56 41 55 41 54 53", 3),
    ("ChannelDownmix_Entry_Ret",
     "55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 EC ?? 45 85 C0", -1),
    ("ChannelDownmix_Entry_Ret",
     "F3 0F 1E FA 55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 EC ??", 3),
    ("ChannelDownmix_Entry_Ret",
     "41 57 41 56 41 55 41 54 55 53 48 83 EC ?? 49 89 ?? 45 85 ??", -1),
    ("CreateAudioFrame_ChannelAssign_Mov",
     "B8 80 BB 00 00 ?? ?? 00 7D 00 00 0F ?? ??", 31),
    ("hp_cutoff_Callback_InjectShellcode",
     "55 48 89 E5 ?? ?? EC ?? 0F 29 ?? ?? ?? 0F 29 ?? ?? ?? 0F 29", 0),
    ("hp_cutoff_Callback_InjectShellcode",
     "F3 0F 1E FA 56 48 83 EC ?? ?? 0F 29 ?? ?? ?? 0F 29 ?? ?? ?? 0F 29", 4),
    ("AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k",
     "48 ?? ?? ?? ?? ?? ?? ?? ?? ?? 48 89 ?? ?? 66 C7 ?? ?? 00 00 C6 ?? ?? 00", 6),
    ("SetBitrate_Imm64_Imm248k",
     "89 ?? 48 B9 00 00 00 00 01 00 00 00 48 09 C1", 4),
    ("CreateAudioFrame_ChannelAssign_Mov",
     "B8 80 BB 00 00 41 BD 00 7D 00 00 44 0F 43 E8", 31),
    ("CreateAudioFrame_ChannelAssign_Mov",
     "B8 80 BB 00 00 41 ?? 00 7D 00 00 ?? 0F 43 ??", 31),
]


def parse_pe(data):
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

    if magic == 0x20B:
        image_base = struct.unpack_from('<Q', data, opt + 24)[0]
    else:
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
        file_offset_adjustment = 0xC00
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



ELF_SYMBOL_MAP = {

    "CodecMismatchThrow_Entry_Ret": {
        "patterns": ["Environment5ThrowIJPKcEE", "Environment5Throw", "throw_error"],
        "at_start": True,
        "prefer_smallest": True,
    },
    "ChannelDownmix_Entry_Ret": {
        "patterns": ["downmix_and_resample"],
        "at_start": True,
    },
    "hp_cutoff_Callback_InjectShellcode": {
        "patterns": ["hp_cutoff"],
        "at_start": True,
    },
    "dc_reject_Callback_InjectShellcode": {
        "patterns": ["dc_reject"],
        "at_start": True,
    },
    "WebRtcSplHighPass_Dispatch_MovRet": {
        "patterns": ["InitializeHighPassFilter"],
        "at_start": True,
    },


    "CommitAudioCodec_ChannelCount_Imm02": {
        "patterns": ["LocalUser16CommitAudioCodecEv",
                     "LocalUser13ApplySettings"],
        "at_start": False,
        "linux_scan": "stereo_cmp_byte",
        "prefer_largest": True,
    },
    "CreateAudioFrame_ChannelAssign_Mov": {
        "patterns": ["CreateAudioFrameToProcess", "CreateAudioFrame"],
        "at_start": False,
        "linux_scan": "channel_cmov",
    },
    "AudioEncoderOpusConfig_Ctor_Channels_Imm02": {
        "patterns": ["AudioEncoderOpusConfigC1Ev", "AudioEncoderOpusConfigC2Ev",
                     "OpusConfigC1", "OpusConfigC2"],
        "at_start": False,
        "linux_scan": "opus_config_channels",
    },
    "OpusEncoderConfig_SetMultiChannelStereo": {
        "patterns": [
            "AudioEncoderMultiChannelOpusConfigC1Ev",
            "AudioEncoderMultiChannelOpusConfigC2Ev",
            "AudioEncoderMultiChannelOpusConfig",
            "MultiChannelOpusConfig",
        ],
        "at_start": False,
        "linux_scan": "multichannel_opus_config_channels",
    },
    "SetBitrate_Imm64_Imm248k": {
        "patterns": ["WebrtcAdmHelper22EnsureRecordingStarted",
                     "WebrtcAdmHelper20EnsurePlayoutStarted"],
        "exclude_patterns": ["__function", "__policy"],
        "at_start": False,
        "linux_scan": "bitrate_movabs_or",
    },
    "SetTargetBitrate_Mulss_Nop6": {
        "patterns": ["AudioEncoderOpusImpl16SetTargetBitrateEi",
                     "SetTargetBitrate"],
        "at_start": False,
        "linux_scan": "set_target_bitrate_mulss",
    },
    "GetMultipliedBitrate_Mulss_Nop7": {
        "patterns": ["GetMultipliedBitrateEiRKNSt4__Cr6vectorIfNS",
                     "GetMultipliedBitrate"],
        "at_start": False,
        "linux_scan": "get_multiplied_bitrate_mulss",
    },
    "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k": {
        "patterns": ["AudioEncoderOpusConfigC1Ev", "AudioEncoderOpusConfigC2Ev"],
        "at_start": False,
        "linux_scan": "opus_config_bitrate",
    },
    "CapturedAudioProcessor_MonoDownmix_NopJmp": {
        "patterns": ["CapturedAudioProcessor7Process"],
        "at_start": False,
        "linux_scan": "mono_downmix_test",
    },
    "CommitAudioCodec_SuccessBranch_Jmp": {
        "patterns": ["LocalUser16CommitAudioCodecEv",
                     "LocalUser13ApplySettings"],
        "at_start": False,
        "linux_scan": "stereo_success2_byte",
        "prefer_largest": True,
    },
    "SelectSampleRate_Cmov48k_Nop3": {
        "patterns": ["LocalUser16CommitAudioCodecEv",
                     "LocalUser13ApplySettings"],
        "at_start": False,
        "linux_scan": "emulate_48khz_cmov",
        "prefer_largest": True,
    },
}


def parse_elf(data):
    if len(data) < 64:
        return None

    if data[:4] != b'\x7fELF':
        return None

    ei_class = data[4]
    ei_data = data[5]
    if ei_class != 2 or ei_data != 1:
        if ei_class == 2 and ei_data == 2:
            return None
        if ei_class == 1:
            return None

    e_type = struct.unpack_from('<H', data, 16)[0]
    e_machine = struct.unpack_from('<H', data, 18)[0]
    e_entry = struct.unpack_from('<Q', data, 24)[0]
    e_shoff = struct.unpack_from('<Q', data, 40)[0]
    e_shentsize = struct.unpack_from('<H', data, 58)[0]
    e_shnum = struct.unpack_from('<H', data, 60)[0]
    e_shstrndx = struct.unpack_from('<H', data, 62)[0]

    if e_shoff == 0 or e_shnum == 0:
        return None

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
            'name': '',
        })

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

    text_section = None
    file_offset_adjustment = 0
    for sec in sections:
        if sec['name'] == '.text':
            text_section = sec
            file_offset_adjustment = sec['vaddr'] - sec['raw_offset']
            break

    if text_section is None:
        SHF_EXECINSTR = 0x4
        for sec in sections:
            if sec['flags'] & SHF_EXECINSTR and sec['vaddr'] > 0 and sec['raw_offset'] > 0:
                text_section = sec
                file_offset_adjustment = sec['vaddr'] - sec['raw_offset']
                break

    symbols = []
    SHT_SYMTAB = 2
    SHT_DYNSYM = 11
    for sec in sections:
        if sec['type'] not in (SHT_SYMTAB, SHT_DYNSYM):
            continue
        if sec['entsize'] == 0:
            continue
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

    func_symbols = {}
    for sym in symbols:
        if sym['is_func'] and sym['value'] > 0:
            func_symbols[sym['name']] = sym

    arch = 'x86_64' if e_machine == 0x3E else f'machine_{e_machine}'

    return {
        'format': 'elf',
        'image_base': 0,
        'file_offset_adjustment': file_offset_adjustment,
        'text_section': text_section,
        'sections': [{'name': s['name'], 'vaddr': s['vaddr'],
                       'raw_size': s['raw_size'], 'raw_offset': s['raw_offset']}
                      for s in sections if s['name']],
        'symbols': symbols,
        'func_symbols': func_symbols,
        'has_symbols': len(func_symbols) > 50,
        'arch': arch,
        'entry': e_entry,
    }




def parse_macho(data):
    if len(data) < 32:
        return None

    magic = struct.unpack_from('<I', data, 0)[0]

    FAT_MAGIC = 0xBEBAFECA
    FAT_MAGIC_64 = 0xBFBAFECA
    if magic in (FAT_MAGIC, FAT_MAGIC_64):
        return _parse_fat_macho(data)

    MH_MAGIC_64 = 0xFEEDFACF
    MH_MAGIC_64_BE = 0xCFFAEDFE

    if magic == MH_MAGIC_64:
        return _parse_macho_slice(data, 0)
    elif magic == MH_MAGIC_64_BE:
        return None
    elif struct.unpack_from('>I', data, 0)[0] in (0xCAFEBABE, 0xCAFEBABF):
        return _parse_fat_macho(data)

    return None


def _parse_fat_macho(data):
    nfat_arch = struct.unpack_from('>I', data, 4)[0]
    if nfat_arch > 20:
        return None

    CPU_TYPE_X86_64 = 0x01000007
    CPU_TYPE_ARM64 = 0x0100000C

    x86_result = None
    arm64_result = None

    for i in range(nfat_arch):
        off = 8 + i * 20
        if off + 20 > len(data):
            break
        cputype = struct.unpack_from('>I', data, off)[0]
        offset = struct.unpack_from('>I', data, off + 8)[0]
        size = struct.unpack_from('>I', data, off + 12)[0]

        if cputype == CPU_TYPE_X86_64 and offset + size <= len(data):
            result = _parse_macho_slice(data, offset)
            if result:
                result['fat_offset'] = offset
                result['fat_size'] = size
                x86_result = result

        elif cputype == CPU_TYPE_ARM64 and offset + size <= len(data):
            result = _parse_macho_slice(data, offset)
            if result:
                result['fat_offset'] = offset
                result['fat_size'] = size
                arm64_result = result

    # macOS patcher is ARM64-only — always prefer the Apple Silicon slice.
    if arm64_result is not None:
        return arm64_result

    if x86_result is not None:
        x86_result['intel_unsupported'] = True
        x86_result['note'] = (
            'Intel (x86_64) macOS slices are no longer supported. '
            'Use a universal/fat discord_voice.node that includes an ARM64 slice.'
        )
    return x86_result


def _parse_macho_slice(data, base_offset):
    magic = struct.unpack_from('<I', data, base_offset)[0]
    if magic != 0xFEEDFACF:
        return None

    cputype = struct.unpack_from('<I', data, base_offset + 4)[0]
    ncmds = struct.unpack_from('<I', data, base_offset + 16)[0]
    sizeofcmds = struct.unpack_from('<I', data, base_offset + 20)[0]

    CPU_TYPE_X86_64 = 0x01000007
    CPU_TYPE_ARM64 = 0x0100000C
    if cputype == CPU_TYPE_X86_64:
        arch = 'x86_64'
    elif cputype == CPU_TYPE_ARM64:
        arch = 'arm64'
    else:
        arch = f'cpu_{cputype:#x}'

    LC_SEGMENT_64 = 0x19
    LC_SYMTAB = 0x02

    sections = []
    text_section = None
    file_offset_adjustment = 0
    cmd_offset = base_offset + 32

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

    func_symbols = {}
    symbols = []
    NLIST_64_SIZE = 16
    if symtab_nsyms > 0 and symtab_off + symtab_nsyms * NLIST_64_SIZE <= len(data):
        strtab_end = strtab_off + strtab_size
        for i in range(min(symtab_nsyms, 200000)):
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
                is_defined = (n_type & 0x0e) == 0x0e
                sym = {'name': sym_name, 'value': n_value, 'is_func': is_defined and n_sect > 0, 'size': 0}
                symbols.append(sym)
                if sym['is_func']:
                    func_symbols[sym_name] = sym

    has_symbols = len(func_symbols) > 50

    if has_symbols:
        sorted_funcs = sorted(func_symbols.values(), key=lambda s: s['value'])
        for i, sym in enumerate(sorted_funcs):
            if i + 1 < len(sorted_funcs):
                gap = sorted_funcs[i + 1]['value'] - sym['value']
                sym['size'] = gap if 0 < gap < 0x100000 else 0
            else:
                sym['size'] = 0

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




def _parse_fat_macho_slices(data):
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


_ARM64_STEREO_SYMBOLS = [
    {
        "name": "MultiChannelOpusConfig_channels",
        "symbol": "AudioEncoderMultiChannelOpusConfigC1Ev",
        "search_insn": b"\x28\x00\x80\x52",
        "occurrence": 1, "scan_range": 64,
        "orig": "28", "patch": "48",
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
        "orig": "F6 57 BD A9", "patch": "C0 03 5F D6",
    },
    {
        "name": "StereoDownMixFrame",
        "symbol": "12DownMixFrameERKNS_10AudioFrameE",
        "search_insn": b"\x20\x01\x00\x34",
        "occurrence": 1, "scan_range": 64,
        "orig": "20 01 00 34", "patch": "1F 20 03 D5",
    },
    {
        "name": "StereoApplyAudioNetworkAdaptor",
        "symbol": "AudioEncoderOpusImpl24ApplyAudioNetworkAdaptor",
        "search_insn": b"\x41\x01\x00\x54",
        "occurrence": 1, "scan_range": 512,
        "orig": "41 01 00 54", "patch": "1F 20 03 D5",
    },
    {
        "name": "SdpToConfig_cinc1",
        "symbol": "AudioEncoderOpusImpl11SdpToConfig",
        "search_insn": b"\x15\x15\x88\x9A",
        "occurrence": 1, "scan_range": 512,
        "orig": "15 15 88 9A", "patch": "55 00 80 52",
    },
    {
        "name": "SdpToConfig_mov1",
        "symbol": "AudioEncoderOpusImpl11SdpToConfig",
        "search_insn": b"\x35\x00\x80\x52",
        "occurrence": 1, "scan_range": 512,
        "orig": "35", "patch": "55",
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
    {
        "name": "CommitAudioCodec_stereo_force",
        "symbol": "LocalUser16CommitAudioCodecEv",
        "search_insn": b"\x1F\x05\x00\x71",
        "occurrence": 2, "scan_range": 768,
        "orig": "1F 05 00 71", "patch": "1F 09 00 71",
    },
    {
        "name": "CommitAudioCodec_stereo_force2",
        "symbol": "LocalUser16CommitAudioCodecEv",
        "search_insn": b"\xE1\x00\x00\x54",
        "occurrence": 1, "scan_range": 768,
        "orig": "E1 00 00 54", "patch": "06 00 00 14",
    },
    {
        "name": "OpusConfig_IsOk",
        "symbol": "AudioEncoderOpusConfig4IsOkEv",
        "at_start": True,
        "orig": "08 00 40 B9 A9 99 99 52",
        "patch": "20 00 80 52 C0 03 5F D6",
    },
    {
        "name": "MultiChannelOpusConfig_IsOk",
        "symbol": "AudioEncoderMultiChannelOpusConfig4IsOkEv",
        "at_start": True,
        "orig": "FF 03 01 D1 F4 4F 02 A9",
        "patch": "20 00 80 52 C0 03 5F D6",
    },
    {
        "name": "CreateAudioFrame_channels1",
        "symbol": "CreateAudioFrameToProcess",
        "search_insn": b"\x3B\x00\x80\x52",
        "occurrence": 1, "scan_range": 256,
        "orig": "3B", "patch": "5B",
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
        "orig": "F6 57 BD A9", "patch": "C0 03 5F D6",
    },
    {
        "name": "NumProcChannels_force_stereo",
        "symbol": "AudioProcessingImpl17num_proc_channelsEv",
        "at_start": True,
        "orig": "08 B4 45 39 1F 05 00 71",
        "patch": "40 00 80 52 C0 03 5F D6",
    },
    {
        "name": "DownmixInterleavedToMono_bypass",
        "symbol": "DownmixInterleavedToMonoIsE",
        "at_start": True,
        "orig": "48 7C 40 93", "patch": "C0 03 5F D6",
    },
    {
        "name": "NoiseCanceller_bypass",
        "symbol": "NoiseCanceller7ProcessEPsmmmj",
        "at_start": True,
        "orig": "FF 03 02 D1", "patch": "C0 03 5F D6",
    },
    {
        "name": "CustomCapturePostproc_bypass",
        "symbol": "DiscordCustomAudioCapturePostproc7ProcessE",
        "symbol_alternates": ["CustomAudioCapturePostproc7ProcessE"],
        "search_insn": b"\xAE\x6C\xFF\x17",
        "occurrence": 1, "scan_range": 0x400,
        "orig": "AE 6C FF 17", "patch": "1F 20 03 D5",
    },
    {
        "name": "ProcessStream_bypass",
        "symbol": "AudioProcessingImpl13ProcessStreamEPKs",
        "search_insn": b"\xE1\x00\x00\x54",
        "occurrence": 1, "scan_range": 0x800,
        "orig": "E1 00 00 54", "patch": "1F 20 03 D5",
    },
    {
        "name": "CapturedAudioProcessor_MonoDownmix",
        "symbol": "CapturedAudioProcessor7Process",
        "search_insn": b"\x48\x02\x00\x37",
        "occurrence": 1, "scan_range": 0x2000,
        "orig": "48 02 00 37", "patch": "1F 20 03 D5",
    },
    {
        "name": "ChannelDownmix_Entry_Ret",
        "symbol": "downmix_and_resample",
        "prologue_scan": 48,
        "orig": "E9 23 B9 6D", "patch": "C0 03 5F D6",
    },
    {
        "name": "CodecMismatchThrow_Entry_Ret",
        "symbol": "Environment5ThrowIJPKcEE",
        "symbol_alternates": ["Environment5Throw"],
        "at_start": True,
        "orig": "FF 43 01 D1", "patch": "C0 03 5F D6",
    },
    {
        "name": "SelectSampleRate_Cmov48k_Nop3",
        "symbol": "LocalUser16CommitAudioCodecEv",
        "search_insn": b"\xE2\x17\x9F\x1A",
        "occurrence": 1, "scan_range": 0x1000,
        "orig": "E2 17 9F 1A", "patch": "1F 20 03 D5",
    },
    {
        "name": "CommitAudioCodec_ChannelCount_alt",
        "symbol": "LocalUser16CommitAudioCodecEv",
        "search_insn": b"\x1F\x05\x00\x71",
        "occurrence": 1, "scan_range": 0x1000,
        "orig": "1F 05 00 71", "patch": "1F 09 00 71",
    },
    {
        "name": "OpusConfig_FrameMs_Rodata",
        "constant_va": 0xA7DAC8,
        "orig": "14", "patch": "0A",
    },
    {
        "name": "OpusConfig_Bitrate_Rodata",
        "constant_va": 0xA7DAB8,
        "patch_offset": 4,
        "orig": "00 7D 00 00", "patch": "C0 C8 03 00",
    },
    # --- 248 kbps runtime default (LocalUser send-config) ---
    # CreateAudioStream / ApplySettings build the send bitrate as:
    #   LDR  Wx,[X8,#0x20]      ; user-configured bitrate
    #   MOV  Wy,#0xFA00 (64000) ; the real default Discord falls back to
    #   CMP  Wx,#0 ; CSEL Wx,Wx,Wy,GT
    # Rewriting the LDR+MOVZ pair into MOVZ Wx,#0xC8C0 + MOVK Wx,#3,LSL#16 forces
    # Wx = 248000 unconditionally; the surviving CMP/CSEL then always keeps it.
    # Site 1 (CreateAudioStream): LDR W8 + MOVZ W9 adjacent (MOVZ at +4).
    {
        "name": "RuntimeBitrate_Ldr_1",
        "symbol": "LocalUser17CreateAudioStreamEv",
        "search_insn": b"\x08\x21\x40\xB9\x09\x40\x9F\x52",
        "occurrence": 1, "scan_range": 0x400, "patch_offset": 0,
        "orig": "08 21 40 B9", "patch": "08 18 99 52",
    },
    {
        "name": "RuntimeBitrate_Movk_1",
        "symbol": "LocalUser17CreateAudioStreamEv",
        "search_insn": b"\x08\x21\x40\xB9\x09\x40\x9F\x52",
        "occurrence": 1, "scan_range": 0x400, "patch_offset": 4,
        "orig": "09 40 9F 52", "patch": "68 00 A0 72",
    },
    # Site 2 (ApplySettings): LDR W9 + MOVZ W10 adjacent (MOVZ at +4).
    {
        "name": "RuntimeBitrate_Ldr_2",
        "symbol": "LocalUser13ApplySettingsERKNS",
        "search_insn": b"\x09\x21\x40\xB9\x0A\x40\x9F\x52",
        "occurrence": 1, "scan_range": 0x600, "patch_offset": 0,
        "orig": "09 21 40 B9", "patch": "09 18 99 52",
    },
    {
        "name": "RuntimeBitrate_Movk_2",
        "symbol": "LocalUser13ApplySettingsERKNS",
        "search_insn": b"\x09\x21\x40\xB9\x0A\x40\x9F\x52",
        "occurrence": 1, "scan_range": 0x600, "patch_offset": 4,
        "orig": "0A 40 9F 52", "patch": "69 00 A0 72",
    },
    # Site 3 (ApplySettings): LDR W9 + CMP W9,#0, MOVZ W10 at +8 (CMP in between).
    {
        "name": "RuntimeBitrate_Ldr_3",
        "symbol": "LocalUser13ApplySettingsERKNS",
        "search_insn": b"\x09\x21\x40\xB9\x3F\x01\x00\x71",
        "occurrence": 1, "scan_range": 0x600, "patch_offset": 0,
        "orig": "09 21 40 B9", "patch": "09 18 99 52",
    },
    {
        "name": "RuntimeBitrate_Movk_3",
        "symbol": "LocalUser13ApplySettingsERKNS",
        "search_insn": b"\x09\x21\x40\xB9\x3F\x01\x00\x71",
        "occurrence": 1, "scan_range": 0x600, "patch_offset": 8,
        "orig": "0A 40 9F 52", "patch": "69 00 A0 72",
    },
    {
        "name": "MultiChannel_FrameMs_Imm10",
        "symbol": "AudioEncoderMultiChannelOpusConfigC1Ev",
        "search_insn": b"\x88\x02\x80\x52",
        "occurrence": 1, "scan_range": 64,
        "orig": "88 02 80 52", "patch": "48 01 80 52",
    },
    {
        "name": "CELT_Force",
        "constant_va": 0xA7D4C0,
        "orig": "18 FC FF FF FF FF FF FF",
        "patch": "EA 03 00 00 00 00 00 00",
    },
    {
        "name": "CELT_DefaultMode",
        "symbol": "opus_encoder_init",
        "search_insn": b"\x28\x7D\x80\x52",
        "occurrence": 1, "scan_range": 0x400,
        "orig": "28 7D 80 52", "patch": "48 7D 80 52",
    },
    {
        "name": "hp_cutoff_Callback_InjectShellcode",
        "symbol": "hp_cutoff",
        "at_start": True,
        "orig": "9F 04 00 71 6B 09 00 54 09 00 80 D2 28 3C 00 13 EA 34 81 52 08 7D 0A 1B 6A BA 89 52 4A 0C A2 72",
        "patch": "E4 00 00 34 8B 7C 05 1B AB 00 00 34 04 44 40 BC 44 44 00 BC 6B 05 00 71 A1 FF FF 54 C0 03 5F D6",
    },
    {
        "name": "dc_reject_Callback_InjectShellcode",
        "symbol": "dc_reject",
        "at_start": True,
        "orig": "A0 00 22 1E 88 66 86 52 E8 32 A8 72 01 01 27 1E 21 18 20 1E 00 10 2E 1E 02 38 21 1E 40 00 40 BD",
        "patch": "E3 00 00 34 6B 7C 04 1B AB 00 00 34 04 44 40 BC 24 44 00 BC 6B 05 00 71 A1 FF FF 54 C0 03 5F D6",
    },
]

MIN_ARM64_VA = 0x4000

ARM64_STEREO_SPEC_NAMES = [s["name"] for s in _ARM64_STEREO_SYMBOLS]

# Sites required by MacOS_ARM64_Patcher.py (static ARM64_PATCHES table).
MACOS_ARM64_PATCHER_NAMES = tuple(ARM64_STEREO_SPEC_NAMES)

MACOS_ARM64_PATCHER_OFFSET_ORDER = (
    # Opus channel count -> force stereo
    "MultiChannelOpusConfig_channels",
    "OpusConfig_channels",
    "CreateAudioFrame_channels1",
    "CreateAudioFrame_channels2",
    "NumProcChannels_force_stereo",
    "CommitAudioCodec_stereo_force",
    "CommitAudioCodec_stereo_force2",
    "CommitAudioCodec_ChannelCount_alt",
    # Downmix / mono collapse -> bypass
    "StereoDownmixChannels",
    "StereoDownMixFrame",
    "DownmixInterleavedToMono_bypass",
    "CapturedAudioProcessor_MonoDownmix",
    "ChannelDownmix_Entry_Ret",
    # SDP negotiation -> keep stereo
    "StereoApplyAudioNetworkAdaptor",
    "SdpToConfig_cinc1",
    "SdpToConfig_mov1",
    "SdpToConfig_cinc2",
    "SdpToConfig_mov2",
    # Config validation -> force OK / skip throw
    "OpusConfig_IsOk",
    "MultiChannelOpusConfig_IsOk",
    "CodecMismatchThrow_Entry_Ret",
    # Audio filters -> bypass
    "InitializeHighPassFilter_bypass",
    "NoiseCanceller_bypass",
    "CustomCapturePostproc_bypass",
    "ProcessStream_bypass",
    # Sample rate / frame size -> 48 kHz, 10 ms
    "SelectSampleRate_Cmov48k_Nop3",
    "OpusConfig_FrameMs_Rodata",
    "MultiChannel_FrameMs_Imm10",
    # Bitrate -> 248 kbps
    "OpusConfig_Bitrate_Rodata",
    "RuntimeBitrate_Ldr_1",
    "RuntimeBitrate_Movk_1",
    "RuntimeBitrate_Ldr_2",
    "RuntimeBitrate_Movk_2",
    "RuntimeBitrate_Ldr_3",
    "RuntimeBitrate_Movk_3",
    # CELT codec forcing
    "CELT_Force",
    "CELT_DefaultMode",
    # Filterless passthrough shellcode (hp_cutoff / dc_reject callbacks)
    "hp_cutoff_Callback_InjectShellcode",
    "dc_reject_Callback_InjectShellcode",
)

# Grouped layout for format_arm64_patches_python_block. Group labels and ordering
# mirror the # region ARM64 patch table block in MacOS_ARM64_Patcher.py exactly.
MACOS_ARM64_PATCH_GROUPS = (
    ("Opus channel count -> force stereo", (
        "MultiChannelOpusConfig_channels",
        "OpusConfig_channels",
        "CreateAudioFrame_channels1",
        "CreateAudioFrame_channels2",
        "NumProcChannels_force_stereo",
        "CommitAudioCodec_stereo_force",
        "CommitAudioCodec_stereo_force2",
        "CommitAudioCodec_ChannelCount_alt",
    )),
    ("Downmix / mono collapse -> bypass", (
        "StereoDownmixChannels",
        "StereoDownMixFrame",
        "DownmixInterleavedToMono_bypass",
        "CapturedAudioProcessor_MonoDownmix",
        "ChannelDownmix_Entry_Ret",
    )),
    ("SDP negotiation -> keep stereo", (
        "StereoApplyAudioNetworkAdaptor",
        "SdpToConfig_cinc1",
        "SdpToConfig_mov1",
        "SdpToConfig_cinc2",
        "SdpToConfig_mov2",
    )),
    ("Config validation -> force OK / skip throw", (
        "OpusConfig_IsOk",
        "MultiChannelOpusConfig_IsOk",
        "CodecMismatchThrow_Entry_Ret",
    )),
    ("Audio filters -> bypass", (
        "InitializeHighPassFilter_bypass",
        "NoiseCanceller_bypass",
        "CustomCapturePostproc_bypass",
        "ProcessStream_bypass",
    )),
    ("Sample rate / frame size -> 48 kHz, 10 ms", (
        "SelectSampleRate_Cmov48k_Nop3",
        "OpusConfig_FrameMs_Rodata",
        "MultiChannel_FrameMs_Imm10",
    )),
    ("Bitrate -> 248 kbps", (
        "OpusConfig_Bitrate_Rodata",
        "RuntimeBitrate_Ldr_1",
        "RuntimeBitrate_Movk_1",
        "RuntimeBitrate_Ldr_2",
        "RuntimeBitrate_Movk_2",
        "RuntimeBitrate_Ldr_3",
        "RuntimeBitrate_Movk_3",
    )),
    ("CELT codec forcing", (
        "CELT_Force",
        "CELT_DefaultMode",
    )),
    ("Filterless passthrough shellcode (hp_cutoff / dc_reject callbacks)", (
        "hp_cutoff_Callback_InjectShellcode",
        "dc_reject_Callback_InjectShellcode",
    )),
)

# Sites required by discord_voice_patcher_linux.sh (not the Windows 55-offset set).
LINUX_PATCHER_OFFSET_ORDER = (
    # Stereo (channels + downmix bypass)
    "CommitAudioCodec_StereoCheck1_Imm0",
    "CommitAudioCodec_StereoCheck2_Imm0",
    "CreateAudioFrame_Channels_MovImm2",
    "CapturedAudioProcessor_MonoDownmix_NopJmp",
    "AudioEncoderOpusConfig_Ctor_Channels_Imm02",
    "AudioEncoderMultiChannelOpusConfig_Ctor_Channels_Imm02",
    "ChannelDownmix_Entry_Ret",
    # 48 kHz sample rate
    "SelectSampleRate_Constant_Imm48k",
    # 248 kbps bitrate (config defaults + single central SetBitRate lock)
    "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k",
    "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k",
    "WebRtcOpus_SetBitRate_ForceImm",
    # 10ms frames + kAudio application
    "AudioEncoderOpusConfig_Ctor_FrameMs_Imm10",
    "AudioEncoderOpusConfig_Ctor_Application_ImmAudio",
    # Filter disable + config validation bypass
    "WebRtcSplHighPass_Entry_Ret",
    "AudioEncoderOpusConfig_IsOK_MovTrueRet",
    # Amplifier shellcode injection
    "hp_cutoff_Callback_InjectShellcode",
    "dc_reject_Callback_InjectShellcode",
    # Force CELT (MDCT) codec mode
    "CELT_Force",
    "CELT_DefaultMode",
)

# Windows finder result key -> Linux patcher shell name (same patch site).
# Simplified patch set (v9.0): stereo, 48kHz, central bitrate lock, 10ms/kAudio,
# filter/validation bypass, amplifier, forced CELT. FEC/DTX/RED + bitrate-tier
# patches were removed (redundant/fragile under forced CELT + central SetBitRate lock).
LINUX_FROM_WINDOWS = {
    "CreateAudioFrame_ChannelAssign_Mov": "CreateAudioFrame_Channels_MovImm2",
    "CapturedAudioProcessor_MonoDownmix_NopJmp": "CapturedAudioProcessor_MonoDownmix_NopJmp",
    "AudioEncoderOpusConfig_Ctor_Channels_Imm02": "AudioEncoderOpusConfig_Ctor_Channels_Imm02",
    "OpusEncoderConfig_SetMultiChannelStereo": "AudioEncoderMultiChannelOpusConfig_Ctor_Channels_Imm02",
    "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k": "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k",
    "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k": "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k",
    "AudioEncoderOpusConfig_Ctor_FrameMs_Imm10": "AudioEncoderOpusConfig_Ctor_FrameMs_Imm10",
    "AudioEncoderOpusConfig_Ctor_Application_ImmAudio": "AudioEncoderOpusConfig_Ctor_Application_ImmAudio",
    "WebRtcSplHighPass_Dispatch_MovRet": "WebRtcSplHighPass_Entry_Ret",
    "hp_cutoff_Callback_InjectShellcode": "hp_cutoff_Callback_InjectShellcode",
    "dc_reject_Callback_InjectShellcode": "dc_reject_Callback_InjectShellcode",
    "ChannelDownmix_Entry_Ret": "ChannelDownmix_Entry_Ret",
    "AudioEncoderOpusConfig_IsOK_MovTrueRet": "AudioEncoderOpusConfig_IsOK_MovTrueRet",
}


# ELF symbol-driven resolution for sites not covered by the shared Windows table.
# Each entry: a function (by mangled-symbol substring) + a byte scan within it.
LINUX_EXTRA_ELF_MAP = {
    "CommitAudioCodec_StereoCheck1_Imm0": {
        "patterns": ["LocalUser16CommitAudioCodecEv"],
        "linux_scan": "stereo_check_dword_f0_imm2",
    },
    "CommitAudioCodec_StereoCheck2_Imm0": {
        "patterns": ["LocalUser17CreateAudioStreamEv"],
        "linux_scan": "stereo_check_dword_f0_imm2",
    },
    "WebRtcSplHighPass_Entry_Ret": {
        "patterns": ["HighPassFilter7ProcessEPNS_11AudioBufferEb"],
        "linux_scan": "function_entry",
    },
    "SelectSampleRate_Constant_Imm48k": {
        "patterns": ["CreateAudioFrameToProcess", "CreateAudioFrame"],
        "linux_scan": "select_sample_rate_imm48k",
    },
    # Central bitrate lock: WebRtcOpus_SetBitRate prologue (push rbp; mov edx, esi).
    "WebRtcOpus_SetBitRate_ForceImm": {
        "patterns": ["WebRtcOpus_SetBitRate"],
        "linux_scan": "webrtcopus_setbitrate_force",
    },
    # Forced CELT: opus_encoder_init writes user_forced_mode (-1000) and default mode (1001).
    "CELT_Force": {
        "patterns": ["opus_encoder_init"],
        "linux_scan": "celt_user_forced_mode",
    },
    "CELT_DefaultMode": {
        "patterns": ["opus_encoder_init"],
        "linux_scan": "celt_default_mode",
    },
}


def _arm64_bl_destination(d, off):
    if off + 4 > len(d):
        return None
    insn = int.from_bytes(d[off : off + 4], "little")
    if (insn >> 26) != 0b100101:
        return None
    imm26 = insn & 0x03FFFFFF
    if imm26 & 0x02000000:
        imm26 -= 0x04000000
    return off + (imm26 << 2)


def _arm64_stereo_lookup_symbol(func_syms, pattern, cache):
    if pattern in cache:
        return cache[pattern]
    candidates = [(n, s) for n, s in func_syms.items() if pattern in n]
    if not candidates:
        cache[pattern] = None
        return None

    def _rank(item):
        name, sym = item
        score = sym["value"]
        if "absl" in name or "invocable" in name or "trace_event" in name:
            score += 1 << 40
        if name.endswith(pattern) or f"{pattern}E" in name:
            score -= 1 << 20
        return score

    best = min(candidates, key=_rank)[1]
    cache[pattern] = best
    return best


def _arm64_stereo_resolve_symbol(func_syms, spec, sym_cache):
    sym = _arm64_stereo_lookup_symbol(func_syms, spec["symbol"], sym_cache)
    if sym is not None:
        return sym
    for alt in spec.get("symbol_alternates", ()):
        sym = _arm64_stereo_lookup_symbol(func_syms, alt, sym_cache)
        if sym is not None:
            return sym
    return None


def _append_arm64_stereo_patch(out, fo, po, spec, already=False):
    entry = {
        "arch": "arm64",
        "va": po,
        "fat_offset": fo + po,
        "orig": spec["orig"],
        "patch": spec["patch"],
        "name": spec["name"],
    }
    if already:
        entry["already_patched"] = True
    out.append(entry)


def _find_stereo_arm64(slice_info, full_data, out):
    d = slice_info["data"]
    fo = slice_info["fat_offset"]

    arm64_info = _parse_macho_slice(full_data, fo)
    if not arm64_info or not arm64_info.get("has_symbols"):
        return

    func_syms = arm64_info["func_symbols"]
    sym_cache = {}

    for spec in _ARM64_STEREO_SYMBOLS:
        orig = _parse_hex_bytes(spec["orig"])
        patch_bytes = _parse_hex_bytes(spec["patch"])

        if spec.get("constant_va") is not None:
            po = spec["constant_va"] + spec.get("patch_offset", 0)
            if po + len(orig) > len(d):
                continue
            current = d[po : po + len(orig)]
            if current == orig:
                _append_arm64_stereo_patch(out, fo, po, spec)
            elif current == patch_bytes:
                _append_arm64_stereo_patch(out, fo, po, spec, already=True)
            continue

        sym = _arm64_stereo_resolve_symbol(func_syms, spec, sym_cache)
        if sym is None:
            continue

        func_va = sym["value"]
        orig = _parse_hex_bytes(spec["orig"])
        patch_bytes = _parse_hex_bytes(spec["patch"])

        if spec.get("bl_target"):
            target_sym = _arm64_stereo_lookup_symbol(func_syms, spec["bl_target"], sym_cache)
            if target_sym is None:
                continue
            target_va = target_sym["value"]
            scan_end = min(func_va + spec.get("scan_range", 512), len(d))
            for off in range(func_va, scan_end - 3, 4):
                if _arm64_bl_destination(d, off) != target_va:
                    continue
                current = d[off : off + 4]
                dyn_spec = dict(spec)
                dyn_spec["orig"] = " ".join(f"{b:02X}" for b in current)
                if current == patch_bytes:
                    _append_arm64_stereo_patch(out, fo, off, dyn_spec, already=True)
                elif (current[3] & 0xFC) == 0x94:
                    _append_arm64_stereo_patch(out, fo, off, dyn_spec)
                break
            continue

        if spec.get("prologue_scan"):
            scan_end = min(func_va + spec["prologue_scan"], len(d))
            found = False
            for po in range(func_va, scan_end - len(orig) + 1, 4):
                current = d[po : po + len(orig)]
                if current == orig:
                    _append_arm64_stereo_patch(out, fo, po, spec)
                    found = True
                    break
                if current == patch_bytes:
                    _append_arm64_stereo_patch(out, fo, po, spec, already=True)
                    found = True
                    break
            if not found:
                continue
            continue

        if spec.get("at_start"):
            po = func_va
            if po + len(orig) > len(d):
                continue
            current = d[po : po + len(orig)]
            if current == orig:
                _append_arm64_stereo_patch(out, fo, po, spec)
            elif current == patch_bytes:
                _append_arm64_stereo_patch(out, fo, po, spec, already=True)
            continue

        search_insn = spec["search_insn"]
        scan_range = spec.get("scan_range", 256)
        occurrence = spec.get("occurrence", 1)
        insn_len = len(search_insn)
        poff = spec.get("patch_offset", 0)
        if spec.get("scan_slice"):
            scan_start = MIN_ARM64_VA
            scan_end = len(d)
        else:
            scan_start = func_va
            scan_end = min(func_va + scan_range, len(d))
        hit = 0
        found = False
        for off in range(scan_start, scan_end - insn_len + 1, 4):
            if d[off : off + insn_len] != search_insn:
                continue
            hit += 1
            if hit != occurrence:
                continue
            po = off + poff
            current = d[po : po + len(orig)]
            if current == orig:
                _append_arm64_stereo_patch(out, fo, po, spec)
            elif current == patch_bytes:
                _append_arm64_stereo_patch(out, fo, po, spec, already=True)
            found = True
            break

        if found or len(orig) != len(patch_bytes):
            continue
        hit = 0
        for off in range(scan_start, scan_end - insn_len + 1, 4):
            patched_insn = bytearray(search_insn)
            for i, b in enumerate(patch_bytes):
                idx = poff + i
                if idx < insn_len:
                    patched_insn[idx] = b
            if d[off : off + insn_len] != bytes(patched_insn):
                continue
            hit += 1
            if hit == occurrence:
                _append_arm64_stereo_patch(out, fo, off + poff, spec, already=True)
                break


def find_macos_stereo_patches(data):
    """Resolve ARM64 stereo patch sites in a fat Mach-O (Intel/x86_64 is not scanned)."""
    slices = _parse_fat_macho_slices(data)
    if not slices:
        return []
    out = []
    for sl in slices:
        if sl["arch"] != "arm64":
            continue
        _find_stereo_arm64(sl, data, out)
    return out




def detect_binary_format(data):
    pe = parse_pe(data)
    if pe:
        pe['format'] = 'pe'
        pe['arch'] = 'x86_64'
        pe['has_symbols'] = False
        pe['func_symbols'] = {}
        pe['symbols'] = []
        return pe
    macho = parse_macho(data)
    if macho:
        return macho
    elf = parse_elf(data)
    if elf:
        return elf
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
    import struct as _st

    end = min(func_start + func_size, len(data))
    func = data[func_start:end]
    flen = len(func)

    if scan_type == "multichannel_opus_config_channels":
        pat = b"\xC7\x07\x14\x00\x00\x00\x48\xC7\x47\x08"
        for i in range(flen - (len(pat) + 4)):
            if func[i : i + len(pat)] != pat:
                continue
            ch_off = i + len(pat)
            if ch_off < flen and func[ch_off] in (0x01, 0x02):
                return func_start + ch_off + adj
        return None

    if scan_type == "opus_config_channels":
        for i in range(flen - 24):
            if (func[i:i+2] == b'\x48\xb8'
                    and func[i+2] == 0x14 and func[i+6:i+10] == b'\x80\xbb\x00\x00'):
                ch_off = i + 0x15
                if ch_off < flen and func[ch_off] in (0x01, 0x02):
                    return func_start + ch_off + adj
        return None

    if scan_type == "opus_config_bitrate":
        for i in range(flen - 10):
            if (func[i:i+2] == b'\x48\xb8'
                    and func[i+2:i+7] == b'\x00\x00\x00\x00\x00'
                    and func[i+7:i+10] == b'\x7d\x00\x00'):
                target_off = i + 5
                if func[target_off:target_off+4] == b'\x00\x7d\x00\x00':
                    return func_start + target_off + adj
        return None

    if scan_type == "stereo_cmp_byte":
        def _is_stereo_cmp(buf, pos, buflen):
            if pos + 8 > buflen:
                return False, 0, 0
            if buf[pos] != 0x80:
                return False, 0, 0
            modrm = buf[pos + 1]
            if not (0xB8 <= modrm <= 0xBF):
                return False, 0, 0
            if (modrm & 7) == 4:
                return False, 0, 0
            val = buf[pos + 6]
            if val not in (0x00, 0x01):
                return False, 0, 0
            jcc_byte = buf[pos + 7]
            if jcc_byte not in (0x74, 0x75, 0x0F):
                return False, 0, 0
            if jcc_byte == 0x0F and pos + 9 <= buflen:
                if buf[pos + 8] not in (0x84, 0x85):
                    return False, 0, 0
            member_off = _st.unpack_from('<I', buf, pos + 2)[0]
            if not (0x100 < member_off < 0x1000):
                return False, 0, 0
            return True, modrm, member_off

        for i in range(flen - 8):
            ok, modrm, member_off = _is_stereo_cmp(func, i, flen)
            if not ok:
                continue
            off_bytes = func[i+2:i+6]
            setter_modrm = 0x80 | (modrm & 7)
            setter = bytes([0xC6, setter_modrm]) + off_bytes + b'\x01'
            search_start = i + 8
            search_end = min(i + 56, flen)
            if setter in func[search_start:search_end]:
                return func_start + i + 6 + adj
        for i in range(flen - 8):
            ok, modrm, member_off = _is_stereo_cmp(func, i, flen)
            if ok:
                return func_start + i + 6 + adj
        return None

    if scan_type == "stereo_success2_byte":
        found_first = False
        for i in range(flen - 8):
            if func[i] != 0x80:
                continue
            modrm = func[i + 1]
            if not (0xB8 <= modrm <= 0xBF) or (modrm & 7) == 4:
                continue
            val = func[i + 6]
            jcc_byte = func[i + 7]
            if val not in (0x00, 0x01):
                continue
            if jcc_byte not in (0x74, 0x75, 0x0F):
                continue
            if jcc_byte == 0x0F and i + 9 <= flen:
                if func[i + 8] not in (0x84, 0x85):
                    continue
            member_off = _st.unpack_from('<I', func, i + 2)[0]
            if not (0x100 < member_off < 0x1000):
                continue
            if not found_first:
                found_first = True
                continue
            return func_start + i + 7 + adj
        return None

    if scan_type == "emulate_48khz_cmov":
        for i in range(flen - 16):
            if func[i] == 0x83 and 0xB8 <= func[i+1] <= 0xBF:
                if (func[i+1] & 7) == 4:
                    continue
                disp = _st.unpack_from('<I', func, i+2)[0]
                if 0x40 < disp < 0x1000 and func[i+6] == 0x02:
                    for j in range(7, 20):
                        if i + j + 4 > flen:
                            break
                        b0 = func[i + j]
                        b1 = func[i + j + 1]
                        if b0 == 0x0F and 0x40 <= b1 <= 0x4F:
                            return func_start + i + j + adj
                        if b0 == 0x48 and b1 == 0x0F and i + j + 2 < flen:
                            if 0x40 <= func[i + j + 2] <= 0x4F:
                                return func_start + i + j + adj
            if func[i] == 0x41 and func[i+1] == 0x83 and i+8 <= flen:
                if 0xB8 <= func[i+2] <= 0xBF and (func[i+2] & 7) != 4:
                    disp = _st.unpack_from('<I', func, i+3)[0]
                    if 0x40 < disp < 0x1000 and func[i+7] == 0x02:
                        for j in range(8, 24):
                            if i + j + 4 > flen:
                                break
                            b0 = func[i + j]
                            b1 = func[i + j + 1]
                            if b0 == 0x0F and 0x40 <= b1 <= 0x4F:
                                return func_start + i + j + adj
                            if b0 == 0x48 and b1 == 0x0F and i + j + 2 < flen:
                                if 0x40 <= func[i + j + 2] <= 0x4F:
                                    return func_start + i + j + adj
        for i in range(flen - 12):
            if func[i:i+3] == b'\x48\x8d\x05' or func[i:i+3] == b'\x48\x8d\x15':
                for j in range(7, 24):
                    if i + j + 4 > flen:
                        break
                    if func[i+j] == 0x48 and func[i+j+1] == 0x0F:
                        if 0x40 <= func[i+j+2] <= 0x4F:
                            return func_start + i + j + adj
        return None

    if scan_type == "channel_cmov":
        for i in range(flen - 40):
            if func[i:i+5] == b'\xb8\x80\xbb\x00\x00':
                for j in range(5, 40):
                    if i+j+4 <= flen and func[i+j:i+j+3] == b'\x4c\x0f\x43':
                        return func_start + i + j + adj
        return None

    if scan_type == "bitrate_movabs_or":
        for i in range(flen - 16):
            if (func[i:i+2] == b'\x48\xb9'
                    and func[i+6:i+10] == b'\x01\x00\x00\x00'
                    and func[i+10:i+13] == b'\x48\x09\xc1'):
                return func_start + i + 2 + adj
        return None

    if scan_type == "set_target_bitrate_mulss":
        needle = b'\xf3\x0f\x59\x44\x81\xec'
        idx = func.find(needle)
        if idx >= 0:
            return func_start + idx + adj
        return None

    if scan_type == "get_multiplied_bitrate_mulss":
        for needle in (b'\xf3\x0f\x59\x44\x81\xec', b'\xf3\x0f\x59\x44\x88\xec'):
            idx = func.find(needle)
            if idx >= 0:
                return func_start + idx + adj
        return None

    if scan_type == "mono_downmix_test":
        def _mono_match_at(i):
            if func[i:i+2] != b'\x84\xc0' or func[i+2] != 0x74:
                return None
            cmp_start = i + 4
            if cmp_start >= flen - 4 or func[cmp_start] != 0x83:
                return None
            modrm = func[cmp_start + 1]
            if ((modrm >> 3) & 7) != 7:
                return None
            mod = modrm >> 6
            if mod == 1 and cmp_start + 4 <= flen:
                imm_off = cmp_start + 3
            elif mod == 2 and cmp_start + 7 <= flen:
                imm_off = cmp_start + 6
            else:
                return None
            if func[imm_off] != 0x09:
                return None
            jg_off = imm_off + 1
            if jg_off >= flen:
                return None
            j0 = func[jg_off]
            if j0 == 0x0F and jg_off + 1 < flen and func[jg_off + 1] in (0x8F, 0x8D):
                return ("near", func_start + i + adj)
            if j0 in (0x7F, 0x7D):
                return ("short", func_start + i + adj)
            return None

        short_best = None
        for i in range(flen - 8):
            m = _mono_match_at(i)
            if not m:
                continue
            kind, off = m
            if kind == "near":
                return off
            short_best = off
        return short_best

    if scan_type == "stereo_check1":
        hits = _linux_stereo_cmp_imm_hits(func, func_start)
        return hits[0] if hits else None

    if scan_type == "stereo_check_dword_f0_imm2":
        idx = func.find(b"\x83\xbb\xf0\x00\x00\x00\x02")
        if idx < 0:
            for i in range(flen - 7):
                if func[i] == 0x83 and func[i + 2 : i + 6] == b"\xf0\x00\x00\x00" and func[i + 6] == 0x02:
                    return func_start + i + 6 + adj
            return None
        return func_start + idx + 6 + adj

    if scan_type == "function_entry":
        return func_start + adj

    if scan_type == "select_sample_rate_imm48k":
        idx = func.find(b"\x41\xbd\x00\x7d\x00\x00")
        if idx >= 0:
            return func_start + idx + adj
        return None

    if scan_type == "webrtcopus_setbitrate_force":
        # WebRtcOpus_SetBitRate prologue: ... push rbp; mov rbp,rsp; mov edx,esi
        # Patch site = the 'push rbp' (overwritten with: push rbp; mov edx, BITRATE_BPS).
        idx = func.find(b"\x55\x48\x89\xe5\x89\xf2")
        if idx >= 0:
            return func_start + idx + adj
        return None

    if scan_type == "celt_user_forced_mode":
        # opus_encoder_init: REX.W C7 /0 [reg+0x88], imm32 == -1000 (OPUS_AUTO).
        # Patch the imm32 (offset +7) to 1002 (MODE_CELT_ONLY).
        for i in range(flen - 11):
            if (func[i] == 0x48 and func[i + 1] == 0xC7 and 0x80 <= func[i + 2] <= 0x87
                    and func[i + 3 : i + 7] == b"\x88\x00\x00\x00"
                    and func[i + 7 : i + 11] == b"\x18\xfc\xff\xff"):
                return func_start + i + 7 + adj
        return None

    if scan_type == "celt_default_mode":
        # opus_encoder_init: C7 /0 [reg+0x3794], imm32 == 1001 (HYBRID).
        # Patch the imm32 (offset +6) to 1002 (MODE_CELT_ONLY).
        for i in range(flen - 10):
            if (func[i] == 0xC7 and 0x80 <= func[i + 1] <= 0x87
                    and func[i + 2 : i + 6] == b"\x94\x37\x00\x00"
                    and func[i + 6 : i + 10] == b"\xe9\x03\x00\x00"):
                return func_start + i + 6 + adj
        return None

    return None


def _linux_stereo_cmp_imm_hits(func, func_start):
    import struct as _st

    flen = len(func)
    hits = []
    for i in range(flen - 8):
        if func[i] != 0x80:
            continue
        modrm = func[i + 1]
        if not (0xB8 <= modrm <= 0xBF) or (modrm & 7) == 4:
            continue
        val = func[i + 6]
        jcc_byte = func[i + 7]
        if val not in (0x00, 0x01):
            continue
        if jcc_byte not in (0x74, 0x75, 0x0F):
            continue
        if jcc_byte == 0x0F and i + 9 <= flen and func[i + 8] not in (0x84, 0x85):
            continue
        member_off = _st.unpack_from("<I", func, i + 2)[0]
        if not (0x100 < member_off < 0x1000):
            continue
        fo = func_start + i + 6
        if fo not in hits:
            hits.append(fo)
    return hits


def _linux_pick_symbol(func_syms, patterns):
    """Prefer real mangled implementations over absl/std wrappers."""
    scored = []
    seen = set()
    for pattern in patterns:
        pl = pattern.lower()
        for sym_name, sym in func_syms.items():
            addr = sym.get("value", 0)
            if not addr or addr in seen:
                continue
            snl = sym_name.lower()
            if pl not in snl:
                continue
            seen.add(addr)
            score = sym.get("size", 0)
            if sym_name.startswith("_ZN"):
                score += 10_000
            if snl.endswith(pl) or f"{pl}e" in snl:
                score += 1_000
            scored.append((score, sym))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def _resolve_linux_extra_elf(bin_info, data):
    if not bin_info.get("has_symbols") or not bin_info.get("func_symbols"):
        return {}
    func_syms = bin_info["func_symbols"]
    adj = bin_info.get("file_offset_adjustment", 0)
    out = {}
    for offset_name, mapping in LINUX_EXTRA_ELF_MAP.items():
        best = _linux_pick_symbol(func_syms, mapping["patterns"])
        if best is None:
            continue
        func_size = best.get("size", 0) or 0x2000
        if func_size > 0x10000:
            func_size = 0x2000
        func_file_start = best["value"] - adj
        if func_file_start < 0:
            continue
        linux_scan = mapping.get("linux_scan")
        if not linux_scan:
            continue
        result = _linux_scan_within_function(data, func_file_start, func_size, linux_scan, adj)
        if result is not None:
            out[offset_name] = result - adj if result >= adj else result
    return out


def resolve_linux_patcher_offsets(windows_results, data, bin_info):
    """Map Windows-style finder results to discord_voice_patcher_linux.sh names."""
    adj = bin_info.get("file_offset_adjustment", 0) if bin_info else 0
    out = {}
    for win_key, linux_name in LINUX_FROM_WINDOWS.items():
        if win_key in windows_results:
            out[linux_name] = windows_results[win_key] - adj
    extra = _resolve_linux_extra_elf(bin_info, data)
    for k, v in extra.items():
        out[k] = v
    caf = out.get("CreateAudioFrame_Channels_MovImm2")
    if caf is not None:
        for delta in (0, -3):
            off = caf + delta
            if off >= 0 and off + 3 <= len(data) and bytes(data[off : off + 3]) == b"\x49\x39\xc4":
                out["CreateAudioFrame_Channels_MovImm2"] = off
                break
    return out


def _linux_patcher_stats(linux_offsets):
    found = sum(1 for n in LINUX_PATCHER_OFFSET_ORDER if linux_offsets.get(n))
    missing = [n for n in LINUX_PATCHER_OFFSET_ORDER if not linux_offsets.get(n)]
    return {
        "found": found,
        "expected": len(LINUX_PATCHER_OFFSET_ORDER),
        "missing": missing,
    }



def _pe_file_off_to_rva(file_off, sections):
    for sec in sections or []:
        ro = sec.get("raw_offset", 0)
        rs = sec.get("raw_size", 0)
        va = sec.get("vaddr", 0)
        if ro > 0 and ro <= file_off < ro + rs:
            return file_off - ro + va
    return None


def _pe_rva_to_file_off(rva, sections):
    for sec in sections or []:
        va = sec.get("vaddr", 0)
        vs = sec.get("vsize", 0) or sec.get("raw_size", 0)
        ro = sec.get("raw_offset", 0)
        if va and ro and va <= rva < va + vs:
            return rva - va + ro
    return None


def _pe_read_cstr(data, off, max_len=512):
    end = data.find(b"\x00", off, min(len(data), off + max_len))
    if end < 0:
        return None
    try:
        return data[off:end].decode("ascii")
    except UnicodeDecodeError:
        return None


def _pe_parse_exports(data, bin_info):
    if bin_info.get("format") != "pe":
        return {}
    cached = bin_info.get("exports_by_name")
    if cached is not None:
        return cached
    sections = bin_info.get("sections") or []
    pe_off = bin_info.get("pe_offset")
    if not pe_off or pe_off + 4 > len(data):
        bin_info["exports_by_name"] = {}
        return {}
    coff = pe_off + 4
    if coff + 20 > len(data):
        bin_info["exports_by_name"] = {}
        return {}
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    if opt + 2 > len(data):
        bin_info["exports_by_name"] = {}
        return {}
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x20B:
        dd_off = opt + 112
    elif magic == 0x10B:
        dd_off = opt + 96
    else:
        bin_info["exports_by_name"] = {}
        return {}
    if dd_off + 8 > opt + opt_size or dd_off + 8 > len(data):
        bin_info["exports_by_name"] = {}
        return {}
    exp_rva = struct.unpack_from("<I", data, dd_off)[0]
    exp_size = struct.unpack_from("<I", data, dd_off + 4)[0]
    if exp_rva == 0 or exp_size < 40:
        bin_info["exports_by_name"] = {}
        return {}
    exp_file = _pe_rva_to_file_off(exp_rva, sections)
    if exp_file is None or exp_file + 40 > len(data):
        bin_info["exports_by_name"] = {}
        return {}
    num_funcs = struct.unpack_from("<I", data, exp_file + 20)[0]
    num_names = struct.unpack_from("<I", data, exp_file + 24)[0]
    funcs_rva = struct.unpack_from("<I", data, exp_file + 28)[0]
    names_rva = struct.unpack_from("<I", data, exp_file + 32)[0]
    ords_rva = struct.unpack_from("<I", data, exp_file + 36)[0]
    funcs_file = _pe_rva_to_file_off(funcs_rva, sections)
    names_file = _pe_rva_to_file_off(names_rva, sections)
    ords_file = _pe_rva_to_file_off(ords_rva, sections)
    if None in (funcs_file, names_file, ords_file):
        bin_info["exports_by_name"] = {}
        return {}
    if funcs_file + num_funcs * 4 > len(data):
        bin_info["exports_by_name"] = {}
        return {}
    if names_file + num_names * 4 > len(data) or ords_file + num_names * 2 > len(data):
        bin_info["exports_by_name"] = {}
        return {}
    out = {}
    for i in range(num_names):
        name_rva = struct.unpack_from("<I", data, names_file + i * 4)[0]
        name_file = _pe_rva_to_file_off(name_rva, sections)
        if name_file is None:
            continue
        nm = _pe_read_cstr(data, name_file)
        if not nm:
            continue
        ord_idx = struct.unpack_from("<H", data, ords_file + i * 2)[0]
        if ord_idx >= num_funcs:
            continue
        fn_rva = struct.unpack_from("<I", data, funcs_file + ord_idx * 4)[0]
        if fn_rva == 0:
            continue
        if exp_rva <= fn_rva < exp_rva + exp_size:
            continue
        out[nm] = fn_rva
    bin_info["exports_by_name"] = out
    return out


def _discover_bitrate_v18_offsets_pe(data, bin_info, results, tiers_used, text_start, text_end):
    if bin_info.get("format") != "pe":
        return

    adj = bin_info.get("file_offset_adjustment", 0xC00)
    flat_ebp = bytes.fromhex("BDC0C8030090")
    flat_r8d = bytes.fromhex("41B8C8030090")
    max_stock = STOCK_MAX_BITRATE_LE
    max248 = struct.pack("<I", 248000)

    def _tier_ebp_valid(rva):
        fo = rva - adj
        if fo < 0 or fo + 6 > len(data):
            return False
        if data[fo:fo + 6] == flat_ebp:
            return True
        if data[fo:fo + 2] != b"\x69\xE8":
            return False
        imm = struct.unpack_from("<I", data, fo + 2)[0]
        if imm in TIER_EBP_IMMS:
            return True
        if fo + 9 <= len(data) and data[fo + 6:fo + 9] == b"\x0F\xAF\xE8" and imm in TIER_R8D_IMMS:
            return True
        return False

    def _apply_derived(name, anchor_name, delta, label):
        if name in results or anchor_name not in results:
            return False
        config_off = results[anchor_name] + delta
        file_off = config_off - adj
        if file_off < 0 or file_off >= len(data):
            return False
        results[name] = config_off
        tiers_used[name] = label
        print(f"  [ OK ] {name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{config_off:08X}  [{label}]")
        return True

    print("\n" + "=" * 65)
    print("  PHASE 2d: Bitrate v18 (flat tiers / clamps / identity)")
    print("=" * 65)

    apply_names = (
        "ApplySettings_BitrateCalcLow_Channels_Mov248k",
        "ApplySettings_BitrateCalcMid_Channels_Mov248k",
        "ApplySettings_BitrateCalcHigh_Channels_Mov248k",
    )
    recreate_names = (
        "RecreateEncoder_BitrateCalcLow_Channels_Mov248k",
        "RecreateEncoder_BitrateCalcMid_Channels_Mov248k",
        "RecreateEncoder_BitrateCalcHigh_Channels_Mov248k",
    )
    for name in apply_names + recreate_names:
        if name in results and not _tier_ebp_valid(results[name]):
            print(f"  [PURGE] {name:<{OFFSET_LOG_NAME_WIDTH}s} @ 0x{results[name]:X} (invalid tier bytes)")
            results.pop(name, None)
            tiers_used.pop(name, None)

    def _scan_tier_ebp_sites(start, end, limit=3):
        sites = []
        pos = max(0, start)
        while pos < min(end, len(data) - 6) and len(sites) < limit:
            if data[pos:pos + 6] == flat_ebp:
                sites.append(pos + adj)
                pos += 6
                continue
            if data[pos:pos + 2] == b"\x69\xE8":
                imm = struct.unpack_from("<I", data, pos + 2)[0]
                if imm in TIER_EBP_IMMS:
                    sites.append(pos + adj)
                    pos += 6
                    continue
                if pos + 9 <= len(data) and data[pos + 6:pos + 9] == b"\x0F\xAF\xE8" and imm in TIER_R8D_IMMS:
                    sites.append(pos + adj)
                    pos += 6
                    continue
            pos += 1
        return sites

    def _scan_adaptor_r8d_sites(start, end, limit=3):
        sites = []
        pos = max(0, start)
        while pos < min(end, len(data) - 7) and len(sites) < limit:
            if data[pos:pos + 7] == flat_r8d:
                sites.append(pos + adj)
                pos += 7
                continue
            if data[pos:pos + 3] == b"\x44\x69\xC6":
                imm = struct.unpack_from("<I", data, pos + 3)[0]
                if imm in TIER_R8D_IMMS:
                    sites.append(pos + adj)
                    pos += 7
                    continue
            if data[pos:pos + 2] in (b"\x41\xB8", b"\x41\xB9"):
                imm = struct.unpack_from("<I", data, pos + 2)[0]
                if imm in TIER_R8D_IMMS and data.find(b"\x41\x0F\xAF\xC0", pos, min(len(data), pos + 24)) >= 0:
                    sites.append(pos + adj)
                    pos += 7
                    continue
            pos += 1
        return sites

    if not all(n in results for n in apply_names):
        anchor = results.get("CommitAudioCodec_ChannelCount_Imm02")
        if anchor is not None:
            anchor_file = anchor - adj
            sites = _scan_tier_ebp_sites(anchor_file - 0x2000, anchor_file + 0x4000, 3)
            if len(sites) >= 3:
                for name, off in zip(apply_names, sites[:3]):
                    if name not in results:
                        results[name] = off
                        tiers_used[name] = "extended(tier-ebp-apply)"
                        print(f"  [ OK ] {name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{off:08X}")

    recreate_names = (
        "RecreateEncoder_BitrateCalcLow_Channels_Mov248k",
        "RecreateEncoder_BitrateCalcMid_Channels_Mov248k",
        "RecreateEncoder_BitrateCalcHigh_Channels_Mov248k",
    )
    if not all(n in results for n in recreate_names):
        start = text_start
        if "ApplySettings_BitrateCalcHigh_Channels_Mov248k" in results:
            start = max(text_start, results["ApplySettings_BitrateCalcHigh_Channels_Mov248k"] - adj)
        apply_sites = {results[n] for n in apply_names if n in results}
        sites = [s for s in _scan_tier_ebp_sites(start, text_end, 6) if s not in apply_sites]
        if len(sites) >= 3:
            for name, off in zip(recreate_names, sites[:3]):
                if name not in results:
                    results[name] = off
                    tiers_used[name] = "extended(tier-ebp-recreate)"
                    print(f"  [ OK ] {name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{off:08X}")

    adapt_names = (
        "AudioBitrateAdaptorCalc32k_Channels_Mov248k",
        "AudioBitrateAdaptorCalc48k_Channels_Mov248k",
        "AudioBitrateAdaptorCalc60k_Channels_Mov248k",
    )
    if not all(n in results for n in adapt_names):
        sites = _scan_adaptor_r8d_sites(text_start, text_end, 3)
        if len(sites) >= 3:
            for name, off in zip(adapt_names, sites[:3]):
                if name not in results:
                    results[name] = off
                    tiers_used[name] = "extended(adaptor-r8d)"
                    print(f"  [ OK ] {name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{off:08X}")

    apply_anchor = results.get("ApplySettings_BitrateCalcLow_Channels_Mov248k")
    if apply_anchor is not None:
        if "SetBitrate_Imm64_Imm248k" in results and abs(results["SetBitrate_Imm64_Imm248k"] - apply_anchor) > 0x3000:
            print(f"  [PURGE] SetBitrate_Imm64_Imm248k{' ':22s} @ 0x{results['SetBitrate_Imm64_Imm248k']:X} (too far from ApplySettings)")
            results.pop("SetBitrate_Imm64_Imm248k", None)
            tiers_used.pop("SetBitrate_Imm64_Imm248k", None)
            for dep in ("SetBitrate_OrMask_Nop3", "SetTargetBitrate_Mulss_Nop6",
                        "SetTargetBitrate_ClampMax248k_Cmp", "SetTargetBitrate_ClampMax248k_Mov",
                        "EncoderOpusImpl_RelayClamp248k_Cmp", "EncoderOpusImpl_RelayClamp248k_Mov"):
                results.pop(dep, None)
                tiers_used.pop(dep, None)
        if "SetBitrate_Imm64_Imm248k" not in results:
            af = apply_anchor - adj
            win_start = max(text_start, af - 0x1000)
            win_end = min(text_end, af + 0x3000)
            for pos in range(win_start, win_end - 16):
                if data[pos:pos + 2] == b"\x48\xB9" and data[pos + 2:pos + 7] == _BITRATE_LE + b"\x00":
                    config_off = pos + 4 + adj
                    results["SetBitrate_Imm64_Imm248k"] = config_off
                    tiers_used["SetBitrate_Imm64_Imm248k"] = "extended(setbitrate-near-apply)"
                    print(f"  [ OK ] SetBitrate_Imm64_Imm248k{' ':22s} = 0x{config_off:X}")
                    break
                if data[pos:pos + 2] == b"\x89\xF8" and data[pos + 2:pos + 4] == b"\x48\xB9":
                    imm = data[pos + 4:pos + 9]
                    if imm == _BITRATE_LE + b"\x00":
                        config_off = pos + 4 + adj
                        results["SetBitrate_Imm64_Imm248k"] = config_off
                        tiers_used["SetBitrate_Imm64_Imm248k"] = "extended(setbitrate-near-apply)"
                        print(f"  [ OK ] SetBitrate_Imm64_Imm248k{' ':22s} = 0x{config_off:X}")
                        break

    if "SetTargetBitrate_Mulss_Nop6" not in results and "SetBitrate_Imm64_Imm248k" in results:
        _apply_derived("SetTargetBitrate_Mulss_Nop6", "SetBitrate_Imm64_Imm248k", 0x40,
                       "derived(SetBitrate_Imm64_Imm248k+0x40)")
    elif "SetTargetBitrate_Mulss_Nop6" in results and "SetBitrate_Imm64_Imm248k" in results:
        if abs(results["SetTargetBitrate_Mulss_Nop6"] - results["SetBitrate_Imm64_Imm248k"]) > 0x100:
            results.pop("SetTargetBitrate_Mulss_Nop6", None)
            tiers_used.pop("SetTargetBitrate_Mulss_Nop6", None)
            _apply_derived("SetTargetBitrate_Mulss_Nop6", "SetBitrate_Imm64_Imm248k", 0x40,
                           "derived(SetBitrate_Imm64_Imm248k+0x40)")

    if "GetMultipliedBitrate_Mulss_Nop7" in results:
        entry = results["GetMultipliedBitrate_Mulss_Nop7"] - 0x3D
        fo = entry - adj
        if 0 <= fo and fo + 3 <= len(data) and data[fo:fo + 3] in (b"\x89\xc8\x48", b"\x8b\xc1\xc3"):
            results["GetMultipliedBitrate_Entry_IdentityRet"] = entry
            tiers_used["GetMultipliedBitrate_Entry_IdentityRet"] = "extended(getmult-entry-exact)"
            print(f"  [ OK ] GetMultipliedBitrate_Entry_IdentityRet{' ':10s} = 0x{entry:X}")

    clamp_windows = []
    if apply_anchor is not None:
        af = apply_anchor - adj
        clamp_windows.append((
            "ApplySettings_MaxAvgBitrateClamp248k_Cmp",
            "ApplySettings_MaxAvgBitrateClamp248k_Mov",
            b"\x81\xFB", b"\xB8",
            max(text_start, af), min(text_end, af + 0x200),
        ))
    recreate_high = results.get("RecreateEncoder_BitrateCalcHigh_Channels_Mov248k")
    if recreate_high is not None:
        rf = recreate_high - adj
        clamp_windows.append((
            "SetBitrateClamp_Max248k_Cmp",
            "SetBitrateClamp_Max248k_Mov",
            b"\x81\xFB", b"\xB8",
            max(text_start, rf), min(text_end, rf + 0x120),
        ))
    set_br = results.get("SetBitrate_Imm64_Imm248k")
    if set_br is not None:
        sf = set_br - adj
        clamp_windows.append((
            "SetTargetBitrate_ClampMax248k_Cmp",
            "SetTargetBitrate_ClampMax248k_Mov",
            b"\x81\xFA", b"\xBA",
            max(text_start, sf - 0x80), min(text_end, sf + 0x80),
        ))
    set_mulss = results.get("SetTargetBitrate_Mulss_Nop6")
    if set_mulss is not None:
        mf = set_mulss - adj
        clamp_windows.append((
            "EncoderOpusImpl_RelayClamp248k_Cmp",
            "EncoderOpusImpl_RelayClamp248k_Mov",
            b"\x3D", b"\xBF",
            max(text_start, mf), min(text_end, mf + 0x400),
        ))

    for cmp_name, mov_name, cmp_op, mov_op, win_start, win_end in clamp_windows:
        if cmp_name in results and mov_name in results:
            continue
        pos = win_start
        while pos < win_end - 12:
            if cmp_op == b"\x3D":
                if data[pos] == 0x3D and data[pos + 1:pos + 5] in (max_stock, max248):
                    cmp_off = pos + adj
                    mov_at = pos + 5
                    if mov_at + 5 <= len(data) and data[mov_at] == 0xBF and data[mov_at + 1:mov_at + 5] in (max_stock, max248):
                        if cmp_name not in results:
                            results[cmp_name] = cmp_off
                            tiers_used[cmp_name] = "extended(clamp-window)"
                            print(f"  [ OK ] {cmp_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{cmp_off:08X}")
                        if mov_name not in results:
                            results[mov_name] = mov_at + adj
                            tiers_used[mov_name] = "extended(clamp-window)"
                            print(f"  [ OK ] {mov_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{mov_at + adj:08X}")
                        break
            elif data[pos:pos + 2] == cmp_op and data[pos + 2:pos + 6] in (max_stock, max248):
                cmp_off = pos + adj
                mov_at = pos + 6
                if mov_at + 5 <= len(data) and data[mov_at] == mov_op[0] and data[mov_at + 1:mov_at + 5] in (max_stock, max248):
                    if cmp_name not in results:
                        results[cmp_name] = cmp_off
                        tiers_used[cmp_name] = "extended(clamp-window)"
                        print(f"  [ OK ] {cmp_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{cmp_off:08X}")
                    if mov_name not in results:
                        results[mov_name] = mov_at + adj
                        tiers_used[mov_name] = "extended(clamp-window)"
                        print(f"  [ OK ] {mov_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{mov_at + adj:08X}")
                    break
            pos += 1

    for name, anchor, delta in (
        ("SetTargetBitrate_ClampMax248k_Cmp", "SetBitrate_Imm64_Imm248k", -0x3C),
        ("SetTargetBitrate_ClampMax248k_Mov", "SetTargetBitrate_ClampMax248k_Cmp", 0x6),
        ("EncoderOpusImpl_RelayClamp248k_Cmp", "SetTargetBitrate_Mulss_Nop6", 0x2FB),
        ("EncoderOpusImpl_RelayClamp248k_Mov", "EncoderOpusImpl_RelayClamp248k_Cmp", 0x5),
        ("SetBitrateClamp_Max248k_Cmp", "RecreateEncoder_BitrateCalcHigh_Channels_Mov248k", 0xD8),
        ("SetBitrateClamp_Max248k_Mov", "SetBitrateClamp_Max248k_Cmp", 0x6),
    ):
        _apply_derived(name, anchor, delta, f"derived({anchor}+0x{delta & 0xFFFFFFFF:X})")


def _discover_windows_extended_offsets_pe(data, bin_info, results, tiers_used, text_start, text_end):
    if bin_info.get("format") != "pe" or "CommitAudioCodec_ChannelCount_Imm02" not in results:
        return

    adj = bin_info.get("file_offset_adjustment", 0xC00)
    image_base = bin_info.get("image_base", 0x180000000)
    sections = bin_info.get("sections") or []

    print("\n" + "=" * 65)
    print("  PHASE 2c: Windows Extended (NetEq / Pacer / Discord API)")
    print("=" * 65)

    pat_ne = bytes.fromhex("48 B8 14 00 00 00 C8 00 00 00")
    ne_hits = []
    idx = text_start
    while idx < text_end:
        j = data.find(pat_ne, idx, text_end)
        if j < 0:
            break
        ne_hits.append(j + adj)
        idx = j + 1
    if len(ne_hits) == 1:
        rva = ne_hits[0]
        results["NetEqDelayManager_MsPerLoss_Imm0"] = rva
        tiers_used["NetEqDelayManager_MsPerLoss_Imm0"] = "extended(neteq-movabs)"
        print(f"  [ OK ] NetEqDelayManager_MsPerLoss_Imm0{' ':16s} = 0x{rva:X}  [movabs 14..C8]")
    elif not ne_hits:
        print("  [FAIL] NetEqDelayManager_MsPerLoss_Imm0: movabs pattern not found")
    else:
        print(f"  [FAIL] NetEqDelayManager_MsPerLoss_Imm0: ambiguous ({len(ne_hits)} movabs hits)")

    pacer_key = b"WebRTC-Pacer-BlockAudio\x00"
    pk = data.find(pacer_key)
    if pk < 0:
        print("  [FAIL] PacerBlockAudio_Flag_XorFalse: string WebRTC-Pacer-BlockAudio not found")
    else:
        str_rva = _pe_file_off_to_rva(pk, sections)
        if str_rva is None:
            print("  [FAIL] PacerBlockAudio_Flag_XorFalse: could not map string file offset to RVA")
        else:
            str_va = image_base + str_rva
            lea_rva = None
            i = text_start
            ts = bin_info.get("text_section") or {}
            tva = ts.get("vaddr", 0x1000)
            traw = ts.get("raw_offset", text_start)
            while i < text_end - 7:
                if data[i : i + 3] == b"\x48\x8d\x05":
                    disp = struct.unpack_from("<i", data, i + 3)[0]
                    insn_rva = tva + (i - traw)
                    tgt_va = image_base + insn_rva + 7 + disp
                    if tgt_va == str_va:
                        lea_rva = insn_rva
                        break
                i += 1
            if lea_rva is None:
                print("  [FAIL] PacerBlockAudio_Flag_XorFalse: no LEA to BlockAudio string in .text")
            else:
                lea_file = lea_rva - adj
                found_p = None
                for k in range(lea_file, min(lea_file + 0x120, text_end - 3)):
                    if data[k : k + 3] == b"\x0f\x94\xc3":
                        found_p = k + adj
                        break
                if found_p:
                    results["PacerBlockAudio_Flag_XorFalse"] = found_p
                    tiers_used["PacerBlockAudio_Flag_XorFalse"] = "extended(pacer-blockaudio)"
                    print(f"  [ OK ] PacerBlockAudio_Flag_XorFalse{' ':21s} = 0x{found_p:X}  [setz bl after LEA]")
                else:
                    print("  [FAIL] PacerBlockAudio_Flag_XorFalse: setz bl not found after LEA")

    exports = _pe_parse_exports(data, bin_info)
    if not exports:
        print(f"  [FAIL] Discord API lock sites: PE export directory unreadable")
    else:
        resolved = 0
        missing = []
        for name, mangled in WINDOWS_DISCORD_EXPORT_NAMES.items():
            rva = exports.get(mangled)
            if rva is None:
                missing.append(name)
                continue
            results[name] = rva
            tiers_used[name] = "extended(discord-api+pe-export)"
            resolved += 1
        if missing:
            print(f"  [WARN] Discord API lock sites: {resolved}/{len(WINDOWS_DISCORD_EXPORT_NAMES)} resolved; missing: {', '.join(missing)}")
        else:
            print(f"  [ OK ] Discord API lock sites{' ':26s} ({resolved} RVAs, PE export table)")


def discover_offsets(data, bin_info, verbose=True):
    _saved_stdout = None
    if not verbose:
        _saved_stdout = sys.stdout
        sys.stdout = io.StringIO()
    try:
        return _discover_offsets_impl(data, bin_info)
    finally:
        if _saved_stdout is not None:
            sys.stdout = _saved_stdout


def _discover_offsets_impl(data, bin_info):
    results = {}
    errors = []
    tiers_used = {}

    fmt = bin_info.get('format', 'raw') if bin_info else 'raw'
    adj = bin_info.get('file_offset_adjustment', 0) if bin_info else 0xC00
    if adj is None:
        adj = 0xC00 if fmt == 'pe' else 0

    # macOS: ARM64-only — do not run Windows/x86_64 signature scans on Mach-O slices.
    if fmt == 'macho':
        arch = bin_info.get('arch', '')
        print("\n" + "=" * 65)
        print("  macOS ARM64-only mode")
        print("=" * 65)
        if arch == 'arm64':
            print("  Skipping x86_64 / Windows-style signature scan.")
            print("  ARM64 patch sites are resolved via symbol table (find_macos_stereo_patches).")
            return results, errors, adj, tiers_used
        print("  [ERROR] Intel (x86_64) slice detected — no ARM64 slice found.")
        print("  macOS patching requires the ARM64 slice in discord_voice.node.")
        if bin_info.get('note'):
            print(f"  {bin_info['note']}")
        errors.append(("_platform", "ARM64-only: no arm64 slice in this Mach-O"))
        return results, errors, adj, tiers_used

    text_start = 0
    text_end = len(data)
    if bin_info and bin_info.get('text_section'):
        ts = bin_info['text_section']
        text_start = ts['raw_offset']
        text_end = text_start + ts['raw_size']
        if fmt == 'pe' and text_start + 16 <= len(data):
            prologue = data[text_start:text_start + 16]
            if not any(p in prologue for p in (b'\x55', b'\x48\x89\xE5', b'\x48\x83\xEC', b'\xE8', b'\x48\x8B')):
                print(f"  [WARN] PE .text at file 0x{text_start:X} does not contain common prologue bytes (55/48 89 E5/48 83 EC/E8)")

    sym_hints = {}
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
                                print(f"  [SKIP] {offset_name:<{OFFSET_LOG_NAME_WIDTH}s} symbol '{sym_name}' @0x{config_off:X} - bytes do not match")
                                accept = False

                if accept:
                    results[offset_name] = config_off
                    tiers_used[offset_name] = f"symbol({sym_name})"
                    print(f"  [SYM ] {offset_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{config_off:08X}  (file 0x{file_off:08X})  [{sym_name}]")

            elif method == 'symbol+scan':
                results[offset_name] = config_off
                tiers_used[offset_name] = f"symbol+scan({sym_name})"
                file_off = config_off - adj
                print(f"  [SCAN] {offset_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{config_off:08X}  (file 0x{file_off:08X})  [via {sym_name}]")

            elif method == 'symbol-range-hint':
                hint_key = f"_symhint_{offset_name}"
                if hint_key in sym_resolved:
                    sym_hints[offset_name] = sym_resolved[hint_key]
                    print(f"  [HINT] {offset_name:<{OFFSET_LOG_NAME_WIDTH}s} function '{sym_name}' - will do targeted scan")

        if not sym_details:
            print("  No symbol matches found - falling through to signature scanning")

    print("\n" + "=" * 65)
    print("  PHASE 1: Signature Scanning (primary + relaxed)")
    print("=" * 65)

    for sig in SIGNATURES:
        if fmt == "elf" and sig.name not in LINUX_WINDOWS_DISCOVERY_NAMES:
            continue
        if sig.name in results:
            print(f"  [SKIP] {sig.name:<{OFFSET_LOG_NAME_WIDTH}s} already resolved via symbol table")
            continue

        scan_start = text_start
        scan_end = text_end
        if sig.name in sym_hints:
            hint_start, hint_end, hint_sym = sym_hints[sig.name]
            scan_start = max(text_start, hint_start - 0x200)
            scan_end = min(text_end, hint_end + 0x200)

        file_off, err, tier = find_offset(data, sig, scan_start, scan_end)

        if err and sig.name in sym_hints:
            file_off, err, tier = find_offset(data, sig, text_start, text_end)

        if err:
            print(f"  [FAIL] {sig.name}: {err}")
            errors.append((sig.name, err))
        else:
            print(f"  [info] signature match at offset 0x{file_off:X}")
            ok, conf, val_msgs = _run_patch_site_validation(data, file_off, sig, adj)
            if not ok:
                for m in val_msgs:
                    print(f"  [warn] {m}")
                print(f"  [warn] {sig.name}: validation failed (confidence {conf} < {CONFIDENCE_THRESHOLD}), skipping")
                errors.append((sig.name, f"confidence {conf} < {CONFIDENCE_THRESHOLD}"))
                continue
            config_off = file_off + adj
            tag = "OK" if tier == "primary" else "ALT"
            print(f"  [{tag:4s}] {sig.name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{config_off:08X}  (file 0x{file_off:08X})  [{tier}] (conf={conf})")

            if sig.expected_original:
                expected = bytes.fromhex(sig.expected_original.replace(' ', ''))
                actual = data[file_off:file_off+len(expected)]
                if actual != expected:
                    print(f"         WARNING: Expected {expected.hex(' ')} but found {actual.hex(' ')}")

            results[sig.name] = config_off
            tiers_used[sig.name] = tier

    still_missing = [sig.name for sig in SIGNATURES if sig.name not in results]
    if still_missing:
        print("\n" + "=" * 65)
        print("  PHASE 1c: Clang/Platform-Specific Alternates")
        print("=" * 65)

        for sig_name, pat_hex, target_off in CLANG_ALT_PATTERNS:
            if fmt == "elf" and sig_name not in LINUX_WINDOWS_DISCOVERY_NAMES:
                continue
            if sig_name not in still_missing:
                continue
            if sig_name in results:
                continue

            pattern = Signature._parse(pat_hex)
            matches = scan_pattern(data, pattern, start=text_start, end=text_end)

            if len(matches) == 0:
                continue

            resolved = matches
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
                    ok, conf, _ = _run_patch_site_validation(data, file_off, orig_sig or {}, adj)
                    if not ok:
                        print(f"  [warn] {sig_name}: validation failed (confidence {conf}), skipping")
                    else:
                        config_off = file_off + adj
                        ambig = f"(ambig:{len(resolved)})" if len(resolved) > 1 else ""
                        tier = f"clang-alt{ambig}"
                        print(f"  [CLNG] {sig_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{config_off:08X}  (file 0x{file_off:08X})  [{tier}] (conf={conf})")
                        results[sig_name] = config_off
                        tiers_used[sig_name] = tier
                        still_missing = [n for n in still_missing if n != sig_name]

        if still_missing:
            print(f"  Still missing after Clang alts: {', '.join(still_missing)}")

    patched_fallbacks = []

    if "CapturedAudioProcessor_MonoDownmix_NopJmp" not in results:
        fb_pat = Signature._parse("48 89 F9 E8 ?? ?? ?? ?? 90 90 90 90 90 90 90 90 90 90 90 90 E9")
        matches = scan_pattern(data, fb_pat, start=text_start, end=text_end)
        if len(matches) > 1:
            matches = [m for m in matches if _mono_downmixer_disambiguator(data, m)]
        if len(matches) == 1:
            config_off = matches[0] + 8 + adj
            results["CapturedAudioProcessor_MonoDownmix_NopJmp"] = config_off
            tiers_used["CapturedAudioProcessor_MonoDownmix_NopJmp"] = "patched-fallback"
            patched_fallbacks.append("CapturedAudioProcessor_MonoDownmix_NopJmp")
            print(f"  [FALL] CapturedAudioProcessor_MonoDownmix_NopJmp{' ':30s} = 0x{config_off:X}  [patched NOP sled]")

    if fmt == "pe" and "SetBitrate_Imm64_Imm248k" not in results:
        for fb_hex in [
            "89 F8 48 B9 ?? ?? ?? ?? ?? ?? ?? ?? 90 90 90 48 89 4E 1C",
            "89 ?? 48 B9 ?? ?? ?? ?? ?? ?? ?? ?? 90 90 90 48 89 ?? ??",
        ]:
            fb_pat = Signature._parse(fb_hex)
            matches = scan_pattern(data, fb_pat, start=text_start, end=text_end)
            if len(matches) == 1:
                config_off = matches[0] + 4 + adj
                results["SetBitrate_Imm64_Imm248k"] = config_off
                tiers_used["SetBitrate_Imm64_Imm248k"] = "patched-fallback"
                patched_fallbacks.append("SetBitrate_Imm64_Imm248k")
                print(f"  [FALL] SetBitrate_Imm64_Imm248k{' ':20s} = 0x{config_off:X}  [patched or->NOP]")
                break

    if fmt == "pe" and "SetTargetBitrate_Mulss_Nop6" not in results and "SetBitrate_Imm64_Imm248k" in results:
        fo = results["SetBitrate_Imm64_Imm248k"] - adj + 0x40
        if 0 <= fo and fo + 6 <= len(data) and data[fo:fo + 6] == b"\x90" * 6:
            results["SetTargetBitrate_Mulss_Nop6"] = fo + adj
            tiers_used["SetTargetBitrate_Mulss_Nop6"] = "patched-fallback"
            patched_fallbacks.append("SetTargetBitrate_Mulss_Nop6")
            print(f"  [FALL] SetTargetBitrate_Mulss_Nop6{' ':20s} = 0x{fo + adj:X}  [patched mulss NOP]")

    if fmt == "pe" and "GetMultipliedBitrate_Mulss_Nop7" not in results:
        mulss_pat = Signature._parse("F3 0F 2A C0 90 90 90 90 90 90 90 F3 0F 2C C0 C3")
        matches = scan_pattern(data, mulss_pat, start=text_start, end=text_end)
        if len(matches) == 1:
            config_off = matches[0] + 4 + adj
            results["GetMultipliedBitrate_Mulss_Nop7"] = config_off
            tiers_used["GetMultipliedBitrate_Mulss_Nop7"] = "patched-fallback"
            patched_fallbacks.append("GetMultipliedBitrate_Mulss_Nop7")
            print(f"  [FALL] GetMultipliedBitrate_Mulss_Nop7{' ':15s} = 0x{config_off:X}  [patched mulss NOP]")

    if fmt == "pe" and "GetMultipliedBitrate_Entry_IdentityRet" not in results:
        for entry_pat in ("8B C1 C3", "89 C8 48"):
            pat = Signature._parse(entry_pat)
            matches = scan_pattern(data, pat, start=text_start, end=text_end)
            if len(matches) == 1:
                config_off = matches[0] + adj
                results["GetMultipliedBitrate_Entry_IdentityRet"] = config_off
                tiers_used["GetMultipliedBitrate_Entry_IdentityRet"] = "patched-fallback"
                patched_fallbacks.append("GetMultipliedBitrate_Entry_IdentityRet")
                print(f"  [FALL] GetMultipliedBitrate_Entry_IdentityRet{' ':10s} = 0x{config_off:X}  [identity/patched entry]")
                break

    if "hp_cutoff_Callback_InjectShellcode" not in results and fmt == "pe":
        hp_key = "WebRtcSplHighPass_Dispatch_MovRet"
        if hp_key not in results and "CommitAudioCodec_ChannelCount_Imm02" in results:
            results[hp_key] = results["CommitAudioCodec_ChannelCount_Imm02"] + 0xC275
        if hp_key in results:
            hp_file = results[hp_key] - adj
            if (0 <= hp_file and hp_file + 11 <= len(data) and
                data[hp_file] == 0x48 and data[hp_file+1] == 0xB8 and data[hp_file+10] == 0xC3):
                hpc_va = struct.unpack_from('<Q', data, hp_file + 2)[0]
                if fmt == 'pe' and bin_info:
                    hpc_config = hpc_va - bin_info['image_base']
                    if 0 < hpc_config < len(data):
                        results["hp_cutoff_Callback_InjectShellcode"] = hpc_config
                        tiers_used["hp_cutoff_Callback_InjectShellcode"] = "patched-stub-extract"
                        patched_fallbacks.append("hp_cutoff_Callback_InjectShellcode")
                        print(f"  [FALL] hp_cutoff_Callback_InjectShellcode{' ':23s} = 0x{hpc_config:X}  [from HP stub VA=0x{hpc_va:X}]")
                elif fmt in ('elf', 'macho'):
                    if 0 < hpc_va < len(data) + adj:
                        results["hp_cutoff_Callback_InjectShellcode"] = hpc_va
                        tiers_used["hp_cutoff_Callback_InjectShellcode"] = "patched-stub-extract"
                        patched_fallbacks.append("hp_cutoff_Callback_InjectShellcode")
                        print(f"  [FALL] hp_cutoff_Callback_InjectShellcode{' ':23s} = 0x{hpc_va:X}  [from HP stub VA]")

    if patched_fallbacks:
        print(f"\n  NOTE: Binary appears already patched. Fallback used for: {', '.join(patched_fallbacks)}")

    print("\n" + "=" * 65)
    print("  PHASE 2: Relative Offset Derivation (chain-aware)")
    print("=" * 65)

    for derived_name in _topo_sort_derivations(DERIVATIONS):
        if fmt == "elf" and derived_name not in LINUX_WINDOWS_DISCOVERY_NAMES:
            continue
        if derived_name in results:
            continue
        if fmt in ('elf', 'macho') and derived_name in _PHASE2_SKIP_CLANG:
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
                print(f"  [ OK ] {derived_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{config_off:08X}  (from {anchor_name} + 0x{delta:X})")
                results[derived_name] = config_off
                tiers_used[derived_name] = f"derived({anchor_name}+0x{delta:X})"
                found = True
                break

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
                    print(f"  [SLID] {derived_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{slid_off:08X}  "
                          f"(from {anchor_name} + 0x{delta:X} {sign}{slide_dist})")
                    results[derived_name] = slid_off
                    tiers_used[derived_name] = f"sliding({anchor_name}+0x{delta:X}{sign}{slide_dist})"
                    found = True
                    break

        if not found:
            _exp_drv = _build_expected_map(fmt)
            for anchor_name, delta in paths:
                if anchor_name not in results:
                    continue
                config_off = results[anchor_name] + delta
                file_off = config_off - adj
                if 0 <= file_off < len(data):
                    has_expected = False
                    if derived_name in _exp_drv:
                        exp_hex, _ = _exp_drv[derived_name]
                        if exp_hex:
                            has_expected = True
                    if has_expected:
                        continue
                    print(f"  [ OK ] {derived_name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{config_off:08X}  (from {anchor_name} + 0x{delta:X})  [unverified]")
                    results[derived_name] = config_off
                    tiers_used[derived_name] = f"derived-unverified({anchor_name}+0x{delta:X})"
                    found = True
                    break

        if not found:
            tried = ", ".join(a for a, _ in paths)
            print(f"  [FAIL] {derived_name}: no anchor available (tried: {tried})")
            errors.append((derived_name, f"no anchor available (tried: {tried})"))

    missing = _missing_discovered(results, fmt)
    if missing and fmt != "elf":
        print("\n" + "=" * 65)
        print("  PHASE 2b: Heuristic Recovery")
        print("=" * 65)

        if "ApplySettings_BitrateCalcLow_Channels_Mov248k" in missing and "CommitAudioCodec_ChannelCount_Imm02" in results:
            anchor_file = results["CommitAudioCodec_ChannelCount_Imm02"] - adj
            config_off, reason = _find_emulate_bitrate_in_anchor_window(data, anchor_file, adj, window=0x2000)
            if config_off is None and "SelectSampleRate_Cmov48k_Nop3" in results and "CommitAudioCodec_SuccessBranch_Jmp" in results:
                lo = min(anchor_file, results["SelectSampleRate_Cmov48k_Nop3"] - adj, results["CommitAudioCodec_SuccessBranch_Jmp"] - adj)
                hi = max(anchor_file, results["SelectSampleRate_Cmov48k_Nop3"] - adj, results["CommitAudioCodec_SuccessBranch_Jmp"] - adj)
                mid = (lo + hi) // 2
                config_off, reason = _find_emulate_bitrate_in_anchor_window(
                    data, mid, adj, window=(hi - lo) // 2 + 0x2000
                )
            if config_off is None and text_start < text_end:
                full_window = max(anchor_file - text_start, text_end - anchor_file)
                if full_window > 0x2000:
                    config_off, reason = _find_emulate_bitrate_in_anchor_window(data, anchor_file, adj, window=full_window)
                    if config_off is not None:
                        reason = f"full-text-scan({reason})"
            if config_off is not None:
                ebm_file = config_off - adj
                dist = abs(ebm_file - anchor_file)
                if dist > 0x20000:
                    print(f"  [REJECT] ApplySettings_BitrateCalcLow_Channels_Mov248k @ 0x{config_off:X} - too far from anchor (0x{dist:X} > 0x20000), skipping")
                    config_off = None
                else:
                    tag = "FULL-TEXT" if "full-text-scan" in reason else "ANCHOR"
                    print(f"  [{tag}] ApplySettings_BitrateCalcLow_Channels_Mov248k    = 0x{config_off:X}  "
                          f"[{reason}]  (distance from ApplySettings anchor: 0x{dist:X})")
                    results["ApplySettings_BitrateCalcLow_Channels_Mov248k"] = config_off
                    tiers_used["ApplySettings_BitrateCalcLow_Channels_Mov248k"] = reason
                    missing = _missing_discovered(results, fmt)

        hints = _run_heuristic_scan(data, missing, adj, text_start, text_end)
        ebm_far_candidates = []
        if hints:
            EMULATE_BITRATE_MAX_DISTANCE = 0x2000
            for name, file_off, reason in hints:
                if name in results:
                    continue
                if name == "ApplySettings_BitrateCalcLow_Channels_Mov248k" and "CommitAudioCodec_ChannelCount_Imm02" in results:
                    anchor_file = results["CommitAudioCodec_ChannelCount_Imm02"] - adj
                    if abs(file_off - anchor_file) > EMULATE_BITRATE_MAX_DISTANCE:
                        ebm_far_candidates.append((file_off, reason))
                        print(f"  [HEUR] Rejected {name} @ 0x{file_off + adj:X} - too far from CommitAudioCodec_ChannelCount_Imm02 (delta 0x{abs(file_off - anchor_file):X} > 0x{EMULATE_BITRATE_MAX_DISTANCE:X})")
                        continue
                config_off = file_off + adj
                _exp_map = _build_expected_map(fmt)
                if name in _exp_map:
                    exp_hex, exp_len = _exp_map[name]
                    if exp_hex:
                        expected = bytes.fromhex(exp_hex.replace(' ', ''))
                        actual = data[file_off:file_off+len(expected)]
                        if actual != expected:
                            continue
                print(f"  [HEUR] {name:<{OFFSET_LOG_NAME_WIDTH}s}  = 0x{config_off:08X}  [{reason}]")
                results[name] = config_off
                tiers_used[name] = f"heuristic({reason})"

        if "ApplySettings_BitrateCalcLow_Channels_Mov248k" not in results and ebm_far_candidates and fmt == "macho" and "CommitAudioCodec_ChannelCount_Imm02" in results:
            anchor_file = results["CommitAudioCodec_ChannelCount_Imm02"] - adj
            expected_32000 = bytes.fromhex("007D00")
            valid = []
            for file_off, reason in ebm_far_candidates:
                if file_off + 3 <= len(data) and data[file_off:file_off + 3] == expected_32000:
                    valid.append((file_off, abs(file_off - anchor_file)))
            if valid:
                valid.sort(key=lambda x: x[1])
                file_off = valid[0][0]
                config_off = file_off + adj
                results["ApplySettings_BitrateCalcLow_Channels_Mov248k"] = config_off
                tiers_used["ApplySettings_BitrateCalcLow_Channels_Mov248k"] = "fallback-far(imul 32000,closest-to-anchor)"
                print(f"  [FALLBACK-FAR] ApplySettings_BitrateCalcLow_Channels_Mov248k = 0x{config_off:X}  (no in-window candidate; using closest imul 32000 - VERIFY bitrate after patch)")
                missing = _missing_discovered(results, fmt)

        if not hints:
            still = _missing_discovered(results, fmt)
            if still:
                print(f"  No heuristic candidates for: {', '.join(still)}")

    if fmt == "pe" and bin_info:
        _discover_windows_extended_offsets_pe(data, bin_info, results, tiers_used, text_start, text_end)
        _discover_bitrate_v18_offsets_pe(data, bin_info, results, tiers_used, text_start, text_end)

    validation_failures = _validate_discovered_offsets(results, data, adj)
    for name, reason in validation_failures:
        results.pop(name, None)
        tiers_used.pop(name, None)
        errors.append((name, reason))
        print(f"  [INVALID] {name}: {reason}")

    errors = [(n, e) for n, e in errors if n not in results]
    _err_seen = {}
    for n, e in errors:
        if n not in _err_seen:
            _err_seen[n] = e
    errors = list(_err_seen.items())

    _prune_results_to_allowed(results, tiers_used, label=fmt)

    if fmt == "elf":
        _prune_elf_linux_discovery(results, tiers_used)

    _log_context_fingerprints(data, results, adj)

    return results, errors, adj, tiers_used




def _resolve_elf_symbols(bin_info, data):
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

        if mapping.get('exclude_patterns'):
            candidates = [c for c in candidates
                          if not any(ep in c['name'] for ep in mapping['exclude_patterns'])]
            if not candidates:
                continue

        if mapping.get('prefer_smallest'):
            candidates.sort(key=lambda c: c.get('size', 0x10000))
        elif mapping.get('prefer_largest'):
            candidates.sort(key=lambda c: c.get('size', 0), reverse=True)

        best = candidates[0]
        for c in candidates:
            if any(p.lower() == c['name'].lower().rstrip('_') for p in mapping['patterns']):
                best = c
                break

        sym_addr = best['value']

        if mapping['at_start']:
            file_off = sym_addr - adj
            if 0 <= file_off < len(data):
                resolved[offset_name] = sym_addr
                details.append((offset_name, sym_addr, best['name'], 'symbol-direct'))
        else:
            linux_scan = mapping.get('linux_scan')
            scan_found = False
            for candidate in candidates:
                func_size = candidate.get('size', 0)
                if func_size == 0 or func_size > 0x10000:
                    func_size = 0x2000

                func_file_start = candidate['value'] - adj
                if func_file_start < 0:
                    func_file_start = 0

                if linux_scan:
                    result = _linux_scan_within_function(
                        data, func_file_start, func_size, linux_scan, adj)
                    if result is not None:
                        resolved[offset_name] = result
                        details.append((offset_name, result, candidate['name'], 'symbol+scan'))
                        scan_found = True
                        break

            if not scan_found:
                func_size = best.get('size', 0)
                if func_size == 0 or func_size > 0x10000:
                    func_size = 0x2000
                func_file_start = sym_addr - adj
                if func_file_start < 0:
                    func_file_start = 0

                if linux_scan:
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

def scan_pattern(data, pattern, limit=0, start=0, end=None):
    matches = []
    pat_len = len(pattern)
    if end is None:
        end = len(data)

    first_fixed = None
    for i, b in enumerate(pattern):
        if b is not None:
            first_fixed = (i, b)
            break

    if first_fixed is None:
        return matches

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
                if sig.name == "CommitAudioCodec_ChannelCount_Imm02" and not has_nearby_stereo_setter(data, matches[0], 120):
                    print(f"  [FILTER] CommitAudioCodec_ChannelCount_Imm02 @ 0x{matches[0]:X} has no nearby stereo setter (accepting anyway)")
                return file_offset, None, tier

        resolved = list(matches)
        if sig.disambiguator and len(resolved) > 1:
            valid = [m for m in resolved if sig.disambiguator(data, m)]
            if len(valid) >= 1:
                resolved = valid

        if sig.name == "CommitAudioCodec_ChannelCount_Imm02" and len(resolved) >= 1:
            resolved = [m for m in resolved if _ess1_no_duplicate_cmp_in_next_24(data, m)]
            if not resolved:
                continue
        if sig.name == "CommitAudioCodec_ChannelCount_Imm02" and len(resolved) >= 1:
            with_setter = [m for m in resolved if has_nearby_stereo_setter(data, m, 120)]
            if len(resolved) > 1 and len(with_setter) >= 1:
                for m in resolved:
                    if m not in with_setter:
                        print(f"  [FILTER] Rejected CommitAudioCodec_ChannelCount_Imm02 @ 0x{m:X} - no nearby stereo setter")
                resolved = with_setter
            elif len(resolved) == 1 and not with_setter:
                print(f"  [FILTER] CommitAudioCodec_ChannelCount_Imm02 @ 0x{resolved[0]:X} has no nearby stereo setter (accepting anyway)")

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
            if tier != "primary":
                file_offset = resolved[0] + target_off
                if 0 <= file_offset < len(data):
                    return file_offset, None, f"{tier}(ambig:{len(resolved)})"

    return None, f"no matches across {len(tiers)} tier(s)", "none"

CONFIDENCE_THRESHOLD = 75

CONFIDENCE_SIGNATURE_MATCH = 50

CONFIDENCE_CONTEXT_VALID = 25

CONFIDENCE_ORIGINAL_BYTES = 25

CONFIDENCE_FINGERPRINT_MATCH = 20

CONFIDENCE_HEURISTIC_PATTERN = 15

_OPCODE_PREFIXES = (0x66, 0xF2, 0xF3, 0x2E, 0x3E, 0x26, 0x64, 0x65, 0x36)

_COMMON_OPCODES = (0x48, 0x49, 0x4C, 0x4D, 0x55, 0x53, 0x56, 0x57, 0x41, 0xC3,
                   0x89, 0x8B, 0xB8, 0xB9, 0xC7, 0xE8, 0xE9, 0x74, 0x75, 0x0F)

def validate_context(binary_data, offset, expected_prefix=None, expected_suffix=None):
    if not isinstance(binary_data, (bytes, bytearray)):
        return False
    n = len(binary_data)
    if offset < 0 or offset >= n:
        return False
    before = min(32, offset)
    after = min(32, n - offset)
    if before < 16 or after < 16:
        return False
    pre = binary_data[offset - before:offset]
    suf = binary_data[offset:offset + after]
    if pre == b'\x00' * len(pre) or pre == b'\xff' * len(pre):
        return False
    if suf == b'\x00' * len(suf) or suf == b'\xff' * len(suf):
        return False
    is_arm64 = False
    if offset % 4 == 0 and len(pre) >= 16:
        arm64_like = 0
        for i in range(0, min(16, len(pre)) - 3, 4):
            top_byte = pre[i + 3]
            if top_byte in (0xD6, 0xF9, 0xA9, 0x52, 0x72, 0xB9, 0x91, 0xD2,
                            0x94, 0x97, 0x54, 0x36, 0x37, 0x34, 0x35, 0x14,
                            0x17, 0xAA, 0x2A, 0x6B, 0xEB, 0x71, 0xF1):
                arm64_like += 1
        if arm64_like >= 2:
            is_arm64 = True
    if is_arm64:
        arm_valid = 0
        for i in range(0, min(16, len(pre)) - 3, 4):
            word = struct.unpack_from('<I', pre, i)[0]
            top4 = (word >> 28) & 0xF
            if top4 in (0x0, 0x1, 0x2, 0x3, 0x5, 0x6, 0x7, 0x9, 0xA, 0xB, 0xD, 0xF):
                arm_valid += 1
        return arm_valid >= 2
    opcode_like = sum(1 for b in pre[-16:] if b in _COMMON_OPCODES or b in _OPCODE_PREFIXES)
    if opcode_like < 2:
        return False
    if expected_prefix is not None:
        exp = expected_prefix if isinstance(expected_prefix, bytes) else bytes.fromhex(expected_prefix.replace(' ', ''))
        if len(exp) > 0 and len(suf) >= len(exp) and suf[:len(exp)] != exp:
            return False
    if expected_suffix is not None:
        exp = expected_suffix if isinstance(expected_suffix, bytes) else bytes.fromhex(expected_suffix.replace(' ', ''))
        if len(exp) > 0 and len(pre) >= len(exp) and pre[-len(exp):] != exp:
            return False
    return True

def compute_function_fingerprint(binary_data, offset, window=96):
    n = len(binary_data)
    if offset < 0 or offset >= n:
        return ""
    half = window // 2
    start = max(0, offset - half)
    end = min(n, offset + half)
    if end - start < 16:
        return ""
    region = bytearray(binary_data[start:end])
    rlen = len(region)
    i = 0
    while i < rlen - 2:
        b0 = region[i]
        b1 = region[i + 1] if i + 1 < rlen else 0
        if 0xB8 <= b0 <= 0xBF and i + 5 <= rlen:
            for j in range(1, 5):
                region[i + j] = 0
            i += 5
            continue
        if b0 == 0x48 and 0xB8 <= b1 <= 0xBF and i + 10 <= rlen:
            for j in range(2, 10):
                region[i + j] = 0
            i += 10
            continue
        if b0 in (0xE8, 0xE9) and i + 5 <= rlen:
            for j in range(1, 5):
                region[i + j] = 0
            i += 5
            continue
        if b0 == 0xEB or (0x70 <= b0 <= 0x7F):
            if i + 2 <= rlen:
                region[i + 1] = 0
            i += 2
            continue
        if b0 == 0x48 and b1 == 0xC7 and i + 7 <= rlen:
            for j in range(3, 7):
                if i + j < rlen:
                    region[i + j] = 0
            i += 7
            continue
        if b0 in (0x48, 0x4C) and b1 == 0x8D and i + 6 <= rlen:
            for j in range(3, min(7, rlen - i)):
                region[i + j] = 0
            i += 7
            continue
        if b0 == 0x0F and 0x80 <= b1 <= 0x8F and i + 6 <= rlen:
            for j in range(2, 6):
                region[i + j] = 0
            i += 6
            continue
        i += 1
    return hashlib.sha1(bytes(region)).hexdigest()

def _detect_function_boundary(binary_data, offset, direction=-1, max_scan=512):
    n = len(binary_data)
    if offset < 0 or offset >= n:
        return None, 0


    if direction < 0:
        start = max(0, offset - max_scan)
        for i in range(offset - 1, start, -1):
            b = binary_data[i]
            if b == 0xCC and i + 4 <= n:
                run = 0
                for j in range(i, min(i + 8, n)):
                    if binary_data[j] == 0xCC:
                        run += 1
                    else:
                        break
                if run >= 3:
                    boundary = i + run
                    if boundary <= offset:
                        return boundary, 8
            if b == 0xC3 and i + 2 <= n:
                nxt = binary_data[i + 1]
                if nxt in (0x90, 0x66, 0x0F, 0xCC):
                    boundary = i + 1
                    while boundary < n and binary_data[boundary] in (0x90, 0xCC):
                        boundary += 1
                    if boundary <= offset:
                        return boundary, 6
        return None, 0
    else:
        end = min(n, offset + max_scan)
        for i in range(offset, end):
            b = binary_data[i]
            if b == 0xC3 and i > offset + 4:
                if i + 1 < n and binary_data[i + 1] in (0xCC, 0x90, 0x66, 0x0F):
                    return i, 7
                if i + 1 < n and binary_data[i + 1] in (0x55, 0x56, 0x57, 0x41, 0x53):
                    return i, 5
            if b == 0xCC and i + 3 < n:
                if binary_data[i + 1] == 0xCC and binary_data[i + 2] == 0xCC:
                    return i, 7
        return None, 0

def _estimate_instruction_flow(binary_data, offset, count=8):
    n = len(binary_data)
    pos = offset
    valid = 0
    checked = 0

    rex_range = range(0x40, 0x50)
    mandatory_prefixes = (0x66, 0xF2, 0xF3)
    _LEN_HINTS = {
        0x50: (1, 1), 0x51: (1, 1), 0x52: (1, 1), 0x53: (1, 1),
        0x54: (1, 1), 0x55: (1, 1), 0x56: (1, 1), 0x57: (1, 1),
        0x58: (1, 1), 0x59: (1, 1), 0x5A: (1, 1), 0x5B: (1, 1),
        0x5C: (1, 1), 0x5D: (1, 1), 0x5E: (1, 1), 0x5F: (1, 1),
        0x90: (1, 1), 0xC3: (1, 1), 0xCC: (1, 1), 0xCB: (1, 1),
        0xC9: (1, 1),
        0xE8: (5, 5), 0xE9: (5, 5),
        0xEB: (2, 2),
        0x74: (2, 2), 0x75: (2, 2), 0x70: (2, 2), 0x71: (2, 2),
        0x72: (2, 2), 0x73: (2, 2), 0x76: (2, 2), 0x77: (2, 2),
        0x78: (2, 2), 0x79: (2, 2), 0x7A: (2, 2), 0x7B: (2, 2),
        0x7C: (2, 2), 0x7D: (2, 2), 0x7E: (2, 2), 0x7F: (2, 2),
        0xB8: (5, 5), 0xB9: (5, 5), 0xBA: (5, 5), 0xBB: (5, 5),
        0xBC: (5, 5), 0xBD: (5, 5), 0xBE: (5, 5), 0xBF: (5, 5),
    }

    while checked < count and pos < n - 1:
        b0 = binary_data[pos]
        step = 0

        adj_pos = pos
        if b0 in rex_range:
            adj_pos += 1
            if adj_pos >= n:
                break
            b0_inner = binary_data[adj_pos]
        else:
            b0_inner = b0

        if b0_inner in _LEN_HINTS:
            mn, mx = _LEN_HINTS[b0_inner]
            step = mn + (adj_pos - pos)
            valid += 1
        elif b0 in mandatory_prefixes or b0 in rex_range:
            step = 3
            valid += 1
        elif b0 in (0x0F,):
            step = 3
            valid += 1
        elif b0 in _COMMON_OPCODES or b0 in _OPCODE_PREFIXES:
            step = 2
            valid += 1
        else:
            step = 2

        checked += 1
        pos += max(step, 1)

    return valid, checked

def run_heuristic_analysis(binary_data, offset, patch_len=4):
    if offset < 32 or offset + 32 > len(binary_data):
        return False, 0
    score = 0
    pre = binary_data[offset - 24:offset]
    suf = binary_data[offset:offset + 24]

    bound_start, bound_conf = _detect_function_boundary(binary_data, offset, direction=-1, max_scan=1024)
    if bound_start is not None:
        dist = offset - bound_start
        if dist < 4096:
            score += 3
    bound_end, end_conf = _detect_function_boundary(binary_data, offset, direction=+1, max_scan=1024)
    if bound_end is not None:
        dist = bound_end - offset
        if dist < 4096:
            score += 2

    valid_insns, checked = _estimate_instruction_flow(binary_data, max(0, offset - 16), count=6)
    if checked > 0 and valid_insns >= (checked * 2 // 3):
        score += 3
    valid_after, checked_after = _estimate_instruction_flow(binary_data, offset, count=6)
    if checked_after > 0 and valid_after >= (checked_after * 2 // 3):
        score += 2

    if pre[-1] in (0x55, 0x53, 0x56, 0x57):
        score += 2
    if len(pre) >= 3 and pre[-3] == 0x48 and pre[-2] == 0x83 and pre[-1] == 0xEC:
        score += 2
    for i in range(len(pre) - 4):
        if pre[i:i+4] == b'\x55\x48\x89\xe5':
            score += 2
            break

    for i in range(len(pre) - 2):
        if pre[i] in (0x48, 0x49, 0x4C) and pre[i + 1] in (0x89, 0x8B, 0xC7, 0x09, 0x01):
            score += 2
            break

    for i in range(min(16, len(suf) - 1)):
        if suf[i] == 0xC3:
            score += 2
            break
        if suf[i] in (0x74, 0x75, 0x0F) and i + 1 < len(suf):
            score += 1
            break

    region = binary_data[max(0, offset - 32):min(len(binary_data), offset + 32)]
    opcode_hits = sum(1 for b in region if b in _COMMON_OPCODES or b in _OPCODE_PREFIXES)
    density = opcode_hits / max(len(region), 1)
    if density > 0.15:
        score += 2

    return score >= 5, min(15, score)

def calculate_confidence(signature_match, context_valid, original_bytes_match,
                         fingerprint_match, heuristic_score):
    total = 0
    if signature_match:
        total += CONFIDENCE_SIGNATURE_MATCH
    if context_valid:
        total += CONFIDENCE_CONTEXT_VALID
    if original_bytes_match:
        total += CONFIDENCE_ORIGINAL_BYTES
    if fingerprint_match:
        total += CONFIDENCE_FINGERPRINT_MATCH
    total += min(CONFIDENCE_HEURISTIC_PATTERN, heuristic_score)
    return total

def validate_patch_site(binary_data, offset, expected_original_bytes, patch_bytes,
                        patch_name="", known_fingerprints=None, expected_prefix=None,
                        expected_suffix=None):
    messages = []
    if offset < 0 or offset >= len(binary_data):
        return False, 0, ["offset out of bounds"]
    if isinstance(expected_original_bytes, str):
        exp_orig = bytes.fromhex(expected_original_bytes.replace(' ', '')) if expected_original_bytes.strip() else b''
    else:
        exp_orig = expected_original_bytes or b''
    if isinstance(patch_bytes, str):
        patch_b = bytes.fromhex(patch_bytes.replace(' ', '')) if patch_bytes.strip() else b''
    else:
        patch_b = patch_bytes or b''
    read_len = max(len(exp_orig), len(patch_b), 1)
    if offset + read_len > len(binary_data):
        return False, 0, ["patch region exceeds binary size"]
    current = binary_data[offset:offset + read_len]
    orig_match = True
    if len(exp_orig) > 0:
        if current[:len(exp_orig)] != exp_orig:
            orig_match = False
            messages.append("unexpected bytes at patch location")
    ctx_ok = validate_context(binary_data, offset, expected_prefix, expected_suffix)
    if not ctx_ok:
        messages.append("context validation failed")
    fp = compute_function_fingerprint(binary_data, offset)
    fp_match = False
    if known_fingerprints and fp and fp in known_fingerprints:
        fp_match = True
    elif known_fingerprints and fp:
        messages.append("fingerprint mismatch")
    heur_ok, heur_score = run_heuristic_analysis(binary_data, offset, len(patch_b))
    if orig_match and len(exp_orig) > 0:
        heur_ok, heur_score = True, CONFIDENCE_HEURISTIC_PATTERN
    elif not heur_ok:
        messages.append("heuristic analysis uncertain")
    conf = calculate_confidence(True, ctx_ok, orig_match, fp_match, heur_score)
    ok = conf >= CONFIDENCE_THRESHOLD
    return ok, conf, messages

def _run_patch_site_validation(data, file_offset, sig_or_dict, adj=0):
    if hasattr(sig_or_dict, 'expected_original') and hasattr(sig_or_dict, 'patch_bytes'):
        exp = sig_or_dict.expected_original or ''
        patch = sig_or_dict.patch_bytes or ''
        name = getattr(sig_or_dict, 'name', '')
    else:
        exp = sig_or_dict.get('o', '') or ''
        patch = sig_or_dict.get('x', '') or ''
        name = sig_or_dict.get('n', '') or ''
    if patch.startswith('<'):
        return True, 100, []
    if not exp and not patch:
        return True, 100, []
    try:
        exp_b = bytes.fromhex(exp.replace(' ', '')) if exp.strip() else b''
    except ValueError:
        exp_b = b''
    try:
        patch_b = bytes.fromhex(patch.replace(' ', '')) if patch.strip() else b''
    except ValueError:
        patch_b = b''
    if not exp_b and not patch_b:
        return True, 100, []
    if file_offset < 0 or file_offset >= len(data):
        return False, 0, ["offset out of bounds"]
    read_len = max(len(exp_b), len(patch_b))
    if file_offset + read_len > len(data):
        return False, 0, ["patch region exceeds binary size"]
    ok, conf, msgs = validate_patch_site(data, file_offset, exp_b or patch_b, patch_b or exp_b,
                                          patch_name=name)
    return ok, conf, msgs

def _topo_sort_derivations(derivations):
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

_WINDOWS_PATCHER_OFFSET_ORDER = (
    "CreateAudioFrame_ChannelAssign_Mov",
    "AudioEncoderOpusConfig_Ctor_Channels_Imm02",
    "CapturedAudioProcessor_MonoDownmix_NopJmp",
    "CommitAudioCodec_ChannelCount_Imm02",
    "CommitAudioCodec_SuccessBranch_Jmp",
    "ApplySettings_BitrateCalcLow_Channels_Mov248k",
    "ApplySettings_BitrateCalcMid_Channels_Mov248k",
    "ApplySettings_BitrateCalcHigh_Channels_Mov248k",
    "RecreateEncoder_BitrateCalcLow_Channels_Mov248k",
    "RecreateEncoder_BitrateCalcMid_Channels_Mov248k",
    "RecreateEncoder_BitrateCalcHigh_Channels_Mov248k",
    "SetBitrateClamp_Max248k_Cmp",
    "SetBitrateClamp_Max248k_Mov",
    "AudioBitrateAdaptorCalc32k_Channels_Mov248k",
    "AudioBitrateAdaptorCalc48k_Channels_Mov248k",
    "AudioBitrateAdaptorCalc60k_Channels_Mov248k",
    "SetBitrate_Imm64_Imm248k",
    "SetBitrate_OrMask_Nop3",
    "SetTargetBitrate_Mulss_Nop6",
    "GetMultipliedBitrate_Mulss_Nop7",
    "GetMultipliedBitrate_Entry_IdentityRet",
    "SetTargetBitrate_ClampMax248k_Cmp",
    "SetTargetBitrate_ClampMax248k_Mov",
    "ApplySettings_MaxAvgBitrateClamp248k_Cmp",
    "ApplySettings_MaxAvgBitrateClamp248k_Mov",
    "EncoderOpusImpl_RelayClamp248k_Cmp",
    "EncoderOpusImpl_RelayClamp248k_Mov",
    "SelectSampleRate_Cmov48k_Nop3",
    "WebRtcSplHighPass_Dispatch_MovRet",
    "hp_cutoff_Callback_InjectShellcode",
    "dc_reject_Callback_InjectShellcode",
    "ChannelDownmix_Entry_Ret",
    "AudioEncoderOpusConfig_IsOK_MovTrueRet",
    "CodecMismatchThrow_Entry_Ret",
    "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k",
    "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k",
    "AudioEncoderOpusConfig_Ctor_FrameMs_Imm10",
    "AudioEncoderOpusConfig_Ctor_Application_ImmAudio",
    "CELT_Force",
    "CELT_DefaultMode",
    "NetEqDelayManager_MsPerLoss_Imm0",
    "PacerBlockAudio_Flag_XorFalse",
    "SetAutomaticGainControlConfig_Entry_Ret",
    "SetAutomaticGainControl_Entry_Ret",
    "SetNoiseSuppression_Entry_Ret",
    "SetEchoCancellation_Entry_Ret",
    "SetEchoCancellationPreEcho_Entry_Ret",
    "EnableBuiltInAEC_Entry_Ret",
    "SetNoiseCancellation_Entry_Ret",
    "SetNoiseCancellationDuringProcessing_Entry_Ret",
)

_WINDOWS_PATCHER_CORE_COUNT = 40
if len(_WINDOWS_PATCHER_OFFSET_ORDER) != 50:
    raise RuntimeError("_WINDOWS_PATCHER_OFFSET_ORDER must be 50 entries (patcher v19.0 sync)")

ALL_OFFSET_NAMES = list(_WINDOWS_PATCHER_OFFSET_ORDER[:_WINDOWS_PATCHER_CORE_COUNT])

WINDOWS_PATCHER_OFFSET_NAMES = list(_WINDOWS_PATCHER_OFFSET_ORDER[:_WINDOWS_PATCHER_CORE_COUNT])

WINDOWS_EXTENDED_OFFSET_NAMES = list(_WINDOWS_PATCHER_OFFSET_ORDER[_WINDOWS_PATCHER_CORE_COUNT:])

LINUX_ONLY_OFFSET_NAMES = ("OpusEncoderConfig_SetMultiChannelStereo",)


def _compute_linux_windows_discovery_names():
    """Windows-style finder keys needed to resolve Linux patcher offsets (derivation closure)."""
    needed = set(LINUX_FROM_WINDOWS.keys()) | set(LINUX_ONLY_OFFSET_NAMES)
    changed = True
    while changed:
        changed = False
        for derived, paths in DERIVATIONS.items():
            if derived in needed:
                continue
            if any(anchor in needed for anchor, _ in paths):
                needed.add(derived)
                changed = True
    return frozenset(needed)


LINUX_WINDOWS_DISCOVERY_NAMES = _compute_linux_windows_discovery_names()


def _prune_elf_linux_discovery(results, tiers_used=None):
    """Drop Windows-only discovery results on ELF after Linux mapping inputs are resolved."""
    removed = [k for k in list(results.keys()) if k not in LINUX_WINDOWS_DISCOVERY_NAMES]
    for k in removed:
        results.pop(k, None)
        if tiers_used is not None:
            tiers_used.pop(k, None)
    if removed:
        print(f"  [INFO] Pruned Windows-only offset(s) on ELF: {', '.join(removed)}")


def _all_offset_names():
    return list(ALL_OFFSET_NAMES) + list(LINUX_ONLY_OFFSET_NAMES)

def _missing_discovered(results, fmt):
    if fmt == "pe":
        names = list(PATCHER_OFFSET_NAMES)
    elif fmt == "elf":
        names = list(LINUX_WINDOWS_DISCOVERY_NAMES)
    else:
        names = list(_all_offset_names())
    return [n for n in names if n not in results]

WINDOWS_DISCORD_EXPORT_NAMES = {
    "SetAutomaticGainControlConfig_Entry_Ret": "?SetAutomaticGainControlConfig@Discord@@QEAAXUGainControllerConfig@media@discord@@@Z",
    "SetAutomaticGainControl_Entry_Ret": "?SetAutomaticGainControl@Discord@@QEAAX_N@Z",
    "SetNoiseSuppression_Entry_Ret": "?SetNoiseSuppression@Discord@@QEAAX_N@Z",
    "SetEchoCancellation_Entry_Ret": "?SetEchoCancellation@Discord@@QEAAX_N@Z",
    "SetEchoCancellationPreEcho_Entry_Ret": "?SetEchoCancellationPreEcho@Discord@@QEAAX_N@Z",
    "EnableBuiltInAEC_Entry_Ret": "?EnableBuiltInAEC@Discord@@QEAAX_N@Z",
    "SetNoiseCancellation_Entry_Ret": "?SetNoiseCancellation@Discord@@QEAAX_N@Z",
    "SetNoiseCancellationDuringProcessing_Entry_Ret": "?SetNoiseCancellationDuringProcessing@Discord@@QEAAX_N@Z",
}

PATCHER_OFFSET_NAMES = list(_WINDOWS_PATCHER_OFFSET_ORDER)

PATCHER_OFFSET_NAME_WIDTH = max(len(n) for n in PATCHER_OFFSET_NAMES)

OFFSET_LOG_NAME_WIDTH = PATCHER_OFFSET_NAME_WIDTH

def count_patcher_offsets_found(results, patcher_names=None):
    names = list(dict.fromkeys(patcher_names or PATCHER_OFFSET_NAMES))
    hits = sum(1 for k in names if k in results)
    return hits, len(names)

ALLOWED_OFFSET_NAMES = (
    frozenset(ALL_OFFSET_NAMES)
    | frozenset(WINDOWS_EXTENDED_OFFSET_NAMES)
    | frozenset(LINUX_ONLY_OFFSET_NAMES)
)

def _log_context_fingerprints(data, results, adj):
    critical = [
        "CommitAudioCodec_ChannelCount_Imm02", "AudioEncoderOpusConfig_Ctor_Channels_Imm02", "CapturedAudioProcessor_MonoDownmix_NopJmp",
        "SetBitrate_Imm64_Imm248k", "CreateAudioFrame_ChannelAssign_Mov",
    ]
    for name in critical:
        if name not in results:
            continue
        rva = results[name]
        file_off = rva - adj
        if file_off < 32 or file_off + 32 > len(data):
            continue
        region = data[file_off - 32:file_off + 32]
        fp = hashlib.sha1(region).hexdigest()[:16]
        print(f"  [CONTEXT FINGERPRINT] {name} @ 0x{rva:X}  sha1:{fp}...")

def _prune_results_to_allowed(results, tiers_used=None, label=""):
    if not results:
        return
    removed = [k for k in list(results.keys()) if k not in ALLOWED_OFFSET_NAMES]
    for k in removed:
        results.pop(k, None)
        if tiers_used is not None:
            tiers_used.pop(k, None)
    if removed and label:
        print(f"  [INFO] Pruned non-patcher offset(s) from {label}: {', '.join(removed)}")

def _sliding_window_recover(data, anchor_config, delta, name, adj, bin_fmt='pe'):
    exp_map = _build_expected_map(bin_fmt)

    if name not in exp_map:
        return None, 0

    exp_hex, exp_len = exp_map[name]
    if not exp_hex:
        return None, 0

    expected = bytes.fromhex(exp_hex.replace(' ', ''))
    if len(expected) < 2:
        window = min(SLIDING_WINDOW_OVERRIDES.get(name, 16), 16)
    else:
        window = SLIDING_WINDOW_OVERRIDES.get(name, SLIDING_WINDOW_DEFAULT)

    exact_file = anchor_config + delta - adj

    if 0 <= exact_file and exact_file + len(expected) <= len(data):
        if data[exact_file:exact_file + len(expected)] == expected:
            return anchor_config + delta, 0

    if len(expected) == 1:
        candidates = []
        for dist in range(1, window + 1):
            for direction in (+1, -1):
                candidate = exact_file + (dist * direction)
                if 0 <= candidate and candidate + 1 <= len(data):
                    if data[candidate:candidate + 1] == expected:
                        candidates.append((candidate, dist * direction))
        if len(candidates) == 0:
            return None, 0
        if len(candidates) != 1:
            print(f"  [SLIDING AMBIGUOUS] {name}: {len(candidates)} matches for expected byte in +/-{window}, skipping")
            return None, 0
        candidate, slide_dist = candidates[0]
        return candidate + adj, slide_dist

    for dist in range(1, window + 1):
        for direction in (+1, -1):
            candidate = exact_file + (dist * direction)
            if 0 <= candidate and candidate + len(expected) <= len(data):
                if data[candidate:candidate + len(expected)] == expected:
                    config_off = candidate + adj
                    return config_off, dist * direction

    return None, 0

def _find_emulate_bitrate_in_anchor_window(data, anchor_file, adj, window=0x2000):
    literal_32000 = b'\x00\x7d\x00\x00'
    start = max(0, anchor_file - window)
    end = min(len(data) - 4, anchor_file + window)
    candidates = []
    pos = data.find(literal_32000, start, end + 1)
    while pos >= 0:
        if pos >= 2 and data[pos - 2] == 0x69:
            candidates.append((pos, True))
        elif pos >= 1 and 0xB8 <= data[pos - 1] <= 0xBF:
            candidates.append((pos, False))
        pos = data.find(literal_32000, pos + 1, end + 1)
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: (abs(x[0] - anchor_file), not x[1]))
    file_off = candidates[0][0]
    reason = "imul 32000" if candidates[0][1] else "mov 32000"
    return file_off + adj, f"anchor-window({reason} @file:0x{file_off:X})"

def _run_heuristic_scan(data, missing_names, adj, text_start, text_end):
    hints = []
    if "ApplySettings_BitrateCalcLow_Channels_Mov248k" in missing_names:
        imul_pat = Signature._parse("69 ?? 00 7D 00 00")
        matches = scan_pattern(data, imul_pat, start=text_start, end=text_end)
        for m in matches:
            candidate_file = m + 2
            reason = f"imul *,32000 @file:0x{m:X}"
            hints.append(("ApplySettings_BitrateCalcLow_Channels_Mov248k", candidate_file, reason))
    if "SelectSampleRate_Cmov48k_Nop3" in missing_names:
        for i in range(text_start, min(text_end, len(data) - 24)):
            if data[i] == 0x83 and 0xB8 <= data[i+1] <= 0xBF and (data[i+1] & 7) != 4:
                if i + 7 <= len(data) and data[i+6] == 0x02:
                    for j in range(7, 20):
                        if i + j + 2 <= len(data) and data[i+j] == 0x0F and 0x40 <= data[i+j+1] <= 0x4F:
                            hints.append(("SelectSampleRate_Cmov48k_Nop3", i + j, f"cmp ...,2 + cmov @file:0x{i:X} [HEURISTIC USED]"))
                            break
            if data[i:i+2] == b'\x41\x83' and i + 8 <= len(data):
                if 0xB8 <= data[i+2] <= 0xBF and (data[i+2] & 7) != 4 and data[i+7] == 0x02:
                    for j in range(8, 24):
                        if i + j + 2 <= len(data) and data[i+j] == 0x0F and 0x40 <= data[i+j+1] <= 0x4F:
                            hints.append(("SelectSampleRate_Cmov48k_Nop3", i + j, f"41 83 cmp ...,2 + cmov @file:0x{i:X} [HEURISTIC USED]"))
                            break
    if "CreateAudioFrame_ChannelAssign_Mov" in missing_names:
        pair_pat = Signature._parse("B8 80 BB 00 00 BD 00 7D 00 00")
        matches = scan_pattern(data, pair_pat, start=text_start, end=text_end, limit=5)
        for m in matches:
            for off in range(20, 60):
                pos = m + off
                if pos + 4 <= len(data) and data[pos:pos+4] == b'\x4C\x0F\x43\xE8':
                    hints.append(("CreateAudioFrame_ChannelAssign_Mov", pos, f"48k/32k pair + cmovae @file:0x{m:X}"))
                    break
    if "AudioEncoderOpusConfig_Ctor_Channels_Imm02" in missing_names:
        bb80_pat = Signature._parse("48 B9 14 00 00 00 80 BB 00 00")
        matches = scan_pattern(data, bb80_pat, start=text_start, end=text_end, limit=5)
        for m in matches:
            for scan in range(12, 40):
                pos = m + scan
                if pos + 5 <= len(data) and data[pos] == 0x48 and data[pos+1] == 0xC7:
                    target = pos + 4
                    if target < len(data):
                        hints.append(("AudioEncoderOpusConfig_Ctor_Channels_Imm02", target,
                                     f"Opus config struct @file:0x{m:X}"))
                    break

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
                if "Encoder" not in name and "Config" not in name:
                    continue
                for opus_pos in opus_positions[:10]:
                    window_start = max(text_start, opus_pos - 0x400)
                    window_end = min(text_end, opus_pos + 0x400)
                    const_pat = Signature._parse("80 BB 00 00")
                    sub_matches = scan_pattern(data, const_pat, start=window_start, end=window_end)
                    for sm in sub_matches[:3]:
                        hints.append((name, sm, f"near Opus string @file:0x{opus_pos:X}"))

    return hints[:15]

def _cross_validate(results, adj, data, tiers_used=None, bin_fmt='pe'):
    warnings = []
    tiers = tiers_used or {}

    if bin_fmt == 'pe':
        for derived_name, paths in DERIVATIONS.items():
            if derived_name not in results:
                continue
            derived_tier = tiers.get(derived_name, '')
            if derived_tier.startswith('symbol'):
                continue
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

    if "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k" in results and "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k" in results:
        for name in ["AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k", "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k"]:
            f = results[name] - adj
            if 0 <= f and f + 4 <= len(data):
                val = data[f:f+4]
                if val != b'\x00\x7D\x00\x00' and val != b'\x00\xDC\x05\x00':
                    warnings.append(f"{name}: unexpected config bytes {val.hex(' ')} "
                                    f"(expected 00 7D 00 00 or 00 DC 05 00)")

    return warnings

BITRATE_OFFSET_NAMES = [
    "ApplySettings_BitrateCalcLow_Channels_Mov248k",
    "ApplySettings_BitrateCalcMid_Channels_Mov248k",
    "ApplySettings_BitrateCalcHigh_Channels_Mov248k",
    "RecreateEncoder_BitrateCalcLow_Channels_Mov248k",
    "RecreateEncoder_BitrateCalcMid_Channels_Mov248k",
    "RecreateEncoder_BitrateCalcHigh_Channels_Mov248k",
    "SetBitrateClamp_Max248k_Cmp",
    "SetBitrateClamp_Max248k_Mov",
    "AudioBitrateAdaptorCalc32k_Channels_Mov248k",
    "AudioBitrateAdaptorCalc48k_Channels_Mov248k",
    "AudioBitrateAdaptorCalc60k_Channels_Mov248k",
    "SetBitrate_Imm64_Imm248k",
    "GetMultipliedBitrate_Entry_IdentityRet",
    "SetTargetBitrate_ClampMax248k_Cmp",
    "SetTargetBitrate_ClampMax248k_Mov",
    "ApplySettings_MaxAvgBitrateClamp248k_Cmp",
    "ApplySettings_MaxAvgBitrateClamp248k_Mov",
    "EncoderOpusImpl_RelayClamp248k_Cmp",
    "EncoderOpusImpl_RelayClamp248k_Mov",
    "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k",
    "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k",
]

def run_bitrate_audit_pe(data, results, adj, text_start, text_end):
    literal_32000 = struct.pack("<I", 32000)
    literal_512000 = struct.pack("<I", 512000)
    bitrate_rvas = set()
    for name in BITRATE_OFFSET_NAMES:
        if name in results and results[name]:
            bitrate_rvas.add(results[name])
    covered_32k = []
    uncovered_32k = []
    covered_512k = []
    uncovered_512k = []
    for start in range(text_start, min(text_end, len(data) - 4)):
        chunk = data[start : start + 4]
        if chunk == literal_32000:
            rva = start + adj
            if any(abs(rva - br) <= 10 for br in bitrate_rvas):
                covered_32k.append((start, rva))
            else:
                uncovered_32k.append((start, rva))
        elif chunk == literal_512000:
            rva = start + adj
            if any(abs(rva - br) <= 10 for br in bitrate_rvas):
                covered_512k.append((start, rva))
            else:
                uncovered_512k.append((start, rva))
    print("\n" + "=" * 65)
    print("  BITRATE AUDIT (PE .text)")
    print("=" * 65)
    print(f"  Known bitrate patch sites: {len(bitrate_rvas)}")
    print(f"  32000 (0x7D00):   {len(covered_32k)} covered, {len(uncovered_32k)} uncovered")
    if uncovered_32k:
        for f, rva in uncovered_32k[:10]:
            print(f"    uncovered  file 0x{f:X}  RVA 0x{rva:X}")
        if len(uncovered_32k) > 10:
            print(f"    ... and {len(uncovered_32k) - 10} more")
    print(f"  512000 (0x7D000): {len(covered_512k)} covered, {len(uncovered_512k)} uncovered")
    if uncovered_512k:
        for f, rva in uncovered_512k[:10]:
            print(f"    uncovered  file 0x{f:X}  RVA 0x{rva:X}")
        if len(uncovered_512k) > 10:
            print(f"    ... and {len(uncovered_512k) - 10} more")
        rva0 = uncovered_512k[0][1]
        print(f"  [INFO] 512000 literals in .text not near known bitrate sites (example RVA 0x{rva0:X}).")
        print("         Treat as noise unless IDA + Linux xref confirm another encoder init path.")
    if not uncovered_32k and not uncovered_512k and bitrate_rvas:
        print("  All 32000/512000 constants in .text are at or near known patch sites.")
    print()
    return uncovered_512k[0][1] if uncovered_512k else None


EXPECTED_ORIGINALS = {
    "CommitAudioCodec_ChannelCount_Imm02":    ("01", 1),
    "CommitAudioCodec_SuccessBranch_Jmp":    ("75", 1),
    "SelectSampleRate_Cmov48k_Nop3":             ("0F 42 C1", 3),
    "ApplySettings_BitrateCalcLow_Channels_Mov248k":   (None, 6),
    "ApplySettings_BitrateCalcMid_Channels_Mov248k":   (None, 6),
    "ApplySettings_BitrateCalcHigh_Channels_Mov248k":  (None, 6),
    "RecreateEncoder_BitrateCalcLow_Channels_Mov248k":  (None, 6),
    "RecreateEncoder_BitrateCalcMid_Channels_Mov248k":  (None, 6),
    "RecreateEncoder_BitrateCalcHigh_Channels_Mov248k": (None, 6),
    "SetBitrateClamp_Max248k_Cmp": ("81 FB", 2),
    "SetBitrateClamp_Max248k_Mov": ("B8", 1),
    "AudioBitrateAdaptorCalc32k_Channels_Mov248k": (None, 7),
    "AudioBitrateAdaptorCalc48k_Channels_Mov248k": (None, 7),
    "AudioBitrateAdaptorCalc60k_Channels_Mov248k": (None, 7),
    "GetMultipliedBitrate_Entry_IdentityRet": ("89 C8", 2),
    "SetTargetBitrate_ClampMax248k_Cmp": ("81 FA", 2),
    "SetTargetBitrate_ClampMax248k_Mov": ("BA", 1),
    "ApplySettings_MaxAvgBitrateClamp248k_Cmp": ("81 FB", 2),
    "ApplySettings_MaxAvgBitrateClamp248k_Mov": ("B8", 1),
    "EncoderOpusImpl_RelayClamp248k_Cmp": ("3D", 1),
    "EncoderOpusImpl_RelayClamp248k_Mov": ("BF", 1),
    "SetBitrate_Imm64_Imm248k":  (None, 5),
    "SetBitrate_OrMask_Nop3":     ("48 09 C1", 3),
    "SetTargetBitrate_Mulss_Nop6": ("F3 0F 59 44 81 EC", 6),
    "GetMultipliedBitrate_Mulss_Nop7": ("F3 41 0F 59 44 88 EC", 7),
    "WebRtcSplHighPass_Dispatch_MovRet":           (None, 11),
    "CreateAudioFrame_ChannelAssign_Mov":   (None, 4),
    "AudioEncoderOpusConfig_Ctor_Channels_Imm02": ("01", 1),
    "AudioEncoderOpusConfig_IsOK_MovTrueRet": ("8B 11 31 C0", 4),
    "CapturedAudioProcessor_MonoDownmix_NopJmp":            ("84 C0", 2),
    "CodecMismatchThrow_Entry_Ret":               ("41", 1),
    "ChannelDownmix_Entry_Ret":              ("41", 1),
    "hp_cutoff_Callback_InjectShellcode":     (None, 0x100),
    "dc_reject_Callback_InjectShellcode":                 (None, 0x1B6),
    "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k":       ("00 7D 00 00", 4),
    "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k":       ("00 7D 00 00", 4),
    "AudioEncoderOpusConfig_Ctor_FrameMs_Imm10":       ("14", 1),
    "AudioEncoderOpusConfig_Ctor_Application_ImmAudio":  ("01", 1),
    "CELT_Force":        ("18 FC FF FF", 4),
    "CELT_DefaultMode":  ("E9 03 00 00", 4),
    "NetEqDelayManager_MsPerLoss_Imm0": ("48 B8 14 00 00 00 C8 00 00 00", 10),
    "PacerBlockAudio_Flag_XorFalse": ("0F 94 C3", 3),
}

EXPECTED_ORIGINALS_CLANG = {
    "ChannelDownmix_Entry_Ret":              ("55", 1),
    "AudioEncoderOpusConfig_IsOK_MovTrueRet": ("55 48 89 E5", 4),
    "SelectSampleRate_Cmov48k_Nop3":             (None, 4),
    "ApplySettings_BitrateCalcLow_Channels_Mov248k":   ("69 E8", 2),
    "GetMultipliedBitrate_Mulss_Nop7": ("F3 0F 59 44 81 EC", 6),
    "hp_cutoff_Callback_InjectShellcode":     (None, 0x100),
    "dc_reject_Callback_InjectShellcode":                 (None, 0x1B6),
}

EXPECTED_ORIGINALS_LINUX_ONLY = {
    "CommitAudioCodec_ChannelCount_Imm02":    ("00", 1),
    "CommitAudioCodec_SuccessBranch_Jmp":    ("74", 1),
    "CreateAudioFrame_ChannelAssign_Mov":   ("4C 0F 43", 4),
    "SelectSampleRate_Cmov48k_Nop3":             ("48 0F 43 D0", 4),
    "OpusEncoderConfig_SetMultiChannelStereo": ("01", 1),
}

EXPECTED_ORIGINALS_MACHO_ONLY = {
    "CodecMismatchThrow_Entry_Ret":               ("55", 1),
    "CreateAudioFrame_ChannelAssign_Mov":   ("4C 0F 43 E0", 4),
    "CommitAudioCodec_SuccessBranch_Jmp":    (None, 1),
    "SelectSampleRate_Cmov48k_Nop3":             (None, 4),
}


def _build_expected_map(fmt, arch=None):
    m = dict(EXPECTED_ORIGINALS)
    if fmt in ('elf', 'macho'):
        m.update(EXPECTED_ORIGINALS_CLANG)
    if fmt == 'elf':
        m.update(EXPECTED_ORIGINALS_LINUX_ONLY)
    if fmt == 'macho':
        m.update(EXPECTED_ORIGINALS_MACHO_ONLY)
    return m

PATCH_INFO = {
    "CommitAudioCodec_ChannelCount_Imm02":    ("02", "Channel count 1->2"),
    "CommitAudioCodec_SuccessBranch_Jmp":    ("EB", "PE: EB on short jcc. ELF: 6x NOP on jz/jnz rel32 (see discord_voice_patcher_linux.sh)"),
    "SelectSampleRate_Cmov48k_Nop3":             ("90 90 90", "cmovb->NOPs (force 48kHz)"),
    "ApplySettings_BitrateCalcLow_Channels_Mov248k":   (FLAT_EBP248K_PATCH, "imul ebp,eax tier -> mov ebp 248k flat"),
    "ApplySettings_BitrateCalcMid_Channels_Mov248k":   (FLAT_EBP248K_PATCH, "imul ebp,eax tier -> mov ebp 248k flat"),
    "ApplySettings_BitrateCalcHigh_Channels_Mov248k":  (FLAT_EBP248K_PATCH, "imul ebp,eax tier -> mov ebp 248k flat"),
    "RecreateEncoder_BitrateCalcLow_Channels_Mov248k":  (FLAT_EBP248K_PATCH, "imul ebp,eax tier -> mov ebp 248k flat"),
    "RecreateEncoder_BitrateCalcMid_Channels_Mov248k":  (FLAT_EBP248K_PATCH, "imul ebp,eax tier -> mov ebp 248k flat"),
    "RecreateEncoder_BitrateCalcHigh_Channels_Mov248k": (FLAT_EBP248K_PATCH, "imul ebp,eax tier -> mov ebp 248k flat"),
    "SetBitrateClamp_Max248k_Cmp": ("81 FB C0 C8 03 00", "max clamp cmp 510k->248k"),
    "SetBitrateClamp_Max248k_Mov": ("B8 C0 C8 03 00", "max clamp mov 510k->248k"),
    "AudioBitrateAdaptorCalc32k_Channels_Mov248k": (FLAT_R8D248K_PATCH, "imul r8d,eax tier -> mov r8d 248k flat"),
    "AudioBitrateAdaptorCalc48k_Channels_Mov248k": (FLAT_R8D248K_PATCH, "imul r8d,eax tier -> mov r8d 248k flat"),
    "AudioBitrateAdaptorCalc60k_Channels_Mov248k": (FLAT_R8D248K_PATCH, "imul r8d,eax tier -> mov r8d 248k flat"),
    "GetMultipliedBitrate_Entry_IdentityRet": ("8B C1 C3", "GetMultipliedBitrate -> identity ret"),
    "SetTargetBitrate_ClampMax248k_Cmp": ("81 FA C0 C8 03 00", "SetTargetBitrate max cmp 510k->248k"),
    "SetTargetBitrate_ClampMax248k_Mov": ("BA C0 C8 03 00", "SetTargetBitrate max mov 510k->248k"),
    "ApplySettings_MaxAvgBitrateClamp248k_Cmp": ("81 FB C0 C8 03 00", "ApplySettings maxavg cmp 510k->248k"),
    "ApplySettings_MaxAvgBitrateClamp248k_Mov": ("B8 C0 C8 03 00", "ApplySettings maxavg mov 510k->248k"),
    "EncoderOpusImpl_RelayClamp248k_Cmp": ("3D C0 C8 03 00", "relay cmp 510k->248k"),
    "EncoderOpusImpl_RelayClamp248k_Mov": ("BF C0 C8 03 00", "relay mov 510k->248k"),
    "SetBitrate_Imm64_Imm248k":  (BITRATE_PATCH_5, "248000 in imm64"),
    "SetBitrate_OrMask_Nop3":     ("90 90 90", "or rcx,rax->NOPs"),
    "SetTargetBitrate_Mulss_Nop6": ("90 90 90 90 90 90", "mulss->NOP"),
    "GetMultipliedBitrate_Mulss_Nop7": ("90 90 90 90 90 90 90", "mulss->NOP"),
    "WebRtcSplHighPass_Dispatch_MovRet":           ("<dynamic: mov rax, IMAGE_BASE+HPC; ret>", "Redirect to HPC"),
    "CreateAudioFrame_ChannelAssign_Mov":   ("49 89 C4 90", "Clang ELF: cmovnb r12,rax -> mov r12,rax; nop (PE/MSVC uses 49 89 C5 90 / r13)"),
    "AudioEncoderOpusConfig_Ctor_Channels_Imm02": ("02", "Channel count 1->2"),
    "OpusEncoderConfig_SetMultiChannelStereo": ("02", "MultiChannel Opus config channels 1->2 (Linux)"),
    "AudioEncoderOpusConfig_IsOK_MovTrueRet": ("48 C7 C0 01 00 00 00 C3", "return 1"),
    "CapturedAudioProcessor_MonoDownmix_NopJmp":            ("90 90 90 90 90 90 90 90 90 90 90 90 E9", "NOP sled + jmp"),
    "CodecMismatchThrow_Entry_Ret":               ("C3", "ret (disable throws)"),
    "ChannelDownmix_Entry_Ret":              ("C3", "ret (disable downmix)"),
    "hp_cutoff_Callback_InjectShellcode":     ("<injected: hp_cutoff>", "Custom HP cutoff + gain"),
    "dc_reject_Callback_InjectShellcode":                 ("<injected: dc_reject>", "Custom DC reject + gain"),
    "AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k":       (BITRATE_PATCH_4, "Config qword: 32000->248000"),
    "AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k":       (BITRATE_PATCH_4, "Config qword: 32000->248000"),
    "AudioEncoderOpusConfig_Ctor_FrameMs_Imm10":       ("0A", "Opus config ctor frame_size_ms 20->10"),
    "AudioEncoderOpusConfig_Ctor_Application_ImmAudio":  ("01", "Opus config ctor application kAudio"),
    "CELT_Force":        ("EA 03 00 00", "opus_encoder_init user_forced_mode -1000->1002 (CELT_ONLY)"),
    "CELT_DefaultMode":  ("EA 03 00 00", "opus_encoder_init default st->mode 1001->1002 (CELT_ONLY)"),
    "NetEqDelayManager_MsPerLoss_Imm0": ("48 B8 00 00 00 00 00 00 00 00", "imm64 -> 0"),
    "PacerBlockAudio_Flag_XorFalse": ("30 DB 90", "setz bl -> xor bl,bl; nop"),
}


def validate_offsets(data, results, adj, bin_fmt='pe'):
    print("\n" + "=" * 65)
    print("  PHASE 3: Byte Verification")
    print("=" * 65)

    verified = 0
    warnings = 0

    expected_map = _build_expected_map(bin_fmt)

    for name, config_off in sorted(results.items(), key=lambda x: x[1]):
        file_off = config_off - adj

        if file_off < 0 or file_off >= len(data):
            print(f"  [FAIL] {name:<{OFFSET_LOG_NAME_WIDTH}s} offset 0x{config_off:X} out of bounds")
            warnings += 1
            continue

        if name in expected_map:
            expected_hex, length = expected_map[name]
            actual = data[file_off:file_off+length]

            if name == "CommitAudioCodec_SuccessBranch_Jmp" and bin_fmt == "elf":
                peek = data[file_off : min(file_off + 6, len(data))]
                if len(peek) >= 1 and peek[0] in (0x74, 0x75):
                    print(f"  [PASS] {name:<{OFFSET_LOG_NAME_WIDTH}s} original bytes: {peek[:1].hex(' ')} (short jcc)")
                    verified += 1
                    continue
                if len(peek) >= 2 and peek[0] == 0x0F and peek[1] in (0x84, 0x85):
                    print(f"  [PASS] {name:<{OFFSET_LOG_NAME_WIDTH}s} jcc near rel32: {peek.hex(' ')}")
                    verified += 1
                    continue
                if len(peek) >= 6 and peek[:6] == b"\x90" * 6:
                    print(f"  [WARN] {name:<{OFFSET_LOG_NAME_WIDTH}s} ALREADY PATCHED (6x NOP)")
                    warnings += 1
                    continue

            if expected_hex:
                expected = bytes.fromhex(expected_hex.replace(' ', ''))
                if actual[:len(expected)] == expected:
                    print(f"  [PASS] {name:<{OFFSET_LOG_NAME_WIDTH}s} original bytes: {actual[:len(expected)].hex(' ')}")
                    verified += 1
                else:
                    patch_hex = PATCH_INFO.get(name, (None,))[0]
                    if name == "SelectSampleRate_Cmov48k_Nop3" and bin_fmt == "elf":
                        patch_hex = "90 90 90 90"
                    if patch_hex and not patch_hex.startswith('<'):
                        try:
                            patched = bytes.fromhex(patch_hex.replace(' ', ''))
                            if actual[:len(patched)] == patched:
                                print(f"  [WARN] {name:<{OFFSET_LOG_NAME_WIDTH}s} ALREADY PATCHED: {actual[:len(patched)].hex(' ')}")
                                warnings += 1
                                continue
                        except ValueError:
                            pass
                    print(f"  [WARN] {name:<{OFFSET_LOG_NAME_WIDTH}s} unexpected: {actual[:len(expected)].hex(' ')} (expected {expected_hex})")
                    warnings += 1
            else:
                print(f"  [INFO] {name:<{OFFSET_LOG_NAME_WIDTH}s} bytes: {actual[:min(8,length)].hex(' ')} (no fixed expected)")
                verified += 1

    return verified, warnings


def check_injection_sites(data, results, adj):
    print("\n" + "=" * 65)
    print("  PHASE 4: Injection Site Capacity")
    print("=" * 65)

    for name, inject_size, desc in [("hp_cutoff_Callback_InjectShellcode", 0x100, "hp_cutoff"), ("dc_reject_Callback_InjectShellcode", 0x1B6, "dc_reject")]:
        if name not in results:
            print(f"  [SKIP] {name}: not found")
            continue

        file_off = results[name] - adj
        func_end = None

        for i in range(file_off, min(file_off + 0x400, len(data) - 3)):
            if data[i:i+4] == b'\xcc\xcc\xcc\xcc':
                func_end = i
                break
            if data[i] == 0xC3 and i > file_off + 8:
                nop_run = 0
                for j in range(i+1, min(i+17, len(data))):
                    if data[j] in (0x90, 0x66, 0x0F, 0x1F, 0x2E, 0x84, 0x00, 0x40):
                        nop_run += 1
                    else:
                        break
                if nop_run >= 4:
                    func_end = i + 1
                    break

        if func_end is None:
            print(f"  [INFO] {name}: no padding found; using symbol size for capacity")
            continue

        available = func_end - file_off
        margin = available - inject_size
        status = "OK" if margin >= 0 else "OVER"
        print(f"  [{status:4s}] {name:30s}  available={available} (0x{available:X})  "
              f"needed={inject_size} (0x{inject_size:X})  margin={margin:+d} bytes")



def _md5_file_hex(file_path, lower=False):
    with open(file_path, "rb") as f:
        h = hashlib.md5(f.read()).hexdigest()
    return h.lower() if lower else h



def _format_rva(rva):
    return f"0x{int(rva):08X}"


def _format_offset_assignment(name, rva, name_width=None, indent="", sep=" = "):
    w = name_width if name_width is not None else PATCHER_OFFSET_NAME_WIDTH
    pad = " " * max(0, w - len(name))
    return f"{indent}{name}{pad}{sep}{_format_rva(rva)}"


def _format_offset_table_lines(names, results, name_width=None, indent="    ", include_missing=False):
    w = name_width if name_width is not None else max((len(n) for n in names), default=PATCHER_OFFSET_NAME_WIDTH)
    lines = []
    for name in names:
        if name in results and results[name]:
            lines.append(_format_offset_assignment(name, results[name], w, indent))
        elif include_missing:
            pad = " " * max(0, w - len(name))
            lines.append(f"{indent}{name}{pad} = 0x00000000")
    return lines


def print_pe_offset_summary(results, tiers_used=None, adj=0):
    if not results:
        return
    name_w = PATCHER_OFFSET_NAME_WIDTH
    rva_w = 10
    file_w = 10
    print(f"  {'Name':<{name_w}s}  {'RVA':>{rva_w}s}  {'File':>{file_w}s}  Tier")
    print(f"  {'-' * name_w}  {'-' * rva_w}  {'-' * file_w}  {'-' * 18}")
    for group_name, patches in PATCHER_DEBUG_GROUPS.items():
        print(f"  [{group_name}]")
        for key, _desc in patches:
            if key in results:
                rva = results[key]
                file_off = rva - adj if adj else rva
                tier = (tiers_used or {}).get(key, "")
                tier_short = tier.split("(")[0].split("-")[0] if tier else "?"
                print(
                    f"  {key:<{name_w}s}  {_format_rva(rva):>{rva_w}s}  "
                    f"{_format_rva(file_off):>{file_w}s}  {tier_short}"
                )
            else:
                print(f"  {key:<{name_w}s}  {'MISSING':>{rva_w}s}")
        print("")


def format_powershell_config(results, bin_info=None, file_path=None, file_size=None):
    lines = []
    fmt = (bin_info or {}).get('format', 'raw')
    adj = (bin_info or {}).get('file_offset_adjustment', 0)

    if bin_info and file_path and file_size:
        md5 = _md5_file_hex(file_path)
        build_str = ''
        if fmt == 'pe' and 'build_time' in bin_info:
            build_str = bin_info['build_time'].strftime('%b %d %Y')
        else:
            build_str = f'{fmt.upper()} binary'
        lines.append(f"    # Auto-generated by discord_voice_node_offset_finder_v5.py v{VERSION}")
        lines.append(f"    # Build: {build_str} | Size: {file_size} | MD5: {md5}")
        if fmt != 'pe':
            lines.append(f"    # Format: {fmt.upper()} | Arch: {bin_info.get('arch', '?')}")
            lines.append(f"    # Note: on macOS and Linux use the 'file_offset' values below for direct binary patching")

    lines.append("    Offsets = @{")
    ordered = _all_offset_names()
    lines.extend(_format_offset_table_lines(ordered, results, indent="        ", include_missing=True))
    lines.append("    }")
    return "\n".join(lines)


def _validate_discovered_offsets(results, data, adj, margin=512):
    invalid = []
    n = len(data)
    for name, rva in list(results.items()):
        if rva == 0:
            invalid.append((name, "offset is zero (invalid)"))
            continue
        file_off = rva - adj
        if file_off < 0:
            invalid.append((name, "file offset is negative"))
            continue
        if file_off >= n - margin:
            invalid.append((name, f"0x{rva:X} (file 0x{file_off:08X}) out of file bounds"))
            continue
    invalid_names = {x for x, _ in invalid}
    rva_to_names = {}
    for name, rva in results.items():
        if name in invalid_names:
            continue
        rva_to_names.setdefault(rva, []).append(name)
    for rva, names in rva_to_names.items():
        if len(names) > 1:
            for name in names[1:]:
                invalid.append((name, f"duplicate RVA 0x{rva:X} (same as {names[0]})"))
    return invalid


def _validate_pe_offsets_for_patcher(results, bin_info, file_size):
    if not bin_info or file_size is None:
        return False, "missing bin_info or file_size"
    adj = bin_info.get("file_offset_adjustment", 0xC00)
    required = set(PATCHER_OFFSET_NAMES)
    if required - set(results):
        return False, "missing required offsets"
    seen_rva = set()
    for name in PATCHER_OFFSET_NAMES:
        rva = results[name]
        if rva == 0:
            return False, f"{name} is zero"
        if rva in seen_rva:
            return False, f"duplicate RVA 0x{rva:X}"
        seen_rva.add(rva)
        file_off = rva - adj
        if file_off < 0 or file_off >= file_size - 512:
            return False, f"{name} (0x{rva:X}) out of file bounds"
    return True, None


def _read_discord_app_build_sidecar(parent_dir):
    if not parent_dir:
        return None
    pdir = Path(parent_dir)
    for fname in ("discord_app_build.txt", "discord_app_build", "APP_BUILD.txt"):
        p = pdir / fname
        if not p.is_file():
            continue
        try:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if s and not s.startswith("#"):
                    return s
        except OSError:
            continue
    return None


def _app_dir_semver_from_name(dir_name):
    m = re.match(r"(?i)^app-([\d.]+)$", dir_name)
    if not m:
        return None, ()
    s = m.group(1).strip()
    parts = []
    for p in s.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            return None, ()
    return s, tuple(parts)


def _discord_app_version_matching_install(file_path, data):
    path = Path(file_path) if file_path else None
    try:
        if data is None and path and path.is_file():
            data = path.read_bytes()
        if not data:
            return None
        sz = len(data)
        digest = hashlib.md5(data).hexdigest()
    except OSError:
        return None

    roots = []
    if sys.platform == "win32":
        la = os.environ.get("LOCALAPPDATA", "")
        if la:
            roots.extend(
                Path(la) / c
                for c in (
                    "Discord",
                    "DiscordCanary",
                    "DiscordPTB",
                    "DiscordDevelopment",
                )
            )
    elif sys.platform == "darwin":
        sup = Path.home() / "Library" / "Application Support"
        for c in ("discord", "discordcanary", "discordptb", "discorddevelopment"):
            roots.append(sup / c)

    best = None
    for root in roots:
        if not root.is_dir():
            continue
        for app_dir in root.glob("app-*"):
            if not app_dir.is_dir():
                continue
            ver_str, ver_tuple = _app_dir_semver_from_name(app_dir.name)
            if not ver_str:
                continue
            hit = False
            for node in app_dir.glob("modules/discord_voice*/discord_voice/discord_voice.node"):
                try:
                    if node.stat().st_size != sz:
                        continue
                    if hashlib.md5(node.read_bytes()).hexdigest() != digest:
                        continue
                except OSError:
                    continue
                hit = True
                break
            if not hit:
                continue
            label = root.name
            if best is None or ver_tuple > best[0]:
                best = (ver_tuple, ver_str, label)

    if best:
        return best[1], f"matching-install:{best[2]}"
    return None


def _read_manifest_discord_app_version(parent_dir):
    if not parent_dir:
        return None
    mf = Path(parent_dir) / "manifest.json"
    if not mf.is_file():
        return None
    try:
        obj = json.loads(mf.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    for key in ("discordAppVersion", "discord_app_version", "appVersion"):
        v = obj.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() != "null":
            return s
    return None


def _pe_rsrc_blob(data, bin_info):
    if not data or not bin_info or bin_info.get("format") != "pe":
        return None
    for sec in bin_info.get("sections") or []:
        if sec.get("name") == ".rsrc":
            ro = sec.get("raw_offset") or 0
            rs = sec.get("raw_size") or 0
            if ro > 0 and rs > 0 and ro + rs <= len(data):
                return data[ro : ro + rs]
    return None


def _utf16_stringfileinfo_value(blob, key_ascii):
    if not blob or not key_ascii:
        return None
    key = (key_ascii + "\0").encode("utf-16le")
    idx = 0
    while idx < len(blob):
        j = blob.find(key, idx)
        if j < 0:
            return None
        pos = j + len(key)
        while pos < len(blob) and blob[pos] == 0:
            pos += 1
        chars = bytearray()
        while pos + 1 < len(blob):
            if blob[pos] == 0 and blob[pos + 1] == 0:
                break
            chars.append(blob[pos])
            chars.append(blob[pos + 1])
            pos += 2
        try:
            s = chars.decode("utf-16le").strip()
        except (UnicodeDecodeError, UnicodeError):
            idx = j + 1
            continue
        if s and re.fullmatch(r"[\d.]+", s):
            return s
        idx = j + 1
    return None


def resolve_discord_app_version(file_path, data=None, bin_info=None, cli_version=None):
    path = Path(file_path) if file_path else None
    parent = path.parent if path else None

    if cli_version:
        v = str(cli_version).strip()
        if v:
            return v, "cli"

    env_v = (os.environ.get("DISCORD_APP_VERSION") or os.environ.get("DISCORD_APP_BUILD") or "").strip()
    if env_v:
        return env_v, "environment"

    side = _read_discord_app_build_sidecar(parent)
    if side:
        return side, "discord_app_build.txt"

    man = _read_manifest_discord_app_version(parent)
    if man:
        return man, "manifest.json"

    if path:
        for part in path.resolve().parts:
            m = re.match(r"(?i)^app-([\d.]+)$", part)
            if m:
                return m.group(1).strip(), "path"
        s = os.path.normpath(str(path))
        m = re.search(r"(?i)app-\s*([\d.]+)", s)
        if m:
            return m.group(1).strip(), "path"

    install_ver = _discord_app_version_matching_install(path, data)
    if install_ver:
        return install_ver[0], install_ver[1]

    if data is not None and bin_info and bin_info.get("format") == "pe":
        blob = _pe_rsrc_blob(data, bin_info)
        if blob:
            fv = _utf16_stringfileinfo_value(blob, "FileVersion")
            if fv:
                return fv, "pe:FileVersion"
            pv = _utf16_stringfileinfo_value(blob, "ProductVersion")
            if pv:
                return pv, "pe:ProductVersion"

    return "unspecified", "none"


def format_windows_patcher_block(results, bin_info, file_path, file_size, discord_app_version=None):
    if not bin_info or not file_path or file_size is None:
        return None
    if bin_info.get('format') != 'pe':
        return None
    ok, _err = _validate_pe_offsets_for_patcher(results, bin_info, file_size)
    if not ok:
        return None
    with open(file_path, 'rb') as f:
        raw = f.read()
    md5 = hashlib.md5(raw).hexdigest().lower()
    if discord_app_version is None:
        app_ver, _src = resolve_discord_app_version(
            Path(file_path), data=raw, bin_info=bin_info, cli_version=None)
    else:
        app_ver = str(discord_app_version).strip() or "unspecified"
    lines = [
        "# region Offsets (PASTE HERE)",
        "",
        "$Script:OffsetsMeta = @{",
    ]
    meta_rows = (
        ("FinderVersion", '"discord_voice_node_offset_finder.py v%s"' % VERSION),
        ("DiscordAppVersion", '"%s"' % app_ver),
        ("Size", str(file_size)),
        ("MD5", '"%s"' % md5),
    )
    meta_w = max(len(k) for k, _ in meta_rows)
    for key, val in meta_rows:
        lines.append("    %s%s = %s" % (key, " " * (meta_w - len(key)), val))
    lines.append("}")
    lines.append("")
    lines.append("$Script:Offsets = @{")
    lines.extend(_format_offset_table_lines(PATCHER_OFFSET_NAMES, results, indent="    "))
    lines.append("}")
    lines.append("")
    lines.append("# endregion Offsets")
    return "\n".join(lines) + "\n"


PATCHER_DEBUG_GROUPS = {
    "STEREO": [
        ("CommitAudioCodec_ChannelCount_Imm02", "LocalUser::CommitAudioCodec / ApplySettings (channel 1->2)"),
        ("CommitAudioCodec_SuccessBranch_Jmp", "LocalUser::CommitAudioCodec / ApplySettings (force success jmp)"),
        ("CreateAudioFrame_ChannelAssign_Mov", "EngineAudioTransport::CreateAudioFrameToProcess"),
        ("AudioEncoderOpusConfig_Ctor_Channels_Imm02", "webrtc::AudioEncoderOpusConfig ctor (ch 1->2)"),
        ("CapturedAudioProcessor_MonoDownmix_NopJmp", "CapturedAudioProcessor::Process (bypass mono path)"),
    ],
    "BITRATE": [
        ("ApplySettings_BitrateCalcLow_Channels_Mov248k", "ApplySettings tier-low -> mov ebp 248k flat"),
        ("ApplySettings_BitrateCalcMid_Channels_Mov248k", "ApplySettings tier-mid -> mov ebp 248k flat"),
        ("ApplySettings_BitrateCalcHigh_Channels_Mov248k", "ApplySettings tier-high -> mov ebp 248k flat"),
        ("RecreateEncoder_BitrateCalcLow_Channels_Mov248k", "RecreateEncoder tier-low -> mov ebp 248k flat"),
        ("RecreateEncoder_BitrateCalcMid_Channels_Mov248k", "RecreateEncoder tier-mid -> mov ebp 248k flat"),
        ("RecreateEncoder_BitrateCalcHigh_Channels_Mov248k", "RecreateEncoder tier-high -> mov ebp 248k flat"),
        ("SetBitrateClamp_Max248k_Cmp", "RecreateEncoder max clamp cmp 510k->248k"),
        ("SetBitrateClamp_Max248k_Mov", "RecreateEncoder max clamp mov 510k->248k"),
        ("AudioBitrateAdaptorCalc32k_Channels_Mov248k", "AudioBitrateAdaptor tier32k -> mov r8d 248k flat"),
        ("AudioBitrateAdaptorCalc48k_Channels_Mov248k", "AudioBitrateAdaptor tier48k -> mov r8d 248k flat"),
        ("AudioBitrateAdaptorCalc60k_Channels_Mov248k", "AudioBitrateAdaptor tier60k -> mov r8d 248k flat"),
        ("SetBitrate_Imm64_Imm248k", "SetBitrate imm64 -> 248k"),
        ("SetBitrate_OrMask_Nop3", "SetBitrate or-mask NOP"),
        ("SetTargetBitrate_Mulss_Nop6", "SetTargetBitrate mulss NOP"),
        ("GetMultipliedBitrate_Mulss_Nop7", "GetMultipliedBitrate mulss NOP"),
        ("GetMultipliedBitrate_Entry_IdentityRet", "GetMultipliedBitrate identity ret"),
        ("SetTargetBitrate_ClampMax248k_Cmp", "SetTargetBitrate max clamp cmp 510k->248k"),
        ("SetTargetBitrate_ClampMax248k_Mov", "SetTargetBitrate max clamp mov 510k->248k"),
        ("ApplySettings_MaxAvgBitrateClamp248k_Cmp", "ApplySettings maxavg clamp cmp 510k->248k"),
        ("ApplySettings_MaxAvgBitrateClamp248k_Mov", "ApplySettings maxavg clamp mov 510k->248k"),
        ("EncoderOpusImpl_RelayClamp248k_Cmp", "EncoderOpusImpl relay clamp cmp 510k->248k"),
        ("EncoderOpusImpl_RelayClamp248k_Mov", "EncoderOpusImpl relay clamp mov 510k->248k"),
    ],
    "SAMPLERATE": [
        ("SelectSampleRate_Cmov48k_Nop3", "SelectSampleRate_Cmov48k_Nop3 (NOP cmovb)"),
    ],
    "FILTER": [
        ("WebRtcSplHighPass_Dispatch_MovRet", "WebRtcSplHighPass_Dispatch_MovRet (RET stub)"),
        ("hp_cutoff_Callback_InjectShellcode", "hp_cutoff_Callback_InjectShellcode (inject hp_cutoff)"),
        ("dc_reject_Callback_InjectShellcode", "dc_reject_Callback_InjectShellcode (inject dc_reject)"),
        ("ChannelDownmix_Entry_Ret", "downmix_and_resample early RET"),
        ("AudioEncoderOpusConfig_IsOK_MovTrueRet", "webrtc::AudioEncoderOpusConfig::IsOK (RET true)"),
        ("CodecMismatchThrow_Entry_Ret", "CodecMismatchThrow_Entry_Ret (RET)"),
    ],
    "ENCODER": [
        ("AudioEncoderOpusConfig_Ctor_Bitrate_Imm248k", "OpusEncoderConfig ctor literal (32000->248000)"),
        ("AudioEncoderMultiChannelOpusConfig_Ctor_Bitrate_Imm248k", "OpusEncoderConfig ctor literal (32000->248000)"),
    ],
    "OPUS": [
        ("AudioEncoderOpusConfig_Ctor_FrameMs_Imm10", "Opus config ctor frame_size_ms 20->10"),
        ("AudioEncoderOpusConfig_Ctor_Application_ImmAudio", "Opus config ctor application kAudio (1)"),
    ],
    "CELT": [
        ("CELT_Force", "opus_encoder_init user_forced_mode -1000->1002 (CELT_ONLY)"),
        ("CELT_DefaultMode", "opus_encoder_init default st->mode 1001->1002 (CELT_ONLY)"),
    ],
    "NETEQ": [
        ("NetEqDelayManager_MsPerLoss_Imm0", "NetEq ms_per_loss_percent -> 0 (optional; off by default)"),
    ],
    "PACING": [
        ("PacerBlockAudio_Flag_XorFalse", "Pacer BlockAudio -> false"),
    ],
    "DISCORD_API_LOCK": [
        ("SetAutomaticGainControlConfig_Entry_Ret", "Discord::SetAutomaticGainControlConfig (AGC off)"),
        ("SetAutomaticGainControl_Entry_Ret", "Discord::SetAutomaticGainControl(bool) (AGC off)"),
        ("SetNoiseSuppression_Entry_Ret", "Discord::SetNoiseSuppression(bool) (NS off)"),
        ("SetEchoCancellation_Entry_Ret", "Discord::SetEchoCancellation(bool) (echo cancel off)"),
        ("SetEchoCancellationPreEcho_Entry_Ret", "Discord::SetEchoCancellationPreEcho (echo cancel off)"),
        ("EnableBuiltInAEC_Entry_Ret", "Discord::EnableBuiltInAEC (acoustic echo off; not Opus FEC)"),
        ("SetNoiseCancellation_Entry_Ret", "Discord::SetNoiseCancellation (Krisp NC off)"),
        ("SetNoiseCancellationDuringProcessing_Entry_Ret", "Discord::SetNoiseCancellationDuringProcessing (Krisp NC off)"),
    ],
}


def format_windows_debug_mode(results=None):
    lines = []
    name_w = PATCHER_OFFSET_NAME_WIDTH
    for group_name, patches in PATCHER_DEBUG_GROUPS.items():
        lines.append(f"  [{group_name}]")
        for key, _desc in patches:
            if results and key in results:
                lines.append(f"    {_format_offset_assignment(key, results[key], name_w, indent='')}")
            else:
                lines.append(f"    {key}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_linux_patcher_block(results, bin_info, file_path, file_size, data=None):
    if not bin_info or not file_path or file_size is None:
        return None
    fmt = bin_info.get('format', 'raw')
    if fmt != 'elf':
        return None
    if data is None:
        try:
            data = file_path.read_bytes()
        except Exception:
            data = b""
    linux_off = resolve_linux_patcher_offsets(results, data, bin_info)
    st = _linux_patcher_stats(linux_off)
    md5 = _md5_file_hex(file_path, lower=True)
    missing = st["missing"]
    lines = [
        "# region Offsets (PASTE HERE) -> discord_voice_patcher_linux.sh",
        f"# discord_voice_node_offset_finder.py v{VERSION}  |  sites {st['found']}/{st['expected']}",
    ]
    if missing:
        lines.append("# WARNING unresolved (left as 0x0, fix before patching): " + ", ".join(missing))
    lines += [
        f'EXPECTED_MD5="{md5}"',
        f"EXPECTED_SIZE={file_size}",
        "FILE_OFFSET_ADJUSTMENT=0",
        "",
    ]
    # Paste-ready bash assignments (no spaces around '=').
    for name in LINUX_PATCHER_OFFSET_ORDER:
        file_off = linux_off.get(name, 0)
        lines.append(f"OFFSET_{name}={_format_rva(file_off)}")
    lines.append("# endregion")
    lines.append("")
    lines.append("REQUIRED_OFFSET_NAMES=(")
    chunk = []
    for name in LINUX_PATCHER_OFFSET_ORDER:
        chunk.append(name)
        if len(chunk) >= 4:
            lines.append("    " + " ".join(chunk))
            chunk = []
    if chunk:
        lines.append("    " + " ".join(chunk))
    lines.append(")")
    return "\n".join(lines) + "\n"


def _macos_stereo_patch_stats(stereo_patches):
    """Count ARM64 stereo table hits vs MACOS_ARM64_PATCHER_OFFSET_ORDER."""
    if not stereo_patches:
        return {
            "arm64_found": 0,
            "arm64_expected": len(MACOS_ARM64_PATCHER_OFFSET_ORDER),
            "arm64_missing": list(MACOS_ARM64_PATCHER_OFFSET_ORDER),
            "arm64": [],
        }
    arm64 = [p for p in stereo_patches if p.get("arch") == "arm64"]
    arm64_names = {p["name"] for p in arm64}
    return {
        "arm64_found": len(arm64),
        "arm64_expected": len(MACOS_ARM64_PATCHER_OFFSET_ORDER),
        "arm64_missing": [n for n in MACOS_ARM64_PATCHER_OFFSET_ORDER if n not in arm64_names],
        "arm64": arm64,
    }


def _format_arm64_patch_entry(p: dict, name_w: int = 0, orig_w: int = 0) -> str:
    """One ARM64_PATCHES list item.

    Long orig/patch strings (shellcode) get an expanded multi-line dict; short
    ones use the aligned single-line layout from MacOS_ARM64_Patcher.py. ``name_w``
    and ``orig_w`` are the column widths used to align the single-line entries.
    """
    name = p["name"]
    fo = p["fat_offset"]
    orig = p["orig"]
    patch = p["patch"]
    if max(len(orig), len(patch)) > 56:
        return (
            f'    {{\n'
            f'        "name": "{name}",\n'
            f'        "fat_offset": 0x{fo:X},\n'
            f'        "orig": "{orig}",\n'
            f'        "patch": "{patch}",\n'
            f'    }},'
        )
    name_field = f'"{name}",'
    orig_field = f'"{orig}",'
    return (
        f'    {{"name": {name_field:<{name_w}} '
        f'"fat_offset": 0x{fo:X}, '
        f'"orig": {orig_field:<{orig_w}} '
        f'"patch": "{patch}"}},'
    )


def format_arm64_patches_python_block(stereo_patches, file_path, file_size,
                                      discord_app_version=None):
    """Copy-paste region for MacOS_ARM64_Patcher.py (# region ARM64 patch table).

    The emitted text reproduces that region 1:1 (markers, PATCHES_META, grouped
    + column-aligned ARM64_PATCHES) so it can replace the patcher's block directly.
    """
    if not stereo_patches:
        return None
    stats = _macos_stereo_patch_stats(stereo_patches)
    arm64 = stats["arm64"]
    if not arm64:
        return None
    by_name = {p["name"]: p for p in arm64}
    md5 = _md5_file_hex(file_path, lower=True)
    a64_info = None
    try:
        data = file_path.read_bytes() if hasattr(file_path, "read_bytes") else Path(file_path).read_bytes()
        macho = parse_macho(data)
        if macho and macho.get("arch") == "arm64":
            a64_info = macho
    except Exception:
        pass
    if discord_app_version is None:
        try:
            app_ver, _src = resolve_discord_app_version(
                Path(file_path), data=None, bin_info=a64_info, cli_version=None)
        except Exception:
            app_ver = "unspecified"
    else:
        app_ver = str(discord_app_version).strip() or "unspecified"

    # Column widths for the aligned single-line entries (shellcode dicts are
    # multi-line and excluded so they don't blow out the padding).
    single = [p for p in by_name.values() if max(len(p["orig"]), len(p["patch"])) <= 56]
    name_w = max((len(f'"{p["name"]}",') for p in single), default=0)
    orig_w = max((len(f'"{p["orig"]}",') for p in single), default=0)

    lines = ["# region ARM64 patch table"]

    missing = [n for n in MACOS_ARM64_PATCHER_OFFSET_ORDER if n not in by_name]
    if missing:
        lines.append(f"# WARNING: finder missing {len(missing)} site(s): {', '.join(missing)}")

    lines.extend([
        "PATCHES_META = {",
        f'    "finder_version": "discord_voice_node_offset_finder_v5.py v{VERSION}",',
        f'    "discord_app_version": "{app_ver}",',
        f'    "file_size": {file_size},',
        f'    "md5": "{md5}",',
    ])
    if a64_info:
        lines.append(f'    "arm64_slice_offset": 0x{a64_info.get("fat_offset", 0):X},')
        lines.append(f'    "arm64_slice_size": {a64_info.get("fat_size", 0)},')
    else:
        lines.append('    "arm64_slice_offset": 0x0,')
        lines.append('    "arm64_slice_size": 0,')
    lines.extend([
        "}",
        "",
        "ARM64_PATCHES: List[dict] = [",
    ])

    for gi, (group_label, names) in enumerate(MACOS_ARM64_PATCH_GROUPS):
        if gi > 0:
            lines.append("")
        lines.append(f"    # {group_label}")
        for name in names:
            p = by_name.get(name)
            if p is None:
                lines.append(f"    # MISSING: {name}")
                continue
            lines.append(_format_arm64_patch_entry(p, name_w, orig_w))

    # Any extra sites not in groups (should not happen)
    extras = [(n, p) for n, p in sorted(by_name.items())
              if n not in MACOS_ARM64_PATCHER_OFFSET_ORDER]
    if extras:
        lines.append("")
        lines.append("    # extra sites (not in known groups)")
        for _name, p in extras:
            lines.append(_format_arm64_patch_entry(p, name_w, orig_w))

    lines.append("]")
    lines.append("# endregion ARM64 patch table")
    return "\n".join(lines) + "\n"


def format_json(results, bin_info, file_path, file_size, adj, tiers_used,
                discord_app_version=None, discord_app_version_source=None):
    fmt = bin_info.get('format', 'raw') if bin_info else 'pe'
    offsets_only = {name: off for name, off in results.items() if name in ALLOWED_OFFSET_NAMES}
    out = {
        "tool": "discord_voice_node_offset_finder",
        "version": VERSION,
        "file": str(file_path),
        "file_size": file_size,
        "md5": _md5_file_hex(file_path),
        "format": fmt,
        "arch": bin_info.get('arch', 'unknown') if bin_info else 'unknown',
        "file_offset_adjustment": hex(adj),
        "offsets": {name: hex(off) for name, off in sorted(offsets_only.items())},
        "resolution_tiers": {k: v for k, v in (tiers_used or {}).items() if k in ALLOWED_OFFSET_NAMES},
        "total_found": len(offsets_only),
        "total_expected": len(ALL_OFFSET_NAMES),
        "linux_only_offset_names": list(LINUX_ONLY_OFFSET_NAMES),
        "discord_app_version": discord_app_version or "unspecified",
        "discord_app_version_source": (discord_app_version_source or "none"),
    }

    if fmt == 'pe' and bin_info:
        out["pe_timestamp"] = bin_info.get('timestamp')
        out["pe_build_time"] = bin_info['build_time'].isoformat() if 'build_time' in bin_info else None
        out["image_base"] = hex(bin_info.get('image_base', 0))
    elif fmt in ('elf', 'macho') and bin_info:
        out["image_base"] = hex(bin_info.get('image_base', 0))
        out["has_symbols"] = bin_info.get('has_symbols', False)
        out["file_offsets"] = {name: hex(off - adj) for name, off in sorted(offsets_only.items())}

    expected_map = _build_expected_map(fmt)
    if fmt == "pe":
        patch_name_order = PATCHER_OFFSET_NAMES
    elif fmt == "elf":
        patch_name_order = LINUX_WINDOWS_DISCOVERY_NAMES
    else:
        patch_name_order = _all_offset_names()
    patches = []
    for name in sorted(patch_name_order):
        if name not in offsets_only:
            continue
        file_off = offsets_only[name] - adj
        expected_hex, length = expected_map.get(name, (None, 0))
        patches.append({
            "name": name,
            "file_offset": file_off,
            "file_offset_hex": hex(file_off),
            "expected_original": expected_hex.replace(' ', '') if expected_hex else None,
            "length": length,
        })
    out["patches"] = patches

    if fmt in ('elf', 'macho'):
        inject = []
        for name, size in [("hp_cutoff_Callback_InjectShellcode", 0x100), ("dc_reject_Callback_InjectShellcode", 0x1B6)]:
            if name in offsets_only:
                file_off = offsets_only[name] - adj
                inject.append({
                    "name": name,
                    "file_offset": file_off,
                    "file_offset_hex": hex(file_off),
                    "inject_size": size,
                })
        out["injection_sites"] = inject

    if fmt == 'elf' and bin_info and results is not None:
        try:
            blob = file_path.read_bytes() if hasattr(file_path, "read_bytes") else b""
        except Exception:
            blob = b""
        linux_off = resolve_linux_patcher_offsets(results, blob, bin_info)
        lst = _linux_patcher_stats(linux_off)
        out["linux_patcher"] = {
            "tool": "discord_voice_patcher_linux.sh",
            "found": lst["found"],
            "expected": lst["expected"],
            "missing": lst.get("missing", []),
            "file_offsets": {n: hex(linux_off[n]) for n in LINUX_PATCHER_OFFSET_ORDER if linux_off.get(n)},
        }
        out["total_found"] = lst["found"]
        out["total_expected"] = lst["expected"]

    if bin_info and fmt == 'macho' and 'stereo_patches' in bin_info:
        sp = bin_info["stereo_patches"]
        out["stereo_patches"] = sp
        st = _macos_stereo_patch_stats(sp)
        out["macos_arm64_patcher"] = {
            "tool": "MacOS_ARM64_Patcher.py",
            "found": st["arm64_found"],
            "expected": st["arm64_expected"],
            "missing": st.get("arm64_missing", []),
        }
        out["total_found"] = st["arm64_found"]
        out["total_expected"] = st["arm64_expected"]

    return json.dumps(out, indent=2, ensure_ascii=True)




def generate_viz_graph(results, out_dir):
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




def find_discord_node():
    clients = ['discord', 'discordcanary', 'discordptb', 'discorddevelopment']
    clients_cap = ['Discord', 'DiscordCanary', 'DiscordPTB', 'DiscordDevelopment']

    def _search_modules_dirs(base):
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
        modules = base / 'modules'
        if modules.exists():
            for vd in modules.glob('discord_voice*'):
                for candidate in [vd / 'discord_voice' / 'discord_voice.node', vd / 'discord_voice.node']:
                    if candidate.exists():
                        return candidate
        return None

    def _search_recursive(base, max_depth=5):
        if not base.exists():
            return None
        for candidate in base.rglob('discord_voice.node'):
            try:
                rel = candidate.relative_to(base)
                if len(rel.parts) <= max_depth:
                    return candidate
            except ValueError:
                pass
        return None

    if sys.platform == 'win32':
        localappdata = os.environ.get('LOCALAPPDATA', '')
        if localappdata:
            for client in clients_cap:
                found = _search_modules_dirs(Path(localappdata) / client)
                if found:
                    return found

    elif sys.platform == 'darwin':
        home = Path.home()

        for app_name in ['Discord', 'Discord Canary', 'Discord PTB', 'Discord Development']:
            app_path = Path(f'/Applications/{app_name}.app/Contents/Resources')
            if app_path.exists():
                found = _search_modules_dirs(app_path)
                if found:
                    return found
                found = _search_recursive(app_path.parent / 'Frameworks', max_depth=6)
                if found:
                    return found

        app_support = home / 'Library' / 'Application Support'
        for client in clients:
            found = _search_modules_dirs(app_support / client)
            if found:
                return found

        for cask_dir in [Path('/usr/local/Caskroom'), Path('/opt/homebrew/Caskroom')]:
            if cask_dir.exists():
                for d in cask_dir.glob('discord*'):
                    found = _search_recursive(d, max_depth=8)
                    if found:
                        return found

        print("  Typical macOS locations:")
        print("    /Applications/Discord.app/Contents/Resources/app-*/modules/discord_voice*/")
        print("    ~/Library/Application Support/discord/*/modules/discord_voice*/")

    else:
        home = Path.home()

        config_dir = home / '.config'
        for client in clients:
            found = _search_modules_dirs(config_dir / client)
            if found:
                return found

        flatpak_base = home / '.var' / 'app'
        for flatpak_id in ['com.discordapp.Discord', 'com.discordapp.DiscordCanary']:
            flatpak = flatpak_base / flatpak_id
            if flatpak.exists():
                for sub in ['config/discord', 'config/discordcanary', '.config/discord', '.config/discordcanary']:
                    found = _search_modules_dirs(flatpak / sub)
                    if found:
                        return found
                found = _search_recursive(flatpak, max_depth=8)
                if found:
                    return found

        for snap_base in [Path('/snap'), home / 'snap']:
            for client in ['discord', 'discord-canary']:
                snap_dir = snap_base / client
                if snap_dir.exists():
                    found = _search_recursive(snap_dir, max_depth=8)
                    if found:
                        return found

        for sys_base in ['/opt', '/usr/share', '/usr/lib']:
            for pattern in ['discord*', 'Discord*']:
                for d in Path(sys_base).glob(pattern):
                    if d.is_dir():
                        found = _search_recursive(d, max_depth=6)
                        if found:
                            return found

        for d in home.glob('.discord*'):
            found = _search_recursive(d, max_depth=6)
            if found:
                return found

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




def _cleanup_created_files(path_list):
    for p in path_list:
        try:
            Path(p).unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


def main():
    created_files = []
    atexit.register(_cleanup_created_files, created_files)

    json_only = '--json' in sys.argv
    quiet = ('--quiet' in sys.argv or '-q' in sys.argv) or json_only
    export_path = None
    cli_discord_ver = None
    file_arg = None
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == '--export' and i + 1 < len(sys.argv):
            export_path = sys.argv[i + 1]
            i += 2
            continue
        if a == '--discord-version' and i + 1 < len(sys.argv):
            cli_discord_ver = sys.argv[i + 1].strip()
            i += 2
            continue
        if a in ('--json', '--quiet', '-q'):
            i += 1
            continue
        if a.startswith('-'):
            i += 1
            continue
        if file_arg is None:
            file_arg = a
        i += 1

    if not quiet:
        print("=" * 65)
        print(f"  Discord Voice Node Offset Finder v{VERSION}")
        print("  Cross-platform tiered scanning with chain-aware derivation")
        print("=" * 65)

    if file_arg:
        file_path = Path(file_arg)
    else:
        print("\nNo file specified, searching for Discord install...")
        file_path = find_discord_node()
        if file_path:
            print(f"  Found: {file_path}")
        else:
            print("  Not found. Usage: python discord_voice_node_offset_finder_v5.py [--discord-version 1.0.xxxx] <path>")
            sys.exit(1)

    if not file_path.exists():
        print(f"\nERROR: File not found: {file_path}")
        sys.exit(1)

    data = file_path.read_bytes()
    file_size = len(data)
    if not quiet:
        print(f"\n  File: {file_path}")
        print(f"  Size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
        print(f"  MD5:  {hashlib.md5(data).hexdigest()}")

    bin_info = detect_binary_format(data)
    fmt = bin_info.get('format', 'raw')
    adj = bin_info.get('file_offset_adjustment', 0)
    arch = bin_info.get('arch', 'unknown')
    dapp_ver, dapp_src = resolve_discord_app_version(
        file_path, data=data, bin_info=bin_info, cli_version=cli_discord_ver)

    if not quiet:
        print(f"\n  Binary Format:       {fmt.upper()}")
        print(f"  Architecture:        {arch}")
        if bin_info.get('note'):
            print(f"  NOTE: {bin_info['note']}")

    if fmt == 'pe' and not quiet:
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

    elif fmt == 'elf' and not quiet:
        ts = bin_info.get('text_section')
        if ts:
            print(f"  Offset Adjustment:   0x{adj:X}  (.text VA 0x{ts['vaddr']:X} - raw 0x{ts['raw_offset']:X})")
        else:
            print(f"  Offset Adjustment:   0x{adj:X}")
        n_func = len(bin_info.get('func_symbols', {}))
        has_sym = bin_info.get('has_symbols', False)
        print(f"  Symbol Table:        {'YES' if has_sym else 'NO'} ({n_func} function symbols)")
        if has_sym:
            print(f"  NOTE: Linux nodes usually ship with symbols; resolution uses the symbol table.")

    elif fmt == 'macho' and not quiet:
        ts = bin_info.get('text_section')
        if ts:
            print(f"  Offset Adjustment:   0x{adj:X}  (__TEXT,__text VA 0x{ts['vaddr']:X} - raw 0x{ts['raw_offset']:X})")
        else:
            print(f"  Offset Adjustment:   0x{adj:X}")
        if bin_info.get('arch') == 'arm64' and bin_info.get('fat_offset') is not None:
            print(f"  Fat Binary:          arm64 slice at offset 0x{bin_info['fat_offset']:X} ({bin_info.get('fat_size', 0):,} bytes)")
            n_func = len(bin_info.get('func_symbols', {}))
            if bin_info.get('has_symbols') and n_func:
                print(f"  ARM64 Symbol Table:  YES ({n_func} function symbols)")
        elif bin_info.get('intel_unsupported'):
            print("  WARNING: No ARM64 slice — Intel-only binaries are unsupported.")
            if bin_info.get('note'):
                print(f"  {bin_info['note']}")

    elif fmt == 'raw' and not quiet:
        print(f"  WARNING: Could not parse binary format - using raw scan (adj=0)")

    if not quiet:
        print(f"  Discord app build:   {dapp_ver}  (source: {dapp_src})")

    stereo_patches = []
    if fmt == 'macho':
        stereo_patches = find_macos_stereo_patches(data)
        if stereo_patches:
            bin_info["stereo_patches"] = stereo_patches

    verbose = not quiet
    emitted_json_text = None
    if quiet:
        _stdout_main = sys.stdout
        sys.stdout = io.StringIO()
    exit_code = 0
    results, errors, adj, tiers_used = None, [], 0, {}
    try:
        results, errors, adj, tiers_used = discover_offsets(data, bin_info, verbose=verbose)
        verified, warnings = validate_offsets(data, results, adj, bin_fmt=fmt)
        check_injection_sites(data, results, adj)

        if fmt == 'pe':
            ts = bin_info.get('text_section')
            if ts:
                t_start = ts['raw_offset']
                t_end = ts['raw_offset'] + ts['raw_size']
            else:
                t_start = 0
                t_end = len(data)
            run_bitrate_audit_pe(data, results, adj, t_start, t_end)

        xval_warnings = _cross_validate(results, adj, data, tiers_used=tiers_used, bin_fmt=fmt)
        if xval_warnings:
            print("\n" + "=" * 65)
            print("  PHASE 5: Cross-Validation")
            print("=" * 65)
            for w in xval_warnings:
                print(f"  [XVAL] {w}")

        if fmt == 'macho' and stereo_patches:
            st = _macos_stereo_patch_stats(stereo_patches)
            print("\n" + "=" * 65)
            print("  macOS ARM64 STEREO PATCH TABLE (MacOS_ARM64_Patcher.py)")
            print("=" * 65)
            print(f"  ARM64 static sites: {st['arm64_found']} / {st['arm64_expected']}")
            if st.get("arm64_missing"):
                print(f"  Missing: {', '.join(st['arm64_missing'])}")

        if len(results) >= 10 and fmt not in ('macho',):
            viz_path = generate_viz_graph(results, file_path.parent)
            if viz_path:
                created_files.append(viz_path)
                print(f"\n  Dependency graph saved: {viz_path}")

        print("\n" + "=" * 65)
        print("  RESULTS SUMMARY")
        print("=" * 65)
        print(f"  Format:           {fmt.upper()} ({arch})")
        if fmt == 'pe':
            patcher_count, n_pk = count_patcher_offsets_found(results)
            print(f"  Windows patcher:   {patcher_count} / {n_pk}  (required for Discord_voice_node_patcher.ps1)")
            core_hits = sum(1 for n in ALL_OFFSET_NAMES if n in results)
            print(f"  Core offsets:      {core_hits} / {len(ALL_OFFSET_NAMES)}  (stereo/codec)")
            print(f"  x86_64 keys in map: {len(results)}")
        elif fmt == 'macho':
            st = _macos_stereo_patch_stats(stereo_patches)
            print(f"  ARM64 patcher:    {st['arm64_found']} / {st['arm64_expected']}  (MacOS_ARM64_Patcher.py)")
            if bin_info.get('intel_unsupported'):
                print("  Intel (x86_64):   unsupported — no ARM64 slice in this binary")
        elif fmt == 'elf':
            linux_off = resolve_linux_patcher_offsets(results, data, bin_info)
            lst = _linux_patcher_stats(linux_off)
            print(f"  Linux patcher:    {lst['found']} / {lst['expected']}  (discord_voice_patcher_linux.sh)")
            if lst.get("missing"):
                print(f"  Missing: {', '.join(lst['missing'])}")
            disc = sum(1 for n in LINUX_WINDOWS_DISCOVERY_NAMES if n in results)
            print(f"  Linux discovery:  {disc} / {len(LINUX_WINDOWS_DISCOVERY_NAMES)} Windows-style keys (intermediate)")
        else:
            core_hits = sum(1 for n in ALL_OFFSET_NAMES if n in results)
            print(f"  Core offsets:       {core_hits} / {len(ALL_OFFSET_NAMES)}")
            print(f"  x86_64 found:      {len(results)} (including platform extras in map)")
        print(f"  Bytes verified:   {verified}")
        print(f"  Warnings:         {warnings}")
        print(f"  Cross-validation: {len(xval_warnings)} issue(s)" if xval_warnings else "  Cross-validation: clean")
        print(f"  Errors:           {len(errors)}")

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

        if results and fmt == 'elf':
            print("\n" + "=" * 65)
            print("  LINUX DISCOVERY KEYS (intermediate -> discord_voice_patcher_linux.sh)")
            print("=" * 65)
            print(f"  {'Name':<{OFFSET_LOG_NAME_WIDTH}s}  {'config_va':>10s}  {'file_offset':>10s}  tier")
            print(f"  {'-' * OFFSET_LOG_NAME_WIDTH}  {'-' * 10}  {'-' * 10}  {'-' * 20}")
            for name in sorted(LINUX_WINDOWS_DISCOVERY_NAMES):
                if name in results:
                    config_off = results[name]
                    file_off = config_off - adj
                    tier = tiers_used.get(name, '?')
                    print(
                        f"  {name:<{OFFSET_LOG_NAME_WIDTH}s}  {_format_rva(config_off):>10s}  "
                        f"{_format_rva(file_off):>10s}  [{tier}]"
                    )
                else:
                    print(f"  {name:<{OFFSET_LOG_NAME_WIDTH}s}  {'NOT FOUND':>10s}")
            print(f"\n  # Note: on Linux use the 'file_offset' values for direct binary patching")

        if results or stereo_patches:
            if fmt == 'pe':
                print("\n" + "=" * 65)
                print("  WINDOWS PATCHER OFFSETS")
                print("=" * 65)
                print_pe_offset_summary(results, tiers_used=tiers_used, adj=adj)
                win_block = format_windows_patcher_block(results, bin_info, file_path, file_size, discord_app_version=dapp_ver)
                if not win_block and bin_info and file_size is not None:
                    ok, err = _validate_pe_offsets_for_patcher(results, bin_info, file_size)
                    if not ok:
                        print(f"\n  [WARN] Windows patcher block skipped: {err}")
                if win_block:
                    print("\n" + "=" * 65)
                    print("  COPY BELOW -> Discord_voice_node_patcher.ps1")
                    print("  Replace the entire # region Offsets (PASTE HERE) ... # endregion Offsets section")
                    print("=" * 65)
                    print("")
                    print("--- BEGIN COPY (Windows) ---")
                    print(win_block, end="")
                    print("--- END COPY ---")
                    print("")
                    print("  DEBUG MODE (matches patcher GUI groups)")
                    print("  " + "-" * 60)
                    print(format_windows_debug_mode(results))
                    print("")

            if fmt == 'elf':
                linux_block = format_linux_patcher_block(results, bin_info, file_path, file_size, data=data)
                if linux_block:
                    print("\n" + "=" * 65)
                    print("  COPY BELOW -> discord_voice_patcher_linux.sh")
                    print("  Replace EXPECTED_MD5, EXPECTED_SIZE, and OFFSET_* section")
                    print("=" * 65)
                    print("")
                    print("--- BEGIN COPY (Linux) ---")
                    print(linux_block)
                    print("--- END COPY ---")
                    print("")
            elif fmt == 'macho':
                arm64_block = format_arm64_patches_python_block(stereo_patches, file_path, file_size)
                if arm64_block:
                    print("\n" + "=" * 65)
                    print("  COPY BELOW -> MacOS_ARM64_Patcher.py")
                    print("  Replace the entire # region ARM64 patch table ... # endregion ARM64 patch table section")
                    print("=" * 65)
                    print("")
                    print("--- BEGIN COPY (macOS ARM64) ---")
                    print(arm64_block)
                    print("--- END COPY ---")
                    print("")

            if fmt == 'macho' and stereo_patches:
                arm64_only = [p for p in stereo_patches if p.get("arch") == "arm64"]
                print("\n" + "=" * 65)
                print("  macOS ARM64 PATCH TABLE (MacOS_ARM64_Patcher.py)")
                print("=" * 65)
                print(f"  {'#':<3} {'Fat Offset':<12} {'Name':<36} Orig -> Patch")
                print(f"  {'-'*3} {'-'*12} {'-'*36} {'-'*20}")
                for i, p in enumerate(arm64_only, 1):
                    print(f"  {i:<3} 0x{p['fat_offset']:08X}  {p['name']:<36} {p['orig']} -> {p['patch']}")
                print(f"\n  Total: {len(arm64_only)} ARM64 patch sites (fat_offset = direct file offset)")
                print("  Apply: python3 MacOS_ARM64_Patcher.py <discord_voice.node>")

            if fmt == 'elf':
                offset_names = _all_offset_names()
                print(f"\n    # File offsets for direct binary patching (hex editor):")
                print("    FileOffsets = @{")
                for line in _format_offset_table_lines(
                        offset_names, {n: results[n] - adj for n in offset_names if n in results},
                        indent="        ", include_missing=True):
                    print(line)
                print("    }")

            stub_line = ""
            if fmt == 'pe' and bin_info and "hp_cutoff_Callback_InjectShellcode" in results:
                hpc_va = bin_info['image_base'] + results["hp_cutoff_Callback_InjectShellcode"]
                va_bytes = struct.pack('<Q', hpc_va)
                stub = b'\x48\xB8' + va_bytes + b'\xC3'
                stub_line = f"\n  WebRtcSplHighPass_Dispatch_MovRet stub: {stub.hex(' ')}\n    mov rax, 0x{hpc_va:X}; ret"
                print(stub_line)

            script_dir = Path(__file__).resolve().parent
            if fmt == 'pe':
                wb = format_windows_patcher_block(results, bin_info, file_path, file_size, discord_app_version=dapp_ver)
                file_content = [wb] if wb else []
            elif fmt == 'macho':
                mb = format_arm64_patches_python_block(stereo_patches, file_path, file_size)
                file_content = [mb] if mb else []
            else:
                ps_config = format_powershell_config(results, bin_info, file_path, file_size)
                file_content = [ps_config]
                file_content.append("\n# File offsets for direct binary patching:")
                for name in _all_offset_names():
                    if name in results:
                        file_content.append(f"# {name} = file:0x{results[name] - adj:X}  config:0x{results[name]:X}")

            for try_dir in [script_dir, file_path.parent, Path.cwd()]:
                try:
                    out_path = try_dir / "offsets.txt"
                    out_path.write_text("\n".join(file_content), encoding="ascii")
                    created_files.append(out_path)
                    print(f"\n  Offset file saved: {out_path}")
                    break
                except Exception:
                    continue

            try:
                json_text = format_json(
                    results, bin_info, file_path, file_size, adj, tiers_used,
                    discord_app_version=dapp_ver,
                    discord_app_version_source=dapp_src)
                emitted_json_text = json_text
                if json_only:
                    pass
                elif export_path:
                    Path(export_path).write_text(json_text, encoding="ascii")
                    if not quiet:
                        print(f"  JSON exported: {export_path}")
                else:
                    json_path = file_path.with_suffix('.offsets.json')
                    json_path.write_text(json_text, encoding="ascii")
                    created_files.append(json_path)
                    print(f"  JSON saved: {json_path}")
            except Exception:
                pass

        patcher_hits, n_pk = count_patcher_offsets_found(results or {})
        patcher_ok = (patcher_hits == n_pk) if results else False

        if fmt == 'pe':
            if patcher_ok:
                print(f"\n  *** ALL {n_pk} WINDOWS PATCHER OFFSETS FOUND ***")
                exit_code = 0
            else:
                if patcher_hits > 0:
                    print(f"\n  *** PARTIAL: {patcher_hits}/{n_pk} Windows patcher offsets ***")
                    exit_code = 1
                else:
                    print(f"\n  *** INSUFFICIENT: Windows patcher needs all {n_pk} ***")
                    exit_code = 2
        elif fmt == 'macho':
            st = _macos_stereo_patch_stats(stereo_patches)
            af, ae = st["arm64_found"], st["arm64_expected"]
            if af == ae:
                print(f"\n  *** ALL {af}/{ae} ARM64 STEREO PATCH SITES FOUND ***")
                exit_code = 0
            elif af >= ae - 2:
                print(f"\n  *** PARTIAL: {af}/{ae} ARM64 stereo patch sites ***")
                if st.get("arm64_missing"):
                    print(f"  Missing: {', '.join(st['arm64_missing'])}")
                exit_code = 1
            else:
                print(f"\n  *** INSUFFICIENT: {af}/{ae} ARM64 stereo patch sites ***")
                if st.get("arm64_missing"):
                    print(f"  Missing: {', '.join(st['arm64_missing'])}")
                exit_code = 2
        elif fmt == 'elf':
            linux_off = resolve_linux_patcher_offsets(results, data, bin_info)
            lst = _linux_patcher_stats(linux_off)
            lf, le = lst["found"], lst["expected"]
            if lf == le:
                print(f"\n  *** ALL {lf}/{le} LINUX PATCHER OFFSETS FOUND ***")
                exit_code = 0
            elif lf >= le - 3:
                print(f"\n  *** PARTIAL: {lf}/{le} Linux patcher offsets ***")
                if lst.get("missing"):
                    print(f"  Missing: {', '.join(lst['missing'])}")
                exit_code = 1
            else:
                print(f"\n  *** INSUFFICIENT: {lf}/{le} Linux patcher offsets ***")
                if lst.get("missing"):
                    print(f"  Missing: {', '.join(lst['missing'])}")
                exit_code = 2
        else:
            n_required = len(ALL_OFFSET_NAMES)
            if core_hits == n_required:
                print(f"\n  *** ALL {n_required} CORE OFFSETS FOUND ***")
                exit_code = 0
            elif core_hits >= n_required - 2:
                print(f"\n  *** PARTIAL SUCCESS: {core_hits}/{n_required} core x86_64 offsets ***")
                exit_code = 1
            else:
                print(f"\n  *** INSUFFICIENT RESULTS: {core_hits}/{n_required} core x86_64 offsets ***")
                exit_code = 2
    finally:
        if quiet:
            sys.stdout = _stdout_main
            if json_only and emitted_json_text is not None:
                print(emitted_json_text)
            elif fmt == 'pe' and results:
                patcher_count, n_q = count_patcher_offsets_found(results)
                xval = _cross_validate(results, adj, data, tiers_used=tiers_used, bin_fmt=fmt)
                print("  {} / {}  (required for Discord_voice_node_patcher.ps1)".format(patcher_count, n_q))
                print("  x86_64 discovered: {} offsets".format(len(results)))
                if patcher_count == n_q:
                    print("  [OK] ALL {} WINDOWS PATCHER OFFSETS FOUND".format(n_q))
                else:
                    print("  *** PARTIAL: {}/{} ***".format(patcher_count, n_q))
                print("  Cross-validation: clean" if not xval else "  Cross-validation: {} issue(s)".format(len(xval)))
                win_block = format_windows_patcher_block(results, bin_info, file_path, file_size, discord_app_version=dapp_ver)
                if win_block:
                    print("")
                    print("--- BEGIN COPY (Windows) ---")
                    print(win_block, end="")
                    print("--- END COPY ---")
            elif fmt == 'elf' and results:
                linux_block = format_linux_patcher_block(results, bin_info, file_path, file_size, data=data)
                if linux_block:
                    print("")
                    print("--- BEGIN COPY (Linux) ---")
                    print(linux_block)
                    print("--- END COPY ---")
            elif fmt == 'macho' and stereo_patches:
                st = _macos_stereo_patch_stats(stereo_patches)
                print("  ARM64 patcher: {} / {}  (MacOS_ARM64_Patcher.py)".format(
                    st["arm64_found"], st["arm64_expected"]))
                print("  Cross-validation: clean" if not xval_warnings else "  Cross-validation: {} issue(s)".format(len(xval_warnings)))
                arm64_block = format_arm64_patches_python_block(stereo_patches, file_path, file_size)
                if arm64_block:
                    print("")
                    print("--- BEGIN COPY (macOS ARM64) ---")
                    print(arm64_block)
                    print("--- END COPY ---")
    return exit_code


if __name__ == '__main__':
    code = main()
    if sys.stdin.isatty() and sys.platform == 'win32':
        input("\n  Press Enter to close...")
    sys.exit(code)

