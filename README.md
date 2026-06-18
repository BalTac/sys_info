# ⚡ sys_info — AI System Dashboard

Real-time hardware monitoring dashboard in three flavors: slick terminal UI, Flet desktop GUI, and matplotlib-based technical view.

![GUI Dashboard](resources/gui_dashboard.png)

## Features

- **CPU** — per-core load bars, average %, frequency
- **RAM** — usage %, used/total GB, swap
- **GPU** (NVIDIA) — temperature, load, VRAM, power draw, fan speed, running processes
- **Disks** — per-partition usage bars
- **Network** — real-time up/down throughput (KB/s)
- **Live charts** — configurable time window (1m / 2m / 5m / all) with CPU, RAM, GPU, Network history
- **Alert thresholds** — CPU warn 80%, RAM warn 80%, GPU temp warn 75°C / danger 85°C

## Screens

| Mode | File | Tech | Vibe |
|------|------|------|------|
| Terminal | `main.py` | [Rich](https://github.com/Textualize/rich) | Cyberpunk terminal chic |
| GUI | `main_flet.py` | [Flet](https://flet.dev) | Dark neon desktop app |
| Technical | `main_graph.py` | Matplotlib + LibreHardwareMonitor | Full-sensor plotting |

![Terminal Dashboard](resources/cli_dashboard.png)

## Quick Start

```bash
# Create venv
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/macOS

# Install
pip install -r requirements.txt

# Run
python main.py                # Rich terminal dashboard
python main_flet.py           # Flet desktop GUI
python main_graph.py          # Matplotlib+LHM technical view
```

Or use the batch files:
```
run_dashboard.bat      →  main.py
run_flet.bat           →  main_flet.py
run_tesla_panel.bat    →  main_graph.py
```

## Requirements

```
rich>=13
psutil>=5.9
pynvml>=11.5
flet>=0.23
matplotlib>=3.7
keyboard>=0.13
```

## Project Structure

```
sys_info/
├── main.py              # Rich terminal dashboard
├── main_flet.py         # Flet GUI entry point
├── main_graph.py        # Matplotlib Tesla Monitor
├── dashboard.py         # Flet Dashboard class
├── data_collector.py    # psutil + pynvml data layer
├── charts.py            # Matplotlib chart renderers
├── config.py            # Theme & config loader
├── config.json          # Thresholds & defaults
├── panels/              # Modular dashboard panels
│   ├── cpu_panel.py
│   ├── ram_panel.py
│   ├── gpu_panel.py
│   ├── disk_panel.py
│   ├── network_panel.py
│   ├── charts_panel.py
│   └── utils.py
├── lhm/                 # LibreHardwareMonitor (external .NET app)
└── resources/           # Screenshots
```

## Configuration

Edit `config.json`:
```json
{
  "refresh_ms": 1000,
  "history_points": 60,
  "chart_refresh_s": 3,
  "thresholds": {
    "cpu_warn": 80,
    "ram_warn": 80,
    "gpu_temp_warn": 75,
    "gpu_temp_danger": 85
  }
}
```

## License

MIT
