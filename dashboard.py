#!/usr/bin/env python3
"""Flet Dashboard — modern compact GUI for system monitoring in portrait orientation."""

import logging
import threading
import time
import platform
import base64
from datetime import datetime

import flet as ft
import psutil

from data_collector import DataCollector, Snapshot, CFG
from charts import cpu_chart, ram_chart, gpu_chart, net_chart, total_power_chart
from ai_detector import format_memory

# ── Design Tokens & Theming ─────────────────────────────────────────────
BG_APP            = "#07050f"  # Dark Space deep void canvas
BG_CARD           = "#110b1f"  # Primary card surface
BG_SUB            = "#0a0814"  # Inset expandable sub-surface
BG_INPUT          = "#100b1a"  # Dropdown & chart container background
BG_BAR            = "#1a122e"  # Progress bar track
BG_BTN_DEFAULT    = "#120e24"  # Segmented button idle state
BG_BTN_SELECTED   = "#22173b"  # Segmented button active state

BORDER_SUBTLE     = "#22173b"  # Default subtle card/divider border
BORDER_STATUS_LIVE= "#164e2b"  # Live badge border
BG_STATUS_LIVE    = "#0a2215"  # Live badge background

TEXT_PRIMARY      = "#e6edf3"  # Off-white primary text (>15:1 contrast)
TEXT_SECONDARY    = "#9ea7b3"  # High-contrast secondary text (>6.5:1, WCAG AA compliant)
TEXT_MUTED        = "#7d8590"  # Subtle timestamps / metadata

# Telemetry accents
ACCENT_CYAN       = "#00d4ff"  # Neon Cyan
ACCENT_GREEN      = "#00f5a0"  # Neon Emerald Green
ACCENT_ORANGE     = "#ff8a00"  # Neon Orange
ACCENT_MAGENTA    = "#f857a6"  # Neon Magenta
ACCENT_VIOLET     = "#b388ff"  # Neon Purple
ACCENT_RED        = "#ff5252"  # Alert / Danger Red
ACCENT_WARN       = "#ffab40"  # Warning Amber

# Backward-compat aliases
ACCENT  = ACCENT_CYAN
GREEN   = ACCENT_GREEN
ORANGE  = ACCENT_ORANGE
MAGENTA = ACCENT_MAGENTA
VIOLET  = ACCENT_VIOLET
CYAN    = "#18ffff"
WHITE   = TEXT_PRIMARY
DIM     = TEXT_SECONDARY
BG      = BG_APP
CARD_BG = BG_CARD


def alpha_hex(color_hex: str, alpha_hex_code: str = "15") -> str:
    """Safely append hex alpha channel to hex colors."""
    cleaned = color_hex.strip()
    return f"{cleaned[:7]}{alpha_hex_code}" if cleaned.startswith("#") else color_hex


def pct_color(v: float, warn: float = 80, danger: float = 90) -> str:
    if v >= danger: return ACCENT_RED
    if v >= warn:   return ACCENT_WARN
    return ACCENT_GREEN


def temp_color(v: int) -> str:
    th = CFG.get("thresholds", {})
    danger = th.get("gpu_temp_danger", 85)
    warn = th.get("gpu_temp_warn", 75)
    if v >= danger: return ACCENT_RED
    if v >= warn: return ACCENT_WARN
    return ACCENT_GREEN


class Dashboard:
    def __init__(self, page: ft.Page):
        self.page = page
        self.collector = DataCollector()
        self._running = True
        self.active_chart = "cpu"
        self.active_window = "2m"  # 1m, 2m, 5m, all
        self.selected_gpu = "all"  # "all" or a GPU index string (multi-GPU charts)
        self.gpu_names: list[str] = []
        self._gpu_options_cache: list[str] = []

        # Expanded state trackers
        self.cores_expanded = False
        self.gpu_procs_expanded = False

        # Widget refs
        self.cpu_avg_text = ft.Ref[ft.Text]()
        self.cpu_freq_text = ft.Ref[ft.Text]()
        self.cpu_bars_col = ft.Ref[ft.Column]()
        self.ram_bar = ft.Ref[ft.ProgressBar]()
        self.swap_text = ft.Ref[ft.Text]()
        self.gpu_col = ft.Ref[ft.Column]()
        self.ai_col = ft.Ref[ft.Column]()
        self.disk_col = ft.Ref[ft.Column]()
        self.net_up_text = ft.Ref[ft.Text]()
        self.net_down_text = ft.Ref[ft.Text]()
        self.chart_img = ft.Ref[ft.Image]()
        self.status_text = ft.Ref[ft.Text]()
        self.uptime_text = ft.Ref[ft.Text]()
        self.time_text = ft.Ref[ft.Text]()
        self.ram_val_text = ft.Ref[ft.Text]()
        self.ram_pct_badge = ft.Ref[ft.Container]()
        self.ram_pct_text = ft.Ref[ft.Text]()
        self.cpu_pct_badge = ft.Ref[ft.Container]()
        self.cpu_pct_text = ft.Ref[ft.Text]()
        self.cpu_power_text = ft.Ref[ft.Text]()
        self.cpu_power_badge = ft.Ref[ft.Container]()
        self.total_power_text = ft.Ref[ft.Text]()

    def build(self):
        # Configure fonts and default styles
        self.page.fonts = {
            "Outfit": "https://fonts.gstatic.com/s/outfit/v11/q35yFy1g9eR16dRCgN7X.woff2"
        }
        self.page.theme = ft.Theme(font_family="Outfit")
        
        self.page.title = "⚡ System Panel"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = BG_APP
        self.page.padding = 12
        self.page.scroll = ft.ScrollMode.AUTO
        
        # Sized for portrait sidebar layout matching current display
        self.page.window.width = 560
        self.page.window.height = 1320
        self.page.window.min_width = 480
        self.page.window.min_height = 800

        # ── Header ──
        hostname = platform.node()
        glow_line = ft.Container(
            height=3,
            gradient=ft.LinearGradient(
                colors=[ACCENT, MAGENTA, ORANGE],
                begin=ft.alignment.Alignment(-1, 0),
                end=ft.alignment.Alignment(1, 0),
            ),
            border_radius=1.5,
            margin=ft.margin.Margin(0, 0, 0, 4)
        )

        status_badge = ft.Container(
            content=ft.Row([
                ft.Container(
                    width=6,
                    height=6,
                    bgcolor=ACCENT_GREEN,
                    border_radius=3,
                ),
                ft.Text("LIVE", color=ACCENT_GREEN, size=9, weight="bold"),
            ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=BG_STATUS_LIVE,
            border=ft.Border.all(1, BORDER_STATUS_LIVE),
            padding=ft.padding.Padding(6, 2, 6, 2),
            border_radius=6,
            tooltip="Live background collector active (1000ms)"
        )

        from config import __version__, __author__, __repo__
        header = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Row([
                        ft.Text("⚡ AI System Panel", size=17, weight="bold", color=ACCENT_CYAN),
                    ]),
                    ft.Text(f"🖥  {hostname}  •  {platform.system()}", color=TEXT_SECONDARY, size=10),
                    ft.Text(f"v{__version__}  ·  (c) {__author__} 2026  ·  {__repo__}", color=TEXT_MUTED, size=11),
                ], spacing=1),
                ft.Column([
                    ft.Row([
                        status_badge,
                        ft.Text("", ref=self.time_text, color=TEXT_PRIMARY, size=11, weight="bold"),
                    ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Text("", ref=self.uptime_text, color=TEXT_SECONDARY, size=10, text_align=ft.TextAlign.RIGHT),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.END),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.Padding(left=2, top=0, right=2, bottom=4),
        )

        # ── Disk & Net row (Side-by-Side to save vertical space) ──
        disk_net_row = ft.Row([
            self._disk_panel(),
            self._network_panel(),
        ], spacing=10)

        # ── Chart Selector ──
        chart_selector = ft.SegmentedButton(
            segments=[
                ft.Segment(value="cpu", label=ft.Text("CPU", size=10, weight="bold")),
                ft.Segment(value="ram", label=ft.Text("RAM", size=10, weight="bold")),
                ft.Segment(value="gpu", label=ft.Text("GPU", size=10, weight="bold")),
                ft.Segment(value="net", label=ft.Text("Network", size=10, weight="bold")),
                ft.Segment(value="power", label=ft.Text("Power", size=10, weight="bold")),
            ],
            selected=["cpu"],
            on_change=self._chart_changed,
            show_selected_icon=False,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                color=TEXT_PRIMARY,
                bgcolor={
                    ft.ControlState.SELECTED: BG_BTN_SELECTED,
                    ft.ControlState.DEFAULT: BG_BTN_DEFAULT,
                },
                overlay_color=alpha_hex(ACCENT_CYAN, "20"),
            ),
        )

        window_selector = ft.SegmentedButton(
            segments=[
                ft.Segment(value="1m", label=ft.Text("1m", size=10, weight="bold")),
                ft.Segment(value="2m", label=ft.Text("2m", size=10, weight="bold")),
                ft.Segment(value="5m", label=ft.Text("5m", size=10, weight="bold")),
                ft.Segment(value="all", label=ft.Text("All", size=10, weight="bold")),
            ],
            selected=["2m"],
            on_change=self._window_changed,
            show_selected_icon=False,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                color=TEXT_PRIMARY,
                bgcolor={
                    ft.ControlState.SELECTED: BG_BTN_SELECTED,
                    ft.ControlState.DEFAULT: BG_BTN_DEFAULT,
                },
                overlay_color=alpha_hex(ACCENT_CYAN, "20"),
            ),
        )

        # ── GPU selector (shown only when the GPU chart is active) ──
        self.gpu_dropdown = ft.Dropdown(
            label="GPU",
            value="all",
            options=[ft.dropdown.Option("all", "All GPUs")],
            on_select=self._gpu_changed,
            width=180,
            text_style=ft.TextStyle(color=TEXT_PRIMARY, size=11),
            label_style=ft.TextStyle(color=TEXT_SECONDARY, size=9),
            border_color=BORDER_SUBTLE,
            bgcolor=BG_INPUT,
        )
        self.gpu_selector_row = ft.Container(
            content=ft.Row([
                ft.Text("GPU:", color=TEXT_PRIMARY, size=11, weight="bold"),
                self.gpu_dropdown,
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            visible=False,
            padding=ft.Padding(top=4, bottom=2),
        )

        chart_header_row = ft.Row([
            ft.Row([
                ft.Icon(ft.icons.Icons.TIMELINE, color=ACCENT_VIOLET, size=16),
                ft.Text("History", size=12, weight="bold", color=TEXT_PRIMARY),
                ft.Container(
                    content=ft.Text("", ref=self.total_power_text, size=10, weight="bold", color=ACCENT_VIOLET),
                    bgcolor=alpha_hex(ACCENT_VIOLET, "15"),
                    border=ft.Border.all(1, alpha_hex(ACCENT_VIOLET, "40")),
                    padding=ft.padding.Padding(6, 2, 6, 2),
                    border_radius=6,
                    tooltip="Combined CPU + GPU estimated real-time power"
                ),
            ], spacing=6),
            chart_selector
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        _BLANK_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        chart_card = ft.Container(
            content=ft.Image(
                src=f"data:image/png;base64,{_BLANK_PNG}",
                ref=self.chart_img,
                height=260,
                fit=ft.BoxFit.CONTAIN,
                border_radius=8,
                tooltip="Rolling telemetry trend chart"
            ),
            bgcolor=BG_INPUT,
            border_radius=12,
            padding=6,
            border=ft.Border.all(1, BORDER_SUBTLE),
            alignment=ft.alignment.Alignment(0, 0),
        )

        self.page.add(
            ft.Column([
                glow_line,
                header,
                self._cpu_panel(),
                self._ram_panel(),
                self._gpu_panel(),
                self._ai_panel(),
                disk_net_row,
                ft.Divider(height=6, color=BORDER_SUBTLE),
                chart_header_row,
                self.gpu_selector_row,
                chart_card,
                ft.Row([window_selector], alignment=ft.MainAxisAlignment.CENTER),
            ], expand=False, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        )

        # Start background thread
        self._start_collector()

    # ── Card Builder ─────────────────────────────────────────────

    def _card(self, title: str, icon: str, content: ft.Control, color: str, action_btn: ft.Control = None) -> ft.Container:
        header_row = ft.Row([
            ft.Row([
                ft.Container(
                    width=3,
                    height=14,
                    bgcolor=color,
                    border_radius=1.5,
                ),
                ft.Text(icon, size=14),
                ft.Text(title, size=12, weight="bold", color=TEXT_PRIMARY),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        
        if action_btn:
            header_row.controls.append(action_btn)
            
        def on_hover(e):
            is_hover = e.data == "true"
            border_col = color if is_hover else BORDER_SUBTLE
            e.control.border = ft.Border.all(1, border_col)
            e.control.shadow = ft.BoxShadow(
                blur_radius=12,
                color=alpha_hex(color, "20") if is_hover else "#00000040",
                spread_radius=1 if is_hover else 0
            )
            e.control.update()

        return ft.Container(
            content=ft.Column([
                header_row,
                ft.Divider(height=1, color=BORDER_SUBTLE),
                content,
            ], spacing=6),
            bgcolor=BG_CARD,
            border_radius=14,
            padding=12,
            border=ft.Border.all(1, BORDER_SUBTLE),
            shadow=ft.BoxShadow(blur_radius=8, color="#00000030", spread_radius=1),
            on_hover=on_hover,
            expand=True,
        )

    # ── Panels ──────────────────────────────────────────────────

    def _cpu_panel(self):
        self.cpu_cores_list = ft.Column(ref=self.cpu_bars_col, spacing=2, scroll=ft.ScrollMode.AUTO, height=150)
        self.cpu_cores_container = ft.Container(
            content=self.cpu_cores_list,
            visible=False,
            padding=ft.Padding(left=6, top=4, right=6, bottom=4),
            border_radius=8,
            bgcolor=BG_SUB
        )
        
        self.cores_btn = ft.IconButton(
            icon=ft.icons.Icons.KEYBOARD_ARROW_DOWN,
            icon_color=ACCENT_GREEN,
            icon_size=16,
            width=36,
            height=36,
            style=ft.ButtonStyle(padding=0),
            on_click=self._toggle_cores,
            tooltip="Toggle CPU Cores detail",
        )
        
        pct_badge = ft.Container(
            ref=self.cpu_pct_badge,
            content=ft.Text("0%", ref=self.cpu_pct_text, size=10, weight="bold", color=ACCENT_GREEN),
            bgcolor=alpha_hex(ACCENT_GREEN, "15"),
            border=ft.Border.all(1, alpha_hex(ACCENT_GREEN, "40")),
            padding=ft.padding.Padding(6, 2, 6, 2),
            border_radius=6,
            tooltip="Average CPU Utilization across all cores"
        )

        panel_content = ft.Column([
            ft.Row([
                ft.Row([
                    ft.Text("CPU Load:", color=TEXT_SECONDARY, size=11),
                    ft.Text("0%", ref=self.cpu_avg_text, size=12, weight="bold", color=TEXT_PRIMARY),
                ], spacing=4),
                pct_badge
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([
                ft.Text("Frequency:", color=TEXT_SECONDARY, size=10),
                ft.Text("", ref=self.cpu_freq_text, color=TEXT_PRIMARY, size=11, weight="bold", text_align=ft.TextAlign.RIGHT),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([
                ft.Row([
                    ft.Icon(ft.icons.Icons.BOLT, color=ACCENT_ORANGE, size=12),
                    ft.Text("CPU Power:", color=TEXT_SECONDARY, size=10),
                ], spacing=3),
                ft.Container(
                    ref=self.cpu_power_badge,
                    content=ft.Text("0 W", ref=self.cpu_power_text, size=10, weight="bold", color=ACCENT_ORANGE),
                    bgcolor=alpha_hex(ACCENT_ORANGE, "15"),
                    border=ft.Border.all(1, alpha_hex(ACCENT_ORANGE, "40")),
                    padding=ft.padding.Padding(6, 2, 6, 2),
                    border_radius=6,
                    tooltip="CPU package / estimated power consumption"
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.cpu_cores_container
        ], spacing=6)
        
        return self._card("Processor", "🧠", panel_content, ACCENT_GREEN, action_btn=self.cores_btn)

    def _ram_panel(self):
        pct_badge = ft.Container(
            ref=self.ram_pct_badge,
            content=ft.Text("0%", ref=self.ram_pct_text, size=10, weight="bold", color=ACCENT_MAGENTA),
            bgcolor=alpha_hex(ACCENT_MAGENTA, "15"),
            border=ft.Border.all(1, alpha_hex(ACCENT_MAGENTA, "40")),
            padding=ft.padding.Padding(6, 2, 6, 2),
            border_radius=6,
            tooltip="RAM percentage consumed"
        )

        panel_content = ft.Column([
            ft.Row([
                ft.Row([
                    ft.Text("Memory:", color=TEXT_SECONDARY, size=11),
                    ft.Text("0 / 0 GB", ref=self.ram_val_text, color=TEXT_PRIMARY, size=12, weight="bold"),
                ], spacing=4),
                pct_badge
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.ProgressBar(ref=self.ram_bar, value=0, bgcolor=BG_BAR,
                           color=ACCENT_MAGENTA, height=6, border_radius=3),
            ft.Text("", ref=self.swap_text, color=TEXT_SECONDARY, size=10),
        ], spacing=6)
        
        return self._card("System Memory", "💾", panel_content, ACCENT_MAGENTA)

    def _gpu_panel(self):
        self.gpu_procs_list = ft.Column(spacing=2)
        self.gpu_procs_container = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Process", size=10, color=TEXT_SECONDARY, weight="bold", expand=True),
                    ft.Text("PID", size=10, color=TEXT_SECONDARY, weight="bold", width=50, text_align=ft.TextAlign.RIGHT),
                    ft.Text("VRAM", size=10, color=TEXT_SECONDARY, weight="bold", width=70, text_align=ft.TextAlign.RIGHT),
                ], spacing=6),
                ft.Divider(height=1, color=BORDER_SUBTLE),
                self.gpu_procs_list
            ], spacing=4),
            visible=False,
            padding=ft.Padding(left=6, top=4, right=6, bottom=4),
            border_radius=8,
            bgcolor=BG_SUB
        )
        
        self.gpu_procs_btn = ft.IconButton(
            icon=ft.icons.Icons.KEYBOARD_ARROW_DOWN,
            icon_color=ACCENT_CYAN,
            icon_size=16,
            width=36,
            height=36,
            style=ft.ButtonStyle(padding=0),
            on_click=self._toggle_gpu_procs,
            tooltip="Toggle active GPU processes",
        )

        panel_content = ft.Column([
            ft.Column(ref=self.gpu_col, spacing=6),
            self.gpu_procs_container
        ], spacing=6)
        
        return self._card("Graphics Cards", "🎮", panel_content, ACCENT_CYAN, action_btn=self.gpu_procs_btn)

    def _ai_panel(self):
        panel_content = ft.Column([
            ft.Column(ref=self.ai_col, spacing=4)
        ], spacing=4)
        return self._card("AI Inference", "🤖", panel_content, ACCENT_MAGENTA)

    def _disk_panel(self):
        panel_content = ft.Column([
            ft.Column(ref=self.disk_col, spacing=4)
        ], spacing=4)
        return self._card("Storage", "💿", panel_content, ACCENT_VIOLET)

    def _network_panel(self):
        panel_content = ft.Row([
            ft.Column([
                ft.Row([ft.Icon(ft.icons.Icons.ARROW_DOWNWARD, color=ACCENT_GREEN, size=12), ft.Text("Down", color=TEXT_SECONDARY, size=10)]),
                ft.Text("0 KB/s", ref=self.net_down_text, size=14, weight="bold", color=ACCENT_GREEN),
            ], spacing=2, expand=True),
            ft.Column([
                ft.Row([ft.Icon(ft.icons.Icons.ARROW_UPWARD, color=ACCENT_CYAN, size=12), ft.Text("Up", color=TEXT_SECONDARY, size=10)]),
                ft.Text("0 KB/s", ref=self.net_up_text, size=14, weight="bold", color=ACCENT_CYAN),
            ], spacing=2, expand=True),
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)
        return self._card("Network", "🌐", panel_content, ACCENT_ORANGE)

    # ── Interaction Callbacks ───────────────────────────────────

    def _toggle_cores(self, e):
        self.cores_expanded = not self.cores_expanded
        self.cores_btn.icon = ft.icons.Icons.KEYBOARD_ARROW_UP if self.cores_expanded else ft.icons.Icons.KEYBOARD_ARROW_DOWN
        self.cpu_cores_container.visible = self.cores_expanded
        self.page.update()

    def _toggle_gpu_procs(self, e):
        self.gpu_procs_expanded = not self.gpu_procs_expanded
        self.gpu_procs_btn.icon = ft.icons.Icons.KEYBOARD_ARROW_UP if self.gpu_procs_expanded else ft.icons.Icons.KEYBOARD_ARROW_DOWN
        self.gpu_procs_container.visible = self.gpu_procs_expanded
        self.page.update()

    def _window_changed(self, e):
        selected_val = list(e.control.selected)[0]
        self.active_window = selected_val
        self._update_charts(self.collector.history())

    def _chart_changed(self, e):
        selected_val = list(e.control.selected)[0]
        self.active_chart = selected_val
        # Show the GPU selector only when the GPU chart is active
        self.gpu_selector_row.visible = (self.active_chart == "gpu")
        self.page.update()
        # Force immediate chart render
        self._update_charts(self.collector.history())

    def _gpu_changed(self, e):
        val = getattr(e, "data", None)
        if not isinstance(val, str) or not val:
            val = e.control.value
        self.selected_gpu = val
        self._update_charts(self.collector.history())

    def _selected_gpu_index(self) -> int | None:
        """Return the selected GPU index, or None if 'all' / invalid."""
        if self.selected_gpu == "all":
            return None
        if self.selected_gpu.isdigit():
            idx = int(self.selected_gpu)
            if 0 <= idx < len(self.gpu_names):
                return idx
        return None

    # ── Background Loop ─────────────────────────────────────────

    def _start_collector(self):
        def loop():
            try:
                self.collector.update()
                snap = self.collector.get()
                self.page.run_thread(self._update_ui, snap)
                self.page.run_thread(self._update_charts, self.collector.history())

                chart_interval = CFG.get("chart_refresh_s", 3)
                last_chart = time.monotonic()
                while self._running:
                    time.sleep(CFG.get("refresh_ms", 1000) / 1000)
                    if not self._running:
                        break
                    self.collector.update()
                    snap = self.collector.get()
                    self.page.run_thread(self._update_ui, snap)

                    now = time.monotonic()
                    if now - last_chart >= chart_interval:
                        last_chart = now
                        self.page.run_thread(self._update_charts, self.collector.history())
            except Exception:
                self._running = False

        threading.Thread(target=loop, daemon=True).start()

    # ── UI Updates ──────────────────────────────────────────────

    def _update_ui(self, snap: Snapshot):
        if not self._running:
            return
        th = CFG.get("thresholds", {})

        # 0. Clock
        if self.time_text.current:
            self.time_text.current.value = datetime.now().strftime('%H:%M:%S')

        # 1. CPU Update
        color = pct_color(snap.cpu_avg, warn=th.get("cpu_warn", 80), danger=th.get("cpu_danger", 90))
        if self.cpu_avg_text.current:
            self.cpu_avg_text.current.value = f"{snap.cpu_avg:.1f}%"
            self.cpu_avg_text.current.color = color
        if self.cpu_freq_text.current:
            self.cpu_freq_text.current.value = f"{snap.cpu_freq:.0f} MHz ({snap.cpu_count}T)"
        if self.cpu_pct_badge.current:
            self.cpu_pct_badge.current.bgcolor = alpha_hex(color, "15")
            self.cpu_pct_badge.current.border = ft.Border.all(1, alpha_hex(color, "40"))
        if self.cpu_pct_text.current:
            self.cpu_pct_text.current.value = f"{snap.cpu_avg:.0f}%"
            self.cpu_pct_text.current.color = color
        if self.cpu_power_text.current:
            est = "~" if snap.cpu_power_source == "estimate" else ""
            suffix = " (est.)" if snap.cpu_power_source == "estimate" else ""
            self.cpu_power_text.current.value = f"{est}{snap.cpu_power_w:.0f} W{suffix}"
        if self.total_power_text.current:
            self.total_power_text.current.value = f"⚡ System: {snap.total_power_w:.0f} W"

        # Expandable Cores list
        if self.cores_expanded and self.cpu_bars_col.current:
            if not self.cpu_bars_col.current.controls:
                for i in range(snap.cpu_count):
                    lbl = ft.Text(f"T {i:2d}", size=10, color=TEXT_SECONDARY, width=32)
                    bar = ft.ProgressBar(value=0, bgcolor=BG_BAR, color=ACCENT_GREEN,
                                         height=6, border_radius=3, expand=True)
                    pct = ft.Text("0%", size=10, color=TEXT_SECONDARY, width=32, text_align=ft.TextAlign.RIGHT)
                    self.cpu_bars_col.current.controls.append(
                        ft.Row([lbl, bar, pct], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                    )
            for i, val in enumerate(snap.cpu_per_core):
                if i < len(self.cpu_bars_col.current.controls):
                    row = self.cpu_bars_col.current.controls[i]
                    row.controls[1].value = val / 100
                    row.controls[1].color = pct_color(val)
                    row.controls[2].value = f"{val:.0f}%"
                    row.controls[2].color = pct_color(val)

        # 2. RAM Update
        ram_col = pct_color(snap.ram_pct, warn=th.get("ram_warn", 80), danger=th.get("ram_danger", 90))
        if self.ram_bar.current:
            self.ram_bar.current.value = snap.ram_pct / 100
            self.ram_bar.current.color = ram_col
        if self.ram_val_text.current:
            self.ram_val_text.current.value = f"{snap.ram_used_gb:.1f} / {snap.ram_total_gb:.1f} GB"
        if self.ram_pct_badge.current:
            self.ram_pct_badge.current.bgcolor = alpha_hex(ram_col, "15")
            self.ram_pct_badge.current.border = ft.Border.all(1, alpha_hex(ram_col, "40"))
        if self.ram_pct_text.current:
            self.ram_pct_text.current.value = f"{snap.ram_pct:.1f}%"
            self.ram_pct_text.current.color = ram_col
        if self.swap_text.current:
            self.swap_text.current.value = f"Swap: {snap.swap_used_gb:.1f} / {snap.swap_total_gb:.1f} GB ({snap.swap_pct:.1f}%)"

        # 3. GPU Update
        if snap.gpus:
            self._update_gpu_selector(snap.gpus)
            gpu_controls = []
            for idx, g in enumerate(snap.gpus):
                name_short = g["name"].replace("NVIDIA ", "").replace("Tesla ", "").replace("GeForce ", "")
                # Add indicator box
                gpu_controls.append(ft.Row([
                    ft.Text("◽", color=ACCENT_CYAN, size=12),
                    ft.Text(f"GPU {idx}: {name_short}", size=12, weight="bold", color=TEXT_PRIMARY)
                ], spacing=4))
                
                # Bars
                gpu_controls.append(ft.Row([
                    ft.Text("Load:", color=TEXT_SECONDARY, size=10, width=32),
                    ft.ProgressBar(value=g["gpu_util"]/100, color=ACCENT_GREEN, bgcolor=BG_INPUT, height=6, border_radius=3, expand=True),
                    ft.Text(f"{g['gpu_util']}%", color=ACCENT_GREEN, size=11, weight="bold", width=35, text_align=ft.TextAlign.RIGHT),
                ], spacing=6))
                
                vram_gb_str = f"{g['vram_used_gb']:.1f} / {g['vram_total_gb']:.1f} GB"
                gpu_controls.append(ft.Row([
                    ft.Text("VRAM:", color=TEXT_SECONDARY, size=10, width=32),
                    ft.ProgressBar(value=g["vram_pct"]/100, color=ACCENT_CYAN, bgcolor=BG_INPUT, height=6, border_radius=3, expand=True),
                    ft.Text(f"{vram_gb_str} ({g['vram_pct']:.0f}%)", color=ACCENT_CYAN, size=11, weight="bold"),
                ], spacing=6))
                
                # Sub stats line
                temp_str = f"{g['temp']}°C"
                power_str = f"{g['power']:.0f} W"
                fan_str = f"Fan {g['fan']}%" if g.get("fan") is not None else "Fan N/A"
                gpu_controls.append(
                    ft.Row([
                        ft.Icon(ft.icons.Icons.THERMOSTAT, color=temp_color(g['temp']), size=11),
                        ft.Text(temp_str, color=temp_color(g['temp']), size=11, weight="bold"),
                        ft.Container(width=10),
                        ft.Icon(ft.icons.Icons.BOLT, color=ACCENT_ORANGE, size=11),
                        ft.Text(power_str, color=ACCENT_ORANGE, size=11, weight="bold"),
                        ft.Container(width=10),
                        ft.Icon(ft.icons.Icons.AC_UNIT, color=TEXT_SECONDARY, size=11),
                        ft.Text(fan_str, color=TEXT_SECONDARY, size=10),
                    ], spacing=2)
                )
                gpu_controls.append(ft.Divider(height=6, color=BORDER_SUBTLE))
            self.gpu_col.current.controls = gpu_controls[:-1] if gpu_controls else []
        else:
            self.gpu_col.current.controls = [ft.Text("No NVIDIA GPU detected", color=TEXT_SECONDARY, size=11, italic=True)]
            # Reset the GPU selector when no GPU is present
            self._gpu_options_cache = []
            self.gpu_names = []
            self.gpu_dropdown.options = [ft.dropdown.Option("all", "All GPUs")]
            if self.selected_gpu != "all":
                self.selected_gpu = "all"
                self.gpu_dropdown.value = "all"

        # Expandable GPU Processes
        if self.gpu_procs_expanded:
            proc_controls = []
            all_procs = []
            for g_idx, g in enumerate(snap.gpus):
                if g.get("processes"):
                    for p in g["processes"]:
                        all_procs.append((g_idx, p))
            
            # Sort by VRAM Usage descending
            all_procs.sort(key=lambda x: x[1]["vram_mb"], reverse=True)
            
            for g_idx, p in all_procs[:6]:
                vram_str = f"{p['vram_mb']:.1f} MB" if p["vram_mb"] > 0 else "N/A"
                name_short = p["name"]
                if len(name_short) > 22:
                    name_short = name_short[:19] + "..."
                proc_controls.append(ft.Row([
                    ft.Text(f"[{g_idx}] {name_short}", size=11, color=TEXT_PRIMARY, expand=True, no_wrap=True),
                    ft.Text(str(p["pid"]), size=10, color=TEXT_SECONDARY, width=50, text_align=ft.TextAlign.RIGHT),
                    ft.Text(vram_str, size=11, color=ACCENT_MAGENTA, weight="bold", width=70, text_align=ft.TextAlign.RIGHT),
                ], spacing=6))
            
            if len(all_procs) > 6:
                proc_controls.append(
                    ft.Text(f"... and {len(all_procs) - 6} more processes", size=10, color=TEXT_SECONDARY, italic=True)
                )
            
            if not proc_controls:
                proc_controls.append(ft.Text("No active processes in VRAM", size=10, color=TEXT_SECONDARY, italic=True))
                
            self.gpu_procs_list.controls = proc_controls

        # 4. AI Inference Update
        ai_ctrls = []
        for e in snap.ai_engines:
            ai_ctrls.append(ft.Row([
                ft.Text("🤖", size=12),
                ft.Text(e["engine"], size=12, weight="bold", color=TEXT_PRIMARY, width=110, no_wrap=True),
                ft.Text(e["model"] or "no model loaded", size=11, color=ACCENT_CYAN if e["model"] else TEXT_SECONDARY, expand=True, no_wrap=True),
            ], spacing=6))
            if e.get("mem_bytes"):
                ai_ctrls.append(ft.Text(f"💾 {format_memory(e['mem_bytes'])}  ·  {' '.join(e['processes'][:2]) if e['processes'] else 'server API'}",
                                        size=9, color=TEXT_SECONDARY))
            ai_ctrls.append(ft.Divider(height=4, color=BORDER_SUBTLE))
        if not ai_ctrls:
            ai_ctrls = [ft.Text("No local AI inference processes detected", size=11, color=TEXT_SECONDARY, italic=True)]
        self.ai_col.current.controls = ai_ctrls

        # 5. Disks Update
        disk_ctrls = []
        for d in snap.disks:
            mount_lbl = d['mount']
            disk_ctrls.append(ft.Row([
                ft.Text(f"💽 {mount_lbl}", size=11, color=TEXT_PRIMARY, weight="bold"),
                ft.Text(f"{d['pct']:.0f}%", size=11, color=ACCENT_VIOLET, weight="bold"),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
            disk_ctrls.append(
                ft.ProgressBar(value=d["pct"]/100, bgcolor=BG_BAR, color=ACCENT_VIOLET, height=6, border_radius=3)
            )
            disk_ctrls.append(
                ft.Text(f"{d['used_gb']:.0f}/{d['total_gb']:.0f} GB", size=9, color=TEXT_SECONDARY)
            )
        self.disk_col.current.controls = disk_ctrls

        # 5. Network Update
        self.net_down_text.current.value = f"{snap.net_recv_kbps:,.0f} KB/s" if snap.net_recv_kbps < 1024 else f"{snap.net_recv_kbps/1024:,.1f} MB/s"
        self.net_up_text.current.value = f"{snap.net_sent_kbps:,.0f} KB/s" if snap.net_sent_kbps < 1024 else f"{snap.net_sent_kbps/1024:,.1f} MB/s"

        # 6. Status / Uptime
        boot = psutil.boot_time()
        up_sec = time.time() - boot
        d, r = divmod(int(up_sec), 86400)
        h, r = divmod(r, 3600)
        m, _ = divmod(r, 60)
        self.uptime_text.current.value = f"Uptime: {d}d {h}h {m}m"

        try:
            self.page.update()
        except Exception:
            self._running = False

    def _update_gpu_selector(self, gpus: list[dict]) -> None:
        """Populate the GPU dropdown options from the live GPU list."""
        names = [
            f"GPU {idx}: {g['name'].replace('NVIDIA ', '').replace('Tesla ', '').replace('GeForce ', '')}"
            for idx, g in enumerate(gpus)
        ]
        if names == self._gpu_options_cache:
            return
        self._gpu_options_cache = names
        self.gpu_names = names
        self.gpu_dropdown.options = [ft.dropdown.Option("all", "All GPUs")] + [
            ft.dropdown.Option(str(idx), name) for idx, name in enumerate(names)
        ]
        # Keep the selection valid if the GPU set changed
        if self.selected_gpu != "all" and (
            not self.selected_gpu.isdigit() or int(self.selected_gpu) >= len(names)
        ):
            self.selected_gpu = "all"
            self.gpu_dropdown.value = "all"

    def _update_charts(self, hist: dict):
        if not self._running:
            return
        try:
            # Apply time window filter
            filtered = self._filter_history(hist)
            if self.active_chart == "cpu":
                img_data = cpu_chart(filtered)
            elif self.active_chart == "ram":
                img_data = ram_chart(filtered)
            elif self.active_chart == "gpu":
                img_data = gpu_chart(filtered, gpu_index=self._selected_gpu_index(), gpu_names=self.gpu_names)
            elif self.active_chart == "power":
                img_data = total_power_chart(filtered)
            else:
                img_data = net_chart(filtered)
                
            self.chart_img.current.src = f"data:image/png;base64,{base64.b64encode(img_data).decode()}"
            self.chart_img.current.update()
        except Exception:
            if not self._running:
                return
            logging.getLogger(__name__).exception("chart %s failed", self.active_chart)

    def _filter_history(self, hist: dict) -> dict:
        """Return history trimmed to the selected time window."""
        if self.active_window == "all":
            return hist
        times = hist.get("times", [])
        if not times:
            return hist
        window_s = {"1m": 60, "2m": 120, "5m": 300}.get(self.active_window, 120)
        cutoff = times[-1] - window_s
        # Find first index >= cutoff
        idx = 0
        for i, t in enumerate(times):
            if t >= cutoff:
                idx = i
                break
        out = {}
        for k, v in hist.items():
            # Per-GPU series are stored as a list of lists: slice each series
            if isinstance(v, list) and v and isinstance(v[0], (list, tuple)):
                out[k] = [series[idx:] for series in v]
            else:
                out[k] = v[idx:]
        return out

    def stop(self):
        self._running = False


def main(page: ft.Page):
    dash = Dashboard(page)
    dash.build()
    page.on_close = lambda e: dash.stop()
    page.on_disconnect = lambda e: dash.stop()


if __name__ == "__main__":
    ft.run(main)

