"""Deterministic G2 growth-expectation capitalization V0 engine."""

from __future__ import annotations

import math
from dataclasses import replace
from data.lib.growth_expectation_contract import (
    ASSUMPTION_SNAPSHOT_VERSION,
    DiagnosticEvidence,
    DiagnosticInput,
    DiagnosticProvenance,
    GrowthExpectationDiagnostic,
    ReverseScenario,
    SensitivityScenario,
    AssumptionSnapshot,
    CurrentBusinessValue,
    compute_diagnostic_digest,
    compute_input_digest,
    evaluate_applicability,
)

FORMULA_VERSION = "v0-epv-proxy"
MAX_SOLVER_YEARS = 50
_SCENARIOS = ("conservative", "base", "optimistic")


def _values(snapshot: AssumptionSnapshot) -> dict[str, object]:
    return {item.key: item.value for item in snapshot.assumptions}


def _range_product(earnings: float, multiples: tuple[float, float]) -> tuple[float, float]:
    return (earnings * multiples[0], earnings * multiples[1])


def _epv_range(input: DiagnosticInput, assumptions: dict[str, object]) -> tuple[float, float]:
    basis = input.normalized_operating_cashflow if assumptions["normalized_earnings_basis"] == "normalized_operating_cashflow" else input.normalized_net_profit
    capex_low, capex_high = assumptions["maintenance_capex_ratio"]
    rate_low, rate_high = assumptions["cost_of_equity"]
    maintenance_growth = float(assumptions["maintenance_growth"])
    candidates = []
    for ratio in (capex_low, capex_high):
        owner_earnings = basis - input.total_capex * ratio
        for rate in (rate_low, rate_high):
            spread = rate - maintenance_growth
            if spread <= 0 or not math.isfinite(spread):
                raise ValueError("no finite EPV solution")
            candidates.append(owner_earnings / spread)
    if min(candidates) < 0 or not all(math.isfinite(value) for value in candidates):
        raise ValueError("no finite EPV solution")
    return (min(candidates), max(candidates))


def _pv_growth(value: float, growth: float, years: float, discount: float, terminal_growth: float, terminal_multiple: float) -> float:
    if discount <= terminal_growth or value <= 0 or growth < 0 or years < 0:
        return math.nan
    yearly = 0.0
    for year in range(1, int(math.ceil(years)) + 1):
        if year > years:
            break
        yearly += value * (1 + growth) ** year / (1 + discount) ** year
    terminal_profit = value * (1 + growth) ** years
    terminal = terminal_profit * terminal_multiple / (1 + discount) ** years
    return yearly + terminal


def _solve_duration(target: float, value: float, growth: float, discount: float, terminal_growth: float, terminal_multiple: float) -> float | None:
    if target <= value:
        return 0.0
    lo, hi = 0.0, float(MAX_SOLVER_YEARS)
    if _pv_growth(value, growth, hi, discount, terminal_growth, terminal_multiple) < target:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if _pv_growth(value, growth, mid, discount, terminal_growth, terminal_multiple) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def _solve_growth(target: float, value: float, years: float, discount: float, terminal_growth: float, terminal_multiple: float) -> float | None:
    if target <= _pv_growth(value, 0.0, years, discount, terminal_growth, terminal_multiple):
        return 0.0
    lo, hi = 0.0, 5.0
    if _pv_growth(value, hi, years, discount, terminal_growth, terminal_multiple) < target:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if _pv_growth(value, mid, years, discount, terminal_growth, terminal_multiple) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def _reverse_scenarios(input: DiagnosticInput, assumptions: dict[str, object], business_value: tuple[float, float]) -> tuple[ReverseScenario, ...]:
    target = input.current_market_value
    base_value = sum(business_value) / 2
    discount = sum(assumptions["cost_of_equity"]) / 2
    terminal_growth = float(assumptions["maintenance_growth"])
    terminal_multiple = sum(assumptions["mature_pe"]) / 2
    mode = assumptions["reverse_mode"]
    result = []
    if mode == "fixed_growth_rate":
        for name, growth in zip(_SCENARIOS, assumptions["reverse_fixed_growth_rate"]):
            duration = _solve_duration(target, base_value, float(growth), discount, terminal_growth, terminal_multiple)
            if duration is None:
                raise LookupError("no finite reverse solution")
            result.append(ReverseScenario(
                scenario=name, mode=mode, growth_rate=float(growth),
                implied_high_growth_duration=duration,
            ))
    else:
        for name, years in zip(_SCENARIOS, assumptions["reverse_fixed_duration_years"]):
            growth = _solve_growth(target, base_value, float(years), discount, terminal_growth, terminal_multiple)
            if growth is None:
                raise LookupError("no finite reverse solution")
            result.append(ReverseScenario(
                scenario=name, mode=mode, duration_years=float(years),
                implied_growth_rate=growth,
            ))
    return tuple(result)


def _sensitivity(input: DiagnosticInput, assumptions: dict[str, object]) -> tuple[SensitivityScenario, ...]:
    epv = []
    for ratio in assumptions["maintenance_capex_ratio"]:
        for rate in assumptions["cost_of_equity"]:
            local = dict(assumptions)
            local["maintenance_capex_ratio"] = (ratio, ratio)
            local["cost_of_equity"] = (rate, rate)
            epv.append(_epv_range(input, local)[0])
    output = [
        SensitivityScenario("maintenance_capex_ratio", float(assumptions["maintenance_capex_ratio"][1]), (min(epv), max(epv))),
        SensitivityScenario("cost_of_equity", float(assumptions["cost_of_equity"][1]), (min(epv), max(epv))),
        SensitivityScenario("mature_pe", float(assumptions["mature_pe"][1]), _range_product(input.normalized_net_profit, assumptions["mature_pe"])),
    ]
    return tuple(output)


def _failure(input: DiagnosticInput, snapshot: AssumptionSnapshot, *, dossier_snapshot: str, profile_version: str, failure_kind: str, reason_code: str, reason: str) -> GrowthExpectationDiagnostic:
    provenance = DiagnosticProvenance(dossier_snapshot, profile_version, FORMULA_VERSION, ASSUMPTION_SNAPSHOT_VERSION)
    input_digest = compute_input_digest(
        ticker=input.ticker, input_payload=input.to_dict(), assumption_snapshot=snapshot.to_dict(),
        formula_version=FORMULA_VERSION, dossier_snapshot=dossier_snapshot, profile_version=profile_version,
    )
    status = "failed" if failure_kind == "computation_failed" else "not_evaluable"
    payload = GrowthExpectationDiagnostic(
        schema_version="g2-growth-expectation-contract-v1", ticker=input.ticker,
        valuation_date=input.valuation_date, report_period=input.report_period, as_of=input.as_of,
        currency=input.currency, value_scale=input.value_scale, calculation_status=status,
        quality_status="failed" if status == "failed" else "warning", decision_grade="diagnostic",
        failure_kind=failure_kind, reason_codes=(reason_code,), reasons=(reason,), warnings=(),
        current_market_value=None, input_snapshot=None, assumption_snapshot=snapshot,
        current_business_value=None, priced_growth_value_range=None, priced_growth_share_range=None,
        reverse_scenarios=(), credible_growth_range=None, expectation_gap=None,
        value_pulled_forward_years=None, expectation_overdraft="not_evaluable",
        sensitivity=(), evidence=(), counter_evidence=(), unknowns=(), what_would_change_my_mind=(),
        provenance=provenance, input_digest=input_digest, diagnostic_digest="0" * 64,
    )
    return replace(payload, diagnostic_digest=compute_diagnostic_digest(payload.to_dict()))


def compute_growth_expectation_diagnostic(
    input: DiagnosticInput,
    assumption_snapshot: AssumptionSnapshot,
    *,
    dossier_snapshot: str,
    profile_version: str,
) -> GrowthExpectationDiagnostic:
    """Compute and bind one immutable V0 diagnostic artifact."""
    if not isinstance(input, DiagnosticInput) or not isinstance(assumption_snapshot, AssumptionSnapshot):
        raise TypeError("validated DiagnosticInput and AssumptionSnapshot are required")
    verdict = evaluate_applicability(input, assumption_snapshot=assumption_snapshot)
    if not verdict.applicable:
        return _failure(
            input, assumption_snapshot, dossier_snapshot=dossier_snapshot, profile_version=profile_version,
            failure_kind=verdict.failure_kind or "data_insufficient",
            reason_code=verdict.reason_codes[0], reason=verdict.reasons[0],
        )
    assumptions = _values(assumption_snapshot)
    try:
        epv_range = _epv_range(input, assumptions)
        mature_range = _range_product(input.normalized_net_profit, assumptions["mature_pe"])
        business = (min(epv_range[0], mature_range[0]), max(epv_range[1], mature_range[1]))
        reverse = _reverse_scenarios(input, assumptions, business)
    except LookupError as exc:
        return _failure(input, assumption_snapshot, dossier_snapshot=dossier_snapshot, profile_version=profile_version,
                        failure_kind="computation_failed", reason_code="solver_no_solution", reason=str(exc))
    except ValueError as exc:
        return _failure(input, assumption_snapshot, dossier_snapshot=dossier_snapshot, profile_version=profile_version,
                        failure_kind="computation_failed", reason_code="solver_non_finite", reason=str(exc))
    priced = (input.current_market_value - business[1], input.current_market_value - business[0])
    share = (priced[0] / input.current_market_value, priced[1] / input.current_market_value)
    credible = (float(assumptions["credible_growth_rate"][0]), float(assumptions["credible_growth_rate"][2]))
    base_reverse = reverse[1]
    implied = base_reverse.implied_growth_rate if base_reverse.implied_growth_rate is not None else base_reverse.growth_rate
    gap = (float(implied) - credible[1], float(implied) - credible[0])
    overdraft = "within_credible_range" if implied <= credible[1] else "above_credible_upper_bound"
    pulled_forward = _solve_duration(
        input.current_market_value,
        sum(business) / 2,
        float(assumptions["credible_growth_rate"][1]),
        sum(assumptions["cost_of_equity"]) / 2,
        float(assumptions["maintenance_growth"]),
        sum(assumptions["mature_pe"]) / 2,
    )
    if pulled_forward is None:
        return _failure(
            input, assumption_snapshot, dossier_snapshot=dossier_snapshot,
            profile_version=profile_version, failure_kind="computation_failed",
            reason_code="solver_no_solution", reason="no finite value-pulled-forward duration",
        )
    warnings = list(verdict.warnings)
    if any(source.freshness != "fresh" for source in input.sources):
        warnings.append("source_freshness_degraded")
    if any(source.degradation_status != "clean" for source in input.sources):
        warnings.append("source_degradation_visible")
    if abs(epv_range[1] - mature_range[0]) > max(epv_range[1], mature_range[1]) * 0.5:
        warnings.append("anchor_divergence")
    status = "degraded" if warnings or any(s.degradation_status != "clean" for s in input.sources) else "clean"
    provenance = DiagnosticProvenance(dossier_snapshot, profile_version, FORMULA_VERSION, ASSUMPTION_SNAPSHOT_VERSION)
    input_digest = compute_input_digest(
        ticker=input.ticker, input_payload=input.to_dict(), assumption_snapshot=assumption_snapshot.to_dict(),
        formula_version=FORMULA_VERSION, dossier_snapshot=dossier_snapshot, profile_version=profile_version,
    )
    artifact = GrowthExpectationDiagnostic(
        schema_version="g2-growth-expectation-contract-v1", ticker=input.ticker,
        valuation_date=input.valuation_date, report_period=input.report_period, as_of=input.as_of,
        currency=input.currency, value_scale=input.value_scale, calculation_status=status,
        quality_status="warning", decision_grade="diagnostic", failure_kind=None,
        reason_codes=(), reasons=(), warnings=tuple(warnings), current_market_value=input.current_market_value,
        input_snapshot=input, assumption_snapshot=assumption_snapshot,
        current_business_value=CurrentBusinessValue(
            epv_range, mature_range, "wide" if "anchor_divergence" in warnings else None),
        priced_growth_value_range=priced, priced_growth_share_range=share, reverse_scenarios=reverse,
        credible_growth_range=credible, expectation_gap=gap, value_pulled_forward_years=pulled_forward,
        expectation_overdraft=overdraft, sensitivity=_sensitivity(input, assumptions),
        evidence=(), counter_evidence=(), unknowns=(), what_would_change_my_mind=(),
        provenance=provenance, input_digest=input_digest, diagnostic_digest="0" * 64,
    )
    return replace(artifact, diagnostic_digest=compute_diagnostic_digest(artifact.to_dict()))
