from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.modules.setdefault("akshare", SimpleNamespace())

from data.lib.identity import compute_input_ticker_set_hash
from screener.small_sample import (  # noqa: E402
    render_small_sample_markdown,
    render_small_sample_json,
    run_small_sample,
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
            "net_profit": [10.0, 11.0, 12.0],
        },
        "balance_sheet": {
            "TOTAL_ASSETS": [100.0, 105.0, 110.0],
            "TOTAL_CURRENT_LIAB": [20.0, 20.0, 20.0],
            "TOTAL_NONCURRENT_LIAB": [20.0, 20.0, 20.0],
        },
        "cash_flow": {
            "NETCASH_OPERATE": [12.0, 13.0, 14.0],
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
        "pe_history": [10.0, 11.0, 12.0],
    }


def _kline() -> dict:
    return {
        "close": [10.0] * 60,
        "turnover_rate": [2.0] * 60,
    }


def _complete_dimensions() -> dict:
    return {
        "basic": _basic(),
        "financials": _financials(),
        "risk": _risk(),
        "valuation": _valuation(),
        "kline": _kline(),
    }


def _bundle(
    *,
    tickers: list[str] | None = None,
    data: dict[str, dict] | None = None,
    provenance: dict | None = None,
) -> dict:
    tickers = tickers or ["600001", "600002", "600003", "600004", "600005"]
    if data is None:
        data = {ticker: _complete_dimensions() for ticker in tickers}
        if "600003" in data:
            data["600003"]["financials"] = {
                "__error__": True,
                "error": "fixture financials failed",
            }
    return {
        "schema_version": "g1-small-sample-run/v1",
        "artifact_type": "fixture/reference",
        "mode": "simulated/development",
        "run_id": "m1-2-fixture-run",
        "profile_version": "g1-2026-07-21",
        "input_ticker_set_hash": compute_input_ticker_set_hash(tickers),
        "as_of": "2026-08-31",
        "provenance": provenance
        or {
            "source": "fixture/reference",
            "not_live_provider_evidence": True,
        },
        "tickers": tickers,
        "data": data,
    }


def test_identity_is_validated_before_staged_execution():
    bundle = _bundle()
    bundle["input_ticker_set_hash"] = "wrong-hash"

    with pytest.raises(ValueError, match="input_ticker_set_hash"):
        run_small_sample(bundle)


def test_live_fixture_provenance_is_rejected():
    bundle = _bundle(
        provenance={
            "source": "live-provider",
            "not_live_provider_evidence": True,
        }
    )

    with pytest.raises(ValueError, match="live"):
        run_small_sample(bundle)


@pytest.mark.parametrize(
    "provenance",
    [
        {"source": "fixture/reference", "not_live_provider_evidence": True, "provider": "akshare"},
        {"source": "fixture/reference", "not_live_provider_evidence": True, "live": True},
        {
            "source": "fixture/reference",
            "not_live_provider_evidence": True,
            "execution_mode": "production",
        },
    ],
)
def test_provenance_rejects_hidden_live_or_provider_markers(provenance):
    with pytest.raises(ValueError, match="provenance"):
        run_small_sample(_bundle(provenance=provenance))


def test_fixture_input_is_capped_to_small_sample_scope():
    tickers = [f"600{index:03d}" for index in range(21)]
    bundle = _bundle(tickers=tickers, data={ticker: _complete_dimensions() for ticker in tickers})

    with pytest.raises(ValueError, match="at most 20"):
        run_small_sample(bundle)


def test_fixture_input_requires_at_least_five_unique_tickers():
    tickers = ["600001", "600002", "600003", "600004"]
    bundle = _bundle(tickers=tickers, data={ticker: _complete_dimensions() for ticker in tickers})

    with pytest.raises(ValueError, match="at least 5"):
        run_small_sample(bundle)


def test_missing_fixture_provenance_marker_is_rejected():
    bundle = _bundle(provenance={"source": "fixture/reference"})

    with pytest.raises(ValueError, match="not_live_provider_evidence"):
        run_small_sample(bundle)


def test_per_ticker_stage_failure_and_candidate_are_visible():
    result = run_small_sample(_bundle())

    by_ticker = {item["ticker"]: item for item in result["tickers"]}
    assert by_ticker["600001.SH"]["candidate"] is True
    assert by_ticker["600001.SH"]["quality_status"] == "complete"
    assert by_ticker["600001.SH"]["scores"]["adjusted_composite"] is not None
    assert by_ticker["600001.SH"]["details"]["pe_ttm"] == 12.0
    assert by_ticker["600001.SH"]["details"]["f_score"] is not None

    failed = by_ticker["600003.SH"]
    assert failed["candidate"] is False
    assert failed["stage_statuses"]["A"] == "passed"
    assert failed["stage_statuses"]["B"] == "failed"
    assert failed["stage_statuses"]["C"] == "not_reached"
    assert failed["exclusion"]["stage"] == "B"
    assert failed["exclusion"]["status"] == "source_failed"
    assert failed["quality_status"] == "failed"


def test_renderers_are_deterministic_and_preserve_not_evidence_boundary():
    first = _bundle(tickers=["600003", "600001", "600002", "600004", "600005"])
    second = _bundle(tickers=["600001", "600002", "600003", "600004", "600005"])

    first_result = run_small_sample(first)
    second_result = run_small_sample(second)

    assert render_small_sample_json(first_result) == render_small_sample_json(second_result)
    assert render_small_sample_markdown(first_result) == render_small_sample_markdown(
        second_result
    )
    assert "composite" in render_small_sample_markdown(first_result)
    assert "PE/PB" in render_small_sample_markdown(first_result)
    payload = json.loads(render_small_sample_json(first_result))
    assert payload["capability_status"] == "not_evidence"
    assert payload["artifact_type"] == "fixture/reference"
    assert [item["ticker"] for item in payload["tickers"]] == [
        "600001.SH",
        "600002.SH",
        "600003.SH",
        "600004.SH",
        "600005.SH",
    ]
    assert "provenance.source" in render_small_sample_markdown(first_result)


def test_cli_writes_run_scoped_json_and_markdown(tmp_path):
    from typer.testing import CliRunner

    from cli import app

    input_path = tmp_path / "fixture.json"
    input_path.write_text(
        json.dumps(_bundle(), ensure_ascii=False),
        encoding="utf-8",
    )
    output_dir = tmp_path / "results"

    result = CliRunner().invoke(
        app,
        [
            "small-sample-run",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (output_dir / "m1-2-fixture-run.json").exists()
    assert (output_dir / "m1-2-fixture-run.md").exists()
    assert not (tmp_path / "watchlist").exists()
    assert not (tmp_path / "debate").exists()


def test_protected_output_root_is_rejected_before_write():
    from screener.small_sample import write_small_sample_artifacts

    repo_root = Path(__file__).resolve().parents[2]
    protected = repo_root / "value-screener" / "data" / "cache"
    with pytest.raises(ValueError, match="protected production output root"):
        write_small_sample_artifacts(_bundle(), protected)
    assert not (protected / "m1-2-fixture-run.json").exists()


def test_heat_filter_exclusion_keeps_previously_computed_scores():
    hot = _complete_dimensions()
    hot["kline"]["close"] = [10.0] * 59 + [13.0]
    tickers = ["600001", "600002", "600003", "600004", "600005"]
    data = {ticker: _complete_dimensions() for ticker in tickers}
    data["600001"] = hot
    bundle = _bundle(tickers=tickers, data=data)

    result = run_small_sample(bundle)
    item = next(item for item in result["tickers"] if item["ticker"] == "600001.SH")
    assert item["candidate"] is False
    assert item["exclusion"]["reason_code"] == "heat_filter_failed"
    assert item["scores"]["adjusted_composite"] is not None
    assert item["details"]["pe_ttm"] == 12.0


def test_same_run_id_cannot_overwrite_different_input(tmp_path):
    from screener.small_sample import write_small_sample_artifacts

    output_dir = tmp_path / "results"
    write_small_sample_artifacts(_bundle(), output_dir)
    changed = json.loads(json.dumps(_bundle(), ensure_ascii=False))
    changed["data"]["600001"]["basic"]["name"] = "不同输入"

    with pytest.raises(ValueError, match="immutable"):
        write_small_sample_artifacts(changed, output_dir)
