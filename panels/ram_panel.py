"""RAM panel — usage %, usage bars, top processes."""

import flet as ft
from config import RAM_COLOR, RAM_ALT, TEXT_PRIMARY
from panels.utils import format_bytes, make_label, make_value, make_panel_card


class RAMPanel:
    def __init__(self, page):
        self.page = page
        self.usage_bar = ft.ProgressBar(width=150, color=RAM_COLOR, active_color=RAM_ALT, bgcolor="#30363d")
        self.used_text = make_value("0", RAM_COLOR, 36)
        self.proc_texts = []
        self._container = None

    def get_widget(self):
        self.proc_texts = [make_value("0.0%", ft.colors.white70, 12) for _ in range(3)]
        self._container = make_panel_card(
            "RAM",
            ft.icons.memory,
            ft.Row([
                ft.Column([
                    ft.Row([
                        make_label("USAGE", RAM_COLOR),
                        ft.Container(expand=True),
                    ]),
                    ft.Container(
                        content=self.usage_bar,
                        width=150,
                        height=8,
                        border_radius=4,
                    ),
                    ft.Container(
                        content=self.used_text,
                        width=100,
                        alignment=ft.alignment.center,
                    ),
                    ft.Container(
                        content=ft.Column(self.proc_texts, spacing=2),
                        padding=5,
                    ),
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ]),
            RAM_COLOR,
        )
        return self._container

    def update(self):
        sn = self.page.snap if hasattr(self.page, "snap") else None
        if not sn:
            return
        usage = sn["ram_usage"]
        ram_used = sn["ram_used"]
        total = sn.get("ram_total", 1)
        used_pct = (ram_used / total * 100) if total else 0
        procs = sn.get("top_procs", [])

        self.usage_bar.value = usage / 100
        self.used_text.value = f"{used_pct:.1f}%"
        for i in range(3):
            if i < len(procs):
                name, mp, pid = procs[i]
                short_name = name[:12] if name else "Process"
                self.proc_texts[i].value = f"{short_name:12s} {mp:.1f}%"
            else:
                self.proc_texts[i].value = ""
        self.page.update()
