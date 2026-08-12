"""预热守护脚本：等待主预热进程退出 -> 补齐缺口 -> 最后刷新 basic -> 跑证据运行.

背景：basic TTL=2h，主预热顺序 basic 在最前，等其他维度跑完 basic 已过期。
因此 basic 必须在证据运行前最后重取（真实 provider 调用，非 mtime 伪造）。
所有步骤写入日志；证据运行失败时保留失败证据。
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

LOG = ROOT / "data" / "prewarm_driver.log"
UNIVERSE_FILE = ROOT / "data" / "universe_full.json"
# 预热进程 wall-clock 预算（含机器休眠时间）；超时强杀，cache-first 补漏自愈
PREWARM_MAX_WAIT_SECONDS = 12 * 3600


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def wait_for_exit(pid: int) -> None:
    deadline = time.time() + PREWARM_MAX_WAIT_SECONDS
    warned = False
    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            log(f"PID {pid} exited")
            return
        if time.time() > deadline:
            log(
                f"TIMEOUT: PID {pid} alive after {PREWARM_MAX_WAIT_SECONDS // 3600}h wall-clock; "
                "SIGTERM/SIGKILL 后继续（cache-first 补漏会自愈未完成部分）"
            )
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            time.sleep(30)
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            log(f"PID {pid} killed; proceeding to top-up")
            return
        if not warned and time.time() > deadline - 2 * 3600:
            log(f"WARNING: PID {pid} still alive; watchdog budget 剩余不足 2h")
            warned = True
        time.sleep(120)


def universe() -> list[str]:
    """live akshare 取 universe（重试 3 次）；失败时兜底读快照文件（口径写入日志）."""
    from run_full_market_evidence import get_full_market_tickers
    for attempt in range(1, 4):
        try:
            tickers, source = get_full_market_tickers(max_n=None)
            payload = {
                "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "source": source,
                "tickers": tickers,
            }
            UNIVERSE_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            log(f"universe (live): {len(tickers)} tickers; {source}")
            return tickers
        except Exception as exc:  # noqa: BLE001 - 网络抖动重试
            log(f"universe live attempt {attempt}/3 failed: {exc}")
            time.sleep(30)
    if UNIVERSE_FILE.exists():
        payload = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
        tickers = [str(t) for t in payload.get("tickers", [])]
        log(
            f"universe (snapshot fallback): {len(tickers)} tickers; "
            f"generated_at={payload.get('generated_at')}; source={payload.get('source')}"
        )
        return tickers
    log("ABORT: universe unavailable (live failed, no snapshot)")
    sys.exit(1)


def cache_report(tickers: list[str]) -> dict[str, list[str]]:
    from data.cache.manager import CacheManager
    from screener.main import G1_QUANT_DIMENSIONS
    cm = CacheManager()
    gaps: dict[str, list[str]] = {}
    for dim in G1_QUANT_DIMENSIONS:
        bad = [t for t in tickers if cm.is_expired(t, dim)]
        gaps[dim] = bad
        log(f"cache check dim={dim}: {len(tickers) - len(bad)}/{len(tickers)} warm, {len(bad)} expired/missing")
    return gaps


def fetch_subset(tickers: list[str], dims: tuple[str, ...]) -> None:
    from data.lib.batch_fetcher import BatchFetcher, FetchTelemetry
    fetcher = BatchFetcher()
    for dim in dims:
        started = time.monotonic()
        telemetry = FetchTelemetry()
        fetcher.fetch_all(tickers, dimensions=(dim,), telemetry=telemetry)
        log(
            f"fetch dim={dim} n={len(tickers)} elapsed={time.monotonic() - started:.0f}s "
            f"cache_hits={len(telemetry.cache_hits)} provider_calls={len(telemetry.provider_calls)} "
            f"failures={len(telemetry.failures)}"
        )
        for failure in telemetry.failures[:20]:
            log(f"  failure: {failure}")


def spot_available() -> bool:
    """探测东财 spot_em 全市场快照是否可用（basic 主选数据源）."""
    try:
        import akshare as ak  # noqa: PLC0415
        started = time.monotonic()
        df = ak.stock_zh_a_spot_em()
        log(f"spot_em available: {len(df)} rows in {time.monotonic() - started:.1f}s")
        return df is not None and len(df) > 0
    except Exception as exc:  # noqa: BLE001 - 探测失败即视为不可用
        log(f"spot_em unavailable: {type(exc).__name__}: {exc}")
        return False


def fetch_basic_with_retry(tickers: list[str]) -> None:
    """basic 最后刷新：spot_em 限流时等待重试，超时后走 per-ticker 兜底（慢但真实）."""
    gaps = cache_report(tickers)
    if not gaps["basic"]:
        return
    for attempt in range(1, 5):
        if spot_available():
            fetch_subset(cache_report(tickers)["basic"], ("basic",))
            gaps = cache_report(tickers)
            if not gaps["basic"]:
                return
            log(f"basic still has {len(gaps['basic'])} gaps after spot fetch; will retry")
        else:
            log(f"spot_em throttled (attempt {attempt}/4); sleep 600s")
        time.sleep(600)
    remaining = cache_report(tickers)["basic"]
    if remaining:
        log(
            f"spot_em still unavailable after retries; fetching {len(remaining)} basic "
            "via per-ticker fallback (Tencent backup; slower, data recorded as-is)"
        )
        fetch_subset(remaining, ("basic",))


def main() -> None:
    # 防休眠唤醒后半开 TCP 连接挂死：driver 自身采集全部受 90s socket 超时约束
    socket.setdefaulttimeout(90)
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 98341
    log(f"driver start; waiting for prewarm PID {pid}")
    wait_for_exit(pid)

    tickers = universe()

    # 补齐 financials/kline/valuation/risk 缺口（cache-first，幂等）
    gaps = cache_report(tickers)
    for dim in ("financials", "kline", "valuation", "risk"):
        if gaps[dim]:
            fetch_subset(gaps[dim], (dim,))

    # basic 最后刷新（此时基本全过期 → 真实重取；spot 限流则重试/兜底）
    fetch_basic_with_retry(tickers)

    # 终检
    gaps = cache_report(tickers)
    not_warm = {dim: bad for dim, bad in gaps.items() if bad}
    if not_warm:
        for dim, bad in not_warm.items():
            log(f"ABORT: dim={dim} still not warm for {len(bad)} tickers: {bad[:30]}")
        log("ABORT: evidence run skipped; cache not fully warm")
        sys.exit(1)

    log("cache fully warm; launching evidence run")
    env_source = "set -a && source /Users/admin/Documents/trade-agent/value-screener/.env && set +a && "
    cmd = (
        env_source
        + f"cd {ROOT} && /Users/admin/Documents/trade-agent/value-screener/.venv/bin/python "
        f"scripts/run_full_market_evidence.py --tickers-file {UNIVERSE_FILE} --coverage full_market"
    )
    started = time.monotonic()
    proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    log(f"evidence run exit={proc.returncode} elapsed={time.monotonic() - started:.0f}s")
    log("=== evidence stdout ===")
    log(proc.stdout)
    if proc.stderr:
        log("=== evidence stderr ===")
        log(proc.stderr[-4000:])
    log("driver done")


if __name__ == "__main__":
    main()
