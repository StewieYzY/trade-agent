from __future__ import annotations

import pytest

from data.lib.growth_expectation_contract import (
    validate_diagnostic_binding,
    validate_assumption_snapshot,
    validate_diagnostic_input,
)
from data.lib.growth_expectation_engine import (
    _pv_growth,
    compute_growth_expectation_diagnostic,
)
from test_g2_growth_expectation_engine import (
    assumptions,
    input_payload,
)


def _compute(*, market_value=1200.0, mode="fixed_growth_rate", net_profit=90.0):
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

    for scenario in diagnostic.reverse_scenarios:
        value = _pv_growth(
            earnings,
            scenario.growth_rate,
            scenario.implied_high_growth_duration,
            discount,
            0.02,
            terminal_multiple,
        )
        assert value == pytest.approx(3000.0, rel=1e-8)


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
        item.assumption_key: item.impact_range
        for item in diagnostic.sensitivity
    }
    assert impacts["maintenance_capex_ratio"] != impacts["cost_of_equity"]
    assert impacts["credible_growth_rate"] != impacts["mature_pe"]
