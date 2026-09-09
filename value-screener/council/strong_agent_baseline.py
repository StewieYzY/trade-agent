"""M2.1 strong single-agent baseline records and comparisons.

The baseline wraps the existing M0.2 Thesis draft boundary.  It does not
implement another prompt, provider client, dossier validator, or diagnostic
validator.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from council.thesis_draft import (
    THESIS_DRAFT_INPUT_SCHEMA_VERSION,
    THESIS_DRAFT_PROMPT_VERSION,
    ThesisDraftInput,
    ThesisDraftInputError,
    run_strong_agent_thesis_draft,
    validate_thesis_draft_artifact,
)
from data.lib.identity import canonical_ticker


BASELINE_INPUT_SCHEMA_VERSION = "g2-strong-agent-baseline-input-v1"
INPUT_ARTIFACT_TYPE = "m0_strong_agent_thesis_draft_input"
BASELINE_RECORD_SCHEMA_VERSION = "g2-strong-agent-baseline-record-v1"
STABLE_RECORD_FIELDS = (
    "canonical_ticker",
    "run_id",
    "baseline_input_digest",
    "diagnostic_digest",
    "dossier_digest",
    "input_digest",
    "prompt_version",
    "profile_version",
    "model",
    "reasoning_level",
    "budget",
    "input_artifact_identity",
)
ALLOWED_DRIFT_FIELDS = (
    "output_digest",
    "thesis_draft_artifact_digest",
    "quality_status",
    "execution_status",
    "failure_kind",
    "status_reasons",
    "usage",
    "agent_signal",
    "agent_out_of_circle",
)


class StrongAgentBaselineError(ValueError):
    """Raised when a baseline input or artifact cannot be trusted."""


@dataclass(frozen=True)
class StrongAgentBaselineInput:
    canonical_ticker: str
    run_id: str
    attempt_index: int
    diagnostic_digest: str
    dossier_digest: str
    input_digest: str
    prompt_version: str
    profile_version: str
    model: str
    reasoning_level: str
    budget: dict[str, Any]
    input_artifact_identity: dict[str, Any]
    thesis_draft_input: dict[str, Any]
    baseline_input_digest: str
    attempt_id: str


@dataclass(frozen=True)
class StrongAgentBaselineArtifacts:
    record_path: Path
    thesis_json_path: Path
    thesis_markdown_path: Path


@dataclass(frozen=True)
class BaselineComparisonArtifacts:
    json_path: Path
    markdown_path: Path


def validate_strong_agent_baseline_input(
    value: Mapping[str, Any],
) -> StrongAgentBaselineInput:
    """Validate fixed baseline identity while delegating M0.2 validation."""
    if not isinstance(value, Mapping):
        raise StrongAgentBaselineError("baseline input must be a mapping")
    allowed = {
        "schema_version",
        "canonical_ticker",
        "run_id",
        "attempt_index",
        "diagnostic_digest",
        "dossier_digest",
        "input_digest",
        "prompt_version",
        "profile_version",
        "model",
        "reasoning_level",
        "budget",
        "input_artifact_identity",
        "thesis_draft_input",
    }
    unknown = sorted(set(value) - allowed)
    missing = sorted(allowed - set(value))
    if missing:
        raise StrongAgentBaselineError(f"baseline input missing fields: {missing}")
    if unknown:
        raise StrongAgentBaselineError(
            f"baseline input contains unknown fields: {unknown}"
        )
    if value["schema_version"] != BASELINE_INPUT_SCHEMA_VERSION:
        raise StrongAgentBaselineError("unsupported baseline input schema_version")

    attempt_index = value["attempt_index"]
    if (
        isinstance(attempt_index, bool)
        or not isinstance(attempt_index, int)
        or attempt_index < 1
    ):
        raise StrongAgentBaselineError("attempt_index must be a positive integer")

    thesis_payload = _required_mapping(
        "thesis_draft_input", value["thesis_draft_input"]
    )
    try:
        thesis_input = ThesisDraftInput.from_dict(thesis_payload)
    except ThesisDraftInputError as exc:
        raise StrongAgentBaselineError(
            f"bound M0.2 input is invalid: {exc}"
        ) from exc

    model = _required_text("model", value["model"])
    reasoning_level = _required_text("reasoning_level", value["reasoning_level"])
    if reasoning_level != "heavy":
        raise StrongAgentBaselineError("reasoning_level must be heavy")
    if value["prompt_version"] != THESIS_DRAFT_PROMPT_VERSION:
        raise StrongAgentBaselineError("prompt_version does not match M0.2")

    input_digest = _sha256(thesis_payload)
    dossier_digest = _sha256(thesis_payload["dossier"])
    diagnostic_digest = thesis_payload["diagnostic_artifact"]["diagnostic"][
        "diagnostic_digest"
    ]
    comparisons = (
        ("canonical_ticker", value["canonical_ticker"], thesis_input.canonical_ticker),
        ("run_id", value["run_id"], thesis_input.run_id),
        ("profile_version", value["profile_version"], thesis_input.profile_version),
        ("diagnostic_digest", value["diagnostic_digest"], diagnostic_digest),
        ("dossier_digest", value["dossier_digest"], dossier_digest),
        ("input_digest", value["input_digest"], input_digest),
    )
    for field, actual, expected in comparisons:
        if actual != expected:
            raise StrongAgentBaselineError(
                f"{field} does not match the bound M0.2 input"
            )

    budget = _validate_budget(value["budget"])
    identity = _validate_input_artifact_identity(
        value["input_artifact_identity"],
        expected_digest=input_digest,
    )
    stable_identity = {
        "canonical_ticker": thesis_input.canonical_ticker,
        "run_id": thesis_input.run_id,
        "diagnostic_digest": diagnostic_digest,
        "dossier_digest": dossier_digest,
        "input_digest": input_digest,
        "prompt_version": THESIS_DRAFT_PROMPT_VERSION,
        "profile_version": thesis_input.profile_version,
        "model": model,
        "reasoning_level": reasoning_level,
        "budget": budget,
        "input_artifact_identity": identity,
    }
    baseline_input_digest = _sha256(stable_identity)
    attempt_id = f"{baseline_input_digest[:16]}-attempt-{attempt_index:03d}"
    return StrongAgentBaselineInput(
        canonical_ticker=thesis_input.canonical_ticker,
        run_id=thesis_input.run_id,
        attempt_index=attempt_index,
        diagnostic_digest=diagnostic_digest,
        dossier_digest=dossier_digest,
        input_digest=input_digest,
        prompt_version=THESIS_DRAFT_PROMPT_VERSION,
        profile_version=thesis_input.profile_version,
        model=model,
        reasoning_level=reasoning_level,
        budget=budget,
        input_artifact_identity=identity,
        thesis_draft_input=thesis_payload,
        baseline_input_digest=baseline_input_digest,
        attempt_id=attempt_id,
    )


async def run_strong_agent_baseline(
    value: Mapping[str, Any],
    output_dir: str | Path,
) -> StrongAgentBaselineArtifacts:
    """Run one bound M0.2 attempt and persist its auditable baseline record."""
    try:
        baseline_input = validate_strong_agent_baseline_input(value)
    except (StrongAgentBaselineError, ThesisDraftInputError) as exc:
        safe_identity = _safe_identity_from_raw(value)
        if safe_identity is None:
            raise
        directory = _validate_output_dir(output_dir)
        return _write_structural_failure_record(
            safe_identity,
            directory,
            str(exc),
        )
    directory = _validate_output_dir(output_dir)
    attempt_dir = directory / f"attempt-{baseline_input.attempt_index:03d}"
    try:
        draft_artifacts = await run_strong_agent_thesis_draft(
            baseline_input.thesis_draft_input,
            attempt_dir,
            model=baseline_input.model,
        )
    except ThesisDraftInputError as exc:
        return _write_structural_failure_record(
            baseline_input,
            directory,
            str(exc),
        )
    artifact = json.loads(
        draft_artifacts.json_path.read_text(encoding="utf-8")
    )
    try:
        validated_artifact = validate_thesis_draft_artifact(
            artifact,
            baseline_input.thesis_draft_input,
        )
    except ThesisDraftInputError as exc:
        return _write_structural_failure_record(
            baseline_input,
            directory,
            str(exc),
        )
    record = _build_baseline_record(baseline_input, validated_artifact)
    record_path = attempt_dir / "baseline-record.json"
    _write_json(record_path, record)
    return StrongAgentBaselineArtifacts(
        record_path=record_path,
        thesis_json_path=draft_artifacts.json_path,
        thesis_markdown_path=draft_artifacts.markdown_path,
    )


def _safe_identity_from_raw(value: Any) -> StrongAgentBaselineInput | None:
    if not isinstance(value, Mapping):
        return None
    try:
        ticker = canonical_ticker(value["canonical_ticker"])
        run_id = _safe_leaf("run_id", value["run_id"])
        attempt_index = value["attempt_index"]
        if (
            isinstance(attempt_index, bool)
            or not isinstance(attempt_index, int)
            or attempt_index < 1
        ):
            return None
    except (KeyError, StrongAgentBaselineError, TypeError, ValueError):
        return None
    model = value.get("model")
    model = model.strip() if isinstance(model, str) and model.strip() else None
    prompt_version = value.get("prompt_version")
    profile_version = value.get("profile_version")
    reasoning_level = value.get("reasoning_level")
    input_digest = value.get("input_digest")
    diagnostic_digest = value.get("diagnostic_digest")
    dossier_digest = value.get("dossier_digest")
    budget = (
        dict(value["budget"])
        if isinstance(value.get("budget"), Mapping)
        else {}
    )
    identity = (
        dict(value["input_artifact_identity"])
        if isinstance(value.get("input_artifact_identity"), Mapping)
        else {}
    )
    stable_identity = {
        "canonical_ticker": ticker,
        "run_id": run_id,
        "diagnostic_digest": diagnostic_digest,
        "dossier_digest": dossier_digest,
        "input_digest": input_digest,
        "prompt_version": prompt_version,
        "profile_version": profile_version,
        "model": model,
        "reasoning_level": reasoning_level,
        "budget": budget,
        "input_artifact_identity": identity,
    }
    baseline_digest = _sha256(stable_identity)
    attempt_id = f"{baseline_digest[:16]}-attempt-{attempt_index:03d}"
    return StrongAgentBaselineInput(
        canonical_ticker=ticker,
        run_id=run_id,
        attempt_index=attempt_index,
        diagnostic_digest=diagnostic_digest,
        dossier_digest=dossier_digest,
        input_digest=input_digest,
        prompt_version=prompt_version,
        profile_version=profile_version,
        model=model,
        reasoning_level=reasoning_level,
        budget=budget,
        input_artifact_identity=identity,
        thesis_draft_input={},
        baseline_input_digest=baseline_digest,
        attempt_id=attempt_id,
    )


def _write_structural_failure_record(
    baseline_input: StrongAgentBaselineInput,
    output_dir: Path,
    reason: str,
) -> StrongAgentBaselineArtifacts:
    attempt_dir = output_dir / f"attempt-{baseline_input.attempt_index:03d}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    thesis_json_path = attempt_dir / (
        f"{baseline_input.canonical_ticker}-{baseline_input.run_id}.json"
    )
    thesis_markdown_path = thesis_json_path.with_suffix(".md")
    diagnostic_status = "unknown"
    if isinstance(baseline_input.thesis_draft_input, Mapping):
        artifact = baseline_input.thesis_draft_input.get("diagnostic_artifact")
        diagnostic = artifact.get("diagnostic") if isinstance(artifact, Mapping) else None
        if isinstance(diagnostic, Mapping):
            diagnostic_status = diagnostic.get(
                "calculation_status",
                "unknown",
            )
    record = {
        "record_schema_version": BASELINE_RECORD_SCHEMA_VERSION,
        "artifact_type": "strong_agent_baseline_record",
        "canonical_ticker": baseline_input.canonical_ticker,
        "run_id": baseline_input.run_id,
        "attempt_index": baseline_input.attempt_index,
        "attempt_id": baseline_input.attempt_id,
        "baseline_input_digest": baseline_input.baseline_input_digest,
        "diagnostic_digest": baseline_input.diagnostic_digest,
        "dossier_digest": baseline_input.dossier_digest,
        "input_digest": baseline_input.input_digest,
        "prompt_version": baseline_input.prompt_version,
        "profile_version": baseline_input.profile_version,
        "model": baseline_input.model,
        "reasoning_level": baseline_input.reasoning_level,
        "budget": baseline_input.budget,
        "input_artifact_identity": baseline_input.input_artifact_identity,
        "engineering_status": "experiment_recorded",
        "provider_call_count": 0,
        "usage": {},
        "quality_status": "failed",
        "execution_status": "failed",
        "diagnostic_status": diagnostic_status,
        "agent_signal": None,
        "agent_out_of_circle": None,
        "failure_kind": "structural",
        "status_reasons": [reason],
        "output_digest": None,
        "thesis_draft_artifact_digest": None,
        "capability_status": "not_evidence",
        "gate_status": "not_passed",
    }
    record["record_digest"] = compute_baseline_record_digest(record)
    record_path = attempt_dir / "baseline-record.json"
    _write_json(record_path, record)
    return StrongAgentBaselineArtifacts(
        record_path=record_path,
        thesis_json_path=thesis_json_path,
        thesis_markdown_path=thesis_markdown_path,
    )


def _build_baseline_record(
    baseline_input: StrongAgentBaselineInput,
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    output = artifact["agent_output"]
    usage = _normalize_usage(artifact.get("usage"))
    failure_kind = artifact.get("failure_kind")
    diagnostic_status = artifact["diagnostic_status"]
    skipped = output.get("signal") == "skip" or output.get("out_of_circle") is True
    if failure_kind or artifact["quality_status"] == "failed":
        execution_status = "failed"
    elif skipped:
        execution_status = "skipped"
    else:
        execution_status = "completed"
    reasons = list(artifact.get("quality_reasons") or [])
    if skipped:
        reasons.extend(output.get("risks") or [])
    if _usage_exceeds_budget(usage, baseline_input.budget):
        reasons.append("usage exceeded fixed baseline budget")
        if execution_status != "failed":
            execution_status = "degraded"
    record = {
        "record_schema_version": BASELINE_RECORD_SCHEMA_VERSION,
        "artifact_type": "strong_agent_baseline_record",
        "canonical_ticker": baseline_input.canonical_ticker,
        "run_id": baseline_input.run_id,
        "attempt_index": baseline_input.attempt_index,
        "attempt_id": baseline_input.attempt_id,
        "baseline_input_digest": baseline_input.baseline_input_digest,
        "diagnostic_digest": baseline_input.diagnostic_digest,
        "dossier_digest": baseline_input.dossier_digest,
        "input_digest": baseline_input.input_digest,
        "prompt_version": baseline_input.prompt_version,
        "profile_version": baseline_input.profile_version,
        "model": baseline_input.model,
        "reasoning_level": baseline_input.reasoning_level,
        "budget": baseline_input.budget,
        "input_artifact_identity": baseline_input.input_artifact_identity,
        "engineering_status": "experiment_recorded",
        "provider_call_count": 1,
        "usage": usage,
        "quality_status": artifact["quality_status"],
        "execution_status": execution_status,
        "diagnostic_status": diagnostic_status,
        "agent_signal": output.get("signal"),
        "agent_out_of_circle": output.get("out_of_circle"),
        "failure_kind": failure_kind,
        "status_reasons": _unique_strings(reasons),
        "output_digest": artifact.get("response_digest"),
        "thesis_draft_artifact_digest": artifact.get("artifact_digest"),
        "capability_status": "not_evidence",
        "gate_status": "not_passed",
    }
    record["record_digest"] = _sha256(record)
    return record


def compute_baseline_record_digest(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise StrongAgentBaselineError("baseline record must be a mapping")
    payload = dict(value)
    payload.pop("record_digest", None)
    return _sha256(payload)


def validate_baseline_record(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise StrongAgentBaselineError("baseline record must be a mapping")
    required = {
        "record_schema_version",
        "artifact_type",
        "canonical_ticker",
        "run_id",
        "attempt_index",
        "attempt_id",
        "baseline_input_digest",
        "diagnostic_digest",
        "dossier_digest",
        "input_digest",
        "prompt_version",
        "profile_version",
        "model",
        "reasoning_level",
        "budget",
        "input_artifact_identity",
        "engineering_status",
        "provider_call_count",
        "usage",
        "quality_status",
        "execution_status",
        "diagnostic_status",
        "agent_signal",
        "agent_out_of_circle",
        "failure_kind",
        "status_reasons",
        "output_digest",
        "thesis_draft_artifact_digest",
        "capability_status",
        "gate_status",
        "record_digest",
    }
    missing = sorted(required - set(value))
    if missing:
        raise StrongAgentBaselineError(
            f"baseline record missing fields: {missing}"
        )
    if value["record_schema_version"] != BASELINE_RECORD_SCHEMA_VERSION:
        raise StrongAgentBaselineError("unsupported baseline record schema_version")
    if value["artifact_type"] != "strong_agent_baseline_record":
        raise StrongAgentBaselineError("invalid baseline record artifact_type")
    if value["capability_status"] != "not_evidence":
        raise StrongAgentBaselineError(
            "baseline record must retain capability_status=not_evidence"
        )
    if value["gate_status"] != "not_passed":
        raise StrongAgentBaselineError(
            "baseline record must retain gate_status=not_passed"
        )
    attempt_index = value["attempt_index"]
    if (
        isinstance(attempt_index, bool)
        or not isinstance(attempt_index, int)
        or attempt_index < 1
    ):
        raise StrongAgentBaselineError("baseline record attempt_index is invalid")
    expected_attempt_id = (
        f"{value['baseline_input_digest'][:16]}-attempt-{attempt_index:03d}"
    )
    if value["attempt_id"] != expected_attempt_id:
        raise StrongAgentBaselineError("baseline record attempt_id mismatch")
    if value["engineering_status"] != "experiment_recorded":
        raise StrongAgentBaselineError(
            "baseline record must retain engineering_status=experiment_recorded"
        )
    if value["record_digest"] != compute_baseline_record_digest(value):
        raise StrongAgentBaselineError("baseline record digest mismatch")
    return dict(value)


def compare_strong_agent_baseline_records(
    records: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare two or more records without invoking M0.2 or a provider."""
    if not isinstance(records, list) or len(records) < 2:
        raise StrongAgentBaselineError(
            "at least two baseline records are required for comparison"
        )
    structural_failures: list[str] = []
    validated: list[dict[str, Any]] = []
    for record in records:
        try:
            validated.append(validate_baseline_record(record))
        except StrongAgentBaselineError as exc:
            structural_failures.append(str(exc))
    if structural_failures:
        comparison = _comparison_payload(
            records=validated,
            structural_failures=structural_failures,
        )
        comparison["comparison_status"] = "structural_failure"
        comparison["comparison_digest"] = _sha256(comparison)
        return comparison

    validated.sort(key=lambda item: item["attempt_index"])
    seen: set[int] = set()
    for record in validated:
        index = record["attempt_index"]
        if index in seen:
            structural_failures.append(f"duplicate attempt_index: {index}")
        seen.add(index)
    first = validated[0]
    for record in validated[1:]:
        for field in STABLE_RECORD_FIELDS:
            if record[field] != first[field]:
                structural_failures.append(f"stable field mismatch: {field}")

    output_changes = [
        {
            "attempt_index": previous["attempt_index"],
            "from": previous["output_digest"],
            "to": current["output_digest"],
        }
        for previous, current in zip(validated, validated[1:])
        if previous["output_digest"] != current["output_digest"]
    ]
    quality_changes = [
        {
            "from_attempt_index": previous["attempt_index"],
            "to_attempt_index": current["attempt_index"],
            "from": previous["quality_status"],
            "to": current["quality_status"],
        }
        for previous, current in zip(validated, validated[1:])
        if previous["quality_status"] != current["quality_status"]
    ]
    usage_deltas = _usage_deltas(validated[0]["usage"], validated[-1]["usage"])
    comparison = _comparison_payload(
        records=validated,
        structural_failures=sorted(set(structural_failures)),
    )
    comparison.update(
        {
            "output_digest_changes": output_changes,
            "quality_changes": quality_changes,
            "usage_deltas": usage_deltas,
        }
    )
    if comparison["structural_failures"]:
        comparison["comparison_status"] = "structural_failure"
    elif output_changes or quality_changes or any(usage_deltas.values()):
        comparison["comparison_status"] = "drifted"
    else:
        comparison["comparison_status"] = "stable"
    comparison["comparison_digest"] = _sha256(comparison)
    return comparison


def _comparison_payload(
    *,
    records: list[dict[str, Any]],
    structural_failures: list[str],
) -> dict[str, Any]:
    stable_results = {}
    if records:
        first = records[0]
        for field in STABLE_RECORD_FIELDS:
            stable_results[field] = all(
                record.get(field) == first.get(field) for record in records
            )
    return {
        "comparison_schema_version": "g2-strong-agent-baseline-comparison-v1",
        "artifact_type": "strong_agent_baseline_comparison",
        "attempt_count": len(records),
        "attempt_ids": [record["attempt_id"] for record in records],
        "attempt_indices": [record["attempt_index"] for record in records],
        "stable_field_results": stable_results,
        "stable_fields": list(STABLE_RECORD_FIELDS),
        "allowed_drift_fields": list(ALLOWED_DRIFT_FIELDS),
        "structural_failures": sorted(set(structural_failures)),
        "output_digest_changes": [],
        "quality_changes": [],
        "usage_deltas": {},
        "capability_status": "not_evidence",
        "gate_status": "not_passed",
    }


def _usage_deltas(
    first: Mapping[str, Any],
    last: Mapping[str, Any],
) -> dict[str, int | float]:
    deltas: dict[str, int | float] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost"):
        before = first.get(key, 0)
        after = last.get(key, 0)
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta = after - before
            deltas[key] = round(delta, 12) if key == "cost" else delta
    return deltas


def render_baseline_record_json(value: Mapping[str, Any]) -> str:
    record = validate_baseline_record(value)
    return _deterministic_json(record)


def render_baseline_record_markdown(value: Mapping[str, Any]) -> str:
    record = validate_baseline_record(value)
    reasons = record.get("status_reasons") or []
    lines = [
        f"# Strong-agent baseline record — {record['canonical_ticker']}",
        "",
        "> M2.1 engineering experiment artifact; not G2 Capability Gate evidence.",
        "",
        "## Run identity",
        "",
        f"- run_id: `{record['run_id']}`",
        f"- attempt_index: `{record['attempt_index']}`",
        f"- attempt_id: `{record['attempt_id']}`",
        f"- baseline_input_digest: `{record['baseline_input_digest']}`",
        f"- diagnostic_digest: `{record['diagnostic_digest']}`",
        f"- dossier_digest: `{record['dossier_digest']}`",
        f"- input_digest: `{record['input_digest']}`",
        f"- model: `{record['model']}`",
        f"- reasoning_level: `{record['reasoning_level']}`",
        "",
        "## Outcome",
        "",
        f"- execution_status: `{record['execution_status']}`",
        f"- quality_status: `{record['quality_status']}`",
        f"- diagnostic_status: `{record['diagnostic_status']}`",
        f"- agent_signal: `{record['agent_signal']}`",
        f"- agent_out_of_circle: `{record['agent_out_of_circle']}`",
        f"- failure_kind: `{record['failure_kind']}`",
        f"- provider_call_count: `{record['provider_call_count']}`",
        "",
        "## Budget and usage",
        "",
        f"- budget: `{record['budget']}`",
        f"- usage: `{record['usage']}`",
        "",
        "## Reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in reasons)
    if not reasons:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Digests",
            "",
            f"- output_digest: `{record['output_digest']}`",
            f"- thesis_draft_artifact_digest: `{record['thesis_draft_artifact_digest']}`",
            f"- record_digest: `{record['record_digest']}`",
            "",
            "## Status boundary",
            "",
            f"- engineering_status: `{record['engineering_status']}`",
            f"- capability_status: `{record['capability_status']}`",
            f"- gate_status: `{record['gate_status']}`",
            "- 本记录不证明 G2 Capability Gate 通过，也不包含真实用户复核结论。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_baseline_comparison_json(value: Mapping[str, Any]) -> str:
    comparison = _validate_comparison_mapping(value)
    return _deterministic_json(comparison)


def render_baseline_comparison_markdown(value: Mapping[str, Any]) -> str:
    comparison = _validate_comparison_mapping(value)
    lines = [
        "# Strong-agent baseline comparison",
        "",
        "> M2.1 engineering experiment artifact; 不是 G2 Capability Gate evidence。",
        "",
        "## Summary",
        "",
        f"- comparison_status: `{comparison['comparison_status']}`",
        f"- attempt_count: `{comparison['attempt_count']}`",
        f"- attempt_indices: `{comparison['attempt_indices']}`",
        f"- comparison_digest: `{comparison['comparison_digest']}`",
        "",
        "## Stable fields",
        "",
    ]
    for field, result in comparison["stable_field_results"].items():
        lines.append(f"- `{field}`: `{result}`")
    lines.extend(["", "## Allowed drift", ""])
    lines.extend(f"- `{field}`" for field in comparison["allowed_drift_fields"])
    lines.extend(["", "## Output digest changes", ""])
    if comparison["output_digest_changes"]:
        lines.extend(
            f"- attempt {item['attempt_index']}: `{item['from']}` → `{item['to']}`"
            for item in comparison["output_digest_changes"]
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Quality changes", ""])
    if comparison["quality_changes"]:
        lines.extend(
            f"- attempt {item['from_attempt_index']} → {item['to_attempt_index']}: "
            f"`{item['from']}` → `{item['to']}`"
            for item in comparison["quality_changes"]
        )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Usage deltas",
            "",
            f"- `{comparison['usage_deltas']}`",
            "",
            "## Structural failures",
            "",
        ]
    )
    if comparison["structural_failures"]:
        lines.extend(f"- {item}" for item in comparison["structural_failures"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Status boundary",
            "",
            f"- capability_status: `{comparison['capability_status']}`",
            f"- gate_status: `{comparison['gate_status']}`",
            "- 本比较不证明 G2 Capability Gate 通过，也不替代真实模型运行或用户盲评。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_baseline_comparison(
    records: list[Mapping[str, Any]],
    output_dir: str | Path,
) -> BaselineComparisonArtifacts:
    comparison = compare_strong_agent_baseline_records(records)
    directory = _validate_output_dir(output_dir)
    json_path = directory / "comparison.json"
    markdown_path = directory / "comparison.md"
    json_path.write_text(
        render_baseline_comparison_json(comparison),
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_baseline_comparison_markdown(comparison),
        encoding="utf-8",
    )
    return BaselineComparisonArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
    )


def _validate_comparison_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise StrongAgentBaselineError("comparison must be a mapping")
    required = {
        "comparison_schema_version",
        "artifact_type",
        "comparison_status",
        "attempt_count",
        "attempt_ids",
        "attempt_indices",
        "stable_field_results",
        "stable_fields",
        "allowed_drift_fields",
        "structural_failures",
        "output_digest_changes",
        "quality_changes",
        "usage_deltas",
        "capability_status",
        "gate_status",
        "comparison_digest",
    }
    missing = sorted(required - set(value))
    if missing:
        raise StrongAgentBaselineError(
            f"comparison missing fields: {missing}"
        )
    if value["comparison_schema_version"] != (
        "g2-strong-agent-baseline-comparison-v1"
    ):
        raise StrongAgentBaselineError("unsupported comparison schema_version")
    if value["artifact_type"] != "strong_agent_baseline_comparison":
        raise StrongAgentBaselineError("invalid comparison artifact_type")
    if value["comparison_status"] not in {
        "stable",
        "drifted",
        "structural_failure",
    }:
        raise StrongAgentBaselineError("invalid comparison_status")
    if value["capability_status"] != "not_evidence":
        raise StrongAgentBaselineError(
            "comparison must retain capability_status=not_evidence"
        )
    if value["gate_status"] != "not_passed":
        raise StrongAgentBaselineError(
            "comparison must retain gate_status=not_passed"
        )
    payload = dict(value)
    digest = payload.pop("comparison_digest", None)
    if digest != _sha256(payload):
        raise StrongAgentBaselineError("comparison digest mismatch")
    return dict(value)


def _deterministic_json(value: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )


def _normalize_usage(value: Any) -> dict[str, Any]:
    usage = dict(value) if isinstance(value, Mapping) else {}
    keys = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost",
        "currency",
    )
    return {key: usage.get(key) for key in keys}


def _usage_exceeds_budget(
    usage: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> bool:
    total_tokens = usage.get("total_tokens")
    if isinstance(total_tokens, (int, float)) and total_tokens > budget["max_total_tokens"]:
        return True
    max_cost = budget.get("max_cost")
    cost = usage.get("cost")
    return (
        max_cost is not None
        and isinstance(cost, (int, float))
        and cost > max_cost
    )


def _validate_output_dir(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise StrongAgentBaselineError("output_dir is required")
    directory = Path(value)
    if directory.exists() and not directory.is_dir():
        raise StrongAgentBaselineError("output_dir must be a directory")
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StrongAgentBaselineError("output_dir is not writable") from exc
    return directory


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _unique_strings(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(value for value in values if isinstance(value, str) and value))


def _validate_budget(value: Any) -> dict[str, Any]:
    budget = _required_mapping("budget", value)
    allowed = {"max_total_tokens", "max_cost", "currency"}
    unknown = set(budget) - allowed
    if unknown or "max_total_tokens" not in budget:
        raise StrongAgentBaselineError(
            "budget must contain max_total_tokens and no unknown fields"
        )
    max_tokens = budget["max_total_tokens"]
    if (
        isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or max_tokens < 1
    ):
        raise StrongAgentBaselineError(
            "budget.max_total_tokens must be a positive integer"
        )
    max_cost = budget.get("max_cost")
    if max_cost is not None and (
        isinstance(max_cost, bool)
        or not isinstance(max_cost, (int, float))
        or max_cost < 0
    ):
        raise StrongAgentBaselineError(
            "budget.max_cost must be null or a non-negative number"
        )
    currency = budget.get("currency")
    if max_cost is not None:
        currency = _required_text("budget.currency", currency)
    elif currency is not None:
        currency = _required_text("budget.currency", currency)
    return {
        "max_total_tokens": max_tokens,
        "max_cost": max_cost,
        "currency": currency,
    }


def _validate_input_artifact_identity(
    value: Any,
    *,
    expected_digest: str,
) -> dict[str, Any]:
    identity = _required_mapping("input_artifact_identity", value)
    expected = {
        "artifact_type": INPUT_ARTIFACT_TYPE,
        "schema_version": THESIS_DRAFT_INPUT_SCHEMA_VERSION,
        "artifact_digest": expected_digest,
    }
    if identity != expected:
        raise StrongAgentBaselineError(
            "input_artifact_identity does not match the bound M0.2 input"
        )
    return expected


def _required_mapping(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise StrongAgentBaselineError(f"{name} must be a non-empty mapping")
    return dict(value)


def _required_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrongAgentBaselineError(f"{name} is required")
    return value.strip()


def _safe_leaf(name: str, value: Any) -> str:
    text = _required_text(name, value)
    path = Path(text)
    if (
        text in {".", ".."}
        or path.is_absolute()
        or "/" in text
        or "\\" in text
        or path.name != text
    ):
        raise StrongAgentBaselineError(
            f"{name} must be a non-empty relative path leaf"
        )
    return text


def _sha256(value: Any) -> str:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise StrongAgentBaselineError(
            "baseline value is not strict JSON"
        ) from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
