from __future__ import annotations

import pytest

from data.lib.growth_expectation_contract import (
    compute_diagnostic_digest,
    validate_diagnostic_binding,
    validate_assumption_snapshot,
    validate_diagnostic_input,
)
from data.lib.growth_expectation_engine import (
    _pv_growth,
    compute_growth_expectation_diagnostic,
    validate_growth_expectation_artifact,
)
from test_g2_growth_expectation_engine import (
    assumptions,
    input_payload,
)


def _compute(*, market_value=3000.0, mode="fixed_growth_rate", net_profit=90.0):
    payload = input_payload(market_value=market_value, industry="consumer")
    payload["normalized_net_profit"] = net_profit
    return compute_growth_expectation_diagnostic(
        validate_diagnostic_input(payload),
        validate_assumption_snapshot(assumptions(mode)),
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )


def test_fixed_growth_reverse_satisfies_market_value_residual():
    diagnostic = _compute(market_value=3000.0)
    earnings = 150.0
    discount = 0.10
    terminal_multiple = 20.0

    assert diagnostic.calculation_status in {"clean", "degraded"}
    assert len(diagnostic.reverse_scenarios) == 3
    for scenario in diagnostic.reverse_scenarios:
        value = _pv_growth(
            earnings,
            scenario.growth_rate,
            scenario.implied_high_growth_duration,
            discount,
            0.02,
            terminal_multiple,
            terminal_earnings=90.0,
        )
        assert value == pytest.approx(3000.0, rel=1e-8)


def test_fixed_duration_reverse_satisfies_market_value_residual():
    diagnostic = _compute(market_value=3000.0, mode="fixed_duration")
    assert diagnostic.calculation_status in {"clean", "degraded"}
    assert len(diagnostic.reverse_scenarios) == 3
    for scenario in diagnostic.reverse_scenarios:
        value = _pv_growth(
            150.0,
            scenario.implied_growth_rate,
            scenario.duration_years,
            0.10,
            0.02,
            20.0,
            terminal_earnings=90.0,
        )
        assert value == pytest.approx(3000.0, rel=1e-8)


def test_market_value_below_terminal_floor_fails_closed():
    diagnostic = _compute(market_value=100.0)

    assert diagnostic.calculation_status == "failed"
    assert diagnostic.reason_codes == ("solver_no_solution",)
    assert not diagnostic.reverse_scenarios


def test_fixed_duration_reverse_can_solve_growth_above_five_without_false_failure():
    from data.lib.growth_expectation_engine import _solve_growth

    growth = _solve_growth(
        1_000_000_000.0,
        150.0,
        5.0,
        0.10,
        0.02,
        20.0,
        terminal_earnings=90.0,
    )

    assert growth is not None
    assert growth > 5.0


def test_adaptive_growth_search_checks_configured_maximum():
    from data.lib.growth_expectation_engine import MAX_SOLVER_GROWTH, _pv_growth, _solve_growth

    target = _pv_growth(
        150.0,
        MAX_SOLVER_GROWTH,
        3.0,
        0.10,
        0.02,
        20.0,
        terminal_earnings=90.0,
    )
    growth = _solve_growth(
        target,
        150.0,
        3.0,
        0.10,
        0.02,
        20.0,
        terminal_earnings=90.0,
    )

    assert growth == pytest.approx(MAX_SOLVER_GROWTH, rel=1e-8)


def test_negative_net_profit_returns_contract_compatible_failure_artifact():
    payload = input_payload(industry="consumer")
    payload["normalized_net_profit"] = -90.0
    snapshot = validate_assumption_snapshot(assumptions())
    diagnostic = compute_growth_expectation_diagnostic(
        validate_diagnostic_input(payload),
        snapshot,
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )

    assert diagnostic.calculation_status == "not_evaluable"
    assert diagnostic.reason_codes == ("invalid_value",)
    assert diagnostic.input_snapshot is not None
    assert diagnostic.input_snapshot.normalized_net_profit == -90.0
    assert diagnostic.current_business_value is None
    assert validate_diagnostic_binding(
        diagnostic.to_dict(),
        ticker="600519.SH",
        input_payload=payload,
        assumption_snapshot=snapshot.to_dict(),
        formula_version="v0-epv-proxy",
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    ).input_snapshot is not None


def test_midpoint_overdraft_is_distinguished_from_upper_bound():
    diagnostic = _compute(market_value=3_000.0, mode="fixed_duration")

    assert diagnostic.expectation_overdraft == "above_base_case"


def test_sensitivity_has_single_variable_outputs_including_credible_growth():
    diagnostic = _compute()
    keys = {item.assumption_key for item in diagnostic.sensitivity}

    assert {
        "maintenance_capex_ratio",
        "cost_of_equity",
        "credible_growth_rate",
        "mature_pe",
    } <= keys
    impacts = {
        (item.assumption_key, item.metric): item.impact_range
        for item in diagnostic.sensitivity
    }
    assert impacts[("maintenance_capex_ratio", "current_business_value")] != impacts[("cost_of_equity", "current_business_value")]
    assert impacts[("credible_growth_rate", "expectation_gap")] != impacts[("mature_pe", "current_business_value")]
    assert ("maintenance_capex_ratio", "reverse_base") in impacts
    assert ("cost_of_equity", "value_pulled_forward_years") in impacts
    credible_business = impacts[("credible_growth_rate", "current_business_value")]
    assert credible_business[0] == pytest.approx(credible_business[1])
    credible_gap = impacts[("credible_growth_rate", "expectation_gap")]
    assert credible_gap[0] < 0 < credible_gap[1]


def test_legacy_sensitivity_artifact_round_trips_without_metric_field():
    diagnostic = _compute(market_value=3000.0)
    payload = diagnostic.to_dict()
    for scenario in payload["sensitivity"]:
        scenario.pop("metric", None)
    payload["diagnostic_digest"] = compute_diagnostic_digest(payload)

    bound = validate_diagnostic_binding(
        payload,
        ticker="600519.SH",
        input_payload=input_payload(market_value=3000.0, industry="consumer"),
        assumption_snapshot=assumptions(),
        formula_version="v0-epv-proxy",
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )

    assert bound.to_dict() == payload


def test_incomplete_sensitivity_is_visible_as_warning():
    diagnostic = _compute(market_value=1800.0)

    assert diagnostic.calculation_status == "degraded"
    assert any(
        warning.startswith("sensitivity_incomplete:")
        for warning in diagnostic.warnings
    )


def test_extreme_finite_growth_returns_failed_artifact_not_overflow():
    payload = input_payload(market_value=1800.0, industry="consumer")
    snapshot_payload = assumptions()
    for item in snapshot_payload["assumptions"]:
        if item["key"] == "reverse_fixed_growth_rate":
            item["value"] = [1e100, 1e154, 1e308]
    diagnostic = compute_growth_expectation_diagnostic(
        validate_diagnostic_input(payload),
        validate_assumption_snapshot(snapshot_payload),
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )

    assert diagnostic.calculation_status == "failed"
    assert diagnostic.reason_codes == ("solver_non_finite",)


def test_engine_semantic_binding_rejects_rehashed_derived_mutation():
    diagnostic = _compute()
    payload = diagnostic.to_dict()
    payload["priced_growth_value_range"] = [0.0, 0.0]
    payload["diagnostic_digest"] = compute_diagnostic_digest(payload)

    with pytest.raises(ValueError, match="priced_growth_value_range"):
        validate_growth_expectation_artifact(
            payload,
            ticker="600519.SH",
            input_payload=input_payload(market_value=3000.0, industry="consumer"),
            assumption_snapshot=assumptions(),
            formula_version="v0-epv-proxy",
            dossier_snapshot="dossier-v1",
            profile_version="profile-v1",
        )
