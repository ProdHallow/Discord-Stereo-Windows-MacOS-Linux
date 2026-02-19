# macOS Patcher

**True stereo and high-bitrate voice for Discord on macOS**

![macOS](https://img.shields.io/badge/MacOS-Active-00C853?style=flat-square)
![Focus](https://img.shields.io/badge/Focus-True%20Stereo%20Voice-5865F2?style=flat-square)

Part of the [Discord Audio Collective](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux) - unlocking **48kHz**, **384kbps**, and **true stereo** on macOS (Intel and Apple Silicon via Rosetta).

---

## Special Thanks

> Massive shoutout to **Crue and HorrorPills/Geeko** for their insane dedication and work on macOS.  
> The macOS build exists entirely because of their efforts and six months of relentless grinding.  
> As a two-person team, they put in immense time, energy, and commitment to make it happen. Absolute respect.

---

## What This Does

| Before | After |
|:------:|:-----:|
| 24 kHz | **48 kHz** |
| ~64 kbps | **384 kbps** |
| Mono downmix | **True Stereo** |
| Aggressive filtering | **Filterless passthrough** |

---

## Requirements

- **Bash** (macOS default is fine)
- **C++ compiler:** Xcode Command Line Tools (includes `clang++`)

  ```bash
  xcode-select --install
  ```

---

## Usage

```bash
chmod +x discord_voice_patcher_macos.sh
./discord_voice_patcher_macos.sh              # Patch with 1x gain
./discord_voice_patcher_macos.sh 3            # Patch with 3x gain
./discord_voice_patcher_macos.sh --restore    # Restore from backup
./discord_voice_patcher_macos.sh --help       # Full options
```

---

## Supported Paths

The patcher looks for `discord_voice.node` under:

| Client | Typical path |
|--------|--------------|
| **Discord** | `~/Library/Application Support/discord/` |
| **Discord Canary** | `~/Library/Application Support/discordcanary/` |
| **Discord PTB** | `~/Library/Application Support/discordptb/` |

It scans versioned app directories and the `discord_voice` module folder automatically.

---

## Repo Layout

| File | Purpose |
|------|---------|
| `discord_voice_patcher_macos.sh` | Runtime patcher (offsets + C++ compile + apply, code signing handling) |
| `README.md` | This file |

Offsets are for a specific Discord build; when Discord updates, update the script with new offsets from the [offset finder](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux).

---

## FAQ

<details>
<summary><b>Discord updated and the patcher stopped working</b></summary>

Offsets are tied to a specific `discord_voice.node` build. When Discord updates, you need new offsets. Run the [offset finder](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux) on the new binary, copy the macOS patcher block into this script, then re-run the patcher.
</details>

<details>
<summary><b>"No C++ compiler found"</b></summary>

Install Xcode Command Line Tools:

```bash
xcode-select --install
```

This provides `clang++` used by the patcher.
</details>

<details>
<summary><b>"Cannot open file" / Permission denied</b></summary>

Ensure the script can write to the voice module. If needed:

```bash
chmod +w /path/to/discord_voice.node
```

If patching or code signing fails:

```bash
codesign --remove-signature /path/to/discord_voice.node
# Then re-run the patcher
```
</details>

<details>
<summary><b>"Binary validation failed - unexpected bytes at patch sites"</b></summary>

The binary doesn't match the offsets in the script (different Discord build). Update the patcher with offsets from the [offset finder](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux) for your current build.
</details>

<details>
<summary><b>"Discord is damaged and can't be opened"</b></summary>

macOS quarantine flag after patching. Clear extended attributes:

```bash
xattr -cr /Applications/Discord.app
```
</details>

<details>
<summary><b>mmap fails / code signing errors</b></summary>

Patching invalidates the binary's code signature. The patcher tries to re-sign with an ad-hoc signature. If that fails:

```bash
codesign --remove-signature /path/to/discord_voice.node
# Then re-run the patcher
```
</details>

<details>
<summary><b>No Discord installations found</b></summary>

Ensure Discord is installed in the usual location and has been run at least once so the voice module is present. Paths checked:

- `~/Library/Application Support/discord/`
- `~/Library/Application Support/discordcanary/`
- `~/Library/Application Support/discordptb/`
- `/Applications/Discord.app`
</details>

<details>
<summary><b>How do I restore / unpatch?</b></summary>

```bash
./discord_voice_patcher_macos.sh --restore
```

You can also let Discord update; it will replace the voice module with a fresh copy.
</details>

---

## Links

- **[Main repo](https://github.com/ProdHallow/Discord-Stereo-Windows-MacOS-Linux)** - Offset finder, Windows/Linux/macOS assets
- **[Voice Playground](https://discord-voice.xyz/)**

---

> WARNING: **Disclaimer:** Provided as-is for research and experimentation. Use at your own risk. Not affiliated with Discord Inc.
