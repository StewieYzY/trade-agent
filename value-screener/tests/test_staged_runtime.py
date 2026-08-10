from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Existing fetcher modules import akshare at module load time. The staged runtime
# tests are fully offline and never call those provider methods.
sys.modules.setdefault("akshare", SimpleNamespace())

from data.lib.canonical_snapshot_consumer import ConsumedField  # noqa: E402
from data.lib.batch_fetcher import BatchFetcher, FetchTelemetry  # noqa: E402
from screener.staged_runtime import (  # noqa: E402
    G1_STAGE_DIMENSIONS,
    run_staged_screening,
)


def _basic(*, market_cap: float = 10e9, name: str = "正常股") -> dict:
    return {
        "name": name,
        "price": 10.0,
        "pe": 12.0,
        "pb": 1.5,
        "market_cap": market_cap,
        "industry": "制造业",
    }


def _financials() -> dict:
    return {
        "years": ["2022", "2023", "2024"],
        "income": {
            "revenue": [100.0, 110.0, 120.0],
            "net_profit": [10.0, 11.0, 12.0],
        },
        "balance_sheet": {
            "TOTAL_ASSETS": [100.0, 105.0, 110.0],
            "TOTAL_CURRENT_LIAB": [20.0, 20.0, 20.0],
            "TOTAL_NONCURRENT_LIAB": [20.0, 20.0, 20.0],
            "GOODWILL": [1.0, 1.0, 1.0],
        },
        "cash_flow": {
            "NETCASH_OPERATE": [12.0, 13.0, 14.0],
            "CONSTRUCT_LONG_ASSET": [2.0, 2.0, 2.0],
        },
    }


def _risk() -> dict:
    return {
        "pledge_ratio": 5.0,
        "pledge_status": "record_found",
        "audit_opinion": "标准无保留意见",
    }


def _valuation() -> dict:
    return {
        "pe_ttm": 12.0,
        "pb": 1.5,
        "pe_percentile_5y": 30.0,
        "pb_percentile_5y": 30.0,
        "pe_history": [10.0, 11.0, 12.0],
        "pb_history": [1.2, 1.3, 1.5],
    }


def _kline() -> dict:
    return {
        "close": [10.0] * 59 + [10.5],
        "turnover_rate": [2.0] * 60,
    }


class FakeBatchFetcher:
    def __init__(self, results: dict[str, dict[str, dict]]) -> None:
        self.results = results
        self.calls: list[tuple[list[str], tuple[str, ...]]] = []

    def fetch_all(self, tickers, *, dimensions, telemetry=None):
        self.calls.append((list(tickers), tuple(dimensions)))
        if telemetry is not None:
            telemetry.record_request(list(tickers), tuple(dimensions))
        result = {
            ticker: {
                dimension: self.results.get(ticker, {}).get(
                    dimension,
                    {"__error__": True, "error": f"missing:{dimension}"},
                )
                for dimension in dimensions
            }
            for ticker in tickers
        }
        if telemetry is not None:
            for ticker, dimensions_data in result.items():
                for dimension, value in dimensions_data.items():
                    if isinstance(value, dict) and value.get("__error__"):
                        telemetry.record_failure(
                            ticker,
                            dimension,
                            status="source_failed",
                            reason=str(value.get("error") or "provider failed"),
                        )
        return result


def _complete_results() -> dict[str, dict[str, dict]]:
    return {
        "600001": {
            "basic": _basic(),
            "financials": _financials(),
            "risk": _risk(),
            "valuation": _valuation(),
            "kline": _kline(),
        },
        "600002": {
            "basic": _basic(market_cap=1e9),
            "financials": _financials(),
            "risk": _risk(),
            "valuation": _valuation(),
            "kline": _kline(),
        },
        "600003": {
            "basic": _basic(),
            "financials": {"__error__": True, "error": "source failed"},
            "risk": _risk(),
            "valuation": _valuation(),
            "kline": _kline(),
        },
    }


def test_stage_boundaries_and_ticker_sets_shrink():
    fetcher = FakeBatchFetcher(_complete_results())

    result = run_staged_screening(
        ["600001", "600002", "600003"],
        fetcher=fetcher,
        run_id="test-run",
    )

    assert [call[1] for call in fetcher.calls] == [
        G1_STAGE_DIMENSIONS["A"],
        G1_STAGE_DIMENSIONS["B"],
        G1_STAGE_DIMENSIONS["C"],
    ]
    assert fetcher.calls[0][0] == ["600001", "600002", "600003"]
    assert fetcher.calls[1][0] == ["600001", "600003"]
    assert fetcher.calls[2][0] == ["600001"]
    assert result.stages["A"].output_tickers == ["600001", "600003"]
    assert result.stages["B"].output_tickers == ["600001"]
    assert len(result.stages["A"].input_tickers) >= len(
        result.stages["B"].input_tickers
    ) >= len(result.stages["C"].input_tickers) >= len(
        result.stages["C"].output_tickers
    )


def test_g2_dossier_dimensions_never_enter_any_stage():
    fetcher = FakeBatchFetcher({"600001": _complete_results()["600001"]})

    run_staged_screening(["600001"], fetcher=fetcher, run_id="no-dossier")

    requested = {dimension for _, dimensions in fetcher.calls for dimension in dimensions}
    assert requested.isdisjoint({"main_business", "peers", "research"})


def test_single_ticker_failure_is_visible_and_does_not_abort_batch():
    results = _complete_results()
    results["600003"]["financials"] = {
        "__error__": True,
        "error": "provider down",
    }
    fetcher = FakeBatchFetcher(results)

    result = run_staged_screening(
        ["600001", "600003"],
        fetcher=fetcher,
        run_id="failure-visible",
    )

    assert result.stages["B"].failures == [
        {
            "ticker": "600003",
            "dimension": "financials",
            "status": "source_failed",
            "reason": "provider down",
        }
    ]
    assert result.stages["C"].input_tickers == ["600001"]


def test_missing_financials_fields_do_not_pass_stage_b():
    results = _complete_results()
    results["600001"]["financials"] = {}
    fetcher = FakeBatchFetcher(results)

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="missing-fin")

    assert result.stages["B"].output_tickers == []
    assert result.stages["C"].input_tickers == []
    assert result.stages["B"].failures[0]["status"] == "not_evaluated"


def test_incomplete_kline_does_not_pass_stage_c():
    results = _complete_results()
    results["600001"]["kline"] = {"close": [10.0], "turnover_rate": [2.0]}
    fetcher = FakeBatchFetcher(results)

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="missing-kline")

    assert result.stages["C"].output_tickers == []
    assert result.stages["C"].failures[0]["status"] == "not_evaluated"


def test_stage_evidence_distinguishes_provider_calls_and_cache_hits():
    fetcher = FakeBatchFetcher({"600001": _complete_results()["600001"]})

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="evidence")

    for stage in result.stages.values():
        assert stage.run_id == "evidence"
        assert stage.requested_dimensions
        assert isinstance(stage.provider_calls, list)
        assert isinstance(stage.cache_hits, list)
        assert isinstance(stage.failures, list)


def test_canonical_metadata_is_retained_without_defaulting_unavailable_value():
    fetcher = FakeBatchFetcher({"600001": _complete_results()["600001"]})
    field = ConsumedField(
        value=None,
        status="stale",
        eligibility="production_eligible",
        reason="outside freshness window",
        provenance={"provider": "fixture", "field": "pe_ttm"},
        as_of="2026-08-01",
        freshness="stale",
    )

    result = run_staged_screening(
        ["600001"],
        fetcher=fetcher,
        run_id="canonical-state",
        canonical_fields={("600001", "pe_ttm"): field},
    )

    retained = result.ticker_evidence["600001.SH"]["canonical_fields"]["pe_ttm"]
    assert retained["value"] is None
    assert retained["status"] == "stale"
    assert retained["reason"] == "outside freshness window"
    assert retained["provenance"] == {"provider": "fixture", "field": "pe_ttm"}
    assert retained["as_of"] == "2026-08-01"
    assert retained["freshness"] == "stale"


def test_canonical_unavailable_field_blocks_candidate_and_consumer_object_is_supported():
    fetcher = FakeBatchFetcher({"600001": _complete_results()["600001"]})
    stale_field = ConsumedField(
        value=None,
        status="stale",
        eligibility="production_eligible",
        reason="outside freshness window",
        provenance={"provider": "fixture", "field": "pe_ttm"},
        as_of="2026-08-01",
        freshness="stale",
    )

    class ConsumerStub:
        def fields_for(self, ticker):
            assert ticker == "600001.SH"
            return {"pe_ttm": stale_field}

    result = run_staged_screening(
        ["600001"],
        fetcher=fetcher,
        run_id="canonical-block",
        canonical_fields=ConsumerStub(),
    )

    assert result.candidates == []
    assert result.stages["C"].failures[0]["status"] == "stale"


def test_canonical_last_price_stale_blocks_stage_a():
    fetcher = FakeBatchFetcher({"600001": _complete_results()["600001"]})
    stale_field = ConsumedField(
        value=None,
        status="stale",
        eligibility="production_eligible",
        reason="quote expired",
        provenance={"provider": "fixture", "field": "last_price"},
        as_of="2026-08-01",
        freshness="stale",
    )

    class ConsumerStub:
        def fields_for(self, ticker):
            return {"last_price": stale_field}

    result = run_staged_screening(
        ["600001"],
        fetcher=fetcher,
        run_id="last-price-block",
        canonical_fields=ConsumerStub(),
    )

    assert result.candidates == []
    assert result.stages["A"].failures[0]["dimension"] == "last_price"


def test_stage_a_required_fields_are_fail_closed():
    results = _complete_results()
    results["600001"]["basic"] = {"market_cap": 10e9}
    fetcher = FakeBatchFetcher(results)

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="basic-contract")

    assert result.stages["A"].output_tickers == []
    assert result.stages["A"].failures[0]["status"] == "not_evaluated"


def test_stage_b_required_financial_and_risk_fields_are_fail_closed():
    results = _complete_results()
    results["600001"]["financials"] = {"years": ["2022", "2023", "2024"]}
    results["600001"]["risk"] = {"pledge_status": "record_found"}
    fetcher = FakeBatchFetcher(results)

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="stage-b-contract")

    assert result.stages["B"].output_tickers == []
    assert result.stages["B"].failures[0]["status"] == "not_evaluated"


def test_invalid_numeric_series_and_values_do_not_crash_or_pass():
    results = _complete_results()
    results["600001"]["basic"]["market_cap"] = float("nan")
    results["600001"]["kline"]["close"] = [True] * 60
    fetcher = FakeBatchFetcher(results)

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="invalid-numeric")

    assert result.candidates == []
    assert result.stages["A"].output_tickers == []


def test_unknown_status_and_malformed_financials_are_isolated_per_ticker():
    results = _complete_results()
    results["600002"]["basic"]["market_cap"] = 10e9
    results["600001"]["financials"] = {
        "status": "provider_new_status",
        "years": ["2022", "2023", "2024"],
        "income": {"net_profit": [1.0, float("nan"), 3.0]},
        "balance_sheet": {
            "TOTAL_ASSETS": [1.0, 2.0, 3.0],
            "TOTAL_CURRENT_LIAB": [1.0, 1.0, 1.0],
            "TOTAL_NONCURRENT_LIAB": [0.0, 0.0, 0.0],
        },
        "cash_flow": {"NETCASH_OPERATE": [1.0, 2.0, 3.0]},
    }
    fetcher = FakeBatchFetcher(results)

    result = run_staged_screening(
        ["600001", "600002"],
        fetcher=fetcher,
        run_id="malformed-isolation",
    )

    assert result.stages["B"].output_tickers == ["600002"]
    assert result.stages["C"].input_tickers == ["600002"]
    assert any(failure["ticker"] == "600001" for failure in result.stages["B"].failures)


def test_malformed_final_score_isolated_from_healthy_ticker(monkeypatch):
    from screener import staged_runtime

    data = {
        "bad": {"basic": {"industry": "行业A", "pe": 10.0}},
        "good": {"basic": {"industry": "行业A", "pe": 10.0}},
    }
    monkeypatch.setattr(staged_runtime, "compute_industry_median_pe", lambda _: {})

    def score(value, _industry_pe):
        if value["ticker"] == "bad":
            raise TypeError("malformed factor input")
        return {"composite": 80.0, "f_score": 8, "dcf_note": None}

    monkeypatch.setattr(staged_runtime, "compute_factor_scores", score)
    monkeypatch.setattr(staged_runtime, "compute_anti_trap", lambda _: {"score": 100.0, "flags": []})
    monkeypatch.setattr(staged_runtime, "check_heat_filter", lambda _: {"pass": True, "failed_filters": []})
    data["bad"]["ticker"] = "bad"
    data["good"]["ticker"] = "good"

    candidates, failures = staged_runtime._score_final_candidates(data, ["bad", "good"])

    assert [candidate["ticker"] for candidate in candidates] == ["good"]
    assert failures[0]["ticker"] == "bad"
    assert failures[0]["reason"] == "scoring_failed"


def test_suffix_first_input_uses_provider_code_but_exposes_canonical_identity():
    fetcher = FakeBatchFetcher({"600001": _complete_results()["600001"]})

    result = run_staged_screening(["600001.SH"], fetcher=fetcher, run_id="suffix-first")

    assert fetcher.calls[0][0] == ["600001"]
    assert result.ticker_evidence.keys() == {"600001.SH"}
    assert result.candidates[0]["ticker"] == "600001.SH"


def test_failure_evidence_is_deduplicated_and_requests_are_exposed():
    results = _complete_results()
    results["600001"]["financials"] = {"__error__": True, "error": "provider down"}
    fetcher = FakeBatchFetcher(results)

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="dedupe")

    failures = result.stages["B"].failures
    assert len(failures) == 1
    assert result.stages["B"].requests == [
        {"tickers": ["600001"], "dimensions": ("financials", "risk")},
    ]


def test_result_has_json_serializable_evidence_and_raw_dimension_results():
    fetcher = FakeBatchFetcher({"600001": _complete_results()["600001"]})

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="serialize")
    payload = result.to_dict()

    assert payload["run_id"] == "serialize"
    assert payload["stages"]["A"]["dimension_results"]["600001"]["basic"]["market_cap"] == 10e9
    assert json.loads(json.dumps(payload, ensure_ascii=False))["run_id"] == "serialize"


def test_default_entry_requires_explicit_fetcher():
    with pytest.raises(ValueError, match="fetcher"):
        run_staged_screening(["600001"], run_id="no-implicit-fetch")


def test_run_identity_and_canonical_ticker_set_are_stable():
    fetcher = FakeBatchFetcher({"600001": _complete_results()["600001"]})

    first = run_staged_screening(["600001", "600001.SH"], fetcher=fetcher)
    second = run_staged_screening(["600001"], fetcher=fetcher)

    assert first.run_id != second.run_id
    assert first.ticker_evidence.keys() == {"600001.SH"}
    assert first.input_ticker_set_hash == second.input_ticker_set_hash
    assert first.candidates[0]["ticker"] == "600001.SH"


def test_top_300_and_heat_filter_parity(monkeypatch):
    from screener import staged_runtime

    data = {str(i): {"basic": {"industry": "行业A", "pe": 10.0}} for i in range(301)}
    calls = []

    monkeypatch.setattr(
        staged_runtime,
        "compute_industry_median_pe",
        lambda all_data: {"行业A": 10.0} if len(all_data) == 301 else {},
    )
    monkeypatch.setattr(
        staged_runtime,
        "compute_factor_scores",
        lambda ticker_data, industry_pe: {
            "composite": float(ticker_data["score"]),
            "f_score": 9,
            "dcf_note": None,
        },
    )
    monkeypatch.setattr(staged_runtime, "compute_anti_trap", lambda data: {"score": 100.0, "flags": []})

    def fake_heat(data):
        calls.append(data["score"])
        return {"pass": True, "failed_filters": []}

    monkeypatch.setattr(staged_runtime, "check_heat_filter", fake_heat)
    for index, ticker_data in enumerate(data.values()):
        ticker_data["score"] = float(index)

    candidates, _failures = staged_runtime._score_final_candidates(data, list(data))

    assert len(candidates) == 300
    assert len(calls) == 300
    assert candidates[0]["ticker"] == "300"
    assert candidates[-1]["ticker"] == "1"


def test_stage_c_heat_failure_is_recorded():
    results = _complete_results()
    results["600001"]["kline"]["close"][-1] = 20.0
    fetcher = FakeBatchFetcher(results)

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="heat-failure")

    assert result.candidates == []
    assert any(
        failure["reason"] == "heat_filter_failed"
        for failure in result.stages["C"].failures
    )
    assert any(
        failure["failed_filters"]
        for failure in result.stages["C"].failures
        if failure["reason"] == "heat_filter_failed"
    )
def test_offline_runtime_has_no_implicit_side_effects(tmp_path):
    fetcher = FakeBatchFetcher({"600001": _complete_results()["600001"]})

    result = run_staged_screening(["600001"], fetcher=fetcher, run_id="offline")

    assert result.evidence_path is None
    assert list(tmp_path.iterdir()) == []


def test_batch_fetcher_telemetry_separates_cache_hit_and_provider_call():
    cache = MagicMock()
    cache.get.side_effect = [
        {"ticker": "600001", "cached": True},
        None,
    ]
    telemetry = FetchTelemetry()
    fetcher = BatchFetcher(max_workers=1, cache=cache)

    with patch("data.lib.batch_fetcher.time.sleep", lambda *_: None), \
         patch(
             "data.fetchers.basic.BasicFetcher.fetch_with_fallback",
             lambda _self, ticker: {"ticker": ticker, "fresh": True},
         ):
        result = fetcher.fetch_all(
            ["600001", "600002"],
            dimensions=["basic"],
            telemetry=telemetry,
        )

    assert result["600001"]["basic"] == {"ticker": "600001", "cached": True}
    assert result["600002"]["basic"] == {"ticker": "600002", "fresh": True}
    assert telemetry.cache_hits == [{"ticker": "600001", "dimension": "basic"}]
    assert telemetry.provider_calls == [{"ticker": "600002", "dimension": "basic"}]
    assert telemetry.failures == []
