# 🎙️ Discord Audio Collective

**Unlocking true stereo and high-bitrate voice across platforms**

![Focus](https://img.shields.io/badge/Focus-True%20Stereo%20Voice-5865F2?style=flat-square)
![Windows](https://img.shields.io/badge/Windows-Active-00C853?style=flat-square)
![macOS](https://img.shields.io/badge/macOS-WIP-FFA500?style=flat-square)
![Linux](https://img.shields.io/badge/Linux-WIP-FFA500?style=flat-square)

---

## 🎯 Our Mission

Enable **filterless true stereo** at **high bitrates** in Discord and beyond.

We analyze and improve stereo voice handling across Windows, macOS, and Linux — focusing on signal integrity, channel behavior, and real-time media experimentation.

---

## 🔬 What We Do

| Area | Focus |
|------|-------|
| **True Stereo Preservation** | Bypassing mono downmix, forcing 2-channel output |
| **Bitrate Unlocking** | Removing encoder caps, pushing to 512kbps Opus max |
| **Sample Rate Restoration** | Bypassing 24kHz limits → native 48kHz |
| **Filter Bypassing** | Disabling high-pass filters, DC rejection, gain processing |
| **Signal Integrity** | Clean passthrough without Discord's audio "enhancements" |

---

## 🖥️ Platform Status

| Platform | Status | Notes |
|----------|:------:|-------|
| **Windows** | ✅ Active | Full support |
| **macOS** | 🔧 WIP | In development |
| **Linux** | 🔧 WIP | In development |

---

## ✨ What We Unlock

| Before | After |
|:------:|:-----:|
| 24 kHz | **48 kHz** |
| ~64 kbps | **512 kbps** |
| Mono downmix | **True Stereo** |
| Aggressive filtering | **Filterless passthrough** |

---

## 🔩 How It Works

We patch Discord's `discord_voice.node` binary at specific memory offsets to bypass limitations:

</details>

---

## 📂 Repositories

- **[Discord-Node-Patcher-Feb-9-2026](https://github.com/ProdHallow/Discord-Node-Patcher-Feb-9-2026)** — Windows voice module patcher
- *macOS/Linux tools coming soon*

---

## 🤝 Partners

**UNP Beats UK / UnpackedX** • **HorrorPills** • **Shaun** • **Oracle** • **Loof-sys** • **Ascend** • **Sentry** • **Sikimzo** • **Hallow**

---

## 💬 Get Involved

Found new offsets? Have test results? Want to help reverse engineer macOS/Linux builds?

**We're always looking for contributors, testers, and audio nerds.**

---

> ⚠️ **Disclaimer:** Tools provided as-is for research and experimentation. Use at your own risk. Not affiliated with Discord Inc.

<div align="center">

**[Report Issue](https://github.com/ProdHallow/Discord-Node-Patcher-Feb-9-2026/issues)** • **[Join the Discussion](https://github.com/ProdHallow)**

</div>
