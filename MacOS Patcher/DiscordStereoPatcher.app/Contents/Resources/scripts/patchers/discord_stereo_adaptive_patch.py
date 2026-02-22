#!/usr/bin/env python3
"""
Discord Stereo Adaptive Patcher
================================
Version-agnostic patcher: runs the offset finder on the current discord_voice.node,
then applies the same 384kbps stereo patches at the discovered offsets.
Use this after a Discord update when the hardcoded-offset patcher no longer matches.

Usage:
  python discord_stereo_adaptive_patch.py [path_to_discord_voice.node] [--check-only]
  If path is omitted, auto-detects Discord install.
  --check-only: Only detect whether the binary is PATCHED or UNPATCHED; do not modify.
  Both x86_64 and ARM64 slices are always patched (no Rosetta required).

Steps:
  1. Find discord_voice.node (arg or auto-detect)
  2. Run offset finder with --export to get offsets JSON
  3. Create backup in ~/Library/Caches/DiscordVoicePatcher/Backups
  4. Apply byte patches at discovered file offsets (384k patch bytes)
  5. Generate and compile injector with discovered HP/DC offsets
  6. Run injector, re-sign binary
"""

import sys
import os
import json
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

# Same backup dir as other patchers
CACHE_DIR = Path.home() / "Library" / "Caches" / "DiscordVoicePatcher"
BACKUP_DIR = CACHE_DIR / "Backups"
BUILD_DIR = CACHE_DIR / "build"
METADATA_FILE = CACHE_DIR / "patch_metadata.json"

# 384 kbps patch bytes by offset finder name (same logic as discord_stereo_patcher_gui)
PATCH_BYTES_BY_NAME = {
    "EmulateStereoSuccess1": "02",
    "EmulateStereoSuccess2": "EB",
    "CreateAudioFrameStereo": "4989C490",
    "AudioEncoderOpusConfigSetChannels": "02",
    "MonoDownmixer": "909090909090909090909090E9",
    "EmulateBitrateModified": "00DC05",
    "SetsBitrateBitrateValue": "00DC050000",
    "SetsBitrateBitwiseOr": "909090",
    "DuplicateEmulateBitrateModified": "00DC05",
    "HighPassFilter": "C3",
    "DownmixFunc": "C3",
    "AudioEncoderOpusConfigIsOk": "C3",
    "ThrowError": "C3",
    "EncoderConfigInit1": "00DC0500",
    "EncoderConfigInit2": "00DC0500",
}

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def _save_patch_metadata(node_path_str, x86_offsets, arm64_meta):
    """Save applied patch offsets so --check-only can verify without re-scanning."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "node_path": node_path_str,
        "x86_64": {name: {"file_offset": off, "patch_hex": PATCH_BYTES_BY_NAME[name]}
                   for name, off in x86_offsets.items() if name in PATCH_BYTES_BY_NAME},
        "arm64": arm64_meta,
    }
    try:
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except OSError:
        pass


def _load_patch_metadata(node_path_str):
    """Load saved metadata. Returns (x86_dict, arm64_list) or (None, None) if unavailable."""
    if not METADATA_FILE.exists():
        return None, None
    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("node_path") != node_path_str:
            return None, None
        return meta.get("x86_64"), meta.get("arm64")
    except (json.JSONDecodeError, OSError):
        return None, None


def _find_finder_script():
    """Locate the offset finder script. Checks multiple locations for bundled vs repo layout."""
    candidates = [
        REPO_ROOT / "finder" / "discord_voice_node_offset_finder_v5.py",
        SCRIPT_DIR / ".." / "finder" / "discord_voice_node_offset_finder_v5.py",
        SCRIPT_DIR.parent / "finder" / "discord_voice_node_offset_finder_v5.py",
    ]
    for c in candidates:
        if c.resolve().is_file():
            return c.resolve()
    return REPO_ROOT / "finder" / "discord_voice_node_offset_finder_v5.py"

FINDER_SCRIPT = _find_finder_script()


def find_discord_node():
    """Locate discord_voice.node under Application Support/discord."""
    base = Path.home() / "Library" / "Application Support" / "discord"
    if not base.exists():
        return None
    for node in base.rglob("discord_voice.node"):
        if node.is_file():
            return node
    return None


def run_offset_finder(node_path, export_path):
    """Run offset finder and write JSON to export_path. Returns (success, json_data or None)."""
    if not FINDER_SCRIPT.exists():
        return False, None
    # Finder expects: <node_path> [--export <export_path>]; first non-option is the binary path
    try:
        result = subprocess.run(
            [sys.executable, str(FINDER_SCRIPT), str(node_path), "--export", str(export_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode > 1:
            if result.stderr:
                print(result.stderr.strip(), file=sys.stderr)
            return False, None
    except subprocess.TimeoutExpired:
        print("Offset finder timed out.", file=sys.stderr)
        return False, None
    except subprocess.CalledProcessError as e:
        if e.stderr:
            print(e.stderr.strip(), file=sys.stderr)
        return False, None
    try:
        with open(export_path, "r", encoding="utf-8") as f:
            return True, json.load(f)
    except (json.JSONDecodeError, OSError):
        return False, None


def create_backup(node_path, name="Discord"):
    """Create timestamped backup; return path or None."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    clean = name.replace(" ", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"discord_voice.node.{clean}.{ts}.backup"
    try:
        shutil.copy2(node_path, backup_path)
        return str(backup_path)
    except OSError:
        return None


def get_patch_specs(export_data, node_path=None):
    """Build list of (name, file_offset, expected_original_hex, patch_hex) from export JSON.
    Prefers saved metadata (exact offsets from patching) over re-scanning the binary."""
    specs = []
    node_path_str = str(node_path) if node_path else None

    saved_x86, saved_arm64 = _load_patch_metadata(node_path_str) if node_path_str else (None, None)

    if saved_x86:
        for name, info in saved_x86.items():
            off = info.get("file_offset")
            patch_hex = info.get("patch_hex", "").replace(" ", "").lower()
            if off is not None and patch_hex:
                specs.append((name, off, None, patch_hex))
    else:
        patches = export_data.get("patches") or []
        file_offsets = export_data.get("file_offsets") or {}
        for p in patches:
            name = p.get("name")
            if name not in PATCH_BYTES_BY_NAME:
                continue
            off = p.get("file_offset")
            if off is None:
                off = file_offsets.get(name)
            if off is None:
                continue
            if isinstance(off, str):
                off = int(off, 16)
            expected = p.get("expected_original")
            if expected:
                expected = expected.replace(" ", "").lower()
            patch_hex = PATCH_BYTES_BY_NAME[name].replace(" ", "").lower()
            specs.append((name, off, expected, patch_hex))
        if not specs and file_offsets:
            for name, hex_bytes in PATCH_BYTES_BY_NAME.items():
                if name not in file_offsets:
                    continue
                off = file_offsets[name]
                if isinstance(off, str):
                    off = int(off, 16)
                specs.append((name, off, None, hex_bytes.replace(" ", "").lower()))

    if saved_arm64 and node_path and Path(node_path).is_file():
        raw = Path(node_path).read_bytes()
        arm64_start = _get_arm64_slice_offset(raw)
        if arm64_start is not None:
            for entry in saved_arm64:
                va = entry.get("va")
                if va is None:
                    continue
                file_off = arm64_start + va
                orig_hex = (entry.get("orig") or "").replace(" ", "").lower()
                patch_hex = (entry.get("patch") or "").replace(" ", "").lower()
                name = entry.get("name", "arm64_unknown")
                if orig_hex and patch_hex and len(orig_hex) == len(patch_hex):
                    specs.append((f"ARM64:{name}", file_off, orig_hex, patch_hex))
    else:
        stereo_patches = export_data.get("stereo_patches") or []
        arm64_sp = [p for p in stereo_patches if p.get("arch") == "arm64"]
        if arm64_sp and node_path and Path(node_path).is_file():
            raw = Path(node_path).read_bytes()
            current_arm64_start = _get_arm64_slice_offset(raw)
            shift = 0
            if current_arm64_start is not None:
                for p in arm64_sp:
                    fo = p.get("fat_offset")
                    va = p.get("va")
                    if fo is not None and va is not None:
                        original_start = fo - va
                        shift = current_arm64_start - original_start
                        break
            for p in arm64_sp:
                fo = p.get("fat_offset")
                if fo is None:
                    continue
                adjusted_fo = fo + shift
                orig_hex = (p.get("orig") or "").replace(" ", "").lower()
                patch_hex = (p.get("patch") or "").replace(" ", "").lower()
                name = p.get("name", "arm64_unknown")
                if orig_hex and patch_hex and len(orig_hex) == len(patch_hex):
                    specs.append((f"ARM64:{name}", adjusted_fo, orig_hex, patch_hex))

    return specs


def check_patch_status(node_path, patch_specs):
    """
    Read file at each patch site; compare to expected_original (unpatched) and patch bytes (patched).
    Returns (unpatched_count, patched_count, list of (name, status) where status in ('patched','unpatched','other').
    """
    data = node_path.read_bytes()
    unpatched = 0
    patched = 0
    details = []
    for name, file_offset, expected_hex, patch_hex in patch_specs:
        patch_bytes = bytes.fromhex(patch_hex)
        length = len(patch_bytes)
        if file_offset + length > len(data):
            details.append((name, "other"))
            continue
        current = data[file_offset : file_offset + length]
        current_hex = current.hex().lower()
        if current_hex == patch_hex:
            patched += 1
            details.append((name, "patched"))
        elif expected_hex and current_hex == expected_hex:
            unpatched += 1
            details.append((name, "unpatched"))
        else:
            details.append((name, "other"))
    return unpatched, patched, details


def _hex_str_to_bytes(s):
    """Convert hex string to bytes. Accepts space-separated ('01 02 03') or contiguous ('010203')."""
    s = (s or "").replace(" ", "").strip()
    if not s:
        return b""
    return bytes.fromhex(s)


def _get_arm64_slice_offset(data):
    """Read the FAT header and return the ARM64 slice's file offset, or None."""
    if len(data) < 32:
        return None
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic not in (0xBEBAFECA, 0xBFBAFECA):
        return None
    nfat = struct.unpack_from(">I", data, 4)[0]
    CPU_ARM64 = 0x0100000C
    for i in range(min(nfat, 20)):
        off = 8 + i * 20
        if off + 20 > len(data):
            break
        cputype = struct.unpack_from(">I", data, off)[0]
        if cputype == CPU_ARM64:
            return struct.unpack_from(">I", data, off + 8)[0]
    return None


def apply_stereo_patches_from_json(node_path, stereo_patches):
    """
    Apply ARM64 stereo_patches from finder JSON to the binary.
    Each entry: arch, fat_offset, orig, patch, name. orig/patch are hex strings (space-sep or not).

    CRITICAL: codesign --remove-signature shrinks slices and shifts the ARM64 slice
    to a lower offset. The fat_offsets in the JSON were recorded from the signed binary.
    We recalculate the shift by reading the current FAT header.
    Returns (count_applied, list_of_applied_metadata).
    """
    if not stereo_patches:
        return 0, []
    arm64_patches = [p for p in stereo_patches if p.get("arch") == "arm64"]
    if not arm64_patches:
        return 0, []
    data = bytearray(node_path.read_bytes())

    current_arm64_start = _get_arm64_slice_offset(data)
    if current_arm64_start is None:
        return 0, []

    original_arm64_start = None
    for p in arm64_patches:
        fo = p.get("fat_offset")
        va = p.get("va")
        if fo is not None and va is not None:
            original_arm64_start = fo - va
            break

    shift = 0
    if original_arm64_start is not None and current_arm64_start != original_arm64_start:
        shift = current_arm64_start - original_arm64_start
        print(f"  ARM64 slice shifted by {shift:+d} bytes (0x{abs(shift):X}) after signature removal")

    applied = 0
    applied_meta = []
    skipped = []
    for p in arm64_patches:
        fo = p.get("fat_offset")
        va = p.get("va")
        if fo is None:
            continue
        adjusted_fo = fo + shift
        orig = _hex_str_to_bytes(p.get("orig"))
        patch = _hex_str_to_bytes(p.get("patch"))
        name = p.get("name", "?")
        if not orig or not patch or len(patch) != len(orig):
            skipped.append(f"{name}: orig/patch size mismatch")
            continue
        if adjusted_fo + len(patch) > len(data):
            skipped.append(f"{name}: offset 0x{adjusted_fo:X} beyond file end")
            continue
        current = data[adjusted_fo : adjusted_fo + len(orig)]
        if current != orig:
            if current == patch:
                print(f"  {name}: already patched at 0x{adjusted_fo:X}")
                applied += 1
                applied_meta.append({"name": name, "va": va or (adjusted_fo - current_arm64_start),
                                     "orig": p.get("orig"), "patch": p.get("patch")})
            else:
                skipped.append(f"{name}: expected {orig.hex()} at 0x{adjusted_fo:X}, got {current.hex()}")
            continue
        data[adjusted_fo : adjusted_fo + len(patch)] = patch
        applied += 1
        applied_meta.append({"name": name, "va": va or (adjusted_fo - current_arm64_start),
                             "orig": p.get("orig"), "patch": p.get("patch")})
    if applied > 0:
        node_path.write_bytes(data)
    if skipped:
        for msg in skipped:
            print(f"  [SKIP] {msg}")
    return applied, applied_meta


def apply_byte_patches(node_path, file_offsets):
    """Apply patches at file_offsets (name -> int). Returns (count_applied, dict of applied offsets)."""
    data = bytearray(node_path.read_bytes())
    applied = 0
    applied_offsets = {}
    for name, hex_bytes in PATCH_BYTES_BY_NAME.items():
        if name not in file_offsets:
            continue
        off = file_offsets[name]
        if isinstance(off, str):
            off = int(off, 16)
        patch = bytes.fromhex(hex_bytes.replace(" ", ""))
        if off + len(patch) > len(data):
            continue
        data[off : off + len(patch)] = patch
        applied += 1
        applied_offsets[name] = off
    node_path.write_bytes(data)
    return applied, applied_offsets


def get_injection_offsets(export_data):
    """Return (hp_offset, dc_offset) from injection_sites, or (None, None)."""
    sites = export_data.get("injection_sites") or []
    hp = dc = None
    for s in sites:
        if s.get("name") == "HighpassCutoffFilter":
            hp = s.get("file_offset")
        elif s.get("name") == "DcReject":
            dc = s.get("file_offset")
    if hp is not None and isinstance(hp, str):
        hp = int(hp, 16)
    if dc is not None and isinstance(dc, str):
        dc = int(dc, 16)
    return hp, dc


def write_injector_cpp(build_dir, hp_offset, dc_offset):
    """Write inject_patcher.cpp and amplifier.cpp with given offsets."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    injector_src = f'''#include <cstdio>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/mman.h>

extern "C" void hp_cutoff(const float*, int, float*, int*, int, int, int, int);
extern "C" void hp_cutoff_end(void);
extern "C" void dc_reject(const float*, float*, int*, int, int, int);
extern "C" void dc_reject_end(void);

static const size_t HP_OFFSET = {hp_offset};
static const size_t DC_OFFSET = {dc_offset};
static const size_t MAX_SIZE  = 400;

int main(int argc, char* argv[]) {{
    if (argc < 2) {{ printf("Usage: %s <path>\\n", argv[0]); return 1; }}
    ptrdiff_t hp_size = (char*)hp_cutoff_end - (char*)hp_cutoff;
    ptrdiff_t dc_size = (char*)dc_reject_end - (char*)dc_reject;
    if (hp_size <= 0 || hp_size > (ptrdiff_t)MAX_SIZE) {{ printf("ERROR: hp_cutoff size\\n"); return 1; }}
    if (dc_size <= 0 || dc_size > (ptrdiff_t)MAX_SIZE) {{ printf("ERROR: dc_reject size\\n"); return 1; }}
    if ((size_t)hp_size > (DC_OFFSET - HP_OFFSET)) {{ printf("ERROR: overlap\\n"); return 1; }}
    int fd = open(argv[1], O_RDWR);
    if (fd < 0) {{ printf("ERROR: open\\n"); return 1; }}
    struct stat st;
    if (fstat(fd, &st) < 0) {{ close(fd); return 1; }}
    void* data = mmap(NULL, st.st_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (data == MAP_FAILED) {{ close(fd); return 1; }}
    if ((off_t)(HP_OFFSET + hp_size) > st.st_size || (off_t)(DC_OFFSET + dc_size) > st.st_size) {{
        munmap(data, st.st_size); close(fd); return 1;
    }}
    memcpy((char*)data + HP_OFFSET, (const char*)hp_cutoff, hp_size);
    memcpy((char*)data + DC_OFFSET, (const char*)dc_reject, dc_size);
    msync(data, st.st_size, MS_SYNC);
    munmap(data, st.st_size);
    close(fd);
    return 0;
}}
'''
    (build_dir / "inject_patcher.cpp").write_text(injector_src)
    # amplifier.cpp - minimal passthrough (same as patcher)
    amplifier_cpp = r'''#include <cstdint>
extern "C" __attribute__((noinline))
void hp_cutoff(const float* in, int cutoff_Hz, float* out, int* hp_mem,
               int len, int channels, int Fs, int arch) {
    int* st = (hp_mem - 3553);
    *(int*)(st + 3557) = 1002;
    *(int*)((char*)st + 160) = -1;
    *(int*)((char*)st + 164) = -1;
    *(int*)((char*)st + 184) = 0;
    unsigned long total = (unsigned long)((unsigned)channels * (unsigned)len);
    for (unsigned long i = 0; i < total; i++) { out[i] = in[i]; }
}
extern "C" __attribute__((noinline, used)) void hp_cutoff_end(void) { __asm__ volatile("nop"); }
extern "C" __attribute__((noinline))
void dc_reject(const float* in, float* out, int* hp_mem, int len, int channels, int Fs) {
    int* st = (hp_mem - 3553);
    *(int*)(st + 3557) = 1002;
    *(int*)((char*)st + 160) = -1;
    *(int*)((char*)st + 164) = -1;
    *(int*)((char*)st + 184) = 0;
    unsigned long total = (unsigned long)((unsigned)channels * (unsigned)len);
    for (unsigned long i = 0; i < total; i++) { out[i] = in[i]; }
}
extern "C" __attribute__((noinline, used)) void dc_reject_end(void) { __asm__ volatile("nop"); }
'''
    (build_dir / "amplifier.cpp").write_text(amplifier_cpp)


def compile_and_run_injector(build_dir, node_path):
    """Compile injector and run it on node_path. Returns (success, message)."""
    # Native arch: injector runs on host and patches file at file offsets
    cmd = [
        "clang++", "-O2", "-fno-builtin", "-std=c++17",
        str(build_dir / "inject_patcher.cpp"),
        str(build_dir / "amplifier.cpp"),
        "-o", str(build_dir / "inject_patcher"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stderr or "Compilation failed"
    injector = build_dir / "inject_patcher"
    injector.chmod(0o755)
    r2 = subprocess.run([str(injector), str(node_path)], capture_output=True, text=True)
    if r2.returncode != 0:
        return False, r2.stderr or "Injection failed"
    return True, "OK"


def enable_library_validation_bypass():
    """Add disable-library-validation to Discord.app helpers that lack it.

    On Apple Silicon, macOS strictly enforces library validation for dlopen().
    The helpers (GPU, Plugin, Renderer) and main binary don't have this entitlement,
    so they reject our ad-hoc signed .node. On Intel this is lenient.

    KEY DIFFERENCE from old approach: we EXTRACT original entitlements from each
    component and ONLY ADD the single key, preserving all original entitlements
    (application-identifier, allow-jit, keychain-access-groups, etc.).
    The old approach replaced all entitlements with a minimal set, which broke Discord.
    """
    discord_paths = [Path("/Applications/Discord.app"),
                     Path.home() / "Applications" / "Discord.app"]
    app_path = next((p for p in discord_paths if p.exists()), None)
    if not app_path:
        print("  [WARN] Discord.app not found — skipping library validation bypass", file=sys.stderr)
        return False

    frameworks = app_path / "Contents" / "Frameworks"

    helper_bundles = [
        ("Discord Helper (GPU)", frameworks / "Discord Helper (GPU).app"),
        ("Discord Helper (Plugin)", frameworks / "Discord Helper (Plugin).app"),
        ("Discord Helper (Renderer)", frameworks / "Discord Helper (Renderer).app"),
    ]

    all_ok = True

    for name, bundle_path in helper_bundles:
        binary_path = bundle_path / "Contents" / "MacOS" / name
        if not binary_path.exists():
            continue

        r = subprocess.run(["codesign", "-d", "--entitlements", ":-", str(binary_path)],
                           capture_output=True, text=True)
        if not r.stdout.strip():
            continue

        ent_file = Path(tempfile.gettempdir()) / f"ent_{name.replace(' ', '_')}.plist"
        ent_file.write_text(r.stdout)

        pb = subprocess.run(["/usr/libexec/PlistBuddy", "-c",
                             "Add :com.apple.security.cs.disable-library-validation bool true",
                             str(ent_file)], capture_output=True)
        if pb.returncode != 0:
            subprocess.run(["/usr/libexec/PlistBuddy", "-c",
                            "Set :com.apple.security.cs.disable-library-validation true",
                            str(ent_file)], capture_output=True)

        sr = subprocess.run(["codesign", "--force", "--sign", "-", "--options", "runtime",
                             "--entitlements", str(ent_file), str(bundle_path)],
                            capture_output=True, text=True)
        ent_file.unlink(missing_ok=True)

        if sr.returncode == 0:
            print(f"  [OK] {name}: disable-library-validation added")
        else:
            print(f"  [FAIL] {name}: {sr.stderr.strip()}")
            if "not permitted" in sr.stderr.lower():
                print("  [INFO] Enable this app in System Settings > Privacy & Security > App Management")
                all_ok = False
                break
            all_ok = False

    if not all_ok:
        return False

    main_binary = app_path / "Contents" / "MacOS" / "Discord"
    if main_binary.exists():
        r = subprocess.run(["codesign", "-d", "--entitlements", ":-", str(main_binary)],
                           capture_output=True, text=True)
        ent_file = Path(tempfile.gettempdir()) / "ent_Discord_main.plist"
        ent_file.write_text(r.stdout)
        pb = subprocess.run(["/usr/libexec/PlistBuddy", "-c",
                             "Add :com.apple.security.cs.disable-library-validation bool true",
                             str(ent_file)], capture_output=True)
        if pb.returncode != 0:
            subprocess.run(["/usr/libexec/PlistBuddy", "-c",
                            "Set :com.apple.security.cs.disable-library-validation true",
                            str(ent_file)], capture_output=True)

        sr = subprocess.run(["codesign", "--force", "--sign", "-", "--options", "runtime",
                             "--entitlements", str(ent_file), str(app_path)],
                            capture_output=True, text=True)
        ent_file.unlink(missing_ok=True)

        if sr.returncode == 0:
            print("  [OK] Discord.app re-signed (original entitlements preserved + disable-library-validation)")
        else:
            print(f"  [FAIL] Outer Discord.app: {sr.stderr.strip()}")
            all_ok = False

    if all_ok:
        subprocess.run(["xattr", "-cr", str(app_path)], capture_output=True)

    return all_ok


def main():
    flags = {"--check-only", "--no-bypass"}
    args = [a for a in sys.argv[1:] if a not in flags]
    check_only = "--check-only" in sys.argv
    node_path = args[0] if args else None
    if not node_path:
        node_path = find_discord_node()
        if not node_path:
            print("No discord_voice.node path given and auto-detect found nothing.", file=sys.stderr)
            print("Usage: python discord_stereo_adaptive_patch.py [path_to_discord_voice.node] [--check-only]", file=sys.stderr)
            sys.exit(1)
    node_path = Path(node_path)
    if not node_path.is_file():
        print(f"File not found: {node_path}", file=sys.stderr)
        sys.exit(1)

    print("Discord Stereo Adaptive Patcher")
    print(f"  Target: {node_path}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Run offset finder
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        export_json = f.name
    try:
        ok, data = run_offset_finder(node_path, export_json)
        if not ok or not data:
            print("Offset finder failed or produced no JSON.", file=sys.stderr)
            os.unlink(export_json)
            sys.exit(1)
    except Exception as e:
        print(f"Error running offset finder: {e}", file=sys.stderr)
        if os.path.exists(export_json):
            os.unlink(export_json)
        sys.exit(1)

    file_offsets = data.get("file_offsets")
    if not file_offsets:
        file_offsets = {}
        for p in data.get("patches", []):
            name = p.get("name")
            off = p.get("file_offset")
            if name is not None and off is not None:
                file_offsets[name] = off

    # Heuristic: detect patched vs unpatched state (includes ARM64 with offset correction)
    patch_specs = get_patch_specs(data, node_path)
    unpatched_n, patched_n, details = check_patch_status(node_path, patch_specs)

    if check_only:
        total = len(details)
        if total == 0:
            print("UNPATCHED (no patch sites found)")
        elif patched_n == total:
            print("PATCHED")
        elif unpatched_n == total:
            print("UNPATCHED")
        else:
            print("PARTIAL")
        if details and (patched_n != total or unpatched_n != total):
            for name, status in details:
                print(f"  {name}: {status}")
        os.unlink(export_json)
        sys.exit(0)

    if patched_n == len(details) and len(details) > 0:
        print("Already patched (all patch sites match). Exiting without changes.")
        os.unlink(export_json)
        sys.exit(0)

    hp_off, dc_off = get_injection_offsets(data)
    if hp_off is None or dc_off is None:
        print("Injection sites (HighpassCutoffFilter, DcReject) not in offset finder output.", file=sys.stderr)
        os.unlink(export_json)
        sys.exit(1)

    # 2) Backup
    backup = create_backup(node_path)
    if backup:
        print(f"  Backup: {backup}")
    else:
        print("  Warning: could not create backup")

    # 3) Remove signature and make writable
    subprocess.run(["codesign", "--remove-signature", str(node_path)], capture_output=True)
    node_path.chmod(0o644)

    # 4) Byte patches
    n, x86_applied_offsets = apply_byte_patches(node_path, file_offsets)
    print(f"  Byte patches applied: {n}")

    # 5) Injector
    write_injector_cpp(BUILD_DIR, hp_off, dc_off)
    inj_ok, inj_msg = compile_and_run_injector(BUILD_DIR, node_path)
    if not inj_ok:
        print(f"  Injection failed: {inj_msg}", file=sys.stderr)
        os.unlink(export_json)
        sys.exit(1)
    print("  Code injection OK")

    # 5b) ARM64 stereo patches (fat binary): always patch both slices
    arm64_applied = 0
    arm64_meta = []
    stereo_patches = data.get("stereo_patches") or []
    arm64_applied, arm64_meta = apply_stereo_patches_from_json(node_path, stereo_patches)
    if arm64_applied > 0:
        print(f"  ARM64 stereo patches from JSON: {arm64_applied} applied")
    else:
        arm_script = REPO_ROOT / "scripts" / "apply_arm64_stereo_patches.py"
        if arm_script.exists():
            r = subprocess.run([sys.executable, str(arm_script), str(node_path)], capture_output=True, text=True, cwd=str(REPO_ROOT))
            if r.returncode == 0:
                print("  ARM64 stereo patches (script): applied")

    # Save patch metadata for reliable verification later
    _save_patch_metadata(str(node_path), x86_applied_offsets, arm64_meta)

    # 6) Refresh inode to avoid macOS signature cache issue.
    #    macOS caches code signatures by inode. Patching in-place leaves stale
    #    cached data that causes dlopen() to reject the file even after re-signing.
    tmp_inode = str(node_path) + ".tmp_inode"
    node_path.rename(tmp_inode)
    Path(tmp_inode).replace(node_path)
    print("  Refreshed file inode (avoids macOS signature cache).")

    # 7) Re-sign the patched .node (ad-hoc)
    subprocess.run(["codesign", "--remove-signature", str(node_path)], capture_output=True)
    subprocess.run(["codesign", "--force", "--sign", "-", str(node_path)], capture_output=True)
    # Verify
    r = subprocess.run(["codesign", "--verify", "--verbose", str(node_path)], capture_output=True, text=True)
    if r.returncode == 0:
        print("  Re-signed .node (ad-hoc) — signature verified valid.")
    else:
        print(f"  Re-signed .node (ad-hoc) — verify FAILED: {r.stderr.strip()}")

    # 8) Clear quarantine
    subprocess.run(["xattr", "-cr", str(node_path)], capture_output=True)
    for ap in [Path("/Applications/Discord.app"), Path.home() / "Applications" / "Discord.app"]:
        if ap.exists():
            subprocess.run(["xattr", "-cr", str(ap)], capture_output=True)
    print("  Quarantine cleared.")

    # 9) Enable library validation bypass on Discord.app (unless --no-bypass passed)
    no_bypass = "--no-bypass" in sys.argv
    if not no_bypass:
        print("  Enabling library validation bypass on Discord.app...")
        bypass_ok = enable_library_validation_bypass()
        if not bypass_ok:
            print("  [WARN] Library validation bypass may have failed.", file=sys.stderr)
            print("  On Apple Silicon, Discord may show a corruption banner.", file=sys.stderr)
    else:
        print("  Library validation bypass: skipped (handled by caller)")

    os.unlink(export_json)
    print("Done. Restart Discord to use stereo.")


if __name__ == "__main__":
    main()
