"""GPU panel — temperature, load, VRAM, fan."""

import flet as ft
from config import GPU_COLOR, GPU_ALT, TEXT_PRIMARY
from panels.utils import format_bytes, make_label, make_value, make_panel_card


class GPUPanel:
    def __init__(self, page):
        self.page = page
        self.temp_text = make_value("0", GPU_COLOR, 36)
        self.load_text = make_value("0%", GPU_COLOR, 20)
        self.vram_text = make_value("0", GPU_COLOR, 18)
        self.fan_text = make_value("0", GPU_COLOR, 18)
        self._container = None

    def get_widget(self):
        self._container = make_panel_card(
            "GPU",
            ft.icons.gpu_card,
            ft.Column([
                ft.Row([
                    ft.Text("TEMP", color=GPU_COLOR, size=10),
                    ft.Container(expand=True),
                    ft.Text("LOAD", color=GPU_COLOR, size=10),
                ]),
                ft.Row([
                    ft.Container(content=self.temp_text, width=80),
                    ft.Container(expand=True),
                    ft.Container(content=self.load_text, width=80),
                ]),
                ft.Row([
                    ft.Text("VRAM", color=GPU_COLOR, size=10),
                    ft.Container(expand=True),
                    ft.Text("FAN", color=GPU_COLOR, size=10),
                ]),
                ft.Row([
                    ft.Container(content=self.vram_text, width=80),
                    ft.Container(expand=True),
                    ft.Container(content=self.fan_text, width=80),
                ]),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
            GPU_COLOR,
        )
        return self._container

    def update(self):
        sn = self.page.snap if hasattr(self.page, "snap") else None
        if not sn:
            return
        temp = sn.get("gpu_temp", 0)
        load = sn.get("gpu_load", 0)
        vram_total = sn.get("gpu_vram_total", 0)
        vram_used = sn.get("gpu_vram_used", 0)
        fan = sn.get("gpu_fan", 0)

        self.temp_text.value = f"{temp:.0f}°C"
        self.load_text.value = f"{load:.0f}%"
        self.vram_text.value = f"{format_bytes(vram_used)}/{format_bytes(vram_total)}"
        self.fan_text.value = f"{fan:.0f} RPM"
        self.page.update()
