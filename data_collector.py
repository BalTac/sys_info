#!/usr/bin/env python3
"""Data collector: psutil + pynvml → snapshot dict + historical deques."""

import os
import time
import threading
from collections import deque
from dataclasses import dataclass, field

import psutil

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
        self.h_gpu_temp: deque[float] = deque(maxlen=n)
        self.h_gpu_load: deque[float] = deque(maxlen=n)
        self.h_net_up: deque[float] = deque(maxlen=n)
        self.h_net_down: deque[float] = deque(maxlen=n)
        self.h_times: deque[float] = deque(maxlen=n)

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
                        "fan": fan,
                        "processes": processes,
                    })
                    # History from first GPU
                    if i == 0:
                        self.h_gpu_temp.append(temp)
                        self.h_gpu_load.append(util.gpu)
            except Exception:
                pass

        with self._lock:
            self.snapshot = snap
            self.h_cpu.append(snap.cpu_avg)
            self.h_ram.append(snap.ram_pct)
            self.h_net_up.append(snap.net_sent_kbps)
            self.h_net_down.append(snap.net_recv_kbps)
            self.h_times.append(now)

    def get(self) -> Snapshot:
        with self._lock:
            return self.snapshot

    def history(self):
        with self._lock:
            return {
                "times": list(self.h_times),
                "cpu": list(self.h_cpu),
                "ram": list(self.h_ram),
                "gpu_temp": list(self.h_gpu_temp),
                "gpu_load": list(self.h_gpu_load),
                "net_up": list(self.h_net_up),
                "net_down": list(self.h_net_down),
            }
