#!/usr/bin/env python3
"""
Discord Voice Node Offset Finder — GUI
Auto-detects and loads the offset finder script from the same directory.
Matches the Stereo Installer dark theme.

Made by: Oracle | Shaun | Hallow | Ascend | Sentry | Sikimzo | Cypher
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from datetime import datetime
from pathlib import Path
import importlib.util
import io
import contextlib

VERSION = "1.0.0"
SCRIPT_DIR = Path(__file__).parent

# ─── Theme Colors (matching Stereo Installer) ────────────────────────
BG           = "#1e1e1e"
BG_LIGHT     = "#2d2d2d"
BG_INPUT     = "#1a1a1a"
FG           = "#e0e0e0"
FG_DIM       = "#888888"
FG_ACCENT    = "#ffffff"
BORDER       = "#3a3a3a"
GREEN        = "#4caf50"
GREEN_HOVER  = "#66bb6a"
BLUE         = "#2196f3"
BLUE_HOVER   = "#42a5f5"
ORANGE       = "#ff9800"
ORANGE_HOVER = "#ffb74d"
GRAY_BTN     = "#555555"
GRAY_HOVER   = "#666666"
RED          = "#f44336"
YELLOW       = "#fdd835"
CYAN         = "#4dd0e1"
SELECT_BG    = "#0d47a1"


class OffsetFinderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Offset Finder")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(620, 580)
        self.root.geometry("660x700")

        # Try to set icon (optional)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        self.finder_module = None
        self.running = False
        self.file_path = tk.StringVar()
        self.os_var = tk.StringVar(value="Auto-Detect")
        self.status_var = tk.StringVar(value="Ready")
        self.last_output = ""  # plain-text copy of last run output for saving

        self._build_ui()
        self._load_finder()

    # ─── UI Construction ──────────────────────────────────────────
    def _build_ui(self):
        # Title area
        title_frame = tk.Frame(self.root, bg=BG)
        title_frame.pack(fill="x", padx=16, pady=(14, 0))

        tk.Label(title_frame, text="Offset Finder", font=("Segoe UI", 20, "bold"),
                 bg=BG, fg=FG_ACCENT).pack()
        tk.Label(title_frame, text="Made by: Oracle | Shaun | Hallow | Ascend | Sentry | Sikimzo | Cypher",
                 font=("Segoe UI", 8), bg=BG, fg=FG_DIM).pack()
        tk.Label(title_frame, text=f"v{VERSION}",
                 font=("Segoe UI", 8), bg=BG, fg=FG_DIM).pack()

        # ─── Binary Selection Group ───
        sel_frame = tk.LabelFrame(self.root, text=" Binary Selection ",
                                  font=("Segoe UI", 9, "bold"),
                                  bg=BG_LIGHT, fg=FG, bd=1, relief="groove",
                                  highlightbackground=BORDER, highlightthickness=1)
        sel_frame.pack(fill="x", padx=16, pady=(12, 0), ipady=4)

        # OS row
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

        # File row
        file_row = tk.Frame(sel_frame, bg=BG_LIGHT)
        file_row.pack(fill="x", padx=10, pady=(4, 8))
        tk.Label(file_row, text="Node File:", font=("Segoe UI", 9),
                 bg=BG_LIGHT, fg=FG, width=10, anchor="w").pack(side="left")

        self.file_entry = tk.Entry(file_row, textvariable=self.file_path,
                                   font=("Consolas", 9), bg=BG_INPUT, fg=FG,
                                   insertbackground=FG, relief="flat", bd=0,
                                   highlightbackground=BORDER, highlightthickness=1)
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(4, 6), ipady=3)

        self.browse_btn = tk.Button(file_row, text="Browse…",
                                    font=("Segoe UI", 9), bg=GRAY_BTN, fg=FG,
                                    activebackground=GRAY_HOVER, activeforeground=FG,
                                    relief="flat", bd=0, padx=12, pady=2,
                                    cursor="hand2", command=self._browse_file)
        self.browse_btn.pack(side="right")

        # ─── Options Group ───
        opt_frame = tk.LabelFrame(self.root, text=" Options ",
                                  font=("Segoe UI", 9, "bold"),
                                  bg=BG_LIGHT, fg=FG, bd=1, relief="groove",
                                  highlightbackground=BORDER, highlightthickness=1)
        opt_frame.pack(fill="x", padx=16, pady=(10, 0), ipady=4)

        self.save_json = tk.BooleanVar(value=True)
        self.save_ps = tk.BooleanVar(value=True)
        self.show_graph = tk.BooleanVar(value=False)
        self.verbose = tk.BooleanVar(value=False)

        opts_inner = tk.Frame(opt_frame, bg=BG_LIGHT)
        opts_inner.pack(fill="x", padx=10, pady=(6, 6))

        left_opts = tk.Frame(opts_inner, bg=BG_LIGHT)
        left_opts.pack(side="left", anchor="nw")
        right_opts = tk.Frame(opts_inner, bg=BG_LIGHT)
        right_opts.pack(side="left", anchor="nw", padx=(30, 0))

        for var, text, parent in [
            (self.save_json, "Save JSON offsets file", left_opts),
            (self.save_ps, "Save PowerShell config", left_opts),
            (self.show_graph, "Generate dependency graph", right_opts),
            (self.verbose, "Verbose output", right_opts),
        ]:
            cb = tk.Checkbutton(parent, text=text, variable=var,
                                font=("Segoe UI", 9), bg=BG_LIGHT, fg=FG,
                                selectcolor=BG_INPUT, activebackground=BG_LIGHT,
                                activeforeground=FG, highlightthickness=0,
                                bd=0, anchor="w")
            cb.pack(anchor="w", pady=1)

        # ─── Output Area ───
        output_frame = tk.Frame(self.root, bg=BG)
        output_frame.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        self.output = scrolledtext.ScrolledText(
            output_frame, font=("Consolas", 9), bg=BG_INPUT, fg=FG,
            insertbackground=FG, relief="flat", bd=0, wrap="word",
            highlightbackground=BORDER, highlightthickness=1, state="disabled")
        self.output.pack(fill="both", expand=True)

        # Configure output text tags for colored output
        self.output.tag_config("pass", foreground=GREEN)
        self.output.tag_config("fail", foreground=RED)
        self.output.tag_config("warn", foreground=YELLOW)
        self.output.tag_config("info", foreground=CYAN)
        self.output.tag_config("header", foreground=ORANGE, font=("Consolas", 9, "bold"))
        self.output.tag_config("success", foreground=GREEN, font=("Consolas", 10, "bold"))

        # ─── Status Bar ───
        status_frame = tk.Frame(self.root, bg=BG_LIGHT, height=24)
        status_frame.pack(fill="x", padx=16, pady=(6, 0))
        self.status_label = tk.Label(status_frame, textvariable=self.status_var,
                                     font=("Segoe UI", 8), bg=BG_LIGHT, fg=FG_DIM,
                                     anchor="w")
        self.status_label.pack(fill="x", padx=6, pady=2)

        # ─── Button Bar ───
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill="x", padx=16, pady=(8, 14))

        self.run_btn = self._make_button(btn_frame, "Find Offsets", GREEN, GREEN_HOVER,
                                         self._run_finder)
        self.run_btn.pack(side="left", padx=(0, 6))

        self.copy_btn = self._make_button(btn_frame, "Copy Output", BLUE, BLUE_HOVER,
                                          self._copy_output)
        self.copy_btn.pack(side="left", padx=(0, 6))

        self.save_btn = self._make_button(btn_frame, "Save Results", GRAY_BTN, GRAY_HOVER,
                                          self._save_results)
        self.save_btn.pack(side="left", padx=(0, 6))

        self.clear_btn = self._make_button(btn_frame, "Clear", GRAY_BTN, GRAY_HOVER,
                                           self._clear_output)
        self.clear_btn.pack(side="left")

        # Drag and drop hint
        self._append_output("  Drop a discord_voice.node file or click Browse to begin.\n", "info")

        # Bind drag-and-drop if available (tkinterdnd2)
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

    # ─── Actions ──────────────────────────────────────────────────
    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select discord_voice.node",
            filetypes=[
                ("Node binary", "*.node"),
                ("All files", "*.*"),
            ])
        if path:
            self.file_path.set(path)
            # Auto-detect OS from file
            self._auto_detect_os(path)

    def _auto_detect_os(self, path):
        """Read first 4 bytes to auto-detect binary format."""
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

    def _clear_output(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self.last_output = ""

    def _copy_output(self):
        text = self.last_output.strip()
        if not text:
            text = self.output.get("1.0", "end").strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status_var.set("Output copied to clipboard")

    def _save_results(self):
        text = self.last_output.strip()
        if not text:
            # Fallback: try reading widget directly
            text = self.output.get("1.0", "end").strip()
        if not text:
            self.status_var.set("Nothing to save")
            return
        path = filedialog.asksaveasfilename(
            title="Save Results",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.status_var.set(f"Saved to {path}")

    # ─── Finder Integration ───────────────────────────────────────
    def _load_finder(self):
        """Dynamically import the offset finder script from same directory."""
        finder_path = None

        # Find any offset finder script in the same folder — don't care about name
        for f in sorted(SCRIPT_DIR.glob("*.py"), reverse=True):
            if f.name == Path(__file__).name:
                continue  # skip ourselves
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")[:4000]
                # Look for identifiers that appear early in the offset finder script
                if "Discord Voice Node Offset Finder" in text or \
                   ("SIGNATURES" in text and "VERSION" in text):
                    finder_path = f
                    break
            except Exception:
                continue

        if finder_path and finder_path.exists():
            spec = importlib.util.spec_from_file_location("offset_finder", finder_path)
            self.finder_module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(self.finder_module)
                ver = getattr(self.finder_module, "VERSION", "?")
                self.status_var.set(f"Loaded: {finder_path.name} (v{ver})")
            except Exception as e:
                self.status_var.set(f"Error loading finder: {e}")
                self.finder_module = None
        else:
            self.status_var.set("Warning: no offset finder script found in same directory")

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
        if self.finder_module is None:
            self._append_output("  [ERROR] Offset finder script not loaded.\n", "fail")
            self._append_output("  Place the offset finder .py script in the same folder as this GUI.\n", "info")
            return

        self.running = True
        self.run_btn.configure(state="disabled", bg=GRAY_BTN)
        self._clear_output()

        # Get file info
        fsize = os.path.getsize(path)
        fname = os.path.basename(path)
        self._append_output(f"  File: {fname}\n", "header")
        self._append_output(f"  Size: {fsize:,} bytes | OS: {self.os_var.get()}\n", "info")
        self._append_output(f"  {'─' * 55}\n\n", "info")

        # Run in background thread
        thread = threading.Thread(target=self._run_finder_thread, args=(path,), daemon=True)
        thread.start()

    def _run_finder_thread(self, path):
        """Execute the offset finder and capture output."""
        try:
            mod = self.finder_module

            # Read binary
            with open(path, "rb") as f:
                data = f.read()

            # Detect format
            bin_info = mod.detect_binary_format(data)
            fmt = bin_info.get("format", "unknown")
            arch = bin_info.get("arch", "unknown")

            self._append_output_safe(f"  Format: {fmt.upper()} | Arch: {arch}\n", "info")

            if bin_info.get("has_symbols"):
                nsyms = len(bin_info.get("func_symbols", {}))
                self._append_output_safe(f"  Symbols: {nsyms} functions found\n", "info")

            self._append_output_safe(f"\n  Scanning for offsets...\n\n", "header")

            # Capture stdout from discover_offsets
            old_stdout = sys.stdout
            capture = io.StringIO()
            sys.stdout = capture

            try:
                results, errors, adj, tiers_used = mod.discover_offsets(data, bin_info)
            finally:
                sys.stdout = old_stdout

            # Parse and colorize captured output
            captured = capture.getvalue()
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

            # Summary
            total = 18
            found = len(results)
            self._append_output_safe(f"\n  {'═' * 55}\n", "header")
            if found == total:
                self._append_output_safe(
                    f"  ✓ ALL {found} OFFSETS FOUND SUCCESSFULLY\n", "success")
            else:
                self._append_output_safe(
                    f"  Found {found}/{total} offsets ({total - found} missing)\n", "warn")
                if errors:
                    for e in errors:
                        self._append_output_safe(f"  Missing: {e}\n", "fail")

            # Cross-validation
            try:
                xval = mod._cross_validate(results, adj, data, tiers_used=tiers_used)
                if xval:
                    for w in xval:
                        self._append_output_safe(f"  [XVAL] {w}\n", "warn")
                else:
                    self._append_output_safe(f"  Cross-validation: clean\n", "pass")
            except Exception:
                pass

            # Generate PowerShell config
            self._append_output_safe(f"\n", None)
            try:
                old_stdout = sys.stdout
                ps_capture = io.StringIO()
                sys.stdout = ps_capture
                ps_text = mod.format_powershell_config(
                    results, bin_info=bin_info, file_path=path,
                    file_size=len(data))
                sys.stdout = old_stdout
                if ps_text:
                    self._append_output_safe(ps_text + "\n", None)
            except Exception:
                sys.stdout = old_stdout

            # Save JSON if requested
            if self.save_json.get():
                try:
                    json_path = Path(path).with_suffix(".offsets.json")
                    json_text = mod.format_json(results, bin_info, path, len(data), adj, tiers_used)
                    json_path.write_text(json_text, encoding="utf-8")
                    self._append_output_safe(f"\n  JSON saved: {json_path}\n", "info")
                except Exception as e:
                    self._append_output_safe(f"\n  JSON save error: {e}\n", "warn")

            self._set_status_safe(
                f"Done — {found}/{total} offsets | {datetime.now().strftime('%H:%M:%S')}")

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

    # ─── Thread-safe output helpers ───────────────────────────────
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


def main():
    root = tk.Tk()

    # Dark title bar on Windows 10/11
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

    # Style the combobox dropdown
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
