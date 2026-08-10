"""Explicit field-level qualification policy for run-scoped provider evidence."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .identity import canonical_ticker
from .provenance import validate_field_evidence

POLICY_VERSION = "g1-field-qualification-policy-v1"
DECISION_SCHEMA_VERSION = "g1-field-qualification-decision-v1"


class QualificationSourceError(ValueError):
    """Qualification source artifacts are incomplete or malformed."""


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_a_share(raw: Any) -> str:
    ticker = canonical_ticker(raw)
    if not ticker.endswith((".SH", ".SZ", ".BJ")):
        raise ValueError(f"not an A-share ticker: {raw!r}")
    return ticker


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class FieldQualificationPolicy:
    """Frozen policy describing the smallest promotable field group."""

    version: str
    required_tickers: tuple[str, ...]
    required_methods: tuple[tuple[str, tuple[str, ...]], ...]
    allowed_providers: tuple[str, ...]
    freshness_seconds: int | None = None
    probe_plan_version: str | None = None

    @classmethod
    def from_mapping(
        cls,
        *,
        version: str = POLICY_VERSION,
        tickers: Iterable[str],
        methods: Mapping[str, Iterable[str]],
        allowed_providers: Iterable[str],
        freshness_seconds: int | None = None,
        probe_plan_version: str | None = None,
    ) -> "FieldQualificationPolicy":
        if not isinstance(version, str) or not version.strip():
            raise ValueError("policy version must be a non-empty string")
        if tickers is None or isinstance(tickers, (str, bytes)):
            raise ValueError("tickers must be an iterable of A-share tickers")
        normalized_tickers = tuple(sorted({_canonical_a_share(ticker) for ticker in tickers}))
        if not normalized_tickers:
            raise ValueError("policy ticker set must not be empty")
        if not methods:
            raise ValueError("policy method matrix must not be empty")
        normalized_methods: list[tuple[str, tuple[str, ...]]] = []
        for raw_method, raw_fields in methods.items():
            if not isinstance(raw_method, str) or not raw_method.strip():
                raise ValueError("policy methods must be non-empty strings")
            if raw_fields is None or isinstance(raw_fields, (str, bytes)):
                raise ValueError("policy fields must be an iterable of strings")
            fields = tuple(sorted({field.strip() for field in raw_fields}))
            if not fields or any(not field for field in fields):
                raise ValueError("policy field set must not be empty")
            normalized_methods.append((raw_method.strip(), fields))
        normalized_providers = tuple(sorted({provider.strip() for provider in allowed_providers}))
        if not normalized_providers or any(not provider for provider in normalized_providers):
            raise ValueError("allowed provider set must not be empty")
        if freshness_seconds is not None and (
            not isinstance(freshness_seconds, int) or freshness_seconds < 0
        ):
            raise ValueError("freshness_seconds must be a non-negative integer")
        return cls(
            version=version.strip(),
            required_tickers=normalized_tickers,
            required_methods=tuple(sorted(normalized_methods)),
            allowed_providers=normalized_providers,
            freshness_seconds=freshness_seconds,
            probe_plan_version=probe_plan_version,
        )

    @property
    def matrix(self) -> set[tuple[str, str]]:
        return {
            (method, field)
            for method, fields in self.required_methods
            for field in fields
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "required_tickers": list(self.required_tickers),
            "required_methods": {
                method: list(fields) for method, fields in self.required_methods
            },
            "allowed_providers": list(self.allowed_providers),
            "freshness_seconds": self.freshness_seconds,
            "probe_plan_version": self.probe_plan_version,
        }

    @property
    def policy_hash(self) -> str:
        return _hash(self.to_dict())


@dataclass(frozen=True)
class QualificationRun:
    source_dir: Path
    manifest: Mapping[str, Any]
    plan: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    evidence_hash: str
    artifact_hashes: Mapping[str, str]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(manifest))
    payload.pop("manifest_hash", None)
    payload.pop("artifact_hashes", None)
    return _hash(payload)


def load_qualification_run(source_dir: str | Path) -> QualificationRun:
    root = Path(source_dir).resolve()
    manifest_path = root / "manifest.json"
    plan_path = root / "plan.json"
    evidence_path = root / "evidence.json"
    if (
        not manifest_path.is_file()
        or not plan_path.is_file()
        or not evidence_path.is_file()
    ):
        raise QualificationSourceError(
            "qualification source requires manifest.json, plan.json, and evidence.json"
        )
    try:
        manifest_bytes = manifest_path.read_bytes()
        plan_bytes = plan_path.read_bytes()
        evidence_bytes = evidence_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        plan = json.loads(plan_bytes)
        payload = json.loads(evidence_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationSourceError(
            f"cannot read qualification source artifact (manifest/plan/evidence): {exc}"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise QualificationSourceError("qualification manifest must be an object")
    if not isinstance(plan, Mapping):
        raise QualificationSourceError("qualification plan must be an object")
    if manifest.get("completion_status") != "completed":
        raise QualificationSourceError("qualification source must be completed")
    artifact_status = manifest.get("artifact_status") or {}
    if any(
        artifact_status.get(name) != "written"
        for name in ("plan", "evidence")
    ):
        raise QualificationSourceError("qualification source artifacts are not written")
    artifact_hashes = manifest.get("artifact_hashes")
    if not isinstance(artifact_hashes, Mapping):
        raise QualificationSourceError("qualification source artifact hashes are missing")
    for name, actual_hash in {
        "plan": _sha256_bytes(plan_bytes),
        "evidence": _sha256_bytes(evidence_bytes),
    }.items():
        if artifact_hashes.get(name) != actual_hash:
            raise QualificationSourceError(f"qualification {name} hash mismatch")
    if manifest.get("manifest_hash") != _manifest_hash(manifest):
        raise QualificationSourceError("qualification manifest hash mismatch")
    if manifest_bytes != _canonical_json_bytes(manifest):
        raise QualificationSourceError(
            "qualification manifest hash/serialization mismatch"
        )

    manifest_run_id = manifest.get("run_id")
    if not isinstance(manifest_run_id, str) or plan.get("run_id") != manifest_run_id:
        raise QualificationSourceError("qualification plan run identity mismatch")
    if plan.get("version") != manifest.get("plan_version"):
        raise QualificationSourceError("qualification plan version mismatch")
    cases = plan.get("cases")
    if not isinstance(cases, list) or not cases:
        raise QualificationSourceError("qualification plan cases are missing")
    if plan.get("plan_hash") != _hash(
        {"version": plan.get("version"), "cases": cases}
    ):
        raise QualificationSourceError("qualification plan hash mismatch")
    if manifest.get("plan_hash") != plan.get("plan_hash"):
        raise QualificationSourceError("qualification manifest/plan hash mismatch")
    expected_fields: set[tuple[str, str, str]] = set()
    expected_tickers: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise QualificationSourceError("qualification plan case is malformed")
        try:
            ticker = _canonical_a_share(case.get("ticker"))
        except (TypeError, ValueError) as exc:
            raise QualificationSourceError("qualification plan ticker is invalid") from exc
        method = case.get("method")
        fields = case.get("fields")
        if not isinstance(method, str) or not method.strip():
            raise QualificationSourceError("qualification plan method is invalid")
        if not isinstance(fields, list) or not fields or any(
            not isinstance(field, str) or not field.strip() for field in fields
        ):
            raise QualificationSourceError("qualification plan fields are invalid")
        expected_tickers.add(ticker)
        for field in fields:
            identity = (ticker, method, field)
            if identity in expected_fields:
                raise QualificationSourceError(
                    "qualification plan contains duplicate identity"
                )
            expected_fields.add(identity)
    if not isinstance(payload, Mapping):
        raise QualificationSourceError("qualification evidence payload must be an object")
    run_id = payload.get("run_id")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or any(not isinstance(item, Mapping) for item in evidence):
        raise QualificationSourceError("qualification evidence must be a list of objects")
    if run_id != manifest_run_id:
        raise QualificationSourceError("qualification run_id mismatch")
    expected_count = manifest.get("evidence_count")
    if expected_count is None:
        status_counts = manifest.get("field_status_counts") or {}
        if not isinstance(status_counts, Mapping):
            raise QualificationSourceError("qualification field status counts are malformed")
        expected_count = sum(
            value for value in status_counts.values() if isinstance(value, int)
        )
    if not isinstance(expected_count, int) or expected_count != len(evidence):
        raise QualificationSourceError(
            f"qualification evidence count mismatch: expected {expected_count}, got {len(evidence)}"
        )
    if manifest.get("ticker_set_hash") != _hash(sorted(expected_tickers)):
        raise QualificationSourceError("qualification ticker identity hash mismatch")
    observed_fields: set[tuple[str, str, str]] = set()
    for item in evidence:
        try:
            ticker = _canonical_a_share(item.get("ticker"))
        except (TypeError, ValueError) as exc:
            raise QualificationSourceError("qualification evidence ticker is invalid") from exc
        identity = (ticker, item.get("method"), item.get("field"))
        if identity not in expected_fields:
            raise QualificationSourceError(
                "qualification evidence identity is outside frozen plan"
            )
        if identity in observed_fields:
            raise QualificationSourceError(
                "qualification evidence contains duplicate identity"
            )
        observed_fields.add(identity)
    missing_fields = expected_fields.difference(observed_fields)
    if missing_fields:
        raise QualificationSourceError(
            "qualification evidence is missing frozen plan identity"
        )
    normalized = tuple(copy.deepcopy(item) for item in evidence)
    return QualificationRun(
        source_dir=root,
        manifest=copy.deepcopy(dict(manifest)),
        plan=copy.deepcopy(dict(plan)),
        evidence=normalized,
        evidence_hash=_hash(
            sorted(
                normalized,
                key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
            )
        ),
        artifact_hashes=copy.deepcopy(dict(artifact_hashes)),
    )


def _identity(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("provider_family", "provider", "method", "ticker", "field")
    }


def _decision(
    *,
    key: tuple[str, str, str, str],
    items: list[Mapping[str, Any]],
    policy: FieldQualificationPolicy,
    reason_codes: list[str],
    source_hash: str,
) -> dict[str, Any]:
    provider_family, provider, method, field = key
    return {
        "provider_family": provider_family,
        "provider": provider,
        "method": method,
        "field": field,
        "decision": "qualified" if not reason_codes else "rejected",
        "reason_codes": sorted(set(reason_codes)),
        "required_tickers": list(policy.required_tickers),
        "observed_tickers": sorted(
            str(item.get("ticker")) for item in items if item.get("ticker") is not None
        ),
        "source_evidence_hashes": sorted(
            str(item.get("response_hash")) for item in items
        ),
        "source_run_evidence_hash": source_hash,
    }


def _blocked_decision(
    run: QualificationRun,
    policy: FieldQualificationPolicy,
    *,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": DECISION_SCHEMA_VERSION,
        "status": "blocked",
        "reason": reason,
        "source_run_id": run.manifest.get("run_id"),
        "source_dir": str(run.source_dir),
        "source_evidence_hash": run.evidence_hash,
        "source_artifact_hashes": dict(run.artifact_hashes),
        "source_plan_hash": run.plan.get("plan_hash"),
        "policy": policy.to_dict(),
        "policy_hash": policy.policy_hash,
        "evaluated_at": None,
        "decisions": [],
        "promoted_evidence": [],
        "unexpected_evidence": [],
    }


def evaluate_qualification_run(
    source_dir: str | Path,
    *,
    policy: FieldQualificationPolicy,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    run = load_qualification_run(source_dir)
    reference = evaluated_at or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    if (
        policy.probe_plan_version is not None
        and run.manifest.get("plan_version") != policy.probe_plan_version
    ):
        return _blocked_decision(
            run,
            policy,
            reason="qualification plan version does not match policy",
        )

    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    unexpected: list[dict[str, Any]] = []
    for item in run.evidence:
        try:
            ticker = _canonical_a_share(item.get("ticker"))
        except (TypeError, ValueError):
            unexpected.append({**_identity(item), "reason": "invalid_ticker"})
            continue
        method = item.get("method")
        field = item.get("field")
        if (method, field) not in policy.matrix or ticker not in policy.required_tickers:
            unexpected.append(
                {
                    **_identity(item),
                    "ticker": ticker,
                    "reason": "outside_policy_matrix",
                }
            )
            continue
        key = (
            str(item.get("provider_family")),
            str(item.get("provider")),
            str(method),
            str(field),
        )
        groups.setdefault(key, []).append(item)

    decisions: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    provider_keys = {
        (str(item.get("provider_family")), str(item.get("provider")))
        for item in run.evidence
    }
    if not provider_keys:
        provider_keys = {("unknown", provider) for provider in policy.allowed_providers}
    required_matrix = policy.matrix
    complete_providers: set[tuple[str, str]] = set()
    for provider_key in provider_keys:
        observed_matrix = {
            (str(item.get("method")), str(item.get("field")))
            for item in run.evidence
            if (
                str(item.get("provider_family")),
                str(item.get("provider")),
            )
            == provider_key
        }
        if required_matrix.issubset(observed_matrix):
            complete_providers.add(provider_key)

    for key in sorted(groups):
        items = groups[key]
        provider_key = key[:2]
        provider = key[1]
        reasons: list[str] = []
        if provider not in policy.allowed_providers:
            reasons.append("provider_not_allowed")
        if provider_key not in complete_providers:
            reasons.append("missing_field_group")
        by_ticker: dict[str, list[Mapping[str, Any]]] = {}
        for item in items:
            ticker = _canonical_a_share(item.get("ticker"))
            by_ticker.setdefault(ticker, []).append(item)
        if any(len(values) != 1 for values in by_ticker.values()):
            reasons.append("duplicate_ticker_evidence")
        missing = set(policy.required_tickers).difference(by_ticker)
        if missing:
            reasons.append("missing_ticker_coverage")

        validated: list[dict[str, Any]] = []
        for item in items:
            normalized = validate_field_evidence(item, allow_production=False)
            if normalized["status"] != "available":
                reasons.append("non_available_status")
            if item.get("freshness_status") in {"stale", "unknown"}:
                reasons.append(
                    f"{item.get('freshness_status')}_freshness"
                )
            retrieved = _parse_time(normalized.get("retrieved_at"))
            if retrieved is None:
                reasons.append("invalid_retrieved_at")
            elif policy.freshness_seconds is not None and (
                reference - retrieved
            ).total_seconds() > policy.freshness_seconds:
                reasons.append("stale_evidence")
            validated.append(normalized)

        metadata_keys = ("unit", "currency", "as_of", "report_period")
        metadata_values = {
            key_name: {
                json.dumps(item.get(key_name), ensure_ascii=False, sort_keys=True, default=str)
                for item in validated
            }
            for key_name in metadata_keys
        }
        if any(len(values) > 1 for values in metadata_values.values()):
            reasons.append("metadata_conflict")

        record = _decision(
            key=key,
            items=items,
            policy=policy,
            reason_codes=reasons,
            source_hash=run.evidence_hash,
        )
        decisions.append(record)
        if record["decision"] == "qualified":
            for item in validated:
                promoted_item = copy.deepcopy(item)
                promoted_item["eligibility"] = "production_eligible"
                promoted.append(promoted_item)

    for provider_family, provider in sorted(provider_keys):
        if (provider_family, provider) in complete_providers:
            continue
        observed = {
            (str(item.get("method")), str(item.get("field")))
            for item in run.evidence
            if (
                str(item.get("provider_family")),
                str(item.get("provider")),
            )
            == (provider_family, provider)
        }
        for method, field in sorted(required_matrix - observed):
            decisions.append(
                _decision(
                    key=(provider_family, provider, method, field),
                    items=[],
                    policy=policy,
                    reason_codes=["missing_field_group"],
                    source_hash=run.evidence_hash,
                )
            )

    status = "qualified" if promoted else "blocked"
    evaluated = reference.isoformat()
    decision = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "status": status,
        "source_run_id": run.manifest.get("run_id"),
        "source_dir": str(run.source_dir),
        "source_evidence_hash": run.evidence_hash,
        "source_artifact_hashes": dict(run.artifact_hashes),
        "source_plan_hash": run.plan.get("plan_hash"),
        "policy": policy.to_dict(),
        "policy_hash": policy.policy_hash,
        "evaluated_at": evaluated,
        "decisions": decisions,
        "promoted_evidence": promoted,
        "unexpected_evidence": unexpected,
    }
    decision["status_summary"] = {
        "qualified_groups": sum(
            item["decision"] == "qualified" for item in decisions
        ),
        "rejected_groups": sum(
            item["decision"] == "rejected" for item in decisions
        ),
        "unexpected_evidence": len(unexpected),
        "promoted_fields": len(promoted),
    }
    decision["decision_hash"] = _hash(
        {key: value for key, value in decision.items() if key != "decision_hash"}
    )
    return decision
