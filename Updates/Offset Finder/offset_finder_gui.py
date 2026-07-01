#!/usr/bin/env python3
"""Tk GUI for discord_voice_node_offset_finder_v5.py (copy blocks for Windows/Linux/macOS)."""

import os
import sys
import shutil
import atexit
import threading
from datetime import datetime
from pathlib import Path
import importlib.util
import io

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext
except ImportError:  # pragma: no cover
    tk = None  # type: ignore[assignment, misc]
    ttk = filedialog = scrolledtext = None  # type: ignore[assignment]

sys.dont_write_bytecode = True

VERSION = "1.2.0"
SCRIPT_DIR = Path(__file__).parent
DEBUG_MODE = os.environ.get("OFFSET_FINDER_DEBUG", "").lower() in ("1", "true", "yes") or "--debug" in sys.argv


def _cleanup_pycache() -> None:
    """Remove `__pycache__` entries near this script (keeps packaged zips tidy)."""
    for d in SCRIPT_DIR.glob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


atexit.register(_cleanup_pycache)


def _hub_scripts_cache_dir() -> Path | None:
    """If Stereo Hub synced the finder, it may live here (same layout as discord_stereo_hub_DEV.hub_scripts_dir)."""
    try:
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            p = Path(base) / "DiscordStereoHub" / "scripts"
        else:
            p = Path.home() / ".cache" / "DiscordStereoHub" / "scripts"
        return p if p.is_dir() else None
    except Exception:
        return None


def _finder_script_search_dirs() -> list[Path]:
    """Prefer OFFSET FINDER/LATEST; also Stereo Hub cache when manifest synced the .py there."""
    dirs = [SCRIPT_DIR]
    hub_scripts = _hub_scripts_cache_dir()
    if hub_scripts and hub_scripts != SCRIPT_DIR:
        dirs.append(hub_scripts)
    return dirs



THEME = {
    "BG": "#1e1e1e",
    "BG_LIGHT": "#2d2d2d",
    "BG_INPUT": "#1a1a1a",
    "FG": "#e0e0e0",
    "FG_DIM": "#888888",
    "FG_ACCENT": "#ffffff",
    "BORDER": "#3a3a3a",
    "GREEN": "#4caf50",
    "GREEN_HOVER": "#66bb6a",
    "BLUE": "#2196f3",
    "BLUE_HOVER": "#42a5f5",
    "ORANGE": "#ff9800",
    "GRAY_BTN": "#555555",
    "GRAY_HOVER": "#666666",
    "RED": "#f44336",
    "YELLOW": "#fdd835",
    "CYAN": "#4dd0e1",
    "SELECT_BG": "#0d47a1",
}

BG = THEME["BG"]
BG_LIGHT = THEME["BG_LIGHT"]
BG_INPUT = THEME["BG_INPUT"]
FG = THEME["FG"]
FG_DIM = THEME["FG_DIM"]
FG_ACCENT = THEME["FG_ACCENT"]
BORDER = THEME["BORDER"]
GREEN = THEME["GREEN"]
GREEN_HOVER = THEME["GREEN_HOVER"]
BLUE = THEME["BLUE"]
BLUE_HOVER = THEME["BLUE_HOVER"]
ORANGE = THEME["ORANGE"]
GRAY_BTN = THEME["GRAY_BTN"]
GRAY_HOVER = THEME["GRAY_HOVER"]
RED = THEME["RED"]
YELLOW = THEME["YELLOW"]
CYAN = THEME["CYAN"]
SELECT_BG = THEME["SELECT_BG"]



def _ascii_safe(s: str | bytes) -> str:
    """ASCII-only text for clipboard / patcher blocks."""
    if not s:
        return ""
    if isinstance(s, bytes):
        s = s.decode("utf-8", errors="replace")
    return s.encode("ascii", errors="replace").decode("ascii")


class OffsetFinderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Offset Finder" + (" [DEBUG]" if DEBUG_MODE else ""))
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(620, 640)
        self.root.geometry("660x750")

        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        self.finder_module = None
        self.running = False
        self.file_path = tk.StringVar()
        self.os_var = tk.StringVar(value="Auto-Detect")
        self.status_var = tk.StringVar(value="Ready")
        self.last_output = ""
        self.last_windows_block = ""
        self.last_linux_block = ""
        self.last_macos_block = ""

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._load_finder()

    def _build_ui(self):
        title_frame = tk.Frame(self.root, bg=BG)
        title_frame.pack(fill="x", padx=16, pady=(14, 0))

        tk.Label(title_frame, text="Offset Finder", font=("Segoe UI", 20, "bold"),
                 bg=BG, fg=FG_ACCENT).pack()
        tk.Label(title_frame, text="Made by: Oracle | Shaun | Hallow | Ascend | Sikimzo | Cypher | Crue | Geeko",
                 font=("Segoe UI", 8), bg=BG, fg=FG_DIM).pack()
        tk.Label(title_frame, text=f"v{VERSION}",
                 font=("Segoe UI", 8), bg=BG, fg=FG_DIM).pack()

        sel_frame = tk.LabelFrame(self.root, text=" Binary Selection ",
                                  font=("Segoe UI", 9, "bold"),
                                  bg=BG_LIGHT, fg=FG, bd=1, relief="groove",
                                  highlightbackground=BORDER, highlightthickness=1)
        sel_frame.pack(fill="x", padx=16, pady=(12, 0), ipady=4)

        os_row = tk.Frame(sel_frame, bg=BG_LIGHT)
        os_row.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(os_row, text="Target OS:", font=("Segoe UI", 9),
                 bg=BG_LIGHT, fg=FG, width=10, anchor="w").pack(side="left")
        self.os_combo = ttk.Combobox(os_row, textvariable=self.os_var,
                                     values=["Auto-Detect", "Windows", "Linux", "macOS"],
                                     state="readonly", width=20)
        self.os_combo.pack(side="left", padx=(4, 0))

        os_hint = tk.Label(os_row, text="(auto-detects PE/ELF/Mach-O)",
                           font=("Segoe UI", 8), bg=BG_LIGHT, fg=FG_DIM)
        os_hint.pack(side="left", padx=(8, 0))

        file_row = tk.Frame(sel_frame, bg=BG_LIGHT)
        file_row.pack(fill="x", padx=10, pady=(4, 8))
        tk.Label(file_row, text="Node File:", font=("Segoe UI", 9),
                 bg=BG_LIGHT, fg=FG, width=10, anchor="w").pack(side="left")

        self.file_entry = tk.Entry(file_row, textvariable=self.file_path,
                                   font=("Consolas", 9), bg=BG_INPUT, fg=FG,
                                   insertbackground=FG, relief="flat", bd=0,
                                   highlightbackground=BORDER, highlightthickness=1)
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(4, 6), ipady=3)

        self.browse_btn = tk.Button(file_row, text="Browse...",
                                    font=("Segoe UI", 9), bg=GRAY_BTN, fg=FG,
                                    activebackground=GRAY_HOVER, activeforeground=FG,
                                    relief="flat", bd=0, padx=12, pady=2,
                                    cursor="hand2", command=self._browse_file)
        self.browse_btn.pack(side="right")

        opt_frame = tk.LabelFrame(self.root, text=" Options ",
                                  font=("Segoe UI", 9, "bold"),
                                  bg=BG_LIGHT, fg=FG, bd=1, relief="groove",
                                  highlightbackground=BORDER, highlightthickness=1)
        opt_frame.pack(fill="x", padx=16, pady=(10, 0), ipady=4)

        self.save_json = tk.BooleanVar(value=True)
        self.verbose = tk.BooleanVar(value=False)

        opts_inner = tk.Frame(opt_frame, bg=BG_LIGHT)
        opts_inner.pack(fill="x", padx=10, pady=(6, 6))

        left_opts = tk.Frame(opts_inner, bg=BG_LIGHT)
        left_opts.pack(side="left", anchor="nw")
        right_opts = tk.Frame(opts_inner, bg=BG_LIGHT)
        right_opts.pack(side="left", anchor="nw", padx=(30, 0))

        for var, text, parent in [
            (self.save_json, "Save JSON offsets file", left_opts),
            (self.verbose, "Verbose output", right_opts),
        ]:
            cb = tk.Checkbutton(parent, text=text, variable=var,
                                font=("Segoe UI", 9), bg=BG_LIGHT, fg=FG,
                                selectcolor=BG_INPUT, activebackground=BG_LIGHT,
                                activeforeground=FG, highlightthickness=0,
                                bd=0, anchor="w")
            cb.pack(anchor="w", pady=1)

        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(side="bottom", fill="x", padx=16, pady=(8, 14))

        status_frame = tk.Frame(self.root, bg=BG_LIGHT, height=24)
        status_frame.pack(side="bottom", fill="x", padx=16, pady=(6, 0))
        self.status_label = tk.Label(status_frame, textvariable=self.status_var,
                                     font=("Segoe UI", 8), bg=BG_LIGHT, fg=FG_DIM,
                                     anchor="w")
        self.status_label.pack(fill="x", padx=6, pady=2)

        output_frame = tk.Frame(self.root, bg=BG)
        output_frame.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        self.output = scrolledtext.ScrolledText(
            output_frame, font=("Consolas", 9), bg=BG_INPUT, fg=FG,
            insertbackground=FG, relief="flat", bd=0, wrap="word",
            highlightbackground=BORDER, highlightthickness=1, state="disabled")
        self.output.pack(fill="both", expand=True)

        self.output.tag_config("pass", foreground=GREEN)
        self.output.tag_config("fail", foreground=RED)
        self.output.tag_config("warn", foreground=YELLOW)
        self.output.tag_config("info", foreground=CYAN)
        self.output.tag_config("header", foreground=ORANGE, font=("Consolas", 9, "bold"))
        self.output.tag_config("success", foreground=GREEN, font=("Consolas", 10, "bold"))

        self.run_btn = self._make_button(btn_frame, "Find Offsets", GREEN, GREEN_HOVER,
                                         self._run_finder)
        self.run_btn.pack(side="left", padx=(0, 6))

        self.copy_btn = self._make_button(btn_frame, "Copy Output", BLUE, BLUE_HOVER,
                                          self._copy_output)
        self.copy_btn.pack(side="left", padx=(0, 6))

        self.copy_block_btn = self._make_button(btn_frame, "Copy Block", BLUE, BLUE_HOVER,
                                                self._copy_block)
        self.copy_block_btn.pack(side="left", padx=(0, 6))

        self.save_btn = self._make_button(btn_frame, "Save Results", GRAY_BTN, GRAY_HOVER,
                                          self._save_results)
        self.save_btn.pack(side="left", padx=(0, 6))

        self.clear_btn = self._make_button(btn_frame, "Clear", GRAY_BTN, GRAY_HOVER,
                                           self._clear_output)
        self.clear_btn.pack(side="left")

        self._append_output("  Drop a discord_voice.node file or click Browse to begin.\n", "info")

        try:
            self.root.drop_target_register('DND_Files')
            self.root.dnd_bind('<<Drop>>', self._on_drop)
        except Exception:
            pass

    def _make_button(self, parent, text, bg_color, hover_color, command):
        btn = tk.Button(parent, text=text, font=("Segoe UI", 9, "bold"),
                        bg=bg_color, fg="#ffffff",
                        activebackground=hover_color, activeforeground="#ffffff",
                        relief="flat", bd=0, padx=16, pady=6,
                        cursor="hand2", command=command)
        btn.bind("<Enter>", lambda e, b=btn, c=hover_color: b.configure(bg=c))
        btn.bind("<Leave>", lambda e, b=btn, c=bg_color: b.configure(bg=c))
        return btn

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select discord_voice.node",
            filetypes=[
                ("Node binary", "*.node"),
                ("All files", "*.*"),
            ])
        if path:
            self.file_path.set(path)
            self._auto_detect_os(path)
            self._run_finder()

    def _auto_detect_os(self, path):
        try:
            with open(path, "rb") as f:
                magic = f.read(4)
            if magic[:2] == b"MZ":
                self.os_var.set("Windows")
            elif magic == b"\x7fELF":
                self.os_var.set("Linux")
            elif magic in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                           b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
                           b"\xca\xfe\xba\xbe"):
                self.os_var.set("macOS")
            else:
                self.os_var.set("Auto-Detect")
        except Exception:
            pass

    def _on_drop(self, event):
        path = event.data.strip("{}")
        self.file_path.set(path)
        self._auto_detect_os(path)
        self._run_finder()

    def _clear_output(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self.last_output = ""
        self.last_windows_block = ""
        self.last_linux_block = ""
        self.last_macos_block = ""

    def _copy_output(self):
        text = self.last_output.strip()
        if not text:
            text = self.output.get("1.0", "end").strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(_ascii_safe(text))
            self.status_var.set("Output copied to clipboard")

    def _copy_block(self):
        block = (self.last_windows_block or self.last_linux_block or self.last_macos_block or "").strip()
        if not block:
            self.status_var.set("No patcher block to copy (run Find Offsets first)")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(_ascii_safe(block))
        if self.last_macos_block and block == self.last_macos_block.strip():
            self.status_var.set("macOS block copied — paste into MacOS_ARM64_Patcher.py region")
        elif self.last_linux_block and block == self.last_linux_block.strip():
            self.status_var.set("Linux block copied — paste into discord_voice_patcher_linux.sh")
        elif self.last_windows_block and block == self.last_windows_block.strip():
            self.status_var.set("Windows block copied — paste into Discord_voice_node_patcher.ps1")
        else:
            self.status_var.set("Block copied (paste into patcher)")

    def _save_results(self):
        text = self.last_output.strip()
        if not text:
            text = self.output.get("1.0", "end").strip()
        if not text:
            self.status_var.set("Nothing to save")
            return
        path = filedialog.asksaveasfilename(
            title="Save Results",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            self.status_var.set(f"Saved to {path}")

    def _load_finder(self):
        finder_path = None
        self_name = Path(__file__).name
        for search_dir in _finder_script_search_dirs():
            if not search_dir.is_dir():
                continue

            named = sorted(
                (f for f in search_dir.glob("discord_voice_node_offset_finder*.py")
                 if f.name != self_name),
                reverse=True,
            )
            if named:
                finder_path = named[0]
                break

            for f in sorted(search_dir.glob("*.py"), reverse=True):
                if f.name == self_name:
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    if (
                        "Discord Voice Node Offset Finder" in text
                        or "discord_voice.node offset finder" in text
                        or ("SIGNATURES" in text and "VERSION" in text and "discover_offsets" in text)
                    ):
                        finder_path = f
                        break
                except Exception:
                    continue
            if finder_path:
                break

        if finder_path and finder_path.exists():
            spec = importlib.util.spec_from_file_location("offset_finder", finder_path)
            self.finder_module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(self.finder_module)
                ver = getattr(self.finder_module, "VERSION", "?")
                self.status_var.set(f"Loaded: {finder_path.name} (v{ver}) from {finder_path.parent.name}/")
            except Exception as e:
                self.status_var.set(f"Error loading finder: {e}")
                self.finder_module = None
        else:
            self.status_var.set("Warning: no offset finder .py (place v5 next to this GUI or sync via Stereo Hub)")

    def _run_finder(self):
        if self.running:
            return

        path = self.file_path.get().strip()
        if not path:
            self._append_output("  [ERROR] No file selected. Browse for a discord_voice.node file.\n", "fail")
            return
        if not os.path.isfile(path):
            self._append_output(f"  [ERROR] File not found: {path}\n", "fail")
            return

        self._load_finder()
        if self.finder_module is None:
            self._append_output("  [ERROR] Offset finder script not loaded.\n", "fail")
            self._append_output(
                "  Put discord_voice_node_offset_finder_v5.py in OFFSET FINDER/LATEST or sync it via Stereo Hub / manifest.\n",
                "info",
            )
            return

        self.running = True
        self.run_btn.configure(state="disabled", bg=GRAY_BTN)
        self._clear_output()

        fsize = os.path.getsize(path)
        fname = os.path.basename(path)
        self._append_output(f"  File: {fname}\n", "header")
        self._append_output(f"  Size: {fsize:,} bytes | OS: {self.os_var.get()}\n", "info")
        self._append_output(f"  {'-' * 55}\n\n", "info")

        thread = threading.Thread(target=self._run_finder_thread, args=(path,), daemon=True)
        thread.start()

    def _run_finder_thread(self, path):
        try:
            mod = self.finder_module
            with open(path, "rb") as f:
                data = f.read()

            bin_info = mod.detect_binary_format(data)
            fmt = bin_info.get("format", "unknown")
            arch = bin_info.get("arch", "unknown")
            verbose = self.verbose.get()
            is_macho = fmt == "macho"

            if verbose:
                self._append_output_safe(f"  Format: {fmt.upper()} | Arch: {arch}\n", "info")
                if is_macho and arch == "arm64" and bin_info.get("has_symbols"):
                    nsyms = len(bin_info.get("func_symbols", {}))
                    self._append_output_safe(
                        f"  ARM64 slice: {bin_info.get('fat_size', 0):,} bytes | "
                        f"{nsyms} symbols\n", "info")
                elif is_macho and bin_info.get("intel_unsupported"):
                    self._append_output_safe(
                        "  WARNING: Intel-only Mach-O — ARM64 slice required for macOS patching\n", "warn")
                elif bin_info.get("has_symbols") and not is_macho:
                    nsyms = len(bin_info.get("func_symbols", {}))
                    self._append_output_safe(f"  Symbols: {nsyms} functions found\n", "info")
                self._append_output_safe("\n  Scanning for offsets...\n\n", "header")

            old_stdout = sys.stdout
            capture = io.StringIO()
            sys.stdout = capture

            try:
                results, errors, adj, tiers_used = mod.discover_offsets(data, bin_info, verbose=verbose)
            finally:
                sys.stdout = old_stdout

            captured = capture.getvalue()
            if verbose:
                for line in captured.splitlines():
                    tag = None
                    if "[PASS]" in line:
                        tag = "pass"
                    elif "[FAIL]" in line:
                        tag = "fail"
                    elif "[WARN]" in line:
                        tag = "warn"
                    elif "[INFO]" in line or "[SKIP]" in line or "[HEUR]" in line:
                        tag = "info"
                    elif line.strip().startswith("PHASE") or line.strip().startswith("==="):
                        tag = "header"
                    self._append_output_safe(line + "\n", tag)

            found = len(results)
            patcher_names = getattr(mod, "PATCHER_OFFSET_NAMES", None)
            patcher_names_u = list(dict.fromkeys(patcher_names)) if patcher_names else []
            is_pe = fmt == "pe"
            is_macho = fmt == "macho"
            is_elf = fmt == "elf"
            stereo_patches = []
            macos_st = None
            if is_macho and hasattr(mod, "find_macos_stereo_patches"):
                stereo_patches = mod.find_macos_stereo_patches(data)
                if hasattr(mod, "_macos_stereo_patch_stats"):
                    macos_st = mod._macos_stereo_patch_stats(stereo_patches)
            if is_pe and patcher_names_u and hasattr(mod, "count_patcher_offsets_found"):
                patcher_count, n_patcher = mod.count_patcher_offsets_found(results)
            elif is_pe and patcher_names_u:
                patcher_count = sum(1 for k in patcher_names_u if k in results)
                n_patcher = len(patcher_names_u)
            else:
                patcher_count = found
                _fallback_n = len(getattr(mod, "PATCHER_OFFSET_NAMES", []) or [])
                n_patcher = len(patcher_names_u) if patcher_names_u else (_fallback_n if _fallback_n else 18)
            linux_st = None
            if is_elf and hasattr(mod, "resolve_linux_patcher_offsets"):
                linux_off = mod.resolve_linux_patcher_offsets(results, data, bin_info)
                linux_st = mod._linux_patcher_stats(linux_off)
            if is_macho and macos_st:
                n_expected = macos_st["arm64_expected"]
                found = macos_st["arm64_found"]
            elif is_elf and linux_st:
                n_expected = linux_st["expected"]
                found = linux_st["found"]
            else:
                n_expected = n_patcher

            try:
                xval = mod._cross_validate(results, adj, data, tiers_used=tiers_used, bin_fmt=fmt)
            except Exception:
                xval = []

            if verbose:
                self._append_output_safe(f"\n  {'=' * 55}\n", "header")
                self._append_output_safe("  RESULTS SUMMARY\n", "header")
                self._append_output_safe(f"  {'=' * 55}\n", "header")
                if is_pe and patcher_names_u:
                    self._append_output_safe(
                        f"  Windows patcher:   {patcher_count} / {n_patcher}  (required for Discord_voice_node_patcher.ps1)\n", "info")
                    self._append_output_safe(
                        f"  x86_64 discovered: {found} offsets\n", "info")
                    if patcher_count == n_patcher:
                        self._append_output_safe(
                            f"  [OK] ALL {n_patcher} WINDOWS PATCHER OFFSETS FOUND\n", "success")
                    else:
                        self._append_output_safe(
                            f"  Windows patcher: {patcher_count}/{n_patcher} ({n_patcher - patcher_count} missing)\n", "warn")
                elif is_macho and macos_st:
                    self._append_output_safe(
                        f"  ARM64 patcher: {macos_st['arm64_found']}/{macos_st['arm64_expected']} "
                        f"(MacOS_ARM64_Patcher.py)\n",
                        "success" if macos_st["arm64_found"] == macos_st["arm64_expected"] else "warn",
                    )
                    if macos_st.get("arm64_missing"):
                        self._append_output_safe(
                            f"  Missing ARM64 sites: {', '.join(macos_st['arm64_missing'])}\n", "warn")
                elif is_elf and linux_st:
                    self._append_output_safe(
                        f"  Linux patcher: {linux_st['found']}/{linux_st['expected']} "
                        f"(discord_voice_patcher_linux.sh)\n",
                        "success" if linux_st["found"] == linux_st["expected"] else "warn",
                    )
                    if linux_st.get("missing"):
                        self._append_output_safe(
                            f"  Missing: {', '.join(linux_st['missing'])}\n", "warn")
                else:
                    if found == n_expected:
                        self._append_output_safe(
                            f"  [OK] ALL {found}/{n_expected} x86_64 OFFSETS FOUND SUCCESSFULLY\n", "success")
                    else:
                        self._append_output_safe(
                            f"  x86_64: Found {found}/{n_expected} offsets ({n_expected - found} missing)\n", "warn")
                if errors:
                    for e in errors:
                        if isinstance(e, (list, tuple)) and len(e) >= 2:
                            self._append_output_safe(f"  Missing: {e[0]}: {e[1]}\n", "fail")
                        else:
                            self._append_output_safe(f"  Missing: {e}\n", "fail")
                if xval:
                    for w in xval:
                        self._append_output_safe(f"  [XVAL] {w}\n", "warn")
                else:
                    self._append_output_safe("  Cross-validation: clean\n", "pass")

            file_size = len(data)

            if verbose and fmt == "pe" and hasattr(mod, "run_bitrate_audit_pe"):
                ts = bin_info.get("text_section")
                t_start = ts["raw_offset"] if ts else 0
                t_end = (ts["raw_offset"] + ts["raw_size"]) if ts else len(data)
                old_stdout = sys.stdout
                audit_out = io.StringIO()
                sys.stdout = audit_out
                try:
                    mod.run_bitrate_audit_pe(data, results, adj, t_start, t_end)
                finally:
                    sys.stdout = old_stdout
                for line in audit_out.getvalue().splitlines():
                    tag = "header" if "====" in line or "BITRATE" in line else ("warn" if "uncovered" in line else None)
                    self._append_output_safe(line + "\n", tag)

            if not verbose and is_pe:
                self._append_output_safe(
                    f"  {patcher_count} / {n_patcher}  (required for Discord_voice_node_patcher.ps1)\n", "info"
                )
                self._append_output_safe(f"  x86_64 discovered: {found} offsets\n", "info")
                if patcher_count == n_patcher:
                    self._append_output_safe(
                        f"  [OK] ALL {n_patcher} WINDOWS PATCHER OFFSETS FOUND\n", "success"
                    )
                else:
                    self._append_output_safe(f"  *** PARTIAL: {patcher_count}/{n_patcher} ***\n", "warn")
                self._append_output_safe("  Cross-validation: clean\n" if not xval else f"  Cross-validation: {len(xval)} issue(s)\n", "pass" if not xval else "warn")

            if not verbose and not is_pe:
                if is_elf and linux_st:
                    tag = "success" if linux_st["found"] == linux_st["expected"] else "warn"
                    self._append_output_safe(
                        f"  Linux patcher: {linux_st['found']}/{linux_st['expected']}\n", tag)
                elif is_macho and macos_st:
                    tag = "success" if macos_st["arm64_found"] == macos_st["arm64_expected"] else "warn"
                    self._append_output_safe(
                        f"  ARM64 patcher: {macos_st['arm64_found']}/{macos_st['arm64_expected']}\n", tag)
                elif found == n_expected:
                    self._append_output_safe(f"  [OK] ALL {found}/{n_expected} offsets found\n", "success")
                else:
                    self._append_output_safe(f"  Found {found}/{n_expected} offsets\n", "warn" if found < n_expected else "info")
                self._append_output_safe("  Cross-validation: clean\n" if not xval else f"  Cross-validation: {len(xval)} issue(s)\n", "pass" if not xval else "warn")

            if fmt == "pe" and hasattr(mod, "format_windows_patcher_block"):
                block = mod.format_windows_patcher_block(results, bin_info, path, file_size)
                if block:
                    self.last_windows_block = _ascii_safe(block)
                    self.last_linux_block = ""
                    self.last_macos_block = ""
                else:
                    self.last_windows_block = ""
                if block:
                    if verbose:
                        self._append_output_safe("\n", None)
                        self._append_output_safe("  " + "=" * 55 + "\n", "header")
                        self._append_output_safe("  COPY BELOW -> Discord_voice_node_patcher.ps1\n", "header")
                        self._append_output_safe("  " + "=" * 55 + "\n\n", "header")
                    self._append_output_safe("--- BEGIN COPY (Windows) ---\n", None)
                    self._append_output_safe(block if block.endswith("\n") else block + "\n", None)
                    self._append_output_safe("--- END COPY ---\n\n", None)
                    if verbose and hasattr(mod, "format_windows_debug_mode"):
                        self._append_output_safe("  DEBUG MODE (patch names)\n", "header")
                        self._append_output_safe("  " + "-" * 55 + "\n", "header")
                        self._append_output_safe(mod.format_windows_debug_mode(results) + "\n\n", None)

            if verbose and is_elf and linux_st and hasattr(mod, "LINUX_WINDOWS_DISCOVERY_NAMES"):
                self._append_output_safe("\n  " + "=" * 55 + "\n", "header")
                self._append_output_safe("  LINUX DISCOVERY KEYS (intermediate)\n", "header")
                self._append_output_safe("  " + "=" * 55 + "\n", "header")
                disc_names = sorted(mod.LINUX_WINDOWS_DISCOVERY_NAMES)
                disc_found = sum(1 for n in disc_names if n in results)
                self._append_output_safe(
                    f"  {disc_found}/{len(disc_names)} Windows-style keys resolved for Linux mapping\n\n", "info")

            if fmt == "elf" and hasattr(mod, "format_linux_patcher_block"):
                block = mod.format_linux_patcher_block(results, bin_info, path, file_size, data=data)
                if block:
                    self.last_linux_block = _ascii_safe(block)
                    if verbose:
                        self._append_output_safe("\n  " + "=" * 55 + "\n", "header")
                        self._append_output_safe("  COPY BELOW -> discord_voice_patcher_linux.sh\n", "header")
                        self._append_output_safe("  Replace EXPECTED_MD5, EXPECTED_SIZE, and OFFSET_* section\n", "info")
                        self._append_output_safe("  " + "=" * 55 + "\n\n", "header")
                    self._append_output_safe("--- BEGIN COPY (Linux) ---\n", None)
                    self._append_output_safe(block + "\n", None)
                    self._append_output_safe("--- END COPY ---\n\n", None)
                else:
                    self.last_linux_block = ""
            elif fmt == "macho" and hasattr(mod, "format_arm64_patches_python_block"):
                block = mod.format_arm64_patches_python_block(stereo_patches, Path(path), file_size)
                if block:
                    self.last_macos_block = _ascii_safe(block)
                    self.last_windows_block = ""
                    self.last_linux_block = ""
                    if verbose:
                        self._append_output_safe("\n  " + "=" * 55 + "\n", "header")
                        self._append_output_safe("  COPY BELOW -> MacOS_ARM64_Patcher.py\n", "header")
                        self._append_output_safe(
                            "  Replace the entire # region ARM64 patch table ... "
                            "# endregion ARM64 patch table section\n", "info")
                        self._append_output_safe("  " + "=" * 55 + "\n\n", "header")
                    self._append_output_safe("--- BEGIN COPY (macOS ARM64) ---\n", None)
                    self._append_output_safe(block + "\n", None)
                    self._append_output_safe("--- END COPY ---\n\n", None)
                else:
                    self.last_macos_block = ""

            if self.save_json.get():
                try:
                    json_path = Path(path).with_suffix(".offsets.json")
                    try:
                        json_text = mod.format_json(
                            results, bin_info, path, len(data), adj, tiers_used)
                    except TypeError:
                        json_text = mod.format_json(results, bin_info, path, len(data), adj, tiers_used)
                    json_path.write_text(json_text, encoding="ascii")
                    self._append_output_safe(f"\n  JSON saved: {json_path}\n", "info")
                except Exception as e:
                    self._append_output_safe(f"\n  JSON save error: {e}\n", "warn")

            if is_pe and patcher_names_u:
                status_msg = f"Done - Windows patcher: {patcher_count}/{n_patcher} | x86_64: {found}/{n_expected}"
            elif is_macho and macos_st:
                status_msg = (
                    f"Done - ARM64 patcher: {macos_st['arm64_found']}/{macos_st['arm64_expected']}"
                )
            elif is_elf and linux_st:
                status_msg = f"Done - Linux patcher: {linux_st['found']}/{linux_st['expected']}"
            else:
                status_msg = f"Done - x86_64: {found}/{n_expected}"
            status_msg += f" | {datetime.now().strftime('%H:%M:%S')}"
            self._set_status_safe(status_msg)

        except Exception as e:
            import traceback
            self._append_output_safe(f"\n  [ERROR] {e}\n", "fail")
            self._append_output_safe(traceback.format_exc() + "\n", "fail")
            self._set_status_safe(f"Error: {e}")

        finally:
            self.root.after(0, self._finish_run)

    def _finish_run(self):
        self.running = False
        self.run_btn.configure(state="normal", bg=GREEN)

    def _append_output(self, text, tag=None):
        self.output.configure(state="normal")
        if tag:
            self.output.insert("end", text, tag)
        else:
            self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")
        self.last_output += text

    def _append_output_safe(self, text, tag=None):
        self.root.after(0, self._append_output, text, tag)

    def _set_status_safe(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def _on_close(self):
        _cleanup_pycache()
        self.root.destroy()



def main():
    if tk is None:
        print("Offset Finder requires Tkinter.", file=sys.stderr)
        if sys.platform.startswith("linux"):
            print("  sudo apt install python3-tk", file=sys.stderr)
        elif sys.platform == "darwin":
            print("  Use python.org Python or: brew install python-tk", file=sys.stderr)
        else:
            print("  Reinstall Python with Tcl/Tk.", file=sys.stderr)
        sys.exit(1)

    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()

    try:
        from ctypes import windll, c_int, byref
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        windll.dwmapi.DwmSetWindowAttribute(
            int(root.wm_frame(), 16) if isinstance(root.wm_frame(), str)
            else root.wm_frame(),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            byref(c_int(1)), 4)
    except Exception:
        pass

    root.option_add("*TCombobox*Listbox.background", BG_INPUT)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT_BG)
    root.option_add("*TCombobox*Listbox.selectForeground", FG_ACCENT)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TCombobox",
                     fieldbackground=BG_INPUT, background=GRAY_BTN,
                     foreground=FG, arrowcolor=FG,
                     selectbackground=SELECT_BG, selectforeground=FG_ACCENT)
    style.map("TCombobox",
              fieldbackground=[("readonly", BG_INPUT)],
              selectbackground=[("readonly", SELECT_BG)])

    app = OffsetFinderGUI(root)
    root.mainloop()




if __name__ == "__main__":
    main()
