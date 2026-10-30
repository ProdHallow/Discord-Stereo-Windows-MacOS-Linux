#!/usr/bin/env python3
"""Discord Voice Node Offset Finder: current Windows x64 active patches only."""
from __future__ import annotations
import argparse,contextlib,hashlib,io,json,os,re,shutil,struct,subprocess,sys,tempfile,uuid
from pathlib import Path
from datetime import datetime,timezone
VERSION = "7.3.0"
TARGET_BITRATE_BPS = 320000
BITRATE_MODE = 'cbr'
_MODERN_SCHEMA = 'discord-voice-patch-manifest-v6'
_PATCHER_PROFILE_CONTRACT = 'discord-voice-patcher-profile-v10'
_PROFILE_BANK_SCHEMA = 'discord-voice-profile-bank-v1'
_ACTIVE_MODERN_MANIFEST = None
_PREVIOUS_FULL_PROFILE_SHA256 = frozenset(('2eb6731093d2e73f71ff4b26cd0214a3586aa0457395930d22387aa9d230810d', '000108af7807755e2c6beb870f3d564e018cb395313289ee73981772b9a1e7b2', '0e3aaaa7b201ae21a81d3c8d2de3c2013b8319c2a5bdcc119bda47ae9c096ba8', '6bf399136c771424891f33b9b4cdbee21934aaf787b6ed6c9a1648a8b1a49f9e', '9b40b9adf694f85e2c9f53d3aef7d89280dc671e3ecd5e6a3b5860245f201e80', '20533f08f956d363b396f49cc683c03db68032d8f003040ebabb40b49f6319f1', '7aa3c21e23a0a89a0c6659b1b1a64e30897f81fe02425ee66b4dae306a0b9e53', 'a0e1f7cd4bf39ce2f5a10e119fbeb6dda6999ca94bbc5aee8b99f2bddf4787ea', 'b56a22330b4db8fc1a2c383468421228a9336aef8459d3dd29834c8ca840fc85', '07a4e29480e943724681cfa13ce4ae72d24f4f24cd7ee4ccd6eff62c2d7d66a2'))
_MODERN_PROFILE = {'id': 'discord-windows-x64-1.0.9265', 'source_sha256': '984dfb5ce083a513dfa207d9b48bca0a9f415d84df09b423e1505a7417009f60', 'source_md5': '6d8c7c6005f2c03454f2344e48cfcdc8', 'source_size': 22325176, 'sites': [{'name': 'CreateAudioFrame_ChannelAssign_Mov', 'reference_rva': 1272096, 'patch': '49 89 CD 90', 'length': 4, 'group': 'STEREO', 'description': 'Use the actual requested/source channel count from RCX instead of the previous minimum.', 'optional': False, 'expected': '4C 0F 43 E9', 'pattern': '4C 0F 43 E9 49 8B 0A 49 39 CD ?? ?? ?? ?? 4D 89 6E 28 C1 E8 02 69 C0 7B 14 00 00', 'target_offset': 10}, {'name': 'CapturedAudioProcessor_APMBypass_NopJmp', 'reference_rva': 969728, 'patch': '90 90 90 90 90 90 90 90 90 90 90 90 E9', 'length': 13, 'group': 'FILTER', 'description': 'Bypass the captured-audio APM processing block; the separate earlier Krisp stage is unaffected.', 'optional': False, 'expected': '84 C0 74 0D 83 BE 80 02 00 00 09 0F 8F', 'pattern': '89 44 24 34 48 89 F9 E8 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 4C 89 6C 24 38 44 0F B6 AC 24 B0 01 00 00 48 8B 8E 78 02 00 00', 'target_offset': 12}, {'name': 'CommitAudioCodec_ChannelCount_Imm02', 'reference_rva': 6730823, 'patch': '02', 'length': 1, 'group': 'STEREO', 'description': 'Default the ordinary Opus SDP configuration to two channels.', 'optional': False, 'expected': '01', 'pattern': '48 89 D9 48 89 FA E8 ?? ?? ?? ?? BD ?? 00 00 00 80 BC 24 80 01 00 00 01 ?? ?? 48 8B 84 24 78 01 00 00', 'target_offset': 12}, {'name': 'OpusSdp_StereoValueBypass_Jmp2', 'reference_rva': 6730870, 'patch': 'EB 09', 'length': 2, 'group': 'STEREO', 'description': 'Skip the stereo value-to-channel conversion while retaining optional-presence checks and string cleanup.', 'optional': False, 'expected': '31 ED', 'pattern': '80 BC 24 80 01 00 00 01 75 ?? 48 8B 84 24 78 01 00 00 48 83 BC 24 70 01 00 00 01 75 ?? 48 83 F8 10 72 ?? 48 8B 9C 24 60 01 00 00 ?? ?? 80 3B 31 40 0F 94 C5 FF C5 48 83 F8 10 72 ?? 48 8B', 'target_offset': 43}, {'name': 'ApplySettings_BitrateBase_Mov248k', 'reference_rva': 6731898, 'patch': '41 BE 00 E2 04 00', 'length': 6, 'group': 'BITRATE', 'description': 'Load flat 320000 into R14D.', 'optional': False, 'expected': '41 BE E0 2E 00 00', 'pattern': 'B9 00 7D 00 00 0F 42 C8 41 81 FE 41 1F 00 00 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 80 BC 24 58 01 00 00 01', 'target_offset': 15, 'accepted_legacy': ['41 BE C0 C8 03 00', '41 BE 00 E2 04 00']}, {'name': 'ApplySettings_BitrateSelect_Nop4', 'reference_rva': 6731904, 'patch': '90 90 90 90', 'length': 4, 'group': 'BITRATE', 'description': 'Disable the merged sample-rate tier selection.', 'optional': False, 'expected': '44 0F 43 F1', 'pattern': '0F 42 C8 41 81 FE 41 1F 00 00 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 80 BC 24 58 01 00 00 01 0F 85 ?? ?? ?? ??', 'target_offset': 16}, {'name': 'ApplySettings_BitrateChannels_Nop4', 'reference_rva': 6731908, 'patch': '90 90 90 90', 'length': 4, 'group': 'BITRATE', 'description': 'Disable the merged channel multiplier.', 'optional': False, 'expected': '44 0F AF F5', 'pattern': '41 81 FE 41 1F 00 00 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 80 BC 24 58 01 00 00 01 0F 85 ?? ?? ?? ?? 48 8B 84 24 48 01 00 00', 'target_offset': 17}, {'name': 'ApplySettings_MaxAvgBitrateClamp248k_Mov', 'reference_rva': 6732130, 'patch': 'B8 00 E2 04 00', 'length': 5, 'group': 'BITRATE', 'description': 'Keep the actual destination register; change the upper bitrate limit.', 'optional': False, 'expected': 'B8 30 C8 07 00', 'pattern': 'E8 ?? ?? ?? ?? EB ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 3D 71 17 00 00 41 BE 70 17 00 00', 'target_offset': 14, 'accepted_legacy': ['B8 C0 C8 03 00', 'B8 00 E2 04 00']}, {'name': 'SetTargetBitrate_ClampMax248k_Mov', 'reference_rva': 6740343, 'patch': 'BF 00 E2 04 00', 'length': 5, 'group': 'BITRATE', 'description': 'Keep the actual destination register; change the upper bitrate limit.', 'optional': False, 'expected': 'BF 30 C8 07 00', 'pattern': 'B9 70 17 00 00 0F 4D CA ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 48 89 44 24 40 8B 46 44', 'target_offset': 14, 'accepted_legacy': ['BF C0 C8 03 00', 'BF 00 E2 04 00']}, {'name': 'SetTargetBitrate_Mulss_Nop6', 'reference_rva': 6740446, 'patch': '90 90 90 90 90 90', 'length': 6, 'group': 'BITRATE', 'description': 'Disable the actual encoder multiplier.', 'optional': False, 'expected': 'F3 0F 59 44 81 EC', 'pattern': '49 39 C0 76 ?? F3 0F 2A C7 ?? ?? ?? ?? ?? ?? F3 0F 2C D0 48 8B 8E D0 00 00 00 E8 ?? ?? ?? ??', 'target_offset': 9}, {'name': 'OpusSdp_MaxPlaybackRate_Keep48k_Nop4', 'reference_rva': 6731182, 'patch': '90 90 90 90', 'length': 4, 'group': 'BANDWIDTH', 'description': 'Keep max_playback_rate_hz at 48000 for full-band coding; this does not change capture sample rate.', 'optional': False, 'expected': '44 0F 42 F0', 'pattern': '3D 40 1F 00 00 7C ?? 3D 80 BB 00 00 ?? ?? ?? ?? 44 89 B4 24 C8 00 00 00 48 8D 05 ?? ?? ?? ?? 48 89 84 24 98 00 00 00', 'target_offset': 12}, {'name': 'HighPassFilter_Process_Entry_Ret', 'reference_rva': 6781632, 'patch': 'C3', 'length': 1, 'group': 'FILTER', 'description': 'Bypass the per-channel biquad processing dispatch confirmed in IDA.', 'optional': False, 'expected': '41', 'pattern': '?? 56 56 57 53 48 83 EC 48 48 89 D6 48 89 CF 48 8B 05 ?? ?? ?? ?? 48 31 E0 48 89 44 24 40 48 8B 42 48 45 84 C0 74 ??', 'target_offset': 0}, {'name': 'CELT_Force', 'reference_rva': 11086392, 'patch': 'EA 03 00 00', 'length': 4, 'group': 'CELT', 'description': 'user_forced_mode moved from state+0x88 to state+0x8C.', 'optional': False, 'expected': '18 FC FF FF', 'pattern': '89 5E 70 0F 28 05 ?? ?? ?? ?? 0F 11 46 7C 48 C7 86 8C 00 00 00 ?? ?? ?? ?? 48 63 86 94 00 00 00 48 69 C8 1F 85 EB 51 48 89 CA', 'target_offset': 21}, {'name': 'CELT_DefaultMode', 'reference_rva': 11086516, 'patch': 'EA 03 00 00', 'length': 4, 'group': 'CELT', 'description': 'Default mode moved from state+0x3794 to state+0x3798.', 'optional': False, 'expected': 'E9 03 00 00', 'pattern': 'C1 E0 08 89 86 80 37 00 00 C7 86 B4 37 00 00 01 00 00 00 C7 86 98 37 00 00 ?? ?? ?? ?? C7 86 A8 37 00 00 51 04 00 00 8B 96 94 00 00 00 48 8D 8E C4 00 00 00', 'target_offset': 25}, {'name': 'SetTargetBitrate_ClampSelect_Nop3', 'reference_rva': 6740348, 'patch': '90 90 90', 'length': 3, 'group': 'BITRATE', 'description': 'Keep EDI at 320000 for the actual encoder call, including lower incoming bitrate requests.', 'optional': False, 'expected': '0F 4C F9', 'pattern': '0F 4D CA ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 48 89 44 24 40 8B 46 44 80 7E 48 01', 'target_offset': 14}, {'name': 'ApplySettings_MaxAvgBitrateSelect_Nop4', 'reference_rva': 6732135, 'patch': '90 90 90 90', 'length': 4, 'group': 'BITRATE', 'description': 'Keep the 320000 clamp result instead of accepting a lower negotiated maxaveragebitrate.', 'optional': False, 'expected': '48 0F 4C C3', 'pattern': 'EB ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 3D 71 17 00 00 41 BE 70 17 00 00 44 0F 4D F0', 'target_offset': 14}, {'name': 'OpusEncodeNative_AnalysisGate_Jmp', 'reference_rva': 11089337, 'patch': 'EB', 'length': 1, 'group': 'FILTER', 'description': 'Take the existing low-complexity branch; it skips analysis and resets initialized analysis state.', 'optional': False, 'expected': '7C', 'pattern': '83 7F 2C 07 48 89 7D B8 44 89 6D 0C ?? ?? 8B 87 94 00 00 00 3D 80 3E 00 00 7C ??', 'target_offset': 12}, {'name': 'OpusEncodeFrame_FilterBypass_CopyGain', 'reference_rva': 11097225, 'patch': '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00', 'length': 80, 'group': 'FILTER', 'description': 'Replace both inlined filters with input-to-output copy and selectable gain; rejoin before the original non-finite signal guard.', 'optional': False, 'kind': 'copy_gain', 'resume_rva': 11097945, 'expected': '0F 85 A1 01 00 00 98 69 C0 A7 09 00 00 49 63 D0 4C 69 C2 D3 4D 62 10 4C 89 C2 48 C1 EA 3F 49 C1 E8 20 41 C1 F8 06 41 01 D0 99 41 F7 F8 45 85 F6 0F 8E 9A 02 00 00 69 D0 29 FE FF FF 81 C2 00 00 00 10 F3 0F 2A C2 44 69 C0 AE 03 00 00 C1 FA 06', 'pattern': '48 63 D1 49 8D 4C 95 00 4C 8B 75 F8 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 48 63 D2 48 98 48 0F AF C0', 'target_offset': 12}, {'name': 'OpusEncoder_Init_ForceCBR', 'group': 'BITRATE', 'optional': False, 'description': 'Initialize Opus with VBR disabled; preserve its separate constraint flag.', 'length': 10, 'expected': '48 B8 01 00 00 00 01 00 00 00', 'patch': '48 B8 00 00 00 00 01 00 00 00', 'target_offset': 0, 'pattern': '48 B8 ?? ?? ?? ?? 01 00 00 00 48 89 86 98 00 00 00 48 B8 18 FC FF FF 18 00 00 00'}, {'name': 'OpusEncoder_SetVBR_ForceCBR', 'group': 'BITRATE', 'optional': False, 'description': 'After validating OPUS_SET_VBR input, force use_vbr=0 and silk_mode.useCBR=1, preventing later VBR re-enablement.', 'length': 13, 'expected': '89 86 98 00 00 00 B9 01 00 00 00 29 C1', 'patch': '31 C0 89 86 98 00 00 00 B9 01 00 00 00', 'target_offset': 9, 'pattern': '83 F8 01 0F 87 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 89 4E 40 E9 ?? ?? ?? ??'}], 'resume_locator': {'pattern': 'F3 0F 16 C0 F3 0F 11 87 90 37 00 00 41 B9 02 00 00 00 85 DB 0F 84 ?? ?? ?? ?? 45 89 C8 45 0F AF C6', 'target_offset': 18}, 'markers': ['ApplySettings_BitrateBase_Mov248k', 'CELT_Force', 'OpusEncodeFrame_FilterBypass_CopyGain']}

CURRENT_ACTIVE_PATCH_NAMES = tuple(site['name'] for site in _MODERN_PROFILE['sites'])
PATCHER_OFFSET_NAMES = list(CURRENT_ACTIVE_PATCH_NAMES)
ALL_OFFSET_NAMES = list(CURRENT_ACTIVE_PATCH_NAMES)
ALLOWED_OFFSET_NAMES = frozenset(CURRENT_ACTIVE_PATCH_NAMES)

def parse_pe(data):
    if len(data) < 0x40 or data[:2] != b'MZ':
        return None

    pe_offset = struct.unpack_from('<I', data, 0x3C)[0]
    if pe_offset < 0x40 or pe_offset + 24 > len(data) or data[pe_offset:pe_offset+4] != b'PE\x00\x00':
        return None

    coff = pe_offset + 4
    num_sections = struct.unpack_from('<H', data, coff + 2)[0]
    timestamp = struct.unpack_from('<I', data, coff + 4)[0]
    opt_header_size = struct.unpack_from('<H', data, coff + 16)[0]

    opt = coff + 20
    if not 1 <= num_sections <= 96 or opt_header_size < 96 or opt + opt_header_size > len(data):
        return None
    magic = struct.unpack_from('<H', data, opt)[0]
    machine = struct.unpack_from('<H', data, coff)[0]
    if magic == 0x20B:
        if opt_header_size < 112 or machine == 0x14C:
            return None
        image_base = struct.unpack_from('<Q', data, opt + 24)[0]
        directory_start, directory_count_offset = opt + 112, opt + 108
    elif magic == 0x10B and machine not in (0x8664, 0xAA64):
        image_base = struct.unpack_from('<I', data, opt + 28)[0]
        directory_start, directory_count_offset = opt + 96, opt + 92
    else:
        return None

    directory_count = struct.unpack_from('<I', data, directory_count_offset)[0]
    if directory_start + directory_count * 8 > opt + opt_header_size:
        return None
    exception_rva, exception_size = (struct.unpack_from('<II', data, directory_start + 24)
                                     if directory_count > 3 else (0, 0))
    headers_size = struct.unpack_from('<I', data, opt + 60)[0]

    sections = []
    sec_offset = opt + opt_header_size
    if sec_offset + num_sections * 40 > min(headers_size, len(data)):
        return None
    for i in range(num_sections):
        s = sec_offset + i * 40
        name = data[s:s+8].rstrip(b'\x00').decode('ascii', errors='replace')
        vsize = struct.unpack_from('<I', data, s + 8)[0]
        vaddr = struct.unpack_from('<I', data, s + 12)[0]
        raw_size = struct.unpack_from('<I', data, s + 16)[0]
        raw_offset = struct.unpack_from('<I', data, s + 20)[0]
        characteristics = struct.unpack_from('<I', data, s + 36)[0]
        if raw_size and (raw_offset < headers_size or raw_offset + raw_size > len(data)):
            return None
        if vaddr + max(vsize, raw_size) > 0x100000000:
            return None
        sections.append({
            'name': name, 'vsize': vsize, 'vaddr': vaddr,
            'raw_size': raw_size, 'raw_offset': raw_offset,
            'characteristics': characteristics,
        })

    # A file byte or RVA must never resolve to two different sections.
    for start_key, size in (('raw_offset', lambda s: s['raw_size']),
                            ('vaddr', lambda s: max(s['vsize'], s['raw_size']))):
        previous_end = 0
        for section in sorted(sections, key=lambda s: s[start_key]):
            if not size(section):
                continue
            if section[start_key] < previous_end:
                return None
            previous_end = section[start_key] + size(section)

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
        'exception_rva': exception_rva, 'exception_size': exception_size,
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
        # Virtual zero-fill has no file offset; raw alignment padding does.
        rs = sec.get("raw_size", 0)
        ro = sec.get("raw_offset", 0)
        if va and ro and va <= rva < va + rs:
            return rva - va + ro
    return None


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


def _modern_hits(data, locator, start=0, end=None):
    pattern = b''.join(b'.' if x == '??' else re.escape(bytes([int(x,16)])) for x in locator['pattern'].split())
    if not pattern:
        raise ValueError('Empty instruction context')
    regex = re.compile(pattern, re.DOTALL)
    end = len(data) if end is None else end
    hits = []
    while start < end:
        match = regex.search(data, start, end)
        if match is None:
            break
        hits.append(match.start() + locator['target_offset'])
        start = match.start() + 1  # Include overlapping matches when testing uniqueness.
    return hits


def _runtime_functions(data, info):
    """Read only the PE exception directory, excluding section alignment padding."""
    rva, size = info.get('exception_rva', 0), info.get('exception_size', 0)
    off = _pe_rva_to_file_off(rva, info['sections'])
    if (not size or size % 12 or off is None or off + size > len(data)
            or _pe_rva_to_file_off(rva + size - 1, info['sections']) != off + size - 1):
        return []
    functions = []
    previous_end = 0
    for p in range(off, off + size, 12):
        begin, end, unwind = struct.unpack_from('<III', data, p)
        if (begin < previous_end or begin >= end
                or _pe_rva_to_file_off(begin, info['sections']) is None
                or _pe_rva_to_file_off(end - 1, info['sections']) is None
                or _pe_rva_to_file_off(unwind, info['sections']) is None):
            return []
        functions.append((begin, end))
        previous_end = end
    return functions


def _check_report_destination(destination, *protected_paths):
    """Reports must not overwrite a node, patcher, or their filesystem aliases."""
    destination = Path(destination).expanduser().resolve()
    for path in protected_paths:
        if path is None:
            continue
        protected = Path(path).expanduser().resolve()
        if destination == protected or (destination.exists() and protected.exists()
                                        and os.path.samefile(destination, protected)):
            raise ValueError('Choose a separate report file; the node and patcher cannot be overwritten.')
    return destination


def _modern_probe(data, info):
    # Scan every Windows x64 PE. Neither a known file identity nor marker
    # preselection is required: a missing marker must be reported as a failed
    # site, rather than silently selecting the legacy engine.
    return info.get('format') == 'pe' and info.get('arch') == 'x86_64'


def _previous_gain_loop(site_rva, resume_rva, gain=1, capacity=80):
    """No calls, stack changes, absolute addresses, or nonvolatile-register changes.
    IDA: RCX=output, R15=input, R14D=frames, R9D=channels. Rejoin the original
    finite-signal guard, not the end of the encoder or another function.
    """
    if not 1 <= gain <= 10:
        raise ValueError('Gain must be between 1 and 10')
    out=bytearray.fromhex('45 89 C8 45 0F AF C6 45 85 C0 0F 8E')
    out += struct.pack('<i', resume_rva-(site_rva+len(out)+4))
    # Match the old gain controls, including per-channel normalization at 2x.
    if gain == 1:
        out += bytes.fromhex('B8 00 00 80 3F 66 0F 6E C8')
    elif gain == 2:
        out += bytes.fromhex('0F 57 C9 F3 41 0F 2A C9 F3 0F 52 C9 F3 0F 58 C9')
    else:
        out += b'\xB8'+struct.pack('<I',gain-2)+bytes.fromhex('44 01 C8 0F 57 C9 F3 0F 2A C8')
    out += bytes.fromhex('31 D2')
    loop=len(out)
    out += bytes.fromhex('F3 41 0F 10 04 97 F3 0F 59 C1 F3 0F 11 04 91 48 FF C2 4C 39 C2 72')
    displacement=loop-(len(out)+1)
    out += struct.pack('b',displacement)
    out += b'\xE9'+struct.pack('<i',resume_rva-(site_rva+len(out)+5))
    if len(out)>capacity:
        raise ValueError('Copy/gain loop exceeds its verified replacement span')
    return bytes(out)+b'\x90'*(capacity-len(out))


def _modern_gain_loop(site_rva, resume_rva, gain=1, capacity=80):
    """Exact linear sample gain, independent of the channel count."""
    if not 1 <= gain <= 10:
        raise ValueError('Gain must be between 1 and 10')
    out = bytearray(_previous_gain_loop(site_rva, resume_rva, 1, capacity))
    # MOV EAX,<float gain>; MOVD XMM1,EAX. The old level-2 RSQRT path
    # is used only to recognize older files, never emitted as a new patch.
    struct.pack_into('<f', out, 17, float(gain))
    return bytes(out)


def _modern_manifest_document(manifest, file_path=None, app_version=None):
    out=dict(manifest)
    if file_path is not None: out['file']=str(file_path)
    if app_version: out['discord_app_version']=str(app_version)
    if file_path is not None:
        out['discord_channel'] = resolve_discord_channel(file_path)
    return json.dumps(out,indent=2,ensure_ascii=True)


def resolve_discord_channel(file_path):
    """Installation-path label only; binary identity determines compatibility."""
    channels = {'discord': 'Stable', 'discordptb': 'PTB',
                'discordcanary': 'Canary', 'discorddevelopment': 'Development'}
    parts = re.split(r'[/\\]+', str(file_path))
    for part in reversed(parts[:-1]):
        if part.lower() in channels:
            return channels[part.lower()]
    return 'Unknown'


def _modern_compact_document(manifest, file_path=None, app_version=None):
    """Keep executable data; omit scan diagnostics and duplicated offset maps."""
    keys = ('schema', 'version', 'profile', 'file_size', 'original_sha256',
            'original_md5', 'target_bitrate_bps', 'bitrate_mode', 'complete', 'total_expected', 'missing',
            'source_builds')
    out = {key: manifest[key] for key in keys if key in manifest}
    version = app_version or manifest.get('discord_app_version')
    if version:
        out['discord_app_version'] = str(version)
    patch_keys = ('name', 'group', 'rva', 'file_offset', 'length',
                  'expected_original', 'patch', 'optional', 'kind', 'accepted_legacy')
    lines = ['{']
    for key, value in out.items():
        lines.append('  ' + json.dumps(key) + ': ' + json.dumps(value) + ',')
    lines.append('  "patches": [')
    for index, site in enumerate(manifest['patches']):
        row = {key: site[key] for key in patch_keys if key in site}
        if 'gain_patches' in site:
            row['gain_patches'] = site['gain_patches']
        if 'legacy_gain_patches' in site:
            row['legacy_gain_patches'] = site['legacy_gain_patches']
        text = json.dumps(row, separators=(', ', ': '), ensure_ascii=True)
        lines.append('    ' + text + (',' if index+1 < len(manifest['patches']) else ''))
    lines.extend(['  ]', '}'])
    return '\n'.join(lines)


def _modern_powershell_block(manifest, file_path=None, app_version=None):
    if not manifest['complete']:
        return None
    return _profile_bank_powershell_block(_merge_profile_bank([], manifest, file_path, app_version))


def _merge_profile_bank(entries, manifest, file_path=None, app_version=None):
    """One entry per stock binary, with channel/version labels shared on duplicates."""
    compact = json.loads(_modern_compact_document(manifest, file_path, app_version))
    identity = compact['original_sha256'].lower()
    builds = list(compact.get('source_builds', []))
    for entry in entries:
        if entry['manifest']['original_sha256'].lower() == identity:
            builds.extend(entry['manifest'].get('source_builds', []))
    if file_path is not None:
        builds.append({'channel': resolve_discord_channel(file_path),
                       'app_version': app_version or manifest.get('discord_app_version') or 'unspecified'})
    compact['source_builds'] = [json.loads(value) for value in sorted({
        json.dumps(build, sort_keys=True) for build in builds})]
    new_entry = {'plan_sha256': patch_plan_fingerprint(compact), 'manifest': compact}
    merged = [entry for entry in entries if entry['manifest']['original_sha256'].lower() != identity]
    merged.append(new_entry)
    return sorted(merged, key=lambda entry: entry['manifest']['original_sha256'].lower())


def _profile_bank_powershell_block(entries):
    rows = []
    for entry in entries:
        document = _modern_compact_document(entry['manifest'])
        rows.append('    {"plan_sha256": ' + json.dumps(entry['plan_sha256'])
                    + ', "manifest": ' + document.replace('\n', '\n    ') + '}')
    return ("# region Offsets (PASTE HERE)\n"
            "# Verified build bank for patcher v24.1+. Automatic updates preserve other builds.\n"
            "$Script:VoiceProfileBank = @'\n"
            '{\n  "schema": "' + _PROFILE_BANK_SCHEMA + '",\n  "profiles": [\n'
            + ',\n'.join(rows) + "\n  ]\n}\n'@ | ConvertFrom-Json\n"
            "# endregion Offsets\n")


def _read_profile_bank(region):
    matches = re.findall(r"(?ms)^\$Script:VoiceProfileBank = @'\r?\n(.*?)\r?\n'@ \| ConvertFrom-Json\s*$", region)
    if len(matches) != 1:
        raise ValueError('Patcher unchanged: expected one readable build bank.')
    bank = json.loads(matches[0])
    entries = bank.get('profiles')
    if bank.get('schema') != _PROFILE_BANK_SCHEMA or not isinstance(entries, list) or not entries:
        raise ValueError('Patcher unchanged: invalid or empty build bank.')
    identities = set()
    for entry in entries:
        m = entry['manifest']
        identity = m['original_sha256'].lower()
        if (not re.fullmatch(r'[0-9a-f]{64}', identity) or identity in identities
                or m.get('schema') != _MODERN_SCHEMA or m.get('complete') is not True
                or m.get('missing') or m.get('total_expected') != len(CURRENT_ACTIVE_PATCH_NAMES)
                or {s['name'] for s in m['patches']} != set(CURRENT_ACTIVE_PATCH_NAMES)
                or len(m['patches']) != len(CURRENT_ACTIVE_PATCH_NAMES)
                or patch_plan_fingerprint(m) != entry.get('plan_sha256')):
            raise ValueError('Patcher unchanged: an existing build profile failed validation.')
        identities.add(identity)
    return entries


def patch_plan_fingerprint(manifest):
    lines = [manifest['schema'], manifest['profile'], str(manifest['file_size']),
             manifest['original_sha256'].lower(), str(manifest['target_bitrate_bps']), manifest['bitrate_mode']]
    for site in sorted(manifest['patches'], key=lambda item: item['file_offset']):
        fields = [site['name'], site['group'], str(int(site['rva'], 16)),
                  str(site['file_offset']), str(site['length']),
                  ''.join(site['expected_original'].split()).upper(),
                  ''.join(site['patch'].split()).upper(),
                  '1' if site['optional'] else '0', site.get('kind', '')]
        fields.extend(''.join(site.get('gain_patches', {}).get(str(gain), '').split()).upper()
                      for gain in range(1, 11))
        fields.extend(''.join(site.get('legacy_gain_patches', {}).get(str(gain), '').split()).upper()
                      for gain in range(1, 11))
        fields.append(','.join(''.join(v.split()).upper() for v in site.get('accepted_legacy', [])))
        lines.append('|'.join(fields))
    return hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest()


def _validate_patcher_syntax(path):
    shell = shutil.which('powershell.exe') or shutil.which('pwsh')
    if not shell:
        raise ValueError('PowerShell is required to validate the updated Windows patcher.')
    command = ("$errors=$null;$tokens=$null;"
               "[void][System.Management.Automation.Language.Parser]::ParseFile("
               "$env:DISCORD_VOICE_VALIDATE_PATH,[ref]$tokens,[ref]$errors);"
               "if($errors.Count){$errors | ForEach-Object {$_.Message};exit 1};exit 0")
    environment = os.environ.copy()
    environment['DISCORD_VOICE_VALIDATE_PATH'] = str(path)
    process = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', command],
                             capture_output=True, text=True, timeout=20, env=environment,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if process.returncode:
        raise ValueError('Updated patcher did not pass syntax validation: '
                         + (process.stdout + process.stderr).strip())


def _prune_generated_patcher_backups(target):
    pattern = re.compile(re.escape(target.name) + r'\.backup-\d{8}-\d{6}-\d{6}-[0-9a-f]{8}\.bak$')
    candidates = sorted((p for p in target.parent.iterdir() if p.is_file() and pattern.fullmatch(p.name)),
                        key=lambda p: (p.stat().st_mtime_ns, p.name))
    keep = set(candidates[:1] + candidates[-5:])
    for candidate in candidates:
        if candidate not in keep:
            candidate.unlink()


def update_patcher_script(manifest, patcher_path, node_path, app_version=None):
    """Merge a validated build into the patcher's bank without losing other builds.

    Only the Offsets region changes. Its fingerprint and expected count move
    with the byte plan. A fresh scan of the source binary verifies every site
    and binds the generated profile to that binary, including new builds.
    """
    if (manifest.get('schema') != _MODERN_SCHEMA or not manifest.get('complete')
            or manifest.get('missing') or manifest.get('errors')
            or len(manifest.get('patches', [])) != manifest.get('total_expected')):
        raise ValueError('Patcher unchanged: a complete, validated Windows profile is required.')
    target = Path(patcher_path).expanduser().resolve(strict=True)
    node = Path(node_path).expanduser().resolve(strict=True)
    if target == node or target.suffix.lower() != '.ps1':
        raise ValueError('Select a Windows .ps1 patcher file, separate from the node binary.')
    original = target.read_bytes()
    try:
        source = original.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('Patcher must use UTF-8 text encoding.') from error
    contract = re.findall(r"(?m)^\$Script:ProfileContract\s*=\s*'([^']+)'\s*\r?$", source)
    if contract != [_PATCHER_PROFILE_CONTRACT]:
        raise ValueError('This patcher does not support automatic profile updates. '
                         'Install the included v24.1 patcher once, then select it here.')
    starts = list(re.finditer(r'(?m)^# region Offsets \(PASTE HERE\)\r?$', source))
    ends = list(re.finditer(r'(?m)^# endregion Offsets\r?$', source))
    if len(starts) != 1 or len(ends) != 1 or starts[0].start() >= ends[0].start():
        raise ValueError('Patcher unchanged: expected one unambiguous Offsets region.')
    data = node.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest.get('sha256'):
        raise ValueError('Node changed after the scan; run Find Offsets again.')
    info = detect_binary_format(data)
    if not _modern_probe(data, info):
        raise ValueError('Automatic patcher updates require a supported modern Windows profile.')
    _, errors, _, _ = discover_offsets(data, info, verbose=False)
    verified = info.get('modern_manifest', {})
    if errors or not verified.get('complete'):
        raise ValueError('Patcher unchanged: some patch sites failed validation; inspect the scan results.')
    if patch_plan_fingerprint(manifest) != patch_plan_fingerprint(verified):
        raise ValueError('Patch data differs from the validated scan; patcher unchanged.')
    version, _ = resolve_discord_app_version(node, data=data, bin_info=info,
                                            cli_version=app_version)
    if not version or version == 'unspecified':
        version = manifest.get('discord_app_version')
        if not version:
            match = re.search(r'(\d+\.\d+\.\d+)$', str(verified.get('profile', '')))
            version = match.group(1) if match else None
    entries = _read_profile_bank(source[starts[0].end():ends[0].start()])
    entries = _merge_profile_bank(entries, verified, node, version)
    block = _profile_bank_powershell_block(entries)
    newline = '\r\n' if '\r\n' in source else '\n'
    block = block.rstrip('\r\n').replace('\n', newline)
    begin, end = starts[0].start(), ends[0].end()
    # End matches include the CR in CRLF; consume the complete region, retaining
    # the existing following line break exactly once.
    if source[end-1:end] == '\r':
        end -= 1
    changed = source[:begin] + block + source[end:]
    encoded = changed.encode('utf-8-sig')  # Windows PowerShell 5.1 understands UTF-8 with BOM.
    if not original.startswith(b'\xef\xbb\xbf'):
        encoded = changed.encode('utf-8')
    digest = patch_plan_fingerprint(verified)
    result = {'status': 'unchanged', 'patcher': str(target), 'backup': None,
              'sites': len(verified['patches']), 'plan_sha256': digest,
              'profile_count': len(entries), 'channel': resolve_discord_channel(node),
              'app_version': version, 'profile_block': block}
    if encoded == original:
        _validate_patcher_syntax(target)
        if target.read_bytes() != original or hashlib.sha256(node.read_bytes()).hexdigest() != manifest['sha256']:
            raise ValueError('Patcher or node changed during validation; run Find Offsets again.')
        return result
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.voice-profile-', suffix='.ps1',
                                         dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _validate_patcher_syntax(temporary)
        if target.read_bytes() != original:
            raise ValueError('Patcher changed during validation; no update written.')
        if hashlib.sha256(node.read_bytes()).hexdigest() != manifest['sha256']:
            raise ValueError('Node changed during validation; no update written.')
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        backup = target.with_name(target.name + '.backup-' + timestamp + '-' + uuid.uuid4().hex[:8] + '.bak')
        with backup.open('xb') as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, target.stat().st_mode)
        os.replace(temporary, target)
        temporary = None
        if target.read_bytes() != encoded:
            raise OSError('Patcher changed after the update; the original is saved at ' + str(backup))
        result.update(status='updated', backup=str(backup))
        try:
            _prune_generated_patcher_backups(target)
        except OSError as error:
            result['backup_cleanup_warning'] = str(error)
        return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def detect_binary_format(data):
    try:
        info = parse_pe(data)
        if info:
            machine = struct.unpack_from('<H',data,info['pe_offset']+4)[0]
            info.update(format='pe',arch={0x8664:'x86_64',0x14c:'x86',0xaa64:'arm64'}.get(machine,'unknown'))
            return info
    except (ValueError,struct.error,OverflowError,OSError):
        pass
    return dict(format='raw',arch='unknown',sections=[],image_base=0,file_offset_adjustment=0,text_section=None)

def _modern_patch_detection(data, manifest):
    """Classify recognized patch bytes; incomplete scans never certify stock.

    On unknown builds, stock means no known modifications at the tracked sites,
    not proof that every other byte is an original vendor byte.
    """
    active = manifest['patches']
    states, legacy, modified_active = {}, [], []
    detected_gain, gain_mode = None, None
    for site in manifest['patches']:
        current = data[site['file_offset']:site['file_offset'] + site['length']]
        original = bytes.fromhex(site['expected_original'])
        if current == original:
            variant = 'stock'
        else:
            gains = site.get('gain_patches', {})
            gain = next((int(k) for k, v in gains.items() if current == bytes.fromhex(v)), None)
            if current == bytes.fromhex(site['patch']) or gain is not None:
                variant = 'current'
                if gain is not None:
                    detected_gain, gain_mode = gain, 'linear'
            else:
                variant = 'legacy'
                legacy.append(site['name'])
                gain = next((int(k) for k, v in site.get('legacy_gain_patches', {}).items()
                             if current == bytes.fromhex(v)), None)
                if gain is not None:
                    detected_gain, gain_mode = gain, 'legacy'
            modified_active.append(site['name'])
        site['detected_variant'] = variant
        states[site['name']] = variant
    modified = [name for name, variant in states.items() if variant != 'stock']
    complete = manifest['complete']
    if not complete:
        status = 'patched_incomplete' if modified else 'unknown'
    elif not modified:
        status = 'stock'
    elif legacy:
        status = 'legacy_patched'
    elif len(modified_active) == manifest['expected_active_patches']:
        status = 'patched'
    else:
        status = 'partially_patched'
    manifest.update(patch_status=status,
                    is_patched=True if modified else (False if complete else None),
                    detection_complete=complete,
                    detection_scope='tracked-patch-sites',
                    known_stock_identity=(complete and manifest['sha256'] == _MODERN_PROFILE['source_sha256']),
                    patched_active_sites=len(modified_active),
                    stock_active_sites=len(active) - len(modified_active),
                    modified_site_count=len(modified),
                    modified_sites=modified, legacy_patch_sites=legacy,
                    site_patch_states=states, unknown_patch_sites=list(manifest['missing']),
                    detected_gain_level=detected_gain, detected_gain_mode=gain_mode)


def _modern_patch_status_text(manifest):
    status = manifest['patch_status']
    count = manifest['patched_active_sites']
    total = manifest['expected_active_patches']
    if status == 'stock':
        return ('STOCK - verified original hash' if manifest['known_stock_identity'] else
                'NO KNOWN PATCHES - tracked sites are stock; new binary identity')
    if status == 'patched_incomplete':
        return f'PATCHED - {count} known active patches detected; offset scan incomplete'
    if status == 'unknown':
        return 'UNKNOWN/INCOMPLETE - ' + (str(manifest['modified_site_count']) + ' known modified sites detected' if manifest['is_patched'] else 'cannot determine full patch state')
    if status == 'patched':
        text = f'PATCHED - {count}/{total} current active patches'
    elif status == 'legacy_patched':
        text = f'LEGACY/MIXED PATCHES - {count}/{total} active sites modified; {len(manifest["legacy_patch_sites"])} legacy site(s)'
    else:
        text = f'PARTIALLY PATCHED - {count}/{total} active sites modified'
    gain = manifest.get('detected_gain_level')
    if gain is not None:
        text += f'; gain {gain}x' if manifest['detected_gain_mode'] == 'linear' else f'; legacy gain level {gain}'
    return text


def _modern_resolve(data, info):
    sections = info['sections']
    adj = info['file_offset_adjustment']
    base = info['image_base']
    ts = info.get('text_section') or {}
    lo = ts.get('raw_offset', 0)
    hi = lo + ts.get('raw_size', 0)
    valid_text = (ts.get('name') == '.text' and 0 < lo < hi <= len(data)
                  and bool(ts.get('characteristics', 0) & 0x20000000))
    result, errors, tiers, patches, diagnostics = {}, [], {}, [], {}
    functions = _runtime_functions(data, info)

    def fail(name, reason):
        errors.append((name, reason))
        print(f'  [FAIL] {name}: {reason}')

    resume_hits = _modern_hits(data, _MODERN_PROFILE['resume_locator'], lo, hi) if valid_text else []
    resume_file = resume_hits[0] if len(resume_hits) == 1 else None
    resume_rva = _pe_file_off_to_rva(resume_file, sections) if resume_file is not None else None
    for reference in _MODERN_PROFILE['sites']:
        name = reference['name']
        if not valid_text:
            fail(name, 'Missing or invalid .text section; cannot search instruction contexts')
            continue
        candidates = _modern_hits(data, reference, lo, hi)
        diagnostics[name] = {
            'candidate_count': len(candidates),
            'candidates': [{'file_offset': candidate,
                            'rva': hex(_pe_file_off_to_rva(candidate, sections))
                                   if _pe_file_off_to_rva(candidate, sections) is not None else None,
                            'bytes': data[candidate:candidate + reference['length']].hex(' ').upper()}
                           for candidate in candidates[:8]],
        }
        if len(candidates) != 1 or candidates[0] is None:
            fail(name, f'Expected exactly one function context, found {len(candidates)}')
            continue
        off = candidates[0]
        rva = _pe_file_off_to_rva(off, sections)
        length = reference['length']
        expected = bytes.fromhex(reference['expected'])
        if (rva is None or not lo <= off < off + length <= hi
                or _pe_rva_to_file_off(rva, sections) != off):
            fail(name, 'Patch span is outside mapped .text bytes')
            continue
        if len(expected) != length or len(bytes.fromhex(reference['patch'])) != length:
            fail(name, 'Instruction/replacement length does not match the patch span')
            continue
        function = next((fn for fn in functions if fn[0] <= rva < fn[1]), None)
        context_rva = rva - reference['target_offset']
        context_length = len(reference['pattern'].split())
        if (function is None or context_rva < function[0]
                or max(rva + length, context_rva + context_length) > function[1]):
            fail(name, 'Instruction context/span is outside a valid runtime function')
            continue
        if name == 'HighPassFilter_Process_Entry_Ret' and rva != function[0]:
            fail(name, 'RET replacement is not at the runtime function entry')
            continue
        site = {key: reference[key] for key in ('name', 'group', 'description', 'optional')}
        site.update(rva=hex(rva), file_offset=off, length=length,
                    expected_original=expected.hex(' ').upper())
        acceptable = [expected]
        if reference.get('kind'):
            site['kind'] = reference['kind']
        if reference.get('accepted_legacy'):
            site['accepted_legacy'] = list(reference['accepted_legacy'])
            acceptable.extend(bytes.fromhex(value) for value in site['accepted_legacy'])
        if reference.get('kind') == 'copy_gain':
            if resume_rva is None:
                fail(name, f'Expected exactly one filter resume context, found {len(resume_hits)}')
                continue
            resume_context = resume_rva - _MODERN_PROFILE['resume_locator']['target_offset']
            resume_end = resume_context + len(_MODERN_PROFILE['resume_locator']['pattern'].split())
            if (not rva + length <= resume_context <= resume_rva < function[1]
                    or resume_end > function[1]):
                fail(name, 'Filter resume/span is outside the matched encoder function')
                continue
            try:
                variants = {str(gain): _modern_gain_loop(rva, resume_rva, gain, length).hex(' ').upper()
                            for gain in range(1, 11)}
            except (ValueError, struct.error) as error:
                fail(name, f'Cannot encode the relocated gain loop: {error}')
                continue
            previous = {str(gain): _previous_gain_loop(rva, resume_rva, gain, length).hex(' ').upper()
                        for gain in range(1, 11)}
            site.update(kind='copy_gain', resume_rva=hex(resume_rva),
                        gain_patches=variants, legacy_gain_patches=previous, patch=variants['1'])
            site['accepted_legacy'] = list(dict.fromkeys(previous.values()))
            acceptable.extend(bytes.fromhex(value) for value in variants.values())
            acceptable.extend(bytes.fromhex(value) for value in previous.values())
        else:
            site['patch'] = reference['patch']
            acceptable.append(bytes.fromhex(reference['patch']))
        if name == 'CapturedAudioProcessor_APMBypass_NopJmp':
            # The replacement keeps the existing rel32 displacement at +13.
            destination = rva + 17 + struct.unpack_from('<i', data, off + 13)[0]
            destination_off = _pe_rva_to_file_off(destination, sections)
            continuation = bytes.fromhex('8B 44 24 34 41 89 45 00')
            if (not rva + 17 <= destination <= function[1] - len(continuation)
                    or destination_off is None
                    or data[destination_off:destination_off + len(continuation)] != continuation):
                fail(name, 'APM bypass branch does not reach the expected continuation inside the function')
                continue
        if name == 'OpusEncodeNative_AnalysisGate_Jmp':
            destination = rva + 2 + struct.unpack_from('b', data, off + 1)[0]
            second_destination = rva + 15 + struct.unpack_from('b', data, off + 14)[0]
            destination_off = _pe_rva_to_file_off(destination, sections)
            continuation = bytes.fromhex('83 BF E8 1D 00 00 00 4C 8B 7D D0')
            if (destination != second_destination
                    or not rva + 15 <= destination <= function[1] - len(continuation)
                    or destination_off is None
                    or data[destination_off:destination_off + len(continuation)] != continuation):
                fail(name, 'Analysis branches do not rejoin at the expected forward continuation')
                continue
        if name == 'OpusSdp_StereoValueBypass_Jmp2':
            context_start = off - reference['target_offset']
            presence = data[context_start + 8:context_start + 10]
            cleanup_off = off + 11
            present_skip = context_start + 10 + struct.unpack_from('b', data, context_start + 9)[0]
            length_skip = context_start + 29 + struct.unpack_from('b', data, context_start + 28)[0]
            inline_target = context_start + 35 + struct.unpack_from('b', data, context_start + 34)[0]
            cleanup_skip = context_start + 60 + struct.unpack_from('b', data, context_start + 59)[0]
            if (presence[:1] != b'\x75' or data[cleanup_off:cleanup_off + 4] != bytes.fromhex('48 83 F8 10')
                    or length_skip != cleanup_off or inline_target != off or present_skip != cleanup_skip
                    or not cleanup_off + 4 < present_skip
                    or _pe_file_off_to_rva(present_skip + 1, sections) is None
                    or _pe_file_off_to_rva(present_skip + 1, sections) >= function[1]
                    or data[present_skip:present_skip + 2] != bytes.fromhex('89 E8')):
                fail(name, 'Stereo optional-presence/cleanup branch targets are not intact')
                continue
        current = data[off:off + length]
        if current not in acceptable:
            fail(name, 'Context matched but original/replacement instruction bytes differ: '
                 + current.hex(' ').upper())
            continue
        site['state'] = 'original' if current == expected else 'already_patched'
        result[name] = rva
        tiers[name] = 'signature(unique-context)'
        patches.append(site)
        label = 'PASS'
        print(f'  [{label}] {name} = 0x{rva:08X} ({site["state"]})')
    previous_end = -1
    for site in sorted(patches, key=lambda item: item['file_offset']):
        if site['file_offset'] < previous_end:
            fail(site['name'], 'Resolved patch spans overlap')
        previous_end = max(previous_end, site['file_offset'] + site['length'])
    # Normalize only recognized patch spans. All other bytes belong to this
    # scanned build, so a successful update gets its own original hash and size.
    # The patcher still rejects any different binary until it too is scanned.
    normalized = bytearray(data)
    for site in patches:
        off = site['file_offset']
        normalized[off:off + site['length']] = bytes.fromhex(site['expected_original'])
    stock_hash = hashlib.sha256(normalized).hexdigest()
    reference_match = stock_hash == _MODERN_PROFILE['source_sha256']
    profile_id = (_MODERN_PROFILE['id'] if reference_match
                  else 'discord-windows-x64-sha256-' + stock_hash[:16])
    if hashlib.sha256(data).hexdigest() in _PREVIOUS_FULL_PROFILE_SHA256:
        fail('_upgrade', 'Previous full patch profile detected. Restore stock with the v23 patcher before using the v24 test profile; patcher export is blocked.')
    complete = not errors and len(patches) == len(_MODERN_PROFILE['sites'])
    manifest = {
        'schema': _MODERN_SCHEMA, 'tool': 'discord_voice_node_offset_finder',
        'version': VERSION, 'profile': profile_id,
        'target_bitrate_bps': TARGET_BITRATE_BPS,
        'bitrate_mode': BITRATE_MODE,
        'template_profile': _MODERN_PROFILE['id'], 'reference_identity_match': reference_match,
        'validation': 'unique-contexts-instruction-bytes-and-runtime-function-bounds',
        'format': 'pe', 'arch': 'x86_64', 'image_base': hex(base), 'file_size': len(data),
        'md5': hashlib.md5(data).hexdigest(), 'sha256': hashlib.sha256(data).hexdigest(),
        'original_sha256': stock_hash, 'original_md5': hashlib.md5(normalized).hexdigest(),
        'normalized_sha256': stock_hash, 'complete': complete,
        'total_found': len(patches), 'total_expected': len(_MODERN_PROFILE['sites']),
        'expected_active_patches': len(CURRENT_ACTIVE_PATCH_NAMES),
        'active_offsets': {p['name']: p['rva'] for p in patches if p['name'] in CURRENT_ACTIVE_PATCH_NAMES},
        'total_active_patches': len(patches),
        'offsets': {name: hex(rva) for name, rva in result.items()},
        'resolution_tiers': tiers, 'patches': patches, 'diagnostics': diagnostics,
        'missing': list(dict.fromkeys(name for name, _ in errors)), 'errors': errors,
        'default_gain': 1,
    }
    _modern_patch_detection(data, manifest)
    info['modern_manifest'] = manifest
    return result, errors, adj, tiers


def discover_offsets(data, bin_info, verbose=True):
    global _ACTIVE_MODERN_MANIFEST
    if not _modern_probe(data,bin_info):
        raise ValueError('This finder supports Windows x64 PE voice nodes.')
    with contextlib.nullcontext() if verbose else contextlib.redirect_stdout(io.StringIO()):
        result = _modern_resolve(data,bin_info)
    _ACTIVE_MODERN_MANIFEST = bin_info['modern_manifest']
    return result

def count_patcher_offsets_found(results,patcher_names=None):
    names = patcher_names or CURRENT_ACTIVE_PATCH_NAMES
    return sum(name in results for name in names),len(names)

def format_json(results,bin_info,file_path,file_size,adj,tiers_used,**kwargs):
    return _modern_manifest_document(bin_info['modern_manifest'],file_path)

def format_windows_patcher_block(results,bin_info,file_path,file_size,discord_app_version=None,patcher_path=None):
    manifest = bin_info['modern_manifest']
    version = discord_app_version or manifest.get('discord_app_version')
    if not version:
        match = re.search(r'(\d+\.\d+\.\d+)$',manifest['profile'])
        version = match.group(1) if match else None
    if patcher_path and manifest['complete']:
        entries = _read_profile_bank(Path(patcher_path).read_text(encoding='utf-8-sig'))
        return _profile_bank_powershell_block(_merge_profile_bank(entries, manifest, file_path, version))
    return _modern_powershell_block(manifest,file_path,version)

def format_windows_debug_mode(results=None):
    return '\n'.join(f'{name} = 0x{results[name]:08X}' for name in CURRENT_ACTIVE_PATCH_NAMES if results and name in results)

def find_discord_node():
    local = os.environ.get('LOCALAPPDATA')
    if sys.platform != 'win32' or not local:
        return None
    root = Path(local)
    for client in ('Discord','DiscordPTB','DiscordCanary','DiscordDevelopment'):
        apps = sorted((root/client).glob('app-*'),
                      key=lambda app: _app_dir_semver_from_name(app.name)[1], reverse=True)
        for app in apps:
            for node in sorted(app.glob('modules/discord_voice*/discord_voice/discord_voice.node')):
                if node.is_file():
                    return node
    return None

def main():
    parser=argparse.ArgumentParser(description=__doc__,
        epilog='Launch without arguments (or with --gui) for the GUI. Use --cli for an automatic console scan.')
    parser.add_argument('--cli', action='store_true', help='Use the console, including automatic node detection')
    parser.add_argument('node',nargs='?');parser.add_argument('--json',action='store_true')
    parser.add_argument('--quiet','-q',action='store_true');parser.add_argument('--verbose','-v',action='store_true')
    parser.add_argument('--export');parser.add_argument('--update-patcher');parser.add_argument('--discord-version')
    args=parser.parse_args();path=Path(args.node) if args.node else find_discord_node()
    if path is None:parser.error('Select a discord_voice.node file.')
    try:
        export_path = (_check_report_destination(args.export, path, args.update_patcher, __file__)
                       if args.export else None)
        data=path.read_bytes();info=detect_binary_format(data)
        discover_offsets(data,info,verbose=args.verbose and not(args.json or args.quiet))
        manifest=info['modern_manifest'];version,_=resolve_discord_app_version(path,data,info,args.discord_version)
        update=None
        if args.update_patcher:
            try:update=update_patcher_script(manifest,args.update_patcher,path,version)
            except Exception as error:update={'status':'failed','error':str(error)}
        document=dict(manifest)
        if update:document['patcher_update']=update
        rendered=_modern_manifest_document(document,path,version)
        if export_path:export_path.write_text(rendered,encoding='utf-8')
        if args.json:print(rendered)
        elif not args.quiet:
            print('Node status: '+_modern_patch_status_text(manifest))
            print(f"Active offsets: {manifest['total_found']}/{manifest['total_expected']}")
            if not manifest['complete']:
                print('Offset scan incomplete; no patcher profile exported.')
                for name,reason in manifest['errors']:print(f'[FAIL] {name}: {reason}')
            else:
                if not manifest['reference_identity_match']:
                    print('New build: known instruction contexts matched. Audio behavior still needs testing.')
                if not args.export and not args.update_patcher:
                    print(format_windows_patcher_block({},info,path,len(data),version))
            if update:print('Patcher: '+update['status']+(' - '+update['error'] if 'error' in update else ''))
            if args.export:print('JSON saved: '+args.export)
        return 0 if manifest['complete'] and (not update or update['status']!='failed') else 1
    except (OSError,ValueError) as error:
        print(str(error),file=sys.stderr);return 1

_EMBEDDED_GUI = None


def _load_embedded_gui():
    """Load the original GUI lazily; command-line scans do not require Tk."""
    global _EMBEDDED_GUI
    if _EMBEDDED_GUI is not None:
        return _EMBEDDED_GUI
    from types import SimpleNamespace
    # The functions retain the engine's globals; GUI VERSION remains 2.3.0.
    embedded_engine = SimpleNamespace(**globals())

    import os
    import sys
    import re
    import hashlib
    import threading
    import queue
    import json
    from pathlib import Path
    import importlib.util
    import io

    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, scrolledtext
    except ImportError:  # pragma: no cover
        tk = None  # type: ignore[assignment, misc]
        ttk = filedialog = scrolledtext = None  # type: ignore[assignment]

    sys.dont_write_bytecode = True

    VERSION = "2.3.0"
    SCRIPT_DIR = Path(__file__).resolve().parent
    DEBUG_MODE = os.environ.get("OFFSET_FINDER_DEBUG", "").lower() in ("1", "true", "yes") or "--debug" in sys.argv


    def _hub_scripts_cache_dir() -> Path | None:
        """If Stereo Hub synced the finder, it may live here (same layout as discord_stereo_hub_DEV.hub_scripts_dir)."""
        try:
            if sys.platform == "win32":
                base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
                p = Path(base) / "DiscordStereoHub" / "scripts"
            else:
                p = Path.home() / ".cache" / "DiscordStereoHub" / "scripts"
            return p if p.is_dir() else None
        except Exception:
            return None


    def _finder_script_search_dirs() -> list[Path]:
        """Prefer OFFSET FINDER/LATEST; also Stereo Hub cache when manifest synced the .py there."""
        dirs = [SCRIPT_DIR]
        hub_scripts = _hub_scripts_cache_dir()
        if hub_scripts and hub_scripts != SCRIPT_DIR:
            dirs.append(hub_scripts)
        return dirs



    THEME = {
        "BG": "#1e1e1e",
        "BG_LIGHT": "#2d2d2d",
        "BG_INPUT": "#1a1a1a",
        "FG": "#e0e0e0",
        "FG_DIM": "#888888",
        "FG_ACCENT": "#ffffff",
        "BORDER": "#3a3a3a",
        "GREEN": "#4caf50",
        "GREEN_HOVER": "#66bb6a",
        "BLUE": "#2196f3",
        "BLUE_HOVER": "#42a5f5",
        "ORANGE": "#ff9800",
        "GRAY_BTN": "#555555",
        "GRAY_HOVER": "#666666",
        "RED": "#f44336",
        "YELLOW": "#fdd835",
        "CYAN": "#4dd0e1",
        "SELECT_BG": "#0d47a1",
    }

    BG = THEME["BG"]
    BG_LIGHT = THEME["BG_LIGHT"]
    BG_INPUT = THEME["BG_INPUT"]
    FG = THEME["FG"]
    FG_DIM = THEME["FG_DIM"]
    FG_ACCENT = THEME["FG_ACCENT"]
    BORDER = THEME["BORDER"]
    GREEN = THEME["GREEN"]
    GREEN_HOVER = THEME["GREEN_HOVER"]
    BLUE = THEME["BLUE"]
    BLUE_HOVER = THEME["BLUE_HOVER"]
    ORANGE = THEME["ORANGE"]
    GRAY_BTN = THEME["GRAY_BTN"]
    GRAY_HOVER = THEME["GRAY_HOVER"]
    RED = THEME["RED"]
    YELLOW = THEME["YELLOW"]
    CYAN = THEME["CYAN"]
    SELECT_BG = THEME["SELECT_BG"]



    def _ascii_safe(s: str | bytes) -> str:
        """ASCII-only text for clipboard / patcher blocks."""
        if not s:
            return ""
        if isinstance(s, bytes):
            s = s.decode("utf-8", errors="replace")
        return s.encode("ascii", errors="replace").decode("ascii")


    class OffsetFinderGUI:
        def __init__(self, root):
            self.root = root
            self.root.title("Offset Finder" + (" [DEBUG]" if DEBUG_MODE else ""))
            self.root.configure(bg=BG)
            self.root.resizable(True, True)
            self.root.minsize(690, 700)
            self.root.geometry("760x850")

            try:
                self.root.iconbitmap(default="")
            except Exception:
                pass

            self.finder_module = None
            self.running = False
            self._closed = False
            self._ui_queue = queue.Queue()
            self._source_path = None
            self._scan_generation = 0
            self.file_path = tk.StringVar()
            settings = self._read_settings()
            saved_patcher = settings.get('patcher_path', '')
            self.patcher_path = tk.StringVar(value=saved_patcher if isinstance(saved_patcher, str) else '')
            self.auto_update_patcher = tk.BooleanVar(value=settings.get('auto_update_patcher', True) is True)
            self.os_var = tk.StringVar(value="Auto-Detect")
            self.status_var = tk.StringVar(value="Ready")
            self.last_output = ""
            self.last_windows_block = ""
            self.last_linux_block = ""
            self.last_macos_block = ""

            self.root.protocol("WM_DELETE_WINDOW", self._on_close)

            self._build_ui()
            self.file_path.trace_add('write', self._input_changed)
            self.copy_block_btn.configure(state='disabled')
            self._pump_job = self.root.after(0, self._drain_ui_queue)
            self._load_finder()

        def _build_ui(self):
            title_frame = tk.Frame(self.root, bg=BG)
            title_frame.pack(fill="x", padx=16, pady=(14, 0))

            tk.Label(title_frame, text="Offset Finder", font=("Segoe UI", 20, "bold"),
                     bg=BG, fg=FG_ACCENT).pack()
            tk.Label(title_frame, text="Made by: Oracle | Shaun | Hallow | Ascend | Sikimzo | Cypher | Crue | Geeko",
                     font=("Segoe UI", 8), bg=BG, fg=FG_DIM).pack()
            tk.Label(title_frame, text=f"v{VERSION}",
                     font=("Segoe UI", 8), bg=BG, fg=FG_DIM).pack()

            sel_frame = tk.LabelFrame(self.root, text=" Binary Selection ",
                                      font=("Segoe UI", 9, "bold"),
                                      bg=BG_LIGHT, fg=FG, bd=1, relief="groove",
                                      highlightbackground=BORDER, highlightthickness=1)
            sel_frame.pack(fill="x", padx=16, pady=(12, 0), ipady=4)

            os_row = tk.Frame(sel_frame, bg=BG_LIGHT)
            os_row.pack(fill="x", padx=10, pady=(8, 4))
            tk.Label(os_row, text="Detected OS:", font=("Segoe UI", 9),
                     bg=BG_LIGHT, fg=FG, width=10, anchor="w").pack(side="left")
            tk.Label(os_row, textvariable=self.os_var, font=("Segoe UI",9),
                     bg=BG_LIGHT,fg=FG).pack(side="left",padx=(4,0))
            tk.Label(os_row,text="(Windows x64 nodes supported)",font=("Segoe UI",8),
                     bg=BG_LIGHT,fg=FG_DIM).pack(side="left",padx=(8,0))

            file_row = tk.Frame(sel_frame, bg=BG_LIGHT)
            file_row.pack(fill="x", padx=10, pady=(4, 8))
            tk.Label(file_row, text="Node File:", font=("Segoe UI", 9),
                     bg=BG_LIGHT, fg=FG, width=10, anchor="w").pack(side="left")

            self.file_entry = tk.Entry(file_row, textvariable=self.file_path,
                                       font=("Consolas", 9), bg=BG_INPUT, fg=FG,
                                       insertbackground=FG, relief="flat", bd=0,
                                       highlightbackground=BORDER, highlightthickness=1)
            self.file_entry.pack(side="left", fill="x", expand=True, padx=(4, 6), ipady=3)

            self.browse_btn = tk.Button(file_row, text="Browse...",
                                        font=("Segoe UI", 9), bg=GRAY_BTN, fg=FG,
                                        activebackground=GRAY_HOVER, activeforeground=FG,
                                        relief="flat", bd=0, padx=12, pady=2,
                                        cursor="hand2", command=self._browse_file)
            self.browse_btn.pack(side="right")

            opt_frame = tk.LabelFrame(self.root, text=" Options ",
                                      font=("Segoe UI", 9, "bold"),
                                      bg=BG_LIGHT, fg=FG, bd=1, relief="groove",
                                      highlightbackground=BORDER, highlightthickness=1)
            opt_frame.pack(fill="x", padx=16, pady=(10, 0), ipady=4)

            self.save_json = tk.BooleanVar(value=True)
            self.verbose = tk.BooleanVar(value=False)

            opts_inner = tk.Frame(opt_frame, bg=BG_LIGHT)
            opts_inner.pack(fill="x", padx=10, pady=(6, 6))

            left_opts = tk.Frame(opts_inner, bg=BG_LIGHT)
            left_opts.pack(side="left", anchor="nw")
            right_opts = tk.Frame(opts_inner, bg=BG_LIGHT)
            right_opts.pack(side="left", anchor="nw", padx=(30, 0))

            for var, text, parent in [
                (self.save_json, "Save JSON offsets file", left_opts),
                (self.verbose, "Verbose output", right_opts),
            ]:
                cb = tk.Checkbutton(parent, text=text, variable=var,
                                    font=("Segoe UI", 9), bg=BG_LIGHT, fg=FG,
                                    selectcolor=BG_INPUT, activebackground=BG_LIGHT,
                                    activeforeground=FG, highlightthickness=0,
                                    bd=0, anchor="w")
                cb.pack(anchor="w", pady=1)

            patcher_frame = tk.LabelFrame(self.root, text=" Patcher update ",
                                          font=("Segoe UI", 9, "bold"), bg=BG_LIGHT,
                                          fg=FG, bd=1, relief="groove")
            patcher_frame.pack(fill="x", padx=16, pady=(10, 0))
            self.auto_update_chk = tk.Checkbutton(
                patcher_frame, text="Add verified builds to the patcher (keeps other builds)",
                variable=self.auto_update_patcher, command=self._save_settings,
                font=("Segoe UI", 9), bg=BG_LIGHT, fg=FG, selectcolor=BG_INPUT,
                activebackground=BG_LIGHT, activeforeground=FG, bd=0)
            self.auto_update_chk.pack(anchor="w", padx=10, pady=(6, 3))
            patcher_row = tk.Frame(patcher_frame, bg=BG_LIGHT)
            patcher_row.pack(fill="x", padx=10, pady=(0, 7))
            tk.Label(patcher_row, text="Patcher:", font=("Segoe UI", 9),
                     bg=BG_LIGHT, fg=FG).pack(side="left", padx=(0, 6))
            self.patcher_entry = tk.Entry(patcher_row, textvariable=self.patcher_path,
                                         font=("Consolas", 9), bg=BG_INPUT, fg=FG,
                                         insertbackground=FG, relief="flat")
            self.patcher_entry.pack(side="left", fill="x", expand=True, ipady=3)
            self.patcher_browse_btn = tk.Button(
                patcher_row, text="Browse...", command=self._choose_patcher,
                font=("Segoe UI", 9), bg=GRAY_BTN, fg=FG, relief="flat", padx=12)
            self.patcher_browse_btn.pack(side="right", padx=(6, 0))

            btn_frame = tk.Frame(self.root, bg=BG)
            btn_frame.pack(side="bottom", fill="x", padx=16, pady=(8, 14))

            status_frame = tk.Frame(self.root, bg=BG_LIGHT, height=24)
            status_frame.pack(side="bottom", fill="x", padx=16, pady=(6, 0))
            self.status_label = tk.Label(status_frame, textvariable=self.status_var,
                                         font=("Segoe UI", 8), bg=BG_LIGHT, fg=FG_DIM,
                                         anchor="w")
            self.status_label.pack(fill="x", padx=6, pady=2)

            output_frame = tk.Frame(self.root, bg=BG)
            output_frame.pack(fill="both", expand=True, padx=16, pady=(10, 0))

            self.output = scrolledtext.ScrolledText(
                output_frame, font=("Consolas", 9), bg=BG_INPUT, fg=FG,
                insertbackground=FG, relief="flat", bd=0, wrap="word",
                highlightbackground=BORDER, highlightthickness=1, state="disabled")
            self.output.pack(fill="both", expand=True)

            self.output.tag_config("pass", foreground=GREEN)
            self.output.tag_config("fail", foreground=RED)
            self.output.tag_config("warn", foreground=YELLOW)
            self.output.tag_config("info", foreground=CYAN)
            self.output.tag_config("header", foreground=ORANGE, font=("Consolas", 9, "bold"))
            self.output.tag_config("success", foreground=GREEN, font=("Consolas", 10, "bold"))

            self.run_btn = self._make_button(btn_frame, "Find Offsets", GREEN, GREEN_HOVER,
                                             self._run_finder)
            self.run_btn.pack(side="left", padx=(0, 6))

            self.copy_btn = self._make_button(btn_frame, "Copy Output", BLUE, BLUE_HOVER,
                                              self._copy_output)
            self.copy_btn.pack(side="left", padx=(0, 6))

            self.copy_block_btn = self._make_button(btn_frame, "Copy Offsets", BLUE, BLUE_HOVER,
                                                    self._copy_block)
            self.copy_block_btn.pack(side="left", padx=(0, 6))

            self.save_btn = self._make_button(btn_frame, "Save Results", GRAY_BTN, GRAY_HOVER,
                                              self._save_results)
            self.save_btn.pack(side="left", padx=(0, 6))

            self.clear_btn = self._make_button(btn_frame, "Clear", GRAY_BTN, GRAY_HOVER,
                                               self._clear_output)
            self.clear_btn.pack(side="left")

            self._append_output("  Choose a discord_voice.node file with Browse to begin.\n", "info")

        @staticmethod
        def _settings_path():
            return SCRIPT_DIR / 'offset_finder_settings.json'

        @classmethod
        def _read_settings(cls):
            try:
                value = json.loads(cls._settings_path().read_text(encoding='utf-8'))
                return value if isinstance(value, dict) else {}
            except (OSError, ValueError):
                return {}

        @staticmethod
        def _find_patcher(contract):
            for candidate in (SCRIPT_DIR / 'Discord_voice_node_patcher.ps1',
                              SCRIPT_DIR.parent / 'Windows' / 'Discord_voice_node_patcher.ps1'):
                try:
                    source = candidate.read_text(encoding='utf-8-sig')
                    matches = re.findall(r"(?m)^\$Script:ProfileContract\s*=\s*'([^']+)'\s*\r?$", source)
                    if matches == [contract]:
                        return str(candidate.resolve())
                except (OSError, UnicodeError):
                    continue
            return ''

        def _save_settings(self):
            try:
                self._settings_path().write_text(json.dumps({
                    'patcher_path': self.patcher_path.get().strip(),
                    'auto_update_patcher': bool(self.auto_update_patcher.get()),
                }, indent=2), encoding='utf-8')
            except OSError:
                self.status_var.set('Settings could not be saved; current choices still apply')

        def _choose_patcher(self):
            if self.running:
                return
            chosen = filedialog.askopenfilename(
                title='Select Discord_voice_node_patcher.ps1 (v24.1+)',
                filetypes=[('PowerShell patcher', '*.ps1')])
            if chosen:
                self.patcher_path.set(chosen)
                self._save_settings()

        def _make_button(self, parent, text, bg_color, hover_color, command):
            btn = tk.Button(parent, text=text, font=("Segoe UI", 9, "bold"),
                            bg=bg_color, fg="#ffffff",
                            activebackground=hover_color, activeforeground="#ffffff",
                            relief="flat", bd=0, padx=16, pady=6,
                            cursor="hand2", command=command)
            btn.bind("<Enter>", lambda e, b=btn, c=hover_color: b.configure(bg=c))
            btn.bind("<Leave>", lambda e, b=btn, c=bg_color: b.configure(bg=c))
            return btn

        def _browse_file(self):
            if self.running:
                return
            path = filedialog.askopenfilename(
                title="Select discord_voice.node",
                filetypes=[
                    ("Node binary", "*.node"),
                    ("All files", "*.*"),
                ])
            if path:
                self.file_path.set(path)
                self._auto_detect_os(path)
                self._run_finder()

        def _auto_detect_os(self, path):
            try:
                with open(path, "rb") as f:
                    magic = f.read(4)
                if magic[:2] == b"MZ":
                    self.os_var.set("Windows")
                elif magic == b"\x7fELF":
                    self.os_var.set("Linux")
                elif magic in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                               b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
                               b"\xca\xfe\xba\xbe"):
                    self.os_var.set("macOS")
                else:
                    self.os_var.set("Auto-Detect")
            except Exception:
                pass

        def _on_drop(self, event):
            if self.running:
                return
            paths = self.root.tk.splitlist(event.data)
            if len(paths) != 1:
                self.status_var.set('Drop one node file at a time')
                return
            path = paths[0]
            self.file_path.set(path)
            self._auto_detect_os(path)
            self._run_finder()

        def _invalidate_copy(self):
            self.last_windows_block = self.last_linux_block = self.last_macos_block = ''
            self.copy_block_btn.configure(state='disabled')

        def _input_changed(self, *_):
            self._scan_generation += 1
            self._invalidate_copy()
            if not self.running:
                self.status_var.set('Input changed — run Find Offsets')

        def _clear_output(self):
            if self.running:
                return
            self._invalidate_copy()
            self.output.configure(state="normal")
            self.output.delete("1.0", "end")
            self.output.configure(state="disabled")
            self.last_output = ""
            self.last_windows_block = ""
            self.last_linux_block = ""
            self.last_macos_block = ""

        def _copy_output(self):
            text = self.last_output.strip()
            if not text:
                text = self.output.get("1.0", "end").strip()
            if text:
                self.root.clipboard_clear()
                self.root.clipboard_append(_ascii_safe(text))
                self.status_var.set("Output copied to clipboard")

        def _copy_block(self):
            if self.running:
                self.status_var.set("Wait for the current scan to finish")
                return
            block = (self.last_windows_block or self.last_linux_block or self.last_macos_block or "").strip()
            if not block:
                self.status_var.set("No patcher block to copy (run Find Offsets first)")
                return
            self.root.clipboard_clear()
            self.root.clipboard_append(_ascii_safe(block))
            if self.last_macos_block and block == self.last_macos_block.strip():
                self.status_var.set("macOS block copied — paste into MacOS_ARM64_Patcher.py region")
            elif self.last_linux_block and block == self.last_linux_block.strip():
                self.status_var.set("Linux block copied — paste into discord_voice_patcher_linux.sh")
            elif self.last_windows_block and block == self.last_windows_block.strip():
                self.status_var.set("Build bank copied — paste into the v24.1+ patcher")
            else:
                self.status_var.set("Block copied (paste into patcher)")

        def _save_results(self):
            text = self.last_output.strip()
            if not text:
                text = self.output.get("1.0", "end").strip()
            if not text:
                self.status_var.set("Nothing to save")
                return
            block = self.last_windows_block or self.last_linux_block or self.last_macos_block
            if block and block.strip() not in text:
                text += "\n\n" + block.strip()
            path = filedialog.asksaveasfilename(
                title="Save Results",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
            if path:
                try:
                    destination = Path(path).resolve()
                    protected = [Path(__file__).resolve()]
                    for value in (self.file_path.get().strip(), self.patcher_path.get().strip(),
                                  getattr(self, '_source_path', ''),
                                  getattr(self.finder_module, '__file__', '')):
                        if value:
                            protected.append(Path(value).resolve())
                    for source in protected:
                        if destination == source or (destination.exists() and source.exists()
                                                      and os.path.samefile(destination, source)):
                            raise ValueError('Choose a separate report file; source files cannot be overwritten.')
                    destination.write_text(text, encoding='utf-8')
                    self.status_var.set(f"Saved to {path}")
                except (OSError, ValueError) as error:
                    self.status_var.set(f'Save failed: {error}')

        def _load_finder(self):
            # The same GUI uses the engine already loaded from this single file.
            self.finder_module = embedded_engine
            if not self.patcher_path.get().strip():
                self.patcher_path.set(self._find_patcher(embedded_engine._PATCHER_PROFILE_CONTRACT))
            finder_path = Path(embedded_engine.__file__)
            ver = embedded_engine.VERSION
            self.status_var.set(f"Loaded: {finder_path.name} (v{ver}) from {finder_path.parent.name}/")

        def _run_finder(self):
            if self.running:
                return

            self._clear_output()
            path = self.file_path.get().strip()
            if not path:
                self._append_output("  [ERROR] No file selected. Browse for a discord_voice.node file.\n", "fail")
                return
            if not os.path.isfile(path):
                self._append_output(f"  [ERROR] File not found: {path}\n", "fail")
                return

            self._load_finder()
            if self.finder_module is None:
                self._append_output("  [ERROR] Offset finder script not loaded.\n", "fail")
                self._append_output(
                    "  Put discord_voice_node_offset_finder_v5.py in OFFSET FINDER/LATEST or sync it via Stereo Hub / manifest.\n",
                    "info",
                )
                return

            try:
                fsize = os.path.getsize(path)
            except OSError as error:
                self._append_output(f"  [ERROR] {error}\n", "fail")
                return
            update_target = None
            if self.auto_update_patcher.get():
                try:
                    with open(path, 'rb') as stream:
                        is_windows = stream.read(2) == b'MZ'
                except OSError as error:
                    self._append_output(f"  [ERROR] {error}\n", "fail")
                    return
                if is_windows:
                    update_target = self.patcher_path.get().strip()
                    if not update_target or not Path(update_target).is_file():
                        self._append_output("  No patcher selected. Scanning offsets only; choose a compatible patcher to update it.\n", "warn")
                        update_target = None
                    else:
                        self._save_settings()
            self._auto_detect_os(path)
            self._source_path = os.path.abspath(path)
            verbose, save_json = self.verbose.get(), self.save_json.get()
            self.running = True
            self.run_btn.configure(state="disabled", bg=GRAY_BTN)
            for widget in (self.file_entry, self.browse_btn, self.clear_btn, self.save_btn,
                           self.patcher_entry, self.patcher_browse_btn, self.auto_update_chk):
                widget.configure(state="disabled")
            fname = os.path.basename(path)
            self._append_output(f"  File: {fname}\n", "header")
            self._append_output(f"  Size: {fsize:,} bytes | OS: {self.os_var.get()}\n", "info")
            self._append_output(f"  {'-' * 55}\n\n", "info")

            profile_target = self.patcher_path.get().strip()
            thread = threading.Thread(target=self._run_finder_thread, args=(path, verbose, save_json, update_target, self._scan_generation, profile_target), daemon=True)
            thread.start()

        def _save_scan_json(self, mod, path, data, bin_info, results, adj, tiers_used):
            try:
                results_dir = SCRIPT_DIR / 'results'
                results_dir.mkdir(exist_ok=True)
                source_id = hashlib.sha256(data).hexdigest()[:12]
                json_path = results_dir / (Path(path).stem + '.' + source_id + '.offsets.json')
                json_text = mod.format_json(results, bin_info, path, len(data), adj, tiers_used)
                json_path.write_text(json_text, encoding='utf-8')
                self._append_output_safe(f'\n  JSON saved: {json_path}\n', 'info')
            except Exception as error:
                self._append_output_safe(f'\n  JSON save error: {error}\n', 'warn')

        def _run_finder_thread(self, path, verbose, save_json, update_target, scan_generation, profile_target=None):
            # Tk variables are captured by _run_finder on the main thread.
            block = ''
            try:
                mod = self.finder_module
                data = Path(path).read_bytes()
                info = mod.detect_binary_format(data)
                capture = io.StringIO()
                from contextlib import redirect_stdout
                with redirect_stdout(capture):
                    results, errors, adj, tiers = mod.discover_offsets(data, info, verbose=verbose)
                if verbose:
                    self._append_output_safe(capture.getvalue(), 'info')
                m = info['modern_manifest']
                m['discord_channel'] = mod.resolve_discord_channel(path)
                version, version_source = mod.resolve_discord_app_version(path, data, info)
                m['discord_app_version_source'] = version_source
                if version != 'unspecified':
                    m['discord_app_version'] = version
                self._append_output_safe(f"  Build: {m['discord_channel']} | app {version}\n", 'info')
                state = mod._modern_patch_status_text(m)
                self._append_output_safe('  Node status: ' + state + '\n', 'info')
                self._append_output_safe(f"  Active offsets: {m['total_found']}/{m['total_expected']}\n", 'info')
                if self._closed or scan_generation != self._scan_generation:
                    return
                if not m['complete']:
                    self._append_output_safe('  Offset scan incomplete - patcher unchanged.\n', 'fail')
                    for name, reason in errors:
                        self._append_output_safe(f'  {name}: {reason}\n', 'fail')
                    if save_json:
                        self._save_scan_json(mod, path, data, info, results, adj, tiers)
                    self._set_status_safe(state + ' | Offset scan incomplete')
                    return
                if hashlib.sha256(Path(path).read_bytes()).hexdigest() != m['sha256']:
                    raise ValueError('Node changed during the scan; run Find Offsets again.')
                block = mod.format_windows_patcher_block(results, info, path, len(data)) or ''
                if not update_target and profile_target and Path(profile_target).is_file():
                    try:
                        block = mod.format_windows_patcher_block(results, info, path, len(data), patcher_path=profile_target) or ''
                    except Exception as error:
                        block = ''
                        self._append_output_safe('  Copy bank unavailable: ' + str(error) + '\n', 'warn')
                if verbose:
                    self._append_output_safe(mod.format_windows_debug_mode(results) + '\n', 'info')
                if save_json:
                    self._save_scan_json(mod, path, data, info, results, adj, tiers)
                if update_target:
                    try:
                        if self._closed or scan_generation != self._scan_generation:
                            block = ''
                            return
                        with redirect_stdout(io.StringIO()):
                            update = mod.update_patcher_script(m, update_target, path)
                        block = update['profile_block']
                        message = ('Patcher build bank updated and verified.' if update['status'] == 'updated'
                                   else 'Patcher already includes this build.')
                        message += f" {update['profile_count']} build profile(s) available."
                        self._append_output_safe('  ' + message + '\n', 'success')
                    except Exception as error:
                        self._append_output_safe('  Patcher update failed: ' + str(error) + '\n', 'fail')
                        self._set_status_safe(state + ' | Patcher update failed')
                        return
                total = m['total_expected']
                self._append_output_safe(f'  Ready. All {total} active offsets validated.\n', 'success')
                if not m.get('reference_identity_match'):
                    self._append_output_safe(
                        '  New build: known instruction contexts matched. Audio behavior still needs testing.\n', 'warn')
                self._set_status_safe(state + f' | {total}/{total} active offsets')
            except Exception as error:
                block = ''
                self._append_output_safe('  [ERROR] ' + str(error) + '\n', 'fail')
                self._set_status_safe('Error: ' + str(error))
            finally:
                self._post_ui(self._finish_run, scan_generation, block)

        def _finish_run(self, scan_generation, block):
            self.running = False
            self.run_btn.configure(state="normal", bg=GREEN)
            for widget in (self.file_entry, self.browse_btn, self.clear_btn, self.save_btn,
                           self.patcher_entry, self.patcher_browse_btn, self.auto_update_chk):
                widget.configure(state="normal")
            if (scan_generation != self._scan_generation
                    or self._source_path and os.path.abspath(self.file_path.get().strip()) != self._source_path):
                self._invalidate_copy()
                self.status_var.set('Input changed — run Find Offsets')
            else:
                self.last_windows_block = block
                self.copy_block_btn.configure(state='normal' if block else 'disabled')

        def _append_output(self, text, tag=None):
            self.output.configure(state="normal")
            if tag:
                self.output.insert("end", text, tag)
            else:
                self.output.insert("end", text)
            self.output.see("end")
            self.output.configure(state="disabled")
            self.last_output += text

        def _append_output_safe(self, text, tag=None):
            self._post_ui(self._append_output, text, tag)

        def _set_status_safe(self, text):
            self._post_ui(self.status_var.set, text)

        def _post_ui(self, callback, *args):
            if not self._closed:
                self._ui_queue.put((callback, args))

        def _drain_ui_queue(self):
            if self._closed:
                return
            try:
                while True:
                    callback, args = self._ui_queue.get_nowait()
                    try:
                        callback(*args)
                    except Exception:
                        self.root.report_callback_exception(*sys.exc_info())
            except queue.Empty:
                pass
            self._pump_job = self.root.after(40, self._drain_ui_queue)

        def _on_close(self):
            self._closed = True
            if self._pump_job is not None:
                self.root.after_cancel(self._pump_job)
            self.root.destroy()



    def main():
        if tk is None:
            print("Offset Finder requires Tkinter.", file=sys.stderr)
            if sys.platform.startswith("linux"):
                print("  sudo apt install python3-tk", file=sys.stderr)
            elif sys.platform == "darwin":
                print("  Use python.org Python or: brew install python-tk", file=sys.stderr)
            else:
                print("  Reinstall Python with Tcl/Tk.", file=sys.stderr)
            sys.exit(1)

        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        root = tk.Tk()

        try:
            from ctypes import windll, c_int, byref
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            windll.dwmapi.DwmSetWindowAttribute(
                int(root.wm_frame(), 16) if isinstance(root.wm_frame(), str)
                else root.wm_frame(),
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                byref(c_int(1)), 4)
        except Exception:
            pass

        root.option_add("*TCombobox*Listbox.background", BG_INPUT)
        root.option_add("*TCombobox*Listbox.foreground", FG)
        root.option_add("*TCombobox*Listbox.selectBackground", SELECT_BG)
        root.option_add("*TCombobox*Listbox.selectForeground", FG_ACCENT)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox",
                         fieldbackground=BG_INPUT, background=GRAY_BTN,
                         foreground=FG, arrowcolor=FG,
                         selectbackground=SELECT_BG, selectforeground=FG_ACCENT)
        style.map("TCombobox",
                  fieldbackground=[("readonly", BG_INPUT)],
                  selectbackground=[("readonly", SELECT_BG)])

        app = OffsetFinderGUI(root)
        root.mainloop()

    _EMBEDDED_GUI = SimpleNamespace(OffsetFinderGUI=OffsetFinderGUI, main=main,
                                    tk=tk, THEME=THEME, VERSION=VERSION)
    return _EMBEDDED_GUI


def _entry_point():
    # A direct launch opens the same GUI. All existing CLI flags still reach main.
    arguments = sys.argv[1:]
    if not arguments or all(arg in ('--gui', '--debug') for arg in arguments):
        _load_embedded_gui().main()
        return 0
    return main()


if __name__ == '__main__':
    sys.exit(_entry_point())
