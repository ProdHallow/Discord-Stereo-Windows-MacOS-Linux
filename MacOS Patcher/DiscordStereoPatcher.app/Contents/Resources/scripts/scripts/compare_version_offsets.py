#!/usr/bin/env python3
"""
Run the offset finder on two discord_voice.node binaries and compare file_offsets.
Useful to see how Discord changed between versions (e.g. 0.0.376 vs 0.0.377).

Usage:
  python scripts/compare_version_offsets.py <path_to_node_v1> <path_to_node_v2>
  python scripts/compare_version_offsets.py  (uses version dumps if present)

Output: JSON exports for both + a diff of file_offsets (and patches array).
"""

import sys
import json
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
FINDER = REPO_ROOT / "finder" / "discord_voice_node_offset_finder_v5.py"
DUMPS = REPO_ROOT / "Original Discord Modules Folder Dumps by Version"


def run_finder(node_path, out_json_path):
    """Run offset finder --export; return (success, data)."""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(FINDER), "--export", str(out_json_path), str(node_path)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return False, None
    try:
        with open(out_json_path, "r", encoding="utf-8") as f:
            return True, json.load(f)
    except (json.JSONDecodeError, OSError):
        return False, None


def main():
    if len(sys.argv) >= 3:
        path_a, path_b = sys.argv[1], sys.argv[2]
    else:
        # Try version dumps
        a_dir = DUMPS / "0.0.376 modules folder macOS"
        b_dir = next((p for p in DUMPS.iterdir() if p.is_dir() and "0.0.377" in p.name), None)
        if not a_dir.is_dir() or not b_dir:
            print("Usage: python compare_version_offsets.py <node_v1> <node_v2>", file=sys.stderr)
            print("Or add version dumps and run from repo root.", file=sys.stderr)
            sys.exit(1)
        path_a = a_dir / "modules" / "discord_voice" / "discord_voice.node"
        path_b = b_dir / "modules" / "discord_voice" / "discord_voice.node"
        if not path_a.is_file() or not path_b.is_file():
            print("discord_voice.node not found in version dumps. Run copy_discord_voice_to_version_dump.sh first.", file=sys.stderr)
            sys.exit(1)
        path_a, path_b = str(path_a), str(path_b)

    path_a = Path(path_a)
    path_b = Path(path_b)
    if not path_a.is_file() or not path_b.is_file():
        print("Both paths must be existing files.", file=sys.stderr)
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        json_a = f.name
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        json_b = f.name
    try:
        ok_a, data_a = run_finder(path_a, json_a)
        ok_b, data_b = run_finder(path_b, json_b)
        if not ok_a:
            print("Offset finder failed on first file.", file=sys.stderr)
            sys.exit(1)
        if not ok_b:
            print("Offset finder failed on second file.", file=sys.stderr)
            sys.exit(1)

        off_a = data_a.get("file_offsets") or {}
        off_b = data_b.get("file_offsets") or {}
        all_names = sorted(set(off_a) | set(off_b))

        print("File offsets comparison (hex)")
        print("  Name                                  |  File A      |  File B      |  Delta")
        print("  " + "-" * 85)
        for name in all_names:
            a = off_a.get(name)
            b = off_b.get(name)
            if isinstance(a, str):
                a = int(a, 16)
            if isinstance(b, str):
                b = int(b, 16)
            a_str = f"0x{a:X}" if a is not None else "—"
            b_str = f"0x{b:X}" if b is not None else "—"
            delta = (b - a) if (a is not None and b is not None) else None
            d_str = f"{delta:+d}" if delta is not None else "—"
            print(f"  {name:<38} |  {a_str:>10}  |  {b_str:>10}  |  {d_str}")

        print("")
        print(f"  JSON A: {json_a}")
        print(f"  JSON B: {json_b}")
    finally:
        Path(json_a).unlink(missing_ok=True)
        Path(json_b).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
