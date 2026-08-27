from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from cli import app
from data.lib.frozen_growth_diagnostic import (
    FrozenInputBundleError,
    compute_frozen_growth_artifact_digest,
    run_frozen_input_growth_diagnostic,
    validate_frozen_growth_diagnostic_artifact,
)


RAW_HASH = "a" * 64


def _source(field: str, *, freshness: str = "fresh", degradation_status: str = "clean"):
    return {
        "ticker": "600519.SH",
        "source_id": f"fixture-{field}",
        "provider": "fixture",
        "field": field,
        "raw_field": f"raw_{field}",
        "raw_payload_hash": RAW_HASH,
        "report_period": "2025-12-31",
        "as_of": "2026-08-24",
        "freshness": freshness,
        "currency": "CNY",
        "value_scale": "hundred_million",
        "published_at": "2026-03-31",
        "degradation_status": degradation_status,
    }


def _diagnostic_input(*, industry: str | None = None, market_value: float = 1800.0):
    return {
        "schema_version": "g2-growth-expectation-input-v1",
        "ticker": "600519.SH",
        "valuation_date": "2026-08-24",
        "report_period": "2025-12-31",
        "as_of": "2026-08-24",
        "currency": "CNY",
        "value_scale": "hundred_million",
        "current_market_value": market_value,
        "normalized_operating_cashflow": 150.0,
        "normalized_earnings": 150.0,
        "total_capex": 60.0,
        "normalized_net_profit": 90.0,
        "sources": [
            _source("current_market_value"),
            _source("normalized_operating_cashflow"),
            _source("normalized_earnings"),
            _source("total_capex"),
            _source("normalized_net_profit"),
        ],
        "industry": industry,
    }


def _assumptions(mode: str = "fixed_growth_rate"):
    values = [
        ("normalized_earnings_basis", "normalized_operating_cashflow", ""),
        ("maintenance_capex_ratio", [0.4, 0.6], "ratio"),
        ("cost_of_equity", [0.09, 0.11], "decimal"),
        ("maintenance_growth", 0.02, "decimal"),
        ("credible_growth_rate", [0.08, 0.12, 0.18], "decimal"),
        ("mature_pe", [18.0, 22.0], "x"),
        ("reverse_mode", mode, ""),
    ]
    values.append(
        (
            "reverse_fixed_growth_rate"
            if mode == "fixed_growth_rate"
            else "reverse_fixed_duration_years",
            [0.10, 0.12, 0.15] if mode == "fixed_growth_rate" else [3.0, 5.0, 8.0],
            "decimal" if mode == "fixed_growth_rate" else "years",
        )
    )
    return {
        "version": "g2-assumption-snapshot-v1",
        "created_at": "2026-08-24",
        "assumptions": [
            {
                "key": key,
                "value": value,
                "unit": unit,
                "source": "user_confirmed",
                "confirmed_by_user": True,
                "version": "v1",
            }
            for key, value, unit in values
        ],
    }


def _bundle(
    *,
    mode: str = "fixed_growth_rate",
    industry: str | None = None,
    market_value: float = 1800.0,
):
    return {
        "schema_version": "m0-frozen-growth-diagnostic-bundle-v1",
        "canonical_ticker": "600519.SH",
        "run_id": "m0-run-001",
        "dossier_snapshot": "dossier-v1",
        "profile_version": "profile-v1",
        "diagnostic_input": _diagnostic_input(
            industry=industry,
            market_value=market_value,
        ),
        "assumption_snapshot": _assumptions(mode),
    }


def test_valid_frozen_bundle_generates_bound_json_and_markdown(tmp_path):
    result = run_frozen_input_growth_diagnostic(_bundle(), tmp_path)

    assert result.json_path == tmp_path / "600519.SH-m0-run-001.json"
    assert result.markdown_path == tmp_path / "600519.SH-m0-run-001.md"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    diagnostic = payload["diagnostic"]
    assert payload["artifact_type"] == "growth_expectation_diagnostic"
    assert payload["capability_status"] == "mvp_evidence"
    assert payload["gate_status"] == "not_passed"
    assert diagnostic["calculation_status"] in {"clean", "degraded"}
    assert diagnostic["decision_grade"] == "diagnostic"
    assert diagnostic["input_digest"]
    assert diagnostic["diagnostic_digest"]
    assert payload["artifact_digest"] == compute_frozen_growth_artifact_digest(payload)
    assert "source_id" in result.markdown_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mode", "field"),
    [
        ("fixed_growth_rate", "implied_high_growth_duration"),
        ("fixed_duration", "implied_growth_rate"),
    ],
)
def test_reverse_mode_is_preserved_in_three_scenarios(tmp_path, mode, field):
    result = run_frozen_input_growth_diagnostic(_bundle(mode=mode), tmp_path)
    diagnostic = json.loads(result.json_path.read_text(encoding="utf-8"))["diagnostic"]

    scenarios = diagnostic["reverse_scenarios"]
    assert len(scenarios) == 3
    assert {scenario["mode"] for scenario in scenarios} == {mode}
    assert all(scenario[field] is not None for scenario in scenarios)


def test_same_bundle_has_stable_digests_and_artifact_content(tmp_path):
    first = run_frozen_input_growth_diagnostic(_bundle(), tmp_path / "one")
    second = run_frozen_input_growth_diagnostic(_bundle(), tmp_path / "two")

    first_payload = json.loads(first.json_path.read_text(encoding="utf-8"))
    second_payload = json.loads(second.json_path.read_text(encoding="utf-8"))
    assert first_payload["diagnostic"] == second_payload["diagnostic"]
    assert first_payload["diagnostic"]["input_digest"] == second_payload["diagnostic"]["input_digest"]
    assert first_payload["diagnostic"]["diagnostic_digest"] == second_payload["diagnostic"]["diagnostic_digest"]
    assert first.markdown_path.read_text(encoding="utf-8") == second.markdown_path.read_text(encoding="utf-8")


def test_artifact_binding_rejects_run_id_relabeling(tmp_path):
    result = run_frozen_input_growth_diagnostic(_bundle(), tmp_path)
    artifact = json.loads(result.json_path.read_text(encoding="utf-8"))
    artifact["run_id"] = "m0-run-other"

    with pytest.raises(FrozenInputBundleError, match="run_id mismatch|digest mismatch"):
        validate_frozen_growth_diagnostic_artifact(artifact, _bundle())


def test_artifact_preserves_provenance_sources_and_user_assumptions(tmp_path):
    result = run_frozen_input_growth_diagnostic(_bundle(), tmp_path)
    diagnostic = json.loads(result.json_path.read_text(encoding="utf-8"))["diagnostic"]

    assert diagnostic["input_snapshot"]["sources"][0]["report_period"] == "2025-12-31"
    assert diagnostic["input_snapshot"]["sources"][0]["as_of"] == "2026-08-24"
    assert diagnostic["input_snapshot"]["sources"][0]["currency"] == "CNY"
    assert diagnostic["input_snapshot"]["sources"][0]["value_scale"] == "hundred_million"
    assert diagnostic["assumption_snapshot"]["assumptions"][0]["confirmed_by_user"] is True
    assert diagnostic["provenance"] == {
        "dossier_snapshot": "dossier-v1",
        "profile_version": "profile-v1",
        "formula_version": "v0-epv-proxy-repair-2",
        "assumption_snapshot_version": "g2-assumption-snapshot-v1",
    }


def test_not_evaluable_artifact_has_no_numeric_conclusions(tmp_path):
    result = run_frozen_input_growth_diagnostic(_bundle(industry="banking"), tmp_path)
    diagnostic = json.loads(result.json_path.read_text(encoding="utf-8"))["diagnostic"]

    assert diagnostic["calculation_status"] == "not_evaluable"
    assert diagnostic["failure_kind"] == "model_not_applicable"
    assert diagnostic["current_market_value"] is None
    assert diagnostic["current_business_value"] is None
    assert diagnostic["reverse_scenarios"] == []
    assert diagnostic["reason_codes"]
    assert diagnostic["input_digest"]
    assert diagnostic["diagnostic_digest"]


def test_failed_no_finite_solution_artifact_has_no_numeric_conclusions(tmp_path):
    result = run_frozen_input_growth_diagnostic(
        _bundle(market_value=1_000_000.0),
        tmp_path,
    )
    diagnostic = json.loads(result.json_path.read_text(encoding="utf-8"))["diagnostic"]

    assert diagnostic["calculation_status"] == "failed"
    assert diagnostic["failure_kind"] == "computation_failed"
    assert diagnostic["current_market_value"] is None
    assert diagnostic["priced_growth_value_range"] is None
    assert diagnostic["reverse_scenarios"] == []
    assert diagnostic["reason_codes"]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda bundle: bundle.pop("run_id"),
        lambda bundle: bundle["canonical_ticker"] == "600519.SH"
        and bundle["diagnostic_input"].update(ticker="600036.SH"),
        lambda bundle: bundle["diagnostic_input"].pop("currency"),
    ],
)
def test_invalid_or_mismatched_bundle_fails_closed_without_artifacts(tmp_path, mutator):
    bundle = _bundle()
    if callable(mutator):
        mutator(bundle)

    with pytest.raises(FrozenInputBundleError):
        run_frozen_input_growth_diagnostic(bundle, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_output_is_confined_to_explicit_directory(tmp_path):
    output_dir = tmp_path / "artifacts"
    result = run_frozen_input_growth_diagnostic(_bundle(), output_dir)

    assert result.json_path.parent == output_dir
    assert result.markdown_path.parent == output_dir
    assert not (tmp_path / "600519.SH-m0-run-001.json").exists()


def test_noncanonical_bundle_ticker_fails_closed(tmp_path):
    bundle = _bundle()
    bundle["canonical_ticker"] = "600519"

    with pytest.raises(FrozenInputBundleError):
        run_frozen_input_growth_diagnostic(bundle, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_markdown_is_diagnostic_only_and_exposes_unknowns(tmp_path):
    result = run_frozen_input_growth_diagnostic(_bundle(), tmp_path)
    markdown = result.markdown_path.read_text(encoding="utf-8")

    assert "growth expectation diagnostic" in markdown.lower()
    assert "当前无法证明" in markdown
    assert "target_price" not in markdown
    assert "买入" not in markdown
    assert "卖出" not in markdown


def test_markdown_has_one_unknowns_section_for_failure(tmp_path):
    result = run_frozen_input_growth_diagnostic(_bundle(industry="banking"), tmp_path)
    markdown = result.markdown_path.read_text(encoding="utf-8")

    assert markdown.count("## 当前无法证明") == 1


def test_cli_growth_diagnostic_does_not_initialize_fetchers_or_llm(tmp_path, monkeypatch):
    input_path = tmp_path / "input.json"
    output_dir = tmp_path / "output"
    input_path.write_text(json.dumps(_bundle()), encoding="utf-8")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("provider/LLM path was initialized")

    monkeypatch.setattr("cli._get_fetcher", fail_if_called)
    result = CliRunner().invoke(
        app,
        [
            "growth-diagnostic",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout


def test_cli_reads_explicit_input_and_prints_artifact_paths(tmp_path):
    input_path = tmp_path / "input.json"
    output_dir = tmp_path / "output"
    input_path.write_text(
        json.dumps(_bundle(), ensure_ascii=False),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "growth-diagnostic",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "600519.SH-m0-run-001.json" in result.stdout
    assert (output_dir / "600519.SH-m0-run-001.json").is_file()
    assert (output_dir / "600519.SH-m0-run-001.md").is_file()
