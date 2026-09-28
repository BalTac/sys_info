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
from charts import cpu_chart, ram_chart, gpu_chart, net_chart
from ai_detector import format_memory

# Premium Neon Color Palette
ACCENT  = "#00d4ff"  # Neon Cyan
GREEN   = "#00f5a0"  # Neon Emerald Green
ORANGE  = "#ff8a00"  # Neon Orange
MAGENTA = "#f857a6"  # Neon Magenta
VIOLET  = "#b388ff"  # Neon Purple
CYAN    = "#18ffff"  # Bright Cyan
WHITE   = "#e6edf3"  # Off-white
DIM     = "#7d8590"  # Muted Gray
BG      = "#07050f"  # Dark Space Deep Violet
CARD_BG = "#110b1f"  # Rich Dark Card BG


def pct_color(v: float, warn: float = 80, danger: float = 90) -> str:
    if v >= danger: return "#ff5252"
    if v >= warn:   return "#ffab40"
    return GREEN


def temp_color(v: int) -> str:
    th = CFG.get("thresholds", {})
    danger = th.get("gpu_temp_danger", 85)
    warn = th.get("gpu_temp_warn", 75)
    if v >= danger: return "#ff5252"
    if v >= warn: return "#ffab40"
    return GREEN


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

    def build(self):
        # Configure fonts and default styles
        self.page.fonts = {
            "Outfit": "https://fonts.gstatic.com/s/outfit/v11/q35yFy1g9eR16dRCgN7X.woff2"
        }
        self.page.theme = ft.Theme(font_family="Outfit")
        
        self.page.title = "⚡ System Panel"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = BG
        self.page.padding = 12
        self.page.scroll = ft.ScrollMode.AUTO
        
        # Sized for portrait sidebar layout
        self.page.window.width = 500
        self.page.window.height = 1150
        self.page.window.min_width = 440
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
                    bgcolor=GREEN,
                    border_radius=3,
                ),
                ft.Text("LIVE", color=GREEN, size=9, weight="bold"),
            ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
            bgcolor="#0a2215",
            border=ft.Border.all(1, "#164e2b"),
            padding=ft.padding.Padding(6, 2, 6, 2),
            border_radius=6,
        )

        from config import __version__, __author__, __repo__
        header = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Row([
                        ft.Text("⚡ AI System Panel", size=17, weight="bold", color=ACCENT),
                    ]),
                    ft.Text(f"🖥  {hostname}  •  {platform.system()}", color=DIM, size=10),
                    ft.Text(f"v{__version__}  ·  (c) {__author__} 2026  ·  {__repo__}", color="#7d8590", size=11),
                ], spacing=1),
                ft.Column([
                    ft.Row([
                        status_badge,
                        ft.Text("", ref=self.time_text, color=WHITE, size=11, weight="bold"),
                    ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Text("", ref=self.uptime_text, color=DIM, size=10, text_align=ft.TextAlign.RIGHT),
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
                ft.Segment(value="net", label=ft.Text("Rete", size=10, weight="bold")),
            ],
            selected=["cpu"],
            on_change=self._chart_changed,
            show_selected_icon=False,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                color=WHITE,
                bgcolor={
                    ft.ControlState.SELECTED: "#22173b",
                    ft.ControlState.DEFAULT: "#120e24",
                },
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
                color=WHITE,
                bgcolor={
                    ft.ControlState.SELECTED: "#22173b",
                    ft.ControlState.DEFAULT: "#120e24",
                },
            ),
        )

        # ── GPU selector (shown only when the GPU chart is active) ──
        self.gpu_dropdown = ft.Dropdown(
            label="GPU",
            value="all",
            options=[ft.dropdown.Option("all", "Tutte")],
            on_select=self._gpu_changed,
            width=180,
            text_style=ft.TextStyle(color=WHITE, size=11),
            label_style=ft.TextStyle(color=DIM, size=9),
            border_color="#22173b",
            bgcolor="#100b1a",
        )
        self.gpu_selector_row = ft.Container(
            content=ft.Row([
                ft.Text("GPU:", color=WHITE, size=11, weight="bold"),
                self.gpu_dropdown,
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            visible=False,
            padding=ft.Padding(top=4, bottom=2),
        )

        chart_header_row = ft.Row([
            ft.Row([
                ft.Icon(ft.icons.Icons.TIMELINE, color=VIOLET, size=16),
                ft.Text("Storico", size=12, weight="bold", color=WHITE),
            ], spacing=4),
            chart_selector
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        _BLANK_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        chart_card = ft.Container(
            content=ft.Image(
                src=f"data:image/png;base64,{_BLANK_PNG}",
                ref=self.chart_img,
                width=440,
                height=260,
                fit=ft.BoxFit.CONTAIN,
                border_radius=8,
            ),
            bgcolor="#100b1a",
            border_radius=12,
            padding=6,
            border=ft.Border.all(1, "#22173b"),
            alignment=ft.alignment.Alignment(0, 0)
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
                ft.Divider(height=6, color="#22173b"),
                chart_header_row,
                self.gpu_selector_row,
                chart_card,
                ft.Row([window_selector], alignment=ft.MainAxisAlignment.CENTER),
            ], expand=False, spacing=8)
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
                ft.Text(title, size=12, weight="bold", color=WHITE),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        
        if action_btn:
            header_row.controls.append(action_btn)
            
        def on_hover(e):
            is_hover = e.data == "true"
            border_col = color if is_hover else "#22173b"
            e.control.border = ft.Border.all(1, border_col)
            e.control.shadow = ft.BoxShadow(
                blur_radius=12,
                color=f"{color}20" if is_hover else "#00000040",
                spread_radius=1 if is_hover else 0
            )
            e.control.update()

        return ft.Container(
            content=ft.Column([
                header_row,
                ft.Divider(height=1, color="#22173b"),
                content,
            ], spacing=6),
            bgcolor=CARD_BG,
            border_radius=14,
            padding=12,
            border=ft.Border.all(1, "#22173b"),
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
            bgcolor="#0a0814"
        )
        
        self.cores_btn = ft.IconButton(
            icon=ft.icons.Icons.KEYBOARD_ARROW_DOWN,
            icon_color=GREEN,
            icon_size=16,
            on_click=self._toggle_cores,
            tooltip="Mostra Cores",
        )
        
        pct_badge = ft.Container(
            ref=self.cpu_pct_badge,
            content=ft.Text("0%", ref=self.cpu_pct_text, size=10, weight="bold", color=GREEN),
            bgcolor=f"{GREEN}15",
            border=ft.Border.all(1, f"{GREEN}40"),
            padding=ft.padding.Padding(6, 2, 6, 2),
            border_radius=6,
        )

        panel_content = ft.Column([
            ft.Row([
                ft.Row([
                    ft.Text("Carico CPU:", color=DIM, size=11),
                    ft.Text("0%", ref=self.cpu_avg_text, size=12, weight="bold", color=WHITE),
                ], spacing=4),
                pct_badge
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([
                ft.Text("Info CPU:", color=DIM, size=10),
                ft.Text("", ref=self.cpu_freq_text, color=WHITE, size=11, weight="bold", text_align=ft.TextAlign.RIGHT),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.cpu_cores_container
        ], spacing=6)
        
        return self._card("Processore", "🧠", panel_content, GREEN, action_btn=self.cores_btn)

    def _ram_panel(self):
        pct_badge = ft.Container(
            ref=self.ram_pct_badge,
            content=ft.Text("0%", ref=self.ram_pct_text, size=10, weight="bold", color=MAGENTA),
            bgcolor=f"{MAGENTA}15",
            border=ft.Border.all(1, f"{MAGENTA}40"),
            padding=ft.padding.Padding(6, 2, 6, 2),
            border_radius=6,
        )

        panel_content = ft.Column([
            ft.Row([
                ft.Row([
                    ft.Text("Memoria:", color=DIM, size=11),
                    ft.Text("0 / 0 GB", ref=self.ram_val_text, color=WHITE, size=12, weight="bold"),
                ], spacing=4),
                pct_badge
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.ProgressBar(ref=self.ram_bar, value=0, bgcolor="#1a122e",
                           color=MAGENTA, height=6, border_radius=3),
            ft.Text("", ref=self.swap_text, color=DIM, size=10),
        ], spacing=6)
        
        return self._card("Memoria di Sistema", "💾", panel_content, MAGENTA)

    def _gpu_panel(self):
        self.gpu_procs_list = ft.Column(spacing=2)
        self.gpu_procs_container = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Processo", size=10, color=DIM, weight="bold", expand=True),
                    ft.Text("PID", size=10, color=DIM, weight="bold", width=50, text_align=ft.TextAlign.RIGHT),
                    ft.Text("VRAM", size=10, color=DIM, weight="bold", width=70, text_align=ft.TextAlign.RIGHT),
                ], spacing=6),
                ft.Divider(height=1, color="#22173b"),
                self.gpu_procs_list
            ], spacing=4),
            visible=False,
            padding=ft.Padding(left=6, top=4, right=6, bottom=4),
            border_radius=8,
            bgcolor="#0a0814"
        )
        
        self.gpu_procs_btn = ft.IconButton(
            icon=ft.icons.Icons.KEYBOARD_ARROW_DOWN,
            icon_color=CYAN,
            icon_size=16,
            on_click=self._toggle_gpu_procs,
            tooltip="Mostra Processi GPU",
        )

        panel_content = ft.Column([
            ft.Column(ref=self.gpu_col, spacing=6),
            self.gpu_procs_container
        ], spacing=6)
        
        return self._card("Schede Video", "🎮", panel_content, CYAN, action_btn=self.gpu_procs_btn)

    def _ai_panel(self):
        panel_content = ft.Column([
            ft.Column(ref=self.ai_col, spacing=4)
        ], spacing=4)
        return self._card("Inferenza AI", "🤖", panel_content, MAGENTA)

    def _disk_panel(self):
        panel_content = ft.Column([
            ft.Column(ref=self.disk_col, spacing=4)
        ], spacing=4)
        return self._card("Archiviazione", "💿", panel_content, VIOLET)

    def _network_panel(self):
        panel_content = ft.Row([
            ft.Column([
                ft.Row([ft.Icon(ft.icons.Icons.ARROW_DOWNWARD, color=GREEN, size=12), ft.Text("Down", color=DIM, size=10)]),
                ft.Text("0 KB/s", ref=self.net_down_text, size=14, weight="bold", color=GREEN),
            ], spacing=2, expand=True),
            ft.Column([
                ft.Row([ft.Icon(ft.icons.Icons.ARROW_UPWARD, color=CYAN, size=12), ft.Text("Up", color=DIM, size=10)]),
                ft.Text("0 KB/s", ref=self.net_up_text, size=14, weight="bold", color=CYAN),
            ], spacing=2, expand=True),
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)
        return self._card("Rete", "🌐", panel_content, ORANGE)

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
            # Initial run to populate data and charts immediately on startup
            self.collector.update()
            snap = self.collector.get()
            self.page.run_thread(self._update_ui, snap)
            hist = self.collector.history()
            self.page.run_thread(self._update_charts, hist)

            chart_interval = CFG.get("chart_refresh_s", 3)
            last_chart = time.monotonic()
            while self._running:
                time.sleep(CFG.get("refresh_ms", 1000) / 1000)
                
                self.collector.update()
                snap = self.collector.get()
                self.page.run_thread(self._update_ui, snap)

                now = time.monotonic()
                if now - last_chart >= chart_interval:
                    last_chart = now
                    hist = self.collector.history()
                    self.page.run_thread(self._update_charts, hist)

        threading.Thread(target=loop, daemon=True).start()

    # ── UI Updates ──────────────────────────────────────────────

    def _update_ui(self, snap: Snapshot):
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
            self.cpu_pct_badge.current.bgcolor = f"{color}15"
            self.cpu_pct_badge.current.border = ft.Border.all(1, f"{color}40")
        if self.cpu_pct_text.current:
            self.cpu_pct_text.current.value = f"{snap.cpu_avg:.0f}%"
            self.cpu_pct_text.current.color = color

        # Expandable Cores list
        if self.cores_expanded and self.cpu_bars_col.current:
            if not self.cpu_bars_col.current.controls:
                for i in range(snap.cpu_count):
                    lbl = ft.Text(f"T {i:2d}", size=10, color=DIM, width=32)
                    bar = ft.ProgressBar(value=0, bgcolor="#1a122e", color=GREEN,
                                         height=6, border_radius=3, expand=True)
                    pct = ft.Text("0%", size=10, color=DIM, width=32, text_align=ft.TextAlign.RIGHT)
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
            self.ram_pct_badge.current.bgcolor = f"{ram_col}15"
            self.ram_pct_badge.current.border = ft.Border.all(1, f"{ram_col}40")
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
                    ft.Text("◽", color=CYAN, size=12),
                    ft.Text(f"GPU {idx}: {name_short}", size=12, weight="bold", color=WHITE)
                ], spacing=4))
                
                # Bars
                gpu_controls.append(ft.Row([
                    ft.Text(f"Load:", color=DIM, size=10, width=32),
                    ft.ProgressBar(value=g["gpu_util"]/100, color=GREEN, bgcolor="#100b1a", height=6, border_radius=3, expand=True),
                    ft.Text(f"{g['gpu_util']}%", color=GREEN, size=11, weight="bold", width=35, text_align=ft.TextAlign.RIGHT),
                ], spacing=6))
                
                vram_gb_str = f"{g['vram_used_gb']:.1f} / {g['vram_total_gb']:.1f} GB"
                gpu_controls.append(ft.Row([
                    ft.Text(f"VRAM:", color=DIM, size=10, width=32),
                    ft.ProgressBar(value=g["vram_pct"]/100, color=CYAN, bgcolor="#100b1a", height=6, border_radius=3, expand=True),
                    ft.Text(f"{vram_gb_str} ({g['vram_pct']:.0f}%)", color=CYAN, size=11, weight="bold"),
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
                        ft.Icon(ft.icons.Icons.BOLT, color=ORANGE, size=11),
                        ft.Text(power_str, color=ORANGE, size=11, weight="bold"),
                        ft.Container(width=10),
                        ft.Icon(ft.icons.Icons.AC_UNIT, color=DIM, size=11),
                        ft.Text(fan_str, color=DIM, size=10),
                    ], spacing=2)
                )
                gpu_controls.append(ft.Divider(height=6, color="#22173b"))
            self.gpu_col.current.controls = gpu_controls[:-1] if gpu_controls else []
        else:
            self.gpu_col.current.controls = [ft.Text("Nessuna GPU NVIDIA rilevata", color=DIM, size=11, italic=True)]
            # Reset the GPU selector when no GPU is present
            self._gpu_options_cache = []
            self.gpu_names = []
            self.gpu_dropdown.options = [ft.dropdown.Option("all", "Tutte")]
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
                    ft.Text(f"[{g_idx}] {name_short}", size=11, color=WHITE, expand=True, no_wrap=True),
                    ft.Text(str(p["pid"]), size=10, color=DIM, width=50, text_align=ft.TextAlign.RIGHT),
                    ft.Text(vram_str, size=11, color=MAGENTA, weight="bold", width=70, text_align=ft.TextAlign.RIGHT),
                ], spacing=6))
            
            if len(all_procs) > 6:
                proc_controls.append(
                    ft.Text(f"... e altri {len(all_procs) - 6} processi", size=10, color=DIM, italic=True)
                )
            
            if not proc_controls:
                proc_controls.append(ft.Text("Nessun processo attivo in VRAM", size=10, color=DIM, italic=True))
                
            self.gpu_procs_list.controls = proc_controls

        # 4. AI Inference Update
        ai_ctrls = []
        for e in snap.ai_engines:
            ai_ctrls.append(ft.Row([
                ft.Text("🤖", size=12),
                ft.Text(e["engine"], size=12, weight="bold", color=WHITE, width=110, no_wrap=True),
                ft.Text(e["model"] or "nessun modello caricato", size=11, color=CYAN if e["model"] else DIM, expand=True, no_wrap=True),
            ], spacing=6))
            if e.get("mem_bytes"):
                ai_ctrls.append(ft.Text(f"💾 {format_memory(e['mem_bytes'])}  ·  {' '.join(e['processes'][:2]) if e['processes'] else 'server API'}",
                                        size=9, color=DIM))
            ai_ctrls.append(ft.Divider(height=4, color="#22173b"))
        if not ai_ctrls:
            ai_ctrls = [ft.Text("Nessun processo di inferenza AI locale rilevato", size=11, color=DIM, italic=True)]
        self.ai_col.current.controls = ai_ctrls

        # 5. Disks Update
        disk_ctrls = []
        for d in snap.disks:
            mount_lbl = d['mount']
            disk_ctrls.append(ft.Row([
                ft.Text(f"💽 {mount_lbl}", size=11, color=WHITE, weight="bold"),
                ft.Text(f"{d['pct']:.0f}%", size=11, color=VIOLET, weight="bold"),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
            disk_ctrls.append(
                ft.ProgressBar(value=d["pct"]/100, bgcolor="#1a122e", color=VIOLET, height=6, border_radius=3)
            )
            disk_ctrls.append(
                ft.Text(f"{d['used_gb']:.0f}/{d['total_gb']:.0f} GB", size=9, color=DIM)
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

        self.page.update()

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
        self.gpu_dropdown.options = [ft.dropdown.Option("all", "Tutte")] + [
            ft.dropdown.Option(str(idx), name) for idx, name in enumerate(names)
        ]
        # Keep the selection valid if the GPU set changed
        if self.selected_gpu != "all" and (
            not self.selected_gpu.isdigit() or int(self.selected_gpu) >= len(names)
        ):
            self.selected_gpu = "all"
            self.gpu_dropdown.value = "all"

    def _update_charts(self, hist: dict):
        try:
            # Apply time window filter
            filtered = self._filter_history(hist)
            if self.active_chart == "cpu":
                img_data = cpu_chart(filtered)
            elif self.active_chart == "ram":
                img_data = ram_chart(filtered)
            elif self.active_chart == "gpu":
                img_data = gpu_chart(filtered, gpu_index=self._selected_gpu_index(), gpu_names=self.gpu_names)
            else:
                img_data = net_chart(filtered)
                
            self.chart_img.current.src = f"data:image/png;base64,{base64.b64encode(img_data).decode()}"
            self.chart_img.current.update()
        except Exception as e:
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


if __name__ == "__main__":
    ft.run(main)

