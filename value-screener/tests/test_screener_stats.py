"""L1 stats 退化标记测试（l4b-docker-run tasks 2.1-2.3）

验证 screen_a_shares 输出的 stats 含两个退化标记字段：
- industry_pe_degraded: 行业 PE 中位数映射为空（样本不足）时为 true
- input_scale: 输入 ticker 数 < 300 → "subset"，否则 "full_market"

以及下游（L2 scout_batch / L4 aggregate_watchlist）不消费这两个字段时行为不变。
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from screener.main import screen_a_shares


def _make_ticker_data(industry="白酒", pe=25.0):
    """构造一份能过 hard gates 的最小 ticker_data（单只退化测试用）。"""
    return {
        "basic": {
            "code": "600519",
            "name": "贵州茅台",
            "industry": industry,
            "pe": pe,
            "pb": 2.0,
            "price": 10.0,
            "market_cap": 100e8,
        },
        "financials": {
            "years": ["2020", "2021", "2022"],
            "income": {"net_profit": [100, 120, 150]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000, 1100, 1200],
                "TOTAL_CURRENT_LIAB": [300, 330, 360],
                "TOTAL_NONCURRENT_LIAB": [200, 220, 240],
            },
            "cash_flow": {"NETCASH_OPERATE": [80, 90, 100]},
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": pe, "graham_number": 100},
        "risk": {"pledge_ratio": 30, "audit_opinion": "标准无保留意见"},
        "kline": {
            "turnover_rate": [0.3] * 60,
            "close": [10.0] * 60,
        },
    }


# ==================== 2.1 单只输入标记 subset + degraded ====================


def test_single_ticker_marks_subset_and_degraded():
    """单只输入：input_scale=="subset" 且 industry_pe_degraded==True.

    单只必然 < 300 → subset；compute_industry_median_pe 在样本数 < 5 时丢弃行业
    返回空 dict → industry_pe_degraded==True。
    """
    tickers = ["600519"]
    fake_all_data = {"600519": _make_ticker_data()}

    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        result = screen_a_shares(tickers)

    stats = result["stats"]
    assert stats["input_scale"] == "subset"
    assert stats["industry_pe_degraded"] is True


# ==================== 2.2 全市场输入标记 full_market + 非 degraded ====================


def test_full_market_marks_full_market_and_not_degraded():
    """≥300 只输入：input_scale=="full_market"；行业 PE 样本充足时 degraded==False.

    构造 305 只 ticker，其中 6 只同行业 "白酒" 且 PE>0 → compute_industry_median_pe
    返回 {"白酒": <median>} 非空 → industry_pe_degraded==False。
    """
    # 6 只白酒（达 MIN_INDUSTRY_SAMPLES=5 阈值），其余 299 只分散到其他行业
    tickers = [f"600{i:03d}" for i in range(305)]
    fake_all_data = {}
    for i, t in enumerate(tickers):
        if i < 6:
            industry, pe = "白酒", 25.0 + i
        else:
            # 其他行业每只独占一个行业名 → 样本数始终 1 < 5 → 不入 map
            industry, pe = f"行业{i}", 20.0
        td = _make_ticker_data(industry=industry, pe=pe)
        td["basic"]["code"] = t
        fake_all_data[t] = td

    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        result = screen_a_shares(tickers)

    stats = result["stats"]
    assert stats["input_scale"] == "full_market"
    assert stats["industry_pe_degraded"] is False


# ==================== 2.3 下游不读新字段 → 行为不变（回归） ====================


def test_scout_batch_only_reads_ticker_unchanged_by_new_stats():
    """L2 scout_batch 只读 candidate['ticker']：L1 输出含新 stats 字段不影响 L2 消费.

    用 scout_batch 现有测试已验证（test_scout_batch.py 的 candidates 都只有 ticker 字段）。
    此处补一条契约级断言：scout_batch 对 candidate 仅访问 .get('ticker')，
    即便 candidate 含完整 factor_scores/anti_trap 等字段也只取 ticker。
    """
    import asyncio
    import json
    from unittest.mock import AsyncMock

    from scout.batch import scout_batch

    # candidate 带 L1 全字段（含本次新增 stats 不在 candidate 里，stats 是顶层字段）
    candidates = [
        {
            "ticker": "600519",
            "name": "贵州茅台",
            "industry": "白酒",
            "factor_scores": {"composite": 80},
            "anti_trap": {"score": 95},
            "adjusted_composite": 76,
            "f_score": 8,
        }
    ]

    accessed_keys = []

    class TrackingDict(dict):
        def get(self, key, default=None):
            accessed_keys.append(key)
            return super().get(key, default)

    tracking_candidates = [TrackingDict(c) for c in candidates]

    async def mock_call(snapshot, system):
        return json.dumps({
            "verdict": "deep_dive",
            "confidence": 85,
            "one_liner": "test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        })

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = {
                "ticker": "600519",
                "name": "测试",
                "industry": "白酒",
                "market_cap": 1000,
                "pe_ttm": 20.0,
                "pb": 2.0,
                "pe_percentile_5y": 50.0,
                "roe_3y": [15.0, 16.0, 17.0],
                "roe_trend": "上升",
                "net_margin": 10.0,
                "debt_ratio": 50.0,
                "goodwill_ratio": 5.0,
                "operating_cashflow": 100.0,
                "net_profit": 80.0,
                "cashflow_match": "匹配",
                "revenue_growth": 10.0,
                "pledge_ratio": 10.0,
                "price_change_60d": 5.0,
                "turnover_avg_percentile_60d": 50.0,
                "f_score": 7,
            }
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                result = asyncio.run(scout_batch(tracking_candidates, force=True))

    # 只返回 deep_dive 的那只
    assert len(result) == 1
    assert result[0]["ticker"] == "600519"
    # 关键契约：scout_batch 仅访问 candidate 的 'ticker' 字段
    # （不读 factor_scores / anti_trap / adjusted_composite 等 L1 产出）
    non_ticker_accesses = [k for k in accessed_keys if k != "ticker"]
    assert non_ticker_accesses == [], (
        f"scout_batch 访问了 candidate 的非 ticker 字段: {non_ticker_accesses}，"
        "违反 L2 只读 ticker 契约"
    )


def test_aggregate_watchlist_unchanged_by_new_stats(tmp_path):
    """L4 aggregate_watchlist 读 L1 文件只取 candidates 列表、不读 stats → 新字段无影响.

    构造一份 L1 输出文件（candidates 含 ticker + 几个 aggregation 读取的字段，
    stats 含本次新增的 industry_pe_degraded / input_scale），跑 aggregate_watchlist
    断言 candidates 数量与 ticker 不变。
    """
    import json
    from monitor.aggregation import aggregate_watchlist

    l1_data = {
        "run_date": "2026-07-01",
        "candidates": [
            {
                "ticker": "600519.SH",
                "name": "贵州茅台",
                "adjusted_composite": 76.0,
                "f_score": 8,
                "pe_ttm": 38.5,
                "pb": 8.2,
                "pledge_ratio": 12.5,
            },
            {
                "ticker": "000858.SZ",
                "name": "五粮液",
                "adjusted_composite": 70.0,
                "f_score": 7,
                "pe_ttm": 25.0,
                "pb": 5.0,
                "pledge_ratio": 20.0,
            },
        ],
        "stats": {
            "total": 2,
            "after_hard_gates": 2,
            "after_factors": 2,
            "after_heat_filter": 2,
            "excluded_by_gates": {},
            # 本次新增字段
            "industry_pe_degraded": True,
            "input_scale": "subset",
        },
    }
    l1_file = tmp_path / "l1.json"
    l1_file.write_text(json.dumps(l1_data), encoding="utf-8")

    with patch("monitor.aggregation.ScoutCache") as MockSC:
        MockSC.return_value.get.return_value = None  # 无 L2 缓存
        # stage=l1 时不触网，但 _supplement_pe_percentile 会建 ValuationFetcher/CacheManager
        # mock 掉避免真实采集
        with patch("monitor.aggregation.ValuationFetcher"), \
             patch("monitor.aggregation.CacheManager"):
            watchlist = aggregate_watchlist(
                run_date="2026-07-01",
                l1_output_file=str(l1_file),
                watchlist_dir=tmp_path / "watchlist",
            )

    # candidates 数量与 ticker 不变（stats 新字段未干扰聚合）
    assert watchlist["l1_candidates"] == 2
    tickers = [c["ticker"] for c in watchlist["candidates"]]
    assert "600519.SH" in tickers
    assert "000858.SZ" in tickers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
