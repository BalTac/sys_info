#!/usr/bin/env python3
"""Entry point — launches Flet system dashboard."""

import flet as ft
from dashboard import Dashboard


def main(page: ft.Page):
    dash = Dashboard(page)
    dash.build()


if __name__ == "__main__":
    ft.run(main)
