#!/usr/bin/env python3
"""
Discord Stereo Audio Patcher for macOS — GUI Version
═════════════════════════════════════════════════════
Finalized and made working by Crue.

Tkinter-based graphical patcher that enables true stereo audio
transmission in Discord voice channels on macOS.

Platform Compatibility:
  - CONFIRMED WORKING: Intel/x86_64 macOS Sequoia 15.7.x
    (tested with Cubase Pro/Nuendo + Rogue Amoeba Loopback)
  - Apple Silicon (M1/M2/M3/M4): fat binary patched in-place (both
    x86_64 and ARM64 slices); Discord runs natively without Rosetta

Features:
  - Auto-detect Discord installations
  - One-click patching with full progress tracking
  - Backup creation and restoration
  - Export patched binary for manual installation
  - Verification of patch status
  - Fat binary: patch both slices in-place (no Rosetta required)
  - Dark theme matching Discord's aesthetic

Requirements:
  - Python 3.6+
  - macOS 10.15+
  - Xcode Command Line Tools (for clang++): xcode-select --install

Version: 1.1.0

Credits:
  Finalized by: Crue
  Original offset discovery & scripts: Oracle, Shaun, Hallow, Ascend,
                                       Sentry, Sikimzo, Cypher
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import os
import sys
import shutil
import tempfile
import threading
import struct
import time
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

VERSION = "1.1.0"
BITRATE = 384
BITRATE_LE_3 = bytes.fromhex("00DC05")      # 384000 LE 3 bytes
BITRATE_LE_4 = bytes.fromhex("00DC0500")     # 384000 LE 4 bytes
BITRATE_LE_5 = bytes.fromhex("00DC050000")   # 384000 LE 5 bytes

CACHE_DIR = Path.home() / "Library" / "Caches" / "DiscordVoicePatcher"
BACKUP_DIR = CACHE_DIR / "Backups"
BUILD_DIR = CACHE_DIR / "build"

# Discord-themed colors
COLORS = {
    "bg_dark":       "#1e1f22",
    "bg_secondary":  "#2b2d31",
    "bg_tertiary":   "#313338",
    "bg_input":      "#383a40",
    "text_normal":   "#dbdee1",
    "text_muted":    "#949ba4",
    "text_header":   "#f2f3f5",
    "blurple":       "#5865f2",
    "blurple_dark":  "#4752c4",
    "green":         "#57f287",
    "red":           "#ed4245",
    "yellow":        "#fee75c",
    "white":         "#ffffff",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Patch Definitions
# ═══════════════════════════════════════════════════════════════════════════════

BYTE_PATCHES = [
    # (offset, hex_bytes, description, category)
    # Stereo Enable
    (0xA296FF, "02",                         "EmulateStereoSuccess1 (channels=2)",        "Stereo"),
    (0xA29700, "EB",                         "EmulateStereoSuccess2 (jne->jmp)",          "Stereo"),
    (0xA1E34A, "4989C490",                   "CreateAudioFrameStereo",                    "Stereo"),
    (0x41BE45, "02",                         "AudioEncoderConfigSetChannels (ch=2)",      "Stereo"),
    (0x9E9DEB, "909090909090909090909090E9", "MonoDownmixer (NOP sled + JMP)",            "Stereo"),
    # Bitrate 384kbps
    (0xA29B5E, "00DC05",                     "EmulateBitrateModified (384kbps)",          "Bitrate"),
    (0x6091E0, "00DC050000",                 "SetsBitrateBitrateValue",                   "Bitrate"),
    (0x6091E8, "909090",                     "SetsBitrateBitwiseOr (NOP)",                "Bitrate"),
    (0xA2EA44, "00DC05",                     "DuplicateEmulateBitrate",                   "Bitrate"),
    # Function Disables
    (0x2B6EC0, "C3",                         "HighPassFilter (RET)",                      "Filter"),
    (0x3FAE70, "C3",                         "DownmixFunc (RET)",                         "Filter"),
    (0x41C150, "C3",                         "AudioEncoderConfigIsOk (RET)",              "Filter"),
    (0x945240, "C3",                         "ThrowError (RET)",                          "Filter"),
    # Encoder Config Init
    (0x41BE4F, "00DC0500",                   "EncoderConfigInit1 (384kbps)",              "Encoder"),
    (0x41B9C8, "00DC0500",                   "EncoderConfigInit2 (384kbps)",              "Encoder"),
    # SDP Stereo Force
    (0xA26B56, "4889C290",                   "SDPStereoForce1 (force stereo=1)",          "SDP"),
    (0xA297AD, "4889C290",                   "SDPStereoForce2 (force stereo=1)",          "SDP"),
]

# Code injection offsets
HP_CUTOFF_OFFSET = 0x403A90
DC_REJECT_OFFSET = 0x403C20

# ═══════════════════════════════════════════════════════════════════════════════
# C++ Source Code (embedded)
# ═══════════════════════════════════════════════════════════════════════════════

AMPLIFIER_CPP = r"""
#include <cstdint>

extern "C" __attribute__((noinline))
void hp_cutoff(const float* in, int cutoff_Hz, float* out, int* hp_mem,
               int len, int channels, int Fs, int arch) {
    int* st = (hp_mem - 3553);
    *(int*)(st + 3557) = 1002;
    *(int*)((char*)st + 160) = -1;
    *(int*)((char*)st + 164) = -1;
    *(int*)((char*)st + 184) = 0;
    unsigned long total = (unsigned long)((unsigned)channels * (unsigned)len);
    for (unsigned long i = 0; i < total; i++) {
        out[i] = in[i];
    }
}

extern "C" __attribute__((noinline, used))
void hp_cutoff_end(void) { __asm__ volatile("nop"); }

extern "C" __attribute__((noinline))
void dc_reject(const float* in, float* out, int* hp_mem,
               int len, int channels, int Fs) {
    int* st = (hp_mem - 3553);
    *(int*)(st + 3557) = 1002;
    *(int*)((char*)st + 160) = -1;
    *(int*)((char*)st + 164) = -1;
    *(int*)((char*)st + 184) = 0;
    unsigned long total = (unsigned long)((unsigned)channels * (unsigned)len);
    for (unsigned long i = 0; i < total; i++) {
        out[i] = in[i];
    }
}

extern "C" __attribute__((noinline, used))
void dc_reject_end(void) { __asm__ volatile("nop"); }
"""

INJECTOR_CPP = r"""
#include <cstdio>
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

static const size_t HP_OFFSET = 0x403A90;
static const size_t DC_OFFSET = 0x403C20;
static const size_t MAX_SIZE  = 400;

int main(int argc, char* argv[]) {
    if (argc < 2) { printf("Usage: %s <path>\n", argv[0]); return 1; }

    ptrdiff_t hp_size = (char*)hp_cutoff_end - (char*)hp_cutoff;
    ptrdiff_t dc_size = (char*)dc_reject_end - (char*)dc_reject;

    printf("hp_cutoff: %td bytes, dc_reject: %td bytes\n", hp_size, dc_size);

    if (hp_size <= 0 || hp_size > (ptrdiff_t)MAX_SIZE) {
        printf("ERROR: hp_cutoff size %td out of range\n", hp_size); return 1;
    }
    if (dc_size <= 0 || dc_size > (ptrdiff_t)MAX_SIZE) {
        printf("ERROR: dc_reject size %td out of range\n", dc_size); return 1;
    }
    if ((size_t)hp_size > (DC_OFFSET - HP_OFFSET)) {
        printf("ERROR: hp_cutoff overlaps dc_reject\n"); return 1;
    }

    int fd = open(argv[1], O_RDWR);
    if (fd < 0) { printf("ERROR: Cannot open file\n"); return 1; }

    struct stat st;
    fstat(fd, &st);

    void* data = mmap(NULL, st.st_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (data == MAP_FAILED) { close(fd); return 1; }

    if ((off_t)(HP_OFFSET + hp_size) > st.st_size) {
        munmap(data, st.st_size); close(fd); return 1;
    }

    printf("Injecting hp_cutoff at 0x%zX (%td bytes)\n", HP_OFFSET, hp_size);
    memcpy((char*)data + HP_OFFSET, (const char*)hp_cutoff, hp_size);

    printf("Injecting dc_reject at 0x%zX (%td bytes)\n", DC_OFFSET, dc_size);
    memcpy((char*)data + DC_OFFSET, (const char*)dc_reject, dc_size);

    msync(data, st.st_size, MS_SYNC);
    munmap(data, st.st_size);
    close(fd);

    printf("Code injection complete!\n");
    return 0;
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Patcher Logic
# ═══════════════════════════════════════════════════════════════════════════════

class PatcherEngine:
    """Core patching logic (no GUI dependencies)."""

    def __init__(self, log_callback=None):
        self.log = log_callback or print
        self.discord_node = None
        self.discord_name = None

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        BUILD_DIR.mkdir(parents=True, exist_ok=True)

    def find_discord(self):
        """Locate Discord installations and return list of (name, path)."""
        search = [
            ("Discord Stable",  Path.home() / "Library/Application Support/discord"),
            ("Discord Canary",  Path.home() / "Library/Application Support/discordcanary"),
            ("Discord PTB",     Path.home() / "Library/Application Support/discordptb"),
        ]
        found = []
        for name, base in search:
            if not base.is_dir():
                continue
            for node in base.rglob("discord_voice.node"):
                if node.is_file():
                    found.append((name, str(node)))
                    break
        return found

    def check_status(self, node_path):
        """Check if binary is patched, unpatched, or unknown."""
        try:
            fo = self.get_fat_offset(node_path)
            with open(node_path, "rb") as f:
                f.seek(0xA296FF + fo)
                byte = f.read(1)
            if byte == b"\x01":
                return "unpatched"
            elif byte == b"\x02":
                return "patched"
            else:
                return "unknown"
        except Exception:
            return "error"

    def create_backup(self, node_path):
        """Create timestamped backup, return backup path."""
        name_clean = (self.discord_name or "Discord").replace(" ", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"discord_voice.node.{name_clean}.{ts}.backup"
        shutil.copy2(node_path, backup_path)

        # Keep only 10 most recent
        backups = sorted(BACKUP_DIR.glob("*.backup"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[10:]:
            old.unlink(missing_ok=True)

        return str(backup_path)

    def list_backups(self):
        """Return list of (path, date, size) for backups."""
        backups = sorted(BACKUP_DIR.glob("*.backup"), key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for b in backups:
            st = b.stat()
            date = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            size_mb = st.st_size / (1024 * 1024)
            result.append((str(b), date, f"{size_mb:.2f} MB"))
        return result

    def restore_backup(self, backup_path, node_path):
        """Restore a backup file to the target path."""
        shutil.copy2(backup_path, node_path)
        self._codesign(node_path)

    def kill_discord(self):
        """Close Discord processes."""
        for app in ["Discord", "Discord Canary", "Discord PTB"]:
            try:
                subprocess.run(
                    ["osascript", "-e", f'tell application "{app}" to quit'],
                    capture_output=True, timeout=5
                )
            except (subprocess.TimeoutExpired, OSError):
                pass
        time.sleep(2)
        try:
            subprocess.run(["pkill", "-f", "[Dd]iscord"], capture_output=True,
                           timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            pass
        time.sleep(1)

    def remove_signature(self, node_path):
        """Remove code signature from binary."""
        subprocess.run(
            ["codesign", "--remove-signature", node_path],
            capture_output=True
        )

    def _codesign(self, node_path):
        """Ad-hoc re-sign binary with inode refresh to avoid macOS signature cache."""
        # Refresh inode — macOS caches signatures by inode
        tmp = node_path + ".tmp_inode"
        Path(node_path).rename(tmp)
        Path(tmp).replace(node_path)

        self.remove_signature(node_path)
        subprocess.run(["codesign", "--force", "--sign", "-", node_path], capture_output=True)
        subprocess.run(["xattr", "-cr", node_path], capture_output=True)
        for app_path in ["/Applications/Discord.app",
                         str(Path.home() / "Applications/Discord.app")]:
            subprocess.run(["xattr", "-cr", app_path], capture_output=True)

    def _resign_discord_app(self):
        """Re-sign all 15 signed components of Discord.app (innermost to outermost).

        On Apple Silicon, allow-jit is mandatory for V8's JIT — stripping it
        kills the process (bounce in dock, no window). We preserve it while
        adding disable-library-validation to allow loading our ad-hoc .node.
        """
        discord_paths = [Path("/Applications/Discord.app"),
                         Path.home() / "Applications" / "Discord.app"]
        app_path = next((p for p in discord_paths if p.exists()), None)
        if not app_path:
            return

        frameworks = app_path / "Contents" / "Frameworks"
        ef_versioned = frameworks / "Electron Framework.framework" / "Versions" / "A"

        CHILD_ENT = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>'
            '<key>com.apple.security.cs.allow-jit</key><true/>'
            '<key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>'
            '<key>com.apple.security.cs.disable-library-validation</key><true/>'
            '<key>com.apple.security.device.audio-input</key><true/>'
            '<key>com.apple.security.device.camera</key><true/>'
            '</dict></plist>'
        )

        child_ent_file = Path(tempfile.gettempdir()) / "discord_child_ent.plist"
        main_ent_file = Path(tempfile.gettempdir()) / "discord_main_ent.plist"
        child_ent_file.write_text(CHILD_ENT)
        main_ent_file.write_text(CHILD_ENT)

        def sign(path, ent_file=None):
            p = Path(path)
            if not p.exists():
                return
            args = ["codesign", "--force", "--sign", "-"]
            if ent_file:
                args += ["--entitlements", str(ent_file)]
            args.append(str(p))
            subprocess.run(args, capture_output=True)

        # 1) Dylibs inside Electron Framework
        lib_dir = ef_versioned / "Libraries"
        if lib_dir.exists():
            for lib in ["libEGL.dylib", "libGLESv2.dylib", "libffmpeg.dylib", "libvk_swiftshader.dylib"]:
                sign(lib_dir / lib, child_ent_file)

        # 2) Executables inside frameworks
        sign(ef_versioned / "Helpers" / "chrome_crashpad_handler", child_ent_file)

        # 3) Frameworks (versioned path)
        sign(ef_versioned, child_ent_file)
        for fw in ["Mantle.framework", "ReactiveObjC.framework"]:
            sign(frameworks / fw, child_ent_file)
        squirrel_v = frameworks / "Squirrel.framework" / "Versions" / "A"
        sign(squirrel_v / "Resources" / "ShipIt", child_ent_file)
        sign(frameworks / "Squirrel.framework", child_ent_file)

        # 4) Helper apps
        for helper in ["Discord Helper", "Discord Helper (GPU)",
                       "Discord Helper (Plugin)", "Discord Helper (Renderer)"]:
            sign(frameworks / f"{helper}.app", child_ent_file)

        # 5) Main binary
        sign(app_path / "Contents" / "MacOS" / "Discord", main_ent_file)

        # 6) Outer bundle
        sign(app_path, main_ent_file)

        # 7) Cleanup
        child_ent_file.unlink(missing_ok=True)
        main_ent_file.unlink(missing_ok=True)
        subprocess.run(["xattr", "-cr", str(app_path)], capture_output=True)

    def get_fat_offset(self, node_path):
        """Return file offset of x86_64 slice in a fat binary, or 0 if thin/non-fat."""
        try:
            with open(node_path, "rb") as f:
                d = f.read(512)
            if len(d) < 32:
                return 0
            magic = struct.unpack_from(">I", d, 0)[0]
            if magic not in (0xBEBAFECA, 0xBFBAFECA):
                return 0
            n = struct.unpack_from(">I", d, 4)[0]
            for i in range(min(n, 20)):
                off = 8 + i * 20
                if off + 20 > len(d):
                    break
                cputype = struct.unpack_from(">I", d, off)[0]
                slice_off = struct.unpack_from(">I", d, off + 8)[0]
                if cputype == 0x01000007:  # x86_64
                    return slice_off
            return 0
        except Exception:
            return 0

    def apply_byte_patch(self, node_path, offset, hex_bytes, description):
        """Apply a single byte patch and verify."""
        data = bytes.fromhex(hex_bytes)
        with open(node_path, "r+b") as f:
            f.seek(offset)
            f.write(data)

        # Verify
        with open(node_path, "rb") as f:
            f.seek(offset)
            actual = f.read(len(data))

        success = actual == data
        return success

    def apply_all_byte_patches(self, node_path, progress_callback=None, fat_offset=0):
        """Apply all byte patches. Returns (success_count, fail_count)."""
        ok = 0
        fail = 0
        total = len(BYTE_PATCHES)

        for i, (offset, hex_bytes, desc, category) in enumerate(BYTE_PATCHES):
            if self.apply_byte_patch(node_path, offset + fat_offset, hex_bytes, desc):
                self.log(f"  [OK] {desc} @ 0x{offset:X}")
                ok += 1
            else:
                self.log(f"  [FAIL] {desc} @ 0x{offset:X}")
                fail += 1

            if progress_callback:
                progress_callback(i + 1, total + 2)  # +2 for code injection

        return ok, fail

    def check_compiler(self):
        """Check if clang++ is available."""
        result = subprocess.run(["which", "clang++"], capture_output=True)
        return result.returncode == 0

    def compile_and_inject(self, node_path, progress_callback=None, fat_offset=0):
        """Compile C++ injection code and apply to binary."""
        # Write sources
        amp_path = BUILD_DIR / "amplifier.cpp"
        inj_path = BUILD_DIR / "inject_patcher.cpp"
        exe_path = BUILD_DIR / "inject_patcher"

        amp_path.write_text(AMPLIFIER_CPP)
        hp_off = HP_CUTOFF_OFFSET + fat_offset
        dc_off = DC_REJECT_OFFSET + fat_offset
        inj_src = INJECTOR_CPP.replace(
            "static const size_t HP_OFFSET = 0x403A90;",
            f"static const size_t HP_OFFSET = {hex(hp_off)};"
        ).replace(
            "static const size_t DC_OFFSET = 0x403C20;",
            f"static const size_t DC_OFFSET = {hex(dc_off)};"
        )
        inj_path.write_text(inj_src)

        # Compile for native architecture (injector runs on host, patches file at file offsets)
        arch_flags = []

        # Compile
        self.log("  Compiling code injector...")
        compile_cmd = [
            "clang++", "-O2", "-fno-builtin", "-std=c++17",
            *arch_flags,
            str(inj_path), str(amp_path),
            "-o", str(exe_path)
        ]

        result = subprocess.run(compile_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.log(f"  [FAIL] Compilation error: {result.stderr}")
            return False

        exe_path.chmod(0o755)
        self.log("  [OK] Compilation successful")
        if fat_offset:
            self.log("  (Injection offsets adjusted for fat binary x86_64 slice)")

        # Run injector
        self.log("  Running code injector...")
        result = subprocess.run(
            [str(exe_path), node_path],
            capture_output=True, text=True
        )

        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                self.log(f"  {line}")

        if result.returncode != 0:
            self.log(f"  [FAIL] Injection error: {result.stderr}")
            return False

        self.log("  [OK] Code injection complete")

        # Cleanup
        for f in [amp_path, inj_path, exe_path]:
            f.unlink(missing_ok=True)

        return True

    def verify_patches(self, node_path, fat_offset=0):
        """Verify all byte patches. Returns list of (desc, passed)."""
        results = []
        for offset, hex_bytes, desc, category in BYTE_PATCHES:
            expected = bytes.fromhex(hex_bytes)
            try:
                with open(node_path, "rb") as f:
                    f.seek(offset + fat_offset)
                    actual = f.read(len(expected))
                results.append((desc, actual == expected, category))
            except Exception:
                results.append((desc, False, category))
        return results

    def is_fat_binary(self, node_path):
        """Check if binary is a universal (fat) binary."""
        result = subprocess.run(["file", node_path], capture_output=True, text=True)
        return "universal binary" in result.stdout

    def full_patch(self, node_path, progress_callback=None, arm64_method="script"):
        """Run the complete patching process. Patches fat binaries in-place (both slices).
        arm64_method: 'script' = run ARM64 patch script when fat; 'skip' = x86_64 only."""
        fat_offset = 0
        if self.is_fat_binary(node_path):
            fat_offset = self.get_fat_offset(node_path)
            if arm64_method == "skip":
                self.log("  Universal (fat) binary — patching x86_64 only (ARM64 skipped).")
            else:
                self.log("  Universal (fat) binary detected — patching both x86_64 and ARM64 in place.")
            if progress_callback:
                progress_callback(1, 24)

        self.log("Removing code signature...")
        self.remove_signature(node_path)
        if progress_callback:
            progress_callback(2, 24)

        self.log("")
        self.log("Applying byte patches...")
        ok, fail = self.apply_all_byte_patches(node_path, progress_callback, fat_offset=fat_offset)

        self.log("")
        self.log("Compiling and injecting replacement functions...")
        inj_ok = self.compile_and_inject(node_path, progress_callback, fat_offset=fat_offset)
        if inj_ok:
            ok += 2
        else:
            fail += 2

        if progress_callback:
            progress_callback(20, 24)

        if fat_offset and arm64_method != "skip":
            self.log("")
            self.log("Applying ARM64 slice stereo patches...")
            repo_root = Path(__file__).resolve().parent.parent
            arm_script = repo_root / "scripts" / "apply_arm64_stereo_patches.py"
            if arm_script.exists():
                result = subprocess.run(
                    [sys.executable, str(arm_script), node_path],
                    capture_output=True, text=True, cwd=str(repo_root)
                )
                if result.returncode == 0:
                    self.log("  [OK] ARM64 patches applied")
                else:
                    self.log("  [WARN] ARM64 script: " + (result.stderr or result.stdout or "unknown"))
            if progress_callback:
                progress_callback(21, 24)

        self.log("")
        self.log("Re-signing binary...")
        self._codesign(node_path)
        if progress_callback:
            progress_callback(22, 24)

        if progress_callback:
            progress_callback(24, 24)

        return ok, fail

    def export_patched(self, node_path, export_dir):
        """Export a patched copy to the specified directory."""
        export_path = Path(export_dir)
        export_path.mkdir(parents=True, exist_ok=True)
        backup_dir = export_path / "original_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Copy original as backup
        shutil.copy2(node_path, backup_dir / "discord_voice.node.original")

        # Copy to export and patch
        export_node = export_path / "discord_voice.node"
        shutil.copy2(node_path, export_node)
        os.chmod(str(export_node), 0o644)

        fat_offset = self.get_fat_offset(str(export_node)) if self.is_fat_binary(str(export_node)) else 0

        # Patch the copy (in-place for fat; both slices)
        self.remove_signature(str(export_node))
        self.apply_all_byte_patches(str(export_node), fat_offset=fat_offset)
        self.compile_and_inject(str(export_node), fat_offset=fat_offset)
        if fat_offset:
            repo_root = Path(__file__).resolve().parent.parent
            arm_script = repo_root / "scripts" / "apply_arm64_stereo_patches.py"
            if arm_script.exists():
                subprocess.run(
                    [sys.executable, str(arm_script), str(export_node)],
                    capture_output=True, cwd=str(repo_root)
                )
        subprocess.run(
            ["codesign", "--force", "--sign", "-", str(export_node)],
            capture_output=True
        )

        # Write guide
        voice_dir = str(Path(node_path).parent)
        guide = export_path / "INSTALL_GUIDE.txt"
        guide.write_text(f"""================================================================================
  Discord Stereo Audio Patch - Manual Installation Guide
  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
================================================================================

WHAT'S INCLUDED:
  discord_voice.node              - Patched binary (ready to install)
  original_backup/                - Copy of your original binary
  INSTALL_GUIDE.txt               - This file

INSTALLATION STEPS:

  1. CLOSE Discord completely (Quit from menu bar or: pkill -f Discord)

  2. BACKUP your original file:
     cp "{voice_dir}/discord_voice.node" ~/Desktop/discord_voice.node.backup

  3. COPY the patched binary:
     cp discord_voice.node "{voice_dir}/discord_voice.node"

  4. RE-SIGN the binary:
     codesign --remove-signature "{voice_dir}/discord_voice.node"
     codesign --force --sign - "{voice_dir}/discord_voice.node"

  5. REMOVE quarantine flag:
     xattr -cr /Applications/Discord.app

  6. Open Discord and test stereo in a voice channel.

TO RESTORE:
  cp original_backup/discord_voice.node.original "{voice_dir}/discord_voice.node"
  codesign --force --sign - "{voice_dir}/discord_voice.node"

NOTE: This patch is for Discord module v0.0.376 only.
      Discord updates may overwrite the patched binary.
================================================================================
""")
        return str(export_path)


# ═══════════════════════════════════════════════════════════════════════════════
# GUI Application
# ═══════════════════════════════════════════════════════════════════════════════

class DiscordStereoPatcherGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Discord Stereo Patcher")
        self.root.geometry("720x750")
        self.root.minsize(650, 650)
        self.root.configure(bg=COLORS["bg_dark"])

        # Note: iconbitmap removed — crashes macOS tkinter with native file dialogs

        self.engine = PatcherEngine(log_callback=self._log)
        self.discord_installations = []
        self.selected_node = tk.StringVar(value="")
        self.is_running = False

        self._setup_styles()
        self._build_ui()
        self._scan_installations()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Dark.TFrame", background=COLORS["bg_dark"])
        style.configure("Card.TFrame", background=COLORS["bg_secondary"])
        style.configure("Header.TLabel",
                        background=COLORS["bg_dark"],
                        foreground=COLORS["text_header"],
                        font=("SF Pro Display", 20, "bold"))
        style.configure("SubHeader.TLabel",
                        background=COLORS["bg_dark"],
                        foreground=COLORS["text_muted"],
                        font=("SF Pro Text", 11))
        style.configure("Dark.TLabel",
                        background=COLORS["bg_dark"],
                        foreground=COLORS["text_normal"],
                        font=("SF Pro Text", 12))
        style.configure("Card.TLabel",
                        background=COLORS["bg_secondary"],
                        foreground=COLORS["text_normal"],
                        font=("SF Pro Text", 12))
        style.configure("CardHeader.TLabel",
                        background=COLORS["bg_secondary"],
                        foreground=COLORS["text_header"],
                        font=("SF Pro Text", 13, "bold"))
        style.configure("Status.TLabel",
                        background=COLORS["bg_secondary"],
                        foreground=COLORS["text_muted"],
                        font=("SF Pro Text", 11))

        # Buttons
        style.configure("Accent.TButton",
                        background=COLORS["blurple"],
                        foreground=COLORS["white"],
                        font=("SF Pro Text", 12, "bold"),
                        padding=(16, 8))
        style.map("Accent.TButton",
                  background=[("active", COLORS["blurple_dark"]),
                              ("disabled", COLORS["bg_input"])])

        style.configure("Secondary.TButton",
                        background=COLORS["bg_input"],
                        foreground=COLORS["text_normal"],
                        font=("SF Pro Text", 11),
                        padding=(12, 6))
        style.map("Secondary.TButton",
                  background=[("active", COLORS["bg_tertiary"]),
                              ("disabled", COLORS["bg_dark"])])

        # Progressbar
        style.configure("Green.Horizontal.TProgressbar",
                        troughcolor=COLORS["bg_input"],
                        background=COLORS["green"],
                        thickness=8)

        # Combobox
        style.configure("Dark.TCombobox",
                        fieldbackground=COLORS["bg_input"],
                        background=COLORS["bg_input"],
                        foreground=COLORS["text_normal"],
                        selectbackground=COLORS["blurple"],
                        font=("SF Pro Text", 11))

    def _build_ui(self):
        main = ttk.Frame(self.root, style="Dark.TFrame")
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # ── Header ──────────────────────────────────────────────────────────
        ttk.Label(main, text="Discord Stereo Patcher",
                  style="Header.TLabel").pack(anchor=tk.W)
        ttk.Label(main, text=f"macOS  |  384kbps  |  Binary SDP Patch  |  v{VERSION}  |  by Crue",
                  style="SubHeader.TLabel").pack(anchor=tk.W)
        ttk.Label(main, text="Confirmed: Intel/x86_64 (Sequoia 15.7.x)  |  In Testing: Apple Silicon",
                  style="SubHeader.TLabel").pack(anchor=tk.W, pady=(0, 12))

        # ── Installation Card ───────────────────────────────────────────────
        card1 = ttk.Frame(main, style="Card.TFrame")
        card1.pack(fill=tk.X, pady=(0, 10))
        card1_inner = ttk.Frame(card1, style="Card.TFrame")
        card1_inner.pack(fill=tk.X, padx=16, pady=12)

        ttk.Label(card1_inner, text="Discord Installation",
                  style="CardHeader.TLabel").pack(anchor=tk.W)

        sel_frame = ttk.Frame(card1_inner, style="Card.TFrame")
        sel_frame.pack(fill=tk.X, pady=(8, 0))

        self.install_combo = ttk.Combobox(
            sel_frame, textvariable=self.selected_node,
            state="readonly", font=("SF Mono", 10), width=55
        )
        self.install_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.install_combo.bind("<<ComboboxSelected>>", self._on_install_selected)

        ttk.Button(sel_frame, text="Browse...", style="Secondary.TButton",
                   command=self._browse_node).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(sel_frame, text="Rescan", style="Secondary.TButton",
                   command=self._scan_installations).pack(side=tk.LEFT, padx=(4, 0))

        self.status_label = ttk.Label(card1_inner, text="Status: Scanning...",
                                       style="Status.TLabel")
        self.status_label.pack(anchor=tk.W, pady=(6, 0))

        # ── Actions Card ────────────────────────────────────────────────────
        card2 = ttk.Frame(main, style="Card.TFrame")
        card2.pack(fill=tk.X, pady=(0, 10))
        card2_inner = ttk.Frame(card2, style="Card.TFrame")
        card2_inner.pack(fill=tk.X, padx=16, pady=12)

        ttk.Label(card2_inner, text="Actions",
                  style="CardHeader.TLabel").pack(anchor=tk.W)

        btn_frame = ttk.Frame(card2_inner, style="Card.TFrame")
        btn_frame.pack(fill=tk.X, pady=(8, 0))

        self.patch_btn = ttk.Button(btn_frame, text="  Patch Discord  ",
                                     style="Accent.TButton",
                                     command=self._start_patch)
        self.patch_btn.pack(side=tk.LEFT)

        self.restore_btn = ttk.Button(btn_frame, text="Restore",
                                       style="Secondary.TButton",
                                       command=self._start_restore)
        self.restore_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.verify_btn = ttk.Button(btn_frame, text="Verify",
                                      style="Secondary.TButton",
                                      command=self._start_verify)
        self.verify_btn.pack(side=tk.LEFT, padx=(4, 0))

        self.export_btn = ttk.Button(btn_frame, text="Export",
                                      style="Secondary.TButton",
                                      command=self._start_export)
        self.export_btn.pack(side=tk.LEFT, padx=(4, 0))

        self.show_backups_btn = ttk.Button(btn_frame, text="Show backups folder",
                                           style="Secondary.TButton",
                                           command=self._open_backups_folder)
        self.show_backups_btn.pack(side=tk.LEFT, padx=(4, 0))

        # ARM64 method (when fat binary)
        arm64_frame = ttk.Frame(card2_inner, style="Card.TFrame")
        arm64_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(arm64_frame, text="ARM64 (when fat):", style="Card.TLabel").pack(side=tk.LEFT)
        self.arm64_method_var = tk.StringVar(value="Patch (script)")
        self.arm64_combo = ttk.Combobox(
            arm64_frame, textvariable=self.arm64_method_var,
            values=["Patch (script)", "Skip ARM64"], state="readonly", width=18
        )
        self.arm64_combo.pack(side=tk.LEFT, padx=(8, 0))

        # ── Progress ────────────────────────────────────────────────────────
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            card2_inner, variable=self.progress_var,
            maximum=100, style="Green.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))

        self.progress_label = ttk.Label(card2_inner, text="Ready",
                                         style="Status.TLabel")
        self.progress_label.pack(anchor=tk.W, pady=(4, 0))

        # ── Log Output ──────────────────────────────────────────────────────
        card3 = ttk.Frame(main, style="Card.TFrame")
        card3.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
        card3_inner = ttk.Frame(card3, style="Card.TFrame")
        card3_inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        ttk.Label(card3_inner, text="Log Output",
                  style="CardHeader.TLabel").pack(anchor=tk.W)

        self.log_text = scrolledtext.ScrolledText(
            card3_inner, wrap=tk.WORD,
            bg=COLORS["bg_dark"], fg=COLORS["text_normal"],
            insertbackground=COLORS["text_normal"],
            font=("SF Mono", 10), relief=tk.FLAT,
            borderwidth=0, highlightthickness=0,
            height=12
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log_text.configure(state=tk.DISABLED)

        # Configure text tags for colored output
        self.log_text.tag_configure("ok", foreground=COLORS["green"])
        self.log_text.tag_configure("error", foreground=COLORS["red"])
        self.log_text.tag_configure("warn", foreground=COLORS["yellow"])
        self.log_text.tag_configure("info", foreground=COLORS["text_muted"])
        self.log_text.tag_configure("header", foreground=COLORS["blurple"],
                                     font=("SF Mono", 10, "bold"))

    # ═════════════════════════════════════════════════════════════════════════
    # UI Helpers
    # ═════════════════════════════════════════════════════════════════════════

    def _log(self, message, tag=None):
        """Thread-safe log to the text widget."""
        def _append():
            self.log_text.configure(state=tk.NORMAL)
            if tag:
                self.log_text.insert(tk.END, message + "\n", tag)
            else:
                # Auto-detect tag from message content
                if "[OK]" in message:
                    self.log_text.insert(tk.END, message + "\n", "ok")
                elif "[FAIL]" in message or "ERROR" in message:
                    self.log_text.insert(tk.END, message + "\n", "error")
                elif "[WARN]" in message or "WARNING" in message:
                    self.log_text.insert(tk.END, message + "\n", "warn")
                elif message.startswith("===") or message.startswith("---"):
                    self.log_text.insert(tk.END, message + "\n", "header")
                else:
                    self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(0, _append)

    def _set_progress(self, current, total):
        """Thread-safe progress update."""
        pct = (current / total) * 100 if total > 0 else 0
        self.root.after(0, lambda: self.progress_var.set(pct))
        self.root.after(0, lambda: self.progress_label.configure(
            text=f"Step {current}/{total} ({pct:.0f}%)"
        ))

    def _set_buttons_state(self, enabled):
        """Enable/disable all action buttons."""
        state = "normal" if enabled else "disabled"
        self.root.after(0, lambda: self.patch_btn.configure(state=state))
        self.root.after(0, lambda: self.restore_btn.configure(state=state))
        self.root.after(0, lambda: self.verify_btn.configure(state=state))
        self.root.after(0, lambda: self.export_btn.configure(state=state))
        self.root.after(0, lambda: self.show_backups_btn.configure(state=state))
        self.root.after(0, lambda: self.arm64_combo.configure(state="readonly" if enabled else "disabled"))

    def _update_status(self, text):
        self.root.after(0, lambda: self.status_label.configure(text=text))

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _get_node_path(self, silent=False):
        """Get the currently selected node path.
        If silent=True, return None without showing messagebox (for status checks).
        """
        val = self.selected_node.get()
        if not val:
            if not silent:
                messagebox.showwarning("No Installation",
                                       "Please select a Discord installation first.",
                                       parent=self.root)
            return None
        # Extract path from combo text (format: "Name — /path/to/node")
        if " — " in val:
            path = val.split(" — ", 1)[1]
        else:
            path = val
        if not os.path.isfile(path):
            if not silent:
                messagebox.showerror("File Not Found", f"Cannot find:\n{path}",
                                     parent=self.root)
            return None
        return path

    # ═════════════════════════════════════════════════════════════════════════
    # Discord Detection
    # ═════════════════════════════════════════════════════════════════════════

    def _scan_installations(self):
        self.discord_installations = self.engine.find_discord()
        values = [f"{name} — {path}" for name, path in self.discord_installations]
        self.install_combo["values"] = values

        if values:
            self.install_combo.current(0)
            self._on_install_selected()
        else:
            self._update_status("Status: No Discord installations found")

    def _browse_node(self):
        try:
            self.root.update_idletasks()
            path = filedialog.askopenfilename(
                parent=self.root,
                title="Select discord_voice.node",
                filetypes=[("Node Binary", "*.node"), ("All Files", "*.*")],
                initialdir=str(Path.home() / "Library" / "Application Support")
            )
        except Exception:
            return
        if path:
            self.discord_installations.append(("Custom", path))
            values = list(self.install_combo["values"])
            values.append(f"Custom — {path}")
            self.install_combo["values"] = values
            self.install_combo.set(f"Custom — {path}")
            self._on_install_selected()

    def _on_install_selected(self, event=None):
        path = self._get_node_path(silent=True)
        if path:
            status = self.engine.check_status(path)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            status_text = {
                "unpatched": "Unpatched (original)",
                "patched":   "Patched (stereo enabled)",
                "unknown":   "Unknown version (may not be compatible)",
                "error":     "Error reading file",
            }.get(status, status)
            self._update_status(f"Status: {status_text}  |  Size: {size_mb:.2f} MB")

    # ═════════════════════════════════════════════════════════════════════════
    # Patch Action
    # ═════════════════════════════════════════════════════════════════════════

    def _start_patch(self):
        node_path = self._get_node_path()
        if not node_path:
            return

        try:
            if not self.engine.check_compiler():
                messagebox.showerror(
                    "Compiler Not Found",
                    "clang++ is required for code injection.\n\n"
                    "Install Xcode Command Line Tools:\n"
                    "  xcode-select --install\n\n"
                    "Then restart this application.",
                    parent=self.root
                )
                return
        except Exception:
            messagebox.showerror("Error", "Could not check for compiler.",
                                 parent=self.root)
            return

        try:
            status = self.engine.check_status(node_path)
        except Exception:
            status = "unknown"

        if status == "patched":
            if not messagebox.askyesno("Already Patched",
                                        "This binary appears to already be patched.\n"
                                        "Re-apply patches?",
                                        parent=self.root):
                return
        elif status == "unknown":
            if not messagebox.askyesno("Unknown Version",
                                        "This binary version could not be verified.\n"
                                        "Offsets may not match. Continue anyway?",
                                        parent=self.root):
                return

        self._clear_log()
        self._set_buttons_state(False)

        # Extract name for backup
        val = self.selected_node.get()
        self.engine.discord_name = val.split(" — ")[0] if " — " in val else "Discord"

        def _do_patch():
            try:
                # Version branching: use adaptive patcher for non–0.0.376
                import re
                version_match = re.search(r"/([0-9]+\.[0-9]+\.[0-9]+)/modules/", node_path)
                discord_version = version_match.group(1) if version_match else None
                if discord_version and discord_version != "0.0.376":
                    self._log("=== Discord Stereo Patcher (adaptive) ===", "header")
                    self._log(f"  Module version {discord_version} detected — using adaptive patcher")
                    self._log("")
                    adaptive_script = Path(__file__).resolve().parent / "discord_stereo_adaptive_patch.py"  # same dir (patchers/)
                    if adaptive_script.exists():
                        self._log("Closing Discord...")
                        self.engine.kill_discord()
                        self._log("  [OK] Discord closed")
                        self._log("Running offset finder and applying patches...")
                        arm64_method = "skip" if (self.arm64_method_var.get() == "Skip ARM64") else "script"
                        proc = subprocess.run(
                            [sys.executable, str(adaptive_script), node_path, f"--arm64-method={arm64_method}"],
                            capture_output=True, text=True, timeout=300
                        )
                        for line in (proc.stdout or "").splitlines():
                            self._log(line)
                        for line in (proc.stderr or "").splitlines():
                            self._log(line, "error")
                        if proc.returncode == 0:
                            self._log("")
                            self._log("  [OK] Adaptive patch complete!", "header")
                            self.root.after(0, lambda: self.progress_label.configure(text="Adaptive patch complete!"))
                            self.root.after(100, lambda: self._ask_launch_discord())
                        else:
                            self._log(f"  [FAIL] Adaptive patcher exited with code {proc.returncode}", "error")
                        self._set_buttons_state(True)
                        self.root.after(0, lambda: self._on_install_selected())
                        return
                    self._log("  Adaptive patcher script not found; using fixed offsets (may fail).", "warn")
                    self._log("")

                self._log("=== Discord Stereo Patcher v{} ===".format(VERSION), "header")
                self._log("")

                # Backup
                self._log("Creating backup...")
                backup = self.engine.create_backup(node_path)
                self._log(f"  [OK] Backup: {os.path.basename(backup)}")
                self._log("")

                # Kill Discord
                self._log("Closing Discord...")
                self.engine.kill_discord()
                self._log("  [OK] Discord closed")
                self._log("")

                # Make writable
                os.chmod(node_path, 0o644)

                # Full patch
                arm64_method = "skip" if (self.arm64_method_var.get() == "Skip ARM64") else "script"
                ok, fail = self.engine.full_patch(node_path, self._set_progress, arm64_method=arm64_method)

                self._log("")
                self._log("=== RESULTS ===", "header")
                if fail == 0:
                    self._log(f"  [OK] All {ok} modifications applied successfully!")
                    self._log("")
                    self._log("Next steps:")
                    self._log("  1. Open Discord")
                    self._log("  2. Join a voice channel")
                    self._log("  3. Test stereo by hard-panning L/R in your DAW")
                    self.root.after(0, lambda: self.progress_label.configure(
                        text=f"Complete! {ok} patches applied."
                    ))
                else:
                    self._log(f"  [WARN] {ok} succeeded, {fail} failed", "warn")
                    self.root.after(0, lambda: self.progress_label.configure(
                        text=f"Done with errors: {ok} ok, {fail} failed"
                    ))

                # Ask to launch
                self.root.after(100, lambda: self._ask_launch_discord())

            except Exception as e:
                self._log(f"\n  [FAIL] Error: {e}", "error")
                self.root.after(0, lambda: self.progress_label.configure(
                    text="Error during patching"
                ))
            finally:
                self._set_buttons_state(True)
                self.root.after(0, lambda: self._on_install_selected())

        threading.Thread(target=_do_patch, daemon=True).start()

    def _ask_launch_discord(self):
        try:
            if messagebox.askyesno("Patching Complete", "Launch Discord now?",
                                    parent=self.root):
                subprocess.Popen(["open", "-a", "Discord"])
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════════════
    # Restore Action
    # ═════════════════════════════════════════════════════════════════════════

    def _start_restore(self):
        node_path = self._get_node_path()
        if not node_path:
            return

        try:
            backups = self.engine.list_backups()
        except Exception:
            backups = []

        if not backups:
            messagebox.showinfo("No Backups", "No backup files found.",
                                parent=self.root)
            return

        # Show backup selection dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Backup to Restore")
        dialog.geometry("550x350")
        dialog.configure(bg=COLORS["bg_dark"])
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Select a backup to restore:",
                  style="Dark.TLabel").pack(padx=16, pady=(16, 8), anchor=tk.W)

        listbox = tk.Listbox(
            dialog, bg=COLORS["bg_secondary"], fg=COLORS["text_normal"],
            font=("SF Mono", 10), selectbackground=COLORS["blurple"],
            relief=tk.FLAT, borderwidth=0, highlightthickness=0
        )
        listbox.pack(fill=tk.BOTH, expand=True, padx=16)

        for path, date, size in backups:
            listbox.insert(tk.END, f"  {date}  |  {size}  |  {os.path.basename(path)}")

        if backups:
            listbox.selection_set(0)

        def _do_restore():
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("No Selection", "Please select a backup.",
                                     parent=dialog)
                return
            backup_path = backups[sel[0]][0]
            dialog.destroy()

            self._clear_log()
            self._set_buttons_state(False)

            def _restore_thread():
                try:
                    self._log("=== Restoring from Backup ===", "header")
                    self._log(f"  Backup: {os.path.basename(backup_path)}")
                    self._log(f"  Target: {node_path}")
                    self._log("")

                    self._log("Closing Discord...")
                    self.engine.kill_discord()
                    self._log("  [OK] Discord closed")

                    self._log("Restoring file...")
                    self.engine.restore_backup(backup_path, node_path)
                    self._log("  [OK] Binary restored")
                    self._log("  [OK] Re-signed")
                    self._log("")
                    self._log("Restart Discord to use the original binary.")

                    self.root.after(0, lambda: self.progress_label.configure(
                        text="Restore complete!"
                    ))
                except Exception as e:
                    self._log(f"\n  [FAIL] Error: {e}", "error")
                finally:
                    self._set_buttons_state(True)
                    self.root.after(0, lambda: self._on_install_selected())

            threading.Thread(target=_restore_thread, daemon=True).start()

        btn_frame = ttk.Frame(dialog, style="Dark.TFrame")
        btn_frame.pack(fill=tk.X, padx=16, pady=12)
        ttk.Button(btn_frame, text="Restore", style="Accent.TButton",
                   command=_do_restore).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Cancel", style="Secondary.TButton",
                   command=dialog.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    # ═════════════════════════════════════════════════════════════════════════
    # Show backups folder
    # ═════════════════════════════════════════════════════════════════════════

    def _open_backups_folder(self):
        """Open the backups directory in Finder (macOS)."""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["open", str(BACKUP_DIR)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open backups folder:\n{e}",
                                 parent=self.root)

    # ═════════════════════════════════════════════════════════════════════════
    # Verify Action
    # ═════════════════════════════════════════════════════════════════════════

    def _start_verify(self):
        node_path = self._get_node_path()
        if not node_path:
            return

        self._clear_log()
        self._set_buttons_state(False)

        def _do_verify():
            try:
                self._log("=== Verifying Patch Status ===", "header")
                self._log("")

                fat_offset = self.engine.get_fat_offset(node_path)
                results = self.engine.verify_patches(node_path, fat_offset=fat_offset)
                passed = sum(1 for _, ok, _ in results if ok)
                failed = sum(1 for _, ok, _ in results if not ok)

                current_cat = None
                for desc, ok, category in results:
                    if category != current_cat:
                        self._log(f"\n--- {category} ---", "header")
                        current_cat = category
                    if ok:
                        self._log(f"  [OK] {desc}")
                    else:
                        self._log(f"  [FAIL] {desc}")

                self._log("")
                self._log(f"Result: {passed}/{len(results)} byte patches verified "
                           f"(+ 2 code injections not checked)")

                if failed == 0:
                    self._log("  All byte patches are applied!", "ok")
                else:
                    self._log(f"  {failed} patches are missing or incorrect", "warn")

                self.root.after(0, lambda: self.progress_label.configure(
                    text=f"Verify: {passed}/{len(results)} patches OK"
                ))
            except Exception as e:
                self._log(f"\n  [FAIL] Error: {e}", "error")
            finally:
                self._set_buttons_state(True)

        threading.Thread(target=_do_verify, daemon=True).start()

    # ═════════════════════════════════════════════════════════════════════════
    # Export Action
    # ═════════════════════════════════════════════════════════════════════════

    def _start_export(self):
        node_path = self._get_node_path()
        if not node_path:
            return

        try:
            if not self.engine.check_compiler():
                messagebox.showerror(
                    "Compiler Not Found",
                    "clang++ is required for export.\n\n"
                    "Install: xcode-select --install",
                    parent=self.root
                )
                return
        except Exception:
            messagebox.showerror("Error", "Could not check for compiler.",
                                 parent=self.root)
            return

        self.root.update_idletasks()
        export_dir = filedialog.askdirectory(
            parent=self.root,
            title="Select Export Directory",
            initialdir=str(Path.home() / "Desktop")
        )
        if not export_dir:
            return

        export_dir = os.path.join(export_dir, "DiscordStereoPatch_export")
        self._clear_log()
        self._set_buttons_state(False)

        val = self.selected_node.get()
        self.engine.discord_name = val.split(" — ")[0] if " — " in val else "Discord"

        def _do_export():
            try:
                self._log("=== Exporting Patched Binary ===", "header")
                self._log(f"  Source: {node_path}")
                self._log(f"  Export: {export_dir}")
                self._log("")

                result_dir = self.engine.export_patched(node_path, export_dir)

                self._log("")
                self._log("=== Export Complete ===", "header")
                self._log(f"  [OK] Files exported to: {result_dir}")
                self._log("  Contents:")
                self._log("    discord_voice.node      - Patched binary")
                self._log("    original_backup/        - Original binary")
                self._log("    INSTALL_GUIDE.txt       - Installation guide")

                self.root.after(0, lambda: self.progress_label.configure(
                    text="Export complete!"
                ))

                # Open in Finder
                def _open_finder():
                    try:
                        subprocess.Popen(["open", result_dir])
                    except Exception:
                        pass
                self.root.after(100, _open_finder)

            except Exception as e:
                self._log(f"\n  [FAIL] Error: {e}", "error")
            finally:
                self._set_buttons_state(True)

        threading.Thread(target=_do_export, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    root = tk.Tk()

    # macOS-specific tweaks
    if sys.platform == "darwin":
        # Note: moveableModal was removed — it causes crashes with messagebox/filedialog
        pass

    app = DiscordStereoPatcherGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
