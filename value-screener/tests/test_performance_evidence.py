"""g1-full-market-performance-cost 测试.

覆盖 evidence orchestrator 的全部行为契约：
- 分阶段耗时（total/l1/l2）
- 关键字段可用率独立计算（含 pledge_status canonical 语义，review P1-1 方案 A）
- L2 成本双口径（实测 + 等效全量，含 cache_hits>0 外推，review P2-4）
- 未处理异常显式暴露
- 完整漏斗、降级分布、失败分布、运行配置、coverage/evidence_notes
- gate_passed 四维度全达标才为 true（含 elapsed/cost 失败分支，review P2-4）
- _check_cache_warmth 真实逻辑（review P2-4）
- save_evidence_bundle 落盘与 build_failure_bundle 失败证据（review P2-4）
- candidate 投影保留 pledge_status provenance（canonical None + status）
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_l1_output(n_candidates=3):
    """构造一份最小 L1 输出（S5 schema），含 run identity 和 stats."""
    candidates = []
    for i in range(n_candidates):
        candidates.append({
            "ticker": f"60000{i}.SH",
            "name": f"测试{i}",
            "industry": "白酒",
            "factor_scores": {"composite": 80.0 + i, "f_score": 7 + i},
            "anti_trap": {"score": 95},
            "adjusted_composite": 76.0 + i,
            "f_score": 7 + i,
            "pe_ttm": 25.0 + i,
            "pb": 2.0 + i * 0.5,
            "pledge_ratio": 10.0 + i,
            "pledge_status": "record_found",
        })
    return {
        "run_id": "test-run-id-1234",
        "run_date": "2026-08-11",
        "profile_version": "test-v1",
        "input_ticker_set_hash": "abc123",
        "candidates": candidates,
        "stats": {
            "total": 5000,
            "after_hard_gates": 800,
            "after_factors": 300,
            "after_heat_filter": 200,
            "excluded_by_gates": {"H3": 4200},
            "industry_pe_degraded": False,
            "input_scale": "full_market",
        },
    }


def _make_l2_output(n=3, unhandled=0, cache_hits=0):
    """构造一份最小 L2 输出（g1-l2-full-result-contract 四字段 payload）."""
    verdicts = ["deep_dive", "watch", "skip"]
    full_results = []
    for i in range(n):
        full_results.append({
            "ticker": f"60000{i}.SH",
            "verdict": verdicts[i % len(verdicts)],
            "confidence": 80 - i * 10,
            "one_liner": f"test {i}",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
            "low_confidence_anomaly": False,
        })
    real_calls = max(n - cache_hits, 0)
    return (
        full_results,
        {
            "call_count": real_calls,
            "cache_hits": cache_hits,
            "prompt_tokens": real_calls * 100,
            "completion_tokens": real_calls * 50,
            "total_tokens": real_calls * 150,
        },
        {
            "errors": [],
            "skips": sum(1 for r in full_results if r["verdict"] == "skip"),
            "watches": sum(1 for r in full_results if r["verdict"] == "watch"),
            "degraded": 0,
            "unhandled_exceptions": unhandled,
        },
    )


def _warmth_mock(warm=True, total_slots=15):
    return patch(
        "performance.run_evidence._check_cache_warmth",
        return_value={
            "warm_cache": warm,
            "cache_hits": total_slots if warm else 0,
            "cache_expired": 0,
            "cache_missing": 0 if warm else total_slots,
            "total_slots": total_slots,
        },
    )


# ==================== 2.1 分阶段耗时 ====================


def test_evidence_bundle_has_timing_fields():
    """evidence bundle SHALL 含 timing.total/l1/l2_elapsed_seconds."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output()
    l2_tuple = _make_l2_output()

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock():
        bundle = asyncio.run(run_full_market_evidence(["600000", "600001", "600002"]))

    timing = bundle["timing"]
    assert "total_elapsed_seconds" in timing
    assert "l1_elapsed_seconds" in timing
    assert "l2_elapsed_seconds" in timing
    assert timing["total_elapsed_seconds"] >= 0
    assert timing["total_elapsed_seconds"] >= timing["l1_elapsed_seconds"] + timing["l2_elapsed_seconds"]


# ==================== 2.2 关键字段可用率（含 pledge_status canonical 语义） ====================


def test_field_availability_independent_calculation():
    """可用率 SHALL 独立从 candidates 字段计算，不从 stats 派生."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output(n_candidates=4)
    # 第 4 只缺 pe_ttm（真缺失），pledge_ratio=None 但 status=record_not_found（usable）
    l1_output["candidates"][3]["pe_ttm"] = None
    l1_output["candidates"][3]["pledge_ratio"] = None
    l1_output["candidates"][3]["pledge_status"] = "record_not_found"
    l2_tuple = _make_l2_output(n=4)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock(total_slots=20):
        bundle = asyncio.run(run_full_market_evidence(["600000", "600001", "600002", "600003"]))

    avail = bundle["field_availability"]
    # 4 候选 × 6 字段 = 24；pe_ttm=None 计 missing；pledge record_not_found 计 usable
    assert avail["total_fields"] == 24
    assert avail["missing_count"] == 1
    assert abs(avail["rate"] - 23.0 / 24.0) < 1e-9


def test_field_availability_full_when_no_missing():
    """所有字段齐全时可用率为 1.0."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output(n_candidates=3)
    l2_tuple = _make_l2_output(n=3)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock():
        bundle = asyncio.run(run_full_market_evidence(["600000", "600001", "600002"]))

    assert bundle["field_availability"]["rate"] == 1.0
    assert bundle["field_availability"]["missing_count"] == 0


def test_pledge_record_not_found_counts_usable():
    """canonical 语义：pledge_ratio=None + pledge_status=record_not_found → usable（非 missing）."""
    from performance.run_evidence import _compute_field_availability

    candidates = [{
        "ticker": "600001.SH", "f_score": 7, "adjusted_composite": 76.0,
        "pe_ttm": 25.0, "pb": 2.0,
        "pledge_ratio": None, "pledge_status": "record_not_found",
    }]
    avail = _compute_field_availability(candidates)
    assert avail["missing_count"] == 0
    assert avail["rate"] == 1.0


def test_pledge_source_failed_counts_missing():
    """pledge_ratio=None + pledge_status=source_failed → missing（provider 失败不可用）."""
    from performance.run_evidence import _compute_field_availability

    candidates = [{
        "ticker": "600001.SH", "f_score": 7, "adjusted_composite": 76.0,
        "pe_ttm": 25.0, "pb": 2.0,
        "pledge_ratio": None, "pledge_status": "source_failed",
    }]
    avail = _compute_field_availability(candidates)
    assert avail["missing_count"] == 1
    assert abs(avail["rate"] - 5.0 / 6.0) < 1e-9


def test_pledge_none_without_status_counts_missing():
    """pledge_ratio=None 且无 pledge_status（旧 L1 输出兼容）→ missing."""
    from performance.run_evidence import _compute_field_availability

    candidates = [{
        "ticker": "600001.SH", "f_score": 7, "adjusted_composite": 76.0,
        "pe_ttm": 25.0, "pb": 2.0, "pledge_ratio": None,
    }]
    avail = _compute_field_availability(candidates)
    assert avail["missing_count"] == 1


# ==================== 2.3 candidate 投影保留 pledge provenance（P1-1 方案 A） ====================


def _make_ticker_data(pledge_ratio, pledge_status):
    """构造能过 hard gates 的最小 ticker_data，risk 字段按参数注入."""
    return {
        "basic": {
            "code": "600519", "name": "贵州茅台", "industry": "白酒",
            "pe": 25.0, "pb": 2.0, "price": 10.0, "market_cap": 100e8,
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
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 25.0, "graham_number": 100},
        "risk": {"pledge_ratio": pledge_ratio, "pledge_status": pledge_status,
                 "goodwill": 0, "audit_opinion": None},
        "kline": {"turnover_rate": [0.3] * 60, "close": [10.0] * 60},
    }


def test_candidate_pledge_record_not_found_preserves_none_with_status():
    """canonical 契约：record_not_found 时 candidate SHALL 保持 None + pledge_status，MUST NOT 改写 0.0."""
    from screener.main import screen_a_shares

    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = {
            "600519": _make_ticker_data(None, "record_not_found"),
        }
        result = screen_a_shares(["600519"])

    cand = result["candidates"][0]
    assert cand["pledge_ratio"] is None, "record_not_found SHALL 保持 None（MUST NOT 视为 0）"
    assert cand["pledge_status"] == "record_not_found", "SHALL 携带 pledge_status provenance"


def test_candidate_pledge_source_failed_preserves_none_with_status():
    """source_failed 时 candidate SHALL 保持 None + pledge_status."""
    from screener.main import screen_a_shares

    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = {
            "600519": _make_ticker_data(None, "source_failed"),
        }
        result = screen_a_shares(["600519"])

    cand = result["candidates"][0]
    assert cand["pledge_ratio"] is None
    assert cand["pledge_status"] == "source_failed"


def test_candidate_pledge_normal_value_preserved():
    """record_found 有值时 SHALL 保持原值."""
    from screener.main import screen_a_shares

    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = {
            "600519": _make_ticker_data(15.5, "record_found"),
        }
        result = screen_a_shares(["600519"])

    cand = result["candidates"][0]
    assert cand["pledge_ratio"] == 15.5
    assert cand["pledge_status"] == "record_found"


# ==================== 2.4 L2 成本双口径 ====================


def test_cost_dual_oracle():
    """evidence bundle SHALL 含实测成本和等效全量成本双口径."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output()
    l2_tuple = _make_l2_output(n=3)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock():
        bundle = asyncio.run(run_full_market_evidence(["600000", "600001", "600002"]))

    cost = bundle["cost"]
    # 实测成本 = 450 tokens × 0.001/1k = 0.00045
    assert abs(cost["measured_yuan"] - 450 * 0.001 / 1000) < 1e-9
    # 等效全量 = (3+0) × 150 × 0.001/1k（无缓存命中时等于实测）
    assert abs(cost["equivalent_full_yuan"] - 3 * 150 * 0.001 / 1000) < 1e-9


def test_cost_equivalent_full_with_cache_hits():
    """cache_hits>0 时等效全量成本 SHALL 按单只平均 token 外推到全部输入（review P2-4）."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output(n_candidates=4)
    # 4 只输入：3 次 cache 命中 + 1 次真实调用（150 tokens）
    l2_tuple = _make_l2_output(n=4, cache_hits=3)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock(total_slots=20):
        bundle = asyncio.run(run_full_market_evidence(
            ["600000", "600001", "600002", "600003"]))

    cost = bundle["cost"]
    assert cost["call_count"] == 1
    assert cost["cache_hits"] == 3
    # 实测 = 150 tokens × 0.001/1k
    assert abs(cost["measured_yuan"] - 150 * 0.001 / 1000) < 1e-9
    # 等效全量 = (1+3) × 150 × 0.001/1k（单只均值 150 外推到 4 份）
    assert abs(cost["equivalent_full_yuan"] - 4 * 150 * 0.001 / 1000) < 1e-9
    assert any("scout-cache 复用口径" in note for note in bundle["evidence_notes"])


def test_cost_equivalent_full_is_undefined_without_real_calls():
    """只有 cache hit、没有真实调用时，等效全量成本 SHALL 为 None，不伪造 0 元."""
    from performance.run_evidence import _compute_cost

    cost = _compute_cost({
        "call_count": 0,
        "cache_hits": 3,
        "total_tokens": 0,
    })
    assert cost["measured_yuan"] == 0.0
    assert cost["equivalent_full_yuan"] is None


# ==================== 2.5 未处理异常显式暴露 ====================


def test_unhandled_exceptions_makes_gate_fail():
    """unhandled_exceptions > 0 时 gate_passed SHALL 为 false."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output()
    l2_tuple = _make_l2_output(n=3, unhandled=2)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock():
        bundle = asyncio.run(run_full_market_evidence(["600000", "600001", "600002"]))

    assert bundle["exceptions"]["unhandled_count"] == 2
    assert bundle["gate_passed"] is False


# ==================== 2.6 漏斗/降级/失败分布/运行配置/coverage ====================


def test_evidence_bundle_has_funnel_and_distribution():
    """evidence bundle SHALL 含完整漏斗、降级分布、失败分布、运行配置和 coverage."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output()
    l2_tuple = _make_l2_output(n=3)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock():
        bundle = asyncio.run(run_full_market_evidence(
            ["600000", "600001", "600002"],
            exclude_cyclicals=True,
            force_l2=True,
            coverage="partial_market",
            ticker_source="cached_subset(test)",
        ))

    funnel = bundle["funnel"]
    assert funnel["total"] == 5000
    assert funnel["after_hard_gates"] == 800
    assert funnel["after_factors"] == 300
    assert funnel["after_heat_filter"] == 200
    assert funnel["l2_input"] == 3
    assert funnel["l2_deep_dive"] >= 1
    assert "l2_error" in funnel
    assert "l2_degraded" in funnel

    run_config = bundle["run_config"]
    assert run_config["exclude_cyclicals"] is True
    assert run_config["force_l2"] is True
    assert run_config["ticker_count"] == 3
    assert run_config["ticker_source"] == "cached_subset(test)"
    assert bundle["coverage"] == "partial_market"
    # coverage != full_market 时 SHALL 有 evidence_notes 标注口径
    assert any("coverage=partial_market" in n for n in bundle["evidence_notes"])


def test_evidence_bundle_has_run_identity():
    """evidence bundle SHALL 继承 L1 的 run identity."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output()
    l2_tuple = _make_l2_output(n=3)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock():
        bundle = asyncio.run(run_full_market_evidence(["600000", "600001", "600002"]))

    assert bundle["run_id"] == "test-run-id-1234"
    assert bundle["profile_version"] == "test-v1"
    assert bundle["input_ticker_set_hash"] == "abc123"
    assert bundle["schema_version"] == "g1-full-market-performance-cost.v2"
    assert bundle["input_tickers"] == ["600000", "600001", "600002"]


# ==================== 2.7 gate_passed 判定（含 elapsed/cost 失败分支） ====================


def test_metrics_gate_passed_true_when_all_criteria_met():
    """四维度全达标时 metrics_gate_passed 为 true；partial 仍不关闭 full-market Gate."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output()
    l2_tuple = _make_l2_output(n=3)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock():
        bundle = asyncio.run(run_full_market_evidence(
            ["600000", "600001", "600002"],
            coverage="partial_market",
        ))

    assert bundle["metrics_gate_passed"] is True
    assert bundle["gate_passed"] is False
    thresholds = bundle["gate_thresholds"]
    assert thresholds["max_elapsed_minutes"] == 15
    assert thresholds["min_field_availability"] == 0.95
    assert thresholds["max_l2_cost_yuan"] == 2.0
    assert thresholds["max_unhandled_exceptions"] == 0


def test_full_market_gate_requires_full_market_coverage():
    """四项指标全达标且 coverage=full_market 时，gate_passed 才为 true."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output()
    l2_tuple = _make_l2_output(n=3)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock():
        bundle = asyncio.run(run_full_market_evidence(
            ["600000", "600001", "600002"],
            coverage="full_market",
            ticker_source="verified_full_universe",
        ))

    assert bundle["metrics_gate_passed"] is True
    assert bundle["gate_passed"] is True


def test_gate_passed_false_when_availability_below_threshold():
    """可用率 < 95% 时 gate_passed 为 false."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output(n_candidates=10)
    # 5 只缺 5 个关键字段（status 非 record_not_found → 计 missing）
    for i in range(5):
        for f in ("pe_ttm", "pb", "pledge_ratio", "f_score", "adjusted_composite"):
            l1_output["candidates"][i][f] = None
        l1_output["candidates"][i]["pledge_status"] = "source_failed"
    l2_tuple = _make_l2_output(n=10)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock(total_slots=50):
        bundle = asyncio.run(run_full_market_evidence([f"60000{i}" for i in range(10)]))

    assert bundle["field_availability"]["rate"] < 0.95
    assert bundle["gate_passed"] is False


def test_judge_gate_elapsed_failure_branch():
    """耗时 > 15min 时 gate_passed 为 false（review P2-4 补测）."""
    from performance.run_evidence import _judge_gate

    timing = {"total_elapsed_seconds": 16 * 60, "l1_elapsed_seconds": 900, "l2_elapsed_seconds": 60}
    avail = {"rate": 1.0}
    cost = {"measured_yuan": 0.1}
    assert _judge_gate(timing, avail, cost, 0) is False


def test_judge_gate_cost_failure_branch():
    """成本 > ¥2 时 gate_passed 为 false（review P2-4 补测）."""
    from performance.run_evidence import _judge_gate

    timing = {"total_elapsed_seconds": 60, "l1_elapsed_seconds": 30, "l2_elapsed_seconds": 30}
    avail = {"rate": 1.0}
    cost = {"measured_yuan": 2.5}
    assert _judge_gate(timing, avail, cost, 0) is False


def test_judge_gate_boundary_values_pass():
    """边界值（恰好等于阈值）SHALL 判 pass（≤/≥ 语义）."""
    from performance.run_evidence import _judge_gate

    timing = {"total_elapsed_seconds": 15 * 60, "l1_elapsed_seconds": 800, "l2_elapsed_seconds": 100}
    avail = {"rate": 0.95}
    cost = {"measured_yuan": 2.0}
    assert _judge_gate(timing, avail, cost, 0) is True


# ==================== 2.8 _check_cache_warmth 真实逻辑（review P2-4） ====================


def _write_cache_entry(base: Path, ticker: str, dim: str, age_seconds: float = 0):
    d = base / ticker
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{dim}.json"
    p.write_text(json.dumps({"ok": True}), encoding="utf-8")
    if age_seconds > 0:
        t = time.time() - age_seconds
        os.utime(p, (t, t))


def test_check_cache_warmth_all_warm(tmp_path):
    """全部维度缓存未过期 → warm_cache=true."""
    from performance.run_evidence import _check_cache_warmth
    from screener.main import G1_QUANT_DIMENSIONS

    tickers = ["600001", "600002"]
    for t in tickers:
        for dim in G1_QUANT_DIMENSIONS:
            _write_cache_entry(tmp_path, t, dim)

    status = _check_cache_warmth(tickers, cache_base=tmp_path)
    assert status["warm_cache"] is True
    assert status["cache_hits"] == len(tickers) * len(G1_QUANT_DIMENSIONS)
    assert status["cache_expired"] == 0
    assert status["cache_missing"] == 0


def test_check_cache_warmth_expired_and_missing(tmp_path):
    """过期与缺失 SHALL 分别计数，warm_cache=false."""
    from performance.run_evidence import _check_cache_warmth
    from screener.main import G1_QUANT_DIMENSIONS

    tickers = ["600001"]
    # basic 新鲜，financials 过期（30 天前，超所有 TTL），其余 3 维缺失
    _write_cache_entry(tmp_path, "600001", "basic")
    _write_cache_entry(tmp_path, "600001", "financials", age_seconds=30 * 24 * 3600)

    status = _check_cache_warmth(tickers, cache_base=tmp_path)
    assert status["warm_cache"] is False
    assert status["cache_hits"] == 1
    assert status["cache_expired"] == 1
    assert status["cache_missing"] == len(G1_QUANT_DIMENSIONS) - 2
    assert status["total_slots"] == len(G1_QUANT_DIMENSIONS)


def test_check_cache_warmth_does_not_create_missing_ticker_dirs(tmp_path):
    """预检缺失缓存时 SHALL 不创建 ticker 目录（review P2-2）."""
    from performance.run_evidence import _check_cache_warmth

    missing_ticker = "600999"
    assert not (tmp_path / missing_ticker).exists()
    status = _check_cache_warmth([missing_ticker], cache_base=tmp_path)
    assert status["cache_missing"] > 0
    assert not (tmp_path / missing_ticker).exists()


# ==================== 2.9 save_evidence_bundle 与 build_failure_bundle（review P2-4） ====================


def test_save_evidence_bundle_roundtrip(tmp_path):
    """save_evidence_bundle SHALL 落盘且内容可回读一致."""
    from performance.run_evidence import save_evidence_bundle

    bundle = {
        "run_id": "abcdef12-3456-4789-8abc-def012345678",
        "run_date": "2026-08-11",
        "gate_passed": True,
        "timing": {"total_elapsed_seconds": 1.5},
    }
    out = save_evidence_bundle(bundle, output_dir=tmp_path)
    assert out.exists()
    assert out.name == "2026-08-11_abcdef12.json"
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["run_id"] == bundle["run_id"]
    assert loaded["gate_passed"] is True


def test_failure_bundle_filenames_are_unique(tmp_path):
    """同日多次失败 SHALL 保留独立文件，不互相覆盖."""
    from performance.run_evidence import build_failure_bundle, save_evidence_bundle

    error = RuntimeError("provider down")
    first = build_failure_bundle(error, 1.0, 2)
    second = build_failure_bundle(error, 2.0, 2)
    first_path = save_evidence_bundle(first, output_dir=tmp_path)
    second_path = save_evidence_bundle(second, output_dir=tmp_path)
    assert first_path != second_path
    assert first_path.exists()
    assert second_path.exists()


def test_save_evidence_bundle_creates_output_dir(tmp_path):
    """输出目录不存在时 SHALL 自动创建."""
    from performance.run_evidence import save_evidence_bundle

    nested = tmp_path / "deep" / "nested"
    bundle = {"run_id": "abcdef12", "run_date": "2026-08-11"}
    out = save_evidence_bundle(bundle, output_dir=nested)
    assert out.exists()


def test_build_failure_bundle_structure():
    """运行失败证据 SHALL 含 run_failed/gate_passed=false/error/traceback/elapsed."""
    from performance.run_evidence import build_failure_bundle

    try:
        raise RuntimeError("provider down")
    except RuntimeError as e:
        bundle = build_failure_bundle(e, elapsed_seconds=12.5, ticker_count=100)

    assert bundle["run_failed"] is True
    assert bundle["gate_passed"] is False
    assert bundle["failure"]["error"] == "provider down"
    assert "RuntimeError" in bundle["failure"]["traceback"]
    assert bundle["failure"]["elapsed_seconds_before_failure"] == 12.5
    assert bundle["exceptions"]["unhandled_count"] == 1
    assert bundle["run_config"]["ticker_count"] == 100
    assert bundle["run_config"]["ticker_source"] == "unspecified"
    assert bundle["input_tickers"] == []
    assert "gate_thresholds" in bundle


# ==================== 2.10 warm_cache 语义（review P2-3） ====================


def test_warm_cache_reflects_l1_precheck_not_l2_hits():
    """warm_cache SHALL 仅反映 L1 数据缓存预检（design D7），不受 L2 cache 命中影响."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output()
    # L2 全冷（force_l2 等效：0 cache hits），但 L1 预检全暖
    l2_tuple = _make_l2_output(n=3, cache_hits=0)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock(warm=True):
        bundle = asyncio.run(run_full_market_evidence(["600000", "600001", "600002"], force_l2=True))

    assert bundle["warm_cache"] is True, "L1 预检全暖 → warm_cache=true，与 L2 cache 无关"
    assert bundle["cost"]["cache_hits"] == 0
    from council.llm import LIGHT_LLM_TIMEOUT_SECONDS
    from scout.batch import SCOUT_CONCURRENCY
    assert bundle["run_config"]["semaphore_concurrency"] == SCOUT_CONCURRENCY
    assert bundle["run_config"]["l2_timeout_seconds"] == LIGHT_LLM_TIMEOUT_SECONDS


def test_cold_l1_cache_generates_evidence_note():
    """L1 缓存未全暖时 SHALL 在 evidence_notes 标注耗时含真实采集."""
    from performance.run_evidence import run_full_market_evidence

    l1_output = _make_l1_output()
    l2_tuple = _make_l2_output(n=3)

    with patch("performance.run_evidence.screen_a_shares", return_value=l1_output), \
         patch("performance.run_evidence.scout_batch", new_callable=AsyncMock, return_value=l2_tuple), \
         _warmth_mock(warm=False):
        bundle = asyncio.run(run_full_market_evidence(["600000", "600001", "600002"]))

    assert bundle["warm_cache"] is False
    assert any("L1 数据缓存未全暖" in n for n in bundle["evidence_notes"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
