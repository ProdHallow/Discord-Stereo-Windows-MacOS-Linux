# 🐧 Linux Patcher & Installer

**True stereo and high-bitrate voice for Discord on Linux**

![Linux](https://img.shields.io/badge/Linux-Active-00C853?style=flat-square)
![Focus](https://img.shields.io/badge/Focus-True%20Stereo%20Voice-5865F2?style=flat-square)

Part of the [Discord Audio Collective](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux) — unlocking **48kHz**, **400kbps**, and **true stereo** on Linux.

---

## 🎯 What This Does

| Before | After |
|:------:|:-----:|
| 24 kHz | **48 kHz** |
| ~64 kbps | **400 kbps** |
| Mono downmix | **True Stereo** |
| Aggressive filtering | **Filterless passthrough** |

---

## 📦 Two Ways to Patch

| Script | Description |
|--------|-------------|
| **discord_voice_patcher_linux.sh** | Compiles and applies patches at runtime. Supports custom gain (1–10x), multi-client detection, backup/restore. Requires a C++ compiler. |
| **Stereo-Installer-Linux.sh** | Downloads pre-patched voice modules from the repo and installs them. No compiler needed. Easiest option if your build is supported. |

Use the **Installer** for simplicity; use the **Patcher** for custom gain or when pre-patched binaries aren’t available for your Discord build.

---

## 🖥️ Supported Install Types

| Install type | Path (typical) |
|--------------|----------------|
| **Deb / native** | `~/.config/discord/`, `~/.config/discordcanary/`, `~/.config/discordptb/` |
| **Flatpak** | `~/.var/app/com.discordapp.Discord/config/discord/` |
| **Snap** | May be read-only; deb or Flatpak recommended for patching |

The patcher and installer auto-detect Discord Stable, Canary, and PTB in these locations.

---

## ⚙️ Requirements

**Patcher**
- **Bash** (re-execs as bash if invoked as sh)
- **C++ compiler:** `g++` or `clang++`

  ```bash
  # Ubuntu/Debian
  sudo apt install g++

  # Fedora/RHEL
  sudo dnf install gcc-c++

  # Arch
  sudo pacman -S gcc
  ```

**Installer**
- **Bash**, **curl**, **jq** (for GitHub API)
- No compiler required

---

## 🚀 Usage

### Patcher

```bash
chmod +x discord_voice_patcher_linux.sh
./discord_voice_patcher_linux.sh              # Patch with 1x gain
./discord_voice_patcher_linux.sh 3            # Patch with 3x gain
./discord_voice_patcher_linux.sh --restore    # Restore from backup
./discord_voice_patcher_linux.sh --help       # Full options
```

### Installer

```bash
chmod +x Stereo-Installer-Linux.sh
./Stereo-Installer-Linux.sh                   # Interactive mode
./Stereo-Installer-Linux.sh --silent          # Auto-fix all clients
./Stereo-Installer-Linux.sh --check           # Check status only
./Stereo-Installer-Linux.sh --restore         # Restore originals
./Stereo-Installer-Linux.sh --help            # Full options
```

---

## 📂 Repo Layout

| File | Purpose |
|------|---------|
| `discord_voice_patcher_linux.sh` | Runtime patcher (offsets + C++ compile + apply) |
| `Stereo-Installer-Linux.sh` | Download pre-patched modules and install |
| `README.md` | This file |

Pre-patched files for the installer are served from the main repo’s `Linux Patcher and Installer/discord_voice/` directory.

---

## ❓ FAQ

<details>
<summary><b>Discord updated and the patcher stopped working</b></summary>

Offsets are tied to a specific `discord_voice.node` build. When Discord updates, you need new offsets. Run the [offset finder](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux) on the new binary, copy the "COPY BELOW" block into the patcher script (replace EXPECTED_*, OFFSET_*, and ORIG_*), then re-run the patcher.
</details>

<details>
<summary><b>"No C++ compiler found"</b></summary>

The patcher compiles a small C++ binary at runtime. Install one:

```bash
# Ubuntu/Debian
sudo apt install g++

# Fedora/RHEL
sudo dnf install gcc-c++

# Arch
sudo pacman -S gcc
```
</details>

<details>
<summary><b>"Cannot open file" / Permission denied</b></summary>

The patcher needs write access to `discord_voice.node`. For user installs under `~/.config/` this is usually fine. If not:

```bash
chmod +w /path/to/discord_voice.node
# or run with sudo (use with care)
sudo ./discord_voice_patcher_linux.sh
```
</details>

<details>
<summary><b>"Binary validation failed — unexpected bytes at patch sites"</b></summary>

The binary doesn’t match the offsets in the script (different Discord build). Update the patcher with offsets from the [offset finder](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux) for your current build.
</details>

<details>
<summary><b>No Discord installations found</b></summary>

Make sure Discord has been run at least once so the voice module is downloaded. The patcher looks for `discord_voice.node` under:

- `~/.config/discord/`
- `~/.config/discordcanary/`
- `~/.config/discordptb/`
- `~/.var/app/com.discordapp.Discord/config/discord/` (Flatpak)

Join a voice channel briefly if the module folder is missing.
</details>

<details>
<summary><b>Flatpak / Snap permission issues</b></summary>

**Flatpak:** Paths under `~/.var/app/` are usually writable. If the script can’t find the node, run:

```bash
find ~/.var/app/com.discordapp.Discord -name "discord_voice.node"
```

**Snap:** Installations are often read-only. Prefer the deb or Flatpak Discord build for patching.
</details>

<details>
<summary><b>How do I restore / unpatch?</b></summary>

**Patcher:**

```bash
./discord_voice_patcher_linux.sh --restore
```

**Installer:**

```bash
./Stereo-Installer-Linux.sh --restore
```

You can also let Discord update; it will replace the voice module with a fresh copy.
</details>

---

## 🔗 Links

- **[Main repo](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux)** — Offset finder, Windows/macOS/Linux assets
- **[Voice Playground](https://discord-voice.xyz/)**

---

> ⚠️ **Disclaimer:** Provided as-is for research and experimentation. Use at your own risk. Not affiliated with Discord Inc.
