"""Provider field evidence / provenance contract.

这是 provider raw response 与 canonical snapshot 之间的纯 contract 层。
它只校验和生成 sidecar metadata，不修改 legacy consumer payload，也不决定
任何字段可以进入生产 ranking。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

STATUSES = {
    "available",
    "partial",
    "record_not_found",
    "source_failed",
    "permission_denied",
    "rate_limited",
    "not_supported_for_market",
    "invalid_value",
    "not_evaluated",
    "conflict",
}

ELIGIBILITIES = {"not_qualified", "shadow_only", "production_eligible"}

_NUMERIC_FIELDS = {
    "last_price",
    "previous_close",
    "volume",
    "turnover_rate",
    "pe_ttm",
    "pb",
    "dividend_yield",
    "revenue",
    "net_profit",
    "total_assets",
    "total_liabilities",
    "cash",
    "operating_cash_flow",
    "capital_expenditure",
    "pe_median",
    "eps_consensus",
    "revenue_consensus",
}
_TIME_REQUIRED_FIELDS = {
    "revenue",
    "net_profit",
    "total_assets",
    "total_liabilities",
    "cash",
    "operating_cash_flow",
    "capital_expenditure",
    "pe_ttm",
    "pb",
    "pe_median",
    "eps_consensus",
    "revenue_consensus",
}


class ProvenanceContractError(ValueError):
    """Evidence contract is malformed or violates a fail-closed rule."""


def _redact(text: Any) -> str:
    value = str(text)
    value = re.sub(r"(?i)(https?://)[^/\s@]+@", r"\1<redacted>@", value)
    value = re.sub(
        r"(?i)\b(authorization|api[_-]?key|secret|token)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        value,
    )
    value = re.sub(r"\bsk-[A-Za-z0-9_-]+\b", "sk-<redacted>", value)
    return value[:2_000]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return _redact(repr(value))


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def validate_field_evidence(
    evidence: Mapping[str, Any],
    *,
    allow_production: bool = False,
) -> dict[str, Any]:
    """Validate one field evidence and return a JSON-safe sidecar record.

    Missing metadata downgrades an otherwise available field to ``not_evaluated``.
    It never silently supplies a unit, currency, date, or production eligibility.
    """
    result = dict(evidence)
    status = result.get("status")
    eligibility = result.get("eligibility", "not_qualified")
    if status not in STATUSES:
        raise ProvenanceContractError(f"unknown status: {status!r}")
    if eligibility not in ELIGIBILITIES:
        raise ProvenanceContractError(f"unknown eligibility: {eligibility!r}")
    if eligibility == "production_eligible" and not allow_production:
        raise ProvenanceContractError("production eligibility requires an explicit later policy")

    required_provenance = (
        "provider_family",
        "provider",
        "method",
        "market",
        "ticker",
        "raw_field",
        "response_hash",
        "retrieved_at",
    )
    provenance = result.get("provenance")
    missing = [
        key
        for key in required_provenance
        if not result.get(key)
        or not isinstance(provenance, Mapping)
        or not provenance.get(key)
    ]
    reason = result.get("reason")
    if missing:
        status = "not_evaluated"
        reason = f"missing provenance: {', '.join(missing)}"

    field = result.get("field")
    value = result.get("value")
    if status == "available":
        if field in _NUMERIC_FIELDS and not _is_numeric(value):
            status = "invalid_value"
            reason = reason or "numeric field has non-finite/non-numeric value"
        elif field in _NUMERIC_FIELDS and not result.get("unit") and not result.get("currency"):
            status = "not_evaluated"
            reason = reason or "numeric field has no unit/currency"
        elif field in _TIME_REQUIRED_FIELDS and not (result.get("as_of") or result.get("report_period")):
            status = "not_evaluated"
            reason = reason or "time basis is missing"

    if status != "available":
        eligibility = "not_qualified"
    result.update(
        {
            "status": status,
            "eligibility": eligibility,
            "value": _json_safe(value),
            "reason": _redact(reason) if reason else None,
            "provenance": _json_safe(provenance or {}),
        }
    )
    return _json_safe(result)


def build_sidecar(
    evidence: Iterable[Mapping[str, Any]],
    *,
    allow_production: bool = False,
) -> dict[str, Any]:
    fields = [
        validate_field_evidence(item, allow_production=allow_production)
        for item in evidence
    ]
    return {
        "schema_version": "provider-contract-and-provenance-v1",
        "field_count": len(fields),
        "evidence_hash": _hash(fields),
        "fields": fields,
    }


def detect_conflicts(
    evidence: Iterable[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    freshness_seconds: int | None = None,
    allow_production: bool = False,
) -> list[dict[str, Any]]:
    """Return conflicts without selecting or dropping any source evidence."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in evidence:
        normalized = validate_field_evidence(item, allow_production=allow_production)
        if normalized["status"] != "available":
            continue
        key = (
            normalized.get("ticker"),
            normalized.get("field"),
        )
        groups[key].append(normalized)

    conflicts: list[dict[str, Any]] = []
    current = now or datetime.now(timezone.utc)
    for key, items in groups.items():
        values = {_hash(item.get("value")) for item in items}
        units = {(item.get("unit"), item.get("currency")) for item in items}
        times = {(item.get("as_of"), item.get("report_period")) for item in items}
        if len(values) > 1:
            conflicts.append({"kind": "value", "key": key, "providers": items})
        if len(units) > 1:
            conflicts.append({"kind": "unit_or_currency", "key": key, "providers": items})
        if len(times) > 1:
            conflicts.append({"kind": "time_basis", "key": key, "providers": items})

        if freshness_seconds is not None:
            fresh = []
            stale = []
            for item in items:
                retrieved = _parse_time(
                    (item.get("provenance") or {}).get("retrieved_at")
                )
                if retrieved is None or (current - retrieved).total_seconds() > freshness_seconds:
                    stale.append(item)
                else:
                    fresh.append(item)
            if fresh and stale:
                conflicts.append(
                    {
                        "kind": "freshness",
                        "key": key,
                        "fresh_providers": fresh,
                        "stale_providers": stale,
                    }
                )
    return conflicts


def sidecar_for_qualification_evidence(
    payload: Mapping[str, Any],
    *,
    allow_production: bool = False,
) -> dict[str, Any]:
    """Convert qualification ``evidence.json`` payload to the contract sidecar."""
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise ProvenanceContractError("qualification payload must contain an evidence list")
    return build_sidecar(evidence, allow_production=allow_production)


def serialize_sidecar(sidecar: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(sidecar), ensure_ascii=False, indent=2, sort_keys=True)
