"""D1 experiment harness must fail closed before any live LLM call."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.repro_out.crosstalk_exp import (
    CONTROL_GROUPS,
    build_prompt_variant,
    build_frozen_dossier,
    load_verified_dossier,
    run_live_experiment,
    write_live_report,
)


def test_control_matrix_and_local_prompt_stripping():
    assert [group["id"] for group in CONTROL_GROUPS] == [
        "group1", "group2", "group3", "group4"
    ]
    assert "可口可乐 → 茅台" in build_prompt_variant("buffett", "retained")
    assert "可口可乐 → 茅台" not in build_prompt_variant("buffett", "stripped")


def test_verified_dossier_rejects_insufficient_data_snapshot(tmp_path: Path):
    path = tmp_path / "600009.json"
    path.write_text(json.dumps({"error": "insufficient_data"}), encoding="utf-8")

    with pytest.raises(ValueError, match="verified dossier"):
        load_verified_dossier(path)


def test_verified_dossier_requires_600009_identity(tmp_path: Path):
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({
        "core_snapshot": {"ticker": "600519.SH", "pe_ttm": 20.0},
        "research_dossier": {"main_business": {"text": "x"}},
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="600009.SH"):
        load_verified_dossier(path)


def test_build_frozen_dossier_copies_read_only_cache_into_envelope(tmp_path: Path):
    source = tmp_path / "source-cache" / "600009"
    source.mkdir(parents=True)
    for name, payload in {
        "basic.json": {
            "code": "600009", "name": "上海机场", "price": 35.0,
            "pe": 26.42, "pb": 2.31, "market_cap": 1000, "industry": "机场",
        },
        "financials.json": {
            "years": ["2023"], "income": {"net_profit": [1]},
            "balance_sheet": {}, "cash_flow": {"CONSTRUCT_LONG_ASSET": [2]},
        },
        "valuation.json": {
            "pe_ttm": 26.42, "pb": 2.31,
            "pe_percentile_5y": 0.4, "pb_percentile_5y": 0.3,
        },
        "main_business.json": {"code": "600009", "by_industry": []},
        "research.json": {"code": "600009", "coverage_count": 0},
        "risk.json": {"pledge_ratio": 0.0, "goodwill": 0.0, "audit_opinion": "clean"},
        "kline.json": {
            "dates": ["2026-08-18"], "close": [35.0],
            "volume": [100], "turnover_rate": [1.0],
        },
    }.items():
        (source / name).write_text(json.dumps(payload), encoding="utf-8")

    output = tmp_path / "frozen.json"
    dossier = build_frozen_dossier(source, output)

    assert dossier["core_snapshot"]["ticker"] == "600009.SH"
    assert dossier["research_dossier"]["main_business"]["code"] == "600009"
    assert dossier["freeze"]["source_ticker"] == "600009"
    assert len(dossier["freeze"]["source_files"]) == 7
    assert output.exists()
    assert load_verified_dossier(output)["freeze"]["source_sha256"]


def test_live_experiment_requires_verified_dossier_before_llm(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "LLM_API_KEY=x\nLLM_API_BASE=http://example\n"
        "LLM_MODEL=weak\nLLM_MODEL_HEAVY=strong\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="verified dossier"):
        __import__("asyncio").run(run_live_experiment(tmp_path / "out", env, tmp_path / "missing.json"))


def test_live_record_contract_keeps_parsed_output_and_run_metadata():
    raw = Path("value-screener/scripts/repro_out/crosstalk_exp_live_20260819/crosstalk_exp_raw/group1.json")
    if not raw.exists():
        pytest.skip("live bundle not present in a clean test checkout")
    payload = json.loads(raw.read_text(encoding="utf-8"))
    assert payload["input_mode"] == "frozen_dossier"
    for record in payload["records"]:
        assert record["status"] == "ok"
        assert record["output"]["name"] == record["agent"]
        assert record["system_prompt_sha256"]
        assert record["user_message_sha256"]
        assert record["dossier_sha256"]
        assert record["usage"]


def test_live_report_records_four_group_metrics_and_f3e_boundary(tmp_path: Path):
    payload = {
        "mode": "live",
        "input_mode": "frozen_dossier",
        "source_sha256": "abc",
        "groups": {
            group["id"]: {
                **group,
                "status": "complete",
                "metrics": {
                    "explicit_crosstalk_rate": 0.0,
                    "implicit_crosstalk_rate": 0.0,
                    "fabricated_number_rate": 0.25,
                    "citation_divergence": {"mean_distance": 0.5},
                },
            }
            for group in CONTROL_GROUPS
        },
    }
    report = write_live_report(tmp_path, payload)
    assert "frozen_dossier" in report
    assert "group4" in report
    assert "neither" in report
    assert "f3e" in report
    assert (tmp_path / "crosstalk_exp_report.md").exists()
