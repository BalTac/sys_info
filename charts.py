#!/usr/bin/env python3
"""Render matplotlib charts → bytes for Flet ft.Image widgets."""

import io
from collections import deque
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

plt.style.use("dark_background")
ACCENT = "#00d4ff"
GREEN = "#00ff88"
ORANGE = "#ffaa00"
MAGENTA = "#ff00ff"
WHITE = "#e0e0e0"


def _fig_to_bytes(fig: plt.Figure, dpi: int = 80) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="none", edgecolor="none", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def cpu_chart(history: dict) -> bytes:
    """CPU usage line chart."""
    fig, ax = plt.subplots(figsize=(8, 3))
    t = history.get("times", [])
    cpu = history.get("cpu", [])
    if not t or not cpu:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=80, facecolor="none", transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    t0 = t[0]
    rel_t = [x - t0 for x in t]
    ax.fill_between(rel_t, cpu, alpha=0.1, color=ACCENT)
    ax.plot(rel_t, cpu, color=ACCENT, linewidth=5, alpha=0.15)
    ax.plot(rel_t, cpu, color=ACCENT, linewidth=3, alpha=0.30)
    ax.plot(rel_t, cpu, color=ACCENT, linewidth=1.5, alpha=1.0)
    ax.set_title("CPU Usage %", color=WHITE, fontsize=10)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.tick_params(colors="#888888", labelsize=8)
    ax.grid(True, color="#332255", alpha=0.25)
    return _fig_to_bytes(fig)


def ram_chart(history: dict) -> bytes:
    """RAM usage line chart."""
    fig, ax = plt.subplots(figsize=(8, 3))
    t = history.get("times", [])
    ram = history.get("ram", [])
    if not t or not ram:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=80, facecolor="none", transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    t0 = t[0]
    rel_t = [x - t0 for x in t]
    ax.fill_between(rel_t, ram, alpha=0.1, color=MAGENTA)
    ax.plot(rel_t, ram, color=MAGENTA, linewidth=5, alpha=0.15)
    ax.plot(rel_t, ram, color=MAGENTA, linewidth=3, alpha=0.30)
    ax.plot(rel_t, ram, color=MAGENTA, linewidth=1.5, alpha=1.0)
    ax.set_title("RAM Usage %", color=WHITE, fontsize=10)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_locator(MaxNLocator(5))
    ax.tick_params(colors="#888888", labelsize=8)
    ax.grid(True, color="#332255", alpha=0.25)
    return _fig_to_bytes(fig)


def gpu_chart(history: dict) -> bytes:
    """GPU temp + load dual-axis chart."""
    fig, ax1 = plt.subplots(figsize=(8, 3))
    t = history.get("times", [])
    temps = history.get("gpu_temp", [])
    loads = history.get("gpu_load", [])
    if not t or not temps:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=80, facecolor="none", transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    t0 = t[0]
    rel_t = [x - t0 for x in t]
    ax1.fill_between(rel_t, temps, alpha=0.1, color=ORANGE)
    ax1.plot(rel_t, temps, color=ORANGE, linewidth=5, alpha=0.15)
    ax1.plot(rel_t, temps, color=ORANGE, linewidth=3, alpha=0.30)
    ax1.plot(rel_t, temps, color=ORANGE, linewidth=1.5, alpha=1.0, label="Temp °C")
    ax1.set_title("GPU Temp + Load", color=WHITE, fontsize=10)
    ax1.set_ylabel("°C", color=ORANGE, fontsize=8)
    ax1.tick_params(colors="#888888", labelsize=8)
    ax1.grid(True, color="#332255", alpha=0.25)

    ax2 = ax1.twinx()
    ax2.plot(rel_t, loads, color=GREEN, linewidth=4, alpha=0.15, linestyle="--")
    ax2.plot(rel_t, loads, color=GREEN, linewidth=2.5, alpha=0.30, linestyle="--")
    ax2.plot(rel_t, loads, color=GREEN, linewidth=1.2, alpha=1.0, linestyle="--", label="Load %")
    ax2.set_ylabel("%", color=GREEN, fontsize=8)
    ax2.tick_params(colors="#888888", labelsize=8)

    return _fig_to_bytes(fig)


def net_chart(history: dict) -> bytes:
    """Network throughput chart."""
    fig, ax = plt.subplots(figsize=(8, 3))
    t = history.get("times", [])
    up = history.get("net_up", [])
    down = history.get("net_down", [])
    if not t:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=80, facecolor="none", transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    t0 = t[0]
    rel_t = [x - t0 for x in t]
    ax.fill_between(rel_t, down, alpha=0.1, color=GREEN)
    ax.plot(rel_t, down, color=GREEN, linewidth=4, alpha=0.15)
    ax.plot(rel_t, down, color=GREEN, linewidth=2.5, alpha=0.30)
    ax.plot(rel_t, down, color=GREEN, linewidth=1.2, alpha=1.0, label="Down KB/s")
    
    ax.plot(rel_t, up, color=ACCENT, linewidth=4, alpha=0.15)
    ax.plot(rel_t, up, color=ACCENT, linewidth=2.5, alpha=0.30)
    ax.plot(rel_t, up, color=ACCENT, linewidth=1.2, alpha=1.0, label="Up KB/s")
    ax.set_title("Network Throughput", color=WHITE, fontsize=10)
    ax.tick_params(colors="#888888", labelsize=8)
    ax.grid(True, color="#332255", alpha=0.25)
    ax.legend(fontsize=7, facecolor="#100b1a", edgecolor="#332255")
    return _fig_to_bytes(fig)
