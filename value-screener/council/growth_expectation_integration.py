"""G2 3.3 binding and projection boundary for growth expectation artifacts."""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Any

from data.lib.growth_expectation_contract import (
    ContractError,
    GrowthExpectationDiagnostic,
    validate_diagnostic_binding,
)
from data.lib.identity import canonical_ticker


_FAILURE_NUMERIC_FIELDS = (
    "current_market_value",
    "current_business_value",
    "priced_growth_value_range",
    "priced_growth_share_range",
    "reverse_scenarios",
    "credible_growth_range",
    "expectation_gap",
    "value_pulled_forward_years",
    "sensitivity",
)


def bind_growth_expectation_artifact(
    value: GrowthExpectationDiagnostic | Mapping[str, Any],
    *,
    ticker: str,
    dossier_snapshot: str | None = None,
    profile_version: str | None = None,
    assumption_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and return a detached JSON-compatible diagnostic artifact."""
    payload = (
        value.to_dict()
        if isinstance(value, GrowthExpectationDiagnostic)
        else dict(value)
    )
    if not isinstance(payload, dict):
        raise ContractError("growth expectation diagnostic must be a mapping")

    ticker = canonical_ticker(ticker)
    if not dossier_snapshot or not profile_version:
        raise ContractError(
            "dossier_snapshot and profile_version are required for integration binding"
        )
    provenance = payload.get("provenance") or {}
    input_snapshot = payload.get("input_snapshot")
    bound_assumption_snapshot = (
        payload.get("assumption_snapshot")
        if payload.get("assumption_snapshot") is not None
        else assumption_snapshot
    )
    if not isinstance(provenance, Mapping):
        raise ContractError("growth expectation diagnostic provenance is required")
    if not isinstance(input_snapshot, Mapping):
        raise ContractError("growth expectation diagnostic input_snapshot is required")
    if not isinstance(bound_assumption_snapshot, Mapping):
        raise ContractError(
            "growth expectation diagnostic binding assumption_snapshot is required"
        )

    bound_dossier_snapshot = provenance.get("dossier_snapshot")
    bound_profile_version = provenance.get("profile_version")
    if bound_dossier_snapshot != dossier_snapshot:
        raise ContractError("growth expectation dossier_snapshot mismatch")
    if bound_profile_version != profile_version:
        raise ContractError("growth expectation profile_version mismatch")

    diagnostic = validate_diagnostic_binding(
        payload,
        ticker=ticker,
        input_payload=input_snapshot,
        assumption_snapshot=bound_assumption_snapshot,
        formula_version=provenance.get("formula_version"),
        dossier_snapshot=bound_dossier_snapshot,
        profile_version=bound_profile_version,
    )
    bound = deepcopy(diagnostic.to_dict())
    if "assumption_snapshot" not in payload:
        bound.pop("assumption_snapshot", None)
    _reject_failure_numeric_conclusions(bound)
    return bound


def _reject_failure_numeric_conclusions(payload: Mapping[str, Any]) -> None:
    if payload.get("calculation_status") not in {"not_evaluable", "failed"}:
        return
    present = [
        field
        for field in _FAILURE_NUMERIC_FIELDS
        if payload.get(field) not in (None, [], {})
    ]
    if present:
        raise ContractError(
            "failure diagnostic must not contain numeric conclusions: "
            + ", ".join(present)
        )


def add_growth_expectation_to_dossier(
    dossier: dict[str, Any],
    diagnostic: GrowthExpectationDiagnostic | Mapping[str, Any],
    *,
    ticker: str,
    dossier_snapshot: str | None = None,
    profile_version: str | None = None,
    assumption_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach one validated artifact to a dossier without mutating its input."""
    bound = bind_growth_expectation_artifact(
        diagnostic,
        ticker=ticker,
        dossier_snapshot=dossier_snapshot,
        profile_version=profile_version,
        assumption_snapshot=assumption_snapshot,
    )
    result = deepcopy(dossier)
    result["growth_expectation_diagnostic"] = bound
    result["valuation_expectation"] = deepcopy(bound)
    result["growth_expectation_identity"] = {
        "ticker": bound["ticker"],
        "input_digest": bound["input_digest"],
        "diagnostic_digest": bound["diagnostic_digest"],
        "dossier_snapshot": bound["provenance"]["dossier_snapshot"],
        "profile_version": bound["provenance"]["profile_version"],
        "formula_version": bound["provenance"]["formula_version"],
        "assumption_snapshot_version": bound["provenance"][
            "assumption_snapshot_version"
        ],
    }
    if bound.get("assumption_snapshot") is None and assumption_snapshot is not None:
        result["growth_expectation_binding_assumption_snapshot"] = deepcopy(
            dict(assumption_snapshot)
        )
    return result


def _identity_from_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ContractError("growth expectation provenance is required")
    return {
        "ticker": payload["ticker"],
        "input_digest": payload["input_digest"],
        "diagnostic_digest": payload["diagnostic_digest"],
        "dossier_snapshot": provenance["dossier_snapshot"],
        "profile_version": provenance["profile_version"],
        "formula_version": provenance["formula_version"],
        "assumption_snapshot_version": provenance[
            "assumption_snapshot_version"
        ],
    }


def build_investment_thesis(
    thesis: Mapping[str, Any] | None,
    dossier: Mapping[str, Any],
) -> dict[str, Any]:
    """Add the dossier-bound valuation expectation to a thesis mapping."""
    if not isinstance(dossier, Mapping):
        raise ContractError("dossier must be a mapping")
    valuation = dossier.get("valuation_expectation")
    diagnostic = dossier.get("growth_expectation_diagnostic")
    if not isinstance(valuation, Mapping) or not isinstance(diagnostic, Mapping):
        raise ContractError("dossier has no bound growth expectation artifact")
    if dict(valuation) != dict(diagnostic):
        raise ContractError("dossier valuation expectation is not the bound artifact")
    expected_identity = _identity_from_artifact(diagnostic)
    if dossier.get("growth_expectation_identity") != expected_identity:
        raise ContractError("dossier growth expectation identity sidecar mismatch")
    provenance = diagnostic.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ContractError("dossier diagnostic provenance is required")
    bound = bind_growth_expectation_artifact(
        diagnostic,
        ticker=diagnostic.get("ticker"),
        dossier_snapshot=provenance.get("dossier_snapshot"),
        profile_version=provenance.get("profile_version"),
        assumption_snapshot=dossier.get(
            "growth_expectation_binding_assumption_snapshot"
        ),
    )
    _reject_failure_numeric_conclusions(bound)

    result = deepcopy(dict(thesis or {}))
    result["valuation_expectation"] = deepcopy(bound)
    result["growth_expectation_diagnostic"] = deepcopy(bound)
    result["growth_expectation_identity"] = deepcopy(
        dossier.get("growth_expectation_identity", {})
    )
    return result
