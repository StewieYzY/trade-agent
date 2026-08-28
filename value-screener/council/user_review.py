"""M0.3 单股研究人工复核记录。

该模块只消费已生成的 M0.1 growth diagnostic artifact、M0.2 Thesis draft
artifact 和用户显式填写的复核内容。它不调用 provider、LLM、Council、
DA 或 Synthesizer，也不替用户生成反馈或下一步投资决策。
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from council.schema import AgentOutput, ValidationError
from data.lib.identity import canonical_ticker


USER_REVIEW_INPUT_SCHEMA_VERSION = "m0-single-stock-user-review-input-v1"
USER_REVIEW_ARTIFACT_SCHEMA_VERSION = "m0-single-stock-user-review-v1"
REVIEW_DIMENSIONS = (
    "facts",
    "assumptions",
    "growth_expectation",
    "thesis_draft",
)
REVIEW_CONCLUSION_STATUSES = {
    "accepted",
    "question",
    "problem",
    "not_evaluable",
}
REVIEW_STATUSES = {"template", "completed"}
_DIAGNOSTIC_ARTIFACT_FIELDS = {
    "artifact_type",
    "artifact_schema_version",
    "canonical_ticker",
    "run_id",
    "dossier_snapshot",
    "profile_version",
    "capability_status",
    "gate_status",
    "diagnostic",
    "artifact_digest",
}
_THESIS_ARTIFACT_FIELDS = {
    "artifact_type",
    "artifact_schema_version",
    "canonical_ticker",
    "run_id",
    "dossier_snapshot",
    "profile_version",
    "diagnostic_digest",
    "agent_id",
    "model",
    "prompt_version",
    "input_digest",
    "prompt_digest",
    "response_digest",
    "diagnostic_status",
    "diagnostic",
    "diagnostic_summary",
    "dossier_quality_status",
    "dossier_quality_reasons",
    "agent_output",
    "quality_status",
    "quality_reasons",
    "pending_verification",
    "failure_kind",
    "usage",
    "capability_status",
    "gate_status",
    "artifact_digest",
}


class UserReviewInputError(ValueError):
    """Raised when an M0.3 input or review record cannot be trusted."""


@dataclass(frozen=True)
class UserReviewArtifacts:
    json_path: Path
    markdown_path: Path


def build_user_review_record(input_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an input envelope and build one deterministic review record."""
    validated = _validate_user_review_input(input_payload)
    diagnostic = validated["diagnostic_artifact"]
    thesis = validated["thesis_draft_artifact"]
    user_review = validated["user_review"]
    review_status = user_review["review_status"]

    record = {
        "artifact_type": "m0_single_stock_user_review",
        "artifact_schema_version": USER_REVIEW_ARTIFACT_SCHEMA_VERSION,
        "canonical_ticker": validated["canonical_ticker"],
        "run_id": validated["run_id"],
        "dossier_snapshot": validated["dossier_snapshot"],
        "profile_version": validated["profile_version"],
        "dossier_digest": _sha256(validated["dossier"]),
        "review_status": review_status,
        "user_review_owner": "user",
        "capability_status": (
            "mvp_evidence" if review_status == "completed" else "not_evidence"
        ),
        "gate_status": "not_passed",
        "reviewed_artifacts": {
            "diagnostic": _diagnostic_reference(
                diagnostic,
                validated["artifact_paths"]["diagnostic"],
            ),
            "thesis_draft": _thesis_reference(
                thesis,
                validated["artifact_paths"]["thesis_draft"],
            ),
        },
        "user_review": deepcopy(user_review),
        "input_digest": _sha256(validated),
    }
    record["artifact_digest"] = compute_user_review_artifact_digest(record)
    return record


def write_user_review_record(
    input_payload: Mapping[str, Any],
    output_dir: str | Path,
) -> UserReviewArtifacts:
    """Write a validated review record as deterministic JSON and Markdown."""
    record = build_user_review_record(input_payload)
    directory = _validate_output_dir(output_dir)
    ticker = record["canonical_ticker"]
    run_id = record["run_id"]
    json_path = directory / f"{ticker}-{run_id}.json"
    markdown_path = directory / f"{ticker}-{run_id}.md"
    _write_text(
        json_path,
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )
    _write_text(markdown_path, render_user_review_markdown(record))
    return UserReviewArtifacts(json_path=json_path, markdown_path=markdown_path)


def validate_user_review_record(
    record: Mapping[str, Any],
    input_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a generated record against its original bound input."""
    if not isinstance(record, Mapping):
        raise UserReviewInputError("user review record must be a mapping")
    expected = build_user_review_record(input_payload)
    if dict(record) != expected:
        raise UserReviewInputError(
            "user review record does not match the bound input or digest"
        )
    return deepcopy(dict(record))


def compute_user_review_artifact_digest(record: Mapping[str, Any]) -> str:
    """Compute the deterministic digest excluding the digest field itself."""
    if not isinstance(record, Mapping):
        raise UserReviewInputError("user review record must be a mapping")
    payload = dict(record)
    payload.pop("artifact_digest", None)
    return _sha256(payload)


def render_user_review_markdown(record: Mapping[str, Any]) -> str:
    """Render one deterministic, non-advisory Markdown review record."""
    reviewed = record["reviewed_artifacts"]
    review = record["user_review"]
    lines = [
        f"# 单股研究人工复核记录 — {record['canonical_ticker']}",
        "",
        "> 本记录保存用户填写的人工复核，不是交易指令，也不是正式 G2 Capability Gate evidence。",
        "",
        "## 状态与边界",
        "",
        f"- review_status: `{record['review_status']}`",
        f"- capability_status: `{record['capability_status']}`",
        f"- gate_status: `{record['gate_status']}`",
    ]
    if record["review_status"] == "template":
        lines.append("- M0 product loop = pending user review")
    else:
        lines.append("- M0.3 是 MVP evidence，不是正式 G2 Capability Gate evidence")

    lines.extend(
        [
            "",
            "## 运行身份",
            "",
            f"- canonical_ticker: `{record['canonical_ticker']}`",
            f"- run_id: `{record['run_id']}`",
            f"- dossier_snapshot: `{record['dossier_snapshot']}`",
            f"- profile_version: `{record['profile_version']}`",
            f"- dossier_digest: `{record['dossier_digest']}`",
            f"- input_digest: `{record['input_digest']}`",
            f"- artifact_digest: `{record['artifact_digest']}`",
            "",
            "## 被复核 artifacts",
            "",
        ]
    )
    for name in ("diagnostic", "thesis_draft"):
        artifact = reviewed[name]
        lines.extend(
            [
                f"### {name}",
                "",
                f"- path: `{artifact['path']}`",
                f"- artifact_type: `{artifact['artifact_type']}`",
                f"- artifact_digest: `{artifact['artifact_digest']}`",
                f"- diagnostic_digest: `{artifact['diagnostic_digest']}`",
                f"- canonical_ticker: `{artifact['canonical_ticker']}`",
                f"- run_id: `{artifact['run_id']}`",
                f"- dossier_snapshot: `{artifact['dossier_snapshot']}`",
                f"- profile_version: `{artifact['profile_version']}`",
                f"- quality_status: `{artifact['quality_status']}`",
            ]
        )
        if artifact.get("report_period") is not None:
            lines.append(f"- report_period: `{artifact['report_period']}`")
        if artifact.get("as_of") is not None:
            lines.append(f"- as_of: `{artifact['as_of']}`")
        lines.append("")

    lines.extend(["## 用户复核", ""])
    labels = {
        "facts": "事实",
        "assumptions": "假设",
        "growth_expectation": "成长预期诊断",
        "thesis_draft": "Thesis 草稿",
    }
    for name in REVIEW_DIMENSIONS:
        dimension = review["dimensions"][name]
        lines.extend(
            [
                f"### {labels[name]} (`{name}`)",
                "",
                f"- conclusion_status: `{dimension['conclusion_status']}`",
                "- feedback:",
                "- issues_or_corrections:",
            ]
        )
        lines.insert(
            len(lines) - 1,
            _markdown_user_text(dimension["feedback"])
            if dimension["feedback"]
            else "  （未填写）",
        )
        if dimension["issues_or_corrections"]:
            lines.extend(
                f"  - {_markdown_list_item(item)}"
                for item in dimension["issues_or_corrections"]
            )
        else:
            lines.append("  - （未填写）")
        lines.append("- not_evaluable_reason:")
        lines.append(
            _markdown_user_text(dimension["not_evaluable_reason"])
            if dimension["not_evaluable_reason"]
            else "  （未填写）"
        )
        lines.append("")

    lines.extend(
        [
            "## 用户填写的复核结论",
            "",
            "### 关键问题",
            "",
        ]
    )
    lines.extend(
        f"- {_markdown_list_item(item)}"
        for item in review["key_issues"] or ["（未填写）"]
    )
    lines.extend(["", "### 认可的内容", ""])
    lines.extend(
        f"- {_markdown_list_item(item)}"
        for item in review["accepted_content"] or ["（未填写）"]
    )
    lines.extend(["", "### Residual risk", ""])
    lines.extend(
        f"- {_markdown_list_item(item)}"
        for item in review["residual_risk"] or ["（未填写）"]
    )
    lines.extend(
        [
            "",
            "### 下一步决策（用户填写）",
            "",
            (
                _markdown_user_text(review["next_decision"])
                if review["next_decision"]
                else "（未填写）"
            ),
            "",
            "## 限制",
            "",
            "- 本记录不自动判断用户是否认可，不生成投资建议、目标价、仓位或买卖动作。",
            "- `mvp_evidence` 只表示真实人工复核记录可供 M0 实验使用，不表示 G2 Capability Gate 通过。",
        ]
    )
    return "\n".join(lines) + "\n"


def _validate_user_review_input(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise UserReviewInputError("user review input must be a mapping")
    allowed = {
        "schema_version",
        "canonical_ticker",
        "run_id",
        "dossier_snapshot",
        "profile_version",
        "artifact_paths",
        "diagnostic_artifact",
        "thesis_draft_artifact",
        "dossier",
        "user_review",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise UserReviewInputError(
            f"user review input contains unknown fields: {unknown}"
        )
    try:
        if value["schema_version"] != USER_REVIEW_INPUT_SCHEMA_VERSION:
            raise UserReviewInputError("unsupported user review input schema_version")
        ticker = _canonical_text("canonical_ticker", value["canonical_ticker"])
        if ticker != value["canonical_ticker"]:
            raise UserReviewInputError("canonical_ticker must be canonical")
        run_id = _safe_leaf("run_id", value["run_id"])
        dossier_snapshot = _required_text(
            "dossier_snapshot", value["dossier_snapshot"]
        )
        profile_version = _required_text(
            "profile_version", value["profile_version"]
        )
        paths = _validate_artifact_paths(value["artifact_paths"])
        diagnostic = _required_mapping(
            "diagnostic_artifact", value["diagnostic_artifact"]
        )
        thesis = _required_mapping(
            "thesis_draft_artifact", value["thesis_draft_artifact"]
        )
        dossier = _required_mapping("dossier", value["dossier"])
        user_review = _validate_user_review(value["user_review"])
    except UserReviewInputError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise UserReviewInputError(f"user review input is invalid: {exc}") from exc

    _validate_exact_fields(
        "diagnostic_artifact",
        diagnostic,
        _DIAGNOSTIC_ARTIFACT_FIELDS,
    )
    _validate_exact_fields(
        "thesis_draft_artifact",
        thesis,
        _THESIS_ARTIFACT_FIELDS,
    )
    diagnostic_view = diagnostic.get("diagnostic")
    if not isinstance(diagnostic_view, Mapping):
        raise UserReviewInputError("diagnostic_artifact.diagnostic must be a mapping")
    input_snapshot = diagnostic_view.get("input_snapshot")
    assumption_snapshot = diagnostic_view.get("assumption_snapshot")
    if not isinstance(input_snapshot, Mapping) or not isinstance(
        assumption_snapshot, Mapping
    ):
        raise UserReviewInputError(
            "diagnostic artifact must contain input and assumption snapshots"
        )
    frozen_bundle = {
        "schema_version": "m0-frozen-growth-diagnostic-bundle-v1",
        "canonical_ticker": ticker,
        "run_id": run_id,
        "dossier_snapshot": dossier_snapshot,
        "profile_version": profile_version,
        "diagnostic_input": dict(input_snapshot),
        "assumption_snapshot": dict(assumption_snapshot),
    }
    try:
        from data.lib.frozen_growth_diagnostic import (
            FrozenInputBundleError,
            validate_frozen_growth_diagnostic_artifact,
        )

        validated_diagnostic = validate_frozen_growth_diagnostic_artifact(
            diagnostic, frozen_bundle
        )
    except (FrozenInputBundleError, TypeError, ValueError, KeyError) as exc:
        raise UserReviewInputError(
            f"diagnostic artifact binding is invalid: {exc}"
        ) from exc

    for field, expected in (
        ("canonical_ticker", ticker),
        ("run_id", run_id),
        ("dossier_snapshot", dossier_snapshot),
        ("profile_version", profile_version),
    ):
        if diagnostic.get(field) != expected:
            raise UserReviewInputError(f"diagnostic artifact {field} mismatch")

    validated_thesis = _validate_thesis_draft_artifact_locally(
        thesis,
        diagnostic=diagnostic,
        ticker=ticker,
        run_id=run_id,
        dossier_snapshot=dossier_snapshot,
        profile_version=profile_version,
        dossier=dossier,
    )

    return {
        "schema_version": USER_REVIEW_INPUT_SCHEMA_VERSION,
        "canonical_ticker": ticker,
        "run_id": run_id,
        "dossier_snapshot": dossier_snapshot,
        "profile_version": profile_version,
        "artifact_paths": paths,
        "diagnostic_artifact": diagnostic,
        "thesis_draft_artifact": validated_thesis,
        "dossier": deepcopy(dossier),
        "user_review": user_review,
    }


def _validate_artifact_paths(value: Any) -> dict[str, str]:
    paths = _required_mapping("artifact_paths", value)
    if set(paths) != {"diagnostic", "thesis_draft"}:
        raise UserReviewInputError(
            "artifact_paths must contain exactly diagnostic and thesis_draft"
        )
    validated: dict[str, str] = {}
    for name in ("diagnostic", "thesis_draft"):
        path = Path(_required_text(f"artifact_paths.{name}", paths[name]))
        if not path.is_file():
            raise UserReviewInputError(
                f"artifact_paths.{name} must point to an existing file"
            )
        validated[name] = str(path)
    return validated


def _validate_exact_fields(
    name: str,
    value: Mapping[str, Any],
    expected_fields: set[str],
) -> None:
    unknown = sorted(set(value) - expected_fields)
    missing = sorted(expected_fields - set(value))
    if unknown:
        raise UserReviewInputError(f"{name} contains unknown fields: {unknown}")
    if missing:
        raise UserReviewInputError(f"{name} is missing fields: {missing}")


def _validate_thesis_draft_artifact_locally(
    artifact: Mapping[str, Any],
    *,
    diagnostic: Mapping[str, Any],
    ticker: str,
    run_id: str,
    dossier_snapshot: str,
    profile_version: str,
    dossier: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        artifact["artifact_type"] != "strong_agent_thesis_draft"
        or artifact["artifact_schema_version"] != "m0-strong-agent-thesis-draft-v1"
        or artifact["capability_status"] != "mvp_evidence"
        or artifact["gate_status"] != "not_passed"
    ):
        raise UserReviewInputError("Thesis draft artifact envelope is invalid")
    for field, expected in (
        ("canonical_ticker", ticker),
        ("run_id", run_id),
        ("dossier_snapshot", dossier_snapshot),
        ("profile_version", profile_version),
        ("diagnostic_digest", diagnostic["diagnostic"]["diagnostic_digest"]),
    ):
        if artifact.get(field) != expected:
            raise UserReviewInputError(f"Thesis draft artifact {field} mismatch")
    if artifact["artifact_digest"] != _sha256(
        {key: value for key, value in artifact.items() if key != "artifact_digest"}
    ):
        raise UserReviewInputError("Thesis draft artifact digest mismatch")
    if artifact["diagnostic"] != diagnostic["diagnostic"]:
        raise UserReviewInputError(
            "Thesis draft diagnostic does not match the M0.1 diagnostic artifact"
        )
    if artifact["diagnostic_summary"] != _diagnostic_summary(
        diagnostic["diagnostic"]
    ):
        raise UserReviewInputError(
            "Thesis draft diagnostic_summary does not match the diagnostic"
        )
    if artifact["agent_id"] != "buffett":
        raise UserReviewInputError("Thesis draft agent_id must be buffett")
    expected_input_digest = _sha256(
        {
            "canonical_ticker": ticker,
            "run_id": run_id,
            "dossier_snapshot": dossier_snapshot,
            "profile_version": profile_version,
            "diagnostic_artifact": diagnostic,
            "dossier": dossier,
            "agent_id": artifact["agent_id"],
            "model": artifact["model"],
            "prompt_version": artifact["prompt_version"],
        }
    )
    if artifact["input_digest"] != expected_input_digest:
        raise UserReviewInputError(
            "Thesis draft input_digest does not match the bound dossier/artifact"
        )
    try:
        output = AgentOutput.from_dict("buffett", artifact["agent_output"])
    except (ValidationError, TypeError, KeyError) as exc:
        raise UserReviewInputError(
            f"Thesis draft agent_output is invalid: {exc}"
        ) from exc
    if output.extra:
        raise UserReviewInputError(
            "Thesis draft agent_output contains unsupported fields: "
            + ", ".join(sorted(output.extra))
        )
    if any(not isinstance(item, str) for item in output.key_metrics):
        raise UserReviewInputError(
            "Thesis draft agent_output key_metrics must be a list of strings"
        )
    grounding_issues = _grounding_issues(
        output.key_metrics,
        {"dossier": dossier, "diagnostic": diagnostic},
    )
    if grounding_issues:
        raise UserReviewInputError(
            "Thesis draft agent_output grounding failed: "
            + "; ".join(grounding_issues)
        )
    if diagnostic["diagnostic"]["calculation_status"] in {"not_evaluable", "failed"}:
        if output.signal != "skip" or output.conviction != 0:
            raise UserReviewInputError(
                "blocked diagnostic cannot publish directional agent output"
            )
    return {**dict(artifact), "agent_output": output.to_dict()}


def _grounding_issues(metrics: list[str], features: Mapping[str, Any]) -> list[str]:
    feature_numbers = _collect_feature_numbers(features)
    issues: list[str] = []
    for metric in metrics:
        for match in re.finditer(r"(\d+\.?\d*)", metric):
            value = float(match.group(1))
            end = match.end()
            if metric[end : end + 1] in {"日", "年", "季", "倍", "期"}:
                continue
            if not any(abs(number - abs(value)) <= 0.5 for number in feature_numbers):
                issues.append(
                    f"key_metrics 含数字 {value:g}，但 features 中无对应字段值"
                )
    return issues


def _diagnostic_summary(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "calculation_status": diagnostic["calculation_status"],
        "quality_status": diagnostic["quality_status"],
        "decision_grade": diagnostic["decision_grade"],
        "expectation_overdraft": diagnostic.get("expectation_overdraft"),
        "credible_growth_range": diagnostic.get("credible_growth_range"),
        "priced_growth_share_range": diagnostic.get("priced_growth_share_range"),
        "warnings": list(diagnostic.get("warnings") or []),
        "reasons": list(diagnostic.get("reasons") or []),
        "input_digest": diagnostic.get("input_digest"),
        "diagnostic_digest": diagnostic.get("diagnostic_digest"),
    }


def _collect_feature_numbers(value: Any) -> list[float]:
    numbers: list[float] = []

    def visit(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            numbers.append(abs(float(node)))
        elif isinstance(node, Mapping):
            for child in node.values():
                visit(child)
        elif isinstance(node, list | tuple):
            for child in node:
                visit(child)

    visit(value)
    return numbers


def _validate_user_review(value: Any) -> dict[str, Any]:
    review = _required_mapping("user_review", value)
    allowed = {
        "review_status",
        "dimensions",
        "key_issues",
        "accepted_content",
        "residual_risk",
        "next_decision",
    }
    unknown = sorted(set(review) - allowed)
    if unknown:
        raise UserReviewInputError(
            f"user_review contains unknown fields: {unknown}"
        )
    status = review.get("review_status")
    if status not in REVIEW_STATUSES:
        raise UserReviewInputError(
            f"user_review.review_status must be one of {sorted(REVIEW_STATUSES)}"
        )
    dimensions = _required_mapping("user_review.dimensions", review.get("dimensions"))
    if set(dimensions) != set(REVIEW_DIMENSIONS):
        raise UserReviewInputError(
            "user_review.dimensions must contain exactly the four M0.3 dimensions"
        )
    validated_dimensions = {
        name: _validate_dimension(name, dimensions[name], status)
        for name in REVIEW_DIMENSIONS
    }
    lists = {
        name: _string_list(f"user_review.{name}", review.get(name))
        for name in ("key_issues", "accepted_content", "residual_risk")
    }
    next_decision = _required_user_text(
        "user_review.next_decision",
        review.get("next_decision"),
    ) if status == "completed" else _optional_text(
        "user_review.next_decision",
        review.get("next_decision", ""),
    )
    return {
        "review_status": status,
        "dimensions": validated_dimensions,
        **lists,
        "next_decision": next_decision,
    }


def _validate_dimension(name: str, value: Any, review_status: str) -> dict[str, Any]:
    dimension = _required_mapping(f"user_review.dimensions.{name}", value)
    allowed = {
        "conclusion_status",
        "feedback",
        "issues_or_corrections",
        "not_evaluable_reason",
    }
    unknown = sorted(set(dimension) - allowed)
    if unknown:
        raise UserReviewInputError(
            f"user_review.dimensions.{name} contains unknown fields: {unknown}"
        )
    conclusion_status = dimension.get("conclusion_status")
    if conclusion_status not in REVIEW_CONCLUSION_STATUSES:
        raise UserReviewInputError(
            f"user_review.dimensions.{name}.conclusion_status is invalid"
        )
    feedback = _optional_user_text(
        f"user_review.dimensions.{name}.feedback",
        dimension.get("feedback", ""),
    )
    corrections = _string_list(
        f"user_review.dimensions.{name}.issues_or_corrections",
        dimension.get("issues_or_corrections"),
    )
    reason = _optional_user_text(
        f"user_review.dimensions.{name}.not_evaluable_reason",
        dimension.get("not_evaluable_reason", ""),
    )
    if review_status == "completed" and not _has_user_text(feedback):
        raise UserReviewInputError(
            f"user_review.dimensions.{name}.feedback is required for completed review"
        )
    if (
        review_status == "completed"
        and conclusion_status == "not_evaluable"
        and not _has_user_text(reason)
    ):
        raise UserReviewInputError(
            f"user_review.dimensions.{name}.not_evaluable_reason is required"
        )
    if (
        review_status == "completed"
        and conclusion_status != "not_evaluable"
        and _has_user_text(reason)
    ):
        raise UserReviewInputError(
            f"user_review.dimensions.{name}.not_evaluable_reason must be empty"
        )
    return {
        "conclusion_status": conclusion_status,
        "feedback": feedback,
        "issues_or_corrections": corrections,
        "not_evaluable_reason": reason,
    }


def _diagnostic_reference(artifact: Mapping[str, Any], path: str) -> dict[str, Any]:
    diagnostic = artifact["diagnostic"]
    return {
        "artifact_type": artifact["artifact_type"],
        "artifact_schema_version": artifact["artifact_schema_version"],
        "path": path,
        "artifact_digest": artifact["artifact_digest"],
        "diagnostic_digest": diagnostic["diagnostic_digest"],
        "canonical_ticker": artifact["canonical_ticker"],
        "run_id": artifact["run_id"],
        "dossier_snapshot": artifact["dossier_snapshot"],
        "profile_version": artifact["profile_version"],
        "calculation_status": diagnostic["calculation_status"],
        "quality_status": diagnostic["quality_status"],
        "report_period": diagnostic.get("report_period"),
        "as_of": diagnostic.get("as_of"),
        "warnings": list(diagnostic.get("warnings") or []),
        "reasons": list(diagnostic.get("reasons") or []),
        "sources": deepcopy((diagnostic.get("input_snapshot") or {}).get("sources", [])),
    }


def _thesis_reference(artifact: Mapping[str, Any], path: str) -> dict[str, Any]:
    return {
        "artifact_type": artifact["artifact_type"],
        "artifact_schema_version": artifact["artifact_schema_version"],
        "path": path,
        "artifact_digest": artifact["artifact_digest"],
        "diagnostic_digest": artifact["diagnostic_digest"],
        "canonical_ticker": artifact["canonical_ticker"],
        "run_id": artifact["run_id"],
        "dossier_snapshot": artifact["dossier_snapshot"],
        "profile_version": artifact["profile_version"],
        "diagnostic_status": artifact["diagnostic_status"],
        "quality_status": artifact["quality_status"],
        "quality_reasons": list(artifact.get("quality_reasons") or []),
        "agent_id": artifact["agent_id"],
        "model": artifact["model"],
    }


def _required_mapping(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise UserReviewInputError(f"{name} must be a non-empty mapping")
    return dict(value)


def _string_list(name: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise UserReviewInputError(f"{name} must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise UserReviewInputError(f"{name} must contain non-empty strings")
    return list(value)


def _required_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UserReviewInputError(f"{name} is required")
    return value.strip()


def _optional_text(name: str, value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise UserReviewInputError(f"{name} must be a string")
    return value.strip()


def _required_user_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UserReviewInputError(f"{name} is required")
    return value


def _optional_user_text(name: str, value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise UserReviewInputError(f"{name} must be a string")
    return value


def _has_user_text(value: str) -> bool:
    return bool(value.strip())


def _canonical_text(name: str, value: Any) -> str:
    text = _required_text(name, value)
    try:
        return canonical_ticker(text)
    except (TypeError, ValueError) as exc:
        raise UserReviewInputError(f"{name} is not a valid ticker") from exc


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
        raise UserReviewInputError(f"{name} must be a non-empty relative path leaf")
    return text


def _validate_output_dir(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise UserReviewInputError("output_dir is required")
    directory = Path(value)
    if directory.exists() and not directory.is_dir():
        raise UserReviewInputError("output_dir must be a directory")
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UserReviewInputError("output_dir is not writable") from exc
    return directory


def _write_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


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
        raise UserReviewInputError("user review value is not strict JSON") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _markdown_user_text(value: str) -> str:
    return f"<pre>{html.escape(value, quote=False)}</pre>"


def _markdown_list_item(value: str) -> str:
    return (
        html.escape(value, quote=False)
        .replace("\r\n", "&#10;")
        .replace("\r", "&#13;")
        .replace("\n", "&#10;")
    )
