#!/usr/bin/env python3
"""
⚡ AI System Dashboard — Rich terminal UI with live bars and panels.
NVIDIA GPU monitoring on Windows. Premium terminal dashboard style.
"""

import os
import sys
import time
import psutil
import platform
from datetime import datetime

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.bar import Bar
from rich.columns import Columns
from rich import box

try:
    import pynvml
    pynvml.nvmlInit()
    NVIDIA_AVAILABLE = True
except (ImportError, pynvml.NVMLError):
    NVIDIA_AVAILABLE = False

console = Console()

# ─── Color Palette ───────────────────────────────────────────────────────────
ACCENT      = "cyan"
ACCENT2     = "magenta"
GOOD        = "green"
WARN        = "yellow"
DANGER      = "red"
DIM         = "bright_black"
TITLE_STYLE = "bold bright_white"
LABEL_STYLE = "bright_white"
VALUE_STYLE = "bold cyan"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def pct_color(pct: float) -> str:
    """Return a Rich color string based on percentage severity."""
    if pct < 50:
        return GOOD
    elif pct < 80:
        return WARN
    return DANGER


def make_bar(label: str, pct: float, width: int = 30, show_val: str | None = None) -> Text:
    """Create a stylish text-based progress bar with color gradient."""
    filled = int(width * pct / 100)
    empty = width - filled
    color = pct_color(pct)

    bar_text = Text()
    bar_text.append(f"  {label:<12} ", style=LABEL_STYLE)
    bar_text.append("▐", style=DIM)
    bar_text.append("█" * filled, style=f"bold {color}")
    bar_text.append("░" * empty, style=DIM)
    bar_text.append("▌", style=DIM)
    if show_val:
        bar_text.append(f" {show_val}", style=f"bold {color}")
    else:
        bar_text.append(f" {pct:5.1f}%", style=f"bold {color}")
    return bar_text


def temp_color(temp: int) -> str:
    """Color based on GPU temperature."""
    if temp < 50:
        return GOOD
    elif temp < 75:
        return WARN
    return DANGER


# ─── Data Collection ─────────────────────────────────────────────────────────

def collect_system_info() -> dict:
    """Collect all system metrics in one call."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu_pcts = psutil.cpu_percent(interval=0.3, percpu=True)
    cpu_avg = sum(cpu_pcts) / len(cpu_pcts) if cpu_pcts else 0
    freq = psutil.cpu_freq()

    return {
        "cpu_pcts": cpu_pcts,
        "cpu_avg": cpu_avg,
        "cpu_freq": freq.current if freq else 0,
        "cpu_count": os.cpu_count(),
        "ram_total_gb": mem.total / (1024 ** 3),
        "ram_used_gb": mem.used / (1024 ** 3),
        "ram_pct": mem.percent,
        "swap_total_gb": swap.total / (1024 ** 3),
        "swap_used_gb": swap.used / (1024 ** 3),
        "swap_pct": swap.percent,
    }


def collect_gpu_info() -> list[dict]:
    """Collect NVIDIA GPU metrics."""
    if not NVIDIA_AVAILABLE:
        return []
    gpus = []
    try:
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="ignore")
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
            power = pynvml.nvmlDeviceGetPowerUsage(h) / 1000
            try:
                power_limit = pynvml.nvmlDeviceGetPowerManagementLimit(h) / 1000
            except pynvml.NVMLError:
                power_limit = None
            try:
                fan = pynvml.nvmlDeviceGetFanSpeed(h)
            except pynvml.NVMLError:
                fan = None

            vram_total_gb = mem.total / (1024 ** 3)
            vram_used_gb = mem.used / (1024 ** 3)
            vram_pct = (mem.used / mem.total * 100) if mem.total > 0 else 0

            # Query running processes using GPU memory
            processes = []
            try:
                funcs = [pynvml.nvmlDeviceGetComputeRunningProcesses, pynvml.nvmlDeviceGetGraphicsRunningProcesses]
                seen_pids = set()
                for func in funcs:
                    try:
                        for p in func(h):
                            if p.pid not in seen_pids:
                                seen_pids.add(p.pid)
                                try:
                                    proc = psutil.Process(p.pid)
                                    pname = proc.name()
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pname = "Unknown"
                                vram_mb = (p.usedGpuMemory or 0) / (1024 ** 2)
                                processes.append({
                                    "pid": p.pid,
                                    "name": pname,
                                    "vram_mb": vram_mb
                                })
                    except pynvml.NVMLError:
                        pass
            except Exception:
                pass

            gpus.append({
                "name": name,
                "vram_total_gb": vram_total_gb,
                "vram_used_gb": vram_used_gb,
                "vram_pct": vram_pct,
                "gpu_util": util.gpu,
                "mem_util": util.memory,
                "temp": temp,
                "power": power,
                "power_limit": power_limit,
                "fan": fan,
                "processes": processes,
            })
    except Exception as e:
        console.print(f"[red][!] GPU error: {e}[/red]", highlight=False)
    return gpus


# ─── Panel Renderers ─────────────────────────────────────────────────────────

def render_header_panel(now: datetime) -> Panel:
    """Top header with system info and timestamp."""
    hostname = platform.node()
    os_info = f"{platform.system()} {platform.release()}"
    py_ver = platform.python_version()
    uptime_sec = time.time() - psutil.boot_time()
    days, rem = divmod(int(uptime_sec), 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    uptime_str = f"{days}d {hours}h {mins}m" if days else f"{hours}h {mins}m"

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1, justify="right")

    left = Text()
    left.append("  ⚡ AI System Dashboard\n", style="bold bright_cyan")
    left.append(f"  🖥  {hostname}", style=LABEL_STYLE)
    left.append(f"  •  {os_info}", style=DIM)
    left.append(f"  •  Python {py_ver}", style=DIM)

    right = Text()
    right.append(f"🕐 {now.strftime('%H:%M:%S')}  ", style="bold bright_white")
    right.append(f"\n⏱  Uptime: {uptime_str}  ", style=DIM)

    grid.add_row(left, right)

    return Panel(
        grid,
        border_style="bright_cyan",
        box=box.DOUBLE_EDGE,
        padding=(0, 1),
    )


def render_cpu_panel(info: dict) -> Panel:
    """CPU panel with per-core bars."""
    lines = []

    # Summary line
    summary = Text()
    summary.append(f"  Cores: ", style=LABEL_STYLE)
    summary.append(f"{info['cpu_count']}", style=VALUE_STYLE)
    summary.append(f"   Frequency: ", style=LABEL_STYLE)
    summary.append(f"{info['cpu_freq']:.0f} MHz", style=VALUE_STYLE)
    summary.append(f"   Average: ", style=LABEL_STYLE)
    avg_col = pct_color(info['cpu_avg'])
    summary.append(f"{info['cpu_avg']:.1f}%", style=f"bold {avg_col}")
    lines.append(summary)
    lines.append(Text())

    # Average bar
    lines.append(make_bar("AVG", info["cpu_avg"], width=18))
    lines.append(Text())

    # Per-core bars (2 columns)
    core_bars_left = []
    core_bars_right = []
    for i, pct in enumerate(info["cpu_pcts"]):
        bar = make_bar(f"Core {i}", pct, width=10)
        if i % 2 == 0:
            core_bars_left.append(bar)
        else:
            core_bars_right.append(bar)

    # Merge into a table for 2-col layout
    core_table = Table.grid(expand=True)
    core_table.add_column(ratio=1)
    core_table.add_column(ratio=1)
    max_rows = max(len(core_bars_left), len(core_bars_right))
    for r in range(max_rows):
        left = core_bars_left[r] if r < len(core_bars_left) else Text("")
        right = core_bars_right[r] if r < len(core_bars_right) else Text("")
        core_table.add_row(left, right)

    group = Text("\n").join(lines)

    # Build final content
    final_table = Table.grid(expand=True)
    final_table.add_column()
    final_table.add_row(group)
    final_table.add_row(core_table)

    return Panel(
        final_table,
        title="[bold bright_white]🧠 CPU[/]",
        title_align="left",
        border_style="bright_blue",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def render_ram_panel(info: dict) -> Panel:
    """RAM + Swap panel with bars."""
    lines = []

    # RAM bar
    ram_val = f"{info['ram_used_gb']:.2f} / {info['ram_total_gb']:.1f} GB ({info['ram_pct']:.1f}%)"
    lines.append(make_bar("RAM", info["ram_pct"], width=18, show_val=ram_val))
    lines.append(Text())

    # Swap bar
    swap_val = f"{info['swap_used_gb']:.2f} / {info['swap_total_gb']:.1f} GB ({info['swap_pct']:.1f}%)"
    lines.append(make_bar("Swap", info["swap_pct"], width=18, show_val=swap_val))

    content = Text("\n").join(lines)

    return Panel(
        content,
        title="[bold bright_white]💾 Memory[/]",
        title_align="left",
        border_style="bright_magenta",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def render_gpu_panel(gpus: list[dict]) -> Panel:
    """GPU panel with VRAM bar, utilization bar, temperature, power, and active processes side-by-side."""
    if not gpus:
        content = Text("  ⚠️  No NVIDIA GPU detected", style="yellow italic")
        return Panel(
            content,
            title="[bold bright_white]🎮 GPU[/]",
            title_align="left",
            border_style="bright_green",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    gpu_status_elements = []
    all_processes = []
    
    for i, gpu in enumerate(gpus):
        gpu_elements = []

        # GPU name header
        name_text = Text()
        name_text.append(f"  🔲 GPU {i}: ", style=LABEL_STYLE)
        name_text.append(gpu["name"], style="bold bright_cyan")
        gpu_elements.append(name_text)
        gpu_elements.append(Text())

        # VRAM bar
        vram_val = f"{gpu['vram_used_gb']:.2f} / {gpu['vram_total_gb']:.2f} GB ({gpu['vram_pct']:.1f}%)"
        gpu_elements.append(make_bar("VRAM", gpu["vram_pct"], width=15, show_val=vram_val))

        # GPU Utilization bar
        gpu_elements.append(make_bar("GPU Load", gpu["gpu_util"], width=15))

        # Memory bandwidth utilization
        gpu_elements.append(make_bar("Mem B/W", gpu["mem_util"], width=15))
        gpu_elements.append(Text())

        # Temperature + Power + Fan in a row
        stats = Text()
        t_col = temp_color(gpu["temp"])
        stats.append(f"  🌡  Temp: ", style=LABEL_STYLE)
        stats.append(f"{gpu['temp']}°C", style=f"bold {t_col}")

        stats.append(f"    ⚡ Power: ", style=LABEL_STYLE)
        if gpu["power_limit"]:
            pwr_pct = (gpu["power"] / gpu["power_limit"]) * 100
            pwr_col = pct_color(pwr_pct)
            stats.append(f"{gpu['power']:.0f} / {gpu['power_limit']:.0f} W", style=f"bold {pwr_col}")
        else:
            stats.append(f"{gpu['power']:.1f} W", style=VALUE_STYLE)

        if gpu["fan"] is not None:
            stats.append(f"    🌀 Fan: ", style=LABEL_STYLE)
            fan_col = pct_color(gpu["fan"])
            stats.append(f"{gpu['fan']}%", style=f"bold {fan_col}")

        gpu_elements.append(stats)
        gpu_status_elements.append(Group(*gpu_elements))

        # Accumulate processes across all GPUs
        if gpu.get("processes"):
            for p in gpu["processes"]:
                all_processes.append({
                    "gpu_idx": i,
                    "pid": p["pid"],
                    "name": p["name"],
                    "vram_mb": p["vram_mb"]
                })

    # Left column: GPU stats stacked vertically
    left_grid = Table.grid(expand=True)
    left_grid.add_column()
    for idx, r in enumerate(gpu_status_elements):
        if idx > 0:
            left_grid.add_row(Text("\n"))
        left_grid.add_row(r)

    # Right column: Active processes table if any exist
    if all_processes:
        proc_table = Table(
            box=box.SIMPLE_HEAD,
            border_style=DIM,
            show_header=True,
            header_style="bold bright_cyan",
            padding=(0, 1),
            expand=True
        )
        proc_table.add_column("GPU", justify="center", style="bold cyan", no_wrap=True)
        proc_table.add_column("PID", justify="right", style=DIM, no_wrap=True)
        proc_table.add_column("Process Name", style=LABEL_STYLE, max_width=15, overflow="ellipsis")
        proc_table.add_column("VRAM Usage", justify="right", style="bold magenta", no_wrap=True)

        # Custom sorting key:
        # Prioritize: 1st if active VRAM or is Ollama/Llama process, 2nd by actual VRAM amount, 3rd if Ollama
        def sort_key(p):
            name_lower = p["name"].lower()
            is_ai = "ollama" in name_lower or "llama" in name_lower
            has_vram = p["vram_mb"] > 0
            return (has_vram or is_ai, p["vram_mb"], is_ai)

        sorted_procs = sorted(all_processes, key=sort_key, reverse=True)
        
        # Limit to top 10 to keep dashboard compact
        displayed_procs = sorted_procs[:10]
        for p in displayed_procs:
            vram_str = f"{p['vram_mb']:.1f} MB" if p["vram_mb"] > 0 else "N/A"
            proc_table.add_row(f"GPU {p['gpu_idx']}", str(p["pid"]), p["name"], vram_str)

        if len(sorted_procs) > 10:
            proc_table.add_row("", "", f"...and {len(sorted_procs) - 10} more", "")

        # Wrap in a neat Panel
        proc_panel = Panel(
            proc_table,
            title="[bold bright_white]📊 Active GPU Processes[/]",
            title_align="left",
            border_style=DIM,
            box=box.ROUNDED,
            padding=(0, 1)
        )

        # Master grid with 2 columns: GPU status and active processes side-by-side
        master_grid = Table.grid(expand=True)
        master_grid.add_column(ratio=5)
        master_grid.add_column(ratio=3)
        master_grid.add_row(left_grid, proc_panel)
        content = master_grid
    else:
        content = left_grid

    return Panel(
        content,
        title="[bold bright_white]🎮 NVIDIA GPU[/]",
        title_align="left",
        border_style="bright_green",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def render_disk_panel() -> Panel:
    """Quick disk usage overview."""
    lines = []
    partitions = psutil.disk_partitions(all=False)
    for part in partitions:
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        pct = usage.percent
        label = part.mountpoint[:10]
        val = f"{used_gb:.1f} / {total_gb:.1f} GB ({pct:.0f}%)"
        lines.append(make_bar(label, pct, width=15, show_val=val))

    if not lines:
        lines.append(Text("  No disks found", style="yellow italic"))

    content = Text("\n").join(lines)

    return Panel(
        content,
        title="[bold bright_white]💿 Disks[/]",
        title_align="left",
        border_style="bright_yellow",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def render_network_panel() -> Panel:
    """Network I/O snapshot."""
    net = psutil.net_io_counters()
    sent_mb = net.bytes_sent / (1024 ** 2)
    recv_mb = net.bytes_recv / (1024 ** 2)

    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    sent_text = Text()
    sent_text.append("  ⬆ Sent: ", style=LABEL_STYLE)
    sent_text.append(f"{sent_mb:.1f} MB", style="bold bright_cyan")

    recv_text = Text()
    recv_text.append("  ⬇ Recv: ", style=LABEL_STYLE)
    recv_text.append(f"{recv_mb:.1f} MB", style="bold bright_green")

    grid.add_row(sent_text, recv_text)

    return Panel(
        grid,
        title="[bold bright_white]🌐 Network[/]",
        title_align="left",
        border_style="bright_red",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def render_footer() -> Text:
    """Footer hint."""
    footer = Text()
    footer.append("  Press ", style=DIM)
    footer.append("Ctrl+C", style="bold bright_white")
    footer.append(" to exit", style=DIM)
    footer.append("  │  ", style=DIM)
    footer.append("⚡ Powered by Rich + psutil + pynvml", style=DIM)
    return footer


# ─── Dashboard Assembly ──────────────────────────────────────────────────────

def build_dashboard() -> Table:
    """Build the complete dashboard as a Rich renderable."""
    now = datetime.now()
    sys_info = collect_system_info()
    gpus = collect_gpu_info()

    # Master table for vertical stacking
    master = Table.grid(expand=True)
    master.add_column()

    # Header
    master.add_row(render_header_panel(now))

    # CPU + RAM side by side
    cpu_ram = Table.grid(expand=True)
    cpu_ram.add_column(ratio=3)
    cpu_ram.add_column(ratio=2)
    cpu_ram.add_row(render_cpu_panel(sys_info), render_ram_panel(sys_info))
    master.add_row(cpu_ram)

    # GPU (full width)
    master.add_row(render_gpu_panel(gpus))

    # Disk + Network side by side
    bottom_row = Table.grid(expand=True)
    bottom_row.add_column(ratio=1)
    bottom_row.add_column(ratio=1)
    bottom_row.add_row(render_disk_panel(), render_network_panel())
    master.add_row(bottom_row)

    # Footer
    master.add_row(render_footer())

    return master


# ─── Main Loop ───────────────────────────────────────────────────────────────

def main(interval: float = 1.0):
    """Run the live dashboard."""
    # Invia la sequenza di escape VT per ridimensionare la finestra a 110 colonne e 48 righe
    sys.stdout.write("\x1b[8;48;150t")
    sys.stdout.flush()
    time.sleep(0.15)  # Piccolo delay per dare tempo al terminale di ridimensionarsi
    console.clear()
    try:
        with Live(
            build_dashboard(),
            console=console,
            refresh_per_second=4,
            screen=True,
            transient=False,
        ) as live:
            while True:
                live.update(build_dashboard())
                time.sleep(interval)
    except KeyboardInterrupt:
        console.clear()
        console.print("\n[bold bright_cyan]📊 Dashboard closed.[/bold bright_cyan]\n")
    finally:
        if NVIDIA_AVAILABLE:
            pynvml.nvmlShutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="⚡ AI System Dashboard")
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=1.0,
        help="Update interval in seconds (default: 1.0)",
    )
    args = parser.parse_args()
    main(args.interval)
