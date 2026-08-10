"""Read-only consumer for the G1 canonical snapshot contract."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .identity import canonical_ticker, compute_snapshot_ticker_set_hash

SUPPORTED_SCHEMA_VERSION = "g1-canonical-snapshot-v1"
_UNAVAILABLE_STATUSES = {
    "record_not_found",
    "source_failed",
    "invalid_value",
    "not_evaluated",
    "stale",
    "degraded",
    "conflict",
    "partial",
    "permission_denied",
    "rate_limited",
    "not_supported_for_market",
}


class SnapshotConsumerError(ValueError):
    """Snapshot cannot satisfy the G1 consumer contract."""


@dataclass(frozen=True)
class ConsumedField:
    value: Any
    status: str
    eligibility: str
    reason: str | None
    provenance: Mapping[str, Any]
    as_of: str | None
    freshness: str | None

    @property
    def available(self) -> bool:
        return (
            self.value is not None
            and self.status == "available"
            and self.eligibility == "production_eligible"
            and self.freshness == "fresh"
        )


class CanonicalSnapshotConsumer:
    """Validated in-memory view over one immutable snapshot run."""

    def __init__(
        self,
        *,
        manifest: Mapping[str, Any],
        records: Mapping[str, Mapping[str, Any]],
        fields: Mapping[tuple[str, str], ConsumedField],
    ) -> None:
        self.manifest = _freeze(manifest)
        self._records = _freeze(records)
        self._fields = MappingProxyType(dict(fields))

    def get(self, ticker: str, field: str) -> ConsumedField:
        canonical = canonical_ticker(ticker)
        try:
            return self._fields[(canonical, field)]
        except KeyError as exc:
            raise SnapshotConsumerError(
                f"field is not represented in canonical snapshot: {canonical}.{field}"
            ) from exc

    def fields_for(self, ticker: str) -> Mapping[str, ConsumedField]:
        canonical = canonical_ticker(ticker)
        selected = {
            field: value
            for (field_ticker, field), value in self._fields.items()
            if field_ticker == canonical
        }
        if not selected:
            raise SnapshotConsumerError(
                f"ticker is not represented in canonical snapshot: {canonical}"
            )
        return MappingProxyType(selected)


def consume_snapshot(
    run_dir: str | Path,
    *,
    expected_run_id: str,
    expected_plan_version: str,
    expected_tickers: Sequence[str],
    expected_ticker_set_hash: str | None = None,
) -> CanonicalSnapshotConsumer:
    root = Path(run_dir)
    payload = _read_payload(root)
    manifest = payload["manifest"]
    records = payload["records"]
    provenance = payload["provenance"]

    _validate_manifest(
        manifest,
        expected_run_id=expected_run_id,
        expected_plan_version=expected_plan_version,
        expected_tickers=expected_tickers,
        expected_ticker_set_hash=expected_ticker_set_hash,
    )
    _validate_records(records)
    _validate_ticker_set(records, expected_tickers)
    fields = _validate_and_build_fields(
        manifest=manifest,
        records=records,
        provenance=provenance,
    )
    return CanonicalSnapshotConsumer(
        manifest=manifest,
        records=records,
        fields=fields,
    )


def _read_payload(root: Path) -> dict[str, Any]:
    required = ("manifest.json", "records.json", "provenance.json")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise SnapshotConsumerError(
            f"missing required snapshot file(s): {', '.join(missing)}"
        )

    payload: dict[str, Any] = {}
    for name in required:
        try:
            value = json.loads((root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotConsumerError(f"invalid {name}") from exc
        payload[name.removesuffix(".json")] = value

    if not isinstance(payload["manifest"], Mapping):
        raise SnapshotConsumerError("manifest.json must contain an object")
    if not isinstance(payload["records"], Mapping):
        raise SnapshotConsumerError("records.json must contain an object")
    if not isinstance(payload["provenance"], Mapping):
        raise SnapshotConsumerError("provenance.json must contain an object")
    return payload


def _validate_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_run_id: str,
    expected_plan_version: str,
    expected_tickers: Sequence[str],
    expected_ticker_set_hash: str | None,
) -> None:
    if manifest.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise SnapshotConsumerError(
            f"unsupported schema_version: {manifest.get('schema_version')!r}"
        )
    if manifest.get("run_id") != expected_run_id:
        raise SnapshotConsumerError("run_id mismatch")
    if manifest.get("plan_version") != expected_plan_version:
        raise SnapshotConsumerError("plan_version mismatch")

    canonical_expected = _canonical_tickers(expected_tickers)
    manifest_hash = manifest.get("ticker_set_hash")
    calculated_hash = compute_snapshot_ticker_set_hash(canonical_expected)
    if expected_ticker_set_hash is not None and manifest_hash != expected_ticker_set_hash:
        raise SnapshotConsumerError("ticker_set_hash mismatch")
    if manifest_hash != calculated_hash:
        raise SnapshotConsumerError("ticker_set_hash mismatch")


def _validate_records(records: Mapping[str, Any]) -> None:
    for raw_ticker, values in records.items():
        try:
            ticker = canonical_ticker(raw_ticker)
        except ValueError as exc:
            raise SnapshotConsumerError(f"invalid ticker identity: {raw_ticker!r}") from exc
        if ticker != raw_ticker:
            raise SnapshotConsumerError(f"ticker identity is not canonical: {raw_ticker!r}")
        if not isinstance(values, Mapping):
            raise SnapshotConsumerError(f"records for {ticker} must be an object")
        if any(not isinstance(field, str) for field in values):
            raise SnapshotConsumerError(f"record field identity is invalid for {ticker}")


def _validate_ticker_set(
    records: Mapping[str, Any],
    expected_tickers: Sequence[str],
) -> None:
    expected = set(_canonical_tickers(expected_tickers))
    actual = set(records)
    if actual != expected:
        raise SnapshotConsumerError(
            f"ticker set mismatch: expected {sorted(expected)}, got {sorted(actual)}"
        )


def _validate_and_build_fields(
    *,
    manifest: Mapping[str, Any],
    records: Mapping[str, Mapping[str, Any]],
    provenance: Mapping[str, Any],
) -> dict[tuple[str, str], ConsumedField]:
    if provenance.get("run_id") != manifest.get("run_id"):
        raise SnapshotConsumerError("provenance run_id mismatch")
    raw_fields = provenance.get("fields")
    if not isinstance(raw_fields, list):
        raise SnapshotConsumerError("provenance.fields must be a list")

    built: dict[tuple[str, str], ConsumedField] = {}
    for item in raw_fields:
        if not isinstance(item, Mapping):
            raise SnapshotConsumerError("provenance field must be an object")
        raw_ticker = item.get("ticker")
        field = item.get("field")
        if not isinstance(raw_ticker, str) or not isinstance(field, str):
            raise SnapshotConsumerError("provenance field identity is invalid")
        try:
            ticker = canonical_ticker(raw_ticker)
        except ValueError as exc:
            raise SnapshotConsumerError(
                f"invalid provenance ticker identity: {raw_ticker!r}"
            ) from exc
        if ticker != raw_ticker:
            raise SnapshotConsumerError(
                f"provenance ticker identity is not canonical: {raw_ticker!r}"
            )
        if ticker not in records or field not in records[ticker]:
            raise SnapshotConsumerError(
                f"provenance field identity mismatch: {ticker}.{field}"
            )
        key = (ticker, field)
        if key in built:
            raise SnapshotConsumerError(f"duplicate provenance field: {ticker}.{field}")

        status = str(item.get("status") or "not_evaluated")
        eligibility = str(item.get("eligibility") or "not_qualified")
        freshness = item.get("freshness_status")
        reason = item.get("reason") or item.get("canonical_reason")
        snapshot_consumable = item.get("canonical_consumable") is True
        is_available = (
            status == "available"
            and eligibility == "production_eligible"
            and snapshot_consumable
            and freshness == "fresh"
        )
        record_value = records[ticker][field]
        if snapshot_consumable:
            if item.get("value") is None:
                raise SnapshotConsumerError(
                    f"available field value is missing: {ticker}.{field}"
                )
            if record_value != item.get("value"):
                raise SnapshotConsumerError(
                    f"records/provenance value mismatch: {ticker}.{field}"
                )
        elif record_value is not None:
            raise SnapshotConsumerError(
                f"unavailable field has a non-null record value: {ticker}.{field}"
            )
        value = _freeze(record_value) if is_available else None
        if status in _UNAVAILABLE_STATUSES or not is_available:
            value = None
        built[key] = ConsumedField(
            value=value,
            status=status,
            eligibility=eligibility,
            reason=reason,
            provenance=_freeze(item),
            as_of=item.get("as_of"),
            freshness=freshness,
        )
    record_keys = {
        (ticker, field)
        for ticker, values in records.items()
        for field in values
    }
    if set(built) != record_keys:
        raise SnapshotConsumerError(
            "records/provenance field identity mismatch"
        )
    return built


def _canonical_tickers(tickers: Sequence[str]) -> list[str]:
    try:
        return sorted({canonical_ticker(ticker) for ticker in tickers})
    except ValueError as exc:
        raise SnapshotConsumerError("invalid expected ticker identity") from exc


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value
