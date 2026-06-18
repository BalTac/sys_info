"""Network panel — up/down speeds, activity indicator."""

import flet as ft
from config import NETWORK_COLOR, NETWORK_ALT, TEXT_PRIMARY
from panels.utils import format_bytes, make_label, make_value, make_panel_card


class NetworkPanel:
    def __init__(self, page):
        self.page = page
        self.up_speed = make_value("0", NETWORK_COLOR, 20)
        self.down_speed = make_value("0", NETWORK_COLOR, 20)
        self._container = None

    def get_widget(self):
        self._container = make_panel_card(
            "NETWORK",
            ft.icons.wifi,
            ft.Row([
                ft.Column([
                    ft.Row([ft.Icon(ft.icons.ARROW_UPWARD, color=NETWORK_COLOR, size=14), ft.Text("UP", color=NETWORK_COLOR, size=10)]),
                    ft.Container(content=self.up_speed, alignment=ft.alignment.center),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(width=40),
                ft.Column([
                    ft.Row([ft.Icon(ft.icons.ARROW_DOWNWARD, color=NETWORK_COLOR, size=14), ft.Text("DOWN", color=NETWORK_COLOR, size=10)]),
                    ft.Container(content=self.down_speed, alignment=ft.alignment.center),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
            ]),
            NETWORK_COLOR,
        )
        return self._container

    def update(self):
        sn = self.page.snap if hasattr(self.page, "snap") else None
        if not sn:
            return
        up = sn.get("net_up", 0)
        down = sn.get("net_down", 0)
        self.up_speed.value = f"{format_bytes(up)}s"
        self.down_speed.value = f"{format_bytes(down)}s"
        self.page.update()
