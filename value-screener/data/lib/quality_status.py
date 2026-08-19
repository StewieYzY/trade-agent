"""G2 run completeness and quality-status contract.

This module owns only run-scoped status persistence and cache eligibility.
It does not decide the G2 capability verdict or mutate debate/watchlist data.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace as dataclass_replace
from pathlib import Path
from typing import Any

from data.lib.identity import canonical_ticker

QUALITY_STATUS_SCHEMA_VERSION = "g2-run-quality-status-v1"
QUALITY_STATUSES = (
    "complete",
    "warning",
    "failed",
    "incomplete",
    "runtime_degraded",
    "da_skipped",
)
QUALITY_STAGES = (
    "r1",
    "r2",
    "da",
    "synthesizer",
    "final_validation",
    "agent",
    "fact_check",
    "synthesis",
)
QUALITY_EXECUTION_MODES = ("single_agent", "council", "fallback")
REQUIRED_STAGES = {
    "single_agent": frozenset(("r1", "final_validation")),
    "council": frozenset(("r1", "r2", "da", "synthesizer", "final_validation")),
    "fallback": frozenset(("agent", "fact_check", "synthesis", "final_validation")),
}
FINAL_QUALITY_GATES = ("passed", "warning", "failed", "not_run")
STATUS_SAFETY_RANK = {
    "complete": 0,
    "warning": 1,
    "da_skipped": 2,
    "runtime_degraded": 3,
    "incomplete": 4,
    "failed": 5,
}


class QualityStatusError(ValueError):
    """Raised when a G2 run-quality record is not trustworthy."""


def _required_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualityStatusError(f"{name} is required")
    return value.strip()


def _validate_run_id(value: Any) -> str:
    run_id = _required_text("run_id", value)
    if run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise QualityStatusError("run_id must be a relative path leaf")
    return run_id


def _validate_reasons(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise QualityStatusError("reasons must be a list")
    reasons = tuple(_required_text("reason", item) for item in value)
    return reasons


def _validate_stages(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise QualityStatusError("completed_stages must be a list")
    stages = tuple(value)
    if any(stage not in QUALITY_STAGES for stage in stages):
        raise QualityStatusError("completed_stages contains an unknown stage")
    if len(set(stages)) != len(stages):
        raise QualityStatusError("completed_stages contains duplicates")
    return stages


@dataclass(frozen=True)
class RunQualityRecord:
    canonical_ticker: str
    run_id: str
    status: str
    reasons: tuple[str, ...] = ()
    completed_stages: tuple[str, ...] = ()
    final_quality_gate: str = "not_run"
    artifact_path: str | None = None
    execution_mode: str = "council"
    schema_version: str = QUALITY_STATUS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            canonical = canonical_ticker(self.canonical_ticker)
        except (TypeError, ValueError) as exc:
            raise QualityStatusError("canonical_ticker is invalid") from exc
        if canonical != self.canonical_ticker:
            raise QualityStatusError("canonical_ticker must be canonical")
        _validate_run_id(self.run_id)
        if self.execution_mode not in QUALITY_EXECUTION_MODES:
            raise QualityStatusError(
                f"unknown execution_mode: {self.execution_mode!r}"
            )
        if self.status not in QUALITY_STATUSES:
            raise QualityStatusError(f"unknown quality status: {self.status!r}")
        if self.final_quality_gate not in FINAL_QUALITY_GATES:
            raise QualityStatusError(
                f"unknown final_quality_gate: {self.final_quality_gate!r}"
            )
        reasons = _validate_reasons(self.reasons)
        stages = _validate_stages(self.completed_stages)
        if self.artifact_path is not None and not isinstance(self.artifact_path, str):
            raise QualityStatusError("artifact_path must be a string or null")
        if self.status == "complete" and reasons:
            raise QualityStatusError(
                "complete status requires empty reasons"
            )
        if self.status == "complete" and self.final_quality_gate != "passed":
            raise QualityStatusError(
                "complete status requires final_quality_gate='passed'"
            )
        if self.status == "complete" and not REQUIRED_STAGES[self.execution_mode].issubset(
            stages
        ):
            raise QualityStatusError(
                "complete status requires all execution-mode stages in completed_stages"
            )
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "completed_stages", stages)
        if self.schema_version != QUALITY_STATUS_SCHEMA_VERSION:
            raise QualityStatusError("unsupported quality status schema_version")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["completed_stages"] = list(self.completed_stages)
        return payload


def is_success_cache_eligible(record: RunQualityRecord) -> bool:
    """Return whether a record can be used as a clean success cache entry."""
    return (
        isinstance(record, RunQualityRecord)
        and record.execution_mode != "fallback"
        and record.status == "complete"
        and record.final_quality_gate == "passed"
    )


def quality_record_path(
    base_dir: str | Path,
    canonical_ticker_value: str,
    run_id: str,
) -> Path:
    try:
        canonical = canonical_ticker(canonical_ticker_value)
    except (TypeError, ValueError) as exc:
        raise QualityStatusError("canonical_ticker is invalid") from exc
    safe_run_id = _validate_run_id(run_id)
    return Path(base_dir) / "quality_status" / canonical / safe_run_id / "record.json"


def write_quality_record(
    base_dir: str | Path,
    record: RunQualityRecord,
) -> Path:
    path = quality_record_path(base_dir, record.canonical_ticker, record.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise FileExistsError(f"refusing to overwrite quality record: {path}") from exc
    return path


def replace_quality_record(
    base_dir: str | Path,
    record: RunQualityRecord,
) -> Path:
    """Atomically update a record already created for the same run."""
    path = quality_record_path(base_dir, record.canonical_ticker, record.run_id)
    if not path.exists():
        raise FileNotFoundError(f"quality record does not exist: {path}")
    existing = read_quality_record(
        base_dir,
        record.canonical_ticker,
        record.run_id,
    )
    if (
        existing is not None
        and STATUS_SAFETY_RANK[record.status] < STATUS_SAFETY_RANK[existing.status]
    ):
        raise QualityStatusError(
            f"refusing status upgrade from {existing.status} to {record.status}"
        )
    if existing is not None:
        record = dataclass_replace(
            record,
            reasons=tuple(dict.fromkeys((*existing.reasons, *record.reasons))),
        )
    temp_path = path.with_suffix(".tmp")
    payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
    try:
        with temp_path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise
    return path


def read_quality_record(
    base_dir: str | Path,
    canonical_ticker_value: str,
    run_id: str,
) -> RunQualityRecord | None:
    canonical = canonical_ticker(canonical_ticker_value)
    safe_run_id = _validate_run_id(run_id)
    path = quality_record_path(base_dir, canonical, safe_run_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = RunQualityRecord(
            canonical_ticker=payload["canonical_ticker"],
            run_id=payload["run_id"],
            status=payload["status"],
            reasons=payload.get("reasons", ()),
            completed_stages=payload.get("completed_stages", ()),
            final_quality_gate=payload.get("final_quality_gate", "not_run"),
            artifact_path=payload.get("artifact_path"),
            execution_mode=payload.get("execution_mode", "council"),
            schema_version=payload.get("schema_version", ""),
        )
        if (
            record.canonical_ticker != canonical
            or record.run_id != safe_run_id
        ):
            raise QualityStatusError(
                "quality record payload identity does not match requested path"
            )
        return record
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise QualityStatusError(f"invalid quality record: {path}") from exc
