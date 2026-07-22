"""Tests for scout/batch.py (tasks 6.7, 6.8, 6.11)."""
import sys
from pathlib import Path
import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scout.batch import scout_batch, call_llm_snapshot

# f1-deviation-fix §7：call_llm（含 call_llm_light/call_llm_snapshot 别名）返回 (content, usage)
LLM_USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


# ── P1 修复（review 反馈）：scout_batch 返回 (shortlist, usage_summary)，累加所有 LLM 调用 ──

def test_scout_batch_returns_tuple_with_usage_summary():
    """scout_batch 返回 (full_results, usage_summary, failure_summary)，usage_summary 含所有调用的 token（非仅 deep_dive）.

    g1-l2-full-result-contract Task 3：三元组升级后 usage_summary 契约不回归——
    第二项仍是 usage_summary，累加所有 LLM 调用（含 watch/skip/error 路径）。
    """
    candidates = [{"ticker": "600001"}, {"ticker": "600002"}, {"ticker": "600003"}]
    call_seq = ["deep_dive", "watch", "skip"]  # 第 1 次 deep_dive、第 2 次 watch、第 3 次 skip
    call_idx = {"i": 0}

    async def mock_call(snapshot, system):
        # 按调用次序返回不同 verdict，验证 watch/skip 的 usage 也被累加（非仅 deep_dive）
        verdict = call_seq[call_idx["i"] % len(call_seq)]
        call_idx["i"] += 1
        return (json.dumps({
            "verdict": verdict,
            "confidence": 80,
            "one_liner": "test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = {"name": "x", "market_cap": 1, "pe_ttm": 10,
                                          "roe_3y": [1, 2, 3], "net_margin": 5}
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                result = asyncio.run(scout_batch(candidates, force=True))

    # 返回三元组
    assert isinstance(result, tuple) and len(result) == 3
    full_results, usage, failure = result
    # full_results 含全量 3 只（含 watch/skip）
    assert len(full_results) == 3
    # usage_summary 累加了所有 3 次调用（deep_dive + watch + skip），不是只 1 次
    assert usage["call_count"] == 3
    assert usage["prompt_tokens"] == 300  # 3 × 100
    assert usage["completion_tokens"] == 150  # 3 × 50
    assert usage["total_tokens"] == 450  # 3 × 150


def test_scout_batch_usage_summary_counts_cache_hits_separately():
    """cache hit 不产生新 LLM 调用（不计入 call_count），但 cache_hits 单独计数."""
    candidates = [{"ticker": "600001"}, {"ticker": "600002"}]

    async def mock_call(snapshot, system):
        return (json.dumps({"verdict": "deep_dive", "confidence": 80, "one_liner": "t",
                            "red_flags": [], "green_flags": [], "anti_trap_flags": []}),
                {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot"):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                # 600001 cache hit（含 usage），600002 cache miss
                # g1-canonical-run-identity: cache.get 现传 run_id/profile_version kwargs，
                # mock 签名用 **kwargs 兼容。
                def cache_get(ticker, date_str, **kwargs):
                    if ticker == "600001":
                        return {"verdict": "deep_dive", "confidence": 80, "one_liner": "cached",
                                "red_flags": [], "green_flags": [], "anti_trap_flags": []}
                    return None
                mock_cache.get.side_effect = cache_get
                full_results, usage, _failure = asyncio.run(scout_batch(candidates, force=False))

    # 600001 cache hit → 不调 LLM；600002 cache miss → 调 1 次
    assert usage["call_count"] == 1
    assert usage["cache_hits"] == 1
    assert usage["prompt_tokens"] == 100  # 仅 600002 的 1 次


def test_scout_batch_top20_cap():
    """验证 top-20 cap: 40 只 deep_dive 只返回前 20."""
    # 创建 40 只候选，全部返回 deep_dive（confidence 从 100 到 61）
    candidates = [{"ticker": f"600{i:03d}"} for i in range(40)]

    async def mock_call(snapshot, system):
        # 根据 ticker 生成不同的 confidence
        ticker = snapshot.split("(")[1].split(")")[0]
        idx = int(ticker[3:])
        confidence = 100 - idx
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": confidence,
            "one_liner": f"Stock {ticker}",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            # Mock assemble_snapshot 返回基本特征
            mock_assemble.return_value = {
                "ticker": "600000",
                "name": "测试股票",
                "industry": "测试行业",
                "market_cap": 1000,
                "pe_ttm": 20.0,
                "pb": 2.0,
                "pe_percentile_5y": 50.0,
                "roe_3y": [15.0, 16.0, 17.0],
                "roe_trend": "趋势上升",
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
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None  # 缓存未命中

                full_results, _usage, _failure = asyncio.run(scout_batch(candidates, force=True))

                # g1-l2-full-result-contract：full_results 含全部 40 只（不再只留 deep_dive）
                assert len(full_results) == 40
                # shortlist 由消费方派生：deep_dive 按 confidence 降序取前 20（top-20 cap）
                shortlist = sorted(
                    [r for r in full_results if r["verdict"] == "deep_dive"],
                    key=lambda x: x.get("confidence", 0), reverse=True
                )[:20]
                # 验证只返回 20 只
                assert len(shortlist) == 20
                # 验证按 confidence 降序排序
                confidences = [r["confidence"] for r in shortlist]
                assert confidences == sorted(confidences, reverse=True)


def test_scout_batch_error_handling():
    """验证 per-candidate error handling: LLM 调用失败不阻塞整批."""
    candidates = [
        {"ticker": "600001"},
        {"ticker": "600002"},
        {"ticker": "600003"},
    ]

    async def mock_call(snapshot, system):
        ticker = snapshot.split("(")[1].split(")")[0]
        if ticker == "600002":
            raise httpx.HTTPStatusError("LLM API error", request=None, response=None)
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": 85,
            "one_liner": f"Stock {ticker}",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    def mock_assemble(ticker, cache_manager=None, **kwargs):
        return {
            "ticker": ticker,
            "name": "测试股票",
            "industry": "测试行业",
            "market_cap": 1000,
            "pe_ttm": 20.0,
            "pb": 2.0,
            "pe_percentile_5y": 50.0,
            "roe_3y": [15.0, 16.0, 17.0],
            "roe_trend": "趋势上升",
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

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None

                full_results, _usage, failure = asyncio.run(scout_batch(candidates, force=True))

                # g1-l2-full-result-contract：full_results 含全部 3 只（600002 verdict=error 仍在）
                assert len(full_results) == 3
                # shortlist 派生：2 只 deep_dive（600002 失败不进 deep_dive）
                shortlist = [r for r in full_results if r["verdict"] == "deep_dive"]
                assert len(shortlist) == 2
                shortlist_tickers = [r["ticker"] for r in shortlist]
                assert "600001" in shortlist_tickers
                assert "600003" in shortlist_tickers
                assert "600002" not in shortlist_tickers
                # failure_summary 定位 600002 失败
                assert "600002" in [e["ticker"] for e in failure["errors"]]


def test_scout_batch_insufficient_data():
    """验证 insufficient data handling: 数据不足的候选被跳过."""
    candidates = [
        {"ticker": "600001"},
        {"ticker": "600002"},  # 数据不足
        {"ticker": "600003"},
    ]

    def mock_assemble(ticker, cache_manager=None, **kwargs):
        if ticker == "600002":
            return {"error": "insufficient_data", "missing_fields": ["name", "industry"]}
        return {
            "ticker": ticker,
            "name": "测试股票",
            "industry": "测试行业",
            "market_cap": 1000,
            "pe_ttm": 20.0,
            "pb": 2.0,
            "pe_percentile_5y": 50.0,
            "roe_3y": [15.0, 16.0, 17.0],
            "roe_trend": "趋势上升",
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

    async def mock_call(snapshot, system):
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": 85,
            "one_liner": "Test stock",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None

                full_results, _usage, failure = asyncio.run(scout_batch(candidates, force=True))

                # g1-l2-full-result-contract：full_results 含全部 3 只（600002 数据不足 verdict=error 仍在）
                assert len(full_results) == 3
                # shortlist 派生：2 只 deep_dive（600002 数据不足不进 deep_dive）
                shortlist = [r for r in full_results if r["verdict"] == "deep_dive"]
                assert len(shortlist) == 2
                shortlist_tickers = [r["ticker"] for r in shortlist]
                assert "600001" in shortlist_tickers
                assert "600003" in shortlist_tickers
                assert "600002" not in shortlist_tickers
                # failure_summary 定位 600002 失败
                assert "600002" in [e["ticker"] for e in failure["errors"]]


def test_scout_batch_cache_hit():
    """验证缓存命中: 缓存有效的候选不调用 LLM."""
    candidates = [
        {"ticker": "600001"},
        {"ticker": "600002"},
    ]

    with patch("scout.batch.ScoutCache") as mock_cache_cls:
        mock_cache = mock_cache_cls.return_value

        # 600001 缓存命中，600002 缓存未命中
        # g1-canonical-run-identity: cache.get 现传 run_id/profile_version kwargs，mock 用 **kwargs 兼容
        def mock_get(ticker, date_str, **kwargs):
            if ticker == "600001":
                return {
                    "verdict": "deep_dive",
                    "confidence": 90,
                    "one_liner": "Cached result",
                    "red_flags": [],
                    "green_flags": [],
                    "anti_trap_flags": [],
                }
            return None

        mock_cache.get.side_effect = mock_get

        async def mock_call(snapshot, system):
            return (json.dumps({
                "verdict": "deep_dive",
                "confidence": 80,
                "one_liner": "Fresh result",
                "red_flags": [],
                "green_flags": [],
                "anti_trap_flags": [],
            }), LLM_USAGE)

        with patch("scout.batch.call_llm_snapshot", new=mock_call):
            with patch("scout.batch.assemble_snapshot") as mock_assemble:
                mock_assemble.return_value = {
                    "ticker": "600002",
                    "name": "测试股票",
                    "industry": "测试行业",
                    "market_cap": 1000,
                    "pe_ttm": 20.0,
                    "pb": 2.0,
                    "pe_percentile_5y": 50.0,
                    "roe_3y": [15.0, 16.0, 17.0],
                    "roe_trend": "趋势上升",
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

                full_results, _usage, _failure = asyncio.run(scout_batch(candidates, force=False))

                # g1-l2-full-result-contract：full_results 含全部 2 只（cache hit + fresh）
                assert len(full_results) == 2
                # 验证 600001 来自缓存
                r_600001 = next(r for r in full_results if r["ticker"] == "600001")
                assert r_600001["confidence"] == 90
                assert r_600001.get("from_cache") is True
                # 验证 600002 是新调用
                r_600002 = next(r for r in full_results if r["ticker"] == "600002")
                assert r_600002["confidence"] == 80


def test_call_llm_snapshot_env_validation():
    """验证 call_llm_snapshot 环境变量校验（fail-fast）."""
    with patch.dict("os.environ", {}, clear=True):
        # 缺少所有环境变量
        try:
            asyncio.run(call_llm_snapshot("test snapshot", "test prompt"))
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "missing required env var" in str(e)


def test_scout_batch_cache_write_failure():
    """验证 cache.set OSError 不丢结果（LLM 已调用，结果应返回）."""
    candidates = [{"ticker": "600001"}]

    async def mock_call(snapshot, system):
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": 90,
            "one_liner": "Test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = {
                "ticker": "600001",
                "name": "测试股票",
                "industry": "测试行业",
                "market_cap": 1000,
                "pe_ttm": 20.0,
                "pb": 2.0,
                "pe_percentile_5y": 50.0,
                "roe_3y": [15.0, 16.0, 17.0],
                "roe_trend": "趋势上升",
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
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None
                mock_cache.set.side_effect = OSError("Disk full")

                full_results, _usage, _failure = asyncio.run(scout_batch(candidates, force=True))

                # g1-l2-full-result-contract：即使缓存写入失败，full_results 仍返回
                assert len(full_results) == 1
                assert full_results[0]["ticker"] == "600001"
                assert full_results[0]["verdict"] == "deep_dive"
                assert full_results[0]["confidence"] == 90


# ── f2 §6.3 L2 降级处理 ────────────────────────────────────────

def test_scout_batch_degraded_financials_gap_to_watch():
    """f2 §6.3: assemble_snapshot 返回 degraded=True 时，batch 标 watch + confidence_cap=50
    + degraded，不调 LLM（数据不全不调 LLM 编造 + 省钱），不进 deep_dive 短名单。
    """
    candidates = [{"ticker": "600002"}]

    async def mock_call(snapshot, system):
        # 降级票不应调 LLM——若调用即测试失败
        raise AssertionError("降级票不应调 LLM")

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            # critical 齐但 financials_floor 不齐 → degraded=True + partial features
            mock_assemble.return_value = {
                "name": "测试",
                "market_cap": 100,
                "degraded": True,
                "degraded_reason": "financials_floor 缺失 pe_ttm",
            }
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                full_results, usage, failure = asyncio.run(scout_batch(candidates, force=True))

    # g1-l2-full-result-contract：full_results 含降级票（verdict=watch），不再丢弃
    assert len(full_results) == 1
    assert full_results[0]["verdict"] == "watch"
    assert full_results[0].get("degraded") is True
    # shortlist 派生：deep_dive 不应含降级票
    shortlist = [r for r in full_results if r["verdict"] == "deep_dive"]
    assert shortlist == []
    # usage 应有降级票的记录但不产生 LLM token（call_count=0）
    assert usage["call_count"] == 0
    # failure_summary：degraded 单独计（不进 errors）
    assert failure["degraded"] == 1
    assert failure["watches"] == 1
    assert failure["errors"] == []

    # 验证 batch 调 assemble_snapshot 时传了 degrade_on_financials_gap=True
    assert mock_assemble.call_args is not None
    assert mock_assemble.call_args.kwargs.get("degrade_on_financials_gap") is True


def test_scout_batch_degraded_not_in_deep_dive_shortlist():
    """f2 §6.3: 降级票不进 deep_dive 短名单（即使 confidence 被错误标高）。

    降级票 confidence 强制 cap=50 + verdict=watch，watch 不进 deep_dive。
    但 watchlist/usage_summary 仍累加（不丢结果）。
    """
    candidates = [{"ticker": "600003"}]

    with patch("scout.batch.call_llm_snapshot", new=AsyncMock()):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = {
                "name": "测试",
                "market_cap": 100,
                "degraded": True,
                "degraded_reason": "financials_floor 缺失",
            }
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                full_results, usage, failure = asyncio.run(scout_batch(candidates, force=True))

    # g1-l2-full-result-contract：降级票在 full_results（verdict=watch），不进 deep_dive
    assert len(full_results) == 1
    assert full_results[0]["verdict"] == "watch"
    shortlist = [r for r in full_results if r["verdict"] == "deep_dive"]
    assert shortlist == []
    # usage_summary 仍累加（降级票虽不调 LLM，但计为处理过）
    assert usage["call_count"] == 0
    # failure_summary：degraded 单独计
    assert failure["degraded"] == 1


# ── g1-l2-full-result-contract：scout_batch 返回三元组 (full_results, usage_summary, failure_summary) ──


def test_scout_batch_returns_triple_with_full_results():
    """scout_batch SHALL 返回三元组，full_results 含每只输入的 verdict 分类，不丢 watch/skip.

    对应 spec `scout-agent` 的「L2 全量结果契约」requirement / Scenario「全量结果含所有分类」。
    红测：当前 scout_batch 返回二元组 (shortlist, usage)，断言三元组 + full_results 长度==3
    含 deep_dive/watch/skip 三分类 → 当前会失败（红）。
    """
    candidates = [{"ticker": "600001"}, {"ticker": "600002"}, {"ticker": "600003"}]
    call_seq = ["deep_dive", "watch", "skip"]  # 三种 verdict 各一只
    call_idx = {"i": 0}

    async def mock_call(snapshot, system):
        verdict = call_seq[call_idx["i"] % len(call_seq)]
        call_idx["i"] += 1
        return (json.dumps({
            "verdict": verdict,
            "confidence": 80,
            "one_liner": "test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = {"name": "x", "market_cap": 1, "pe_ttm": 10,
                                          "roe_3y": [1, 2, 3], "net_margin": 5}
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                result = asyncio.run(scout_batch(candidates, force=True))

    # 返回三元组
    assert isinstance(result, tuple), f"scout_batch 应返回三元组，got {type(result)}"
    assert len(result) == 3, f"三元组应有 3 项，got {len(result)}"
    full_results, usage, failure = result

    # full_results 长度 == 输入候选数 3（含 watch/skip，不再只留 deep_dive）
    assert len(full_results) == 3, (
        f"full_results 应含所有 3 只输入（含 watch/skip），got {len(full_results)}"
    )
    verdicts = sorted(r["verdict"] for r in full_results)
    assert verdicts == ["deep_dive", "skip", "watch"], (
        f"full_results 应含 deep_dive/watch/skip 三分类，got {verdicts}"
    )


def test_scout_batch_returns_shortlist_derived_from_full_results():
    """shortlist SHALL 由消费方从 full_results 派生，不是 scout_batch 的独立返回项.

    对应 spec「L2 全量结果契约」/ Scenario「shortlist 由全量结果派生」。
    scout_batch 返回三元组 (full_results, usage_summary, failure_summary)——
    第二项是 usage_summary 不是 shortlist。
    红测：当前第二项是 usage_summary（已是），但断言 shortlist 可从 full_results 派生为
    deep_dive 按 confidence 降序取前 20 → 验证派生关系成立。
    """
    # 构造 3 只 deep_dive（不同 confidence）+ 2 只 watch/skip
    candidates = [{"ticker": f"60000{i}"} for i in range(5)]
    # 按调用次序：deep_dive(85)/watch(70)/deep_dive(95)/skip(60)/deep_dive(90)
    call_seq = [
        ("deep_dive", 85),
        ("watch", 70),
        ("deep_dive", 95),
        ("skip", 60),
        ("deep_dive", 90),
    ]
    call_idx = {"i": 0}

    async def mock_call(snapshot, system):
        verdict, confidence = call_seq[call_idx["i"] % len(call_seq)]
        call_idx["i"] += 1
        return (json.dumps({
            "verdict": verdict,
            "confidence": confidence,
            "one_liner": "test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = {"name": "x", "market_cap": 1, "pe_ttm": 10,
                                          "roe_3y": [1, 2, 3], "net_margin": 5}
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                result = asyncio.run(scout_batch(candidates, force=True))

    full_results, usage, failure = result

    # 第二项是 usage_summary（不是 shortlist）
    assert "call_count" in usage, "三元组第二项应是 usage_summary"
    assert "errors" in failure, "三元组第三项应是 failure_summary"

    # shortlist 由消费方从 full_results 派生：deep_dive 按 confidence 降序
    shortlist = sorted(
        [r for r in full_results if r["verdict"] == "deep_dive"],
        key=lambda x: x.get("confidence", 0), reverse=True
    )[:20]
    assert len(shortlist) == 3, f"deep_dive 应有 3 只，got {len(shortlist)}"
    # 按 confidence 降序：95 > 90 > 85
    assert [r["confidence"] for r in shortlist] == [95, 90, 85], (
        f"shortlist 应按 confidence 降序派生，got {[r['confidence'] for r in shortlist]}"
    )


def test_scout_batch_failure_summary_locates_error_ticker():
    """failure_summary["errors"] SHALL 含 {ticker, reason, stage}，可定位失败 ticker.

    对应 spec「L2 全量结果契约」/ Scenario「failure_summary 可定位失败 ticker 与原因」。
    构造 600002 的 LLM 调用抛 httpx.HTTPStatusError，断言 errors 含其 ticker/reason/stage，
    其他成功候选仍在 full_results。
    """
    candidates = [{"ticker": "600001"}, {"ticker": "600002"}, {"ticker": "600003"}]

    async def mock_call(snapshot, system):
        # 用 call_idx 区分，避免依赖 snapshot 文本解析 ticker
        # 但这里需要精确定位 600002 抛错——用 candidates 顺序对齐
        ticker = snapshot.split("(")[1].split(")")[0] if "(" in snapshot else None
        if ticker == "600002" or "600002" in snapshot:
            raise httpx.HTTPStatusError("LLM API error", request=None, response=None)
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": 85,
            "one_liner": f"Stock {ticker}",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    def mock_assemble(ticker, cache_manager=None, **kwargs):
        return {
            "ticker": ticker,
            "name": "测试股票",
            "industry": "测试行业",
            "market_cap": 1000,
            "pe_ttm": 20.0,
            "pb": 2.0,
            "pe_percentile_5y": 50.0,
            "roe_3y": [15.0, 16.0, 17.0],
            "roe_trend": "趋势上升",
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

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                full_results, _usage, failure = asyncio.run(scout_batch(candidates, force=True))

    # failure_summary["errors"] 含 600002 的 ticker/reason/stage
    error_tickers = [e["ticker"] for e in failure["errors"]]
    assert "600002" in error_tickers, (
        f"errors 应含失败 ticker 600002，got {error_tickers}"
    )
    err_entry = next(e for e in failure["errors"] if e["ticker"] == "600002")
    assert "reason" in err_entry and err_entry["reason"], "error entry 应含 reason"
    assert err_entry.get("stage") == "scout", f"error entry 应含 stage='scout'，got {err_entry.get('stage')}"
    # 其他成功候选仍在 full_results
    result_tickers = [r["ticker"] for r in full_results]
    assert "600001" in result_tickers and "600003" in result_tickers, (
        "成功候选应仍在 full_results"
    )


def test_scout_batch_failure_summary_counts_separated():
    """failure_summary SHALL 把 error/skip/watch/degraded 分开计数.

    对应 spec「L2 全量结果契约」/ Scenario「error/skip/watch/degraded 分开计数」。
    构造 1 error/2 skip/1 degraded→watch/1 deep_dive，断言分开计数：
    errors=1, skips=2, watches=1, degraded=1, unhandled_exceptions=0。
    """
    candidates = [{"ticker": f"60000{i}"} for i in range(5)]
    # 按调用次序：error(抛异常)/skip/degraded→watch(skip LLM)/skip/deep_dive
    # 注意 degraded 票不调 LLM（assemble 返回 degraded=True），call_idx 只对非 degraded 票递增
    call_seq = ["skip", "skip", "deep_dive"]  # 600002/600005 skip, 600003 error(抛), 600001 deep_dive
    # 候选顺序：600001 deep_dive / 600002 error / 600003 degraded / 600004 skip / 600005 skip
    call_idx = {"i": 0}

    def mock_assemble(ticker, cache_manager=None, **kwargs):
        # 600003 触发降级（degraded=True，不调 LLM）
        if ticker == "600003":
            return {"name": "测试", "market_cap": 100, "degraded": True,
                    "degraded_reason": "financials_floor 缺失"}
        return {
            "ticker": ticker,
            "name": "测试股票",
            "industry": "测试行业",
            "market_cap": 1000,
            "pe_ttm": 20.0,
            "roe_3y": [15.0, 16.0, 17.0],
            "net_margin": 10.0,
        }

    async def mock_call(snapshot, system):
        # 600002 抛异常
        if "600002" in snapshot:
            raise httpx.HTTPStatusError("LLM API error", request=None, response=None)
        # 其他按 call_seq 返回 skip/skip/deep_dive
        verdict = call_seq[call_idx["i"] % len(call_seq)]
        call_idx["i"] += 1
        return (json.dumps({
            "verdict": verdict,
            "confidence": 80,
            "one_liner": "test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                _full, _usage, failure = asyncio.run(scout_batch(candidates, force=True))

    # 分开计数：errors=1(600002), skips=2(600004/600005), watches=1(600003 degraded→watch),
    # degraded=1(600003), unhandled_exceptions=0
    assert failure["unhandled_exceptions"] == 0, (
        f"整批无未处理异常，got unhandled_exceptions={failure['unhandled_exceptions']}"
    )
    assert len(failure["errors"]) == 1, f"errors 应为 1（600002），got {failure['errors']}"
    assert failure["skips"] == 2, f"skips 应为 2，got {failure['skips']}"
    assert failure["watches"] == 1, f"watches 应为 1（600003 degraded→watch），got {failure['watches']}"
    assert failure["degraded"] == 1, f"degraded 应为 1（600003），got {failure['degraded']}"
    # degraded 不进 errors
    error_tickers = [e["ticker"] for e in failure["errors"]]
    assert "600003" not in error_tickers, "degraded 票不应计入 errors"


def test_scout_batch_unhandled_exceptions_zero():
    """非预期异常 SHALL 计入 errors，unhandled_exceptions == 0，整批不中断.

    对应 spec「L2 全量结果契约」/ Scenario「整批无未处理异常」。
    构造 assemble_snapshot 抛 TypeError（非 httpx 异常，触发 process_one 兜底 except Exception），
    断言该只进 errors，unhandled_exceptions==0，其他候选仍处理。
    """
    candidates = [{"ticker": "600001"}, {"ticker": "600002"}, {"ticker": "600003"}]

    def mock_assemble(ticker, cache_manager=None, **kwargs):
        if ticker == "600002":
            raise TypeError("脏数据类型错位")
        return {
            "ticker": ticker,
            "name": "测试股票",
            "industry": "测试行业",
            "market_cap": 1000,
            "pe_ttm": 20.0,
            "roe_3y": [15.0, 16.0, 17.0],
            "net_margin": 10.0,
        }

    async def mock_call(snapshot, system):
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": 85,
            "one_liner": "test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                full_results, _usage, failure = asyncio.run(scout_batch(candidates, force=True))

    # 600002 进 errors（兜底捕获 TypeError），unhandled_exceptions==0
    assert failure["unhandled_exceptions"] == 0, (
        f"兜底异常应已捕获，unhandled_exceptions==0，got {failure['unhandled_exceptions']}"
    )
    error_tickers = [e["ticker"] for e in failure["errors"]]
    assert "600002" in error_tickers, (
        f"600002 的 TypeError 应计入 errors，got {error_tickers}"
    )
    # 整批不中断：其他两只仍处理
    result_tickers = [r["ticker"] for r in full_results]
    assert "600001" in result_tickers and "600003" in result_tickers, "整批应继续处理其他候选"


# ── g1-l2-full-result-contract review 修复：full_results 长度 == N + error 字段契约 ──


def test_scout_batch_missing_ticker_still_in_full_results():
    """缺 ticker 的输入（{''} 无 ticker）SHALL 仍在 full_results，长度 == N，verdict=error.

    对应 review 阻断1：缺 ticker 的 candidate 原 return None 被过滤 → full_results 丢一条。
    修复后返回 error result（ticker=None + input_index 定位），进 full_results + errors。
    """
    candidates = [{"ticker": "600001"}, {}, {"ticker": "600003"}]  # 第 2 只缺 ticker

    async def mock_call(snapshot, system):
        return (json.dumps({"verdict": "deep_dive", "confidence": 80, "one_liner": "t",
                            "red_flags": [], "green_flags": [], "anti_trap_flags": []}),
                LLM_USAGE)

    def mock_assemble(ticker, cache_manager=None, **kwargs):
        return {"ticker": ticker, "name": "x", "market_cap": 1, "pe_ttm": 10,
                "roe_3y": [1, 2, 3], "net_margin": 5}

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                full_results, _usage, failure = asyncio.run(scout_batch(candidates, force=True))

    # full_results 长度 == 输入 N=3（缺 ticker 的 {} 不丢）
    assert len(full_results) == 3, (
        f"full_results 长度应 == 输入 3，got {len(full_results)}（缺 ticker 不应被过滤）"
    )
    # 缺 ticker 的那条：verdict=error, ticker=None, input_index=1
    err = next(r for r in full_results if r.get("verdict") == "error")
    assert err["ticker"] is None, "缺 ticker 的 error result ticker 应为 None（不伪造）"
    assert err["input_index"] == 1, f"input_index 应为 1，got {err.get('input_index')}"
    assert err.get("stage") == "input_validation", (
        f"stage 应为 input_validation，got {err.get('stage')}"
    )
    # 在 failure_summary.errors
    assert any(e.get("input_index") == 1 for e in failure["errors"]), (
        "缺 ticker 的 error 应进 failure_summary.errors（含 input_index）"
    )


def test_scout_batch_non_dict_input_does_not_escape():
    """非 dict 输入（None）SHALL 不抛异常逃逸整批，进 error result + errors.

    对应 review 阻断1：scout_batch([None]) 原 AttributeError 逃逸（candidate.get 在 try 外）。
    修复后输入校验移进 try，TypeError 走兜底，返回 error result。
    """
    candidates = [{"ticker": "600001"}, None, {"ticker": "600003"}]  # 第 2 只 None

    async def mock_call(snapshot, system):
        return (json.dumps({"verdict": "deep_dive", "confidence": 80, "one_liner": "t",
                            "red_flags": [], "green_flags": [], "anti_trap_flags": []}),
                LLM_USAGE)

    def mock_assemble(ticker, cache_manager=None, **kwargs):
        return {"ticker": ticker, "name": "x", "market_cap": 1, "pe_ttm": 10,
                "roe_3y": [1, 2, 3], "net_margin": 5}

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                full_results, _usage, failure = asyncio.run(scout_batch(candidates, force=True))

    # 不抛异常（已跑到断言即证明），full_results 长度 == 3
    assert len(full_results) == 3, f"full_results 应 == 3，got {len(full_results)}"
    # None 输入那条：verdict=error, ticker=None, input_index=1, stage=unexpected_exception
    err = next(r for r in full_results if r.get("input_index") == 1)
    assert err["verdict"] == "error"
    assert err["ticker"] is None
    assert err.get("stage") == "unexpected_exception", (
        f"非 dict 输入应走兜底 stage=unexpected_exception，got {err.get('stage')}"
    )
    # unhandled_exceptions == 0（兜底已捕获，未逃逸）
    assert failure["unhandled_exceptions"] == 0
    # 整批不中断：其他两只仍处理
    result_tickers = [r["ticker"] for r in full_results]
    assert "600001" in result_tickers and "600003" in result_tickers


def test_error_results_satisfy_full_result_contract():
    """所有 error result（insufficient_data / LLM error）SHALL 含 full-result 6 契约字段.

    对应 review 阻断2：error result 原 ticker/verdict/error 缺 one_liner/red_flags/
    green_flags/anti_trap_flags/low_confidence_anomaly，违反 delta spec「每条 full result
    含这些字段」。修复后所有 error 分支补全。
    """
    CONTRACT_FIELDS = {"one_liner", "red_flags", "green_flags",
                      "anti_trap_flags", "low_confidence_anomaly"}
    candidates = [
        {"ticker": "600001"},  # LLM error（mock_call 抛 HTTPStatusError）
        {"ticker": "600002"},  # insufficient_data（assemble 返回 error）
        {"ticker": "600003"},  # 正常 deep_dive（对照）
    ]

    def mock_assemble(ticker, cache_manager=None, **kwargs):
        if ticker == "600002":
            return {"error": "insufficient_data", "missing_fields": ["name", "industry"]}
        return {"ticker": ticker, "name": "x", "market_cap": 1, "pe_ttm": 10,
                "roe_3y": [1, 2, 3], "net_margin": 5}

    async def mock_call(snapshot, system):
        if "600001" in snapshot:
            raise httpx.HTTPStatusError("LLM API error", request=None, response=None)
        return (json.dumps({"verdict": "deep_dive", "confidence": 80, "one_liner": "t",
                            "red_flags": [], "green_flags": [], "anti_trap_flags": []}),
                LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                full_results, _usage, _failure = asyncio.run(scout_batch(candidates, force=True))

    # 两条 error（600001 LLM error / 600002 insufficient）
    error_results = [r for r in full_results if r.get("verdict") == "error"]
    assert len(error_results) == 2, f"应有 2 条 error，got {len(error_results)}"
    for r in error_results:
        missing = CONTRACT_FIELDS - set(r.keys())
        assert not missing, (
            f"error result 缺契约字段 {missing}，ticker={r.get('ticker')}"
        )
    # 对照：deep_dive 那条本就有这些字段
    dd = next(r for r in full_results if r["ticker"] == "600003")
    assert CONTRACT_FIELDS <= set(dd.keys())


# ============================================================
# g1-canonical-run-identity: scout_batch 继承 run_id（design D2 + Migration 5）
# ============================================================

def _basic_llm_mock(verdict="deep_dive", confidence=75):
    """构造一个返回固定 verdict 的 mock_call."""
    async def mock_call(snapshot, system):
        return (json.dumps({
            "verdict": verdict, "confidence": confidence,
            "one_liner": "test", "red_flags": [], "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)
    return mock_call


def _basic_features(ticker="600001"):
    """构造 assemble_snapshot 的 mock 返回."""
    return {
        "ticker": ticker, "name": "测试", "industry": "测试",
        "market_cap": 1000, "pe_ttm": 20.0, "pb": 2.0,
        "pe_percentile_5y": 50.0, "roe_3y": [15.0, 16.0, 17.0],
        "roe_trend": "趋势上升", "net_margin": 10.0, "debt_ratio": 50.0,
        "goodwill_ratio": 5.0, "operating_cashflow": 100.0, "net_profit": 80.0,
        "cashflow_match": "匹配", "revenue_growth": 10.0, "pledge_ratio": 10.0,
        "price_change_60d": 5.0, "turnover_avg_percentile_60d": 50.0, "f_score": 7,
    }


def test_scout_batch_inherits_run_id_from_l1():
    """scout_batch 收到 run_identity 参数 → full_results 每条 + cache entry SHALL 继承.

    对应 run-identity spec: L2 从 L1 继承 run_id，MUST NOT 生成新 run_id。
    scout_batch(candidates, force, run_identity={run_id, profile_version,
    input_ticker_set_hash}) 继承之。
    """
    candidates = [{"ticker": "600001"}]
    run_identity = {
        "run_id": "l1_run_id_abc123",
        "profile_version": "g1-2026-07-21",
        "input_ticker_set_hash": "l1_input_hash",
    }

    with patch("scout.batch.call_llm_snapshot", new=_basic_llm_mock()):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = _basic_features()
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None  # 无缓存命中

                results, _usage, _fail = asyncio.run(
                    scout_batch(candidates, run_identity=run_identity)
                )

    # full_results 每条继承 run identity
    assert len(results) == 1
    r = results[0]
    assert r.get("run_id") == "l1_run_id_abc123", "full_results 每条 SHALL 继承 run_id"
    assert r.get("profile_version") == "g1-2026-07-21"
    assert r.get("input_ticker_set_hash") == "l1_input_hash"
    # ScoutCache.set 被调用且传了 run identity
    mock_cache.set.assert_called()
    set_kwargs = mock_cache.set.call_args.kwargs
    assert set_kwargs.get("run_id") == "l1_run_id_abc123", \
        "cache entry SHALL 绑定 run_id（传给 ScoutCache.set）"
    assert set_kwargs.get("profile_version") == "g1-2026-07-21"


def test_scout_batch_fallback_run_id_when_no_l1():
    """candidates 无 run_identity → scout_batch fallback 生成 run_id 标注 scout_fallback.

    对应 run-identity spec: 纯 L2 单跑 fallback 生成 run_id，MUST NOT 报错中断。
    """
    candidates = [{"ticker": "600001"}]  # 手动构造，非来自 L1，无 run_identity

    with patch("scout.batch.call_llm_snapshot", new=_basic_llm_mock()):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = _basic_features()
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None

                results, _usage, _fail = asyncio.run(
                    scout_batch(candidates)  # 不传 run_identity
                )

    assert len(results) == 1
    r = results[0]
    assert r.get("run_id"), "fallback SHALL 生成 run_id（非空）"
    assert r.get("run_id_source") == "scout_fallback", \
        "fallback run_id SHALL 标注 run_id_source=scout_fallback"
    assert r.get("profile_version"), "fallback SHALL 仍带 profile_version"


def test_scout_batch_triple_contract_unchanged():
    """scout_batch 仍返回三元组，签名向后兼容（G1-2 闭合不重开）.

    run_identity 是可选入参，不传时仍返回 (full_results, usage_summary, failure_summary)。
    """
    candidates = [{"ticker": "600001"}]
    with patch("scout.batch.call_llm_snapshot", new=_basic_llm_mock()):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = _basic_features()
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None
                ret = asyncio.run(scout_batch(candidates))

    assert isinstance(ret, tuple) and len(ret) == 3, \
        "MUST 仍返回三元组 (full_results, usage_summary, failure_summary)"
    results, usage, fail = ret
    assert isinstance(results, list)
    assert isinstance(usage, dict) and "call_count" in usage
    assert isinstance(fail, dict) and "errors" in fail


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
