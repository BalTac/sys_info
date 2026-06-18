"""Disk panel — usage bar, read/write speeds."""

import flet as ft
from config import DISK_COLOR, DISK_ALT, TEXT_PRIMARY
from panels.utils import format_bytes, make_label, make_value, make_panel_card


class DiskPanel:
    def __init__(self, page):
        self.page = page
        self.usage_bar = ft.ProgressBar(width=150, color=DISK_COLOR, active_color=DISK_ALT, bgcolor="#30363d")
        self.used_text = make_value("0", DISK_COLOR, 36)
        self.total_text = make_label("0", ft.colors.white70, 14)
        self._container = None

    def get_widget(self):
        self._container = make_panel_card(
            "DISK",
            ft.icons.storage,
            ft.Column([
                ft.Row([
                    make_label("USAGE", DISK_COLOR),
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
                    content=self.total_text,
                    width=100,
                    alignment=ft.alignment.center,
                ),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            DISK_COLOR,
        )
        return self._container

    def update(self):
        sn = self.page.snap if hasattr(self.page, "snap") else None
        if not sn:
            return
        usage = sn["disk_usage"]
        total = sn.get("disk_total", 0)
        used = sn["disk_used"]

        self.usage_bar.value = usage / 100
        self.used_text.value = f"{usage:.1f}%"
        self.total_text.value = f"of {format_bytes(total)}"
        self.page.update()
