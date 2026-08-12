"""健康看门狗：定时巡检 + 设备保活 + 守护进程自愈.

每 5 分钟：
- 记录进程状态、缓存进度、磁盘余量
- caffeinate 不在则拉起（防设备休眠）
- driver 已死且 pipeline 未完成 → 自动重启 driver（cache-first 幂等）
- pipeline 完成（driver done/ABORT）→ 释放 caffeinate 并退出
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "health_watchdog.log"
DRIVER_PID_FILE = ROOT / "data" / "driver.pid"
WATCHDOG_PID_FILE = ROOT / "data" / "watchdog.pid"
DRIVER_LOG = ROOT / "data" / "prewarm_driver.log"
EVIDENCE_DIR = ROOT / "data" / "evidence"
PY = "/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python"
CHECK_INTERVAL = 300


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def pipeline_done() -> str | None:
    """driver 日志出现终态标记则返回该标记."""
    if not DRIVER_LOG.exists():
        return None
    tail = DRIVER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-6:]
    for line in tail:
        if "driver done" in line:
            return "driver done"
        if "ABORT" in line:
            return "ABORT"
    return None


def cache_counts() -> dict[str, int]:
    counts = {}
    for dim in ("basic", "financials", "kline", "valuation", "risk"):
        n = 0
        for ticker_dir in (ROOT / "data" / "cache").iterdir() if (ROOT / "data" / "cache").exists() else []:
            if ticker_dir.is_dir() and (ticker_dir / f"{dim}.json").exists():
                n += 1
        counts[dim] = n
    return counts


def ensure_caffeinate() -> None:
    check = subprocess.run(["pgrep", "-x", "caffeinate"], capture_output=True)
    if check.returncode != 0:
        subprocess.Popen(["caffeinate", "-i"], start_new_session=True)
        log("caffeinate restarted (device stay-awake)")


def start_driver() -> None:
    logf = open(ROOT / "data" / "prewarm_driver.nohup.log", "a")
    # 传不存在的 PID → driver 立即进入补漏阶段（cache-first 幂等，等价无损重启）
    proc = subprocess.Popen(
        [PY, "-u", str(ROOT / "scripts" / "prewarm_driver.py"), "999999"],
        stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    DRIVER_PID_FILE.write_text(str(proc.pid))
    log(f"driver restarted pid={proc.pid}")


def main() -> None:
    if WATCHDOG_PID_FILE.exists():
        other = read_pid(WATCHDOG_PID_FILE)
        if other and other != os.getpid() and alive(other):
            print(f"watchdog already running pid={other}; exit")
            return
    WATCHDOG_PID_FILE.write_text(str(os.getpid()))
    log("watchdog start")
    ensure_caffeinate()

    while True:
        try:
            done = pipeline_done()
            driver_pid = read_pid(DRIVER_PID_FILE)
            counts = cache_counts()
            free_gb = __import__("shutil").disk_usage(ROOT).free // (1024 ** 3)
            log(
                f"check: driver_pid={driver_pid} alive={alive(driver_pid) if driver_pid else False} "
                f"cache={counts} disk_free={free_gb}GB done={done}"
            )
            if done:
                subprocess.run(["pkill", "-x", "caffeinate"], capture_output=True)
                log(f"pipeline finished ({done}); caffeinate released; watchdog exit")
                break
            ensure_caffeinate()
            if driver_pid is None or not alive(driver_pid):
                log("driver not alive; restarting")
                start_driver()
        except Exception as exc:  # noqa: BLE001 - 看门狗自身不能被异常杀死
            log(f"watchdog iteration error: {type(exc).__name__}: {exc}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
