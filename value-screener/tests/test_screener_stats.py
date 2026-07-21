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
        # f1-deviation-fix §7：call_llm 返回 (content, usage)
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": 85,
            "one_liner": "test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})

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
                result, _usage, _failure = asyncio.run(scout_batch(tracking_candidates, force=True))

    # full_results 含该只（输入 1 只全 deep_dive）
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


# ==================== g1-staged-fetch-boundary：L1 采集维度白名单 ====================


def test_screen_a_shares_passes_g1_quant_dimensions_excluding_dossier():
    """screen_a_shares 调 fetch_all 时 MUST 显式传 G1 量化五维白名单，不含 dossier 三维.

    对应 spec `staged-fetch-boundary` / `quantitative-screener` 的 fetch 边界 requirement。
    红测：当前 screen_a_shares 调 fetch_all 不传 dimensions（等价全采 8 维），
    断言 fetch_all 收到的 dimensions 恰为五维白名单 → 当前会失败（红）。
    """
    from screener.main import G1_QUANT_DIMENSIONS

    tickers = ["600519"]
    fake_all_data = {"600519": _make_ticker_data()}

    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        screen_a_shares(tickers)

    # 断言 fetch_all 收到的 dimensions 参数恰为 G1_QUANT_DIMENSIONS
    fetch_all_call = MockBF.return_value.fetch_all
    assert fetch_all_call.called, "fetch_all 未被调用"
    # call_args: (tickers, dimensions) 位置参数；dimensions 是第二位置参
    call_args = fetch_all_call.call_args
    # 优先按位置参数取（screen_a_shares 应以位置参传 dimensions）
    if call_args.args and len(call_args.args) >= 2:
        passed_dims = call_args.args[1]
    else:
        passed_dims = call_args.kwargs.get("dimensions")

    assert passed_dims == G1_QUANT_DIMENSIONS, (
        f"screen_a_shares 应传 G1_QUANT_DIMENSIONS={G1_QUANT_DIMENSIONS}，"
        f"实际传了 {passed_dims!r}"
    )
    # 显式排除 dossier 三维（防止未来白名单被误改）
    dossier_dims = ("main_business", "peers", "research")
    for d in dossier_dims:
        assert d not in passed_dims, (
            f"dossier 维度 {d!r} 不应出现在 L1 采集白名单中"
        )


def test_g1_quant_dimensions_constant_exposed_and_ordered():
    """G1_QUANT_DIMENSIONS SHALL 为 screener.main 模块级常量，且值为 G1 量化五维有序集合.

    红测：当前 main.py 无 G1_QUANT_DIMENSIONS 常量 → ImportError（红）。
    """
    from screener.main import G1_QUANT_DIMENSIONS

    assert G1_QUANT_DIMENSIONS == ("basic", "financials", "kline", "valuation", "risk")


# ==================== g1-staged-fetch-boundary：漏斗 ticker 集合逐层缩小 ====================


def test_funnel_counts_monotonically_non_increasing():
    """漏斗计数 SHALL 反向单调：total >= after_hard_gates >= after_factors >= after_heat_filter.

    构造混合样本：部分不过 hard_gates（market_cap<50亿）、部分不过 heat_filter（涨幅>20%）。
    对应 spec `staged-fetch-boundary` 的漏斗缩小 requirement。
    """

    def _passing_ticker(code):
        """能过 hard_gates 且能过 heat_filter 的样本。"""
        return _make_ticker_data()

    def _failing_hard_gate_ticker(code):
        """不过 hard_gates：市值 < 50 亿（H3）。"""
        td = _make_ticker_data()
        td["basic"]["market_cap"] = 1e8  # 1 亿 < 50 亿
        td["basic"]["code"] = code
        return td

    def _failing_heat_filter_ticker(code):
        """能过 hard_gates 但不过 heat_filter：近 60 日涨幅 >20%（HF2）。"""
        td = _make_ticker_data()
        td["basic"]["code"] = code
        # close[-60]=10, close[-1]=15 → 涨幅 50% > 20%
        td["kline"]["close"] = [10.0] * 59 + [15.0]
        return td

    tickers = ["600001", "600002", "600003", "600004", "600005", "600006"]
    fake_all_data = {
        "600001": _passing_ticker("600001"),
        "600002": _passing_ticker("600002"),
        "600003": _failing_hard_gate_ticker("600003"),  # 不过 hard_gates
        "600004": _failing_hard_gate_ticker("600004"),  # 不过 hard_gates
        "600005": _failing_heat_filter_ticker("600005"),  # 过 hard_gates 不过 heat
        "600006": _passing_ticker("600006"),
    }

    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        result = screen_a_shares(tickers)

    stats = result["stats"]
    total = stats["total"]
    after_hard_gates = stats["after_hard_gates"]
    after_factors = stats["after_factors"]
    after_heat_filter = stats["after_heat_filter"]

    # 6 只输入，2 只不过 hard_gates → after_hard_gates = 4
    assert total == 6
    assert after_hard_gates == 4, f"expected 4 pass hard_gates, got {after_hard_gates}"
    # 反向单调
    assert total >= after_hard_gates >= after_factors >= after_heat_filter, (
        f"漏斗计数非反向单调: total={total} >= after_hard_gates={after_hard_gates} "
        f">= after_factors={after_factors} >= after_heat_filter={after_heat_filter}"
    )
    # 600005 过 hard_gates 但不过 heat_filter → after_heat_filter 至少比 after_hard_gates 少 1
    assert after_heat_filter <= after_hard_gates - 1


def test_top300_truncation_activates():
    """超过 300 只全过 hard_gates 时，after_factors SHALL == 300，激活 [:300] 截断.

    对应 spec `staged-fetch-boundary` 的漏斗缩小 requirement（top-300 阶段集合缩小）。
    补 item 4：6 只样本无法激活截断，本测试用 305 只全过 hard_gates 样本证明
    top-300 阶段把 after_hard_gates(305) 缩小到 after_factors(300)。
    """
    n = 305
    tickers = [f"600{i:03d}" for i in range(n)]
    fake_all_data = {}
    for i, t in enumerate(tickers):
        td = _make_ticker_data()
        td["basic"]["code"] = t
        # 给每只不同的 pe 让 composite 有区分度，避免并列排序影响截断边界断言
        td["basic"]["pe"] = 20.0 + i
        td["valuation"]["pe_ttm"] = 20.0 + i
        fake_all_data[t] = td

    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        result = screen_a_shares(tickers)

    stats = result["stats"]
    assert stats["total"] == n
    assert stats["after_hard_gates"] == n, (
        f"305 只全过 hard_gates，expected after_hard_gates={n}，got {stats['after_hard_gates']}"
    )
    # top-300 截断激活：after_factors 恰为 300
    assert stats["after_factors"] == 300, (
        f"[:300] 截断应激活，expected after_factors=300，got {stats['after_factors']}"
    )
    # 截断证明 top-300 阶段集合缩小：305 → 300
    assert stats["after_factors"] < stats["after_hard_gates"]
    # 候选输出 = heat_filter 后，不超 300
    assert stats["after_heat_filter"] <= stats["after_factors"] <= 300


# ==================== g1-staged-fetch-boundary：单股失败隔离不回归 ====================


def test_single_ticker_dim_error_does_not_break_batch():
    """单只股票某量化维度采集失败（__error__）SHALL 不阻断整批 screen_a_shares.

    对应 spec `staged-fetch-boundary` 的失败隔离不回归 requirement。
    构造两只：一只 basic 维度返回 __error__（整体仍可被 hard_gates 处理，只是缺字段），
    另一只正常。断言 screen_a_shares 不抛异常、正常 ticker 仍进漏斗。
    """
    tickers = ["600519", "600520"]
    good = _make_ticker_data()
    good["basic"]["code"] = "600519"

    bad = _make_ticker_data()
    bad["basic"]["code"] = "600520"
    # 模拟该 ticker 的 basic 维度采集失败（BatchFetcher._fetch_one 返回 __error__ 结构）
    bad["basic"] = {"__error__": True, "reason": "fetch failed"}

    fake_all_data = {"600519": good, "600520": bad}

    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        # 不应抛异常
        result = screen_a_shares(tickers)

    stats = result["stats"]
    # 600519 正常 → 应进入漏斗；600520 basic 失败（market_cap=None）不误触 gate
    # 但 hard_gates 容错：market_cap 为 None 时跳过 H3，可能仍 pass
    # 关键断言：整批不抛异常 + 至少 600519 进入 candidates
    assert stats["total"] == 2
    candidate_tickers = [c["ticker"] for c in result["candidates"]]
    assert "600519" in candidate_tickers, "正常 ticker 应进入最终候选池"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
