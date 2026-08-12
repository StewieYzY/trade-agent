"""沪深 5208 只五维 L1 预热脚本（北交所不在 scope）.

- socket 全局超时 90s：防休眠唤醒后半开 TCP 连接挂死
- cache-first：已完成维度直接命中，可随时中断重启（无损）
- stdout 建议重定向到 data/prewarm_shsz.log 保留 DIM_DONE 遥测
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

socket.setdefaulttimeout(90)


def main() -> None:
    import akshare as ak
    from data.lib.batch_fetcher import BatchFetcher, FetchTelemetry
    from data.lib.market_router import parse_ticker
    from screener.main import G1_QUANT_DIMENSIONS

    df = ak.stock_info_a_code_name()
    all_tickers = [str(c).zfill(6) for c in df["code"].tolist()]
    tickers = [
        t for t in all_tickers
        if parse_ticker(t).full.endswith((".SH", ".SZ"))
    ]
    print(
        f"PREWARM_SH_SZ_START all={len(all_tickers)} sh_sz={len(tickers)} "
        f"bj_excluded={len(all_tickers) - len(tickers)}",
        flush=True,
    )
    fetcher = BatchFetcher()
    for dim in G1_QUANT_DIMENSIONS:
        started = time.monotonic()
        telemetry = FetchTelemetry()
        print(f"DIM_START dim={dim}", flush=True)
        fetcher.fetch_all(tickers, dimensions=(dim,), telemetry=telemetry)
        print(
            f"DIM_DONE dim={dim} elapsed_seconds={time.monotonic() - started:.1f} "
            f"cache_hits={len(telemetry.cache_hits)} "
            f"provider_calls={len(telemetry.provider_calls)} "
            f"failures={len(telemetry.failures)}",
            flush=True,
        )
        for failure in telemetry.failures[:20]:
            print(f"FAILURE dim={dim} {failure}", flush=True)
    print("PREWARM_SH_SZ_DONE", flush=True)


if __name__ == "__main__":
    main()
