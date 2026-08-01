from __future__ import annotations

import os
import subprocess
from pathlib import Path


def read_mem_available_kib() -> int:
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    return 0


def read_load_average() -> float:
    return os.getloadavg()[0]


def read_temperature_c() -> float | None:
    candidates = [
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/sys/class/hwmon/hwmon0/temp1_input"),
    ]
    for path in candidates:
        if path.exists():
            raw = path.read_text(encoding="utf-8").strip()
            try:
                value = float(raw)
            except ValueError:
                continue
            return value / 1000.0 if value > 1000 else value
    return None


def sqlite_page_info(path: Path) -> tuple[int, int]:
    import sqlite3

    conn = sqlite3.connect(path)
    try:
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        return page_count, page_size
    finally:
        conn.close()


def process_cpu_seconds(pid: int) -> float:
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.exists():
        return 0.0
    parts = stat_path.read_text(encoding="utf-8").split()
    clk_tck = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    return (int(parts[13]) + int(parts[14])) / clk_tck


def process_rss_kib(pid: int) -> int:
    status_path = Path(f"/proc/{pid}/status")
    if not status_path.exists():
        return 0
    with status_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return 0


def approximate_cpu_percent(pid: int) -> float:
    completed = subprocess.run(["ps", "-p", str(pid), "-o", "%cpu="], text=True, capture_output=True, check=False)
    if completed.returncode != 0 or not completed.stdout.strip():
        return 0.0
    return float(completed.stdout.strip())
