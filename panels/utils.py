"""Helper utilities for panels (progress bars, labels, formatting)."""

import flet as ft


def format_bytes(b):
    """Format bytes to readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:,.1f} {unit}"
        b /= 1024
    return f"{b:,.1f} PB"


def make_label(text, color=None):
    return ft.Text(text, color=color or ft.colors.WHITE, size=10)


def make_value(text, color=None, size=36, weight="bold"):
    return ft.Text(text, color=color or ft.colors.WHITE, size=size, weight=weight)


def make_panel_card(title, icon, content, color, surface="#161b22", border_color="#30363d"):
    return ft.Container(
        content=ft.Column(
            [
                ft.Row([ft.Icon(icon, color=color, size=18), make_label(title, ft.colors.WHITE70)],
                       horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(height=1, color=border_color),
                ft.Container(content=content, padding=10),
            ],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.START,
            expand=False,
        ),
        padding=12,
        border_radius=16,
        bgcolor=surface,
        border=ft.border.all(width=1, color=border_color),
        shadow=ft.BoxShadow(blur_radius=10, color="#00000040", spread_radius=2),
        expand=False,
    )
