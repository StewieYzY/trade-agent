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
    validate_diagnostic_binding,
    compute_diagnostic_digest,
    compute_input_digest,
    evaluate_applicability,
)

FORMULA_VERSION = "v0-epv-proxy"
MAX_SOLVER_YEARS = 50
MAX_SOLVER_GROWTH = 1_000_000.0
SOLVER_RESIDUAL_TOLERANCE = 1e-8
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


def _pv_growth(
    earnings_basis: float,
    growth: float,
    years: float,
    discount: float,
    terminal_growth: float,
    terminal_multiple: float,
    *,
    terminal_earnings: float | None = None,
) -> float:
    if (
        discount <= terminal_growth
        or earnings_basis <= 0
        or growth < 0
        or years < 0
        or (terminal_earnings is not None and terminal_earnings <= 0)
    ):
        return math.nan
    terminal_earnings = (
        earnings_basis if terminal_earnings is None else terminal_earnings
    )
    full_years = int(math.floor(years))
    yearly = sum(
        earnings_basis * (1 + growth) ** year / (1 + discount) ** year
        for year in range(1, full_years + 1)
    )
    fraction = years - full_years
    if fraction:
        next_year = full_years + 1
        yearly += fraction * (
            earnings_basis
            * (1 + growth) ** next_year
            / (1 + discount) ** next_year
        )
    terminal_profit = terminal_earnings * (1 + growth) ** years
    terminal = terminal_profit * terminal_multiple / (1 + discount) ** years
    return yearly + terminal


def _solve_duration(
    target: float,
    earnings_basis: float,
    growth: float,
    discount: float,
    terminal_growth: float,
    terminal_multiple: float,
    *,
    terminal_earnings: float,
) -> float | None:
    floor = _pv_growth(
        earnings_basis,
        0.0,
        0.0,
        discount,
        terminal_growth,
        terminal_multiple,
        terminal_earnings=terminal_earnings,
    )
    if not math.isfinite(floor):
        return None
    if target < floor:
        return None
    if abs(target - floor) <= SOLVER_RESIDUAL_TOLERANCE * max(1.0, target):
        return 0.0
    lo, hi = 0.0, float(MAX_SOLVER_YEARS)
    upper = _pv_growth(
        earnings_basis,
        growth,
        hi,
        discount,
        terminal_growth,
        terminal_multiple,
        terminal_earnings=terminal_earnings,
    )
    if not math.isfinite(upper) or upper < target:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        value = _pv_growth(
            earnings_basis,
            growth,
            mid,
            discount,
            terminal_growth,
            terminal_multiple,
            terminal_earnings=terminal_earnings,
        )
        if not math.isfinite(value):
            return None
        if value >= target:
            hi = mid
        else:
            lo = mid
    result = _pv_growth(
        earnings_basis,
        growth,
        hi,
        discount,
        terminal_growth,
        terminal_multiple,
        terminal_earnings=terminal_earnings,
    )
    if abs(result - target) > SOLVER_RESIDUAL_TOLERANCE * max(1.0, target):
        return None
    return hi


def _solve_growth(
    target: float,
    earnings_basis: float,
    years: float,
    discount: float,
    terminal_growth: float,
    terminal_multiple: float,
    *,
    terminal_earnings: float,
) -> float | None:
    floor = _pv_growth(
        earnings_basis,
        0.0,
        years,
        discount,
        terminal_growth,
        terminal_multiple,
        terminal_earnings=terminal_earnings,
    )
    if not math.isfinite(floor):
        return None
    if target < floor:
        return None
    if abs(target - floor) <= SOLVER_RESIDUAL_TOLERANCE * max(1.0, target):
        return 0.0
    lo, hi = 0.0, 1.0
    while True:
        upper = _pv_growth(
            earnings_basis,
            hi,
            years,
            discount,
            terminal_growth,
            terminal_multiple,
            terminal_earnings=terminal_earnings,
        )
        if math.isfinite(upper) and upper >= target:
            break
        if hi >= MAX_SOLVER_GROWTH:
            return None
        hi = min(hi * 2, MAX_SOLVER_GROWTH)
    for _ in range(80):
        mid = (lo + hi) / 2
        value = _pv_growth(
            earnings_basis,
            mid,
            years,
            discount,
            terminal_growth,
            terminal_multiple,
            terminal_earnings=terminal_earnings,
        )
        if not math.isfinite(value):
            return None
        if value >= target:
            hi = mid
        else:
            lo = mid
    result = _pv_growth(
        earnings_basis,
        hi,
        years,
        discount,
        terminal_growth,
        terminal_multiple,
        terminal_earnings=terminal_earnings,
    )
    if abs(result - target) > SOLVER_RESIDUAL_TOLERANCE * max(1.0, target):
        return None
    return hi


def _reverse_scenarios(
    input: DiagnosticInput, assumptions: dict[str, object]
) -> tuple[ReverseScenario, ...]:
    target = input.current_market_value
    earnings_basis = (
        input.normalized_operating_cashflow
        if assumptions["normalized_earnings_basis"]
        == "normalized_operating_cashflow"
        else input.normalized_net_profit
    )
    discount = sum(assumptions["cost_of_equity"]) / 2
    terminal_growth = float(assumptions["maintenance_growth"])
    terminal_multiple = sum(assumptions["mature_pe"]) / 2
    terminal_earnings = input.normalized_net_profit
    mode = assumptions["reverse_mode"]
    result = []
    if mode == "fixed_growth_rate":
        for name, growth in zip(_SCENARIOS, assumptions["reverse_fixed_growth_rate"]):
            duration = _solve_duration(
                target,
                earnings_basis,
                float(growth),
                discount,
                terminal_growth,
                terminal_multiple,
                terminal_earnings=terminal_earnings,
            )
            if duration is None:
                raise LookupError("no finite reverse solution")
            result.append(
                ReverseScenario(
                    scenario=name,
                    mode=mode,
                    growth_rate=float(growth),
                    implied_high_growth_duration=duration,
                )
            )
    else:
        for name, years in zip(_SCENARIOS, assumptions["reverse_fixed_duration_years"]):
            growth = _solve_growth(
                target,
                earnings_basis,
                float(years),
                discount,
                terminal_growth,
                terminal_multiple,
                terminal_earnings=terminal_earnings,
            )
            if growth is None:
                raise LookupError("no finite reverse solution")
            result.append(
                ReverseScenario(
                    scenario=name,
                    mode=mode,
                    duration_years=float(years),
                    implied_growth_rate=growth,
                )
            )
    return tuple(result)


def _diagnostic_metrics(
    input: DiagnosticInput, assumptions: dict[str, object]
) -> dict[str, object]:
    epv_range = _epv_range(input, assumptions)
    mature_range = _range_product(input.normalized_net_profit, assumptions["mature_pe"])
    business = (min(epv_range[0], mature_range[0]), max(epv_range[1], mature_range[1]))
    reverse = _reverse_scenarios(input, assumptions)
    credible = (
        float(assumptions["credible_growth_rate"][0]),
        float(assumptions["credible_growth_rate"][2]),
    )
    base_reverse = reverse[1]
    implied = (
        base_reverse.implied_growth_rate
        if base_reverse.implied_growth_rate is not None
        else base_reverse.growth_rate
    )
    credible_mid = float(assumptions["credible_growth_rate"][1])
    if implied <= credible_mid:
        overdraft = "within_credible_range"
    elif implied <= credible[1]:
        overdraft = "above_base_case"
    else:
        overdraft = "above_credible_upper_bound"
    earnings_basis = (
        input.normalized_operating_cashflow
        if assumptions["normalized_earnings_basis"]
        == "normalized_operating_cashflow"
        else input.normalized_net_profit
    )
    pulled_forward = _solve_duration(
        input.current_market_value,
        earnings_basis,
        credible_mid,
        sum(assumptions["cost_of_equity"]) / 2,
        float(assumptions["maintenance_growth"]),
        sum(assumptions["mature_pe"]) / 2,
        terminal_earnings=input.normalized_net_profit,
    )
    if pulled_forward is None:
        raise LookupError("no finite value-pulled-forward duration")
    return {
        "epv_range": epv_range,
        "mature_range": mature_range,
        "business": business,
        "reverse": reverse,
        "credible": credible,
        "implied": float(implied),
        "expectation_gap": (
            float(implied) - credible[1],
            float(implied) - credible[0],
        ),
        "overdraft": overdraft,
        "pulled_forward": pulled_forward,
    }


def _sensitivity(
    input: DiagnosticInput, assumptions: dict[str, object]
) -> tuple[tuple[SensitivityScenario, ...], tuple[str, ...]]:
    base_rate = sum(assumptions["cost_of_equity"]) / 2
    base_ratio = sum(assumptions["maintenance_capex_ratio"]) / 2
    base_credible = sum(assumptions["credible_growth_rate"]) / 3
    base_pe = sum(assumptions["mature_pe"]) / 2
    base_assumptions = dict(assumptions)
    base_assumptions["maintenance_capex_ratio"] = (base_ratio, base_ratio)
    base_assumptions["cost_of_equity"] = (base_rate, base_rate)
    base_assumptions["credible_growth_rate"] = (
        base_credible,
        base_credible,
        base_credible,
    )
    base_assumptions["mature_pe"] = (base_pe, base_pe)
    points = {
        "maintenance_capex_ratio": assumptions["maintenance_capex_ratio"],
        "cost_of_equity": assumptions["cost_of_equity"],
        "credible_growth_rate": assumptions["credible_growth_rate"],
        "mature_pe": assumptions["mature_pe"],
    }
    metric_values: dict[tuple[str, str], list[float]] = {}
    warnings: list[str] = []
    for assumption_key, bounds in points.items():
        for point in bounds:
            local = dict(base_assumptions)
            if assumption_key == "credible_growth_rate":
                local[assumption_key] = (float(point), float(point), float(point))
            else:
                local[assumption_key] = (float(point), float(point))
            try:
                metrics = _diagnostic_metrics(input, local)
            except (LookupError, ValueError):
                warnings.append(
                    f"sensitivity_incomplete:{assumption_key}={point}"
                )
                continue
            scalar_values = {
                "current_business_value": sum(metrics["business"]) / 2,
                "reverse_base": metrics["implied"],
                "expectation_gap": sum(metrics["expectation_gap"]) / 2,
                "value_pulled_forward_years": metrics["pulled_forward"],
                "expectation_overdraft": float(
                    {
                        "within_credible_range": 0,
                        "above_base_case": 1,
                        "above_credible_upper_bound": 2,
                    }[metrics["overdraft"]]
                ),
            }
            for metric, scalar in scalar_values.items():
                metric_values.setdefault((assumption_key, metric), []).append(scalar)
    output = []
    for (assumption_key, metric), values in metric_values.items():
        bound = assumptions[assumption_key]
        value = float(bound[1])
        output.append(
            SensitivityScenario(
                assumption_key,
                value,
                (min(values), max(values)),
                metric=metric,
            )
        )
    if not output:
        raise LookupError("no evaluable sensitivity perturbation")
    return tuple(output), tuple(sorted(set(warnings)))


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
        current_market_value=None, input_snapshot=input, assumption_snapshot=snapshot,
        current_business_value=None, priced_growth_value_range=None, priced_growth_share_range=None,
        reverse_scenarios=(), credible_growth_range=None, expectation_gap=None,
        value_pulled_forward_years=None, expectation_overdraft="not_evaluable",
        sensitivity=(), evidence=(), counter_evidence=(), unknowns=(), what_would_change_my_mind=(),
        provenance=provenance, input_digest=input_digest, diagnostic_digest="0" * 64,
    )
    finalized = replace(
        payload, diagnostic_digest=compute_diagnostic_digest(payload.to_dict())
    )
    return validate_diagnostic_binding(
        finalized.to_dict(),
        ticker=input.ticker,
        input_payload=input.to_dict(),
        assumption_snapshot=snapshot.to_dict(),
        formula_version=FORMULA_VERSION,
        dossier_snapshot=dossier_snapshot,
        profile_version=profile_version,
    )


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
        if input.normalized_net_profit <= 0:
            return _failure(
                input,
                assumption_snapshot,
                dossier_snapshot=dossier_snapshot,
                profile_version=profile_version,
                failure_kind="data_insufficient",
                reason_code="invalid_value",
                reason="positive normalized net profit is required for mature PE anchor",
            )
        epv_range = _epv_range(input, assumptions)
        mature_range = _range_product(input.normalized_net_profit, assumptions["mature_pe"])
        business = (min(epv_range[0], mature_range[0]), max(epv_range[1], mature_range[1]))
        reverse = _reverse_scenarios(input, assumptions)
        sensitivity, sensitivity_warnings = _sensitivity(input, assumptions)
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
    credible_mid = float(assumptions["credible_growth_rate"][1])
    if implied <= credible_mid:
        overdraft = "within_credible_range"
    elif implied <= credible[1]:
        overdraft = "above_base_case"
    else:
        overdraft = "above_credible_upper_bound"
    pulled_forward = _solve_duration(
        input.current_market_value,
        (
            input.normalized_operating_cashflow
            if assumptions["normalized_earnings_basis"]
            == "normalized_operating_cashflow"
            else input.normalized_net_profit
        ),
        float(assumptions["credible_growth_rate"][1]),
        sum(assumptions["cost_of_equity"]) / 2,
        float(assumptions["maintenance_growth"]),
        sum(assumptions["mature_pe"]) / 2,
        terminal_earnings=input.normalized_net_profit,
    )
    if pulled_forward is None:
        return _failure(
            input, assumption_snapshot, dossier_snapshot=dossier_snapshot,
            profile_version=profile_version, failure_kind="computation_failed",
            reason_code="solver_no_solution", reason="no finite value-pulled-forward duration",
        )
    warnings = list(verdict.warnings)
    warnings.extend(sensitivity_warnings)
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
        expectation_overdraft=overdraft, sensitivity=sensitivity,
        evidence=(), counter_evidence=(), unknowns=(), what_would_change_my_mind=(),
        provenance=provenance, input_digest=input_digest, diagnostic_digest="0" * 64,
    )
    finalized = replace(
        artifact, diagnostic_digest=compute_diagnostic_digest(artifact.to_dict())
    )
    return validate_diagnostic_binding(
        finalized.to_dict(),
        ticker=input.ticker,
        input_payload=input.to_dict(),
        assumption_snapshot=assumption_snapshot.to_dict(),
        formula_version=FORMULA_VERSION,
        dossier_snapshot=dossier_snapshot,
        profile_version=profile_version,
    )
