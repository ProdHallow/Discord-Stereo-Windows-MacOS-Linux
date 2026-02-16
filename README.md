🎙️ Discord Audio Collective  
Unlocking true stereo and high-bitrate voice across platforms  

🎯 Our Mission  
Enable filterless true stereo at high bitrates in Discord and beyond.  
We analyze and improve stereo voice handling across Windows, macOS, and Linux — focusing on signal integrity, channel behavior, and real-time media experimentation.

🔬 What We Do  

| Area Focus              | Description                                                                 |
|-------------------------|-----------------------------------------------------------------------------|
| True Stereo Preservation| Bypassing mono downmix, forcing 2-channel output                           |
| Bitrate Unlocking       | Removing encoder caps, pushing to 512kbps Opus max                          |
| Sample Rate Restoration | Bypassing 24kHz limits → native 48kHz                                       |
| Filter Bypassing        | Disabling high-pass filters, DC rejection, gain processing                  |
| Signal Integrity        | Clean passthrough without Discord's audio "enhancements"                    |

🖥️ Platform Status  

| Platform | Status    | Notes                                                                 |
|----------|-----------|-----------------------------------------------------------------------|
| Windows  | ✅ Active | Full support — GUI patcher with multi-client detection               |
| macOS    | 🧪 Beta   | Bash patcher with auto-detection, code signing handling, Apple Silicon support |
| Linux    | 🧪 Beta   | Bash patcher with auto-detection — deb, Flatpak, Snap supported      |

✨ What We Unlock  

**Before** → **After**  
24 kHz → 48 kHz  
~64 kbps → 512 kbps  
Mono downmix → True Stereo  
Aggressive filtering → Filterless passthrough  

📂 Repositories  

| Repository                  | Description                                      | Status   |
|-----------------------------|--------------------------------------------------|----------|
| Discord-Node-Patcher        | Windows voice module patcher                     | ✅ Active |
| Discord-Stereo-Installer    | Pre-patched binaries & installer                 | ✅ Active |
| macOS Beta Patcher          | macOS voice module patcher                       | 🧪 Beta  |
| Linux Beta Patcher          | Linux voice module patcher                       | 🧪 Beta  |

❓ FAQ  

<details>  
<summary><b>"No C++ compiler found"</b></summary>  
The patcher compiles a small C++ binary at runtime to apply patches. You need a compiler installed:  

**Windows:** Install Visual Studio (Community is free — select "Desktop development with C++"), or install MinGW-w64.  

**Linux:**  
```bash
Ubuntu/Debian:  sudo apt install g++  
Fedora/RHEL:    sudo dnf install gcc-c++  
Arch:           sudo pacman -S gcc  
```  

**macOS:**  
```bash
xcode-select --install  
```  
This installs Xcode Command Line Tools which includes clang++.  
</details>  

<details>  
<summary><b>"Cannot open file" / Permission denied</b></summary>  
The patcher needs write access to discord_voice.node.  

**Windows:** Right-click the patcher → Run as Administrator. The script auto-elevates, but if it fails, do it manually.  

**Linux:** Most user installs (~/.config/discord/) are user-writable. If not:  
```bash
sudo chmod +w /path/to/discord_voice.node  
# or run the patcher with sudo  
sudo ./discord_voice_patcher_linux.sh  
```  

**macOS:** Try chmod +w first. If that doesn't work, it may be a code signing or SIP issue:  
```bash
codesign --remove-signature /path/to/discord_voice.node  
```  
</details>  

<details>  
<summary><b>"Binary validation failed — unexpected bytes at patch sites"</b></summary>  
The patcher checks a few known byte sequences before writing anything. If they don't match, it means the discord_voice.node binary is from a different build than expected. This is a safety feature — it prevents corrupting the wrong binary.  
Fix: Obtain updated patch information compatible with your build and try again.  
</details>  

<details>  
<summary><b>"This file appears to already be patched"</b></summary>  
The patcher detected its own patch bytes at the target locations. This is just a warning — it will re-patch anyway to ensure all 18 patches are applied consistently (useful if a partial patch happened previously).  
</details>  

<details>  
<summary><b>No Discord installations found</b></summary>  
The patcher scans standard install paths. If you installed Discord to a custom location, it won't be auto-detected.  

**Windows:** Make sure Discord is installed via the official installer (checks %LOCALAPPDATA%\Discord).  
**Linux:** Supported paths include ~/.config/discord, /opt/discord, Flatpak (~/.var/app/com.discordapp.Discord), and Snap (/snap/discord).  
**macOS:** Checks ~/Library/Application Support/discord and /Applications/Discord.app.  

If your install is somewhere else, you can manually point the compiled patcher at the .node file.  
</details>  

<details>  
<summary><b>Audio sounds distorted / clipping</b></summary>  
You're using too high a gain multiplier. The gain setting amplifies the raw audio samples — anything above 3x can cause clipping on loud sources.  
Recommended: Start at 1x (no boost) or 2x. Only go higher if your mic is very quiet. If you're already patched and hearing distortion, re-run the patcher with a lower gain value.  
</details>  

<details>  
<summary><b>Does this work with BetterDiscord / Vencord / Equicord?</b></summary>  
Yes. The Windows patcher auto-detects BetterDiscord, Vencord, Equicord, BetterVencord, and Lightcord. It patches the underlying discord_voice.node module, which is shared regardless of which client mod you use.  
On Linux/macOS, as long as the mod uses the standard Electron module structure, the patcher will find the voice node.  
</details>  

<details>  
<summary><b>Will this get my account banned?</b></summary>  
This modifies client-side audio encoding behavior in the locally installed voice module. It does not interact with Discord's servers in any unauthorized way — it simply changes how your client encodes audio before sending it through the normal Opus pipeline. As of now, there have been no known bans from using this patcher.  
That said, modifying Discord's files is technically against their Terms of Service. Use at your own discretion.  
</details>  

<details>  
<summary><b>How do I restore / unpatch?</b></summary>  
**Windows:** Run the patcher and click Restore, or run with -Restore flag. It will list your backups.  

**Linux/macOS:**  
```bash
./discord_voice_patcher_linux.sh --restore  
./discord_voice_patcher_macos.sh --restore  
```  
You can also just let Discord update — any update will replace discord_voice.node with a fresh copy.  
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

**Snap:** Snap installs under /snap/discord/current/ are read-only. You may need to copy the node file out, patch it, and copy it back, or use the deb install instead.  
</details>  

<details>  
<summary><b>Does the other person need the patch too?</b></summary>  
No. The patch modifies how your client encodes and sends audio. The receiving end just sees a standard (but higher quality) Opus stream. No changes needed on their side — they'll hear the improvement automatically.  
</details>  

<details>  
<summary><b>What's the difference between the Installer and the Patcher?</b></summary>  

* Discord-Stereo-Installer provides pre-patched discord_voice.node binaries. Download and drop in — no compiler needed. Windows only.  

* Discord-Node-Patcher compiles and applies patches at runtime. Supports custom gain, multi-client detection, and works even if the pre-patched binary isn't available yet for your build.  

Use the Installer for simplicity, the Patcher for flexibility.  
</details>  

<details>  
<summary><h2>📋 Changelog</h2></summary>  
v6.0 — Cross-Platform Release (Feb 2026)  

* 🧪 Linux Beta Patcher — native bash script, auto-detects deb/Flatpak/Snap installs  
* 🧪 macOS Beta Patcher — native bash script, handles code signing, Apple Silicon (Rosetta) support  
* Platform-specific patch bytes (r12 vs r13 register, je vs jne branch, Clang vs MSVC prologue)  
* POSIX file I/O (mmap/msync) for Linux/macOS patchers  
* Cross-platform process management and client detection  

v5.0 — Multi-Client (Feb 2026)  

* Multi-client detection (Stable, Canary, PTB, Development, BetterDiscord, Vencord, Equicord, etc.)  
* GUI patcher with slider-based gain control, backup/restore, auto-relaunch  
* Auto-updater with version comparison and downgrade prevention  
* User config persistence (remembers last gain, backup preference)  

v4.0 — Encoder Config Init (Feb 2026)  

* Patched both Opus encoder config constructors (EncoderConfigInit1, EncoderConfigInit2)  
* Prevents bitrate reset between encoder creation and first SetBitrate call  
* Duplicate bitrate path patching (DuplicateEmulateBitrateModified)  

v3.0 — Full Stereo Pipeline (Jan 2026)  

* Complete stereo enforcement: CreateAudioFrameStereo, SetChannels, MonoDownmixer  
* Bitrate unlock to 512kbps across all encoder paths  
* 48kHz sample rate restoration  
* High-pass filter bypass with function body injection  
* ConfigIsOk override and ThrowError suppression  
* Configurable audio gain (1–10x) via compiled amplifier injection  

v2.0 — Initial Patcher (Jan 2026)  

* Basic binary patching for stereo and bitrate  
* Single-client support  

v1.0 — Proof of Concept (Dec 2025)  

* Manual hex editing guide  
* Initial offset discovery for Windows PE binary  
</details>  

<details>  
<summary><h2>🧬 Technical Deep Dive</h2></summary>  
Architecture Overview  
The patcher operates by modifying Discord's discord_voice.node — a native Node.js addon (shared library) that contains the Opus encoder pipeline, audio preprocessing, and WebRTC integration. The binary is compiled from C++ and ships as a PE DLL (Windows), ELF shared object (Linux), or Mach-O dylib (macOS).  

The 18 Patch Targets  
Each patch modifies a specific behavior in the voice encoding pipeline:  

1. CreateAudioFrameStereo — forces stereo channel count in the frame metadata  
2. AudioEncoderOpusConfigSetChannels — overwrite immediate operand to 2  
3. MonoDownmixer — NOP sled + unconditional jump bypasses the entire function  
4. EmulateStereoSuccess1 — force to 2 (stereo)  
5. EmulateStereoSuccess2 — patch to unconditional jump  
6. EmulateBitrateModified — overwrite with 512000  
7. SetsBitrateBitrateValue — write 512000 as 32-bit LE value  
8. SetsBitrateBitwiseOr — NOP to prevent clamping  
9. Emulate48Khz — NOP to allow 48kHz passthrough  
10. HighPassFilter — replace with ret / stub  
11. HighpassCutoffFilter — overwrite with compiled hp_cutoff() function  
12. DcReject — overwrite with compiled dc_reject() function  
13. DownmixFunc — immediate RET to skip entirely  
14. AudioEncoderOpusConfigIsOk — return 1 unconditionally  
15. ThrowError — immediate RET suppresses encoder errors  
16. DuplicateEmulateBitrateModified — same 512kbps patch as #6  
17. EncoderConfigInit1 — init bitrate to 512kbps  
18. EncoderConfigInit2 — same init patch  

(Platform differences in calling conventions, file offsets, register usage, etc. remain as in the original — omitted here for brevity but can be re-added if needed.)

Amplifier Injection  
The hp_cutoff and dc_reject functions are compiled separately as a C++ translation unit, then their compiled machine code is copied byte-for-byte into the binary at the corresponding function offsets. This effectively replaces Discord's filter implementations with custom versions that disable internal filtering and apply a configurable gain multiplier.

Why Not Just Hex Edit?  
Manual hex editing works for a one-off patch, but breaks the moment Discord updates (which happens frequently and silently). The patcher solves this through automated application, compiled injection, validation, and backup/restore features.

</details>  

🤝 Partners  

* Shaun (sh6un)  
* UnpackedX (FxMDev) - discord-voice.xyz  
* Oracle (oracle-dsc)  
* Loof-sys  
* HorrorPills  
* Hallow  
* Ascend  
* BluesCat  
* Sentry  
* Sikimzo  

💬 Get Involved  
Found test results? Want to help reverse engineer macOS/Linux builds?  
We're always looking for contributors, testers, and audio nerds.  

⚠️ Disclaimer: Tools provided as-is for research and experimentation. Use at your own risk. Not affiliated with Discord Inc.

<div align="center">  
Report Issue • Join the Discussion  
</div>
