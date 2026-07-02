"""Task 1.1 (f1-deviation-fix): P0 根因现状确认（D1，缩减版）.

对 600519 / 600900 / 600009 三只票，调用 assemble_council_features(ticker)，
dump 返回的 features dict 到 scripts/repro_out/{ticker}_features.json，
重点检查 financials_floor（pe_ttm / roe_3y / net_margin）是否为 None。

判定逻辑（design D1）：
- 若 600519/600900 的 financials_floor 确为 None → 根因在代码层 guard 放行，走 §2
- 若 features 竟然齐全 → 根因可能也在模型层，走 §3 衍生 change

用法：
    cd value-screener && python scripts/repro_features.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 让脚本在 value-screener/ 下直接运行（与 conftest.py 同口径）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.features import assemble_council_features  # noqa: E402

FINANCIALS_FLOOR = ["pe_ttm", "roe_3y", "net_margin"]

TICKERS = ["600519", "600900", "600009"]
OUT_DIR = Path(__file__).resolve().parent / "repro_out"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    summary = {}
    for ticker in TICKERS:
        features = assemble_council_features(ticker)
        out_path = OUT_DIR / f"{ticker}_features.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(features, f, ensure_ascii=False, indent=2, default=str)

        if "error" in features:
            summary[ticker] = {
                "status": "insufficient_data",
                "error": features.get("error"),
                "missing_fields": features.get("missing_fields", []),
                "financials_floor": {k: None for k in FINANCIALS_FLOOR},
            }
            print(f"[{ticker}] insufficient_data: {features.get('missing_fields')}")
            continue

        floor_status = {k: features.get(k) for k in FINANCIALS_FLOOR}
        floor_none = [k for k, v in floor_status.items() if v is None]
        summary[ticker] = {
            "status": "ok" if not floor_none else "partial",
            "financials_floor": floor_status,
            "floor_none_fields": floor_none,
            "name": features.get("name"),
            "market_cap": features.get("market_cap"),
        }
        marker = "OK (齐全)" if not floor_none else f"PARTIAL (缺失 {floor_none})"
        print(f"[{ticker}] {marker}")
        print(f"        name={features.get('name')}, market_cap={features.get('market_cap')}")
        print(f"        pe_ttm={floor_status['pe_ttm']}, roe_3y={floor_status['roe_3y']}, net_margin={floor_status['net_margin']}")

    # 汇总
    summary_path = OUT_DIR / "repro_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n汇总写入 {summary_path}")


if __name__ == "__main__":
    main()
