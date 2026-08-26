from __future__ import annotations

import pytest

from council.research_dossier import build_research_dossier
from data.lib.growth_expectation_contract import ContractError, compute_diagnostic_digest
from data.lib.growth_expectation_engine import compute_growth_expectation_diagnostic

from test_g2_growth_expectation_engine import (
    FORMULA_VERSION,
    assumptions,
    input_payload,
)
from test_research_dossier import (
    _core_snapshot,
    _financials_with_capex,
    _main_business,
    _patch_all_fetchers,
    _peers,
    _research,
    _risk_with_pledge,
)


def _diagnostic(*, market_value: float = 1800.0, industry: str | None = "consumer"):
    from data.lib.growth_expectation_contract import (
        validate_assumption_snapshot,
        validate_diagnostic_input,
    )

    payload = input_payload(market_value=market_value, industry=industry)
    payload["ticker"] = "600009.SH"
    for item in payload["sources"]:
        item["ticker"] = "600009.SH"
    return compute_growth_expectation_diagnostic(
        validate_diagnostic_input(payload),
        validate_assumption_snapshot(assumptions()),
        dossier_snapshot="dossier-v1",
        profile_version="profile-v1",
    )


def _clean_diagnostic():
    payload = _diagnostic(industry="consumer").to_dict()
    payload["calculation_status"] = "clean"
    payload["warnings"] = []
    payload["diagnostic_digest"] = compute_diagnostic_digest(payload)
    return payload


def _build(diagnostic):
    with _patch_all_fetchers(
        mb=_main_business(),
        peers=_peers(),
        research=_research(),
        fin=_financials_with_capex(),
        risk=_risk_with_pledge(),
    ):
        return build_research_dossier(
            "600009.SH",
            core_snapshot=_core_snapshot(),
            growth_expectation_diagnostic=(
                diagnostic.to_dict()
                if hasattr(diagnostic, "to_dict")
                else diagnostic
            ),
            dossier_snapshot="dossier-v1",
            profile_version="profile-v1",
        )


def test_dossier_and_thesis_preserve_bound_diagnostic_identity_and_assumptions():
    diagnostic = _diagnostic()

    dossier = _build(diagnostic)
    from council.investment_thesis import build_investment_thesis

    thesis = build_investment_thesis({"ticker": "600519.SH"}, dossier)

    assert dossier["growth_expectation_diagnostic"] == diagnostic.to_dict()
    assert dossier["valuation_expectation"] == diagnostic.to_dict()
    assert thesis["valuation_expectation"] == diagnostic.to_dict()
    assert thesis["valuation_expectation"]["input_digest"] == diagnostic.input_digest
    assert thesis["valuation_expectation"]["diagnostic_digest"] == diagnostic.diagnostic_digest
    assert thesis["valuation_expectation"]["assumption_snapshot"] == diagnostic.assumption_snapshot.to_dict()
    assert thesis["valuation_expectation"]["provenance"] == diagnostic.provenance.to_dict()
    assert thesis["valuation_expectation"]["calculation_status"] == diagnostic.calculation_status


def test_dossier_rejects_mutated_digest_before_returning():
    payload = _diagnostic().to_dict()
    payload["diagnostic_digest"] = "0" * 64

    with pytest.raises(ContractError, match="diagnostic_digest"):
        with _patch_all_fetchers():
            build_research_dossier(
                "600009.SH",
                core_snapshot=_core_snapshot(),
                growth_expectation_diagnostic=payload,
                dossier_snapshot="dossier-v1",
                profile_version="profile-v1",
            )


def test_dossier_rejects_provenance_identity_mismatch():
    payload = _diagnostic().to_dict()
    payload["provenance"]["profile_version"] = "profile-other"

    with pytest.raises(ContractError, match="profile_version"):
        with _patch_all_fetchers():
            build_research_dossier(
                "600009.SH",
                core_snapshot=_core_snapshot(),
                growth_expectation_diagnostic=payload,
                dossier_snapshot="dossier-v1",
                profile_version="profile-v1",
            )


def test_thesis_rejects_dossier_artifact_mutated_after_dossier_binding():
    dossier = _build(_diagnostic())
    dossier["valuation_expectation"]["diagnostic_digest"] = "0" * 64

    from council.investment_thesis import build_investment_thesis

    with pytest.raises(ContractError, match="bound artifact|diagnostic_digest"):
        build_investment_thesis({}, dossier)


@pytest.mark.parametrize("sidecar", [None, {"ticker": "600009.SH"}])
def test_thesis_rejects_missing_or_forged_identity_sidecar(sidecar):
    dossier = _build(_diagnostic())
    if sidecar is None:
        dossier.pop("growth_expectation_identity")
    else:
        dossier["growth_expectation_identity"] = sidecar

    from council.investment_thesis import build_investment_thesis

    with pytest.raises(ContractError, match="identity sidecar"):
        build_investment_thesis({}, dossier)


def test_dossier_and_thesis_views_are_detached_from_each_other():
    dossier = _build(_diagnostic())

    from council.investment_thesis import build_investment_thesis

    thesis = build_investment_thesis({}, dossier)
    thesis["valuation_expectation"]["warnings"].append("consumer mutation")
    thesis["valuation_expectation"]["assumption_snapshot"]["assumptions"][0][
        "source"
    ] = "consumer mutation"

    assert "consumer mutation" not in dossier["valuation_expectation"]["warnings"]
    assert (
        dossier["valuation_expectation"]["assumption_snapshot"]["assumptions"][0][
            "source"
        ]
        != "consumer mutation"
    )


def test_not_evaluable_without_embedded_assumptions_uses_external_binding_snapshot():
    diagnostic = _diagnostic(industry="banking")
    payload = diagnostic.to_dict()
    external_snapshot = payload.pop("assumption_snapshot")
    payload.pop("assumptions", None)
    payload["diagnostic_digest"] = compute_diagnostic_digest(payload)

    with _patch_all_fetchers():
        dossier = build_research_dossier(
            "600009.SH",
            core_snapshot=_core_snapshot(),
            growth_expectation_diagnostic=payload,
            dossier_snapshot="dossier-v1",
            profile_version="profile-v1",
            growth_expectation_assumption_snapshot=external_snapshot,
        )

    from council.investment_thesis import build_investment_thesis

    thesis = build_investment_thesis({}, dossier)
    assert "assumption_snapshot" not in dossier["growth_expectation_diagnostic"]
    assert dossier["growth_expectation_diagnostic"]["calculation_status"] == "not_evaluable"
    assert "assumption_snapshot" not in thesis["valuation_expectation"]
    assert thesis["valuation_expectation"]["diagnostic_digest"] == payload["diagnostic_digest"]


@pytest.mark.parametrize(
    ("diagnostic", "expected_status"),
    [
        (_clean_diagnostic(), "clean"),
        (_diagnostic(industry=None), "degraded"),
        (_diagnostic(industry="banking"), "not_evaluable"),
        (_diagnostic(market_value=1_000_000.0), "failed"),
    ],
)
def test_dossier_and_thesis_preserve_each_calculation_status(
    diagnostic, expected_status
):
    dossier = _build(diagnostic)
    from council.investment_thesis import build_investment_thesis

    thesis = build_investment_thesis({}, dossier)

    valuation = thesis["valuation_expectation"]
    assert valuation["calculation_status"] == expected_status
    assert valuation["quality_status"] == (
        "failed" if expected_status == "failed" else "warning"
    )
    if expected_status in {"not_evaluable", "failed"}:
        assert valuation["current_market_value"] is None
        assert valuation["current_business_value"] is None
        assert valuation["priced_growth_value_range"] is None
        assert valuation["reverse_scenarios"] == []
        assert valuation["sensitivity"] == []
        assert valuation["reasons"]
