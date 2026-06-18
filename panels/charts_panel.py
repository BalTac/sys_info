"""ChartsPanel — matpotlib charts rendered as Flet Images."""

import io
import time
import flet as ft
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COL = {
    "cpu": ("#238636", "#3fb950"),
    "gpu": ("#d29922", "#f2a93a"),
    "ram": ("#1f6feb", "#58a6ff"),
    "net": ("#39d353", "#7ee787"),
}


# helpers
def _panel(title, icon, content, color, surface="#161b22", border="#30363d"):
    return ft.Container(
        content=ft.Column([
            ft.Row([ft.Icon(icon, color=color, size=18), ft.Text(title, color="white70", size=10)],
                   horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1, color=border),
            content,
        ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=12, border_radius=16, bgcolor=surface,
        border=ft.border.all(width=1, color=border),
        shadow=ft.BoxShadow(blur_radius=10, color="#00000040", spread_radius=2),
    )


class ChartsPanel:
    """Generate matplotlib chart images."""

    def __init__(self, collector):
        self.collector = collector

    def _line_img(self, data, title, color1, color2, prefix=""):
        """Render one line chart -> ft.Image."""
        if len(data) < 3:
            return ft.Image(
                content=ft.Text(f"Waiting for data...", color="white70", size=12),
                width=600, height=180,
            )
        vals = [d["value"] for d in data if isinstance(d, dict)]
        xs = list(range(len(vals)))
        y_min = min(vals) * 0.9
        y_max = max(vals) * 1.1 if max(vals) != min(vals) else min(vals) + 1

        fig, ax = plt.subplots(figsize=(10, 3.2), dpi=80)
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#161b22")
        for s in ("bottom", "top", "left", "right"):
            ax.spines[s].set_color("#30363d")
        ax.tick_params(colors="#8b949e")
        ax.grid(axis="y", color="#30363d", alpha=0.25)
        ax.fill_between(xs, vals, alpha=0.25, color=color1)
        ax.plot(xs, vals, color=color1, linewidth=2.5, marker="o", markersize=3)
        ax.set_ylim(y_min, y_max)
        ax.set_title(title, color="#e6edf3", fontsize=12, pad=10)
        if prefix:
            last_val = vals[-1]
            ax.text(0.98, 0.95, prefix, transform=ax.transAxes,
                    ha="right", va="top", fontsize=14, weight="bold", color=color1)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="#0d1117", dpi=80)
        plt.close(fig)
        buf.seek(0)
        return ft.Image(content=buf, width=600, height=200)

    def render(self):
        """Create all chart widgets for the dashboard."""
        cpu_b = self.collector.history.get("cpu_usage")
        ram_b = self.collector.history.get("ram_percent")
        gpu_b = self.collector.history.get("gpu_temp")

        c1 = _panel("CPU", ft.icons.celular_x_terminal,
                     self._line_img(list(cpu_b), "CPU Usage (%)", *COL["cpu"], "CPU") if cpu_b else ft.Text("N/A", color="white70"),
                     COL["cpu"][0])
        c2 = _panel("RAM", ft.icons.memory,
                     self._line_img(list(ram_b) if ram_b else [], "RAM Usage (%)", *COL["ram"], "RAM"),
                     COL["ram"][0])
        c3 = _panel("GPU TEMP", ft.icons.thermostat,
                     self._line_img(list(gpu_b) if gpu_b else [], "GPU Temperature (°C)", *COL["gpu"], "GPU"),
                     COL["gpu"][0])
        return [c1, c2, c3]
