# 🎙️ Discord Audio Collective

**Unlocking true stereo and high-bitrate voice across platforms**

**⚠️ macOS installer is currently non-functional (placeholders/testing).**

![Focus](https://img.shields.io/badge/Focus-True%20Stereo%20Voice-5865F2?style=flat-square)
[![Voice Playground](https://img.shields.io/badge/Voice%20Playground-Labs-white?style=flat-square&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjEwIi8+PGxpbmUgeDE9IjIiIHkxPSIxMiIgeDI9IjIyIiB5Mj0iMTIiLz48cGF0aCBkPSJNMTIgMmExNS4zIDE1LjMgMCAwIDEgNCAxMCAxNS4zIDE1LjMgMCAwIDEtNCAxMCAxNS4zIDE1LjMgMCAwIDEtNC0xMCAxNS4zIDE1LjMgMCAwIDEgNC0xMHoiLz48L3N2Zz4=)](https://discord-voice.xyz/)
![Windows](https://img.shields.io/badge/Windows-Active-00C853?style=flat-square)
![macOS](https://img.shields.io/badge/MacOS-Active-00C853?style=flat-square)
![Linux](https://img.shields.io/badge/Linux-Active-00C853?style=flat-square)

---

## 🚀 v0.5 Release

The **v0.5** release is available on GitHub Releases:
- https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux/releases/tag/v0.5

**Included:** Windows patcher + installer, Linux patcher + installer, and the macOS patcher.  
**Not included:** macOS installer (still a placeholder).

> **macOS caution:** I have no way of testing the current macOS patcher as I don't own a Mac.  
> It might not actually enable stereo / influence stereo, and it may cause crashes when entering a voice channel (VC).  
> The macOS-side developers (**Geeko** and **Crüe**) are working to get the official release out in the coming weeks.

---

## 🙌 Special Thanks

> Massive shoutout to **Crüe and HorrorPills/Geeko** for their insane dedication and work on macOS.  
> The macOS build exists entirely because of their efforts and six months of relentless grinding.  
> As a two-person team, they put in immense time, energy, and commitment to make it happen. Absolute respect.

---

## 🎯 Our Mission

Enable **filterless true stereo** at **high bitrates** in Discord and beyond.

We analyze and improve stereo voice handling across Windows, macOS, and Linux — focusing on signal integrity, channel behavior, and real-time media experimentation.

---

## 🔬 What We Do

| Area | Focus |
|------|-------|
| **True Stereo Preservation** | Bypassing mono downmix, forcing 2-channel output |
| **Bitrate Unlocking** | Removing encoder caps, pushing to 400kbps Opus max |
| **Sample Rate Restoration** | Bypassing 24kHz limits → native 48kHz |
| **Filter Bypassing** | Disabling high-pass filters, DC rejection, gain processing |
| **Signal Integrity** | Clean passthrough without Discord's audio "enhancements" |

---

## 🖥️ Platform Status

| Platform | Status | Notes |
|----------|:------:|-------|
| **Windows** | ✅ Active | Full support — GUI patcher with multi-client detection |
| **macOS** | ✅ Active | Bash patcher with auto-detection, code signing handling, Apple Silicon support |
| **Linux** | ✅ Active | Bash patcher with auto-detection — deb, Flatpak, Snap supported |

---

## ✨ What We Unlock

| Before | After |
|:------:|:-----:|
| 24 kHz | **48 kHz** |
| ~64 kbps | **400 kbps** |
| Mono downmix | **True Stereo** |
| Aggressive filtering | **Filterless passthrough** |

---

## 📂 Repositories

| Repository | Description | Status |
|------------|-------------|:------:|
| **[Windows Patcher and Installer](./Windows%20Patcher%20and%20Installer/)** | Windows voice module patcher and installer | ✅ Active |
| **[macOS Patcher](./MacOS%20Patcher/)** | macOS voice module patcher | ✅ Active |
| **[Linux Patcher and Installer](./Linux%20Patcher%20and%20Installer/)** | Linux voice module patcher and installer | ✅ Active |

---

## ❓ FAQ

<details>
<summary><b>Discord updated and the patcher stopped working</b></summary>

This is expected. Discord ships a new `discord_voice.node` binary with most updates, which changes the internal layout the patcher targets. You'll need to wait for updated offsets to be published, then update the values in your patcher script and re-run it.

Check the repo for the latest offset updates after a Discord release.
</details>

<details>
<summary><b>"No C++ compiler found"</b></summary>

The patcher compiles a small C++ binary at runtime to apply patches. You need a compiler installed:

**Windows:** Install [Visual Studio](https://visualstudio.microsoft.com/) (Community is free — select "Desktop development with C++"), or install [MinGW-w64](https://www.mingw-w64.org/).

**Linux:**
```
Ubuntu/Debian:  sudo apt install g++
Fedora/RHEL:    sudo dnf install gcc-c++
Arch:           sudo pacman -S gcc
```

**macOS:**
```
xcode-select --install
```
This installs Xcode Command Line Tools which includes `clang++`.
</details>

<details>
<summary><b>"Cannot open file" / Permission denied</b></summary>

The patcher needs write access to `discord_voice.node`.

**Windows:** Right-click the patcher → **Run as Administrator**. The script auto-elevates, but if it fails, do it manually.

**Linux:** Most user installs (`~/.config/discord/`) are user-writable. If not:
```bash
sudo chmod +w /path/to/discord_voice.node
# or run the patcher with sudo
sudo ./discord_voice_patcher_linux.sh
```

**macOS:** Try `chmod +w` first. If that doesn't work, it may be a code signing or SIP issue:
```bash
codesign --remove-signature /path/to/discord_voice.node
```
</details>

<details>
<summary><b>"Binary validation failed — unexpected bytes at patch sites"</b></summary>

The patcher checks a few known byte sequences before writing anything. If they don't match, it means the `discord_voice.node` binary is from a different build than the offsets expect. This is a safety feature — it prevents corrupting the wrong binary.

**Fix:** Make sure you're using offsets that match your current Discord build. Check the repo for the latest updates.
</details>

<details>
<summary><b>"This file appears to already be patched"</b></summary>

The patcher detected its own patch bytes at the target locations. This is just a warning — it will re-patch anyway to ensure all 18 patches are applied consistently (useful if a partial patch happened previously).
</details>

<details>
<summary><b>No Discord installations found</b></summary>

The patcher scans standard install paths. If you installed Discord to a custom location, it won't be auto-detected.

**Windows:** Make sure Discord is installed via the official installer (checks `%LOCALAPPDATA%\Discord`).

**Linux:** Supported paths include `~/.config/discord`, `/opt/discord`, Flatpak (`~/.var/app/com.discordapp.Discord`), and Snap (`/snap/discord`).

**macOS:** Checks `~/Library/Application Support/discord` and `/Applications/Discord.app`.

If your install is somewhere else, you can manually point the compiled patcher at the `.node` file.
</details>

<details>
<summary><b>Audio sounds distorted / clipping</b></summary>

You're using too high a gain multiplier. The gain setting amplifies the raw audio samples — anything above **3x** can cause clipping on loud sources.

**Recommended:** Start at **1x** (no boost) or **2x**. Only go higher if your mic is very quiet. If you're already patched and hearing distortion, re-run the patcher with a lower gain value.
</details>

<details>
<summary><b>Does this work with BetterDiscord / Vencord / Equicord?</b></summary>

**Yes.** The Windows patcher auto-detects BetterDiscord, Vencord, Equicord, BetterVencord, and Lightcord. It patches the underlying `discord_voice.node` module, which is shared regardless of which client mod you use.

On Linux/macOS, as long as the mod uses the standard Electron module structure, the patcher will find the voice node.
</details>

<details>
<summary><b>Will this get my account banned?</b></summary>

This modifies client-side audio encoding behavior in the locally installed voice module. It does not interact with Discord's servers in any unauthorized way — it simply changes how your client encodes audio before sending it through the normal Opus pipeline. As of now, there have been **no known bans** from using this patcher.

That said, modifying Discord's files is technically against their Terms of Service. Use at your own discretion.
</details>

<details>
<summary><b>How do I restore / unpatch?</b></summary>

**Windows:** Run the patcher and click **Restore**, or run with `-Restore` flag. It will list your backups.

**Linux/macOS:**
```bash
./discord_voice_patcher_linux.sh --restore
./discord_voice_patcher_macos.sh --restore
```

You can also just **let Discord update** — any update will replace `discord_voice.node` with a fresh copy.
</details>

<details>
<summary><b>macOS: "Discord is damaged and can't be opened"</b></summary>

macOS quarantine flagging after patching. Fix:
```bash
xattr -cr /Applications/Discord.app
```
</details>

<details>
<summary><b>macOS: mmap fails / code signing errors</b></summary>

Patching invalidates the binary's code signature. The macOS patcher automatically re-signs with an ad-hoc signature, but if that fails:
```bash
codesign --remove-signature /path/to/discord_voice.node
# Then re-run the patcher
```
</details>

<details>
<summary><b>Linux: Flatpak / Snap permission issues</b></summary>

Flatpak and Snap sandboxing may prevent the patcher from writing to the voice module.

**Flatpak:**
```bash
# Find the actual path
find ~/.var/app/com.discordapp.Discord -name "discord_voice.node"
# Patch with explicit path if needed
```

**Snap:** Snap installs under `/snap/discord/current/` are read-only. You may need to copy the node file out, patch it, and copy it back, or use the deb install instead.
</details>

<details>
<summary><b>Does the other person need the patch too?</b></summary>

**No.** The patch modifies how *your* client encodes and sends audio. The receiving end just sees a standard (but higher quality) Opus stream. No changes needed on their side — they'll hear the improvement automatically.
</details>

<details>
<summary><b>What's the difference between the Installer and the Patcher?</b></summary>

- **[Windows Patcher and Installer folder](./Windows%20Patcher%20and%20Installer/)** includes the installer flow (`Stereo-Installer-Windows.bat`) for quick setup with no compiler.
- **[Windows Patcher and Installer folder](./Windows%20Patcher%20and%20Installer/)** also includes the runtime patcher flow (`Stereo-Node-Patcher-Windows.BAT`) for custom gain and latest-build flexibility.

Use the Installer for simplicity, the Patcher for flexibility.
</details>

---

<details>
<summary><h2>📋 Changelog</h2></summary>

### v6.0 — Cross-Platform Release (Feb 2026)
- 🧪 **Linux Beta Patcher** — native bash script, auto-detects deb/Flatpak/Snap installs
- 🧪 **macOS Beta Patcher** — native bash script, handles code signing, Apple Silicon (Rosetta) support
- Platform-specific patch bytes (r12 vs r13 register, je vs jne branch, Clang vs MSVC prologue)
- POSIX file I/O (mmap/msync) for Linux/macOS patchers
- Cross-platform process management and client detection

### v5.0 — Multi-Client & GUI Patcher (Feb 2026)
- Multi-client detection (Stable, Canary, PTB, Development, BetterDiscord, Vencord, Equicord, etc.)
- GUI patcher with slider-based gain control, backup/restore, auto-relaunch
- Auto-updater with version comparison and downgrade prevention
- User config persistence (remembers last gain, backup preference)

### v4.0 — Encoder Config Init (Feb 2026)
- Patched both Opus encoder config constructors (`EncoderConfigInit1`, `EncoderConfigInit2`)
- Prevents bitrate reset between encoder creation and first `SetBitrate` call
- Duplicate bitrate path patching (`DuplicateEmulateBitrateModified`)

### v3.0 — Full Stereo Pipeline (Jan 2026)
- Complete stereo enforcement: `CreateAudioFrameStereo`, `SetChannels`, `MonoDownmixer`
- Bitrate unlock to 400kbps across all encoder paths
- 48kHz sample rate restoration
- High-pass filter bypass with function body injection
- `ConfigIsOk` override and `ThrowError` suppression
- Configurable audio gain (1–10x) via compiled amplifier injection

### v2.0 — Initial Patcher (Jan 2026)
- Basic binary patching for stereo and bitrate
- Single-client support
- Manual offset entry

### v1.0 — Proof of Concept (Dec 2025)
- Manual hex editing guide
- Initial Windows PE binary research

</details>

---

<details>
<summary><h2>🧬 Technical Deep Dive</h2></summary>

### Architecture Overview

The patcher operates by modifying Discord's `discord_voice.node` — a native Node.js addon (shared library) that contains the Opus encoder pipeline, audio preprocessing, and WebRTC integration. The binary is compiled from C++ and ships as a PE DLL (Windows), ELF shared object (Linux), or Mach-O dylib (macOS).

The patching workflow:

```
Patcher (Bash/PowerShell)
┌──────────────────────────┐
│ Read offsets from config  │
│ Generate C++ source       │
│ Compile amplifier +       │
│   patcher binary          │
│ Execute against binary    │
│ Write patched bytes       │
└──────────────────────────┘
```

### The 18 Patch Targets

Each patch modifies a specific behavior in the voice encoding pipeline:

| # | Target | What It Does | Patch |
|---|--------|-------------|-------|
| 1 | `CreateAudioFrameStereo` | Allocates audio frame buffer — forces stereo channel count in the frame metadata | `mov r13,rax; nop` (Win) / `mov r12,rax; nop` (Linux/macOS) |
| 2 | `AudioEncoderOpusConfigSetChannels` | Opus config channel setter — overwrite immediate operand to `2` | `0x02` |
| 3 | `MonoDownmixer` | Mixes stereo→mono before encoding — NOP sled + unconditional jump bypasses the entire function | 12× `NOP` + `JMP` |
| 4 | `EmulateStereoSuccess1` | Stereo capability check return value — force to `2` (stereo) | `0x02` |
| 5 | `EmulateStereoSuccess2` | Conditional branch after stereo check — patch to unconditional jump | `JMP` (`0xEB`) — Win: was `JNE`, Linux/macOS: was `JE` |
| 6 | `EmulateBitrateModified` | Bitrate calculation result — overwrite with 400000 (`0x061A80`) | `0x80 0x1A 0x06` |
| 7 | `SetsBitrateBitrateValue` | Bitrate storage — write 400000 as 32-bit LE value | `0x80 0x1A 0x06 0x00 0x00` |
| 8 | `SetsBitrateBitwiseOr` | Bitwise OR that caps bitrate — NOP to prevent clamping | 3× `NOP` |
| 9 | `Emulate48Khz` | `cmovb` that clamps sample rate to 24kHz — NOP to allow 48kHz passthrough | 3× `NOP` |
| 10 | `HighPassFilter` | Entry point of HP filter function — replace with ret (Linux/macOS) or `mov rax, <addr>; ret` stub (Windows) | `RET` / 11-byte stub |
| 11 | `HighpassCutoffFilter` | HP filter body — overwrite 0x100 bytes with compiled `hp_cutoff()` function | Compiled function body |
| 12 | `DcReject` | DC rejection filter body — overwrite 0x1B6 bytes with compiled `dc_reject()` function | Compiled function body |
| 13 | `DownmixFunc` | Downmix processing function — immediate `RET` to skip entirely | `0xC3` |
| 14 | `AudioEncoderOpusConfigIsOk` | Config validation — return `1` unconditionally | `mov rax,1; ret` (Win) / `ret` (Linux/macOS) |
| 15 | `ThrowError` | Error throwing function — immediate `RET` suppresses encoder errors | `0xC3` |
| 16 | `DuplicateEmulateBitrateModified` | Parallel bitrate calculation path — same 400kbps patch as #6 | `0x80 0x1A 0x06` |
| 17 | `EncoderConfigInit1` | First Opus config constructor — init bitrate to 400kbps instead of 32kbps | `0x80 0x1A 0x06 0x00` |
| 18 | `EncoderConfigInit2` | Second Opus config constructor — same init patch | `0x80 0x1A 0x06 0x00` |

### Platform Differences

The same 18 patches exist on all platforms, but the binary format and compiler toolchain create differences:

| Aspect | Windows (PE) | Linux (ELF) | macOS (Mach-O) |
|--------|:----------:|:-----------:|:-------------:|
| **Compiler** | MSVC | Clang | Clang |
| **Calling convention** | rcx, rdx, r8, r9 | rdi, rsi, rdx, rcx | rdi, rsi, rdx, rcx |
| **File offset adjustment** | VA − 0xC00 | 0 (VA = file offset) | VA − (−0x4000) |
| **Image base** | `0x180000000` | 0 (PIE) | 0 (PIE) |
| **CreateAudioFrameStereo** | `mov r13,rax` | `mov r12,rax` | `mov r12,rax` |
| **EmulateStereoSuccess1 original** | `0x01` | `0x00` | `0x00` |
| **EmulateStereoSuccess2 original** | `JNE (0x75)` | `JE (0x74)` | `JE (0x74)` |
| **DownmixFunc prologue** | `push r14 (0x41)` | `push rbp (0x55)` | `push rbp (0x55)` |
| **ConfigIsOk patch** | 8-byte `mov rax,1; ret` | 1-byte `ret` | 1-byte `ret` |
| **HighPassFilter patch** | 11-byte stub (`mov rax,<VA>; ret`) | 1-byte `ret` | 1-byte `ret` |

### Amplifier Injection

The `hp_cutoff` and `dc_reject` functions are compiled separately as a C++ translation unit, then their compiled machine code is copied byte-for-byte into the binary at the corresponding function offsets. This effectively replaces Discord's filter implementations with custom versions that:

1. Write specific values to the Opus encoder state struct (disabling internal filtering)
2. Apply a simple gain multiplier: `out[i] = in[i] * (channels + Multiplier)`

The `Multiplier` value is `gain - 2`, where `gain` is the user's selected multiplier. At `1x`, the multiplier is `-1`, which combined with `channels` (2 for stereo) gives `1.0x` — unity gain, no amplification.

On Windows, the compiled function bodies need to be position-independent since they're injected at a fixed VA. On Linux/macOS (PIE binaries), the compiler naturally generates position-independent code.

### Why Not Just Hex Edit?

Manual hex editing works for a one-off patch, but breaks the moment Discord updates (which happens frequently and silently). The patcher architecture solves this by:

1. **Compiled injection** — the amplifier functions are compiled natively, ensuring correct ABI and optimization
2. **Validation** — byte-level checks before writing prevent corrupting the wrong binary
3. **Backup/restore** — automatic backup management so you can always roll back

</details>

---

## 🤝 Partners

- **[Shaun (sh6un)](https://github.com/sh6un)**
- **[UnpackedX](https://codeberg.org/UnpackedX)** - [Voice Playgrounds Site](https://discord-voice.xyz/) and **[Codeberg](https://codeberg.org/UnpackedX)**
- **[Oracle (oracle-dsc)](https://github.com/oracle-dsc)**
- **[Loof-sys](https://github.com/LOOF-sys)**
- **[HorrorPills / Geeko](https://github.com/HorrorPills)** and **[Codeberg](https://codeberg.org/HorrorPills)**
- **[Hallow](https://github.com/ProdHallow)**
- **[Ascend](https://github.com/bloodybapestas)**
- BluesCat
- **[Sentry](https://github.com/sentry1000)**
- **[Sikimzo](https://github.com/sikimzo)**
- THE MF GOAT **CRÜE**
- THE OTHER GOAT **Geeko**

---

## 💬 Get Involved

Found new offsets? Have test results? Want to help reverse engineer macOS/Linux builds?

**We're always looking for contributors, testers, and audio nerds.**

---

> ⚠️ **Disclaimer:** Tools provided as-is for research and experimentation. Use at your own risk. Not affiliated with Discord Inc.

<div align="center">

**[Report Issue](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux/issues)** • **[Join the Development Discord](https://discord.gg/gDY6F8RAfM)**

</div>
