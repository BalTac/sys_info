#!/usr/bin/env python3
"""Data collector: psutil + pynvml → snapshot dict + historical deques."""

import os
import time
import threading
from collections import deque
from dataclasses import dataclass, field

import psutil

from ai_detector import detect_ai_inference

try:
    import pynvml
    pynvml.nvmlInit()
    NVIDIA = True
except Exception:
    NVIDIA = False

CFG = {
    "history_points": 60,
    "refresh_ms": 1000,
    "chart_refresh_s": 3,
    "thresholds": {"cpu_warn": 80, "ram_warn": 80, "gpu_temp_warn": 75, "gpu_temp_danger": 85},
}
try:
    import json
    with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as fh:
        CFG |= json.load(fh)
except Exception:
    pass


try:
    import json
    with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as fh:
        CFG |= json.load(fh)
except Exception:
    pass

# ─── Power: CPU TDP detection (for the estimate fallback) ─────────────────────

# Curated map used only when config.json leaves power.cpu_tdp_w as null.
# Keys are matched (case-insensitively) against the real CPU model string.
_TDP_MAP = (
    ("i9-", 125.0), ("i7-", 95.0), ("i5-", 65.0), ("i3-", 60.0),
    ("ryzen 9", 105.0), ("ryzen 7", 95.0), ("ryzen 5", 65.0), ("ryzen 3", 65.0),
    ("threadripper", 180.0),
)
_DEFAULT_TDP_W = 65.0


def cpu_model_name() -> str:
    """Best-effort human CPU model name (Windows registry, then fallbacks)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            name, _ = winreg.QueryValueEx(k, "ProcessorNameString")
            if name:
                return str(name).strip()
    except Exception:
        pass
    try:
        import platform
        return platform.processor() or ""
    except Exception:
        return ""


def detect_cpu_tdp(cpu_name: str | None = None) -> float:
    """Return a TDP estimate in watts for the given (or detected) CPU model."""
    name = (cpu_name if cpu_name is not None else cpu_model_name()).lower()
    for needle, tdp in _TDP_MAP:
        if needle in name:
            return tdp
    return _DEFAULT_TDP_W


@dataclass
class Snapshot:
    ts: float = field(default_factory=time.time)
    cpu_avg: float = 0
    cpu_per_core: list[float] = field(default_factory=list)
    cpu_freq: float = 0
    cpu_count: int = 0
    ram_total_gb: float = 0
    ram_used_gb: float = 0
    ram_pct: float = 0
    swap_total_gb: float = 0
    swap_used_gb: float = 0
    swap_pct: float = 0
    disks: list[dict] = field(default_factory=list)
    net_sent_kbps: float = 0
    net_recv_kbps: float = 0
    gpus: list[dict] = field(default_factory=list)
    ai_engines: list[dict] = field(default_factory=list)
    cpu_power_w: float = 0
    cpu_power_source: str = "none"   # "lhm" | "estimate" | "none"
    cpu_tdp_w: float = 0
    total_power_w: float = 0

    @property
    def cpu_pcts(self) -> list[float]:
        return self.cpu_per_core

    def __getitem__(self, key: str):
        return getattr(self, key)


class DataCollector:
    """Thread-safe collector with rolling history for charts."""

    def __init__(self):
        self._lock = threading.Lock()
        self.snapshot = Snapshot()
        self._last_net = None
        self._last_net_ts = time.time()

        # History deques for charts
        n = CFG["history_points"]
        self.h_cpu: deque[float] = deque(maxlen=n)
        self.h_ram: deque[float] = deque(maxlen=n)
        # Per-GPU history: one deque per GPU index (multi-GPU support)
        self.h_gpu_temp: list[deque[float]] = []
        self.h_gpu_load: list[deque[float]] = []
        self.h_net_up: deque[float] = deque(maxlen=n)
        self.h_net_down: deque[float] = deque(maxlen=n)
        self.h_cpu_power: deque[float] = deque(maxlen=n)
        self.h_total_power: deque[float] = deque(maxlen=n)
        self.h_times: deque[float] = deque(maxlen=n)

        # Power: TDP + optional real CPU power via LibreHardwareMonitor (.NET)
        power_cfg = CFG.get("power", {}) or {}
        self.cpu_tdp_w = power_cfg.get("cpu_tdp_w") or detect_cpu_tdp()
        self.platform_w = float(power_cfg.get("platform_estimate_w") or 0)
        self._lhm_enabled = bool(power_cfg.get("lhm_enabled", True))
        self._lhm_state = "unloaded"   # unloaded | ok | disabled
        self._lhm_computer = None
        self._lhm_cpu = None

    # ── CPU power via LibreHardwareMonitor (real MSR/RAPL reading) ──────────

    def _init_lhm_power(self) -> None:
        """Lazily open LHM CPU power sensors. Never raises; disables on failure."""
        if self._lhm_state != "unloaded":
            return
        self._lhm_state = "disabled"
        if not self._lhm_enabled:
            return
        try:
            import clr  # pythonnet
            dll = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "lhm", "LibreHardwareMonitorLib.dll")
            if not os.path.exists(dll):
                return
            clr.AddReference(dll)
            from LibreHardwareMonitor.Hardware import Computer
            computer = Computer()
            computer.IsCpuEnabled = True
            computer.Open()
            if not computer.Hardware:
                return
            self._lhm_computer = computer
            self._lhm_cpu = computer.Hardware[0]
            self._lhm_state = "ok"
        except Exception:
            self._lhm_state = "disabled"

    def _read_lhm_cpu_power(self) -> float | None:
        """Read CPU Package power in W. Returns None when unavailable/denied.

        LHM reports 0.0 when the process lacks the privileges needed for MSR
        access, so a non-positive reading is treated as 'no real value'.
        """
        if self._lhm_state == "unloaded":
            self._init_lhm_power()
        if self._lhm_state != "ok" or self._lhm_cpu is None:
            return None
        try:
            self._lhm_cpu.Update()
            package = cores = None
            for s in self._lhm_cpu.Sensors:
                if str(s.SensorType) != "Power":
                    continue
                if s.Name == "CPU Package":
                    package = s.Value
                elif s.Name == "CPU Cores":
                    cores = s.Value
            value = package if package is not None else cores
            if value is None or float(value) <= 0:
                return None
            return float(value)
        except Exception:
            self._lhm_state = "disabled"
            return None

    def close(self) -> None:
        """Release the LHM .NET handle (best effort)."""
        if self._lhm_computer is not None:
            try:
                self._lhm_computer.Close()
            except Exception:
                pass
        self._lhm_computer = None
        self._lhm_cpu = None
        self._lhm_state = "disabled"

    def _ensure_gpu_history(self, idx: int) -> None:
        """Create per-GPU history deques up to index `idx` if missing."""
        while len(self.h_gpu_temp) <= idx:
            self.h_gpu_temp.append(deque(maxlen=CFG["history_points"]))
            self.h_gpu_load.append(deque(maxlen=CFG["history_points"]))

    def update(self):
        """Gather all metrics once; call from a background thread."""
        snap = Snapshot()
        snap.cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        snap.cpu_avg = sum(snap.cpu_per_core) / len(snap.cpu_per_core) if snap.cpu_per_core else 0
        freq = psutil.cpu_freq()
        snap.cpu_freq = freq.current if freq else 0
        snap.cpu_count = os.cpu_count() or 0

        mem = psutil.virtual_memory()
        snap.ram_total_gb = mem.total / (1024**3)
        snap.ram_used_gb = mem.used / (1024**3)
        snap.ram_pct = mem.percent

        swap = psutil.swap_memory()
        snap.swap_total_gb = swap.total / (1024**3)
        snap.swap_used_gb = swap.used / (1024**3)
        snap.swap_pct = swap.percent

        # Disks
        snap.disks = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                snap.disks.append({
                    "device": part.device,
                    "mount": part.mountpoint,
                    "total_gb": usage.total / (1024**3),
                    "used_gb": usage.used / (1024**3),
                    "pct": usage.percent,
                })
            except PermissionError:
                pass

        # Network
        net = psutil.net_io_counters()
        now = time.time()
        if self._last_net is not None:
            dt = now - self._last_net_ts
            snap.net_sent_kbps = (net.bytes_sent - self._last_net.bytes_sent) / dt / 1024
            snap.net_recv_kbps = (net.bytes_recv - self._last_net.bytes_recv) / dt / 1024
        self._last_net = net
        self._last_net_ts = now

        # GPU
        snap.gpus = []
        gpu_hist = []  # (idx, temp, load) appended atomically under the lock
        if NVIDIA:
            try:
                for i in range(pynvml.nvmlDeviceGetCount()):
                    h = pynvml.nvmlDeviceGetHandleByIndex(i)
                    name = pynvml.nvmlDeviceGetName(h)
                    if isinstance(name, bytes):
                        name = name.decode()
                    mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                    util = pynvml.nvmlDeviceGetUtilizationRates(h)
                    temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
                    power = pynvml.nvmlDeviceGetPowerUsage(h) / 1000
                    try:
                        power_limit = pynvml.nvmlDeviceGetPowerManagementLimit(h) / 1000
                    except Exception:
                        power_limit = None
                    try:
                        fan = pynvml.nvmlDeviceGetFanSpeed(h)
                    except Exception:
                        fan = None
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

                    snap.gpus.append({
                        "name": name,
                        "vram_total_gb": mem.total / (1024**3),
                        "vram_used_gb": mem.used / (1024**3),
                        "vram_pct": (mem.used / mem.total * 100) if mem.total else 0,
                        "gpu_util": util.gpu,
                        "mem_util": util.memory,
                        "temp": temp,
                        "power": power,
                        "power_limit": power_limit,
                        "fan": fan,
                        "processes": processes,
                    })
                    # Defer per-GPU history to the locked block below (atomic with h_times)
                    gpu_hist.append((i, temp, util.gpu))
            except Exception:
                pass

        # Local AI inference engines (ollama, llama.cpp, LM Studio, ...) — throttled inside
        snap.ai_engines = detect_ai_inference()

        # ── Power: CPU (real via LHM, else estimate) + system total ────────
        snap.cpu_tdp_w = self.cpu_tdp_w
        real_cpu_w = self._read_lhm_cpu_power()
        if real_cpu_w is not None:
            snap.cpu_power_w = real_cpu_w
            snap.cpu_power_source = "lhm"
        else:
            # Model-based estimate: linear in CPU load against the TDP envelope.
            snap.cpu_power_w = (snap.cpu_avg / 100.0) * self.cpu_tdp_w
            snap.cpu_power_source = "estimate" if self.cpu_tdp_w > 0 else "none"

        # Total = CPU + every GPU (NVML, real) + optional documented platform baseline.
        gpu_w = sum(float(g.get("power") or 0) for g in snap.gpus)
        snap.total_power_w = snap.cpu_power_w + gpu_w + self.platform_w

        with self._lock:
            self.snapshot = snap
            self.h_cpu.append(snap.cpu_avg)
            self.h_ram.append(snap.ram_pct)
            self.h_net_up.append(snap.net_sent_kbps)
            self.h_net_down.append(snap.net_recv_kbps)
            self.h_cpu_power.append(snap.cpu_power_w)
            self.h_total_power.append(snap.total_power_w)
            self.h_times.append(now)

            # Multi-GPU history: advance every series atomically with h_times, and
            # drop stale series if the GPU count shrank.
            n = len(snap.gpus)
            self.h_gpu_temp = self.h_gpu_temp[:n]
            self.h_gpu_load = self.h_gpu_load[:n]
            for i, temp, load in gpu_hist:
                self._ensure_gpu_history(i)
                self.h_gpu_temp[i].append(temp)
                self.h_gpu_load[i].append(load)

    def get(self) -> Snapshot:
        with self._lock:
            return self.snapshot

    def history(self):
        with self._lock:
            return {
                "times": list(self.h_times),
                "cpu": list(self.h_cpu),
                "ram": list(self.h_ram),
                "gpu_temp": [list(d) for d in self.h_gpu_temp],
                "gpu_load": [list(d) for d in self.h_gpu_load],
                "net_up": list(self.h_net_up),
                "net_down": list(self.h_net_down),
                "cpu_power": list(self.h_cpu_power),
                "total_power": list(self.h_total_power),
            }
