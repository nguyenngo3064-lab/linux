#!/usr/bin/python3
"""Read-only system metrics and fixed service operations."""

import os
import shutil
import subprocess

FIREFOX_SERVICE = "cloud-firefox.service"
CONTROL_SERVICE = "cloud-firefox-control.service"
_cpu_previous = None


def _command(arguments, timeout=8):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True,
                                timeout=timeout, check=False)
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _service_active(name):
    code, output = _command(["/usr/bin/sudo", "-n", "/usr/bin/systemctl",
                             "is-active", name])
    return code == 0 and output == "active"


def _cpu_usage():
    global _cpu_previous
    try:
        with open("/proc/stat", encoding="ascii") as source:
            values = [int(value) for value in source.readline().split()[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values[:8])
        usage = None
        if _cpu_previous is not None:
            total_delta = total - _cpu_previous[0]
            idle_delta = idle - _cpu_previous[1]
            if total_delta > 0:
                usage = max(0.0, min(100.0, 100.0 * (total_delta - idle_delta) / total_delta))
        _cpu_previous = (total, idle)
        return round(usage, 1) if usage is not None else None
    except (OSError, ValueError, IndexError):
        return None


def _memory():
    values = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as source:
            for line in source:
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0]) * 1024
        total = values["MemTotal"]
        available = values.get("MemAvailable", values.get("MemFree", 0))
        return {"total_bytes": total, "used_bytes": max(0, total - available),
                "available_bytes": available}
    except (OSError, ValueError, KeyError):
        return {"total_bytes": None, "used_bytes": None, "available_bytes": None}


def _oom_kills():
    try:
        with open("/proc/vmstat", encoding="ascii") as source:
            for line in source:
                if line.startswith("oom_kill "):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def _uptime():
    try:
        with open("/proc/uptime", encoding="ascii") as source:
            return int(float(source.readline().split()[0]))
    except (OSError, ValueError, IndexError):
        return None


def _human_bytes(amount):
    if amount is None:
        return "khong ro"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(amount)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024


def status():
    memory = _memory()
    try:
        disk = shutil.disk_usage("/")
        disk_data = {"total_bytes": disk.total, "used_bytes": disk.used,
                     "free_bytes": disk.free}
    except OSError:
        disk_data = {"total_bytes": None, "used_bytes": None, "free_bytes": None}
    return {
        "firefox": _service_active(FIREFOX_SERVICE),
        "control": _service_active(CONTROL_SERVICE),
        "memory": memory,
        "cpu_percent": _cpu_usage(),
        "uptime_seconds": _uptime(),
        "disk": disk_data,
        "oom_kills": _oom_kills(),
    }


def logs():
    code, output = _command(["/usr/bin/sudo", "-n", "/usr/bin/journalctl",
                             "--no-pager", "-n", "100", "-u", FIREFOX_SERVICE], timeout=10)
    if code != 0:
        raise RuntimeError("Khong doc duoc system journal")
    return output[-16000:]


def action(name):
    actions = {
        "start": ("start", FIREFOX_SERVICE),
        "stop": ("stop", FIREFOX_SERVICE),
        "restart": ("restart", FIREFOX_SERVICE),
        "control-start": ("start", CONTROL_SERVICE),
        "control-stop": ("stop", CONTROL_SERVICE),
    }
    if name not in actions:
        raise ValueError("Tac vu khong hop le")
    verb, service = actions[name]
    code, _ = _command(["/usr/bin/sudo", "-n", "/usr/bin/systemctl", verb, service], timeout=20)
    if code != 0:
        raise RuntimeError("systemd khong thuc hien duoc tac vu")


def format_bytes(amount):
    return _human_bytes(amount)