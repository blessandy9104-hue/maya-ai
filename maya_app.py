import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext

import maya_service
import maya_suggestion_review
import maya_web_research
from maya_identity import cognitive_state, get_avatar_path, load_identity
from maya_identity.identity import load_engine_config
from maya_identity.embodiment import PresenceEngine
from maya_identity.embodiment.visual_command import build_visual_command
from maya_identity.renderer import ProceduralFace, TemporaryShapeRenderer
from maya_identity.wireframe import MayaWireframeFace
from maya_runtime import face_drive
from maya_state_signals import snapshot as state_snapshot
from maya_safety_monitor import emergency_stop, status as resource_status

ROOT = Path(__file__).resolve().parent
CHILD_ENV = dict(os.environ)
CHILD_ENV["PYTHONIOENCODING"] = "utf-8"
CHILD_ENV["MAYA_SEMANTIC_BRIDGE"] = "1"

C = {
    "bg": "#0a0e1a",
    "panel": "#101629",
    "panel2": "#161d33",
    "card": "#0d1322",
    "field": "#0b1020",
    "edge": "#25305a",
    "edge2": "#1b2340",
    "accent": "#6d7cff",
    "accent2": "#9a8cff",
    "accent_dim": "#4d5bb5",
    "ink": "#e7ebfa",
    "muted": "#8a93b8",
    "dim": "#5b6488",
    "ok": "#4ade80",
    "warn": "#fbbf24",
    "bad": "#ff5c7a",
    "cyan": "#38bdf8",
}
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_SB = ("Segoe UI Semibold", 9)
FONT_H1 = ("Segoe UI Semibold", 19)
FONT_H2 = ("Segoe UI Semibold", 12)
FONT_MONO = ("Consolas", 9)

WORLD_TYPES = ["fact", "historical_record", "observation", "report"]
CONFIDENCES = ["low", "medium", "high"]
RESEARCH_COMMANDS = (":research", ":world", ":income", ":evidence", ":focus", ":review")

# Bounded UI mailbox: content kinds (chat/log) keep the newest by retiring the
# oldest; every other kind is a refresh/superseded state that may be dropped at
# the door when full. Drops are counted so the UI can surface a rate-limited
# truncation banner instead of silently losing output.
_MAIL_CAP = 512
_MAIL_CONTENT_KINDS = frozenset(("chat", "log"))

# Runtime observability (Phase 4): one bounded summary per poll interval
# (never per interaction) is merged into maya_instrumentation's runtime
# aggregate. Off by default and a no-op when instrumentation is not enabled.
_OBS_POLL_INTERVAL = 5  # polls (60 ms each) between runtime summaries

_INSTRUMENTATION = {"ref": None, "loaded": False}


def _instrumentation():
    if not _INSTRUMENTATION["loaded"]:
        _INSTRUMENTATION["loaded"] = True
        try:
            import maya_instrumentation as _inst
            _INSTRUMENTATION["ref"] = _inst
        except Exception:  # noqa: BLE001 - never break the UI on a missing hook
            _INSTRUMENTATION["ref"] = None
    return _INSTRUMENTATION["ref"]


class Mailbox:
    """Bounded, non-blocking message box used by the Tk controller.

    Duck-types ``queue.Queue`` for the parts ``poll`` touches (``get_nowait``,
    ``qsize``) so the drain loop stays unchanged. ``put(kind, *payload)``
    applies the drop policy above and returns True when a message was dropped.
    """

    def __init__(self, maxsize=_MAIL_CAP):
        self.maxsize = int(maxsize)
        self.drops = 0
        self.q = queue.Queue(maxsize=self.maxsize)

    def put(self, kind, *payload):
        item = (kind,) + tuple(payload)
        if kind in _MAIL_CONTENT_KINDS:
            dropped = False
            try:
                self.q.put_nowait(item)
                return False
            except queue.Full:
                dropped = True
            try:
                self.q.get_nowait()
                self.drops += 1
            except queue.Empty:
                pass
            try:
                self.q.put_nowait(item)
                return dropped
            except queue.Full:
                self.drops += 1
                return True
        try:
            self.q.put_nowait(item)
            return False
        except queue.Full:
            self.drops += 1
            return True

    def get_nowait(self):
        return self.q.get_nowait()

    def qsize(self):
        return self.q.qsize()

    def __len__(self):
        return self.q.qsize()


class MayaApp:
    def __init__(self, r):
        self.r = r
        self.q = Mailbox()
        self._mail_drops = 0
        self._mail_overflow_at = 0.0
        self.chat_p = None
        self.stop = False
        self.resource_warning_sent = False
        self._activity = "idle"
        self._typing_settle_after = None
        self.pages = {}
        self.nav = {}
        self.log_widgets = {}
        self._identity = load_identity()
        self._faces = []
        self._shape_frame = 0
        self._latest_semantic = None
        self._latest_visual_identity = None
        self._chat_streaming_until = 0.0
        self._face_lab_speak_until = 0.0
        self.presence = PresenceEngine()
        # Phase 2: a single serialized compute worker owns payload building and
        # face projection. The UI thread only enqueues a detached input
        # snapshot (bounded, single slot) and later applies render-ready parts
        # via ``mail("tick_ready", ...)``; the expensive projection never runs
        # on the Tk UI thread.
        self._compute_q = queue.Queue(maxsize=1)
        self._compute_thread = threading.Thread(
            target=self._tick_compute_loop, name="maya-tick-compute",
            daemon=True)
        self._compute_thread.start()
        self._tick_ready_count = 0
        self._tick_skips = 0
        self._last_tick_skip_log = 0.0
        # Phase 3: every submitted tick carries a strictly increasing
        # generation. A tick_ready/tick_failed that lags the committed frame is
        # stale and is dropped, so an older frame can never overwrite a newer
        # committed one and stale work never claims completion.
        self._tick_gen = 0
        self._last_committed_gen = 0
        self._stale_skips = 0
        self._obs_polls = 0
        try:
            icon = get_avatar_path().get("icon")
            if icon:
                r.iconbitmap(str(icon))
        except Exception:
            pass
        r.title("Maya - Local Intelligence")
        r.configure(bg=C["bg"])
        r.geometry("1180x800")
        r.minsize(1020, 680)
        r.option_add("*Font", FONT)
        self._build_header()
        self._build_body()
        self._build_statusbar()
        r.bind_all("<Control-Alt-s>", lambda _e: self.goto("control"))
        r.bind_all("<Control-Alt-h>", lambda _e: self.goto("home"))
        r.bind_all("<Control-Alt-f>", lambda _e: self.goto("world"))
        r.bind_all("<Control-Alt-g>", lambda _e: self.goto("settings"))
        r.bind_all("<Control-Alt-t>", lambda _e: self.goto("thinking"))
        r.bind_all("<Control-q>", lambda _e: self.close())
        r.bind_all("<Control-Alt-Escape>", lambda _e: self.do_emergency())
        r.protocol("WM_DELETE_WINDOW", self.close)
        r.after(60, self.poll)
        r.after(2500, self.monitor_resources)
        r.after(2500, self.status_ticker)
        self.goto("home")
        self.mail("log", "control", f"[{time.strftime('%H:%M:%S')}] Control Centre ready. Actions run in isolated threads and log every result.\n", C["ok"])

    def mail(self, *payload):
        if self.q.put(*payload):
            self._mail_drops += 1
            self._mail_overflow()

    def _mail_overflow(self):
        now = time.time()
        if now - self._mail_overflow_at < 5.0:
            return
        self._mail_overflow_at = now
        self.q.put("log", "control",
                   "[mailbox] UI behind; output truncated (older lines skipped)\n",
                   C["warn"])

    def _build_header(self):
        bar = tk.Frame(self.r, bg=C["panel"])
        bar.pack(fill="x")
        inner = tk.Frame(bar, bg=C["panel"])
        inner.pack(fill="x", padx=18, pady=(12, 10))
        self.header_face = MayaWireframeFace(inner, size=48, state="sleeping", bg=C["panel"])
        self.header_face.pack(side="left")
        self._faces.append(self.header_face)
        titles = tk.Frame(inner, bg=C["panel"])
        titles.pack(side="left", padx=(12, 0))
        tk.Label(titles, text="MAYA", bg=C["panel"], fg=C["ink"], font=FONT_H1, anchor="w").pack(anchor="w")
        tk.Label(titles, text="SUPERVISED LOCAL INTELLIGENCE   ·   PRIVATE   ·   REVIEW-GATED", bg=C["panel"], fg=C["muted"], font=("Segoe UI", 8, "bold"), anchor="w").pack(anchor="w")
        chips = tk.Frame(inner, bg=C["panel"])
        chips.pack(side="right")
        self.chip_service = self._chip(chips, "Service", "…", C["muted"])
        self.chip_learning = self._chip(chips, "Learning", "…", C["muted"])
        self.chip_presence = self._chip(chips, "Presence", "…", C["muted"])
        self.chip_chat = self._chip(chips, "Chat", "offline", C["muted"])
        self._btn(chips, "EMERGENCY STOP", self.do_emergency, kind="bad", padx=14)
        glow = tk.Frame(bar, bg=C["accent_dim"], height=3)
        glow.pack(fill="x")

    def _chip(self, parent, label, value, color):
        chip = tk.Frame(parent, bg=C["panel2"], highlightbackground=C["edge"], highlightthickness=1)
        chip.pack(side="left", padx=6, pady=4)
        tk.Label(chip, text=label, bg=C["panel2"], fg=C["muted"], font=("Segoe UI", 8, "bold")).pack(side="left", padx=(8, 4), pady=4)
        text = tk.Label(chip, text=value, bg=C["panel2"], fg=color, font=FONT_B)
        text.pack(side="left", padx=(0, 8), pady=4)
        setattr(self, "_chip_val_" + label.lower(), text)
        return text

    def _build_statusbar(self):
        bar = tk.Frame(self.r, bg=C["panel2"])
        bar.pack(fill="x", side="bottom")
        tk.Label(bar, text="Service", bg=C["panel2"], fg=C["muted"], font=("Segoe UI", 8, "bold")).pack(side="left", padx=(14, 4), pady=4)
        self.sb_service = tk.Label(bar, text="offline", bg=C["panel2"], fg=C["muted"], font=("Segoe UI", 8))
        self.sb_service.pack(side="left", pady=4)
        tk.Label(bar, text="|  Resources", bg=C["panel2"], fg=C["muted"], font=("Segoe UI", 8)).pack(side="left", padx=(12, 4), pady=4)
        self.sb_res = tk.Label(bar, text="safe", bg=C["panel2"], fg=C["ok"], font=("Segoe UI", 8))
        self.sb_res.pack(side="left", pady=4)
        tk.Label(bar, text="|  All actions review-gated   ·   Emergency: Ctrl+Alt+Esc", bg=C["panel2"], fg=C["dim"], font=("Segoe UI", 8)).pack(side="right", padx=14, pady=4)

    def _build_body(self):
        body = tk.Frame(self.r, bg=C["bg"])
        body.pack(fill="both", expand=True)
        side = tk.Frame(body, bg=C["panel"], width=176)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        for key, label in (("home", "Home"), ("control", "Control Centre"), ("world", "World"), ("tasks", "Tasks"), ("thinking", "How Maya Thinks"), ("settings", "Settings")):
            self.nav[key] = self._btn(side, label, lambda k=key: self.goto(k), kind="nav", anchor="w", pady=8)
            self.nav[key].pack(fill="x", padx=8, pady=2)
        tk.Frame(side, bg=C["edge2"], height=1).pack(fill="x", padx=10, pady=8)
        tk.Label(side, text="Hotkeys", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x", padx=14)
        for text in ("Ctrl+Alt+S  Control Centre", "Ctrl+Alt+H  Home", "Ctrl+Alt+F  World", "Ctrl+Alt+G  Settings", "Ctrl+Alt+Esc  Emergency", "Ctrl+Q  Quit"):
            tk.Label(side, text=text, bg=C["panel"], fg=C["muted"], font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=14, pady=1)
        self._btn(side, "Quit", self.close, kind="ghost").pack(fill="x", padx=8, pady=(18, 8), side="bottom")
        self.content = tk.Frame(body, bg=C["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.pages = {
            "home": self._build_page_home(),
            "control": self._build_page_control(),
            "world": self._build_page_world(),
            "tasks": self._build_page_tasks(),
            "thinking": self._build_page_thinking(),
            "settings": self._build_page_settings(),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def goto(self, key):
        self.pages[key].tkraise()
        for nav_key, btn in self.nav.items():
            if nav_key == key:
                btn.configure(bg=C["accent"], fg="#0b0f1e", activebackground=C["accent2"], activeforeground="#0b0f1e")
            else:
                btn.configure(bg=C["panel"], fg=C["muted"], activebackground=C["accent_dim"], activeforeground="#ffffff")

    def _btn(self, parent, text, command, kind="ghost", width=None, anchor="center", padx=12, pady=7):
        palettes = {
            "accent": (C["accent"], "#0b0f1e", C["accent2"], "#0b0f1e"),
            "ok": (C["ok"], "#04130b", C["ok"], "#04130b"),
            "bad": (C["bad"], "#2a0611", C["bad"], "#2a0611"),
            "warn": (C["warn"], "#241a02", C["warn"], "#241a02"),
            "ghost": (C["panel2"], C["ink"], C["accent_dim"], "#ffffff"),
            "nav": (C["panel"], C["muted"], C["accent_dim"], "#ffffff"),
            "quiet": (C["field"], C["muted"], C["accent_dim"], "#ffffff"),
        }
        bg, fg, abg, afg = palettes.get(kind, palettes["ghost"])
        width_cfg = {"width": width} if width else {}
        return tk.Button(parent, text=text, command=command, relief="flat", bd=0, font=FONT_SB,
                         bg=bg, fg=fg, activebackground=abg, activeforeground=afg,
                         highlightthickness=0, cursor="hand2", padx=padx, pady=pady, anchor=anchor, **width_cfg)

    def _card(self, parent, title):
        card = tk.Frame(parent, bg=C["panel"], highlightbackground=C["edge"], highlightthickness=1)
        tk.Label(card, text=title, bg=C["panel"], fg=C["accent2"], font=FONT_SB, anchor="w").pack(fill="x", padx=14, pady=(10, 2))
        body = tk.Frame(card, bg=C["panel"])
        body.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        return body

    def _field_row(self, parent, label):
        row = tk.Frame(parent, bg=C["panel"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=C["panel"], fg=C["muted"], font=FONT_SB, width=14, anchor="w").pack(side="left")
        entry = tk.Entry(row, bg=C["field"], fg=C["ink"], insertbackground=C["cyan"], relief="flat",
                         highlightthickness=1, highlightbackground=C["edge"], highlightcolor=C["accent"])
        entry.pack(side="left", fill="x", expand=True)
        return entry

    def _output(self, parent):
        out = scrolledtext.ScrolledText(parent, wrap=tk.WORD, state="disabled", bg=C["card"], fg=C["ink"],
                                        font=FONT_MONO, relief="flat", highlightthickness=1,
                                        highlightbackground=C["edge"], highlightcolor=C["accent"], padx=12, pady=12)
        return out

    def _append_text(self, w, s, fg=None):
        if w is None:
            return
        w.configure(state="normal")
        if fg:
            tag = "f" + fg.replace("#", "")
            if tag not in w.tag_names():
                w.tag_configure(tag, foreground=fg)
            w.insert("end", s, tag)
        else:
            w.insert("end", s)
        w.see("end")
        w.configure(state="disabled")

    def _build_identity_panel(self, p):
        panel = tk.Frame(p, bg=C["card"], highlightbackground=C["edge"], highlightthickness=1)
        self.home_face = MayaWireframeFace(panel, size=176, state="sleeping", bg=C["card"])
        self.home_face.pack(side="left", padx=14, pady=10)
        self._faces.append(self.home_face)
        # Batch 8C: the temporary geometric embodiment is an additional visual
        # surface driven by the SAME tick state (VisualState) as the face. It
        # is not Maya's identity and is replaced later by a face renderer.
        self.temp_shape = TemporaryShapeRenderer(panel, size=132, state="sleeping", bg=C["card"])
        self.temp_shape.pack(side="left", padx=(0, 8), pady=10)
        self._faces.append(self.temp_shape)
        tk.Label(panel, text="temp embodiment · state-driven", bg=C["card"], fg=C["dim"],
                 font=("Segoe UI", 7), width=18).pack(side="left")
        right = tk.Frame(panel, bg=C["card"])
        right.pack(side="left", fill="both", expand=True, padx=(0, 14), pady=10)
        name_row = tk.Frame(right, bg=C["card"])
        name_row.pack(anchor="w")
        tk.Label(name_row, text=self._identity.get("canonical_name", "MAYA").upper(),
                 bg=C["card"], fg=C["ink"], font=FONT_H1).pack(side="left")
        ver = self._identity.get("identity_version", "")
        tk.Label(name_row, text=f"v{ver}", bg=C["panel2"], fg=C["accent2"], font=FONT_SB, padx=8, pady=2).pack(side="left", padx=8)
        if self.home_face.is_placeholder():
            tk.Label(name_row, text="PLACEHOLDER IDENTITY", bg="#3a1520", fg="#ff7f9b",
                     font=("Segoe UI Semibold", 8), padx=8, pady=2).pack(side="left", padx=8)
        tk.Label(right, text=self._identity.get("tagline", ""), bg=C["card"], fg=C["muted"],
                 font=("Segoe UI", 10, "italic"), anchor="w").pack(anchor="w", pady=(2, 6))
        tk.Label(right, text=self._identity.get("critical_identity_rule", ""), bg=C["card"], fg=C["dim"],
                 font=("Segoe UI", 8), anchor="w", wraplength=520, justify="left").pack(anchor="w")
        self.ident_state = tk.Label(right, text="presence · dormant", bg=C["card"], fg=C["muted"], font=FONT_SB)
        self.ident_state.pack(anchor="w", pady=(10, 0))
        foot = tk.Frame(panel, bg=C["card"])
        foot.pack(side="bottom", fill="x", padx=14, pady=(0, 8))
        tk.Label(foot, text=self.home_face.status_text(), bg=C["card"], fg=C["dim"], font=("Segoe UI", 8)).pack(side="left")
        return panel

    def _build_page_home(self):
        p = tk.Frame(self.content, bg=C["bg"])
        head = tk.Frame(p, bg=C["bg"])
        head.pack(fill="x", padx=20, pady=(14, 4))
        tk.Label(head, text="Conversation", bg=C["bg"], fg=C["ink"], font=FONT_H2).pack(side="left")
        tk.Label(head, text="Actions remain confirmation-controlled. Nothing activates without explicit approval.", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9)).pack(side="left", padx=12)
        self._build_identity_panel(p).pack(fill="x", padx=20, pady=(4, 6))
        self.chat_out = self._output(p)
        self.chat_out.pack(fill="both", expand=True, padx=20, pady=(6, 8))
        row = tk.Frame(p, bg=C["bg"])
        row.pack(fill="x", padx=20, pady=(0, 6))
        self.chat_in = tk.Entry(row, bg=C["field"], fg=C["ink"], insertbackground=C["cyan"], font=("Segoe UI", 12),
                                relief="flat", highlightthickness=1, highlightbackground=C["edge"], highlightcolor=C["accent"])
        self.chat_in.pack(side="left", fill="x", expand=True, ipady=6)
        self.chat_in.bind("<Return>", lambda _e: self.chat_send())
        self.chat_in.bind("<KeyRelease>", self._on_typing)
        self._btn(row, "Send", self.chat_send, kind="accent").pack(side="left", padx=(8, 0))
        quick = tk.Frame(p, bg=C["bg"])
        quick.pack(fill="x", padx=20, pady=(0, 12))
        for text in ("Hello Maya", "Goodnight Maya", ":status", "show me my interests", ":seed demo", ":world summary", ":help"):
            self._btn(quick, text, lambda v=text: self.chat_quick(v), kind="quiet", pady=4).pack(side="left", padx=4)
        self._append_text(self.chat_out, "Maya desktop ready. Local core at your service.\n")
        return p

    def _build_page_control(self):
        p = tk.Frame(self.content, bg=C["bg"])
        tk.Label(p, text="Control Centre", bg=C["bg"], fg=C["ink"], font=FONT_H2).pack(anchor="w", padx=20, pady=(14, 4))
        tk.Label(p, text="One-click supervised controls. Every action is executed, logged, and reported here.", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)
        cols = tk.Frame(p, bg=C["bg"])
        cols.pack(fill="both", expand=True, padx=20, pady=10)
        left = tk.Frame(cols, bg=C["bg"])
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(cols, bg=C["bg"], width=360)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        service = self._card(left, "SERVICE")
        btn_row = tk.Frame(service, bg=C["panel"])
        btn_row.pack(fill="x")
        self._btn(btn_row, "Wake", lambda: self.run_action("control", ":wake"), kind="ok").pack(side="left", padx=4)
        self._btn(btn_row, "Sleep", lambda: self.run_action("control", ":sleep")).pack(side="left", padx=4)
        self._btn(btn_row, "Status", lambda: self.run_action("control", ":status")).pack(side="left", padx=4)

        learning = self._card(left, "LEARNING")
        btn_row = tk.Frame(learning, bg=C["panel"])
        btn_row.pack(fill="x")
        self._btn(btn_row, "Activate", lambda: self.run_action("control", "activate learning"), kind="ok").pack(side="left", padx=4)
        self._btn(btn_row, "Pause", lambda: self.run_action("control", "pause learning")).pack(side="left", padx=4)
        self._btn(btn_row, "Status", lambda: self.run_action("control", "learning status")).pack(side="left", padx=4)

        presence = self._card(left, "PRESENCE MODE")
        btn_row = tk.Frame(presence, bg=C["panel"])
        btn_row.pack(fill="x")
        self._btn(btn_row, "Presence ON", lambda: self.run_presence("on"), kind="ok").pack(side="left", padx=4)
        self._btn(btn_row, "Presence OFF", lambda: self.run_presence("off")).pack(side="left", padx=4)
        self._btn(btn_row, "Presence STATUS", lambda: self.run_presence("status")).pack(side="left", padx=4)
        self._btn(btn_row, "RESET STOP", lambda: self.run_presence("reset-stop")).pack(side="left", padx=4)

        dash = self._card(left, "REVIEW DASHBOARDS")
        btn_row = tk.Frame(dash, bg=C["panel"])
        btn_row.pack(fill="x")
        self._btn(btn_row, "Focus", lambda: self.run_action("control", ":focus"), kind="ghost").pack(side="left", padx=4)
        self._btn(btn_row, "Approvals", lambda: self.run_action("control", ":review"), kind="ghost").pack(side="left", padx=4)
        self._btn(btn_row, "Research", lambda: self.run_action("control", ":research"), kind="ghost").pack(side="left", padx=4)
        self._btn(btn_row, "Evidence", lambda: self.run_action("control", ":evidence"), kind="ghost").pack(side="left", padx=4)
        self._btn(btn_row, "Income", lambda: self.run_action("control", ":income"), kind="ghost").pack(side="left", padx=4)

        safety = self._card(left, "SAFETY")
        btn_row = tk.Frame(safety, bg=C["panel"])
        btn_row.pack(fill="x")
        self._btn(btn_row, "EMERGENCY STOP", self.do_emergency, kind="bad").pack(side="left", padx=4, ipady=2)
        self._btn(btn_row, "Resource Status", lambda: self.run_action("control", ":status detail"), kind="ghost").pack(side="left", padx=4)

        live = self._card(right, "LIVE STATUS")
        self.live_text = tk.Label(live, text="reading state…", bg=C["panel"], fg=C["ink"], justify="left", font=("Consolas", 9), anchor="w")
        self.live_text.pack(fill="both", expand=True)
        self._btn(live, "Refresh Now", lambda: self.mail("tick", None), kind="accent").pack(fill="x", pady=(6, 0))

        tk.Label(p, text="ACTIVITY LOG", bg=C["bg"], fg=C["accent2"], font=FONT_SB).pack(anchor="w", padx=20)
        self.control_log = self._output(p)
        self.control_log.pack(fill="both", expand=True, padx=20, pady=(4, 12))
        self.log_widgets["control"] = self.control_log
        return p

    def _build_page_world(self):
        p = tk.Frame(self.content, bg=C["bg"])
        tk.Label(p, text="World Model", bg=C["bg"], fg=C["ink"], font=FONT_H2).pack(anchor="w", padx=20, pady=(14, 4))
        tk.Label(p, text="Provenance-first evidence store. Source, confidence, and retrieval time are always recorded.", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)

        overview = tk.Frame(p, bg=C["bg"])
        overview.pack(fill="x", padx=20, pady=8)
        self._btn(overview, "Summary", lambda: self.run_action("world", ":world summary"), kind="accent").pack(side="left", padx=4)
        self._btn(overview, "List Evidence", lambda: self.run_action("world", ":world list"), kind="ghost").pack(side="left", padx=4)
        self.cmp_entry = tk.Entry(overview, bg=C["field"], fg=C["ink"], insertbackground=C["cyan"], relief="flat",
                                  highlightthickness=1, highlightbackground=C["edge"], highlightcolor=C["accent"])
        self.cmp_entry.pack(side="left", fill="x", expand=True, padx=8, ipady=4)
        self.cmp_entry.bind("<Return>", lambda _e: self.world_compare())
        self._btn(overview, "Compare Topic", self.world_compare, kind="ghost").pack(side="left", padx=4)

        add = self._card(p, "ADD SOURCE-BACKED EVIDENCE")
        grid = tk.Frame(add, bg=C["panel"])
        grid.pack(fill="x")
        self.world_claim = self._field_row(grid, "Claim")
        self.world_source = self._field_row(grid, "Source")
        row2 = tk.Frame(grid, bg=C["panel"])
        row2.pack(fill="x", pady=3)
        tk.Label(row2, text="Confidence", bg=C["panel"], fg=C["muted"], font=FONT_SB, width=14, anchor="w").pack(side="left")
        self.world_conf = tk.StringVar(value="medium")
        tk.OptionMenu(row2, self.world_conf, *CONFIDENCES).pack(side="left", padx=4)
        tk.Label(row2, text="Type", bg=C["panel"], fg=C["muted"], font=FONT_SB, width=8, anchor="w").pack(side="left")
        self.world_type = tk.StringVar(value="fact")
        tk.OptionMenu(row2, self.world_type, *WORLD_TYPES).pack(side="left", padx=4)
        self._btn(grid, "Add Evidence", self.world_add, kind="ok").pack(side="left", padx=12)

        self.world_out = self._output(p)
        self.world_out.pack(fill="both", expand=True, padx=20, pady=(8, 12))
        self.log_widgets["world"] = self.world_out
        return p

    def _build_page_tasks(self):
        p = tk.Frame(self.content, bg=C["bg"])
        tk.Label(p, text="Tasks", bg=C["bg"], fg=C["ink"], font=FONT_H2).pack(anchor="w", padx=20, pady=(14, 4))
        tk.Label(p, text="Single source of truth: tasks.json. Changes are immediate and logged.", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)
        top = tk.Frame(p, bg=C["bg"])
        top.pack(fill="x", padx=20, pady=8)
        self._btn(top, "Refresh List", lambda: self.run_action("tasks", ":tasks"), kind="accent").pack(side="left", padx=4)
        self._btn(top, "Stats", lambda: self.run_action("tasks", ":task stats"), kind="ghost").pack(side="left", padx=4)
        self.add_entry = self._row_input(top, "Add:", "task add", "tasks")
        self.done_entry = self._row_input(top, "Done #:", "task done", "tasks")
        self.remove_entry = self._row_input(top, "Remove #:", "task remove", "tasks")
        self.tasks_out = self._output(p)
        self.tasks_out.pack(fill="both", expand=True, padx=20, pady=(4, 12))
        self.log_widgets["tasks"] = self.tasks_out
        return p

    def _build_page_thinking(self):
        p = tk.Frame(self.content, bg=C["bg"])
        tk.Label(p, text="How Maya Thinks", bg=C["bg"], fg=C["ink"], font=FONT_H2).pack(anchor="w", padx=20, pady=(14, 4))
        tk.Label(p, text="Real pattern-mapping output from local evidence, review only. Relative evidence fit, not a calibrated probability; Andy decides; Maya does not take external action.", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)
        presets = tk.Frame(p, bg=C["bg"])
        presets.pack(fill="x", padx=20, pady=10)
        for label, cmd in (
            ("AI workflow in Python", "I want to build automated Python workflows with local AI that save me time"),
            ("Research & evidence briefs", "I want to offer source-labelled research and writing briefs as a service"),
            ("Markets & data tools", "I want to build educational tools around markets and data analysis without trading"),
        ):
            self._btn(presets, label, lambda c=cmd, l=label: self.show_thinking(l, "patterns", c), kind="quiet").pack(side="left", padx=4)
        self._btn(presets, "Interests", lambda: self.show_thinking("Interests", "interests", ""), kind="ghost", padx=12).pack(side="left", padx=4)
        self._btn(presets, "Emerging Interests", lambda: self.show_thinking("Emerging Interests", "emerging", ""), kind="ghost", padx=12).pack(side="left", padx=4)
        self.thinking_out = self._output(p)
        self.thinking_out.pack(fill="both", expand=True, padx=20, pady=(6, 12))
        self.log_widgets["thinking"] = self.thinking_out
        self._append_text(self.thinking_out, "Press a preset above to see Maya's actual pattern mapping from local evidence.\n")
        return p

    def show_thinking(self, label, kind, text):
        def worker():
            try:
                if kind == "interests":
                    from maya_learning import interest_summary
                    out = interest_summary()
                elif kind == "emerging":
                    from maya_emerging_interests import emerging_interest_review
                    out = emerging_interest_review()
                else:
                    from maya_pattern_mapping import render_pattern_map
                    out = render_pattern_map(text)
            except Exception as exc:
                out = f"Pattern display error: {exc}"
            self.mail("log", "thinking", f"[{time.strftime('%H:%M:%S')}] map | {label}\n{out}\n\n", C["ink"])
        threading.Thread(target=worker, daemon=True).start()

    def _bind_scroll(self, parent, handler, exclude=(), seen=None):
        if seen is None:
            seen = set()
        for child in parent.winfo_children():
            if id(child) in seen:
                continue
            seen.add(id(child))
            if child.winfo_class() not in exclude:
                try:
                    child.bind("<MouseWheel>", handler)
                except Exception:
                    pass
                self._bind_scroll(child, handler, exclude, seen)

    def _settings_scroll(self, event):
        try:
            self.settings_canvas.yview_scroll(int(-event.delta / 120), "units")
        except Exception:
            pass

    def _build_page_settings(self):
        p = tk.Frame(self.content, bg=C["bg"])
        tk.Label(p, text="Settings", bg=C["bg"], fg=C["ink"], font=FONT_H2).pack(anchor="w", padx=20, pady=(14, 4))
        tk.Label(p, text="Exposes existing CLI/file controls — every action here is logged. Nothing in this panel invents new gating behavior.", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=20)

        canvas = tk.Canvas(p, bg=C["bg"], highlightthickness=0)
        self.settings_canvas = canvas
        scroll = tk.Scrollbar(p, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=C["bg"])
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(body_id, width=e.width))
        canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=8)
        scroll.pack(side="right", fill="y", padx=(0, 14), pady=8)

        cols = tk.Frame(body, bg=C["bg"])
        cols.pack(fill="both", expand=True, padx=6)
        left = tk.Frame(cols, bg=C["bg"])
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(cols, bg=C["bg"], width=430)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        # 1. Presence & Service
        service = self._card(left, "PRESENCE & SERVICE")
        row = tk.Frame(service, bg=C["panel"])
        row.pack(fill="x")
        tk.Label(row, text="Service", bg=C["panel"], fg=C["muted"], font=FONT_SB, width=14, anchor="w").pack(side="left")
        self.settings_service = tk.Label(row, text="…", bg=C["panel"], fg=C["muted"], font=FONT_B)
        self.settings_service.pack(side="left")
        btn_row = tk.Frame(service, bg=C["panel"])
        btn_row.pack(fill="x", pady=(4, 0))
        self._btn(btn_row, "Wake", self.settings_wake, kind="ok").pack(side="left", padx=4)
        self._btn(btn_row, "Sleep", self.settings_sleep).pack(side="left", padx=4)
        self._btn(btn_row, "Refresh State", lambda: self.mail("settings_refresh", None), kind="quiet").pack(side="left", padx=4)

        row = tk.Frame(service, bg=C["panel"])
        row.pack(fill="x", pady=(10, 0))
        tk.Label(row, text="Presence Mode", bg=C["panel"], fg=C["muted"], font=FONT_SB, width=14, anchor="w").pack(side="left")
        self.settings_presence = tk.Label(row, text="…", bg=C["panel"], fg=C["muted"], font=FONT_B)
        self.settings_presence.pack(side="left")
        btn_row = tk.Frame(service, bg=C["panel"])
        btn_row.pack(fill="x", pady=(4, 0))
        self._btn(btn_row, "ON", lambda: self.run_presence("on", page="settings"), kind="ok", padx=10).pack(side="left", padx=4)
        self._btn(btn_row, "OFF", lambda: self.run_presence("off", page="settings"), padx=10).pack(side="left", padx=4)

        # 2. Safety
        safety = self._card(left, "SAFETY")
        row = tk.Frame(safety, bg=C["panel"])
        row.pack(fill="x")
        tk.Label(row, text="Emergency Stop", bg=C["panel"], fg=C["muted"], font=FONT_SB, width=14, anchor="w").pack(side="left")
        self.settings_stop = tk.Label(row, text="…", bg=C["panel"], fg=C["muted"], font=FONT_B)
        self.settings_stop.pack(side="left")
        tk.Label(safety, text="Emergency stop blocks Presence Mode and the presence worker until cleared. It is never auto-cleared.", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8), wraplength=620, justify="left").pack(anchor="w", pady=(2, 2))
        self._btn(safety, "Clear Emergency Stop", self.settings_clear_stop, kind="warn").pack(anchor="w", pady=4)
        tk.Frame(safety, bg=C["edge2"], height=1).pack(fill="x", pady=8)
        row = tk.Frame(safety, bg=C["panel"])
        row.pack(fill="x")
        tk.Label(row, text="App Control", bg=C["panel"], fg=C["muted"], font=FONT_SB, width=14, anchor="w").pack(side="left")
        self.settings_owner = tk.Label(row, text="…", bg=C["panel"], fg=C["muted"], font=FONT_B)
        self.settings_owner.pack(side="left")
        tk.Label(safety, text="owner_control_enabled is a launch permission for allow-listed local apps. It is read-only here and disabled by default; enabling remains a deliberate manual policy-file edit, exactly as today.", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8), wraplength=620, justify="left").pack(anchor="w", pady=(2, 2))

        # 3. Research Cache
        cache = self._card(right, "RESEARCH CACHE")
        self.settings_cache = tk.Label(cache, text="…", bg=C["panel"], fg=C["ink"], justify="left", font=("Consolas", 9), anchor="w")
        self.settings_cache.pack(fill="x")
        row = tk.Frame(cache, bg=C["panel"])
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text="Entry cap", bg=C["panel"], fg=C["muted"], font=FONT_SB, width=14, anchor="w").pack(side="left")
        self.cache_cap_entry = tk.Entry(row, bg=C["field"], fg=C["ink"], insertbackground=C["cyan"], relief="flat", highlightthickness=1, highlightbackground=C["edge"], highlightcolor=C["accent"])
        self.cache_cap_entry.pack(side="left", fill="x", expand=True)
        row = tk.Frame(cache, bg=C["panel"])
        row.pack(fill="x")
        tk.Label(row, text="Staleness days", bg=C["panel"], fg=C["muted"], font=FONT_SB, width=14, anchor="w").pack(side="left")
        self.cache_ttl_entry = tk.Entry(row, bg=C["field"], fg=C["ink"], insertbackground=C["cyan"], relief="flat", highlightthickness=1, highlightbackground=C["edge"], highlightcolor=C["accent"])
        self.cache_ttl_entry.pack(side="left", fill="x", expand=True)
        btn_row = tk.Frame(cache, bg=C["panel"])
        btn_row.pack(fill="x", pady=(6, 0))
        self._btn(btn_row, "Apply Cache Config", self.settings_apply_cache, kind="accent").pack(side="left", padx=4)
        self._btn(btn_row, "Clear Cache", self.settings_clear_cache, kind="bad").pack(side="left", padx=4)

        # 4. Suggestion Review
        review = self._card(right, "SUGGESTION REVIEW")
        row = tk.Frame(review, bg=C["panel"])
        row.pack(fill="x")
        tk.Label(row, text="Pending suggestions", bg=C["panel"], fg=C["muted"], font=FONT_SB, anchor="w").pack(side="left")
        self.settings_pending = tk.Label(row, text="…", bg=C["panel"], fg=C["muted"], font=FONT_B)
        self.settings_pending.pack(side="left", padx=8)
        self._btn(row, "Refresh", lambda: self.mail("suggestion_list", None), kind="quiet", pady=2).pack(side="right")
        self.suggestion_frame = tk.Frame(review, bg=C["panel"])
        self.suggestion_frame.pack(fill="both", expand=True)

        # 5. Embodiment (Voice Sync)
        emb = self._card(right, "EMBODIMENT · VOICE SYNC")
        row = tk.Frame(emb, bg=C["panel"])
        row.pack(fill="x")
        tk.Label(row, text="Voice sync", bg=C["panel"], fg=C["muted"], font=FONT_SB, width=14, anchor="w").pack(side="left")
        self.settings_voice = tk.Label(row, text="…", bg=C["panel"], fg=C["muted"], font=FONT_B)
        self.settings_voice.pack(side="left")
        tk.Label(emb, text="Disabled by default; returns neutral deltas only (glow/neural/eye/symbol at 0.0, voice_linked off). Whatever its state, an off toggle always returns to that exact neutral baseline.", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 8), wraplength=400, justify="left").pack(anchor="w", pady=(2, 2))

        face_lab = self._build_face_lab(body)
        if face_lab is not None:
            face_lab.pack(fill="x", padx=8, pady=(0, 8))

        tk.Label(body, text="SETTINGS ACTIVITY LOG", bg=C["bg"], fg=C["accent2"], font=FONT_SB).pack(anchor="w", padx=8)
        self.settings_log = self._output(body)
        self.settings_log.pack(fill="both", expand=True, padx=8, pady=(4, 12))
        self.log_widgets["settings"] = self.settings_log
        self._bind_scroll(body, self._settings_scroll, exclude=("Text", "Entry"))
        self.mail("settings_refresh", None)
        self.mail("suggestion_list", None)
        return p

    def refresh_settings(self):
        def worker():
            try:
                pid = maya_service.running_pid()
                service = f"awake (pid {pid})" if pid else "asleep"
            except Exception:
                pid, service = None, "unknown"
            try:
                policy_path = ROOT / "maya_app_control_policy.json"
                policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.exists() else {}
                owner_enabled = bool(policy.get("owner_control_enabled"))
            except Exception:
                owner_enabled = None
            try:
                voice_enabled = bool(load_engine_config("voice").get("enabled"))
            except Exception:
                voice_enabled = None
            try:
                status = json.loads((ROOT / "presence_status.json").read_text(encoding="utf-8"))
                presence_mode = status.get("mode", "unknown")
            except Exception:
                presence_mode = "unknown"
            stop_active = (ROOT / "PRESENCE_STOP").exists()
            self.mail("set", "settings_service", service, C["ok"] if pid else C["muted"])
            self.mail("set", "settings_presence", presence_mode, C["warn"] if presence_mode == "on" else C["muted"])
            self.mail("set", "settings_stop", "ACTIVE" if stop_active else "clear", C["bad"] if stop_active else C["ok"])
            self.mail("set", "settings_owner", ("enabled" if owner_enabled else "disabled") if owner_enabled is not None else "read error", C["warn"] if owner_enabled else C["muted"])
            self.mail("set", "settings_voice", ("enabled" if voice_enabled else "disabled") if voice_enabled is not None else "read error", C["ok"] if voice_enabled else C["muted"])
            cache = self._cache_status()
            self.mail("set", "settings_cache", cache["text"], C["ink"])
            self.mail("settings_fields", maya_web_research.CACHE_MAX_ENTRIES, maya_web_research.CACHE_TTL_DAYS)
        threading.Thread(target=worker, daemon=True).start()

    def _cache_status(self):
        cap = maya_web_research.CACHE_MAX_ENTRIES
        ttl = maya_web_research.CACHE_TTL_DAYS
        path = maya_web_research.CACHE_FILE
        try:
            rows = len(maya_web_research._read_cache())
            size = path.stat().st_size if path.exists() else 0
        except Exception:
            rows, size = 0, 0
        cap_bytes = maya_web_research.CACHE_MAX_BYTES
        text = (f"rows: {rows}   file: {size} B   caps: {cap} entries / {cap_bytes // (1024 * 1024)} MB / {ttl} days staleness")
        return {"rows": rows, "size": size, "text": text}

    def settings_wake(self):
        def worker():
            try:
                maya_service.wake()
                pid = maya_service.running_pid()
                msg = f"Maya service awake; running_pid = {pid}"
            except Exception as exc:
                msg = f"wake error: {exc}"
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ wake service\n{msg}\n", C["ok"] if "awake" in msg else C["bad"])
            self.mail("settings_refresh", None)
        threading.Thread(target=worker, daemon=True).start()

    def settings_sleep(self):
        def worker():
            try:
                maya_service.sleep_service()
                msg = "Maya service asleep; running_pid = None"
            except Exception as exc:
                msg = f"sleep error: {exc}"
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ sleep service\n{msg}\n", C["ink"])
            self.mail("settings_refresh", None)
        threading.Thread(target=worker, daemon=True).start()

    def settings_clear_stop(self):
        stop_active = (ROOT / "PRESENCE_STOP").exists()
        if not stop_active:
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ clear emergency stop\nNo PRESENCE_STOP present; nothing to clear.\n", C["ink"])
            return
        confirm = messagebox.askyesno(
            "Clear Emergency Stop",
            "Emergency Stop is currently active (PRESENCE_STOP exists).\n\n"
            "Clearing it re-enables Presence Mode and the presence worker.\n"
            "This does NOT disable any safety monitoring, and observation stays off.\n\n"
            "Clear the emergency stop?",
            parent=self.r,
        )
        if not confirm:
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ clear emergency stop cancelled by user\n", C["warn"])
            return
        self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ clear emergency stop confirmed; calling presence.py reset-stop\n", C["warn"])
        self.run_presence("reset-stop", page="settings")

    def settings_apply_cache(self):
        def worker():
            raw_cap = self.cache_cap_entry.get().strip()
            raw_ttl = self.cache_ttl_entry.get().strip()
            try:
                cap = int(raw_cap)
                ttl = int(raw_ttl)
            except ValueError:
                self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ apply cache config rejected: entry cap and staleness days must be integers\n", C["bad"])
                return
            if cap < 1 or ttl < 1 or cap > 10000 or ttl > 3650:
                self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ apply cache config rejected: values out of range (cap 1-10000, days 1-3650)\n", C["bad"])
                return
            old_cap = maya_web_research.CACHE_MAX_ENTRIES
            old_ttl = maya_web_research.CACHE_TTL_DAYS
            maya_web_research.CACHE_MAX_ENTRIES = cap
            maya_web_research.CACHE_TTL_DAYS = ttl
            status = self._cache_status()
            self.mail("set", "settings_cache", status["text"], C["ink"])
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ apply cache config\nentries: {old_cap} -> {cap}   staleness: {old_ttl} -> {ttl} days\n{status['text']}\n", C["ink"])
        threading.Thread(target=worker, daemon=True).start()

    def settings_clear_cache(self):
        path = maya_web_research.CACHE_FILE
        try:
            rows = len(maya_web_research._read_cache())
            size = path.stat().st_size if path.exists() else 0
        except Exception:
            rows, size = 0, 0
        if not path.exists():
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ clear cache\nNo research cache file present; nothing to clear.\n", C["ink"])
            return
        confirm = messagebox.askyesno(
            "Clear Research Cache",
            f"The research cache currently holds {rows} rows ({size} bytes).\n\n"
            "Clearing it deletes the cache file. Cached results are unreviewed lookup shortcuts only;\n"
            "future lookups will simply re-fetch live. No trusted memory is affected.\n\n"
            "Clear the research cache?",
            parent=self.r,
        )
        if not confirm:
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ clear cache cancelled by user\n", C["warn"])
            return

        def worker():
            try:
                path.unlink(missing_ok=True)
                msg = f"research cache deleted: {rows} rows, {size} bytes were removed"
            except Exception as exc:
                msg = f"cache clear error: {exc}"
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ clear cache\n{msg}\n", C["warn"])
            self.mail("settings_refresh", None)
        threading.Thread(target=worker, daemon=True).start()

    def _rebuild_suggestions(self):
        for child in self.suggestion_frame.winfo_children():
            child.destroy()
        try:
            pending = maya_suggestion_review.pending_suggestions()
        except Exception as exc:
            pending = []
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ suggestion list read error: {exc}\n", C["bad"])
        self.settings_pending.configure(text=str(len(pending)))
        self._bind_scroll(self.suggestion_frame, self._settings_scroll, exclude=("Text", "Entry"))
        if not pending:
            tk.Label(self.suggestion_frame, text="No pending suggestions.", bg=C["panel"], fg=C["dim"], font=("Segoe UI", 9)).pack(anchor="w", pady=4)
            return
        for item in sorted(pending, key=lambda i: i.get("created_at", 0)):
            sid = item.get("suggestion_id", "?")
            goal = item.get("individual_goal") or item.get("goal") or item.get("label") or ""
            card = tk.Frame(self.suggestion_frame, bg=C["panel2"], highlightbackground=C["edge"], highlightthickness=1)
            card.pack(fill="x", pady=3)
            head = tk.Frame(card, bg=C["panel2"])
            head.pack(fill="x", padx=8, pady=(6, 0))
            tk.Label(head, text=sid, bg=C["panel2"], fg=C["accent2"], font=FONT_MONO).pack(side="left")
            btn_row = tk.Frame(card, bg=C["panel2"])
            btn_row.pack(side="right", padx=6, pady=4)
            self._btn(btn_row, "Approve", lambda s=sid: self.suggestion_review(s, "approve"), kind="ok", pady=3, padx=10).pack(side="left", padx=3)
            self._btn(btn_row, "Reject", lambda s=sid: self.suggestion_review(s, "reject"), kind="bad", pady=3, padx=10).pack(side="left", padx=3)
            tk.Label(card, text=str(goal)[:160], bg=C["panel2"], fg=C["ink"], font=("Segoe UI", 9), wraplength=340, justify="left").pack(anchor="w", padx=8, pady=(0, 6))

    def suggestion_review(self, suggestion_id, decision):
        def worker():
            try:
                result = maya_suggestion_review.review_suggestion(suggestion_id, decision)
                text = json.dumps(result, ensure_ascii=False)
                color = C["ok"] if result.get("status") == "approved_pending_sandbox_and_regression" else (C["bad"] if result.get("status") == "rejected_by_user" else C["ink"])
            except Exception as exc:
                text = f"review error: {exc}"
                color = C["bad"]
            self.mail("log", "settings", f"[{time.strftime('%H:%M:%S')}] ❯ suggestion {decision} {suggestion_id}\n{text}\n", color)
            self.mail("suggestion_list", None)
            self.mail("settings_refresh", None)
        threading.Thread(target=worker, daemon=True).start()

    def _row_input(self, parent, label, kind, page):
        row = tk.Frame(parent, bg=C["bg"])
        row.pack(side="left", padx=6)
        tk.Label(row, text=label, bg=C["bg"], fg=C["muted"], font=FONT_SB).pack(side="left")
        entry = tk.Entry(row, bg=C["field"], fg=C["ink"], insertbackground=C["cyan"], width=16, relief="flat",
                         highlightthickness=1, highlightbackground=C["edge"], highlightcolor=C["accent"])
        entry.pack(side="left", padx=4, ipady=3)
        entry.bind("<Return>", lambda _e, k=kind: self.task_op(k))
        return entry

    def task_op(self, kind):
        entry, value = {"task add": (self.add_entry, "task add "), "task done": (self.done_entry, "task done "), "task remove": (self.remove_entry, "task remove ")}[kind]
        text = value + entry.get().strip()
        entry.delete(0, "end")
        if text.strip() != value:
            self.run_action("tasks", text)

    def world_compare(self):
        topic = self.cmp_entry.get().strip()
        if topic:
            self.cmp_entry.delete(0, "end")
            self.run_action("world", ":world compare " + topic)
        else:
            self.run_action("world", ":world compare")

    def world_add(self):
        claim = self.world_claim.get().strip()
        source = self.world_source.get().strip()
        if not claim or not source:
            self.run_action("world", ":world add")
            return
        payload = f":world add | {claim} | {source} | {self.world_conf.get()} | {self.world_type.get()}"
        self.world_claim.delete(0, "end")
        self.world_source.delete(0, "end")
        self.run_action("world", payload)

    def run_command(self, cmd):
        import maya_chat
        result = maya_chat.maya_local_command(cmd)
        if result is None:
            return "No local command matched."
        return result

    def run_action(self, page, cmd):
        def worker():
            kind = "research" if cmd.lstrip().startswith(RESEARCH_COMMANDS) else "processing"
            self._cancel_typing_settle()
            self.mail("activity", kind)
            try:
                out = self.run_command(cmd)
            except Exception as exc:
                out = f"Command error: {exc}"
            color = C["bad"] if out.strip().startswith("Command error") else C["ink"]
            self.mail("log", page, f"[{time.strftime('%H:%M:%S')}] ❯ {cmd}\n{out}\n\n", color)
            self.mail("activity", "idle")
        threading.Thread(target=worker, daemon=True).start()

    def run_presence(self, action, page="control"):
        def worker():
            try:
                result = subprocess.run(
                    [sys.executable, str(ROOT / "presence.py"), action],
                    cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=12, env=CHILD_ENV,
                )
                out = (result.stdout + result.stderr).strip() or f"presence {action} completed"
            except Exception as exc:
                out = f"Presence controller error: {exc}"
            self.mail("log", page, f"[{time.strftime('%H:%M:%S')}] ❯ presence {action}\n{out}\n\n", C["ink"])
            self.mail("settings_refresh", None)
        threading.Thread(target=worker, daemon=True).start()

    def do_emergency(self):
        try:
            stop = emergency_stop("GUI emergency stop")
        except Exception as exc:
            stop = {"error": str(exc)}
        reason = stop.get("reason") if isinstance(stop, dict) else None
        err = stop.get("error") if isinstance(stop, dict) else None
        detail = f" (marker write error: {err})" if err else ""
        self.mail("log", "control", f"[{time.strftime('%H:%M:%S')}] ❯ EMERGENCY STOP\nEmergency stop triggered: {reason or 'manual emergency stop'}, at {time.strftime('%H:%M:%S')}{detail}\n", C["bad"])
        self.run_presence("stop")
        try:
            if self.chat_p and self.chat_p.poll() is None:
                self.chat_p.stdin.write("exit\n")
                self.chat_p.stdin.flush()
                self.chat_p.wait(2)
        except Exception:
            pass
        self.mail("tick", None)

    def _on_typing(self, _event=None):
        """User is typing: lift a resting face to listening (bounded by
        face_drive.typing_activity) and schedule the settle-back timer."""
        overlay = face_drive.typing_activity(self._activity)
        if overlay is not None and overlay != self._activity:
            self.mail("activity", overlay)
        self._schedule_typing_settle()

    def _schedule_typing_settle(self):
        if self._typing_settle_after is not None:
            try:
                self.r.after_cancel(self._typing_settle_after)
            except Exception:
                pass
        self._typing_settle_after = self.r.after(
            int(face_drive.TYPING_SETTLE_SECONDS * 1000), self._typing_settle)

    def _typing_settle(self):
        self._typing_settle_after = None
        self.mail("activity_settle", None)

    def chat_quick(self, v):
        self.chat_in.delete(0, "end")
        self.chat_in.insert(0, v)
        self.chat_send()

    def chat_send(self):
        v = self.chat_in.get().strip()
        self.chat_in.delete(0, "end")
        if not v:
            return
        self._cancel_typing_settle()
        self.mail("activity", "listening")
        self.start_chat()
        try:
            self.chat_p.stdin.write(v + "\n")
            self.chat_p.stdin.flush()
        except Exception as exc:
            self._append_text(self.chat_out, f"[chat pipeline error: {exc}]\n")
        self.mail("activity", "processing")

    def start_chat(self):
        if self.chat_p and self.chat_p.poll() is None:
            return
        self.chat_p = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "maya_chat.py")],
            env={**os.environ, "MAYA_FACE_LINES": "1"},
            cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", bufsize=1,
        )
        threading.Thread(target=self._read_chat, daemon=True).start()
        self.mail("chip", "Chat", "online", C["ok"])

    def _cancel_typing_settle(self):
        if self._typing_settle_after is not None:
            try:
                self.r.after_cancel(self._typing_settle_after)
            except Exception:
                pass
            self._typing_settle_after = None

    def _read_chat(self):
        first = True
        for line in self.chat_p.stdout:
            if first:
                self.mail("activity", "idle")
                self._cancel_typing_settle()
                first = False
            if "[face] " in line:
                from maya_runtime.face_drive import parse_face_line
                state = parse_face_line(line)
                if state is not None:
                    self.mail("activity", state)
                continue
            if line.startswith("[semantic] "):
                try:
                    from maya_identity.embodiment.semantic_interpretation import (
                        from_line)
                    cue = from_line(line)
                    if cue is not None:
                        self._latest_semantic = cue
                except Exception:
                    pass
                continue
            self._chat_streaming_until = time.time() + 2.0
            self.mail("chat", line)
        self.mail("chip", "Chat", "offline", C["muted"])

    def monitor_resources(self):
        if self.stop:
            return
        try:
            result = resource_status()
            available = result.get("monitor_available")
            if available and not result.get("safe"):
                if not self.resource_warning_sent:
                    self.resource_warning_sent = True
                    snap = result.get("snapshot", {})
                    reasons = ", ".join(result.get("reasons", [])) or "unsafe"
                    self._append_text(self.control_log, f"[resource] RESOURCE SAFETY STOP — {reasons} (CPU {snap.get('cpu_percent', 0):.1f}%, MEM {snap.get('memory_percent', 0):.1f}%) at {time.strftime('%H:%M:%S')}\n", C["bad"])
                    self.do_emergency()
            elif available:
                self.resource_warning_sent = False
        except Exception as exc:
            self._append_text(self.control_log, f"[resource] monitor unavailable: {exc}\n", C["warn"])
        self.r.after(2500, self.monitor_resources)

    def _make_tick_payload(self, activity=None):
        snap = state_snapshot(
            activity=activity or getattr(self, "_activity", "idle"))
        core = {
            "service": snap["presence"],
            "learning": snap["learning"],
            "presence": snap["raw"]["presence_mode"],
            "processing": snap["activity"] == "processing",
            "listening": snap["activity"] == "listening",
            "research": snap["activity"] == "research",
            "activity": snap["activity"],
            "conversation": snap["conversation"],
            "resources": snap["resources"],
        }
        signal = cognitive_state.apply(core)
        return {**snap, **signal}

    def _refresh_presence(self):
        self._submit_tick()

    def status_ticker(self):
        if self.stop:
            return
        self._submit_tick()
        self.r.after(3000, self.status_ticker)

    def _submit_tick(self, payload=None):
        """Schedule one serialized tick (payload build + projection compute).

        Runs entirely on the single compute worker; this UI-thread call only
        enqueues a detached input snapshot and never blocks. A full single-slot
        queue drops the redundant presentation frame - backpressure instead of
        a UI stall - while chat/approval data always flows on its own channel.
        """
        if self.stop:
            return
        self._tick_gen += 1
        job = (payload,
               getattr(self, "_activity", "idle"),
               self._latest_semantic,
               getattr(self, "_chat_streaming_until", 0.0),
               getattr(self, "_face_lab_speak_until", 0.0),
               self._face_runtime_state_enabled(),
               self._tick_gen)
        try:
            self._compute_q.put_nowait(job)
        except queue.Full:
            self._tick_skips += 1
            self._log_tick_skip()

    def _log_tick_skip(self):
        now = time.time()
        if now - self._last_tick_skip_log < 5.0:
            return
        self._last_tick_skip_log = now
        self.mail("log", "control",
                  "[async] tick projection queue full; a presentation frame "
                  "was skipped (no chat or approval data was lost)\n",
                  C["warn"])

    def _tick_compute_loop(self):
        while True:
            try:
                job = self._compute_q.get(timeout=0.1)
            except queue.Empty:
                if self.stop:
                    self._drain_compute()
                    return
                continue
            if job is None or self.stop:
                if job is None:
                    self._drain_compute()
                return
            payload, activity, semantic, streaming_until, lab_speak_until, \
                runtime_enabled, gen = job
            try:
                if payload is None:
                    payload = self._make_tick_payload(activity)
                parts = self._project_apply_tick(
                    payload, semantic, streaming_until, lab_speak_until,
                    runtime_enabled)
                self._tick_ready_count += 1
                self.mail("tick_ready", parts, gen)
            except Exception as exc:  # noqa: BLE001 - a projection never
                # kills the compute worker; surface it honestly fail-closed.
                self.mail("tick_failed", f"{type(exc).__name__}: {exc}", gen)

    def _drain_compute(self):
        try:
            while True:
                self._compute_q.get_nowait()
        except queue.Empty:
            pass

    def poll(self):
        if self.stop:
            return
        try:
            while True:
                kind, *rest = self.q.get_nowait()
                if kind == "chat":
                    self._append_text(self.chat_out, rest[0])
                elif kind == "log":
                    page, text = rest[0], rest[1]
                    fg = rest[2] if len(rest) > 2 else None
                    self._append_text(self.log_widgets.get(page), text, fg)
                elif kind == "chip":
                    label, value, color = rest
                    widget = getattr(self, "_chip_val_" + label.lower(), None)
                    if widget:
                        widget.configure(text=value, fg=color)
                elif kind == "tick":
                    payload = rest[0] if rest else None
                    if isinstance(payload, dict):
                        # Route a full payload through the serialized compute
                        # worker; never project on the UI thread.
                        self._submit_tick(payload=payload)
                    else:
                        # Manual/emergency reset: immediate trivial mutation.
                        self._apply_tick(None)
                elif kind == "tick_ready":
                    # The compute worker finished: widget mutation only. A stale
                    # ready (older than the committed frame) is dropped - it can
                    # never overwrite a newer committed view.
                    parts = rest[0] if rest else None
                    gen = rest[1] if len(rest) > 1 else None
                    if gen is not None and gen < self._last_committed_gen:
                        self._stale_skips += 1
                        continue
                    if gen is not None:
                        self._last_committed_gen = gen
                    self._apply_tick_parts(parts)
                elif kind == "tick_failed":
                    detail = rest[0] if rest else "unknown"
                    gen = rest[1] if len(rest) > 1 else None
                    if gen is not None and gen < self._last_committed_gen:
                        self._stale_skips += 1
                        continue
                    if gen is not None:
                        self._last_committed_gen = gen
                    self._append_text(
                        self.log_widgets.get("control"),
                        f"[async] tick projection failed; presentation reset "
                        f"({detail})\n", C["bad"])
                    self._apply_tick(None)
                elif kind == "activity":
                    value = rest[0] if rest else "idle"
                    self._activity = value if value in ("idle", "processing", "listening", "research") else "idle"
                    if value != "listening" or self._typing_settle_after is None:
                        self._cancel_typing_settle()
                    self._refresh_presence()
                elif kind == "activity_settle":
                    # Typing-inactivity settle, guarded at the single state
                    # owner: never degrades a working state that started
                    # while the user was typing.
                    if self._activity == "listening":
                        self._activity = "idle"
                        self._refresh_presence()
                elif kind == "settings_refresh":
                    self.refresh_settings()
                elif kind == "suggestion_list":
                    self._rebuild_suggestions()
                elif kind == "set":
                    widget = getattr(self, rest[0], None)
                    if widget is not None:
                        cfg = {"text": rest[1]}
                        if len(rest) > 2 and rest[2]:
                            cfg["fg"] = rest[2]
                        try:
                            widget.configure(**cfg)
                        except Exception:
                            pass
                elif kind == "settings_fields":
                    if self.cache_cap_entry is not None and self.cache_ttl_entry is not None:
                        self.cache_cap_entry.delete(0, "end")
                        self.cache_cap_entry.insert(0, str(rest[0]))
                        self.cache_ttl_entry.delete(0, "end")
                        self.cache_ttl_entry.insert(0, str(rest[1]))
        except queue.Empty:
            pass
        self._tick_runtime_observability()
        self.r.after(60, self.poll)

    def _tick_runtime_observability(self):
        # One bounded runtime summary per poll interval - never per
        # interaction - merged into the instrumentation aggregate. A no-op
        # unless instrumentation is enabled; never raises on the hot path.
        self._obs_polls += 1
        if self._obs_polls % _OBS_POLL_INTERVAL != 0:
            return
        inst = _instrumentation()
        if inst is None or not inst.is_enabled():
            return
        try:
            counts = {
                "mailbox": self.q.drops,
                "mail": self._mail_drops,
                "tick_skips": self._tick_skips,
                "stale_skips": self._stale_skips,
                "tick_ready": self._tick_ready_count,
                "compute_queue": self._compute_q.qsize(),
                "compute_alive": int(
                    self._compute_thread is not None
                    and self._compute_thread.is_alive()),
            }
            merged = inst.report_runtime_counts(
                counts, phase="poll",
                levels=("compute_queue", "compute_alive"))
        except Exception:  # noqa: BLE001
            return
        if merged is None:
            return
        try:
            inst.record("runtime_summary", stage="tk", phase="poll",
                        count=len(merged), meta={"source": "tk"})
        except Exception:  # noqa: BLE001
            pass

    def _derive_face_metadata(self, snapshot, commands=None, visual="sleeping",
                          streaming_until=0.0, lab_speak_until=0.0):
        meta = {
            "visual_state": visual or "sleeping",
            "emotion": str(snapshot.get("expression_signal") or "neutral"),
            "confidence": 0.55 if snapshot.get("resources") == "safe" else 0.20,
            "attention": 0.0,
            "thinking": 0.0,
            "breath": 0.40,
            "glow_intensity": 0.15,
            "scan_activity": 0.20,
        }
        if commands:
            for k in ("eye_focus", "neural_activity", "glow_intensity",
                       "particle_density", "breath", "gaze_x", "gaze_y"):
                if k in commands:
                    meta[k] = commands[k]
        if (float(streaming_until or 0.0) > time.time()
                or float(lab_speak_until or 0.0) > time.time()):
            meta["speaking"] = 0.72
            meta["voice_intensity"] = 0.45
        if snapshot.get("resources") != "safe":
            meta["preset"] = "error"
        return meta

    def _face_runtime_state_enabled(self):
        return os.environ.get("MAYA_LEGACY_FACE_ANIMATION", "0") != "1"

    def _runtime_face_state(self, visual, meta, commands):
        from maya_runtime.face_drive import runtime_face_state
        return runtime_face_state(visual=visual, meta=meta, commands=commands)

    def _apply_tick(self, snapshot):
        if snapshot is None:
            # Reset commits the latest submitted generation, so any in-flight
            # older tick_ready/tick_failed arriving later is stale and dropped.
            self._last_committed_gen = max(self._last_committed_gen,
                                           self._tick_gen)
            for label in ("service", "learning", "presence"):
                getattr(self, "_chip_val_" + label).configure(text="…", fg=C["muted"])
            return
        raw = snapshot.get("raw", {})
        service = raw.get("service", "unknown")
        learning = snapshot.get("learning", "off")
        presence_mode = raw.get("presence_mode", "off")
        svc_color = C["ok"] if service == "awake" else C["muted"]
        getattr(self, "_chip_val_service").configure(text=service, fg=svc_color)
        getattr(self, "_chip_val_learning").configure(text=learning, fg=C["ok"] if learning == "on" else C["muted"])
        getattr(self, "_chip_val_presence").configure(text=presence_mode, fg=C["warn"] if presence_mode != "off" else C["muted"])
        visual = snapshot.get("visual_state", "sleeping")
        commands = self.presence.tick(visual_state=visual, signals=raw)
        for face in self._faces:
            face.set_state(visual)
            if hasattr(face, "set_command"):
                face.set_command(commands)
        meta = self._derive_face_metadata(
            snapshot, commands, visual,
            getattr(self, "_chat_streaming_until", 0.0),
            getattr(self, "_face_lab_speak_until", 0.0))
        if self._face_runtime_state_enabled():
            runtime_fs = self._runtime_face_state(visual, meta, commands)
            from maya_identity.embodiment.visual_state import build_visual_state

            vs = build_visual_state(runtime_fs, meta, commands,
                                    semantic=self._latest_semantic)
            self._latest_visual_identity = build_visual_command(
                base_state=vs, meta=meta)
            self._shape_frame += 1
            for face in self._faces:
                if hasattr(face, "set_visual_state"):
                    try:
                        face.set_visual_state(vs, frame=self._shape_frame)
                    except Exception:
                        pass
                elif hasattr(face, "set_face_state"):
                    try:
                        face.set_face_state(runtime_fs)
                    except Exception:
                        face.clear_face_state()
        else:
            for face in self._faces:
                if hasattr(face, "clear_face_state"):
                    face.clear_face_state()
        for face in self._faces:
            if hasattr(face, "set_metadata"):
                face.set_metadata(meta)
        self._refresh_face_lab(meta)
        awake = visual in ("awake", "processing", "listening", "research")
        self.ident_state.configure(text=snapshot.get("visual_label", ""), fg=C["warn"] if awake else C["muted"])
        lines = []
        lines.append(f"presence    : {snapshot.get('presence', 'unknown')}")
        lines.append(f"activity    : {snapshot.get('activity', 'idle')}")
        lines.append(f"state       : {visual}")
        lines.append(f"learning    : {learning}")
        lines.append(f"conversation: {snapshot.get('conversation', 'idle')}")
        lines.append(f"expression  : {snapshot.get('expression_signal', 'calm')}")
        lines.append(f"resources   : {snapshot.get('resources', 'safe')}")
        self.live_text.configure(text="\n".join(lines))
        self.sb_service.configure(text=service, fg=svc_color)
        self.sb_res.configure(text=snapshot.get("resources", "safe"), fg=C["ok"] if snapshot.get("resources") == "safe" else C["warn"])

    def _project_apply_tick(self, snapshot, semantic=None, streaming_until=0.0,
                            lab_speak_until=0.0, runtime_enabled=True):
        """Project one tick snapshot into render-ready parts (compute only).

        Runs on the single serialized compute worker. Every live-UI value
        (activity, semantic cue, speaking windows, face-runtime flag) is
        detached at submit time, so this never reads widget or UI-thread state
        except through its arguments. Returns a ``parts`` dict consumed by
        :meth:`_apply_tick_parts`; ``None`` snapshots produce a neutral reset.
        """
        if snapshot is None:
            return {"reset": True, "snapshot": None}
        raw = snapshot.get("raw", {}) or {}
        service = str(raw.get("service") or "unknown")
        learning = str(snapshot.get("learning") or "off")
        presence_mode = str(raw.get("presence_mode") or "off")
        visual = str(snapshot.get("visual_state") or "sleeping")
        commands = self.presence.tick(visual_state=visual, signals=raw)
        meta = self._derive_face_metadata(
            snapshot, commands, visual, streaming_until, lab_speak_until)
        fs, vs, visual_command = None, None, None
        if runtime_enabled:
            fs = self._runtime_face_state(visual, meta, commands)
            from maya_identity.embodiment.visual_state import build_visual_state
            vs = build_visual_state(fs, meta, commands, semantic=semantic)
            visual_command = build_visual_command(base_state=vs, meta=meta)
        return {
            "reset": False,
            "snapshot": dict(snapshot),
            "service": service,
            "learning": learning,
            "presence_mode": presence_mode,
            "visual": visual,
            "svc_color": C["ok"] if service == "awake" else C["muted"],
            "learning_color": C["ok"] if learning == "on" else C["muted"],
            "presence_color": C["warn"] if presence_mode != "off" else C["muted"],
            "resources": str(snapshot.get("resources") or "safe"),
            "commands": commands,
            "meta": meta,
            "fs": fs,
            "vs": vs,
            "visual_command": visual_command,
        }

    def _apply_tick_parts(self, parts):
        """Apply render-ready tick parts: widget mutation ONLY (UI thread).

        The projection already ran on the compute worker; this method only
        touches widgets and the UI-owned shape frame.
        """
        if parts is None or parts.get("reset"):
            self._apply_tick(None)
            return
        getattr(self, "_chip_val_service").configure(
            text=parts["service"], fg=parts["svc_color"])
        getattr(self, "_chip_val_learning").configure(
            text=parts["learning"], fg=parts["learning_color"])
        getattr(self, "_chip_val_presence").configure(
            text=parts["presence_mode"], fg=parts["presence_color"])
        visual = parts["visual"]
        for face in self._faces:
            face.set_state(visual)
            if hasattr(face, "set_command"):
                face.set_command(parts["commands"])
        vs, fs = parts["vs"], parts["fs"]
        if vs is not None and fs is not None:
            self._latest_visual_identity = parts["visual_command"]
            self._shape_frame += 1
            for face in self._faces:
                if hasattr(face, "set_visual_state"):
                    try:
                        face.set_visual_state(vs, frame=self._shape_frame)
                    except Exception:
                        pass
                elif hasattr(face, "set_face_state"):
                    try:
                        face.set_face_state(fs)
                    except Exception:
                        face.clear_face_state()
        else:
            for face in self._faces:
                if hasattr(face, "clear_face_state"):
                    face.clear_face_state()
        for face in self._faces:
            if hasattr(face, "set_metadata"):
                face.set_metadata(parts["meta"])
        self._refresh_face_lab(parts["meta"])
        awake = visual in ("awake", "processing", "listening", "research")
        snapshot = parts["snapshot"] or {}
        self.ident_state.configure(
            text=snapshot.get("visual_label", ""),
            fg=C["warn"] if awake else C["muted"])
        self.live_text.configure(text="\n".join([
            f"presence    : {snapshot.get('presence', 'unknown')}",
            f"activity    : {snapshot.get('activity', 'idle')}",
            f"state       : {visual}",
            f"learning    : {parts['learning']}",
            f"conversation: {snapshot.get('conversation', 'idle')}",
            f"expression  : {snapshot.get('expression_signal', 'calm')}",
            f"resources   : {parts['resources']}",
        ]))
        self.sb_service.configure(text=parts["service"], fg=parts["svc_color"])
        self.sb_res.configure(
            text=parts["resources"],
            fg=C["ok"] if parts["resources"] == "safe" else C["warn"])

    def _for_each_face(self, fn):
        for face in self._faces:
            try:
                fn(face)
            except Exception:
                pass

    def _refresh_face_lab(self, meta=None):
        lab = getattr(self, "_face_lab_status", None)
        if lab is None:
            return
        try:
            snap = self.home_face.snapshot()
            ctrl = snap["controls"]
            meta = meta or {}
            text = (
                f"state {snap['state']:<10}  tick {snap['tick']:<6}  "
                f"emotion {str(meta.get('emotion', '-')):<10}  "
                f"speaking {ctrl.get('speaking', 0):.2f}  thinking {ctrl.get('thinking', 0):.2f}  "
                f"attention {ctrl.get('attention', 0):.2f}  uncertainty {ctrl.get('uncertainty', 0):.2f}  "
                f"verts {self.home_face.mesh.vertex_count()}  edges {len(self.home_face._draw_plan)}  "
                f"tick_ms {MayaWireframeFace.FRAME_MS}"
            )
            lab.configure(text=text)
        except Exception:
            pass

    def _build_face_lab(self, parent):
        if os.environ.get("MAYA_FACE_DEBUG") != "1":
            return None
        card = tk.Frame(parent, bg=C["panel"], highlightbackground=C["edge"], highlightthickness=1)
        tk.Label(card, text="MAYA FACE LAB — DEV (MAYAWIREFRAME)", bg=C["panel"], fg=C["accent2"],
                 font=FONT_SB, anchor="w").pack(fill="x", padx=14, pady=(10, 2))
        body = tk.Frame(card, bg=C["panel"])
        body.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        cols = tk.Frame(body, bg=C["panel"])
        cols.pack(fill="both", expand=True)

        left = tk.Frame(cols, bg=C["panel"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        presets = ["neutral", "idle", "listening", "thinking", "calm", "happy",
                   "concerned", "surprised", "uncertain", "speaking", "error"]
        grid = tk.Frame(left, bg=C["panel"])
        grid.pack(anchor="w", fill="x")
        for i, name in enumerate(presets):
            self._btn(grid, name.upper().replace("_", " "),
                      lambda n=name: self._for_each_face(lambda f, p=n: f.apply_preset(p)),
                      kind="quiet", padx=8, pady=3).grid(row=i // 3, column=i % 3, sticky="w", padx=3, pady=2)
        act = tk.Frame(left, bg=C["panel"])
        act.pack(anchor="w", pady=(8, 0))
        self._btn(act, "Blink", self._lab_blink, kind="quiet").pack(side="left", padx=3)
        self._btn(act, "Speak 2s", self._lab_speak, kind="quiet").pack(side="left", padx=3)
        self._btn(act, "Reset", lambda: self._for_each_face(
            lambda f: f.controller.controls.clear_targets()), kind="quiet").pack(side="left", padx=3)

        right = tk.Frame(cols, bg=C["panel"])
        right.pack(side="left", fill="both", expand=True)
        rows = tk.Frame(right, bg=C["panel"])
        rows.pack(fill="x")
        self._lab_slider(rows, "smile", "control", "smile")
        self._lab_slider(rows, "attention", "control", "attention")
        self._lab_slider(rows, "speaking", "control", "speaking")
        self._lab_slider(rows, "thinking", "control", "thinking")
        self._lab_slider(rows, "uncertainty", "control", "uncertainty")
        self._lab_slider(rows, "confidence", "control", "confidence")
        self._lab_slider(rows, "brightness", "material", "line_brightness")
        self._lab_slider(rows, "glow", "material", "glow_intensity")
        self._lab_slider(rows, "scan", "material", "scan_intensity")
        self._lab_slider(rows, "particles", "material", "particle_density")
        self._lab_slider(rows, "speed", "material", "animation_speed")
        toggles = tk.Frame(right, bg=C["panel"])
        toggles.pack(anchor="w", pady=(6, 0))
        rm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(toggles, text="Reduced motion", variable=rm_var,
                       bg=C["panel"], activebackground=C["panel"], fg=C["muted"],
                       selectcolor=C["panel"], font=FONT_SB,
                       command=lambda: self._for_each_face(
                           lambda f: f.set_reduced_motion(rm_var.get()))).pack(side="left", padx=3)

        self._face_lab_status = tk.Label(card, text="…", bg=C["panel"], fg=C["dim"],
                                         font=("Consolas", 8), anchor="w")
        self._face_lab_status.pack(fill="x", padx=14, pady=(0, 10))
        return card

    def _lab_slider(self, parent, text, kind, name):
        row = tk.Frame(parent, bg=C["panel"])
        row.pack(fill="x", pady=1)
        tk.Label(row, text=text, bg=C["panel"], fg=C["muted"], font=FONT_SB,
                 width=13, anchor="w").pack(side="left")
        var = tk.DoubleVar(value=0.0 if kind == "control" else 0.5)
        if kind == "material":
            var.set({"line_brightness": 0.72, "glow_intensity": 0.35,
                     "scan_intensity": 1.0, "particle_density": 0.5,
                     "animation_speed": 1.0}.get(name, 0.5))

        def on(v, knd=kind, nm=name):
            val = float(v) / 100.0
            if knd == "control":
                self._for_each_face(lambda f: f.set_control(nm, val))
            else:
                self._for_each_face(lambda f: f.set_material(nm, val))

        tk.Scale(row, from_=0, to=100, orient="horizontal", variable=var,
                 bg=C["panel"], fg=C["ink"], highlightthickness=0, showvalue=False,
                 length=150, command=on, bd=0).pack(side="left")

    def _lab_blink(self):
        self._for_each_face(lambda f: f.set_control("blink", 1.0))
        self.r.after(1400, lambda: self._for_each_face(lambda f: f.set_control("blink", 0.0)))

    def _lab_speak(self):
        self._face_lab_speak_until = time.time() + 2.0

    def close(self):
        self.stop = True
        try:
            if self.chat_p and self.chat_p.poll() is None:
                self.chat_p.stdin.write("exit\n")
                self.chat_p.stdin.flush()
                self.chat_p.wait(3)
        except Exception:
            pass
        try:
            # Deterministic compute-worker stop: wake and drain the single
            # serialized tick slot so no projection lands after the window is
            # destroyed.
            try:
                self._compute_q.put_nowait(None)
            except queue.Full:
                pass
            self._compute_thread.join(timeout=2.0)
        except Exception:
            pass
        try:
            self.r.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    # Batch 8E: Qt-first launch (PySide6/Qt Quick), Tk fallback intact.
    from maya_runtime.ui.qt import QT_AVAILABLE, QT_DISABLED
    if QT_AVAILABLE and not QT_DISABLED:
        from maya_runtime.ui.qt import launch as qt_launch
        try:
            qt_launch()
            raise SystemExit(0)
        except SystemExit:
            raise
        except Exception as exc:
            print(f"[qt interface unavailable ({exc}); falling back to Tk]")
    root = tk.Tk()
    MayaApp(root)
    root.mainloop()