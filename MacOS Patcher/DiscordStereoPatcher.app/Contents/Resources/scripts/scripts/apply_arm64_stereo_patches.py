#!/usr/bin/env python3
"""
Apply ARM64 stereo patches to a fat/universal discord_voice.node.
Used so Discord can run natively on Apple Silicon (M-series) without Rosetta.
Patches the ARM64 slice in-place; the x86_64 slice is patched by the main patcher.

Usage:
  python3 scripts/apply_arm64_stereo_patches.py <path_to_discord_voice.node>

Exits 0 if any arm64 patches were applied, 1 if not a fat binary or no patches found.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "finder"))

from discord_voice_node_offset_finder_v5 import find_macos_stereo_patches


def _hex_to_bytes(s):
    return bytes([int(b, 16) for b in s.split() if b])


def main():
    if len(sys.argv) < 2:
        print("Usage: apply_arm64_stereo_patches.py <path_to_discord_voice.node>", file=sys.stderr)
        sys.exit(1)
    node_path = Path(sys.argv[1])
    if not node_path.is_file():
        print(f"File not found: {node_path}", file=sys.stderr)
        sys.exit(1)

    data = bytearray(node_path.read_bytes())
    patches = find_macos_stereo_patches(data)
    arm64 = [p for p in patches if p.get("arch") == "arm64"]
    if not arm64:
        # Not fat or no arm64 slice
        sys.exit(1)

    applied = 0
    for p in arm64:
        fo = p["fat_offset"]
        orig = _hex_to_bytes(p["orig"])
        patch = _hex_to_bytes(p["patch"])
        if fo + len(patch) > len(data):
            continue
        if data[fo : fo + len(orig)] != orig:
            continue
        data[fo : fo + len(patch)] = patch
        applied += 1

    if applied > 0:
        node_path.write_bytes(data)
        print(f"  Applied {applied} ARM64 stereo patches (native Apple Silicon)")
    sys.exit(0 if applied > 0 else 1)


if __name__ == "__main__":
    main()
