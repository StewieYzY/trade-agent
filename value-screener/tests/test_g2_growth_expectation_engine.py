from __future__ import annotations

from dataclasses import replace

import pytest

from data.lib.growth_expectation_contract import (
    ASSUMPTION_SNAPSHOT_VERSION,
    ContractError,
    validate_assumption_snapshot,
    validate_diagnostic_input,
    validate_diagnostic_binding,
)
from data.lib.growth_expectation_engine import (
    FORMULA_VERSION,
    compute_growth_expectation_diagnostic,
)


RAW_HASH = "d" * 64


def source(field: str, *, degradation_status: str = "clean", freshness: str = "fresh"):
    return {
        "ticker": "600519.SH",
        "source_id": f"src-{field}",
        "provider": "fixture",
        "field": field,
        "raw_field": field,
        "raw_payload_hash": RAW_HASH,
        "report_period": "2025-12-31",
        "as_of": "2026-08-24",
        "freshness": freshness,
        "currency": "CNY",
        "value_scale": "hundred_million",
        "published_at": "2026-03-31",
        "degradation_status": degradation_status,
    }


def input_payload(*, market_value: float = 1200.0, industry=None):
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
            source("current_market_value"),
            source("normalized_operating_cashflow"),
            source("normalized_earnings"),
            source("total_capex"),
            source("normalized_net_profit"),
        ],
        "industry": industry,
    }


def assumptions(mode: str = "fixed_growth_rate"):
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
            "reverse_fixed_growth_rate" if mode == "fixed_growth_rate" else "reverse_fixed_duration_years",
            [0.10, 0.12, 0.15] if mode == "fixed_growth_rate" else [3.0, 5.0, 8.0],
            "decimal" if mode == "fixed_growth_rate" else "years",
        )
    )
    return {
        "version": ASSUMPTION_SNAPSHOT_VERSION,
        "created_at": "2026-08-24",
        "assumptions": [
            {
                "key": key,
                "value": value,
                "unit": unit,
                "source": "user",
                "confirmed_by_user": True,
                "version": "v1",
            }
            for key, value, unit in values
        ],
    }


def compute(mode="fixed_growth_rate", *, market_value=1200.0, industry=None):
    return compute_growth_expectation_diagnostic(
        validate_diagnostic_input(input_payload(market_value=market_value, industry=industry)),
        validate_assumption_snapshot(assumptions(mode)),
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )


def test_fixed_growth_engine_returns_anchors_reverse_and_signed_values():
    diagnostic = compute(market_value=100.0)

    assert diagnostic.calculation_status in {"clean", "degraded"}
    assert diagnostic.current_business_value.epv_proxy_range == pytest.approx((1266.6666667, 1800.0))
    assert diagnostic.current_business_value.mature_multiple_range == pytest.approx((1620.0, 1980.0))
    assert diagnostic.priced_growth_value_range[0] < 0
    assert len(diagnostic.reverse_scenarios) == 3
    assert {item.mode for item in diagnostic.reverse_scenarios} == {"fixed_growth_rate"}
    assert all(item.implied_high_growth_duration is not None for item in diagnostic.reverse_scenarios)


def test_fixed_duration_engine_solves_only_growth_rate():
    diagnostic = compute("fixed_duration")

    assert diagnostic.calculation_status in {"clean", "degraded"}
    assert len(diagnostic.reverse_scenarios) == 3
    assert {item.mode for item in diagnostic.reverse_scenarios} == {"fixed_duration"}
    assert all(item.implied_growth_rate is not None for item in diagnostic.reverse_scenarios)


def test_sensitivity_is_bounded_and_higher_discount_rate_reduces_epv():
    diagnostic = compute()
    values = {
        item.assumption_key: item
        for item in diagnostic.sensitivity
    }

    assert values["cost_of_equity"].impact_range[0] <= values["cost_of_equity"].impact_range[1]
    assert values["maintenance_capex_ratio"].impact_range[0] <= values["maintenance_capex_ratio"].impact_range[1]
    assert values["cost_of_equity"].value == pytest.approx(0.11)


def test_missing_industry_is_visible_as_degraded_warning():
    diagnostic = compute(industry=None)

    assert diagnostic.calculation_status == "degraded"
    assert "industry_unknown" in diagnostic.warnings


def test_stale_source_is_visible_as_degraded_warning():
    payload = input_payload()
    payload["sources"][0] = source("current_market_value", freshness="stale")
    diagnostic = compute_growth_expectation_diagnostic(
        validate_diagnostic_input(payload),
        validate_assumption_snapshot(assumptions()),
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )

    assert diagnostic.calculation_status == "degraded"
    assert "source_freshness_degraded" in diagnostic.warnings


def test_artifact_is_reproducible_and_binding_detects_mutation():
    diagnostic = compute()
    payload = diagnostic.to_dict()
    bound = validate_diagnostic_binding(
        payload,
        ticker="600519.SH",
        input_payload=input_payload(),
        assumption_snapshot=assumptions(),
        formula_version=FORMULA_VERSION,
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )

    assert bound.to_dict() == payload
    assert compute().to_dict() == payload

    mutated = dict(payload)
    mutated["current_market_value"] = 999.0
    with pytest.raises(ContractError):
        validate_diagnostic_binding(
            mutated,
            ticker="600519.SH",
            input_payload=input_payload(),
            assumption_snapshot=assumptions(),
            formula_version=FORMULA_VERSION,
            dossier_snapshot="dossier-v1",
            profile_version="profile-v1",
        )


def test_unconfirmed_or_invalid_contract_input_fails_before_calculation():
    bad_assumptions = assumptions()
    bad_assumptions["assumptions"][1]["confirmed_by_user"] = False
    with pytest.raises(ContractError):
        compute_growth_expectation_diagnostic(
            validate_diagnostic_input(input_payload()),
            validate_assumption_snapshot(bad_assumptions),
            dossier_snapshot="dossier-v1",
            profile_version="profile-v1",
        )


def test_financial_industry_returns_not_evaluable_without_numeric_conclusions():
    diagnostic = compute(industry="banking")

    assert diagnostic.calculation_status == "not_evaluable"
    assert diagnostic.failure_kind == "model_not_applicable"
    assert diagnostic.current_business_value is None
    assert diagnostic.reason_codes == ("model_not_applicable",)


def test_unbounded_market_value_returns_failed_without_numeric_conclusions():
    diagnostic = compute(market_value=1_000_000.0)

    assert diagnostic.calculation_status == "failed"
    assert diagnostic.failure_kind == "computation_failed"
    assert diagnostic.reason_codes == ("solver_no_solution",)
    assert diagnostic.priced_growth_value_range is None
