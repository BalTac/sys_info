"""CPU panel — usage %, cores bars, temperature, load avg."""

import flet as ft
from config import CPU_COLOR, CPU_ALT, TEXT_PRIMARY
from panels.utils import format_bytes, make_label, make_value, make_panel_card


class CPUPanel:
    def __init__(self, page):
        self.page = page
        self.usage_bar = ft.ProgressBar(width=150, color=CPU_COLOR, active_color=CPU_ALT, bgcolor="#30363d")
        self.core_bars = []
        self.temp_text = make_value("0", CPU_COLOR, 36)
        self.load_texts = [
            make_label("1m", CPU_COLOR),
            make_label("5m", CPU_COLOR),
            make_label("15m", CPU_COLOR),
        ]
        self.procs_text = make_value("CPU", CPU_COLOR, 14)
        self._container = None

    def get_widget(self):
        self._container = make_panel_card(
            "CPU",
            ft.icons.CELL_TOWER,
            ft.Row([
                ft.Column([
                    ft.Row([
                        make_label("USAGE", CPU_COLOR),
                        ft.Container(expand=True),
                    ]),
                    ft.Container(
                        content=self.usage_bar,
                        width=150,
                        height=8,
                        border_radius=4,
                    ),
                    ft.Row([
                        ft.Text("0%", color=CPU_COLOR, size=14, weight="bold", text_align="center"),
                    ]),
                    ft.Row([
                        ft.Container(content=self.temp_text, width=50),
                        ft.Container(content=self.load_texts[0], width=40, alignment=ft.alignment.center),
                        ft.Container(content=self.load_texts[1], width=40, alignment=ft.alignment.center),
                        ft.Container(content=self.load_texts[2], width=40, alignment=ft.alignment.center),
                    ]),
                    ft.Row([
                        self.procs_text,
                        ft.Icon(ft.icons.CPU_CHIPS, color=CPU_COLOR, size=14),
                    ]),
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ]),
            CPU_COLOR,
        )
        return self._container

    def update(self):
        sn = self.page.snapt if hasattr(self.page, "snapt") else None
        if not sn:
            return
        usage = sn["cpu_usage"]
        cores = sn.get("cpu_cores", [0])
        temp = sn.get("cpu_temp", 0)
        load_avg = sn.get("cpu_load_avg", (0, 0, 0))

        self.usage_bar.value = usage / 100
        self.temp_text.value = f"{temp:.0f}°C"
        for i, lt in enumerate(self.load_texts):
            lt.value = f"{load_avg[i]:.2f}" if load_avg[i] else "0.00"
            lt.color = CPU_COLOR if load_avg[i] < 7 else ft.colors.orange if load_avg[i] < 8 else ft.colors.red
        self.procs_text.value = f"{len(cores)} CORES"
        self.page.update()
