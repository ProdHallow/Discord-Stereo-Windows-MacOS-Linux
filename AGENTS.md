# AGENTS.md

## Cursor Cloud specific instructions

This is **not** a web app or service — it is a collection of standalone desktop tools (PowerShell, Bash, Python) that binary-patch Discord's native `discord_voice.node` module. There are no servers, databases, Docker containers, or package managers (`package.json` files in the repo are Discord module metadata, not project deps).

### Key tools and how to exercise them

| Tool | Path | Run |
|---|---|---|
| **Offset Finder CLI** | `Updates/Offset Finder/discord_voice_node_offset_finder_v5.py` | `python3 <path> <discord_voice.node>` (needs a real binary; exits cleanly with an error if none provided) |
| **Offset Finder GUI** | `Updates/Offset Finder/offset_finder_gui.py` | `python3 <path>` (requires display / tkinter) |
| **Linux Patcher** | `Updates/Linux/Updates/discord_voice_patcher_linux.sh` | `bash <path> --help` (requires Discord installed to actually patch) |
| **Linux Launcher** | `Updates/Linux/discord-stereo-launcher.sh` | `bash <path> --help` |
| **Linux Installer GUI** | `Updates/Linux/Updates/Discord_Stereo_Installer_For_Linux.py` | `python3 <path>` (requires display / tkinter + bash scripts alongside) |

### Linting

- **Shell scripts:** `shellcheck Updates/Linux/Updates/discord_voice_patcher_linux.sh` and `shellcheck Updates/Linux/discord-stereo-launcher.sh`. Existing warnings are informational (SC2034, SC2015, SC2012, SC2155) — not errors.
- **Python scripts:** `python3 -m py_compile <path>` for syntax checking. All three `.py` files compile cleanly.

### Build / compile verification

The patcher compiles C++ at runtime. To verify the toolchain works:
```bash
g++ -O2 -std=c++17 -c <amplifier.cpp> -o /dev/null
```
Both `g++` and `clang++` are available in the environment.

### Required system packages

- `python3`, `python3-tk` (for GUI tools), `shellcheck` (for linting)
- `g++` or `clang++` (for the patcher's runtime C++ compilation)
- `networkx`, `matplotlib` (optional Python packages for offset finder visualization)

### Important caveats

- The tools **cannot run end-to-end** without a Discord desktop client installed and a real `discord_voice.node` binary present. The `--help` and syntax-check paths are the appropriate "hello world" for this codebase in a headless cloud VM.
- The `Voice Node Dump/` directory contains archived module trees for research — these are metadata files, not the actual `.node` binaries (those are too large for git).
- Windows scripts (`.ps1`, `.bat`) are not testable on Linux.
