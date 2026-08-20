Discord Audio Collective - Discontinued

«[!IMPORTANT]
This project has been discontinued and is no longer maintained.»

As of August 2026, active development of Discord Audio Collective and the Discord Stereo patching tools has ended.

This repository will remain available as an archive for research, reference, and historical purposes, but users should not expect future updates, compatibility fixes, new offsets, patched "discord_voice.node" builds, or support for future Discord releases.

Why development ended

Discord's voice implementation changes frequently, and maintaining reliable patches across Windows, macOS, and Linux requires continuously reverse engineering new versions of "discord_voice.node".

I have decided to move away from actively reverse engineering Discord's audio node and focus my time on other projects.

The project accomplished what it originally set out to explore: modifying Discord's local voice processing to experiment with higher-quality, filterless, stereo audio.

What this means

- Stereo Hub is no longer maintained.
- Windows patchers are no longer maintained.
- Linux patchers are no longer maintained.
- macOS development and integration are no longer being pursued through this repository.
- Offset Finder updates are discontinued.
- New Discord versions may break existing patches at any time.
- Existing patched nodes may eventually become incompatible.
- Issues and pull requests may not receive responses.
- No compatibility with future Discord releases is promised.

Can I still use it?

Yes, if the existing tools still work with your version of Discord.

Everything in this repository is being left available for anyone interested in experimenting with it, studying the implementation, or building upon the research.

Use the existing tools at your own risk.

Discord updates can replace or change "discord_voice.node", and outdated binary patches may fail or behave unpredictably.

Forks and continued development

Anyone interested in continuing the project is welcome to fork the repository and build upon the existing work.

If another developer or community project continues this research, that project should be considered independent unless explicitly stated otherwise.

Thank you

Thank you to everyone who tested builds, reported offsets, contributed research, helped with macOS and Linux development, shared discoveries, or simply used the project.

Special thanks to the people and projects that contributed to or worked alongside Discord Audio Collective:

"Shaun (sh6un)" (https://github.com/sh6un) · "UnpackedX" (https://codeberg.org/UnpackedX) · "Voice Playground" (https://discord-voice.xyz/) · "Oracle" (https://github.com/oracle-dsc) · "Loof-sys" (https://github.com/LOOF-sys) · "Hallow" (https://github.com/ProdHallow) · "Ascend" (https://github.com/bloodybapestas) · BluesCat · "Sikimzo" (https://github.com/sikimzo) · "CRÜE" (https://codeberg.org/DiscordStereoPatcher-macOS) · "HorrorPills / Geeko" (https://github.com/HorrorPills)

What started as an experiment grew into a cross-platform effort involving reverse engineering, binary patching, tooling, testing, and a community interested in getting better audio out of Discord.

I appreciate everyone who was part of it.

---

Repository status

Status: 🛑 Discontinued / Archived
Maintenance: None
Future Discord compatibility: Not guaranteed
Support: No longer provided

«Disclaimer: This repository is preserved for research and experimentation. It is not affiliated with or endorsed by Discord Inc. Editing Discord client files may violate Discord's terms of service. Use at your own risk.»