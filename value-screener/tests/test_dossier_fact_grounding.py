"""g2-dossier-data-quality 字段级事实契约 RED 测试（纯 Python，零 LLM）."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.fact_grounding import (  # noqa: E402
    FactContractError,
    FactEvidence,
    build_fact_contract,
    derive_quality_status,
)


def _mb(report_date: str | None = "2025-12-31", code: str = "600009") -> dict:
    return {
        "code": code,
        "report_date": report_date,
        "by_industry": [
            {"name": "航空及相关服务", "revenue": 1.2e10, "revenue_ratio": 0.94, "gross_margin": 0.25},
        ],
    }


def _peers(code: str = "600009") -> dict:
    return {
        "code": code,
        "industry": "航空机场",
        "peer_avg_pe": 18.1,
        "industry_pe_rank": 2,
        "peer_count": 4,
        "peer_pe_list": [12.57, 28.74, 26.42, 12.99],
    }


def _research(code: str = "600009") -> dict:
    return {
        "code": code,
        "consensus_eps": 1.152,
        "target_price": 30.41,
        "buy_rating_pct": 1.0,
        "coverage_count": 2,
        "rating_distribution": {"买入": 1, "增持": 1},
    }


def _capex() -> dict:
    return {"latest": 1.307e9, "series": [1.244e9, 1.958e9, 1.307e9], "years": ["2023", "2024", "2025"]}


def _dossier(mb=None, peers=None, research=None, capex=None, degraded=None) -> dict:
    return {
        "core_snapshot": {"ticker": "600009"},
        "research_dossier": {
            "main_business": _mb() if mb is None else mb,
            "peers": _peers() if peers is None else peers,
            "capex_proxy": _capex() if capex is None else capex,
            "research": _research() if research is None else research,
            "degraded_fields": [] if degraded is None else degraded,
        },
    }


def test_closed_vocabulary_rejects_unknown_severity():
    with pytest.raises(FactContractError, match="severity"):
        FactEvidence(
            role="peers",
            fact_key="peers.peer_avg_pe",
            label="同行平均 PE",
            value=18.1,
            severity="critical",
            source="eastmoney.stock_board_industry_cons_em",
            report_period=None,
            as_of="2026-08-20T00:00:00+00:00",
            published_at=None,
            retrieved_at="2026-08-20T00:00:00+00:00",
            freshness="fresh",
            degradation_status="clean",
        )


def test_fact_evidence_derives_traceable():
    fact = FactEvidence(
        role="peers",
        fact_key="peers.peer_avg_pe",
        label="同行平均 PE",
        value=18.1,
        severity="high",
        source="eastmoney.stock_board_industry_cons_em",
        report_period=None,
        as_of="2026-08-20T00:00:00+00:00",
        published_at=None,
        retrieved_at="2026-08-20T00:00:00+00:00",
        freshness="fresh",
        degradation_status="clean",
    )
    assert fact.traceable is True


def test_high_severity_missing_time_basis_fails_closed():
    mb = _mb(report_date=None)
    with pytest.raises(FactContractError, match="time basis|report_period"):
        build_fact_contract(
            _dossier(mb=mb),
            ticker="600009",
            retrieved_at=None,
        )


def test_high_severity_source_ticker_mismatch_fails_closed():
    with pytest.raises(FactContractError, match="ticker mismatch"):
        build_fact_contract(
            _dossier(mb=_mb(code="000001")),
            ticker="600009",
            retrieved_at="2026-08-20T00:00:00+00:00",
        )


def test_traceability_stats_count_only_present_facts():
    contract = build_fact_contract(
        _dossier(research={"__error__": True, "dim": "research"}),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    assert contract["total_fact_count"] > 0
    assert contract["traceable_ratio"] == 1.0
    assert any(item["role"] == "research" and item["degradation_status"] == "unavailable"
               for item in contract["role_status"])


def test_stale_fact_is_not_clean():
    contract = build_fact_contract(
        _dossier(mb=_mb(report_date="2020-12-31")),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
        stale_after_days=365,
    )
    assert contract["clean"] is False
    assert contract["stale_fact_count"] > 0
    status, reasons = derive_quality_status(contract)
    assert status == "degraded"
    assert any("stale" in reason for reason in reasons)


def test_degraded_role_visible_in_contract():
    contract = build_fact_contract(
        _dossier(peers={"__error__": True, "dim": "peers"}),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    status, reasons = derive_quality_status(contract)
    assert status == "degraded"
    assert any("peers" in reason for reason in reasons)


def test_main_business_fallback_only_is_degraded():
    """主营只剩文本兜底、无数值主营构成 → 不得标 clean."""
    contract = build_fact_contract(
        _dossier(mb={"code": "600009", "main_business_text": "航空运输服务"}),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    assert contract["clean"] is False
    status, reasons = derive_quality_status(contract)
    assert status == "degraded"
    assert any("main_business" in reason for reason in reasons)


def test_research_published_at_does_not_override_retrieval_freshness():
    """研报发布时间过旧 → 新鲜度 stale，不能冒充 clean evidence."""
    research = _research()
    research["published_at"] = "2020-01-01"
    contract = build_fact_contract(
        _dossier(research=research),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
        stale_after_days=365,
    )
    assert contract["clean"] is True
    assert contract["stale_fact_count"] == 0
    status, reasons = derive_quality_status(contract)
    assert status == "clean"
    assert reasons == []


def test_invalid_published_at_is_visible_without_changing_primary_freshness():
    research = _research()
    research["published_at"] = "not-a-time"
    contract = build_fact_contract(
        _dossier(research=research),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
        fail_closed=False,
    )
    assert contract["clean"] is False
    assert contract["stale_fact_count"] == 0
    assert any("published_at" in (fact["reason"] or "") for fact in contract["facts"])


def test_non_high_untraceable_fact_reduces_traceable_ratio():
    """非高严重度不可追溯事实应进入分母并把追溯率降到 1 以下."""
    peers = {
        "code": "000001",
        "industry": "航空机场",
        "peer_avg_pe": None,
        "industry_pe_rank": None,
        "peer_count": 4,
        "peer_pe_list": [1.0, 2.0],
    }
    contract = build_fact_contract(
        _dossier(peers=peers),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    assert contract["traceable_ratio"] < 1.0
    assert contract["clean"] is False


def test_fail_closed_false_reports_failed_status():
    """fail_closed=False 时，高严重度不可追溯事实导出 failed 而非抛异常."""
    contract = build_fact_contract(
        _dossier(mb=_mb(report_date=None)),
        ticker="600009",
        retrieved_at=None,
        fail_closed=False,
    )
    assert contract["failed"] is True
    assert contract["clean"] is False
    status, reasons = derive_quality_status(contract)
    assert status == "failed"
    assert any(
        "time basis" in reason or "missing source" in reason
        for reason in reasons
    )


def test_traceable_ratio_zero_when_no_facts_present():
    """全 role 不可用时总事实数为 0，追溯率应为 0.0 而非 None."""
    contract = build_fact_contract(
        _dossier(
            mb={"__error__": True, "dim": "main_business"},
            peers={"__error__": True, "dim": "peers"},
            research={"__error__": True, "dim": "research"},
            capex={"__error__": True, "dim": "capex_proxy"},
            degraded=["main_business", "peers", "research", "capex_proxy"],
        ),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    assert contract["total_fact_count"] == 0
    assert contract["traceable_ratio"] == 0.0
    assert contract["clean"] is False


def test_high_severity_non_finite_value_fails_closed():
    """高严重度字段出现 NaN/inf → fail closed，不得静默丢弃."""
    mb = _mb()
    mb["by_industry"][0]["revenue"] = float("nan")
    with pytest.raises(FactContractError, match="non-finite"):
        build_fact_contract(
            _dossier(mb=mb),
            ticker="600009",
            retrieved_at="2026-08-20T00:00:00+00:00",
            now=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )


def test_high_severity_non_finite_value_fail_closed_false_reports_failed():
    """fail_closed=False 时，非有限高严重度值导出 failed 与可见 reason."""
    mb = _mb()
    mb["by_industry"][0]["revenue"] = float("inf")
    contract = build_fact_contract(
        _dossier(mb=mb),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
        fail_closed=False,
    )
    assert contract["failed"] is True
    assert contract["high_severity_invalid_count"] >= 1
    status, reasons = derive_quality_status(contract)
    assert status == "failed"
    assert any("non-finite" in reason for reason in reasons)


def test_non_finite_fact_degrades_its_role_even_when_sibling_fact_is_valid():
    """同一 role 的 NaN 不得被丢弃后仍让 sibling 数字冒充 clean."""
    peers = _peers()
    peers["peer_avg_pe"] = float("nan")
    peers["peer_count"] = 777
    contract = build_fact_contract(
        _dossier(peers=peers),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        fail_closed=False,
    )
    peer_status = next(item for item in contract["role_status"] if item["role"] == "peers")
    assert peer_status["degradation_status"] == "degraded"
    assert contract["failed"] is True


def test_core_list_non_finite_fact_degrades_core_role():
    """core 列表型 NaN/inf 也必须降级整个 core role."""
    dossier = _dossier()
    dossier["core_snapshot"]["roe_3y"] = [10.0, float("nan"), 12.0]
    contract = build_fact_contract(
        dossier,
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        fail_closed=False,
    )
    core_status = next(
        item for item in contract["role_status"] if item["role"] == "core_snapshot"
    )
    assert core_status["degradation_status"] == "degraded"
    assert contract["failed"] is True


def test_recent_report_with_stale_cache_as_of_is_not_fresh():
    """报告期较新但缓存读取时间过旧时，事实仍不得标 fresh."""
    dossier = _dossier()
    dossier["core_snapshot"]["pe_ttm"] = 20.0
    dossier["core_snapshot"]["fact_provenance"] = {
        "pe_ttm": {
            "source": "cache.valuation",
            "report_period": "2025-12-31",
            "as_of": "2020-01-01T00:00:00+00:00",
        }
    }
    contract = build_fact_contract(
        dossier,
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        now=datetime(2026, 8, 20, tzinfo=timezone.utc),
        stale_after_days=365,
        fail_closed=False,
    )
    fact = next(item for item in contract["facts"] if item["fact_key"] == "core_snapshot.pe_ttm")
    assert fact["freshness"] == "stale"
    assert contract["clean"] is False


def test_core_numeric_fact_without_provenance_is_not_clean():
    """core_snapshot 数字没有字段级来源时，不能成为 clean evidence."""
    dossier = _dossier()
    dossier["core_snapshot"].update(
        {"market_cap": 100.0, "pe_ttm": 20.0, "roe_3y": [10.0, 11.0, 12.0]}
    )
    contract = build_fact_contract(
        dossier,
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        fail_closed=False,
    )
    assert contract["clean"] is False
    assert contract["core_untraceable_count"] > 0
    assert contract["high_severity_untraceable_count"] > 0
    assert contract["failed"] is True
    status, reasons = derive_quality_status(contract)
    assert status == "failed"
    assert any(
        "time basis" in reason or "missing source" in reason
        for reason in reasons
    )


def test_invalid_report_period_is_not_traceable_and_fails_closed():
    """非法报告期不能仅因字符串非空而被当作可追溯."""
    mb = _mb(report_date="not-a-date")
    with pytest.raises(FactContractError, match="time basis|report_period"):
        build_fact_contract(
            _dossier(mb=mb),
            ticker="600009",
            retrieved_at="2026-08-20T00:00:00+00:00",
        )


def test_invalid_report_period_month_is_not_accepted():
    """报告期月份必须在 1-12，YYYY-00 不能进入 clean contract."""
    with pytest.raises(FactContractError, match="time basis|report_period"):
        build_fact_contract(
            _dossier(mb=_mb(report_date="2025-00")),
            ticker="600009",
            retrieved_at="2026-08-20T00:00:00+00:00",
        )


def test_empty_role_dict_is_degraded_and_has_zero_traceable_ratio():
    """空 peers/research/capex_proxy dict 不能伪装成 clean role."""
    contract = build_fact_contract(
        _dossier(peers={}, research={}, capex={}),
        ticker="600009",
        retrieved_at="2026-08-20T00:00:00+00:00",
        fail_closed=False,
    )
    assert contract["clean"] is False
    assert all(
        item["degradation_status"] != "clean"
        for item in contract["role_status"]
        if item["role"] in {"peers", "research", "capex_proxy"}
    )
