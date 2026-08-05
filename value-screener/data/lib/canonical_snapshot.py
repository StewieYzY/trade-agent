"""Immutable canonical snapshot boundary.

该模块只消费 provider contract evidence，不调用 provider、不修改 legacy cache，
也不决定任何 provider 是否 production eligible。
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .identity import canonical_ticker
from .provenance import detect_conflicts, validate_field_evidence


class SnapshotError(ValueError):
    """Snapshot input or output violates the immutable boundary."""


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_run_id(run_id: str | None) -> str:
    value = run_id or str(uuid.uuid4())
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or Path(value).is_absolute()
        or "/" in value
        or "\\" in value
    ):
        raise SnapshotError("run_id must be a non-empty relative path leaf")
    return value


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _source_set_hash(
    evidence: Iterable[Mapping[str, Any]],
    *,
    freshness_seconds: int | None = None,
    freshness_evaluated_at: str | None = None,
) -> str:
    identity = [
        {
            "ticker": item.get("ticker"),
            "field": item.get("field"),
            "provider_family": item.get("provider_family"),
            "provider": item.get("provider"),
            "method": item.get("method"),
            "response_hash": item.get("response_hash"),
            "status": item.get("status"),
            "eligibility": item.get("eligibility", "not_qualified"),
            "freshness_status": item.get("freshness_status"),
        }
        for item in evidence
    ]
    return _hash(
        {
            "fields": sorted(
                identity,
                key=lambda item: json.dumps(item, sort_keys=True),
            ),
            "freshness_seconds": freshness_seconds,
            "freshness_evaluated_at": freshness_evaluated_at,
        }
    )


def _ticker_set_hash(tickers: Iterable[str]) -> str:
    canonical = sorted(canonical_ticker(ticker) for ticker in tickers)
    return _hash(canonical)


def _status_summary(evidence: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in evidence:
        status = str(item.get("status"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def build_snapshot(
    evidence: Iterable[Mapping[str, Any]],
    *,
    tickers: Iterable[str],
    plan_version: str,
    run_id: str | None = None,
    as_of: str | None = None,
    freshness_seconds: int | None = None,
    freshness_as_of: datetime | None = None,
) -> dict[str, Any]:
    if freshness_seconds is not None and freshness_seconds < 0:
        raise SnapshotError("freshness_seconds must be non-negative")
    freshness_evaluated_at = (
        freshness_as_of.isoformat()
        if freshness_as_of is not None
        else (
            datetime.now(timezone.utc).isoformat()
            if freshness_seconds is not None
            else None
        )
    )
    freshness_reference = freshness_as_of
    if freshness_reference is None and freshness_seconds is not None:
        freshness_reference = datetime.fromisoformat(freshness_evaluated_at)
    raw_evidence = list(evidence)
    normalized = [
        validate_field_evidence(item, allow_production=True)
        for item in raw_evidence
    ]
    ticker_list = sorted({canonical_ticker(ticker) for ticker in tickers})
    if not ticker_list:
        raise SnapshotError("snapshot ticker set must not be empty")

    conflicts = detect_conflicts(
        [
            item
            for item in raw_evidence
            if item.get("eligibility") == "production_eligible"
        ],
        freshness_seconds=freshness_seconds,
        now=freshness_reference,
        allow_production=True,
    )
    conflict_keys = {
        tuple(conflict["key"][:2])
        for conflict in conflicts
        if "key" in conflict and len(conflict["key"]) >= 2
    }

    records: dict[str, dict[str, Any]] = {ticker: {} for ticker in ticker_list}
    sidecar: list[dict[str, Any]] = []
    for item in normalized:
        ticker = canonical_ticker(item["ticker"])
        if ticker not in records:
            records[ticker] = {}
        key = (ticker, item.get("field"))
        is_eligible = (
            item["status"] == "available"
            and item.get("eligibility") == "production_eligible"
            and item.get("freshness_status") not in {"stale", "unknown"}
            and key not in conflict_keys
        )
        field = str(item["field"])
        if is_eligible:
            records[ticker][field] = item.get("value")
        else:
            records[ticker].setdefault(field, None)
        sidecar.append(
            {
                **item,
                "canonical_consumable": is_eligible,
                "canonical_reason": (
                    None
                    if is_eligible
                    else ("conflict" if key in conflict_keys else "not eligible")
                ),
            }
        )

    safe_id = _safe_run_id(run_id)
    return {
        "run_id": safe_id,
        "plan_version": plan_version,
        "schema_version": "g1-canonical-snapshot-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "ticker_set_hash": _ticker_set_hash(ticker_list),
        "source_set_hash": _source_set_hash(
            normalized,
            freshness_seconds=freshness_seconds,
            freshness_evaluated_at=freshness_evaluated_at,
        ),
        "status_summary": _status_summary(normalized),
        "freshness_evaluated_at": freshness_evaluated_at,
        "conflict_count": len(conflicts),
        "records": records,
        "provenance": sidecar,
        "conflicts": conflicts,
    }


def write_snapshot(
    evidence: Iterable[Mapping[str, Any]],
    *,
    tickers: Iterable[str],
    plan_version: str,
    output_root: str | Path,
    run_id: str | None = None,
    as_of: str | None = None,
    freshness_seconds: int | None = None,
    freshness_as_of: datetime | None = None,
    manifest_extra: Mapping[str, Any] | None = None,
) -> Path:
    snapshot = build_snapshot(
        evidence,
        tickers=tickers,
        plan_version=plan_version,
        run_id=run_id,
        as_of=as_of,
        freshness_seconds=freshness_seconds,
        freshness_as_of=freshness_as_of,
    )
    root = Path(output_root).resolve()
    run_dir = (root / snapshot["run_id"]).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise SnapshotError("snapshot run directory escapes output root") from exc
    if run_dir.exists():
        raise SnapshotError(f"snapshot run already exists: {snapshot['run_id']}")
    run_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        key: snapshot[key]
        for key in (
            "run_id",
            "plan_version",
            "schema_version",
            "generated_at",
            "as_of",
            "ticker_set_hash",
            "source_set_hash",
            "status_summary",
            "freshness_evaluated_at",
            "conflict_count",
        )
    }
    if manifest_extra:
        collisions = set(manifest).intersection(manifest_extra)
        if collisions:
            raise SnapshotError(
                f"manifest extra collides with canonical fields: {sorted(collisions)}"
            )
        manifest.update(manifest_extra)
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "records.json", snapshot["records"])
    _write_json(
        run_dir / "provenance.json",
        {
            "run_id": snapshot["run_id"],
            "fields": snapshot["provenance"],
            "conflicts": snapshot["conflicts"],
        },
    )
    return run_dir


def read_snapshot(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    required = ("manifest.json", "records.json", "provenance.json")
    if not all((root / name).exists() for name in required):
        raise SnapshotError("snapshot run is incomplete")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    records = json.loads((root / "records.json").read_text(encoding="utf-8"))
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    return {"manifest": manifest, "records": records, "provenance": provenance}
