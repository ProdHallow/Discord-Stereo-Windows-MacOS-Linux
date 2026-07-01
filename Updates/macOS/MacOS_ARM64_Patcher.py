#!/usr/bin/env python3
# ARM64-only patches for discord_voice.node on Apple Silicon

from __future__ import annotations

import json
import os
import re
import shutil
import hashlib
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Protocol, Tuple

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception:
    tk = None  # type: ignore


class LogSink(Protocol):
    def info(self, msg: str) -> None: ...
    def ok(self, msg: str) -> None: ...
    def warn(self, msg: str) -> None: ...
    def fail(self, msg: str) -> None: ...


APP_NAME = "Discord Stereo Patcher"
APP_VERSION = "1.0.0"


TARGET_BITRATE_BPS = 248000


# region ARM64 instruction encoders
def _arm64_cbz(rt: int, target_insn: int, from_insn: int) -> int:
    """Encode CBZ Wt (32-bit). imm19 is the branch offset in instructions."""
    imm19 = target_insn - from_insn
    return 0x34000000 | ((imm19 & 0x7FFFF) << 5) | (rt & 0x1F)


def _arm64_b_ne(target_insn: int, from_insn: int) -> int:
    """Encode B.NE. imm19 is the branch offset in instructions."""
    imm19 = target_insn - from_insn
    return 0x54000001 | ((imm19 & 0x7FFFF) << 5)


def _arm64_passthrough_shellcode(len_reg: int, ch_reg: int, out_reg: int) -> bytes:
    """Filterless passthrough: copy len*channels floats from X0 to X<out_reg> (8 insns)."""
    ins = [0] * 8
    ins[0] = _arm64_cbz(len_reg, 7, 0)                       # CBZ Wlen, ret
    # MADD W11, Wlen, Wch, WZR  (W11 = len * channels)
    ins[1] = 0x1B000000 | ((ch_reg & 0x1F) << 16) | (31 << 10) | ((len_reg & 0x1F) << 5) | 11
    ins[2] = _arm64_cbz(11, 7, 2)                            # CBZ W11, ret
    ins[3] = 0xBC404404                                      # LDR S4, [X0], #4
    ins[4] = 0xBC004404 | ((out_reg & 0x1F) << 5)            # STR S4, [Xout], #4
    ins[5] = 0x7100056B                                      # SUBS W11, W11, #1
    ins[6] = _arm64_b_ne(3, 6)                               # B.NE loop (-> LDR)
    ins[7] = 0xD65F03C0                                      # RET
    return struct.pack("<8I", *ins)
# endregion ARM64 instruction encoders


# region ARM64 patch table
PATCHES_META = {
    "finder_version": "discord_voice_node_offset_finder_v5.py v5.11.0",
    "discord_app_version": "unspecified",
    "file_size": 51474192,
    "md5": "c3efcdd6b6b11698eca006a9d93d7de5",
    "arm64_slice_offset": 0x1A80000,
    "arm64_slice_size": 23686928,
}

ARM64_PATCHES: List[dict] = [
    # Opus channel count -> force stereo
    {"name": "MultiChannelOpusConfig_channels",    "fat_offset": 0x1DEDA90, "orig": "28",                      "patch": "48"},
    {"name": "OpusConfig_channels",                "fat_offset": 0x1DEDED4, "orig": "28",                      "patch": "48"},
    {"name": "CreateAudioFrame_channels1",         "fat_offset": 0x2220A98, "orig": "3B",                      "patch": "5B"},
    {"name": "CreateAudioFrame_channels2",         "fat_offset": 0x2220AD0, "orig": "3B",                      "patch": "5B"},
    {"name": "NumProcChannels_force_stereo",       "fat_offset": 0x1CB99D4, "orig": "08 B4 45 39 1F 05 00 71", "patch": "40 00 80 52 C0 03 5F D6"},
    # NOTE: The CommitAudioCodec_* send-setup hacks (stereo_force / stereo_force2 /
    # ChannelCount_alt) were REMOVED. They do not contribute to stereo -- the encoder
    # channel count is forced to 2 at the config layer (OpusConfig_channels +
    # SdpToConfig_* -> num_channels=2) and by LocalUser::CreateAudioStream calling
    # CreateAudioSendStream(..., 48000, 2). Those patches only mutated send-stream
    # setup control flow (e.g. stereo_force inverted the SDP "stereo" string, which
    # SdpToConfig ignores anyway), adding misconfiguration risk with no benefit.

    # Downmix / mono collapse -> bypass
    {"name": "StereoDownmixChannels",              "fat_offset": 0x1CD0F30, "orig": "F6 57 BD A9",             "patch": "C0 03 5F D6"},
    {"name": "StereoDownMixFrame",                 "fat_offset": 0x1E3F06C, "orig": "20 01 00 34",             "patch": "1F 20 03 D5"},
    {"name": "DownmixInterleavedToMono_bypass",    "fat_offset": 0x1A9B62C, "orig": "48 7C 40 93",             "patch": "C0 03 5F D6"},
    {"name": "CapturedAudioProcessor_MonoDownmix", "fat_offset": 0x21EE8B4, "orig": "48 02 00 37",             "patch": "1F 20 03 D5"},
    {"name": "ChannelDownmix_Entry_Ret",           "fat_offset": 0x1DD5838, "orig": "E9 23 B9 6D",             "patch": "C0 03 5F D6"},

    # SDP negotiation -> keep stereo
    # NOTE: StereoApplyAudioNetworkAdaptor was REMOVED. It NOP'd the guard
    # (B.NE 0x3707CC) in AudioEncoderOpusImpl::ApplyAudioNetworkAdaptor that skips
    # channel forcing when the ANA runtime config has no valid channel decision.
    # With the guard gone, the function reads the uninitialized (0xAAAA..) channel
    # field, WebRtcOpus_SetForceChannels rejects it (>2 -> returns -1), and the
    # RTC_CHECK fires FatalLog() -> process abort. ApplyAudioNetworkAdaptor runs on
    # every RTCP feedback event (OnReceivedUplinkBandwidth / Rtt / PacketLoss /
    # Overhead), so this aborted the encoder within seconds of joining a call ->
    # "captures input but never encodes/sends" and "crashes on voice join".
    {"name": "SdpToConfig_cinc1",                  "fat_offset": 0x1DEEE34, "orig": "15 15 88 9A",             "patch": "55 00 80 52"},
    {"name": "SdpToConfig_mov1",                   "fat_offset": 0x1DEEE3C, "orig": "35",                      "patch": "55"},
    {"name": "SdpToConfig_cinc2",                  "fat_offset": 0x1DEEE5C, "orig": "15 15 88 9A",             "patch": "55 00 80 52"},
    {"name": "SdpToConfig_mov2",                   "fat_offset": 0x1DEEE64, "orig": "35",                      "patch": "55"},

    # Config validation -> force OK / skip throw
    {"name": "OpusConfig_IsOk",                    "fat_offset": 0x1DEE048, "orig": "08 00 40 B9 A9 99 99 52", "patch": "20 00 80 52 C0 03 5F D6"},
    {"name": "MultiChannelOpusConfig_IsOk",        "fat_offset": 0x1DEDC5C, "orig": "FF 03 01 D1 F4 4F 02 A9", "patch": "20 00 80 52 C0 03 5F D6"},
    {"name": "CodecMismatchThrow_Entry_Ret",       "fat_offset": 0x214D560, "orig": "FF 43 01 D1",             "patch": "C0 03 5F D6"},

    # Audio filters -> bypass
    {"name": "InitializeHighPassFilter_bypass",    "fat_offset": 0x1CB8D7C, "orig": "F6 57 BD A9",             "patch": "C0 03 5F D6"},
    {"name": "NoiseCanceller_bypass",              "fat_offset": 0x21DC034, "orig": "FF 03 02 D1",             "patch": "C0 03 5F D6"},
    {"name": "CustomCapturePostproc_bypass",       "fat_offset": 0x2201104, "orig": "AE 6C FF 17",             "patch": "1F 20 03 D5"},
    {"name": "ProcessStream_bypass",               "fat_offset": 0x1CBB71C, "orig": "E1 00 00 54",             "patch": "1F 20 03 D5"},

    # Sample rate / frame size -> 48 kHz, 10 ms
    # NOTE: SelectSampleRate_Cmov48k_Nop3 was REMOVED. Despite the name, its site
    # (0x7AA528) is the CSET that computes the AudioStreamType arg for
    # EngineAudioTransport::AddSendStream -- NOT the sample rate (48 kHz is hard-coded
    # in CreateAudioSendStream(..., 48000, 2)). NOP'ing it left that arg as a stale
    # register value; AddSendStream only stores it as map metadata, so the patch was
    # pointless and is dropped.
    {"name": "OpusConfig_FrameMs_Rodata",          "fat_offset": 0x24FDAC8, "orig": "14",                      "patch": "0A"},
    {"name": "MultiChannel_FrameMs_Imm10",         "fat_offset": 0x1DEDA88, "orig": "88 02 80 52",             "patch": "48 01 80 52"},

    # Bitrate -> 248 kbps
    {"name": "OpusConfig_Bitrate_Rodata",          "fat_offset": 0x24FDABC, "orig": "00 7D 00 00",             "patch": "C0 C8 03 00"},
    {"name": "RuntimeBitrate_Ldr_1",               "fat_offset": 0x22277A8, "orig": "08 21 40 B9",             "patch": "08 18 99 52"},
    {"name": "RuntimeBitrate_Movk_1",              "fat_offset": 0x22277AC, "orig": "09 40 9F 52",             "patch": "68 00 A0 72"},
    {"name": "RuntimeBitrate_Ldr_2",               "fat_offset": 0x222AB08, "orig": "09 21 40 B9",             "patch": "09 18 99 52"},
    {"name": "RuntimeBitrate_Movk_2",              "fat_offset": 0x222AB0C, "orig": "0A 40 9F 52",             "patch": "69 00 A0 72"},
    {"name": "RuntimeBitrate_Ldr_3",               "fat_offset": 0x222ADF4, "orig": "09 21 40 B9",             "patch": "09 18 99 52"},
    {"name": "RuntimeBitrate_Movk_3",              "fat_offset": 0x222ADFC, "orig": "0A 40 9F 52",             "patch": "69 00 A0 72"},

    # CELT codec forcing
    {"name": "CELT_Force",                         "fat_offset": 0x24FD4C0, "orig": "18 FC FF FF FF FF FF FF", "patch": "EA 03 00 00 00 00 00 00"},
    {"name": "CELT_DefaultMode",                   "fat_offset": 0x1DD9AB0, "orig": "28 7D 80 52",             "patch": "48 7D 80 52"},

    # Filterless passthrough shellcode (hp_cutoff / dc_reject callbacks)
    {
        "name": "hp_cutoff_Callback_InjectShellcode",
        "fat_offset": 0x1DDD730,
        "orig": "9F 04 00 71 6B 09 00 54 09 00 80 D2 28 3C 00 13 EA 34 81 52 08 7D 0A 1B 6A BA 89 52 4A 0C A2 72",
        "patch": "E4 00 00 34 8B 7C 05 1B AB 00 00 34 04 44 40 BC 44 44 00 BC 6B 05 00 71 A1 FF FF 54 C0 03 5F D6",
    },
    {
        "name": "dc_reject_Callback_InjectShellcode",
        "fat_offset": 0x1DDD864,
        "orig": "A0 00 22 1E 88 66 86 52 E8 32 A8 72 01 01 27 1E 21 18 20 1E 00 10 2E 1E 02 38 21 1E 40 00 40 BD",
        "patch": "E3 00 00 34 6B 7C 04 1B AB 00 00 34 04 44 40 BC 24 44 00 BC 6B 05 00 71 A1 FF FF 54 C0 03 5F D6",
    },
]
# endregion ARM64 patch table


# region Patch engine
ARM64_STEREO_SPEC_NAMES = [p["name"] for p in ARM64_PATCHES]


def _hex_bytes(s: str) -> bytes:
    return bytes(int(b, 16) for b in s.split() if b)

def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_macos_stereo_patches(data: bytes) -> List[dict]:
    """Resolve static ARM64 patch sites against the fat binary."""
    if len(data) < 8:
        return []
    out: List[dict] = []
    for spec in ARM64_PATCHES:
        fo = spec["fat_offset"]
        orig = _hex_bytes(spec["orig"])
        patch_b = _hex_bytes(spec["patch"])
        if fo + max(len(orig), len(patch_b)) > len(data):
            continue
        current = data[fo : fo + len(orig)]
        entry = {
            "arch": "arm64",
            "name": spec["name"],
            "fat_offset": fo,
            "orig": spec["orig"],
            "patch": spec["patch"],
        }
        if current == orig:
            out.append(entry)
        elif data[fo : fo + len(patch_b)] == patch_b:
            entry["already_patched"] = True
            out.append(entry)
    return out


def missing_arm64_stereo_patch_names(data: bytes) -> List[str]:
    found = {p["name"] for p in find_macos_stereo_patches(data)}
    return [n for n in ARM64_STEREO_SPEC_NAMES if n not in found]


def apply_macos_stereo_patches(data, arm64_only: bool = False) -> Tuple[int, int, List[str]]:
    patches = find_macos_stereo_patches(data)
    if arm64_only:
        patches = [p for p in patches if p.get("arch") == "arm64"]
    if not patches:
        return 0, 0, []

    if not isinstance(data, bytearray):
        data = bytearray(data)

    seen: set = set()
    applied = skipped = 0
    names: List[str] = []
    for p in patches:
        fo = p["fat_offset"]
        orig = _hex_bytes(p["orig"])
        patch = _hex_bytes(p["patch"])
        key = (fo, orig.hex())
        if key in seen:
            continue
        seen.add(key)
        if fo + len(patch) > len(data):
            skipped += 1
            continue
        current = bytes(data[fo : fo + len(orig)])
        if current == orig:
            data[fo : fo + len(patch)] = patch
            applied += 1
            names.append(p["name"])
        elif current == patch or p.get("already_patched"):
            skipped += 1
            names.append(p["name"] + " (already)")
        else:
            skipped += 1
    return applied, skipped, names


def apply_all_arm64_patches(data, *, arm64_only: bool = True) -> Tuple[int, int, List[str]]:
    if not isinstance(data, bytearray):
        data = bytearray(data)
    return apply_macos_stereo_patches(data, arm64_only=arm64_only)
# endregion Patch engine


# region Theme, constants & drawing helpers
COLORS = {
    "bg_dark": "#1e1f22",
    "bg_secondary": "#2b2d31",
    "bg_tertiary": "#313338",
    "bg_input": "#383a40",
    "text_normal": "#dbdee1",
    "text_muted": "#949ba4",
    "text_header": "#f2f3f5",
    "blurple": "#5865f2",
    "blurple_dark": "#4752c4",
    "green": "#57f287",
    "red": "#ed4245",
    "yellow": "#fee75c",
    "white": "#ffffff",
}

CACHE_DIR = Path.home() / "Library" / "Caches" / "DiscordVoicePatcher"
BACKUP_DIR = CACHE_DIR / "Backups"
VOICE_BACKUP_DIR = CACHE_DIR / "VoiceBackup"
VOICE_BACKUP_API = (
    "https://api.github.com/repos/ProdHallow/Discord-Stereo-Windows-MacOS-Linux/"
    "contents/Updates%2FNodes%2FUnpatched%20Nodes%20%28For%20Patcher%29%2FmacOS"
)



BADGE_GREEN_BG = "#1a3328"
BADGE_GREEN_FG = "#3dd68c"
BADGE_YELLOW_BG = "#3d3520"
BADGE_YELLOW_FG = "#fbbf24"
LOG_BG = "#111214"
CARD_BORDER = "#3f4147"
RADIUS_CARD = 12
RADIUS_BTN = 8
RADIUS_INPUT = 8
RADIUS_BADGE = 14
RADIUS_LOG = 10
RADIUS_PROGRESS = 5
CARD_BORDER_WIDTH = 1


def _rounded_inset(radius: int) -> int:
    """Keep embedded rectangular windows off the curved corner band."""
    return CARD_BORDER_WIDTH + max(radius - CARD_BORDER_WIDTH, 0)


def _draw_rounded_panel(
    canvas,
    w: int,
    h: int,
    radius: int,
    *,
    fill: str,
    border: str = CARD_BORDER,
    tag: str = "",
) -> None:
    inner_r = max(radius - CARD_BORDER_WIDTH, 0)
    _draw_round_rect(canvas, 0, 0, w, h, radius, fill=border, outline="", tags=tag)
    _draw_round_rect(
        canvas,
        CARD_BORDER_WIDTH,
        CARD_BORDER_WIDTH,
        w - CARD_BORDER_WIDTH,
        h - CARD_BORDER_WIDTH,
        inner_r,
        fill=fill,
        outline="",
        tags=tag,
    )


def _ui_font(size: int = 10, bold: bool = False) -> Tuple[str, int, str]:
    family = "SF Pro Text" if sys.platform == "darwin" else "Segoe UI"
    return (family, size, "bold" if bold else "normal")


def _ui_font_display(size: int = 22) -> Tuple[str, int, str]:
    family = "SF Pro Display" if sys.platform == "darwin" else "Segoe UI"
    return (family, size, "bold")


def _mono_font(size: int = 10) -> Tuple[str, int]:
    family = "SF Mono" if sys.platform == "darwin" else "Consolas"
    return (family, size)


def _short_home_path(p: Path) -> str:
    try:
        home = str(Path.home())
        s = str(p)
        if s.startswith(home):
            return "~" + s[len(home) :]
        return s
    except Exception:
        return str(p)


def _parent_bg(widget) -> str:
    try:
        return widget.cget("bg")
    except Exception:
        return COLORS["bg_dark"]


def _draw_round_rect(canvas, x1, y1, x2, y2, radius, *, fill, outline="", width=0, tags="") -> int:
    """Solid rounded rectangle using arcs + rectangles (crisp corners)."""
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    kw: dict = {"fill": fill, "outline": outline or fill, "width": width}
    if tags:
        kw["tags"] = tags
    if r <= 0:
        return canvas.create_rectangle(x1, y1, x2, y2, **kw)
    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, **kw)
    canvas.create_rectangle(x1, y1 + r, x2, y2 - r, **kw)
    for cx, cy in ((x1, y1), (x2 - 2 * r, y1), (x1, y2 - 2 * r), (x2 - 2 * r, y2 - 2 * r)):
        canvas.create_oval(cx, cy, cx + 2 * r, cy + 2 * r, **kw)
    return 0


def _measure_text(text: str, font) -> Tuple[int, int]:
    try:
        import tkinter.font as tkfont

        f = tkfont.Font(font=font)
        return f.measure(text) + 28, f.metrics("linespace") + 16
    except Exception:
        return max(len(text) * 7 + 28, 80), 34
# endregion Theme, constants & drawing helpers


# region UI widgets
class ThemedButton(tk.Canvas):
    """Rounded canvas button — works on macOS and Windows."""

    def __init__(
        self,
        parent,
        text: str,
        bg: str,
        hover: str,
        command,
        *,
        fg: str = "#ffffff",
        radius: int = RADIUS_BTN,
    ) -> None:
        pbg = _parent_bg(parent)
        w, h = _measure_text(text, _ui_font(10))
        super().__init__(
            parent,
            width=w,
            height=h,
            bg=pbg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._text = text
        self._base_bg = bg
        self._hover_bg = hover
        self._cur_bg = bg
        self._command = command
        self._enabled = True
        self._fg = fg
        self._disabled_bg = COLORS["bg_tertiary"]
        self._disabled_fg = COLORS["text_muted"]
        self._radius = radius
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w = max(self.winfo_width(), 4)
        h = max(self.winfo_height(), 4)
        _draw_rounded_panel(self, w, h, self._radius, fill=self._cur_bg)
        self.create_text(
            w / 2,
            h / 2,
            text=self._text,
            fill=self._fg if self._enabled else self._disabled_fg,
            font=_ui_font(10),
        )

    def _click(self, _event=None) -> None:
        if self._enabled:
            self._command()

    def _enter(self, _event=None) -> None:
        if self._enabled:
            self._cur_bg = self._hover_bg
            self._draw()

    def _leave(self, _event=None) -> None:
        if self._enabled:
            self._cur_bg = self._base_bg
            self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._cur_bg = self._base_bg if enabled else self._disabled_bg
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()


class SectionCard(tk.Frame):
    """Rounded section panel with title and body area."""

    def __init__(self, parent, title: str, *, radius: int = RADIUS_CARD) -> None:
        super().__init__(parent, bg=COLORS["bg_dark"])
        self._radius = radius
        self.canvas = tk.Canvas(self, bg=COLORS["bg_dark"], highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.inner = tk.Frame(self.canvas, bg=COLORS["bg_secondary"])
        tk.Label(
            self.inner,
            text=title,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_muted"],
            font=_ui_font(10, True),
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16, pady=(14, 8))
        self.body = tk.Frame(self.inner, bg=COLORS["bg_secondary"])
        self.body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        inset = _rounded_inset(self._radius)
        self._inset = inset
        self._win = self.canvas.create_window(inset, inset, anchor=tk.NW, window=self.inner)
        self.canvas.bind("<Configure>", self._paint)

    def _paint(self, _event=None) -> None:
        w = max(self.canvas.winfo_width(), 4)
        h = max(self.canvas.winfo_height(), 4)
        self.canvas.delete("card")
        _draw_rounded_panel(
            self.canvas,
            w,
            h,
            self._radius,
            fill=COLORS["bg_secondary"],
            tag="card",
        )
        self.canvas.tag_lower("card")
        inset = self._inset
        inner_w = max(w - inset * 2, 1)
        inner_h = max(h - inset * 2, 1)
        self.canvas.coords(self._win, inset, inset)
        self.canvas.itemconfigure(self._win, width=inner_w, height=inner_h)


class RoundedLogPanel(tk.Frame):
    """Log console with rounded border."""

    def __init__(self, parent) -> None:
        super().__init__(parent, bg=COLORS["bg_secondary"])
        self.canvas = tk.Canvas(self, bg=COLORS["bg_secondary"], highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self._radius = RADIUS_LOG

        wrap = tk.Frame(self.canvas, bg=LOG_BG)
        scroll = tk.Scrollbar(
            wrap,
            bg=COLORS["bg_tertiary"],
            troughcolor=LOG_BG,
            activebackground=COLORS["bg_input"],
            highlightthickness=0,
            bd=0,
            width=12,
        )
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text = tk.Text(
            wrap,
            wrap=tk.WORD,
            bg=LOG_BG,
            fg=COLORS["text_normal"],
            insertbackground=COLORS["text_normal"],
            font=_mono_font(10),
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            height=14,
            yscrollcommand=scroll.set,
        )
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=self.text.yview)

        inset = _rounded_inset(self._radius)
        self._inset = inset
        self._win = self.canvas.create_window(inset, inset, anchor=tk.NW, window=wrap)
        self.canvas.bind("<Configure>", self._paint)

    def _paint(self, _event=None) -> None:
        w = max(self.canvas.winfo_width(), 4)
        h = max(self.canvas.winfo_height(), 4)
        self.canvas.delete("logbg")
        _draw_rounded_panel(self.canvas, w, h, self._radius, fill=LOG_BG, tag="logbg")
        self.canvas.tag_lower("logbg")
        inset = self._inset
        inner_w = max(w - inset * 2, 1)
        inner_h = max(h - inset * 2, 1)
        self.canvas.coords(self._win, inset, inset)
        self.canvas.itemconfigure(self._win, width=inner_w, height=inner_h)


def _badge(parent, text: str, bg: str, fg: str) -> tk.Canvas:
    pbg = _parent_bg(parent)
    w, h = _measure_text(text, _ui_font(9))
    h = max(h - 4, 26)
    c = tk.Canvas(parent, width=w, height=h, bg=pbg, highlightthickness=0, bd=0)

    def _draw() -> None:
        c.delete("all")
        ww = max(c.winfo_width(), w)
        hh = max(c.winfo_height(), h)
        _draw_rounded_panel(c, ww, hh, RADIUS_BADGE, fill=bg, border=bg)
        c.create_text(ww / 2, hh / 2, text=text, fill=fg, font=_ui_font(9))

    c.bind("<Configure>", lambda _e: _draw())
    _draw()
    return c


class ProgressBar(tk.Frame):
    def __init__(self, parent) -> None:
        super().__init__(parent, bg=COLORS["bg_secondary"])
        self._pct = 0.0
        self._canvas = tk.Canvas(self, height=8, bg=COLORS["bg_secondary"], highlightthickness=0, bd=0)
        self._canvas.pack(fill=tk.X)
        self._canvas.bind("<Configure>", lambda _e: self._draw())

    def set(self, pct: float) -> None:
        self._pct = max(0.0, min(100.0, pct))
        self._draw()

    def _draw(self) -> None:
        try:
            self._canvas.delete("all")
            w = max(self._canvas.winfo_width(), 1)
            h = 8
            _draw_round_rect(self._canvas, 0, 1, w, h - 1, RADIUS_PROGRESS, fill=COLORS["bg_input"], outline="")
            fill = int((w - 2) * self._pct / 100.0)
            if fill > 4:
                _draw_round_rect(self._canvas, 1, 2, 1 + fill, h - 2, RADIUS_PROGRESS, fill=COLORS["green"], outline="")
        except Exception:
            pass


class DarkDropdown(tk.Frame):
    def __init__(self, parent, variable: tk.StringVar, on_select=None) -> None:
        super().__init__(parent, bg=COLORS["bg_secondary"])
        self.var = variable
        self._values: List[str] = []
        self._on_select = on_select
        self.canvas = tk.Canvas(self, height=38, bg=COLORS["bg_secondary"], highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.X, expand=True)

        self.inner = tk.Frame(self.canvas, bg=COLORS["bg_input"])
        self.label = tk.Label(
            self.inner,
            textvariable=variable,
            bg=COLORS["bg_input"],
            fg=COLORS["text_normal"],
            font=_mono_font(10),
            anchor=tk.W,
            padx=12,
            pady=8,
        )
        self.label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            self.inner,
            text="▾",
            bg=COLORS["bg_input"],
            fg=COLORS["text_muted"],
            padx=10,
        ).pack(side=tk.RIGHT)

        inset = _rounded_inset(RADIUS_INPUT)
        self._inset = inset
        self._win = self.canvas.create_window(inset, inset, anchor=tk.NW, window=self.inner)
        for widget in (self.canvas, self.inner, self.label):
            widget.bind("<Button-1>", self._open_menu)
        self.canvas.bind("<Configure>", self._paint)
        variable.trace_add("write", lambda *_: self._paint())

    def _paint(self, _event=None) -> None:
        w = max(self.canvas.winfo_width(), 4)
        h = max(self.canvas.winfo_height(), 38)
        self.canvas.delete("dd")
        _draw_rounded_panel(self.canvas, w, h, RADIUS_INPUT, fill=COLORS["bg_input"], tag="dd")
        self.canvas.tag_lower("dd")
        inset = self._inset
        self.canvas.coords(self._win, inset, inset)
        self.canvas.itemconfigure(
            self._win,
            width=max(w - inset * 2, 1),
            height=max(h - inset * 2, 1),
        )

    def set_values(self, values: List[str]) -> None:
        self._values = list(values)

    def _open_menu(self, _event=None) -> None:
        if not self._values:
            return
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=COLORS["bg_input"],
            fg=COLORS["text_normal"],
            activebackground=COLORS["blurple"],
            activeforeground=COLORS["white"],
            borderwidth=0,
        )
        for value in self._values:
            menu.add_command(label=value, command=lambda v=value: self._pick(v))
        try:
            menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())
        finally:
            menu.grab_release()

    def _pick(self, value: str) -> None:
        self.var.set(value)
        if self._on_select:
            self._on_select()
# endregion UI widgets


# region App paths & helpers
def app_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "DiscordArm64StereoPatcher"


def log_path() -> Path:
    return app_data_dir() / "arm64_stereo_patcher.log"


def safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def human_exc(e: BaseException) -> str:
    return f"{type(e).__name__}: {e}"
# endregion App paths & helpers


# region Discord process control
_DISCORD_CLIENTS = (
    ("discordcanary", "Discord Canary", "Discord Canary.app"),
    ("discordptb", "Discord PTB", "Discord PTB.app"),
    ("discorddevelopment", "Discord Development", "Discord Development.app"),
    ("discord", "Discord", "Discord.app"),
)


def resolve_client_from_node(node: Path) -> Tuple[str, str, str]:
    s = str(node).lower()
    for key, app_name, bundle in _DISCORD_CLIENTS:
        if f"/{key}/" in s or f"application support/{key}" in s:
            return key, app_name, bundle
    return "discord", "Discord", "Discord.app"


def _lsof_holders(path: Path) -> list[str]:
    if sys.platform != "darwin":
        return []
    try:
        r = subprocess.run(["lsof", "-t", str(path)], capture_output=True, text=True, check=False)
    except Exception:
        return []
    if r.returncode != 0:
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def is_file_in_use(path: Path) -> bool:
    return bool(_lsof_holders(path))


def _pgrep_match(pattern: str) -> bool:
    try:
        r = subprocess.run(["pgrep", "-if", pattern], capture_output=True, text=True, check=False)
    except Exception:
        return False
    return r.returncode == 0


def is_discord_running_for_node(node: Path) -> bool:
    key, app_name, bundle = resolve_client_from_node(node)
    for pattern in (bundle, app_name, f"Application Support/{key}"):
        if _pgrep_match(pattern):
            return True
    return False


def close_discord_for_node(node: Path, log: LogSink) -> None:
    if sys.platform != "darwin":
        return
    key, app_name, _bundle = resolve_client_from_node(node)
    running = is_discord_running_for_node(node)
    locked = is_file_in_use(node)
    if not running and not locked:
        log.ok("Discord is not running")
        return

    log.info(f"Closing {app_name}...")
    subprocess.run(
        ["osascript", "-e", f'tell application "{app_name}" to quit'],
        capture_output=True,
        text=True,
        check=False,
    )
    subprocess.run(["killall", app_name], capture_output=True, text=True, check=False)
    subprocess.run(["pkill", "-f", f"Application Support/{key}"], capture_output=True, text=True, check=False)

    for _ in range(24):
        if not is_file_in_use(node) and not is_discord_running_for_node(node):
            time.sleep(0.5)
            log.ok("Discord closed")
            return
        time.sleep(0.25)

    log.warn("Discord did not exit cleanly — forcing...")
    subprocess.run(["pkill", "-9", "-f", f"Application Support/{key}"], capture_output=True, text=True, check=False)
    subprocess.run(["killall", "-9", app_name], capture_output=True, text=True, check=False)
    for pid in _lsof_holders(node):
        try:
            subprocess.run(["kill", "-9", pid], capture_output=True, text=True, check=False)
        except Exception:
            pass
    time.sleep(0.5)

    if is_file_in_use(node) or is_discord_running_for_node(node):
        raise RuntimeError(
            f"Could not close {app_name}. The voice module is still in use.\n"
            f"Quit Discord from the menu bar (or Activity Monitor) and try again."
        )
    log.ok("Discord closed")


def relaunch_discord_for_node(node: Path, log: LogSink) -> None:
    if sys.platform != "darwin":
        return
    _key, app_name, bundle = resolve_client_from_node(node)
    try:
        r = subprocess.run(["open", "-a", app_name], capture_output=True, text=True, check=False)
        if r.returncode == 0:
            log.ok(f"Relaunched {app_name}")
            return
    except Exception:
        pass
    for app_path in (Path("/Applications") / bundle, Path.home() / "Applications" / bundle):
        if app_path.is_dir():
            subprocess.run(["open", str(app_path)], check=False)
            log.ok(f"Relaunched {app_path}")
            return
    log.warn(f"Could not relaunch {app_name} automatically — open it manually.")
# endregion Discord process control


# region Voice backup download (GitHub)
def _github_request_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "DiscordVoicePatcher-macOS",
    }
    token = (
        os.environ.get("DISCORD_VOICE_PATCHER_GITHUB_TOKEN", "").strip()
        or os.environ.get("GITHUB_TOKEN", "").strip()
    )
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _clear_directory_contents(path: Path) -> None:
    if not path.is_dir():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def download_voice_backup_from_github(log: LogSink) -> Path:
    """Fetch unpatched macOS voice module files from GitHub."""
    log.info("Downloading voice backup files from GitHub...")
    safe_mkdir(VOICE_BACKUP_DIR)
    if any(VOICE_BACKUP_DIR.iterdir()):
        log.info("  Clearing existing voice backup folder...")
        _clear_directory_contents(VOICE_BACKUP_DIR)

    log.info("  Fetching file list from GitHub API...")
    req = urllib.request.Request(VOICE_BACKUP_API, headers=_github_request_headers())
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError(
                "GitHub API rate limit exceeded. Set DISCORD_VOICE_PATCHER_GITHUB_TOKEN "
                "or GITHUB_TOKEN, or try again later."
            ) from e
        raise RuntimeError(f"GitHub API HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"GitHub API request failed: {e}") from e

    if not isinstance(payload, list):
        raise RuntimeError("Unexpected GitHub API response (expected a directory listing)")
    if not payload:
        raise RuntimeError("GitHub repository response is empty.")

    file_count = 0
    failed: List[str] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        name = item.get("name")
        url = item.get("download_url")
        if not name or not url:
            continue
        dest = VOICE_BACKUP_DIR / name
        log.info(f"  Downloading: {name}")
        try:
            freq = urllib.request.Request(url, headers=_github_request_headers())
            with urllib.request.urlopen(freq, timeout=120) as fr:
                data = fr.read()
            if not data:
                raise RuntimeError("downloaded file is empty")
            dest.write_bytes(data)
            if dest.suffix.lower() in (".node", ".dylib") and dest.stat().st_size < 1024:
                log.warn(f"  [!] Warning: {name} seems too small ({dest.stat().st_size} bytes)")
            file_count += 1
        except Exception as e:
            log.warn(f"  [!] Failed to download {name}: {human_exc(e)}")
            failed.append(name)

    if file_count == 0:
        raise RuntimeError("No valid files were downloaded from GitHub.")
    if failed:
        log.warn(f"  [!] Warning: {len(failed)} file(s) failed to download")
    log.ok(f"Downloaded {file_count} voice backup file(s)")
    return VOICE_BACKUP_DIR


def verify_downloaded_voice_node(node_path: Path, log: LogSink) -> None:
    if not node_path.is_file():
        raise RuntimeError(f"discord_voice.node was not found in voice backup folder: {node_path}")
    size = node_path.stat().st_size
    node_md5 = md5_file(node_path)
    log.info(f"Voice node downloaded: {size / (1024 * 1024):.2f} MB | MD5={node_md5}")
    expected_md5 = str(PATCHES_META.get("md5") or "").lower()
    if expected_md5 and node_md5 != expected_md5:
        raise RuntimeError(
            "Offsets do not match the downloaded discord_voice.node build.\n"
            f"  Downloaded node MD5: {node_md5}\n"
            f"  OffsetsMeta MD5:     {expected_md5}\n"
            "Update PATCHES_META in the patcher for this voice module build."
        )
    expected_size = PATCHES_META.get("file_size")
    if expected_size and int(expected_size) != size:
        log.warn(
            f"Warning: PATCHES_META file_size ({expected_size}) "
            f"does not match downloaded node size ({size})"
        )


def get_prepared_voice_backup_path(log: LogSink) -> Path:
    backup_dir = download_voice_backup_from_github(log)
    verify_downloaded_voice_node(backup_dir / "discord_voice.node", log)
    return backup_dir


def install_voice_bundle(node: Path, backup_dir: Path, log: LogSink) -> None:
    voice_dir = node.parent
    if not voice_dir.is_dir():
        raise RuntimeError(f"Voice directory does not exist: {voice_dir}")
    backup_files = [p for p in backup_dir.iterdir() if p.is_file() or p.is_dir()]
    if not backup_files:
        raise RuntimeError(f"No files found in voice backup path: {backup_dir}")

    log.info(f"Removing old voice module files in {_short_home_path(voice_dir)}...")
    _clear_directory_contents(voice_dir)
    log.info("Installing compatible voice module...")
    for item in backup_files:
        dest = voice_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    if not node.is_file():
        raise RuntimeError(
            "discord_voice.node not found after installing voice module. "
            "Join a voice channel in Discord first, or check the install path."
        )
    log.ok(f"Voice backup contains {len(backup_files)} file(s) — installed into voice folder")
# endregion Voice backup download (GitHub)


# region Installation discovery & status
def discover_discord_installations() -> List[Tuple[str, str]]:
    search = [
        ("Discord Stable", Path.home() / "Library/Application Support/discord"),
        ("Discord Canary", Path.home() / "Library/Application Support/discordcanary"),
        ("Discord PTB", Path.home() / "Library/Application Support/discordptb"),
    ]
    found: List[Tuple[str, str]] = []
    for name, base in search:
        if not base.is_dir():
            continue
        for node in base.rglob("discord_voice.node"):
            if node.is_file():
                found.append((name, str(node)))
                break
    return found


def format_node_status_line(node_path: str) -> str:
    node = Path(node_path)
    if not node.is_file():
        return "Node file not found"
    ver = _version_from_node(node)
    state = check_patch_status(node_path)
    labels = {
        "unpatched": "Unpatched (original)",
        "patched": "Patched (stereo enabled)",
        "unknown": "Unknown version",
        "error": "Error reading file",
    }
    size_mb = node.stat().st_size / (1024 * 1024)
    return f"v{ver} | {labels.get(state, state)} | {size_mb:.2f} MB"


def check_patch_status(node_path: str) -> str:
    try:
        state = _patch_state(Path(node_path))
        if state == "unpatched":
            return "unpatched"
        if state == "patched":
            return "patched"
        if state in ("not found", "error"):
            return "error"
        return "unknown"
    except Exception:
        return "error"


def list_backups() -> List[Tuple[str, str, str]]:
    """Return (path, date, size) tuples for available backups."""
    result: List[Tuple[str, str, str]] = []
    roots = [BACKUP_DIR, app_data_dir() / "backups"]
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        files: List[Path] = []
        for pat in ("*.backup", "discord_voice.node.UNPATCHED"):
            files.extend(root.rglob(pat))
        for b in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
            key = str(b.resolve())
            if key in seen or not b.is_file():
                continue
            seen.add(key)
            st = b.stat()
            date = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            size_mb = st.st_size / (1024 * 1024)
            result.append((str(b), date, f"{size_mb:.2f} MB"))
    return result


def _version_from_node(node: Path) -> str:
    m = re.search(r"/app-([0-9.]+)/modules/", str(node))
    if m:
        return m.group(1)
    for part in node.parts:
        if part.startswith("app-"):
            return part.replace("app-", "")
    return "unknown"


def _patch_state(node: Path) -> str:
    if not node.is_file():
        return "not found"
    try:
        data = node.read_bytes()
        patches = [p for p in find_macos_stereo_patches(data) if p.get("arch") == "arm64"]
        if not patches:
            return "unknown"
        patched = sum(1 for p in patches if p.get("already_patched"))
        if patched == len(patches):
            return "patched"
        if patched == 0:
            return "unpatched"
        return f"partial ({patched}/{len(patches)})"
    except Exception:
        return "unknown"
# endregion Installation discovery & status


# region Backup & patch workflow
def backup_path_for(node: Path) -> Path:
    key = str(node.parent).replace("\\", "_").replace("/", "_").replace(":", "")
    return app_data_dir() / "backups" / key / "discord_voice.node.UNPATCHED"


def meta_path_for(node: Path) -> Path:
    key = str(node.parent).replace("\\", "_").replace("/", "_").replace(":", "")
    return app_data_dir() / "backups" / key / "meta.json"


def ensure_backup(node: Path, log: LogSink) -> Path:
    bd = backup_path_for(node)
    if bd.is_file():
        try:
            cur_md5 = md5_file(node)
            bak_md5 = md5_file(bd)
            expected = str(PATCHES_META.get("md5") or "")
            if expected and cur_md5 == expected and bak_md5 != expected:
                shutil.copy2(node, bd)
                log.ok(f"Backup refreshed (matched stock): {_short_home_path(bd)}")
            else:
                log.info(f"Backup already exists: {_short_home_path(bd)}")
        except Exception:
            log.info(f"Backup already exists: {_short_home_path(bd)}")
        return bd
    safe_mkdir(bd.parent)
    shutil.copy2(node, bd)
    log.ok(f"Backup saved: {_short_home_path(bd)}")
    return bd


def record_last_patch(node: Path) -> None:
    mp = meta_path_for(node)
    safe_mkdir(mp.parent)
    mp.write_text(json.dumps({"last_patch_utc": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")


def patch_node_file(node_path: Path, *, write: bool = True) -> tuple[int, int, list[str]]:
    data = bytearray(node_path.read_bytes())
    applied, skipped, names = apply_all_arm64_patches(data, arm64_only=True)
    if write and applied > 0:
        node_path.write_bytes(data)
    return applied, skipped, names


def prepare_and_patch_node(
    node_path: Path,
    log: LogSink,
    *,
    patch_local: bool = False,
) -> tuple[int, int, list[str]]:
    """Download stock voice bundle (unless patch_local), install, then patch."""
    if not patch_local:
        get_prepared_voice_backup_path(log)
    else:
        log.info("Patch local only: using existing voice module files (no download).")

    ensure_backup(node_path, log)
    close_discord_for_node(node_path, log)

    if not patch_local:
        install_voice_bundle(node_path, VOICE_BACKUP_DIR, log)

    try:
        os.chmod(node_path, 0o644)
    except Exception:
        pass

    data = bytearray(node_path.read_bytes())
    applied, skipped, names = apply_all_arm64_patches(data, arm64_only=True)
    if applied == 0 and skipped == 0:
        raise RuntimeError("No ARM64 patches found (not a fat Mach-O or symbols missing).")

    if applied > 0:
        _write_node_bytes(node_path, data, log)
        record_last_patch(node_path)
    else:
        log.ok(f"Already patched ({skipped} site(s) verified)")

    # Always (re)sign the node and Discord.app — even when already patched — so a
    # previously blocked re-sign (e.g. missing App Management permission on
    # macOS 15/26) can be repaired simply by running the patcher again.
    codesign_node(node_path, log)
    resign_ok = enable_library_validation_bypass(log, node_path)
    _report_patch_coverage(node_path, log, applied=applied)
    if not resign_ok:
        _log_resign_required(log, node_path)

    return applied, skipped, names, resign_ok


def restore_node_file(node_path: Path, log: LogSink) -> bool:
    bd = backup_path_for(node_path)
    if not bd.is_file():
        log.fail(f"No backup found for: {_short_home_path(node_path)}")
        log.fail(f"Expected backup at: {_short_home_path(bd)}")
        return False
    close_discord_for_node(node_path, log)
    shutil.copy2(bd, node_path)
    codesign_node(node_path, log)
    # Patching re-signs the client app ad-hoc, so a prior (possibly broken) patch
    # can leave the bundle unlaunchable. Re-seal the SAME client here so restore
    # fully recovers it.
    app_path = find_discord_app(node_path)
    if app_path is not None:
        resign_discord_app_adhoc(app_path, log)
    log.ok("Binary restored from backup")
    return True
# endregion Backup & patch workflow


# region CLI
def run_cli(argv: list[str]) -> int:
    patch_local = False
    args = list(argv)
    while args and args[0] in ("--patch-local", "--patch-local-only"):
        patch_local = True
        args.pop(0)

    if not args:
        print(f"Usage: {Path(sys.argv[0]).name} <path/to/discord_voice.node>", file=sys.stderr)
        print(f"       {Path(sys.argv[0]).name} --restore <path/to/discord_voice.node>", file=sys.stderr)
        print(f"       {Path(sys.argv[0]).name} --patch-local <path/to/discord_voice.node>", file=sys.stderr)
        return 1

    if args[0] == "--restore":
        if len(args) < 2:
            print("Missing path for --restore", file=sys.stderr)
            return 1
        node_path = Path(args[1])
        if not node_path.is_file():
            print(f"File not found: {node_path}", file=sys.stderr)
            return 1
    else:
        node_path = Path(args[0])
        if not node_path.is_file():
            print(f"File not found: {node_path}", file=sys.stderr)
            return 1

    class _CliLog:
        def info(self, msg: str) -> None:
            print(msg)

        def ok(self, msg: str) -> None:
            print(f"OK: {msg}")

        def warn(self, msg: str) -> None:
            print(f"WARN: {msg}", file=sys.stderr)

        def fail(self, msg: str) -> None:
            print(f"FAIL: {msg}", file=sys.stderr)

    log = _CliLog()
    try:
        if args[0] == "--restore":
            ok = restore_node_file(node_path, log)
            return 0 if ok else 1

        applied, skipped, names, resign_ok = prepare_and_patch_node(node_path, log, patch_local=patch_local)
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    if applied > 0:
        print(f"  Applied {applied} ARM64 patches (stereo + bitrate + filters)")
        for n in names:
            if not n.endswith("(already)"):
                print(f"    - {n}")
    elif skipped > 0:
        print(f"  ARM64 stereo patches already applied ({skipped} sites checked)")
    if resign_ok:
        relaunch_discord_for_node(node_path, log)
    else:
        log.warn("Not relaunching Discord — fix the re-sign above first (it would just crash).")
        return 2
    return 0
# endregion CLI


# region Code signing
def _refresh_node_inode(node: Path) -> None:
    """Avoid macOS caching the old code signature by inode."""
    tmp = node.with_suffix(node.suffix + ".tmp_inode")
    node.rename(tmp)
    tmp.replace(node)


def find_discord_app(node: Optional[Path] = None) -> Optional[Path]:
    """Locate the .app bundle for the client whose node is being patched.

    When ``node`` is given we resolve the matching client (Stable / PTB / Canary /
    Development) so we re-sign the SAME app whose voice node we patched. Re-signing
    the wrong bundle (e.g. always Discord.app while patching PTB) leaves library
    validation ON for the real client, so it refuses to load the ad-hoc patched
    node and voice produces no audio. With no node, fall back to any client found.
    """
    if node is not None:
        _key, _name, bundle = resolve_client_from_node(node)
        bundles = [bundle]
    else:
        bundles = [b for _k, _n, b in _DISCORD_CLIENTS]
    for bundle in bundles:
        for base in (Path("/Applications"), Path.home() / "Applications"):
            cand = base / bundle
            if cand.is_dir():
                return cand
    return None


def resign_discord_app_adhoc(app_path: Path, log: LogSink) -> bool:
    """Deep ad-hoc re-sign of Discord.app *without* the hardened runtime.

    On Apple Silicon every binary must carry at least an ad-hoc signature to run.
    Patching discord_voice.node and re-signing it ad-hoc breaks the original
    Developer-ID seal, so the app must be re-signed too. We deliberately do NOT
    pass ``--options runtime``: the hardened runtime is what enforces library
    validation (which would block dlopen of our ad-hoc .node) and the
    JIT / executable-memory restrictions (which the Electron renderer needs).
    A plain deep ad-hoc signature re-seals the whole bundle consistently, lets
    Discord launch, and lets it load the patched node — no per-binary
    entitlement surgery (which previously left the bundle unlaunchable).
    """
    if sys.platform != "darwin":
        return True
    # Strip quarantine / stale metadata so codesign can seal cleanly.
    subprocess.run(["xattr", "-cr", str(app_path)], capture_output=True, text=True, check=False)
    sr = subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if sr.returncode != 0:
        err = (sr.stderr or sr.stdout or "").strip()
        log.warn(f"Discord.app re-sign failed — {err or 'unknown error'}")
        if "not permitted" in err.lower() or "permission" in err.lower():
            log.warn("Grant this app 'App Management' access in System Settings > Privacy & Security, then retry.")
        return False
    # codesign can re-add xattrs; clear again so Gatekeeper sees a clean bundle.
    subprocess.run(["xattr", "-cr", str(app_path)], capture_output=True, text=True, check=False)
    log.ok("Discord.app re-signed ad-hoc (launch + library-validation bypass)")
    vr = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(app_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if vr.returncode != 0:
        log.warn(f"codesign verify warning: {(vr.stderr or vr.stdout or '').strip()}")
    return True


def enable_library_validation_bypass(log: LogSink, node: Optional[Path] = None) -> bool:
    """Re-sign the patched node's Discord app so it can dlopen our ad-hoc node."""
    if sys.platform != "darwin":
        return True
    app_path = find_discord_app(node)
    if app_path is None:
        log.warn("Discord app bundle not found — skipping app re-sign")
        return False
    return resign_discord_app_adhoc(app_path, log)


def _log_resign_required(log: LogSink, node: Optional[Path] = None) -> None:
    """Loud, actionable notice when Discord.app could not be re-signed.

    Without the re-sign, macOS keeps Discord under the hardened runtime with
    library validation ON, so it cannot load our ad-hoc patched voice node —
    Discord then fails to open or crashes on joining a voice channel.
    """
    app = find_discord_app(node) or Path("/Applications/Discord.app")
    log.warn("")
    log.warn("=================== ACTION REQUIRED ===================")
    log.warn("Discord.app could NOT be re-signed. macOS will block the")
    log.warn("patched voice node, so Discord may fail to open or will")
    log.warn("CRASH when you join a voice channel.")
    log.warn("")
    log.warn("On macOS 15 (Sequoia) / 26 (Tahoe) this needs permission:")
    log.warn("  1. System Settings > Privacy & Security > App Management")
    log.warn("  2. Enable your terminal (Terminal/iTerm) and/or Python")
    log.warn("  3. FULLY quit that app, reopen it, then run this patcher again")
    log.warn("")
    log.warn("Or run these once in Terminal (after granting the permission):")
    log.warn(f'  codesign --force --deep --sign - "{app}"')
    log.warn(f'  xattr -cr "{app}"')
    log.warn("=======================================================")


def codesign_node(node: Path, log: LogSink) -> None:
    if sys.platform != "darwin":
        return
    try:
        _refresh_node_inode(node)
        subprocess.run(["codesign", "--remove-signature", str(node)], capture_output=True, text=True, check=False)
        r = subprocess.run(
            ["codesign", "--force", "--sign", "-", str(node)],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(["xattr", "-cr", str(node)], capture_output=True, text=True, check=False)
        if r.returncode == 0:
            log.ok("Ad-hoc codesign completed")
            vr = subprocess.run(
                ["codesign", "--verify", "--verbose", str(node)],
                capture_output=True,
                text=True,
                check=False,
            )
            if vr.returncode != 0:
                log.warn(f"codesign verify failed: {(vr.stderr or vr.stdout or '').strip()}")
        else:
            err = (r.stderr or r.stdout or "").strip()
            log.warn(f"codesign failed: {err or 'unknown error'}")
    except Exception as e:
        log.warn(f"codesign skipped: {human_exc(e)}")
# endregion Code signing


# region Diagnostics & verification
def _report_patch_coverage(node: Path, log: LogSink, *, applied: int) -> None:
    data = node.read_bytes()
    missing = missing_arm64_stereo_patch_names(data)
    found = [p for p in find_macos_stereo_patches(data) if p.get("arch") == "arm64"]
    patched_n = sum(1 for p in found if p.get("already_patched"))
    log.info("")
    log.info(f"Coverage: {patched_n}/{len(ARM64_STEREO_SPEC_NAMES)} spec sites present on disk")
    if missing:
        log.warn(f"Missing {len(missing)} patch site(s) — stereo may not work until these are found:")
        for name in missing:
            log.warn(f"  - {name}")
    if applied > 0 and patched_n < len(ARM64_STEREO_SPEC_NAMES) - 1:
        log.warn(
            "Incomplete patch set. Restore from UNPATCHED backup, update the patcher, and patch again with Discord fully quit."
        )


def scan_patches(node: Path, log: LogSink) -> list:
    patches = find_macos_stereo_patches(node.read_bytes())
    arm = [p for p in patches if p.get("arch") == "arm64"]
    log.info(f"Found {len(arm)} ARM64 stereo patch site(s) in fat binary")
    for p in arm[:30]:
        log.info(f"  {p['name']} @ 0x{p['fat_offset']:X}  {p['orig']} -> {p['patch']}")
    if len(arm) > 30:
        log.info(f"  ... and {len(arm) - 30} more")
    return arm


def _write_node_bytes(node: Path, data: bytes | bytearray, log: LogSink) -> None:
    if is_file_in_use(node):
        raise RuntimeError("discord_voice.node is locked — close Discord and try again.")
    node.write_bytes(data)
    log.ok("Binary patched on disk")


def verify_patches(node: Path, log: LogSink) -> None:
    data = node.read_bytes()
    patches = [p for p in find_macos_stereo_patches(data) if p.get("arch") == "arm64"]
    if not patches:
        raise RuntimeError("No ARM64 stereo patch sites found in this binary.")
    ok_n = warn_n = 0
    log.info("")
    for p in patches:
        fo = p["fat_offset"]
        orig = _hex_bytes(p["orig"])
        patch_b = _hex_bytes(p["patch"])
        if p.get("already_patched") or data[fo : fo + len(patch_b)] == patch_b:
            log.ok(f"  {p['name']}")
            ok_n += 1
        elif data[fo : fo + len(orig)] == orig:
            log.warn(f"  {p['name']} — still original bytes")
            warn_n += 1
        else:
            log.warn(f"  {p['name']} — unexpected bytes @ 0x{fo:X}")
            warn_n += 1
    log.info("")
    if warn_n == 0:
        log.ok(f"Verify passed: {ok_n}/{len(patches)} ARM64 site(s) patched")
    else:
        log.warn(f"Verify: {ok_n} OK, {warn_n} need attention ({len(patches)} total)")


def export_patched_node(node: Path, export_dir: Path, log: LogSink) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(node, export_dir / "discord_voice.node")
    bd = backup_path_for(node)
    if bd.is_file():
        ob = export_dir / "original_backup"
        ob.mkdir(exist_ok=True)
        shutil.copy2(bd, ob / "discord_voice.node")
    (export_dir / "INSTALL_GUIDE.txt").write_text(
        "Discord Stereo Patcher — ARM64 export\n"
        "=====================================\n\n"
        "1. Quit Discord completely.\n"
        "2. Replace your discord_voice.node with the exported copy.\n"
        "3. Run: codesign --force --sign - discord_voice.node\n"
        "4. Reopen Discord and test stereo in a voice channel.\n",
        encoding="utf-8",
    )
    log.ok(f"Files exported to: {export_dir}")
    return export_dir


def diagnose_node(node: Path, log: "GuiLog") -> None:
    log.info(f"Path: {node}")
    if not node.is_file():
        raise RuntimeError("discord_voice.node does not exist.")
    st = node.stat()
    log.info(f"Size: {st.st_size:,} bytes ({st.st_size / (1024 * 1024):.2f} MB)")
    log.info(f"Discord build: v{_version_from_node(node)}")
    log.info(f"Patch state: {check_patch_status(str(node))}")
    bd = backup_path_for(node)
    log.info(f"Backup exists: {'yes' if bd.is_file() else 'no'} — {_short_home_path(bd)}")
    scan_patches(node, log)
    verify_patches(node, log)
# endregion Diagnostics & verification


# region GUI application
class GuiLog:
    """Adapts PatcherApp._log to the patcher log interface."""

    def __init__(self, app: "PatcherApp") -> None:
        self._app = app

    def info(self, msg: str) -> None:
        self._app._log(msg)

    def ok(self, msg: str) -> None:
        self._app._log(f"  [OK] {msg}")

    def warn(self, msg: str) -> None:
        self._app._log(f"  [WARN] {msg}", "warn")

    def fail(self, msg: str) -> None:
        self._app._log(f"  [FAIL] {msg}", "error")


class PatcherApp:
    def __init__(self) -> None:
        if tk is None:
            raise RuntimeError(
                "tkinter is not available.\n"
                "macOS: install Python from python.org or use system python3 with tk support."
            )
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("760x780")
        self.root.minsize(700, 700)
        self.root.configure(bg=COLORS["bg_dark"])

        self.discord_installations: List[Tuple[str, str]] = []
        self.selected_node = tk.StringVar(value="")
        self.patch_local_only = tk.BooleanVar(value=False)
        self.is_running = False

        self._resize_job = None
        self._build_ui()
        self.root.bind("<Map>", lambda _e: self.root.after_idle(self._repaint_rounded))
        # Reflow the canvas-embedded rounded panels on every window resize,
        # including macOS native fullscreen — Tk/Aqua otherwise leaves the
        # embedded log/cards at a stale size, so the log appears hidden.
        self.root.bind("<Configure>", self._on_root_configure)
        self.root.after(50, self._repaint_rounded)
        self.root.after(200, self._repaint_rounded)
        self._scan_installations()

    def _on_root_configure(self, event=None) -> None:
        if event is not None and event.widget is not self.root:
            return
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(60, self._repaint_rounded)

    def _repaint_rounded(self) -> None:
        self._resize_job = None
        self.root.update_idletasks()
        for widget in getattr(self, "_rounded_widgets", ()):
            paint = getattr(widget, "_paint", None)
            if callable(paint):
                paint()
        for btn in getattr(self, "_action_buttons", ()):
            if hasattr(btn, "_draw"):
                btn._draw()

    def _build_ui(self) -> None:
        main = tk.Frame(self.root, bg=COLORS["bg_dark"])
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        tk.Label(
            main,
            text=APP_NAME,
            bg=COLORS["bg_dark"],
            fg=COLORS["text_header"],
            font=_ui_font_display(22),
            anchor=tk.W,
        ).pack(fill=tk.X)
        tk.Label(
            main,
            text=f"macOS ARM64  |  48 kHz  |  248 kbps  |  Stereo  |  Forced CELT  |  v{APP_VERSION}",
            bg=COLORS["bg_dark"],
            fg=COLORS["text_muted"],
            font=_ui_font(10),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(4, 8))

        badges = tk.Frame(main, bg=COLORS["bg_dark"])
        badges.pack(fill=tk.X, pady=(0, 14))
        _badge(badges, "Apple Silicon (ARM64 only)", BADGE_GREEN_BG, BADGE_GREEN_FG).pack(side=tk.LEFT, padx=(0, 8))
        _badge(badges, "Stereo · 48 kHz · 248 kbps · CELT · Filterless", BADGE_GREEN_BG, BADGE_GREEN_FG).pack(side=tk.LEFT)

        install_card = SectionCard(main, "Discord Installation")
        install_card.pack(fill=tk.X, pady=(0, 10))
        sel_row = tk.Frame(install_card.body, bg=COLORS["bg_secondary"])
        sel_row.pack(fill=tk.X)
        self.install_picker = DarkDropdown(
            sel_row,
            self.selected_node,
            on_select=self._on_install_selected,
        )
        self.install_picker.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.btn_rescan = ThemedButton(
            sel_row,
            "Rescan",
            COLORS["bg_input"],
            COLORS["bg_tertiary"],
            self._scan_installations,
            fg=COLORS["text_normal"],
        )
        self.btn_rescan.pack(side=tk.LEFT)
        self.status_label = tk.Label(
            install_card.body,
            text="Scanning...",
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_muted"],
            font=_ui_font(10),
            anchor=tk.W,
        )
        self.status_label.pack(fill=tk.X, pady=(8, 0))

        patch_opts = tk.Frame(install_card.body, bg=COLORS["bg_secondary"])
        patch_opts.pack(fill=tk.X, pady=(8, 0))
        tk.Checkbutton(
            patch_opts,
            text="Patch local only (skip GitHub download)",
            variable=self.patch_local_only,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_muted"],
            activebackground=COLORS["bg_secondary"],
            activeforeground=COLORS["text_normal"],
            selectcolor=COLORS["bg_input"],
            font=_ui_font(10),
            anchor=tk.W,
        ).pack(side=tk.LEFT)

        actions_card = SectionCard(main, "Actions")
        actions_card.pack(fill=tk.X, pady=(0, 10))
        btn_row = tk.Frame(actions_card.body, bg=COLORS["bg_secondary"])
        btn_row.pack(fill=tk.X)
        self.patch_btn = ThemedButton(
            btn_row,
            "Patch Discord",
            COLORS["blurple"],
            COLORS["blurple_dark"],
            self._start_patch,
        )
        self.patch_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.restore_btn = ThemedButton(
            btn_row,
            "Restore",
            COLORS["bg_input"],
            COLORS["bg_tertiary"],
            self._start_restore,
            fg=COLORS["text_normal"],
        )
        self.restore_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.verify_btn = ThemedButton(
            btn_row,
            "Verify",
            COLORS["bg_input"],
            COLORS["bg_tertiary"],
            self._start_verify,
            fg=COLORS["text_normal"],
        )
        self.verify_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.diagnose_btn = ThemedButton(
            btn_row,
            "Diagnose",
            COLORS["bg_input"],
            COLORS["bg_tertiary"],
            self._start_diagnose,
            fg=COLORS["text_normal"],
        )
        self.diagnose_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.export_btn = ThemedButton(
            btn_row,
            "Export",
            COLORS["bg_input"],
            COLORS["bg_tertiary"],
            self._start_export,
            fg=COLORS["text_normal"],
        )
        self.export_btn.pack(side=tk.LEFT)

        backup_row = tk.Frame(actions_card.body, bg=COLORS["bg_secondary"])
        backup_row.pack(fill=tk.X, pady=(12, 4))
        tk.Label(
            backup_row,
            text=f"Backups: {_short_home_path(BACKUP_DIR)}",
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_muted"],
            font=_ui_font(10),
            anchor=tk.W,
        ).pack(side=tk.LEFT)
        self.btn_open_backups = ThemedButton(
            backup_row,
            "Open in Finder",
            COLORS["bg_input"],
            COLORS["bg_tertiary"],
            self._open_backups_folder,
            fg=COLORS["text_normal"],
        )
        self.btn_open_backups.pack(side=tk.RIGHT)

        import platform

        arch = platform.machine().lower()
        if arch == "arm64":
            sys1 = "Target: Apple Silicon discord_voice.node (ARM64 slice)"
            sys2 = "Intel/x86_64 slices are not modified by this patcher"
        else:
            sys1 = f"Host CPU: {arch} — patcher still targets the ARM64 slice inside the fat binary"
            sys2 = "Run on Apple Silicon or patch a copied discord_voice.node from Discord.app"
        tk.Label(
            actions_card.body,
            text=sys1,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_muted"],
            font=_ui_font(10),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(4, 0))
        tk.Label(
            actions_card.body,
            text=sys2,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_muted"],
            font=_ui_font(10),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(2, 0))

        self.progress = ProgressBar(actions_card.body)
        self.progress.pack(fill=tk.X, pady=(12, 6))
        self.progress_label = tk.Label(
            actions_card.body,
            text="Ready",
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_muted"],
            font=_ui_font(10),
            anchor=tk.W,
        )
        self.progress_label.pack(fill=tk.X)

        log_card = SectionCard(main, "Log Output")
        log_card.pack(fill=tk.BOTH, expand=True)
        self.log_panel = RoundedLogPanel(log_card.body)
        self.log_panel.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log_text = self.log_panel.text
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.tag_configure("ok", foreground=COLORS["green"])
        self.log_text.tag_configure("error", foreground=COLORS["red"])
        self.log_text.tag_configure("warn", foreground=COLORS["yellow"])
        self.log_text.tag_configure("info", foreground=COLORS["text_muted"])
        self.log_text.tag_configure("header", foreground=COLORS["blurple"], font=(*_mono_font(10), "bold"))

        self._rounded_widgets = (install_card, actions_card, log_card, self.install_picker, self.log_panel)
        self._action_buttons = (
            self.btn_rescan,
            self.patch_btn,
            self.restore_btn,
            self.verify_btn,
            self.diagnose_btn,
            self.export_btn,
            self.btn_open_backups,
        )

    def _log(self, message: str, tag: Optional[str] = None) -> None:
        def _append() -> None:
            self.log_text.configure(state=tk.NORMAL)
            if tag:
                self.log_text.insert(tk.END, message + "\n", tag)
            elif "[OK]" in message:
                self.log_text.insert(tk.END, message + "\n", "ok")
            elif "[FAIL]" in message or "ERROR" in message:
                self.log_text.insert(tk.END, message + "\n", "error")
            elif "[WARN]" in message or "WARNING" in message:
                self.log_text.insert(tk.END, message + "\n", "warn")
            elif message.startswith("===") or message.startswith("---"):
                self.log_text.insert(tk.END, message + "\n", "header")
            else:
                self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
            try:
                with log_path().open("a", encoding="utf-8") as f:
                    f.write(message + "\n")
            except Exception:
                pass

        self.root.after(0, _append)

    def _set_progress(self, current: int, total: int, label: str = "") -> None:
        pct = (current / total) * 100 if total > 0 else 0
        self.root.after(0, lambda: self.progress.set(pct))
        if label:
            self.root.after(0, lambda: self.progress_label.configure(text=label))

    def _set_buttons_state(self, enabled: bool) -> None:
        for btn in self._action_buttons:
            self.root.after(0, lambda b=btn, e=enabled: b.set_enabled(e))

    def _update_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status_label.configure(text=text))

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _get_node_path(self, silent: bool = False) -> Optional[str]:
        val = self.selected_node.get()
        if not val:
            if not silent:
                messagebox.showwarning(
                    "No Installation",
                    "Please select a Discord installation first.",
                    parent=self.root,
                )
            return None
        if " — " in val:
            path = val.split(" — ", 1)[1]
        else:
            path = val
        if not os.path.isfile(path):
            if not silent:
                messagebox.showerror("File Not Found", f"Cannot find:\n{path}", parent=self.root)
            return None
        return path

    def _scan_installations(self) -> None:
        self.discord_installations = discover_discord_installations()
        values = [f"{name} — {path}" for name, path in self.discord_installations]
        self.install_picker.set_values(values)
        if values:
            self.selected_node.set(values[0])
            self._on_install_selected()
        else:
            self.selected_node.set("")
            self._update_status("No Discord installations found")

    def _on_install_selected(self, event=None) -> None:
        path = self._get_node_path(silent=True)
        if path:
            self._update_status(format_node_status_line(path))
        else:
            self._update_status("No installation selected")

    def _open_backups_folder(self) -> None:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        app_data_dir().joinpath("backups").mkdir(parents=True, exist_ok=True)
        path = str(BACKUP_DIR)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open backups folder:\n{e}", parent=self.root)

    def _ask_launch_discord(self) -> None:
        try:
            if messagebox.askyesno("Patching Complete", "Launch Discord now?", parent=self.root):
                path = self._get_node_path(silent=True)
                if path:
                    relaunch_discord_for_node(Path(path), GuiLog(self))
        except Exception:
            pass

    def _start_patch(self) -> None:
        node_path = self._get_node_path()
        if not node_path:
            return

        try:
            status = check_patch_status(node_path)
        except Exception:
            status = "unknown"

        if status == "patched":
            if not messagebox.askyesno(
                "Already Patched",
                "This binary appears to already be patched.\nRe-apply patches?",
                parent=self.root,
            ):
                return
        elif status == "unknown":
            if not messagebox.askyesno(
                "Unknown Version",
                "This binary version could not be verified.\nOffsets may not match. Continue anyway?",
                parent=self.root,
            ):
                return

        self._clear_log()
        self._set_buttons_state(False)

        def _do_patch() -> None:
            try:
                node = Path(node_path)
                log = GuiLog(self)
                patch_local = self.patch_local_only.get()
                self._log(f"=== Discord Stereo Patcher v{APP_VERSION} ===", "header")
                self._log("")
                self._set_progress(1, 3)

                applied, skipped, names, resign_ok = prepare_and_patch_node(node, log, patch_local=patch_local)

                self._set_progress(3, 3)
                self._log("")
                self._log("=== RESULTS ===", "header")
                if applied > 0:
                    self._log(f"  [OK] Applied {applied} ARM64 patch(es) (stereo + bitrate + filters)!")
                    for n in names:
                        if not n.endswith("(already)"):
                            self._log(f"    - {n}")
                elif skipped > 0:
                    self._log(f"  [OK] Already patched ({skipped} site(s) verified)")

                if not resign_ok:
                    self.root.after(
                        0,
                        lambda: self.progress_label.configure(
                            text="Patched, but Discord.app re-sign BLOCKED — see log (App Management)"
                        ),
                    )
                elif applied > 0:
                    self._log("")
                    self._log("Next steps:")
                    self._log("  1. Open Discord")
                    self._log('     macOS will ask for your keychain password because the app')
                    self._log('     was re-signed — click "Always Allow" and enter your login')
                    self._log('     (macOS user) password. If Discord keeps closing, open')
                    self._log('     Keychain Access, delete the "discord Safe Storage" item,')
                    self._log("     then reopen Discord (you may need to log in again).")
                    self._log("  2. Join a voice channel")
                    self._log("  3. Test stereo by hard-panning L/R in your DAW")
                    self.root.after(
                        0,
                        lambda: self.progress_label.configure(text=f"Complete! {applied} patches applied."),
                    )
                else:
                    self.root.after(0, lambda: self.progress_label.configure(text="Already patched"))

                if resign_ok:
                    self.root.after(100, self._ask_launch_discord)
            except Exception as e:
                self._log(f"\n  [FAIL] Error: {e}", "error")
                self.root.after(0, lambda: self.progress_label.configure(text="Error during patching"))
            finally:
                self._set_buttons_state(True)
                self.root.after(0, self._on_install_selected)

        threading.Thread(target=_do_patch, daemon=True).start()

    def _start_restore(self) -> None:
        node_path = self._get_node_path()
        if not node_path:
            return

        backups = list_backups()
        if not backups:
            messagebox.showinfo("No Backups", "No backup files found.", parent=self.root)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Select Backup to Restore")
        dialog.geometry("550x350")
        dialog.configure(bg=COLORS["bg_dark"])
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="Select a backup to restore:",
            bg=COLORS["bg_dark"],
            fg=COLORS["text_normal"],
            font=_ui_font(11),
        ).pack(padx=16, pady=(16, 8), anchor=tk.W)

        listbox = tk.Listbox(
            dialog,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_normal"],
            font=_mono_font(10),
            selectbackground=COLORS["blurple"],
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
        )
        listbox.pack(fill=tk.BOTH, expand=True, padx=16)

        for path, date, size in backups:
            listbox.insert(tk.END, f"  {date}  |  {size}  |  {os.path.basename(path)}")
        if backups:
            listbox.selection_set(0)

        def _do_restore() -> None:
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("No Selection", "Please select a backup.", parent=dialog)
                return
            backup_path = backups[sel[0]][0]
            dialog.destroy()

            self._clear_log()
            self._set_buttons_state(False)

            def _restore_thread() -> None:
                try:
                    log = GuiLog(self)
                    self._log("=== Restoring from Backup ===", "header")
                    self._log(f"  Backup: {os.path.basename(backup_path)}")
                    self._log(f"  Target: {node_path}")
                    self._log("")
                    self._log("Closing Discord...")
                    close_discord_for_node(Path(node_path), log)
                    self._log("Restoring file...")
                    shutil.copy2(backup_path, node_path)
                    codesign_node(Path(node_path), log)
                    self._log("  [OK] Binary restored")
                    self._log("  [OK] Re-signed")
                    # Repair the app bundle: a prior patch re-signs the client app
                    # ad-hoc, which can leave it unlaunchable on its own.
                    app_path = find_discord_app(Path(node_path))
                    if app_path is not None:
                        self._log(f"Re-sealing {app_path.name}...")
                        resign_discord_app_adhoc(app_path, log)
                    self._log("")
                    self._log("Restart Discord to use the original binary.")
                    self.root.after(0, lambda: self.progress_label.configure(text="Restore complete!"))
                except Exception as e:
                    self._log(f"\n  [FAIL] Error: {e}", "error")
                finally:
                    self._set_buttons_state(True)
                    self.root.after(0, self._on_install_selected)

            threading.Thread(target=_restore_thread, daemon=True).start()

        btn_frame = tk.Frame(dialog, bg=COLORS["bg_dark"])
        btn_frame.pack(fill=tk.X, padx=16, pady=12)
        ThemedButton(btn_frame, "Cancel", COLORS["bg_input"], COLORS["bg_tertiary"], dialog.destroy, fg=COLORS["text_normal"]).pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        ThemedButton(btn_frame, "Restore", COLORS["blurple"], COLORS["blurple_dark"], _do_restore).pack(side=tk.RIGHT)

    def _start_diagnose(self) -> None:
        node_path = self._get_node_path()
        if not node_path:
            return
        self._clear_log()
        self._set_buttons_state(False)

        def _do_diagnose() -> None:
            try:
                self._log("=== Diagnose ===", "header")
                self._log("")
                diagnose_node(Path(node_path), GuiLog(self))
                self.root.after(0, lambda: self.progress_label.configure(text="Diagnose complete!"))
                self.root.after(0, lambda: self.progress.set(100))
            except Exception as e:
                self._log(f"\n  [FAIL] Error: {e}", "error")
            finally:
                self._set_buttons_state(True)

        threading.Thread(target=_do_diagnose, daemon=True).start()

    def _start_verify(self) -> None:
        node_path = self._get_node_path()
        if not node_path:
            return

        self._clear_log()
        self._set_buttons_state(False)

        def _do_verify() -> None:
            try:
                self._log("=== Verifying Patch Status ===", "header")
                self._log("")
                log = GuiLog(self)
                verify_patches(Path(node_path), log)
                self.root.after(0, lambda: self.progress_label.configure(text="Verify complete!"))
            except Exception as e:
                self._log(f"\n  [FAIL] Error: {e}", "error")
            finally:
                self._set_buttons_state(True)

        threading.Thread(target=_do_verify, daemon=True).start()

    def _start_export(self) -> None:
        node_path = self._get_node_path()
        if not node_path:
            return

        self.root.update_idletasks()
        export_dir = filedialog.askdirectory(
            parent=self.root,
            title="Select Export Directory",
            initialdir=str(Path.home() / "Desktop"),
        )
        if not export_dir:
            return

        export_dir = os.path.join(export_dir, "DiscordStereoPatch_export")
        self._clear_log()
        self._set_buttons_state(False)

        def _do_export() -> None:
            try:
                self._log("=== Exporting Patched Binary ===", "header")
                self._log(f"  Source: {node_path}")
                self._log(f"  Export: {export_dir}")
                self._log("")
                result = export_patched_node(Path(node_path), Path(export_dir), GuiLog(self))
                self._log("")
                self._log("=== Export Complete ===", "header")
                self._log(f"  [OK] Files exported to: {result}")
                self._log("  Contents:")
                self._log("    discord_voice.node      - Patched binary")
                self._log("    original_backup/        - Original binary")
                self._log("    INSTALL_GUIDE.txt       - Installation guide")
                self.root.after(0, lambda: self.progress_label.configure(text="Export complete!"))

                def _open_finder() -> None:
                    try:
                        subprocess.Popen(["open", str(result)])
                    except Exception:
                        pass

                self.root.after(100, _open_finder)
            except Exception as e:
                self._log(f"\n  [FAIL] Error: {e}", "error")
            finally:
                self._set_buttons_state(True)

        threading.Thread(target=_do_export, daemon=True).start()

    def run(self) -> None:
        self.root.mainloop()


def run_gui() -> int:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        safe_mkdir(app_data_dir())
    except Exception:
        pass
    try:
        PatcherApp().run()
        return 0
    except Exception as e:
        sys.stderr.write(f"{APP_NAME} failed: {human_exc(e)}\n")
        return 1
# endregion GUI application


# region Program entry point
def _want_gui() -> bool:
    if len(sys.argv) < 2:
        return True
    arg = sys.argv[1]
    if arg in ("--gui", "-g", "/gui"):
        return True
    if arg.startswith("-"):
        if arg in ("--restore", "--patch-local", "--patch-local-only"):
            return False
        return True
    return False


def main() -> int:
    if _want_gui():
        return run_gui()
    return run_cli(sys.argv[1:])
# endregion Program entry point


if __name__ == "__main__":
    raise SystemExit(main())