from __future__ import annotations

import math

import pytest

from data.lib.growth_expectation_contract import (
    ASSUMPTION_SNAPSHOT_VERSION,
    GROWTH_EXPECTATION_SCHEMA_VERSION,
    ContractError,
    compute_input_digest,
    evaluate_applicability,
    validate_assumption_snapshot,
    validate_diagnostic,
    validate_diagnostic_binding,
    validate_diagnostic_input,
)

FORMULA_VERSION = "v0-epv-proxy"


def _source(field: str, freshness: str = "fresh") -> dict:
    return {
        "source_id": f"src-{field}",
        "field": field,
        "report_period": "2025-12-31",
        "as_of": "2026-08-24",
        "freshness": freshness,
        "currency": "CNY",
        "value_scale": "hundred_million",
        "published_at": "2026-03-31",
        "degradation_status": "clean",
    }


def _valid_input() -> dict:
    return {
        "schema_version": "g2-growth-expectation-input-v1",
        "ticker": "600519.SH",
        "valuation_date": "2026-08-24",
        "report_period": "2025-12-31",
        "as_of": "2026-08-24",
        "currency": "CNY",
        "value_scale": "hundred_million",
        "current_market_value": 1200.0,
        "normalized_operating_cashflow": 150.0,
        "total_capex": 60.0,
        "normalized_net_profit": 90.0,
        "sources": [
            _source("current_market_value"),
            _source("normalized_operating_cashflow"),
            _source("total_capex"),
            _source("normalized_net_profit"),
        ],
    }


def _valid_assumptions(reverse_mode: str = "fixed_growth_rate") -> dict:
    return {
        "version": ASSUMPTION_SNAPSHOT_VERSION,
        "created_at": "2026-08-24",
        "assumptions": [
            {
                "key": "normalized_earnings_basis",
                "value": "normalized_operating_cashflow",
                "unit": "",
                "source": "user_confirmed",
                "confirmed_by_user": True,
                "version": "v1",
            },
            {
                "key": "maintenance_capex_ratio",
                "value": 0.5,
                "unit": "ratio",
                "source": "user_confirmed",
                "confirmed_by_user": True,
                "version": "v1",
            },
            {
                "key": "cost_of_equity",
                "value": 0.10,
                "unit": "decimal",
                "source": "user_confirmed",
                "confirmed_by_user": True,
                "version": "v1",
            },
            {
                "key": "maintenance_growth",
                "value": 0.02,
                "unit": "decimal",
                "source": "user_confirmed",
                "confirmed_by_user": True,
                "version": "v1",
            },
            {
                "key": "credible_growth_rate",
                "value": [0.08, 0.12, 0.18],
                "unit": "decimal",
                "source": "user_confirmed",
                "confirmed_by_user": True,
                "version": "v1",
            },
            {
                "key": "mature_pe",
                "value": 20.0,
                "unit": "x",
                "source": "user_confirmed",
                "confirmed_by_user": True,
                "version": "v1",
            },
            {
                "key": "reverse_mode",
                "value": reverse_mode,
                "unit": "",
                "source": "user_confirmed",
                "confirmed_by_user": True,
                "version": "v1",
            },
            (
                {
                    "key": "reverse_fixed_growth_rate",
                    "value": 0.12,
                    "unit": "decimal",
                    "source": "user_confirmed",
                    "confirmed_by_user": True,
                    "version": "v1",
                }
                if reverse_mode == "fixed_growth_rate"
                else {
                    "key": "reverse_fixed_duration_years",
                    "value": 5.0,
                    "unit": "years",
                    "source": "user_confirmed",
                    "confirmed_by_user": True,
                    "version": "v1",
                }
            ),
        ],
    }


def _base_diagnostic() -> dict:
    return {
        "schema_version": GROWTH_EXPECTATION_SCHEMA_VERSION,
        "ticker": "600519.SH",
        "valuation_date": "2026-08-24",
        "report_period": "2025-12-31",
        "currency": "CNY",
        "value_scale": "hundred_million",
        "calculation_status": "clean",
        "quality_status": "warning",
        "decision_grade": "diagnostic",
        "failure_kind": None,
        "reason_codes": [],
        "reasons": [],
        "warnings": [],
        "current_market_value": 1200.0,
        "assumption_snapshot": _valid_assumptions(),
        "current_business_value": {
            "epv_proxy_range": [800.0, 1000.0],
            "mature_multiple_range": [900.0, 1100.0],
            "anchor_divergence": "moderate",
        },
        "priced_growth_value_range": [300.0, 400.0],
        "priced_growth_share_range": [0.1, 0.25],
        "reverse_scenarios": [
            {
                "mode": "fixed_growth_rate",
                "growth_rate": 0.12,
                "implied_high_growth_duration": 6.0,
            }
        ],
        "credible_growth_range": [0.08, 0.18],
        "expectation_gap": [0.02, 0.06],
        "expectation_overdraft": "within_credible_range",
        "sensitivity": [
            {
                "assumption_key": "maintenance_capex_ratio",
                "value": 0.6,
                "impact_range": [0.08, 0.28],
            }
        ],
        "evidence": [],
        "provenance": {
            "dossier_snapshot": "dossier-v1",
            "profile_version": "profile-v1",
            "formula_version": FORMULA_VERSION,
            "assumption_snapshot_version": ASSUMPTION_SNAPSHOT_VERSION,
        },
        "input_digest": "a" * 64,
    }


def _bound_diagnostic() -> dict:
    payload = _base_diagnostic()
    payload["input_digest"] = compute_input_digest(
        ticker="600519.SH",
        input_payload=_valid_input(),
        assumption_snapshot=_valid_assumptions(),
        formula_version=FORMULA_VERSION,
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )
    return payload


def _strip_numbers(
    payload: dict,
    *,
    status: str,
    failure_kind: str,
    reason_codes: list[str],
    reasons: list[str],
) -> dict:
    payload.update(
        {
            "calculation_status": status,
            "quality_status": "failed" if status == "failed" else "warning",
            "decision_grade": "diagnostic",
            "failure_kind": failure_kind,
            "reason_codes": reason_codes,
            "reasons": reasons,
            "warnings": [],
            "current_market_value": None,
            "assumption_snapshot": None,
            "current_business_value": None,
            "priced_growth_value_range": None,
            "priced_growth_share_range": None,
            "reverse_scenarios": [],
            "credible_growth_range": None,
            "expectation_gap": None,
            "expectation_overdraft": None,
            "sensitivity": [],
            "evidence": [],
            "provenance": {
                "dossier_snapshot": "dossier-v1",
                "profile_version": "profile-v1",
                "formula_version": FORMULA_VERSION,
                "assumption_snapshot_version": ASSUMPTION_SNAPSHOT_VERSION,
            },
            "input_digest": "a" * 64,
        }
    )
    return payload


# Input contract


def test_input_contract_accepts_valid_payload():
    parsed = validate_diagnostic_input(_valid_input())
    assert parsed.ticker == "600519.SH"
    assert parsed.normalized_operating_cashflow == 150.0


def test_input_contract_rejects_missing_field():
    payload = _valid_input()
    payload.pop("report_period")
    with pytest.raises(ContractError, match="report_period"):
        validate_diagnostic_input(payload)


@pytest.mark.parametrize("field", ["currency", "value_scale"])
def test_input_contract_rejects_unknown_unit(field):
    payload = _valid_input()
    payload[field] = "not-a-unit"
    with pytest.raises(ContractError, match="not supported"):
        validate_diagnostic_input(payload)


@pytest.mark.parametrize("bad", [-1.0, math.nan, math.inf])
def test_input_contract_rejects_illegal_market_value(bad):
    payload = _valid_input()
    payload["current_market_value"] = bad
    with pytest.raises(ContractError):
        validate_diagnostic_input(payload)


@pytest.mark.parametrize(
    "field",
    ["normalized_operating_cashflow", "total_capex", "normalized_net_profit"],
)
def test_input_contract_rejects_non_finite_financial_field(field):
    payload = _valid_input()
    payload[field] = math.nan
    with pytest.raises(ContractError, match="finite"):
        validate_diagnostic_input(payload)


def test_input_contract_rejects_negative_total_capex():
    payload = _valid_input()
    payload["total_capex"] = -1.0
    with pytest.raises(ContractError, match="non-negative"):
        validate_diagnostic_input(payload)


def test_input_contract_rejects_source_mismatch():
    payload = _valid_input()
    payload["sources"][0]["as_of"] = "2025-01-01"
    with pytest.raises(ContractError, match="as_of mismatch"):
        validate_diagnostic_input(payload)


def test_input_contract_rejects_missing_field_level_source():
    payload = _valid_input()
    payload["sources"] = [
        source for source in payload["sources"] if source["field"] != "total_capex"
    ]
    with pytest.raises(ContractError, match="missing field-level sources"):
        validate_diagnostic_input(payload)


def test_input_contract_rejects_duplicate_field_level_source():
    payload = _valid_input()
    payload["sources"].append(_source("current_market_value"))
    with pytest.raises(ContractError, match="duplicate field-level sources"):
        validate_diagnostic_input(payload)


# Output contract


def test_output_contract_accepts_clean_result():
    parsed = validate_diagnostic(_base_diagnostic())
    assert parsed.calculation_status == "clean"
    assert parsed.quality_status == "warning"
    assert parsed.decision_grade == "diagnostic"
    assert parsed.current_business_value is not None
    assert parsed.priced_growth_share_range == (0.1, 0.25)


def test_output_contract_accepts_degraded_result():
    payload = _base_diagnostic()
    payload["calculation_status"] = "degraded"
    payload["warnings"] = ["maintenance capex proxy only"]
    parsed = validate_diagnostic(payload)
    assert parsed.calculation_status == "degraded"
    assert parsed.warnings == ("maintenance capex proxy only",)


@pytest.mark.parametrize(
    "field",
    [
        "quality_status",
        "decision_grade",
        "current_market_value",
        "priced_growth_value_range",
        "priced_growth_share_range",
        "expectation_gap",
        "sensitivity",
        "credible_growth_range",
        "current_business_value",
    ],
)
def test_output_contract_clean_rejects_missing_required(field):
    payload = _base_diagnostic()
    payload.pop(field)
    with pytest.raises(ContractError):
        validate_diagnostic(payload)


def test_output_contract_clean_rejects_failed_quality_status():
    payload = _base_diagnostic()
    payload["quality_status"] = "failed"
    with pytest.raises(ContractError, match="quality_status"):
        validate_diagnostic(payload)


def test_output_contract_not_evaluable_has_no_numbers():
    payload = _strip_numbers(
        _base_diagnostic(),
        status="not_evaluable",
        failure_kind="model_not_applicable",
        reason_codes=["model_out_of_scope"],
        reasons=["financial industry"],
    )
    parsed = validate_diagnostic(payload)
    assert parsed.calculation_status == "not_evaluable"
    assert parsed.current_business_value is None
    assert parsed.priced_growth_share_range is None


def test_output_contract_failed_has_no_numbers_and_keeps_provenance():
    payload = _strip_numbers(
        _base_diagnostic(),
        status="failed",
        failure_kind="computation_failed",
        reason_codes=["solver_no_solution"],
        reasons=["no finite reverse solution"],
    )
    parsed = validate_diagnostic(payload)
    assert parsed.calculation_status == "failed"
    assert parsed.provenance is not None


def test_output_contract_failed_requires_provenance():
    payload = _strip_numbers(
        _base_diagnostic(),
        status="failed",
        failure_kind="computation_failed",
        reason_codes=["solver_no_solution"],
        reasons=["no finite reverse solution"],
    )
    payload["provenance"] = None
    with pytest.raises(ContractError, match="provenance"):
        validate_diagnostic(payload)


def test_output_contract_failed_rejects_invalid_reason_code():
    payload = _strip_numbers(
        _base_diagnostic(),
        status="failed",
        failure_kind="computation_failed",
        reason_codes=["bogus"],
        reasons=["no finite reverse solution"],
    )
    with pytest.raises(ContractError, match="unsupported value"):
        validate_diagnostic(payload)


def test_output_contract_failed_rejects_mismatched_reason_code():
    payload = _strip_numbers(
        _base_diagnostic(),
        status="failed",
        failure_kind="computation_failed",
        reason_codes=["model_out_of_scope"],
        reasons=["no finite reverse solution"],
    )
    with pytest.raises(ContractError, match="inconsistent with failure_kind"):
        validate_diagnostic(payload)


def test_failure_is_not_presented_as_clean():
    payload = _base_diagnostic()
    payload["failure_kind"] = "data_insufficient"
    with pytest.raises(ContractError, match="must not have failure_kind"):
        validate_diagnostic(payload)


# Assumption snapshot


def test_assumption_snapshot_accepts_complete_confirmed():
    parsed = validate_assumption_snapshot(_valid_assumptions())
    assert parsed.version == ASSUMPTION_SNAPSHOT_VERSION
    assert len(parsed.assumptions) == 8


def test_assumption_snapshot_rejects_missing_required_key():
    snapshot = _valid_assumptions()
    snapshot["assumptions"] = [
        item
        for item in snapshot["assumptions"]
        if item["key"] != "maintenance_capex_ratio"
    ]
    with pytest.raises(ContractError, match="missing required assumptions"):
        validate_assumption_snapshot(snapshot)


def test_assumption_snapshot_rejects_unconfirmed_assumption():
    snapshot = _valid_assumptions()
    snapshot["assumptions"][1]["confirmed_by_user"] = False
    with pytest.raises(ContractError, match="not confirmed"):
        validate_assumption_snapshot(snapshot)


def test_assumption_snapshot_rejects_duplicate_key():
    snapshot = _valid_assumptions()
    duplicate = dict(snapshot["assumptions"][1])
    snapshot["assumptions"].append(duplicate)
    with pytest.raises(ContractError, match="duplicate keys"):
        validate_assumption_snapshot(snapshot)


def test_assumption_snapshot_rejects_unit_mismatch():
    snapshot = _valid_assumptions()
    snapshot["assumptions"][2]["unit"] = "percent"
    with pytest.raises(ContractError, match="unit must be"):
        validate_assumption_snapshot(snapshot)


def test_assumption_value_is_immutable_after_parse():
    snapshot = _valid_assumptions()
    parsed = validate_assumption_snapshot(snapshot)
    credible = next(
        item for item in parsed.assumptions if item.key == "credible_growth_rate"
    )
    assert isinstance(credible.value, tuple)
    snapshot["assumptions"][4]["value"][0] = 0.99
    assert credible.value[0] == 0.08


# Model applicability and reverse modes


def test_applicability_rejects_financial_industry():
    verdict = evaluate_applicability(
        industry="banks",
        normalized_earnings=100.0,
    )
    assert not verdict.applicable
    assert verdict.failure_kind == "model_not_applicable"


def test_applicability_rejects_missing_earnings():
    verdict = evaluate_applicability(industry="industrial", normalized_earnings=None)
    assert not verdict.applicable
    assert verdict.failure_kind == "data_insufficient"


@pytest.mark.parametrize("bad", [math.nan, math.inf, True, "100"])
def test_applicability_rejects_non_finite_or_non_numeric_earnings(bad):
    verdict = evaluate_applicability(industry="industrial", normalized_earnings=bad)
    assert not verdict.applicable
    assert verdict.failure_kind == "data_insufficient"


def test_applicability_accepts_industrial_positive_earnings():
    verdict = evaluate_applicability(
        industry="industrial",
        normalized_earnings=100.0,
        units_aligned=True,
        periods_aligned=True,
    )
    assert verdict.applicable
    assert verdict.failure_kind is None


def test_reverse_scenarios_must_share_one_mode():
    payload = _base_diagnostic()
    payload["reverse_scenarios"] = [
        {"mode": "fixed_growth_rate", "growth_rate": 0.12, "implied_high_growth_duration": 6.0},
        {"mode": "fixed_duration", "duration_years": 5.0, "implied_growth_rate": 0.10},
    ]
    with pytest.raises(ContractError, match="share one reverse mode"):
        validate_diagnostic(payload)


def test_reverse_scenarios_must_match_assumption_reverse_mode():
    payload = _base_diagnostic()
    payload["reverse_scenarios"] = [
        {"mode": "fixed_duration", "duration_years": 5.0, "implied_growth_rate": 0.10}
    ]
    with pytest.raises(ContractError, match="match assumption reverse_mode"):
        validate_diagnostic(payload)


def test_fixed_duration_scenario_round_trips():
    payload = _base_diagnostic()
    payload["assumption_snapshot"] = _valid_assumptions(reverse_mode="fixed_duration")
    payload["reverse_scenarios"] = [
        {"mode": "fixed_duration", "duration_years": 5.0, "implied_growth_rate": 0.10}
    ]
    parsed = validate_diagnostic(payload)
    assert parsed.reverse_scenarios[0].mode == "fixed_duration"
    assert parsed.reverse_scenarios[0].implied_growth_rate == 0.10


# Digest binding, round-trip and mutation


def test_input_digest_binds_to_input_and_assumptions():
    payload = _bound_diagnostic()
    parsed = validate_diagnostic_binding(
        payload,
        ticker="600519.SH",
        input_payload=_valid_input(),
        assumption_snapshot=_valid_assumptions(),
        formula_version=FORMULA_VERSION,
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )
    assert parsed.calculation_status == "clean"


def test_input_digest_mismatch_is_rejected():
    payload = _base_diagnostic()
    with pytest.raises(ContractError, match="input_digest does not match"):
        validate_diagnostic_binding(
            payload,
            ticker="600519.SH",
            input_payload=_valid_input(),
            assumption_snapshot=_valid_assumptions(),
            formula_version=FORMULA_VERSION,
            dossier_snapshot="dossier-v1",
            profile_version="profile-v1",
        )


def test_clean_result_requires_fresh_sources():
    input_payload = _valid_input()
    input_payload["sources"][0]["freshness"] = "stale"
    assumptions = _valid_assumptions()
    payload = _base_diagnostic()
    payload["input_digest"] = compute_input_digest(
        ticker="600519.SH",
        input_payload=input_payload,
        assumption_snapshot=assumptions,
        formula_version=FORMULA_VERSION,
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )
    with pytest.raises(ContractError, match="fresh"):
        validate_diagnostic_binding(
            payload,
            ticker="600519.SH",
            input_payload=input_payload,
            assumption_snapshot=assumptions,
            formula_version=FORMULA_VERSION,
            dossier_snapshot="dossier-v1",
            profile_version="profile-v1",
        )


def test_clean_result_round_trips_through_to_dict():
    parsed = validate_diagnostic(_base_diagnostic())
    assert validate_diagnostic(parsed.to_dict()).to_dict() == parsed.to_dict()


def test_tampered_input_digest_is_detected_on_binding():
    payload = _bound_diagnostic()
    payload["input_digest"] = "b" * 64
    with pytest.raises(ContractError, match="input_digest does not match"):
        validate_diagnostic_binding(
            payload,
            ticker="600519.SH",
            input_payload=_valid_input(),
            assumption_snapshot=_valid_assumptions(),
            formula_version=FORMULA_VERSION,
            dossier_snapshot="dossier-v1",
            profile_version="profile-v1",
        )


def test_binding_rejects_ticker_mismatch():
    payload = _bound_diagnostic()
    with pytest.raises(ContractError, match="diagnostic ticker mismatch"):
        validate_diagnostic_binding(
            payload,
            ticker="000001.SZ",
            input_payload=_valid_input(),
            assumption_snapshot=_valid_assumptions(),
            formula_version=FORMULA_VERSION,
            dossier_snapshot="dossier-v1",
            profile_version="profile-v1",
        )


def test_binding_rejects_dossier_snapshot_mismatch():
    payload = _bound_diagnostic()
    with pytest.raises(ContractError, match="dossier_snapshot mismatch"):
        validate_diagnostic_binding(
            payload,
            ticker="600519.SH",
            input_payload=_valid_input(),
            assumption_snapshot=_valid_assumptions(),
            formula_version=FORMULA_VERSION,
            dossier_snapshot="other-dossier",
            profile_version="profile-v1",
        )


def test_input_contract_rejects_missing_schema_version():
    payload = _valid_input()
    payload.pop("schema_version")
    with pytest.raises(ContractError, match="schema_version"):
        validate_diagnostic_input(payload)


def test_input_contract_rejects_unknown_field():
    payload = _valid_input()
    payload["extra"] = "unexpected"
    with pytest.raises(ContractError, match="unknown fields"):
        validate_diagnostic_input(payload)


def test_input_contract_rejects_invalid_report_period():
    payload = _valid_input()
    payload["report_period"] = "2025-99"
    with pytest.raises(ContractError, match="report_period"):
        validate_diagnostic_input(payload)


def test_input_contract_rejects_source_without_published_at():
    payload = _valid_input()
    payload["sources"][0].pop("published_at")
    with pytest.raises(ContractError, match="published_at"):
        validate_diagnostic_input(payload)


def test_assumption_snapshot_requires_reverse_fixed_growth_rate():
    snapshot = _valid_assumptions()
    snapshot["assumptions"] = [
        item
        for item in snapshot["assumptions"]
        if item["key"] != "reverse_fixed_growth_rate"
    ]
    with pytest.raises(ContractError, match="requires reverse_fixed_growth_rate"):
        validate_assumption_snapshot(snapshot)


def test_assumption_snapshot_requires_reverse_fixed_duration():
    snapshot = _valid_assumptions(reverse_mode="fixed_duration")
    snapshot["assumptions"] = [
        item
        for item in snapshot["assumptions"]
        if item["key"] != "reverse_fixed_duration_years"
    ]
    with pytest.raises(ContractError, match="requires reverse_fixed_duration_years"):
        validate_assumption_snapshot(snapshot)


def test_output_clean_rejects_negative_market_value():
    payload = _base_diagnostic()
    payload["current_market_value"] = -1.0
    with pytest.raises(ContractError, match="non-negative"):
        validate_diagnostic(payload)


def test_output_clean_rejects_negative_implied_duration():
    payload = _base_diagnostic()
    payload["reverse_scenarios"][0]["implied_high_growth_duration"] = -1.0
    with pytest.raises(ContractError, match="non-negative"):
        validate_diagnostic(payload)


def test_output_exposes_prd_assumptions_map():
    parsed = validate_diagnostic(_base_diagnostic())
    expected = {
        item["key"]: (
            tuple(item["value"]) if isinstance(item["value"], list) else item["value"]
        )
        for item in _valid_assumptions()["assumptions"]
    }
    assert parsed.to_dict()["assumptions"] == expected


@pytest.mark.parametrize("drop", ["provenance", "input_digest"])
def test_not_evaluable_requires_provenance_and_digest(drop):
    payload = _strip_numbers(
        _base_diagnostic(),
        status="not_evaluable",
        failure_kind="model_not_applicable",
        reason_codes=["model_out_of_scope"],
        reasons=["financial industry"],
    )
    payload[drop] = None
    with pytest.raises(ContractError, match=drop):
        validate_diagnostic(payload)


# Golden cases


def test_golden_cases_cover_all_paths():
    clean = _base_diagnostic()

    degraded = _base_diagnostic()
    degraded["calculation_status"] = "degraded"
    degraded["warnings"] = ["maintenance capex proxy only"]

    not_evaluable = _strip_numbers(
        _base_diagnostic(),
        status="not_evaluable",
        failure_kind="model_not_applicable",
        reason_codes=["model_out_of_scope"],
        reasons=["financial industry"],
    )

    failed = _strip_numbers(
        _base_diagnostic(),
        status="failed",
        failure_kind="computation_failed",
        reason_codes=["solver_no_solution"],
        reasons=["no finite reverse solution"],
    )

    golden = [
        (clean, "clean", True),
        (degraded, "degraded", True),
        (not_evaluable, "not_evaluable", False),
        (failed, "failed", False),
    ]
    for payload, expected_status, expects_numbers in golden:
        parsed = validate_diagnostic(payload)
        assert parsed.calculation_status == expected_status
        assert (parsed.current_business_value is not None) is expects_numbers
