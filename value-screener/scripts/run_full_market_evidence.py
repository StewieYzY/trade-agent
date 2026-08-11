"""真实 warm-cache L1+L2 performance/cost evidence 运行脚本.

获取 ticker 列表 -> screen_a_shares (L1) -> scout_batch (L2) -> evidence bundle.
运行失败时保留失败证据，不以默认值伪造成功。

口径说明（review P1-2/P2-5）：
- ticker 来源为「已缓存目录」（cached subset）时 coverage=partial_market，
  结论仅对该输入集合成立；完整可交易集合（full_market）运行需先完成全量冷采集。
- evidence bundle 记录 ticker_source 与 evidence_notes，保证可复现与口径透明。

用法：
    cd value-screener
    set -a && source .env && set +a
    python scripts/run_full_market_evidence.py [--max N] [--coverage full_market|partial_market]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def get_full_market_tickers(max_n: int | None = None) -> tuple[list[str], str]:
    """获取沪深 A 股 ticker 列表，排除北交所，返回 (tickers, source)."""
    import akshare as ak
    from data.lib.market_router import parse_ticker

    df = ak.stock_info_a_code_name()
    all_tickers = [str(c).zfill(6) for c in df["code"].tolist()]
    tickers = [
        ticker for ticker in all_tickers
        if parse_ticker(ticker).full.endswith((".SH", ".SZ"))
    ]
    source = (
        f"akshare.stock_info_a_code_name({len(all_tickers)} total)"
        f" filtered SH/SZ ({len(tickers)} total); BJ excluded by scope"
    )
    if max_n and max_n < len(tickers):
        tickers = tickers[:max_n]
        source += f"[--max {max_n}]"
    return tickers, source


def get_cached_tickers() -> tuple[list[str], str]:
    """获取已缓存目录中的 ticker 列表（cached subset），返回 (tickers, source)."""
    cache_dir = Path("data/cache")
    tickers = sorted([
        d.name for d in cache_dir.iterdir()
        if d.is_dir() and not d.name.startswith("__") and not d.name.endswith(".py")
    ])
    return tickers, f"cached_subset(data/cache, {len(tickers)} dirs)"

def load_universe_file(path: str) -> tuple[list[str], str]:
    """读取 universe 快照文件（{source, generated_at, tickers[]}），返回 (tickers, source).

    用于断网场景：universe 列表可离线复用已生成快照，口径记录在 ticker_source 中。
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    tickers = [str(t) for t in payload.get("tickers", [])]
    provenance = payload.get("source", "unknown provenance")
    generated_at = payload.get("generated_at", "unknown")
    source = f"universe_file:{path}; {provenance}; generated_at={generated_at}"
    return tickers, source



async def main():
    parser = argparse.ArgumentParser(description="Warm-cache L1+L2 evidence run")
    parser.add_argument("--max", type=int, default=None, help="Limit ticker count (full-market mode only)")
    parser.add_argument("--output", type=str, default="data/evidence", help="Output directory")
    parser.add_argument("--source", type=str, default="cached",
                        choices=["cached", "full"],
                        help="Ticker source: cached subset or full market list")
    parser.add_argument("--coverage", type=str, default=None,
                        choices=["partial_market", "full_market"],
                        help="Coverage label; default derived from source")
    parser.add_argument("--tickers-file", type=str, default=None,
                        help="Universe 快照 JSON（{source, generated_at, tickers[]}），优先于 --source")
    args = parser.parse_args()

    from performance.run_evidence import run_full_market_evidence, save_evidence_bundle, build_failure_bundle

    tickers: list[str] = []
    source = "unspecified"
    coverage = args.coverage or "partial_market"

    run_start = time.monotonic()
    try:
        if args.tickers_file:
            tickers, source = load_universe_file(args.tickers_file)
            if args.max and args.max < len(tickers):
                tickers = tickers[: args.max]
                source += f"[--max {args.max}]"
            coverage = args.coverage or ("full_market" if args.max is None else "partial_market")
        elif args.source == "full":
            tickers, source = get_full_market_tickers(max_n=args.max)
            coverage = args.coverage or ("full_market" if args.max is None else "partial_market")
        else:
            tickers, source = get_cached_tickers()
            coverage = args.coverage or "partial_market"

        print("=== Warm-cache L1+L2 Evidence Run ===")
        print(f"  source:   {source}")
        print(f"  coverage: {coverage}")
        print(f"  tickers:  {len(tickers)}")
        print()

        bundle = await run_full_market_evidence(
            tickers, exclude_cyclicals=False, force_l2=False,
            coverage=coverage, ticker_source=source,
        )
    except Exception as e:  # noqa: BLE001 - 失败证据保留，不伪造成功
        elapsed = time.monotonic() - run_start
        print(f"\n  ❌ 运行失败（{elapsed:.1f}s）：{e}")
        bundle = build_failure_bundle(
            e,
            elapsed,
            len(tickers),
            coverage=coverage,
            tickers=tickers,
            ticker_source=source,
        )

    out_path = save_evidence_bundle(bundle, output_dir=args.output)
    print(f"\n保存到：{out_path}")

    if bundle.get("run_failed"):
        print(f"RUN FAILED: {bundle['failure']['error']}")
        print(f"gate_passed: {bundle['gate_passed']}")
        return

    print(f"gate_passed: {bundle['gate_passed']}")
    print(f"warm_cache(L1 数据缓存): {bundle['warm_cache']}")
    t = bundle["timing"]
    print(f"timing: total={t['total_elapsed_seconds']:.1f}s, "
          f"L1={t['l1_elapsed_seconds']:.1f}s, L2={t['l2_elapsed_seconds']:.1f}s")
    print(f"funnel: {bundle['funnel']}")
    avail = bundle["field_availability"]
    print(f"field_availability: {avail['rate']:.4f} "
          f"({avail['missing_count']} missing / {avail['total_fields']} total)")
    cost = bundle["cost"]
    print(f"cost: measured=¥{cost['measured_yuan']:.4f}, "
          f"equiv_full=¥{cost['equivalent_full_yuan']:.4f}, "
          f"calls={cost['call_count']}, cache_hits={cost['cache_hits']}")
    exc = bundle["exceptions"]
    print(f"exceptions: unhandled={exc['unhandled_count']}, errors={len(exc['error_details'])}")
    for note in bundle.get("evidence_notes", []):
        print(f"note: {note}")


if __name__ == "__main__":
    asyncio.run(main())
