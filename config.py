"""Configuration and theming constants."""

import json
import os

__version__ = "0.1.0"
__author__ = "BalTac"
__repo__ = "https://github.com/BalTac/sys_info"

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    """Load config.json from project root."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()

# Theme colors
BG_COLOR = "#0d1117"
SURFACE_COLOR = "#161b22"
BORDER_COLOR = "#30363d"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"

# Panel accent colors
CPU_COLOR = "#238636"
CPU_ALT = "#3fb950"
RAM_COLOR = "#1f6feb"
RAM_ALT = "#58a6ff"
GPU_COLOR = "#d29922"
GPU_ALT = "#f2a93a"
DISK_COLOR = "#8957e5"
DISK_ALT = "#bc8cff"
NETWORK_COLOR = "#39d353"
NETWORK_ALT = "#7ee787"
ALERT_COLOR = "#da3633"

# Defaults (keys mirror config.json)
REFRESH_RATE = CONFIG.get("refresh_ms", 1000)
HISTORY_LENGTH = CONFIG.get("history_points", 60)
THRESHOLDS = CONFIG.get("thresholds", {
    "cpu_warn": 80,
    "ram_warn": 80,
    "gpu_temp_warn": 75,
    "gpu_temp_danger": 85
})
