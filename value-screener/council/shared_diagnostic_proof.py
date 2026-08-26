"""Deterministic proof for the G2 3.4 shared diagnostic boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from data.lib.growth_expectation_contract import (
    ContractError,
    compute_diagnostic_digest,
    validate_assumption_snapshot,
    validate_diagnostic_binding,
)
from data.lib.identity import canonical_ticker


class SharedDiagnosticProofError(ValueError):
    """Raised when shared-input proof evidence is not trustworthy."""


_PATH_NAMES = frozenset({"strong_single_agent", "council"})
_ENVELOPE_FIELDS = frozenset(
    {
        "ticker",
        "run_id",
        "dossier_snapshot",
        "diagnostic_digest",
        "assumption_snapshot_digest",
    }
)
_FINDING_KINDS = frozenset(
    {"counter_evidence", "risk", "key_variable", "assumption_challenge", "shared_diagnostic"}
)
_SHARED_DIAGNOSTIC_METRICS = frozenset(
    {
        "future_value_share",
        "implied_growth_rate",
        "value_pulled_forward_years",
    }
)


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SharedDiagnosticProofError(f"{name} is required")
    return value.strip()


def _digest_text(name: str, value: Any) -> str:
    digest = _text(name, value)
    if len(digest) != 64 or digest.lower() != digest or any(
        char not in "0123456789abcdef" for char in digest
    ):
        raise SharedDiagnosticProofError(f"{name} is invalid")
    return digest


def _validate_envelope(name: str, value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SharedDiagnosticProofError(f"{name} envelope must be a mapping")
    unknown = set(value) - _ENVELOPE_FIELDS
    if unknown:
        raise SharedDiagnosticProofError(
            f"{name} envelope contains unknown fields: {sorted(unknown)}"
        )
    try:
        ticker = canonical_ticker(_text(f"{name}.ticker", value["ticker"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise SharedDiagnosticProofError(f"{name}.ticker is invalid") from exc
    digest = _digest_text(f"{name}.diagnostic_digest", value.get("diagnostic_digest"))
    assumption_digest = _digest_text(
        f"{name}.assumption_snapshot_digest",
        value.get("assumption_snapshot_digest"),
    )
    return {
        "ticker": ticker,
        "run_id": _text(f"{name}.run_id", value.get("run_id")),
        "dossier_snapshot": _text(
            f"{name}.dossier_snapshot", value.get("dossier_snapshot")
        ),
        "diagnostic_digest": digest,
        "assumption_snapshot_digest": assumption_digest,
    }


def build_shared_diagnostic_proof(
    *,
    diagnostic: Mapping[str, Any],
    ticker: str,
    run_id: str,
    input_payload: Mapping[str, Any],
    assumption_snapshot: Mapping[str, Any],
    formula_version: str,
    dossier_snapshot: str,
    profile_version: str,
    diagnostic_identity: Mapping[str, Any],
    path_envelopes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Prove that both paths reference one validated, immutable artifact."""
    if not isinstance(diagnostic, Mapping):
        raise SharedDiagnosticProofError("diagnostic must be a mapping")
    if not isinstance(path_envelopes, Mapping) or set(path_envelopes) != _PATH_NAMES:
        raise SharedDiagnosticProofError(
            "path_envelopes must contain strong_single_agent and council"
        )
    try:
        validated_snapshot = validate_assumption_snapshot(assumption_snapshot)
        bound = validate_diagnostic_binding(
            diagnostic,
            ticker=ticker,
            input_payload=input_payload,
            assumption_snapshot=assumption_snapshot,
            formula_version=formula_version,
            dossier_snapshot=dossier_snapshot,
            profile_version=profile_version,
        )
        canonical = canonical_ticker(ticker)
    except (ContractError, TypeError, ValueError) as exc:
        raise SharedDiagnosticProofError(str(exc)) from exc

    if bound.diagnostic_digest != compute_diagnostic_digest(diagnostic):
        raise SharedDiagnosticProofError("diagnostic_digest does not match artifact")
    if bound.assumption_snapshot is None:
        raise SharedDiagnosticProofError("diagnostic assumption_snapshot is required")
    if bound.assumption_snapshot.to_dict() != validated_snapshot.to_dict():
        raise SharedDiagnosticProofError("assumption_snapshot does not match artifact")

    if not isinstance(diagnostic_identity, Mapping):
        raise SharedDiagnosticProofError("diagnostic_identity must be a mapping")
    expected_identity_fields = {
        "ticker",
        "run_id",
        "dossier_snapshot",
        "diagnostic_digest",
        "assumption_snapshot_digest",
    }
    if set(diagnostic_identity) != expected_identity_fields:
        raise SharedDiagnosticProofError(
            "diagnostic_identity must contain the complete identity chain"
        )
    identity = {
        "ticker": canonical,
        "run_id": _text("run_id", run_id),
        "dossier_snapshot": _text("dossier_snapshot", dossier_snapshot),
        "diagnostic_digest": bound.diagnostic_digest,
        "assumption_snapshot_digest": _digest(validated_snapshot.to_dict()),
    }
    if dict(diagnostic_identity) != identity:
        raise SharedDiagnosticProofError(
            "diagnostic_identity does not match bound artifact and run"
        )
    provenance = bound.provenance
    if bound.ticker != identity["ticker"]:
        raise SharedDiagnosticProofError("ticker does not match artifact")
    if provenance is None or provenance.dossier_snapshot != identity["dossier_snapshot"]:
        raise SharedDiagnosticProofError("dossier_snapshot does not match artifact")

    normalized = {
        name: _validate_envelope(name, path_envelopes[name])
        for name in sorted(_PATH_NAMES)
    }
    for name, envelope in normalized.items():
        for field in (
            "ticker",
            "run_id",
            "dossier_snapshot",
            "diagnostic_digest",
            "assumption_snapshot_digest",
        ):
            if envelope[field] != identity[field]:
                raise SharedDiagnosticProofError(
                    f"{name} {field} does not match shared identity"
                )

    return {
        "status": "passed",
        "identity": identity,
        "paths": tuple(sorted(normalized)),
    }


def _normalize_findings(
    name: str, findings: Sequence[Mapping[str, Any]]
) -> list[tuple[str, str, Mapping[str, Any]]]:
    if not isinstance(findings, (list, tuple)):
        raise SharedDiagnosticProofError(f"{name} findings must be a list")
    normalized: list[tuple[str, str, Mapping[str, Any]]] = []
    fingerprints: dict[str, str] = {}
    for index, finding in enumerate(findings):
        if not isinstance(finding, Mapping):
            raise SharedDiagnosticProofError(f"{name}[{index}] must be a mapping")
        fingerprint = _text(
            f"{name}[{index}].fingerprint", finding.get("fingerprint")
        )
        kind = _text(f"{name}[{index}].kind", finding.get("kind"))
        _text(f"{name}[{index}].summary", finding.get("summary"))
        if kind not in _FINDING_KINDS:
            raise SharedDiagnosticProofError(
                f"{name}[{index}].kind is unsupported: {kind}"
            )
        if fingerprint in fingerprints and fingerprints[fingerprint] != kind:
            raise SharedDiagnosticProofError(
                f"{name}[{index}].fingerprint has conflicting kinds"
            )
        fingerprints[fingerprint] = kind
        normalized.append((fingerprint, kind, finding))
    return normalized


def classify_council_increment(
    *,
    baseline: Sequence[Mapping[str, Any]],
    council: Sequence[Mapping[str, Any]],
    diagnostic_digest: str | None = None,
) -> dict[str, Any]:
    """Classify only new substantive Council findings as increment."""
    baseline_findings = _normalize_findings("baseline", baseline)
    council_findings = _normalize_findings("council", council)
    baseline_fingerprints = {fingerprint for fingerprint, _, _ in baseline_findings}
    if any(kind == "shared_diagnostic" for _, kind, _ in (*baseline_findings, *council_findings)):
        if not diagnostic_digest:
            raise SharedDiagnosticProofError(
                "diagnostic_digest is required for shared_diagnostic findings"
            )
        diagnostic_digest = _digest_text("diagnostic_digest", diagnostic_digest)
        for fingerprint, kind, finding in (*baseline_findings, *council_findings):
            if kind != "shared_diagnostic":
                continue
            if finding.get("diagnostic_digest") != diagnostic_digest:
                raise SharedDiagnosticProofError(
                    f"shared_diagnostic finding {fingerprint} is not bound to diagnostic_digest"
                )
            if finding.get("metric") not in _SHARED_DIAGNOSTIC_METRICS:
                raise SharedDiagnosticProofError(
                    f"shared_diagnostic finding {fingerprint} must name a supported metric"
                )
    duplicates: set[str] = set()
    excluded_shared: set[str] = set()
    accepted: set[str] = set()
    seen: set[str] = set()
    for fingerprint, kind, finding in council_findings:
        if fingerprint in baseline_fingerprints or fingerprint in seen:
            duplicates.add(fingerprint)
        elif kind == "shared_diagnostic":
            excluded_shared.add(fingerprint)
        else:
            accepted.add(fingerprint)
        seen.add(fingerprint)
    return {
        "increment_count": len(accepted),
        "accepted": tuple(sorted(accepted)),
        "excluded_shared": tuple(sorted(excluded_shared)),
        "duplicates": tuple(sorted(duplicates)),
    }
