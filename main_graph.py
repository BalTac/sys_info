#!/usr/bin/env python3
import os
import sys
import time
import logging
import subprocess
import threading
from datetime import datetime
from typing import Optional

import matplotlib.pyplot as plt
import keyboard

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.layout import Layout

# ─── CONSTANTS ─────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LHM_EXE = os.path.join(BASE_DIR, "lhm", "LibreHardwareMonitor.exe")
LHM_DLL = os.path.join(BASE_DIR, "lhm", "LibreHardwareMonitorLib.dll")

MAX_DATA_POINTS = 3600
REFRESH_PER_SECOND = 4
POLL_INTERVAL = 1.0
SENSOR_RETRY_COUNT = 5
SENSOR_RETRY_DELAY = 1.0

# ─── LOGGING ────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("tesla")


# ─── TESLA MONITOR ──────────────────────────────────────────────

class TeslaMonitor:
    def __init__(self) -> None:
        self.console = Console()

        # LHM
        self.lhm_available = False
        self.lhm_process: Optional[subprocess.Popen] = None
        self._Computer = None
        self.fan_rpm_sensor = None
        self.fan_pwm_sensor = None
        self.fan_hw = None

        # NVML
        self.nvml_available = False
        self.gpu_handle = None

        # Recording
        self.recording = False
        self.data: list = []
        self.pending_plot = False
        self._lock = threading.Lock()

        self._init_nvml()
        self._init_lhm()

    # ── Init ────────────────────────────────────────────────────

    def _init_nvml(self) -> None:
        try:
            import pynvml
            pynvml.nvmlInit()
            self.nvml_available = True
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode()
                if "Tesla" in name:
                    self.gpu_handle = h
                    break
            if self.gpu_handle:
                log.info("NVML ready — Tesla GPU cached")
            else:
                log.warning("NVML ready — no Tesla GPU found")
        except Exception as e:
            log.warning("NVML unavailable: %s", e)

    def _init_lhm(self) -> None:
        if not os.path.exists(LHM_DLL):
            log.warning("LHM DLL not found at %s", LHM_DLL)
            return
        try:
            import clr
            clr.AddReference(LHM_DLL)
            from LibreHardwareMonitor.Hardware import Computer
            self._Computer = Computer
            self.lhm_available = True
            log.info("LHM library loaded")
        except Exception as e:
            log.warning("LHM unavailable: %s", e)

    # ── LHM lifecycle ───────────────────────────────────────────

    def start_lhm(self) -> None:
        if not os.path.exists(LHM_EXE) or not self.lhm_available:
            return
        self.lhm_process = subprocess.Popen(
            [LHM_EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(2)
        self.find_sensors()

    def stop_lhm(self) -> None:
        if self.lhm_process:
            self.lhm_process.terminate()
            self.lhm_process = None

    # ── Sensor discovery ────────────────────────────────────────

    def find_sensors(self) -> None:
        if not self.lhm_available:
            return
        computer = self._Computer()
        computer.IsMotherboardEnabled = True
        computer.Open()

        for attempt in range(SENSOR_RETRY_COUNT):

            def walk(hw):
                hw.Update()
                for sensor in hw.Sensors:
                    stype = sensor.SensorType.ToString()
                    if stype == "Fan" and sensor.Name == "Fan #5":
                        self.fan_rpm_sensor = sensor
                        self.fan_hw = hw
                    elif stype == "Control" and sensor.Name == "Fan #5":
                        self.fan_pwm_sensor = sensor
                        self.fan_hw = hw
                for sub in hw.SubHardware:
                    walk(sub)

            for hw in computer.Hardware:
                walk(hw)

            if self.fan_rpm_sensor or self.fan_pwm_sensor:
                log.info("Fan sensors found (attempt %d)", attempt + 1)
                return
            time.sleep(SENSOR_RETRY_DELAY)

        log.warning("Fan sensors not found after %d attempts", SENSOR_RETRY_COUNT)

    def get_fan_rpm(self) -> Optional[float]:
        if self.fan_rpm_sensor and self.fan_hw:
            self.fan_hw.Update()
            return float(self.fan_rpm_sensor.Value)
        return None

    def get_fan_pwm(self) -> Optional[float]:
        if self.fan_pwm_sensor and self.fan_hw:
            self.fan_hw.Update()
            return float(self.fan_pwm_sensor.Value)
        return None

    # ── GPU data ────────────────────────────────────────────────

    def get_gpu_data(self) -> tuple[int, int]:
        if not self.nvml_available or self.gpu_handle is None:
            return 0, 0
        try:
            import pynvml
            temp = pynvml.nvmlDeviceGetTemperature(
                self.gpu_handle, pynvml.NVML_TEMPERATURE_GPU
            )
            util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle).gpu
            return temp, util
        except Exception as e:
            log.error("GPU read error: %s", e)
            return 0, 0

    # ── Recording ───────────────────────────────────────────────

    def toggle_recording(self) -> None:
        with self._lock:
            self.recording = not self.recording
            if self.recording:
                self.data.clear()
                self.console.print("[green]● Recording started[/green]")
            else:
                self.console.print("[red]■ Recording stopped[/red]")
                self.pending_plot = True

    def record_sample(
        self, temp: int, util: int, rpm: Optional[float], pwm: Optional[float]
    ) -> None:
        with self._lock:
            if not self.recording:
                return
            self.data.append((time.time(), temp, util, rpm, pwm))
            if len(self.data) > MAX_DATA_POINTS:
                self.data.pop(0)

    # ── Plot ────────────────────────────────────────────────────

    def plot(self) -> None:
        with self._lock:
            if not self.data:
                self.pending_plot = False
                return
            snap = list(self.data)
            self.pending_plot = False

        t0 = snap[0][0]
        times = [t - t0 for t, *_ in snap]
        temps = [x[1] for x in snap]
        utils = [x[2] for x in snap]
        rpms = [x[3] if x[3] else 0 for x in snap]
        pwms = [x[4] if x[4] else 0 for x in snap]

        plt.style.use("dark_background")
        fig, ax1 = plt.subplots(figsize=(12, 6))

        ax1.plot(times, temps, color="#00d4ff", linewidth=2, label="Temp °C")
        ax1.fill_between(times, temps, alpha=0.15)

        ax2 = ax1.twinx()
        ax2.plot(times, rpms, "--", color="#ffaa00", label="Fan RPM")

        ax3 = ax1.twinx()
        ax3.spines.right.set_position(("outward", 60))
        ax3.plot(times, utils, ":", color="#00ff88", label="GPU %")

        ax4 = ax1.twinx()
        ax4.spines.right.set_position(("outward", 120))
        ax4.plot(times, pwms, "-.", color="#ff00ff", label="PWM %")

        lines = ax1.get_lines() + ax2.get_lines() + ax3.get_lines() + ax4.get_lines()
        labels = [l.get_label() for l in lines]
        plt.legend(lines, labels)

        plt.title("Tesla P40 Thermal + Fan Behavior")
        ax1.grid(True, alpha=0.2)
        plt.tight_layout()
        plt.show()

    # ── UI ──────────────────────────────────────────────────────

    C = "bold bright_cyan"
    M = "bold bright_magenta"
    G = "bold bright_green"
    Y = "bold bright_yellow"
    W = "bold bright_white"
    D = "bright_black"

    def _vu_meter(self, value: float, mx: float, w: int = 20, c: str = "cyan") -> Text:
        pct = min(value / mx, 1.0) if mx else 0
        fill = int(w * pct)
        t = Text()
        t.append("▐", style=self.D)
        t.append("█" * fill, style=f"bold {c}")
        t.append("░" * (w - fill), style=self.D)
        t.append("▌", style=self.D)
        return t

    def render(
        self, temp: int, util: int, rpm: Optional[float], pwm: Optional[float]
    ) -> Layout:
        L = Layout()
        L.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )

        # ── HEADER ──────────────────────────────────────────────
        h = Text()
        h.append("  TESLA P40 THERMAL MONITOR", style=self.C)
        h.append("   ", style=self.D)
        h.append("STATUS: ", style=self.W)
        h.append("ONLINE", style=self.G)
        h.append("  ", style=self.D)
        h.append(datetime.now().strftime('%H:%M:%S'), style=self.M)

        L["header"].update(Panel(
            h, border_style=self.C, box=box.HEAVY, padding=(0, 1),
        ))

        # ── MAIN ────────────────────────────────────────────────
        L["main"].split_row(
            Layout(name="stats"),
            Layout(name="bar", size=30),
        )

        # ── STATS ───────────────────────────────────────────────
        s = Text()
        for label, val, mx, clr, fmt in [
            ("TEMP",    temp, 100,   "bright_cyan",   "{:>3}°C"),
            ("GPU LOAD", util, 100,  "bright_green",  "{:>3}%"),
        ]:
            s.append(f"  {label:<9}", style=self.W)
            s.append(self._vu_meter(val, mx, c=clr))
            s.append(f"  {fmt.format(val)}\n", style=f"bold {clr}")

        s.append(f"  {'FAN RPM':<9}", style=self.W)
        if rpm:
            s.append(self._vu_meter(rpm, 5000, c="bright_yellow"))
            s.append(f"  {rpm:>4.0f}\n", style=self.Y)
        else:
            s.append("  N/A\n", style=self.D)

        s.append(f"  {'PWM':<9}", style=self.W)
        if pwm is not None:
            s.append(self._vu_meter(pwm, 100, c="bright_magenta"))
            s.append(f"  {pwm:>5.1f}%", style=self.M)
        else:
            s.append("  N/A", style=self.D)

        L["main"]["stats"].update(Panel(
            s, border_style=self.M, box=box.HEAVY, padding=(1, 2),
        ))

        # ── GPU LOAD BAR ────────────────────────────────────────
        pct = util or 0
        n = int(pct / 5.56)
        b = Text()
        b.append("\n")
        b.append("  ")
        b.append("█" * n, style=self.G)
        b.append("░" * (18 - n), style=self.D)
        b.append(f"  {pct:>3.0f}%\n", style=self.G)
        b.append("\n")
        if self.recording:
            b.append("  ● REC", style="bold bright_red")
            b.append(f"  [{len(self.data):>4}]", style=self.D)
        else:
            b.append("  ○ IDLE", style=self.D)

        L["main"]["bar"].update(Panel(
            b, border_style=self.C, box=box.HEAVY, padding=(1, 1),
            title="[bold bright_white]GPU LOAD[/]",
        ))

        # ── FOOTER ──────────────────────────────────────────────
        f = Text()
        f.append("  CTRL+R", style=self.C)
        f.append("  REC  ", style=self.D)
        f.append("│", style=self.C)
        f.append("  CTRL+C", style=self.M)
        f.append("  EXIT  ", style=self.D)
        f.append("│", style=self.C)
        from config import __version__
        f.append(f"  v{__version__}  ", style=self.D)

        L["footer"].update(Panel(
            f, border_style=self.C, box=box.HEAVY, padding=(0, 1),
        ))

        return L

    # ── Run ─────────────────────────────────────────────────────

    def run(self, interval: float = POLL_INTERVAL) -> None:
        temp, util = self.get_gpu_data()
        rpm = self.get_fan_rpm()
        pwm = self.get_fan_pwm()

        keyboard.add_hotkey("ctrl+r", self.toggle_recording)

        try:
            with Live(
                self.render(temp, util, rpm, pwm),
                refresh_per_second=REFRESH_PER_SECOND,
            ) as live:
                while True:
                    temp, util = self.get_gpu_data()
                    rpm = self.get_fan_rpm()
                    pwm = self.get_fan_pwm()

                    self.record_sample(temp, util, rpm, pwm)

                    if self.pending_plot:
                        self.plot()

                    live.update(self.render(temp, util, rpm, pwm))
                    time.sleep(interval)

        except KeyboardInterrupt:
            self.console.print("\nBye 👋")

    def shutdown(self) -> None:
        self.stop_lhm()
        if self.nvml_available:
            try:
                import pynvml
                pynvml.nvmlShutdown()
            except Exception:
                pass


# ─── MAIN ───────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Tesla P40 Thermal Monitor")
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=POLL_INTERVAL,
        help="Update interval in seconds (default: %(default)s)",
    )
    args = parser.parse_args()

    sys.stdout.write("\x1b[8;48;150t")
    sys.stdout.flush()
    time.sleep(0.15)

    monitor = TeslaMonitor()
    monitor.start_lhm()

    try:
        monitor.run(interval=args.interval)
    finally:
        monitor.shutdown()


if __name__ == "__main__":
    main()
