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

# Per-GPU palette for multi-GPU charts (each GPU gets its own color)
GPU_CHART_PALETTE = ["#ffaa00", "#00d4ff", "#00ff88", "#f857a6", "#b388ff", "#18ffff"]


def _as_series_list(value):
    """Normalize GPU history to a list of per-GPU lists.

    Handles both the legacy flat list (single GPU) and the per-GPU
    list-of-lists produced by ``DataCollector`` for multi-GPU systems.
    """
    if not value:
        return []
    if isinstance(value[0], (list, tuple)):
        return [list(s) for s in value]
    return [list(value)]


def _pad_series(series, length):
    """Pad/trim a series so it always matches the time-axis length."""
    if not series:
        return [0.0] * length
    series = list(series)
    if len(series) < length:
        series = series + [series[-1]] * (length - len(series))
    return series[:length]


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


def gpu_chart(history: dict, gpu_index: int | None = None, gpu_names: list[str] | None = None) -> bytes:
    """GPU temp + load dual-axis chart (supports multiple GPUs).

    - ``gpu_index``: ``None`` -> plot every GPU series (each on its own color);
      an ``int`` -> plot only that GPU.
    - ``gpu_names``: optional display names per GPU, used in the legend.
    """
    fig, ax1 = plt.subplots(figsize=(8, 4.6))
    t = history.get("times", [])
    temps = _as_series_list(history.get("gpu_temp", []))
    loads = _as_series_list(history.get("gpu_load", []))
    if gpu_names is None:
        gpu_names = []

    # Restrict to the requested GPU if a specific index was selected
    if gpu_index is not None and 0 <= gpu_index < len(temps):
        temps = [temps[gpu_index]]
        loads = [loads[gpu_index]] if gpu_index < len(loads) else [[]]
        gpu_names = [gpu_names[gpu_index]] if gpu_index < len(gpu_names) else [f"GPU {gpu_index}"]

    if not t or not temps or all(not s for s in temps):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=80, facecolor="none", transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    t0 = t[0]
    rel_t = [x - t0 for x in t]
    multi = len(temps) > 1

    pt = len(rel_t)
    ax2 = ax1.twinx()
    for idx in range(max(len(temps), len(loads))):
        color = GPU_CHART_PALETTE[idx % len(GPU_CHART_PALETTE)]
        name = gpu_names[idx] if idx < len(gpu_names) else f"GPU {idx}"
        temp_label = f"{name} Temp" if multi else "Temp °C"
        load_label = f"{name} Load" if multi else "Load %"

        temp = _pad_series(temps[idx] if idx < len(temps) else [], pt)
        load = _pad_series(loads[idx] if idx < len(loads) else [], pt)

        # Temperature (solid, left axis)
        ax1.fill_between(rel_t, temp, alpha=0.10, color=color)
        ax1.plot(rel_t, temp, color=color, linewidth=5, alpha=0.15)
        ax1.plot(rel_t, temp, color=color, linewidth=3, alpha=0.30)
        ax1.plot(rel_t, temp, color=color, linewidth=1.5, alpha=1.0, label=temp_label)

        # Load (dashed, right axis)
        ax2.plot(rel_t, load, color=color, linewidth=4, alpha=0.15, linestyle="--")
        ax2.plot(rel_t, load, color=color, linewidth=2.5, alpha=0.30, linestyle="--")
        ax2.plot(rel_t, load, color=color, linewidth=1.2, alpha=1.0, linestyle="--", label=load_label)

    ax1.set_title("GPU Temp + Load", color=WHITE, fontsize=10)
    ax1.set_ylabel("°C", color=ORANGE, fontsize=8)
    ax1.tick_params(colors="#888888", labelsize=8)
    ax1.grid(True, color="#332255", alpha=0.25)

    ax2.set_ylabel("%", color=GREEN, fontsize=8)
    ax2.tick_params(colors="#888888", labelsize=8)

    # Legend only when multiple series are shown, to avoid clutter
    if multi:
        handles = ax1.get_legend_handles_labels()
        handles2 = ax2.get_legend_handles_labels()
        ax1.legend(handles[0] + handles2[0], handles[1] + handles2[1],
                   fontsize=8, loc="upper left", facecolor="#100b1a", edgecolor="#332255")

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
