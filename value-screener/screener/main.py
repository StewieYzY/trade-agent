"""L1 入口 — screen_a_shares().

编排三道漏斗：
1. Layer 1: BatchFetcher.fetch_all() 批量采集
2. 第一道漏斗: Hard Gates → ~800
3. 第二道漏斗: Factor Scores + Anti-Trap → ~300 (按 composite 降序取 top)
4. 第三道漏斗: Heat Filter → ~200
5. 组装输出 JSON (S5 schema)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from data.lib.batch_fetcher import BatchFetcher
from .hard_gates import check_hard_gates
from .factor_scores import compute_factor_scores
from .anti_trap import compute_anti_trap
from .heat_filter import check_heat_filter


def screen_a_shares(tickers: list[str], exclude_cyclicals: bool = False) -> dict[str, Any]:
    """全市场 A 股量化筛选.

    Args:
        tickers: 股票代码列表
        exclude_cyclicals: 是否排除周期股（默认 False）

    Returns:
        S5 Output Schema:
        {
            "run_date": str,
            "candidates": [...],
            "stats": {
                "total": int,
                "after_hard_gates": int,
                "after_factors": int,
                "after_heat_filter": int,
                "excluded_by_gates": {...}
            }
        }
    """
    # Layer 1: 批量采集
    fetcher = BatchFetcher()
    all_data = fetcher.fetch_all(tickers)

    total = len(tickers)

    # 第一道漏斗: Hard Gates
    after_hard_gates = []
    excluded_by_gates = {}

    for ticker in tickers:
        ticker_data = all_data.get(ticker, {})
        result = check_hard_gates(ticker_data, exclude_cyclicals=exclude_cyclicals)

        if result["pass"]:
            after_hard_gates.append(ticker)
        else:
            # 统计各 gate 排除的股票
            for gate in result["failed_gates"]:
                excluded_by_gates[gate] = excluded_by_gates.get(gate, 0) + 1

    # 第二道漏斗: Factor Scores + Anti-Trap
    candidates_with_scores = []

    for ticker in after_hard_gates:
        ticker_data = all_data.get(ticker, {})

        factor_scores = compute_factor_scores(ticker_data)
        anti_trap = compute_anti_trap(ticker_data)

        # 应用 anti-trap 扣分到 composite
        adjusted_composite = factor_scores["composite"] * (anti_trap["score"] / 100.0)

        candidates_with_scores.append({
            "ticker": ticker,
            "factor_scores": factor_scores,
            "anti_trap": anti_trap,
            "adjusted_composite": adjusted_composite
        })

    # 按 adjusted_composite 降序排序，取 top 300
    candidates_with_scores.sort(key=lambda x: x["adjusted_composite"], reverse=True)
    top_300 = candidates_with_scores[:300]

    # 第三道漏斗: Heat Filter
    final_candidates = []

    for candidate in top_300:
        ticker = candidate["ticker"]
        ticker_data = all_data.get(ticker, {})

        result = check_heat_filter(ticker_data)

        if result["pass"]:
            final_candidates.append(candidate)

    # 组装输出 JSON (S5 schema)
    output_candidates = []

    for candidate in final_candidates:
        ticker = candidate["ticker"]
        ticker_data = all_data.get(ticker, {})

        basic = ticker_data.get("basic", {})
        valuation = ticker_data.get("valuation", {})
        risk = ticker_data.get("risk", {})

        output_candidates.append({
            "ticker": ticker,
            "name": basic.get("name", ""),
            "industry": basic.get("industry", ""),
            "factor_scores": candidate["factor_scores"],
            "anti_trap": candidate["anti_trap"],
            "f_score": candidate["factor_scores"]["f_score"],
            "graham_number": valuation.get("graham_number"),
            "pe_ttm": valuation.get("pe_ttm"),
            "pb": valuation.get("pb"),
            "pledge_ratio": risk.get("pledge_ratio")
        })

    return {
        "run_date": date.today().isoformat(),
        "candidates": output_candidates,
        "stats": {
            "total": total,
            "after_hard_gates": len(after_hard_gates),
            "after_factors": len(top_300),
            "after_heat_filter": len(final_candidates),
            "excluded_by_gates": excluded_by_gates
        }
    }
