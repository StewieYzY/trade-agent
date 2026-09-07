"""M1.3 G1 小样本人工复核的离线记录与确定性产物。"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import html
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping
import uuid

import fcntl

from data.lib.identity import canonical_ticker, compute_input_ticker_set_hash
from data.lib.production_paths import ProductionPathViolation, validate_g1_output_root


SOURCE_SCHEMA_VERSION = "g1-small-sample-run/v1"
REVIEW_SCHEMA_VERSION = "g1-small-sample-user-review/v1"
REVIEW_DIMENSIONS = (
    "candidate",
    "inclusion_or_exclusion_reason",
    "scores_and_thresholds",
    "quality_and_data",
)
FEEDBACK_STATUSES = (
    "accepted",
    "question",
    "problem",
    "not_evaluable",
)
_SOURCE_FIELDS = {
    "schema_version",
    "artifact_type",
    "mode",
    "capability_status",
    "gate_status",
    "run_id",
    "profile_version",
    "input_ticker_set_hash",
    "as_of",
    "provenance",
    "summary",
    "tickers",
    "staged_evidence",
}
_TICKER_FIELDS = {
    "ticker",
    "stage_statuses",
    "candidate",
    "quality_status",
    "details",
    "scores",
    "exclusion",
}
_FEEDBACK_FIELDS = {
    "status",
    "feedback",
    "question",
    "issue",
    "corrected_value",
    "suggested_action",
}
_SUMMARY_FIELDS = {
    "threshold_issues",
    "false_positive_tickers",
    "false_negative_tickers",
    "data_insufficiency",
    "next_steps",
}
_PROVENANCE_FIELDS = {
    "source",
    "not_live_provider_evidence",
    "fixture_id",
    "dataset_hash",
    "reader",
}
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_STAGE_FIELDS = {
    "stage",
    "run_id",
    "input_tickers",
    "output_tickers",
    "requested_dimensions",
    "canonical_input_tickers",
    "canonical_output_tickers",
    "requests",
    "provider_calls",
    "cache_hits",
    "failures",
    "dimension_results",
    "passed_count",
    "failed_count",
}
_CANDIDATE_FIELDS = {
    "ticker",
    "name",
    "industry",
    "factor_scores",
    "anti_trap",
    "adjusted_composite",
    "f_score",
    "graham_number",
    "pe_ttm",
    "pb",
    "pledge_ratio",
    "heat_filter",
}
_TICKER_EVIDENCE_FIELDS = {"raw_ticker", "canonical_fields"}
_CANONICAL_FIELD_FIELDS = {
    "value",
    "status",
    "eligibility",
    "reason",
    "provenance",
    "as_of",
    "freshness",
    "available",
}
_CANONICAL_FIELD_NAMES = {
    "name",
    "price",
    "last_price",
    "pe",
    "pb",
    "market_cap",
    "industry",
    "years",
    "net_profit",
    "TOTAL_ASSETS",
    "TOTAL_CURRENT_LIAB",
    "TOTAL_NONCURRENT_LIAB",
    "NETCASH_OPERATE",
    "pledge_ratio",
    "pledge_status",
    "audit_opinion",
    "pe_ttm",
    "pe_percentile_5y",
    "pe_history",
    "close",
    "turnover_rate",
}
_FAILURE_FIELDS = {"ticker", "dimension", "status", "reason"}
_FAILURE_OPTIONAL_FIELDS = {"failed_filters"}
_FAILURE_STATUSES = {
    "conflict",
    "degraded",
    "partial",
    "permission_denied",
    "rate_limited",
    "not_supported_for_market",
    "record_not_found",
    "source_failed",
    "invalid_value",
    "not_evaluated",
    "stale",
}
_CANONICAL_STATUSES = {"available", "complete"} | _FAILURE_STATUSES
_CANONICAL_ELIGIBILITIES = {"not_qualified", "shadow_only"}
_CANONICAL_FRESHNESS = {"fresh", "stale", "unknown", None}
_RECORD_FIELDS = {
    "artifact_type",
    "artifact_schema_version",
    "source_artifact_type",
    "source_schema_version",
    "source_artifact_digest",
    "source_markdown_path",
    "source_markdown_digest",
    "run_id",
    "profile_version",
    "input_ticker_set_hash",
    "as_of",
    "provenance",
    "review_status",
    "user_review_owner",
    "capability_status",
    "gate_status",
    "ticker_reviews",
    "feedback_summary",
    "issue_categories",
    "source_snapshot",
    "artifact_digest",
}


class SmallSampleUserReviewInputError(ValueError):
    """M1.3 输入、反馈或输出记录不可信时抛出。"""


@dataclass(frozen=True)
class SmallSampleUserReviewArtifacts:
    json_path: Path
    markdown_path: Path


def build_small_sample_user_review_record(
    m1_result: Mapping[str, Any],
    reviews: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    *,
    summary: Mapping[str, Any] | None = None,
    markdown_path: str | Path | None = None,
) -> dict[str, Any]:
    """绑定 M1.2 结果并构造 template 或显式 completed review record。"""
    try:
        source = _validate_m1_result(m1_result)
        source_digest = _sha256(source)
        source_markdown = _validate_optional_markdown(markdown_path, source)
        ticker_reviews = _build_ticker_reviews(source["tickers"], reviews)
        review_status = "template" if reviews is None else "completed"
        issue_categories = _validate_summary(summary)

        record: dict[str, Any] = {
            "artifact_type": "g1_small_sample_user_review",
            "artifact_schema_version": REVIEW_SCHEMA_VERSION,
            "source_artifact_type": source["artifact_type"],
            "source_schema_version": source["schema_version"],
            "source_artifact_digest": source_digest,
            "source_markdown_path": source_markdown,
            "source_markdown_digest": (
                _sha256(Path(source_markdown).read_text(encoding="utf-8"))
                if source_markdown is not None
                else None
            ),
            "run_id": source["run_id"],
            "profile_version": source["profile_version"],
            "input_ticker_set_hash": source["input_ticker_set_hash"],
            "as_of": source["as_of"],
            "provenance": deepcopy(source["provenance"]),
            "review_status": review_status,
            "user_review_owner": "user",
            "capability_status": (
                "mvp_evidence" if review_status == "completed" else "not_evidence"
            ),
            "gate_status": "not_passed",
            "ticker_reviews": ticker_reviews,
            "feedback_summary": _summarize_feedback(ticker_reviews),
            "issue_categories": issue_categories,
            "source_snapshot": deepcopy(source),
        }
        record["artifact_digest"] = compute_small_sample_user_review_digest(record)
        return record
    except SmallSampleUserReviewInputError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise SmallSampleUserReviewInputError(
            f"M1.2 result structure is invalid: {exc}"
        ) from exc


def render_small_sample_user_review_json(record: Mapping[str, Any]) -> str:
    """以稳定 key 顺序渲染 JSON。"""
    return (
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )


def render_small_sample_user_review_markdown(record: Mapping[str, Any]) -> str:
    """渲染可读且不改变用户原文的 Markdown。"""
    lines = [
        "# G1 小样本人工复核记录",
        "",
        f"- review_status: `{record['review_status']}`",
        f"- capability_status: `{record['capability_status']}`",
        f"- gate_status: `{record['gate_status']}`",
        (
            "- 本记录是 template，等待真实用户复核；空值不表示认可。"
            if record["review_status"] == "template"
            else "- 本记录保存显式人工反馈，不代表 G1 Capability Gate 通过。"
        ),
        "",
        "## 运行身份",
        "",
        f"- run_id: `{_markdown_cell(record['run_id'])}`",
        f"- profile_version: `{_markdown_cell(record['profile_version'])}`",
        f"- input_ticker_set_hash: `{_markdown_cell(record['input_ticker_set_hash'])}`",
        f"- as_of: `{_markdown_cell(record['as_of'])}`",
        f"- source_artifact_digest: `{record['source_artifact_digest']}`",
        "",
        "## 逐票反馈",
        "",
        "| ticker | dimension | status | feedback | question | issue | corrected_value | suggested_action |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for ticker_review in record["ticker_reviews"]:
        for dimension in REVIEW_DIMENSIONS:
            feedback = ticker_review["dimensions"][dimension]
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_cell(ticker_review["ticker"]),
                        _markdown_cell(dimension),
                        _markdown_cell(feedback["status"]),
                        _markdown_cell(feedback["feedback"]),
                        _markdown_cell(feedback["question"]),
                        _markdown_cell(feedback["issue"]),
                        _markdown_cell(feedback["corrected_value"]),
                        _markdown_cell(feedback["suggested_action"]),
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## 反馈汇总",
            "",
            f"- status_counts: `{_markdown_cell(record['feedback_summary']['status_counts'])}`",
            f"- dimension_status_counts: `{_markdown_cell(record['feedback_summary']['dimension_status_counts'])}`",
            "",
            "### 阈值问题",
            "",
            *_markdown_list(record["issue_categories"]["threshold_issues"]),
            "",
            "### 误选",
            "",
            *_markdown_list(record["issue_categories"]["false_positive_tickers"]),
            "",
            "### 漏选",
            "",
            *_markdown_list(record["issue_categories"]["false_negative_tickers"]),
            "",
            "### 数据不足",
            "",
            *_markdown_list(record["issue_categories"]["data_insufficiency"]),
            "",
            "### 下一步建议",
            "",
            *_markdown_list(record["issue_categories"]["next_steps"]),
            "",
            "## 限制",
            "",
            "- 不调用 provider、LLM、Scout 或 Council。",
            "- 不自动修改候选、筛选规则、阈值、watchlist 或 Gate verdict。",
            "- `not_evaluable` 和空值不表示用户认可。",
        ]
    )
    return "\n".join(lines) + "\n"


def compute_small_sample_user_review_digest(record: Mapping[str, Any]) -> str:
    """计算不含 artifact_digest 字段的确定性 digest。"""
    if not isinstance(record, Mapping):
        raise SmallSampleUserReviewInputError("review record must be a mapping")
    payload = dict(record)
    payload.pop("artifact_digest", None)
    return _sha256(payload)


def validate_small_sample_user_review_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """校验已生成记录的 digest，防止输出被静默篡改。"""
    if not isinstance(record, Mapping):
        raise SmallSampleUserReviewInputError("review record must be a mapping")
    expected = record.get("artifact_digest")
    if (
        not isinstance(expected, str)
        or expected != compute_small_sample_user_review_digest(record)
    ):
        raise SmallSampleUserReviewInputError(
            "review record artifact digest mismatch"
        )
    _validate_record_shape(record)
    return deepcopy(dict(record))


def _validate_record_shape(record: Mapping[str, Any]) -> None:
    unknown = sorted(set(record) - _RECORD_FIELDS)
    missing = sorted(_RECORD_FIELDS - set(record))
    if unknown or missing:
        raise SmallSampleUserReviewInputError(
            f"review record structure invalid: unknown={unknown}, missing={missing}"
        )
    if (
        record["artifact_type"] != "g1_small_sample_user_review"
        or record["artifact_schema_version"] != REVIEW_SCHEMA_VERSION
        or record["source_artifact_type"] != "fixture/reference"
        or record["source_schema_version"] != SOURCE_SCHEMA_VERSION
        or record["user_review_owner"] != "user"
        or record["gate_status"] != "not_passed"
    ):
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: envelope"
        )
    if (
        not isinstance(record["review_status"], str)
        or record["review_status"] not in {"template", "completed"}
    ):
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: review_status"
        )
    expected_capability = (
        "mvp_evidence"
        if record["review_status"] == "completed"
        else "not_evidence"
    )
    if record["capability_status"] != expected_capability:
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: capability_status"
        )
    for key in (
        "run_id",
        "profile_version",
        "input_ticker_set_hash",
        "as_of",
        "source_artifact_digest",
        "artifact_digest",
    ):
        if not isinstance(record[key], str) or not record[key].strip():
            raise SmallSampleUserReviewInputError(
                f"review record structure invalid: {key}"
            )
    if not _SAFE_RUN_ID.fullmatch(record["run_id"]):
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: run_id"
        )
    if len(record["source_artifact_digest"]) != 64 or len(record["artifact_digest"]) != 64:
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: digest"
        )
    source_snapshot = record["source_snapshot"]
    if not isinstance(source_snapshot, Mapping):
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: source snapshot"
        )
    try:
        normalized_source = _validate_m1_result(source_snapshot)
    except (SmallSampleUserReviewInputError, TypeError, ValueError) as exc:
        raise SmallSampleUserReviewInputError(
            "review record source snapshot is invalid"
        ) from exc
    if _sha256(normalized_source) != record["source_artifact_digest"]:
        raise SmallSampleUserReviewInputError(
            "review record source artifact binding is invalid"
        )
    for key in (
        "run_id",
        "profile_version",
        "input_ticker_set_hash",
        "as_of",
        "provenance",
    ):
        if record[key] != normalized_source[key]:
            raise SmallSampleUserReviewInputError(
                f"review record semantic invalid: source identity is invalid: {key}"
            )
    if record["source_markdown_path"] is not None and not isinstance(
        record["source_markdown_path"], str
    ):
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: source_markdown_path"
        )
    if record["source_markdown_path"] is None:
        if record["source_markdown_digest"] is not None:
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: source Markdown digest"
            )
    else:
        if (
            not isinstance(record["source_markdown_digest"], str)
            or len(record["source_markdown_digest"]) != 64
        ):
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: source Markdown digest"
            )
        try:
            normalized_markdown_path = _validate_optional_markdown(
                record["source_markdown_path"],
                normalized_source,
            )
        except SmallSampleUserReviewInputError as exc:
            raise SmallSampleUserReviewInputError(
                "review record Markdown binding is invalid"
            ) from exc
        if normalized_markdown_path != record["source_markdown_path"]:
            raise SmallSampleUserReviewInputError(
                "review record Markdown path binding is invalid"
            )
        markdown_file = Path(normalized_markdown_path)
        if _sha256(markdown_file.read_text(encoding="utf-8")) != record[
            "source_markdown_digest"
        ]:
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: source Markdown digest"
            )
    if not isinstance(record["provenance"], Mapping):
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: provenance"
        )
    provenance = record["provenance"]
    if (
        set(provenance) - _PROVENANCE_FIELDS
        or provenance.get("source") != "fixture/reference"
        or provenance.get("not_live_provider_evidence") is not True
        or any(
            key != "not_live_provider_evidence"
            and (
                not isinstance(value, str)
                or not value.strip()
                or any(
                    marker in value.casefold()
                    for marker in ("live", "provider", "production")
                )
            )
            for key, value in provenance.items()
        )
    ):
        raise SmallSampleUserReviewInputError(
            "review record semantic invalid: provenance"
        )
    if not isinstance(record["ticker_reviews"], list) or not record["ticker_reviews"]:
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: ticker_reviews"
        )
    seen: set[str] = set()
    source_rows_by_ticker = {
        row["ticker"]: row for row in normalized_source["tickers"]
    }
    for item in record["ticker_reviews"]:
        if not isinstance(item, Mapping) or set(item) != {
            "ticker",
            "source_result",
            "dimensions",
        }:
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: ticker review"
            )
        ticker = item["ticker"]
        try:
            canonical = canonical_ticker(ticker)
        except (TypeError, ValueError) as exc:
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: ticker"
            ) from exc
        if ticker != canonical or ticker in seen:
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: ticker identity"
            )
        seen.add(ticker)
        source_result = item["source_result"]
        if not isinstance(source_result, Mapping) or set(
            item["source_result"]
        ) != _TICKER_FIELDS:
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: source_result"
            )
        if source_result["ticker"] != ticker:
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: ticker identity"
            )
        if source_result != source_rows_by_ticker.get(ticker):
            raise SmallSampleUserReviewInputError(
                "review record semantic invalid: source result binding is invalid"
            )
        if (
            not isinstance(source_result["stage_statuses"], Mapping)
            or set(source_result["stage_statuses"]) != {"A", "B", "C"}
            or any(
                not isinstance(status, str)
                or status not in {"passed", "failed", "not_reached"}
                for status in source_result["stage_statuses"].values()
            )
            or not isinstance(source_result["candidate"], bool)
            or not isinstance(source_result["details"], Mapping)
            or not isinstance(source_result["scores"], Mapping)
            or (
                source_result["exclusion"] is not None
                and not isinstance(source_result["exclusion"], Mapping)
            )
        ):
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: source_result"
            )
        if source_result["quality_status"] not in {
            "complete",
            "degraded",
            "failed",
            "not_evaluable",
        }:
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: source_result quality"
            )
        try:
            _validate_ticker_semantics(source_result, ticker)
            _validate_result_payload(
                source_result,
                ticker,
                prefix="review record",
            )
        except SmallSampleUserReviewInputError as exc:
            raise SmallSampleUserReviewInputError(
                "review record semantic invalid: source_result"
            ) from exc
        dimensions = item["dimensions"]
        if not isinstance(dimensions, Mapping) or set(dimensions) != set(
            REVIEW_DIMENSIONS
        ):
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: dimensions"
            )
        for feedback in dimensions.values():
            if not isinstance(feedback, Mapping) or set(feedback) != _FEEDBACK_FIELDS:
                raise SmallSampleUserReviewInputError(
                    "review record structure invalid: feedback"
                )
            if (
                not isinstance(feedback["status"], str)
                or feedback["status"] not in FEEDBACK_STATUSES
            ):
                raise SmallSampleUserReviewInputError(
                    "review record structure invalid: feedback status"
                )
            for key in ("feedback", "question", "issue", "suggested_action"):
                if not isinstance(feedback[key], str):
                    raise SmallSampleUserReviewInputError(
                        "review record structure invalid: feedback text"
                    )
            _strict_json(feedback["corrected_value"])
            if record["review_status"] == "template":
                if (
                    feedback["status"] != "not_evaluable"
                    or any(
                        feedback[key]
                        for key in (
                            "feedback",
                            "question",
                            "issue",
                            "suggested_action",
                        )
                    )
                    or feedback["corrected_value"] is not None
                ):
                    raise SmallSampleUserReviewInputError(
                        "review record semantic invalid: template feedback"
                    )
            else:
                _validate_feedback(
                    ticker,
                    "review",
                    feedback,
                )
    if not isinstance(record["issue_categories"], Mapping) or set(
        record["issue_categories"]
    ) != _SUMMARY_FIELDS:
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: issue_categories"
        )
    for key, values in record["issue_categories"].items():
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip()
            for value in values
        ):
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: issue category values"
            )
    if not isinstance(record["feedback_summary"], Mapping) or set(
        record["feedback_summary"]
    ) != {
        "status_counts",
        "dimension_status_counts",
        "question_or_problem_tickers",
    }:
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: feedback_summary"
        )
    status_counts = record["feedback_summary"]["status_counts"]
    if (
        not isinstance(status_counts, Mapping)
        or set(status_counts) != set(FEEDBACK_STATUSES)
        or any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in status_counts.values()
        )
    ):
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: status counts"
        )
    dimension_counts = record["feedback_summary"]["dimension_status_counts"]
    if (
        not isinstance(dimension_counts, Mapping)
        or set(dimension_counts) != set(REVIEW_DIMENSIONS)
    ):
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: dimension status counts"
        )
    for counts in dimension_counts.values():
        if (
            not isinstance(counts, Mapping)
            or set(counts) != set(FEEDBACK_STATUSES)
            or any(
                not isinstance(count, int) or isinstance(count, bool) or count < 0
                for count in counts.values()
            )
        ):
            raise SmallSampleUserReviewInputError(
                "review record structure invalid: dimension status counts"
            )
    summary_tickers = record["feedback_summary"]["question_or_problem_tickers"]
    try:
        invalid_summary_ticker = (
            not isinstance(summary_tickers, list)
            or any(
                not isinstance(ticker, str)
                or ticker != canonical_ticker(ticker)
                for ticker in summary_tickers
            )
        )
    except (TypeError, ValueError) as exc:
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: feedback summary ticker"
        ) from exc
    if invalid_summary_ticker:
        raise SmallSampleUserReviewInputError(
            "review record structure invalid: feedback summary ticker"
        )
    try:
        expected_categories = _validate_summary(record["issue_categories"])
    except SmallSampleUserReviewInputError as exc:
        raise SmallSampleUserReviewInputError(
            "review record semantic invalid: issue categories"
        ) from exc
    if record["issue_categories"] != expected_categories:
        raise SmallSampleUserReviewInputError(
            "review record semantic invalid: issue category ordering"
        )
    expected_feedback_summary = _summarize_feedback(record["ticker_reviews"])
    if record["feedback_summary"] != expected_feedback_summary:
        raise SmallSampleUserReviewInputError(
            "review record semantic invalid: feedback summary"
        )
    record_tickers = [item["ticker"] for item in record["ticker_reviews"]]
    if record_tickers != sorted(record_tickers):
        raise SmallSampleUserReviewInputError(
            "review record semantic invalid: ticker order"
        )
    if record["input_ticker_set_hash"] != compute_input_ticker_set_hash(
        record_tickers
    ):
        raise SmallSampleUserReviewInputError(
            "review record semantic invalid: ticker-set identity"
        )


def write_small_sample_user_review_record(
    m1_result: Mapping[str, Any],
    output_dir: str | Path,
    reviews: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    *,
    summary: Mapping[str, Any] | None = None,
    markdown_path: str | Path | None = None,
) -> SmallSampleUserReviewArtifacts:
    """安全、幂等地写入 run-scoped JSON/Markdown 复核产物。"""
    record = build_small_sample_user_review_record(
        m1_result,
        reviews,
        summary=summary,
        markdown_path=markdown_path,
    )
    try:
        _reject_symlink_components(output_dir)
        canonical_root = _canonical_project_root()
        directory = validate_g1_output_root(
            output_dir,
            repo_root=canonical_root,
        )
        validate_g1_output_root(output_dir)
    except ProductionPathViolation as exc:
        raise SmallSampleUserReviewInputError(str(exc)) from exc
    if directory.exists() and not directory.is_dir():
        raise SmallSampleUserReviewInputError("output_dir must be a directory")

    run_id = record["run_id"]
    json_path = directory / f"{run_id}-review.json"
    markdown_file = directory / f"{run_id}-review.md"
    json_text = render_small_sample_user_review_json(record)
    markdown_text = render_small_sample_user_review_markdown(record)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SmallSampleUserReviewInputError(
            f"output_dir cannot be created or written: {directory}"
        ) from exc
    legacy_lock_path = directory / f".{run_id}.review.lock"
    if os.path.lexists(legacy_lock_path):
        raise SmallSampleUserReviewInputError(
            f"output_dir contains unexpected lock artifact: {legacy_lock_path}"
        )
    directory_fd: int | None = None
    try:
        directory_fd = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        try:
            existing_paths = (
                _dir_entry_exists(directory_fd, json_path.name),
                _dir_entry_exists(directory_fd, markdown_file.name),
            )
            if any(existing_paths) and not all(existing_paths):
                raise SmallSampleUserReviewInputError(
                    "output_dir contains incomplete review artifact pair"
                )
            for path, expected in (
                (json_path, json_text),
                (markdown_file, markdown_text),
            ):
                _check_existing_dir_artifact(
                    directory_fd,
                    path.name,
                    expected,
                    path,
                )

            created_names: list[str] = []
            try:
                for path, expected in (
                    (json_path, json_text),
                    (markdown_file, markdown_text),
                ):
                    if _dir_entry_exists(directory_fd, path.name):
                        _check_existing_dir_artifact(
                            directory_fd,
                            path.name,
                            expected,
                            path,
                        )
                        continue
                    staged_name = (
                        f".{run_id}.review-staging-{uuid.uuid4().hex}.tmp"
                    )
                    try:
                        staged_fd = os.open(
                            staged_name,
                            os.O_WRONLY
                            | os.O_CREAT
                            | os.O_EXCL
                            | getattr(os, "O_NOFOLLOW", 0),
                            0o600,
                            dir_fd=directory_fd,
                        )
                        with os.fdopen(
                            staged_fd,
                            "w",
                            encoding="utf-8",
                        ) as staged:
                            staged.write(expected)
                        os.replace(
                            staged_name,
                            path.name,
                            src_dir_fd=directory_fd,
                            dst_dir_fd=directory_fd,
                        )
                    except OSError:
                        try:
                            os.unlink(staged_name, dir_fd=directory_fd)
                        except OSError:
                            pass
                        raise
                    created_names.append(path.name)
            except OSError:
                for created_name in created_names:
                    try:
                        os.unlink(created_name, dir_fd=directory_fd)
                    except OSError:
                        pass
                raise
        finally:
            fcntl.flock(directory_fd, fcntl.LOCK_UN)
    except SmallSampleUserReviewInputError:
        raise
    except OSError as exc:
        raise SmallSampleUserReviewInputError(
            f"output_dir write failed: {directory}"
        ) from exc
    finally:
        if directory_fd is not None:
            try:
                os.close(directory_fd)
            except OSError:
                pass
    return SmallSampleUserReviewArtifacts(
        json_path=json_path,
        markdown_path=markdown_file,
    )


def _dir_entry_exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _check_existing_dir_artifact(
    directory_fd: int,
    name: str,
    expected: str,
    display_path: Path,
) -> None:
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(entry.st_mode):
        raise SmallSampleUserReviewInputError(
            f"output_dir contains non-regular artifact: {display_path}"
        )
    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        with os.fdopen(fd, "r", encoding="utf-8") as artifact:
            current = artifact.read()
    except OSError as exc:
        raise SmallSampleUserReviewInputError(
            f"cannot read existing artifact: {display_path}"
        ) from exc
    if current != expected:
        raise SmallSampleUserReviewInputError(
            "immutable run artifact already exists with different content: "
            f"{display_path}"
        )


def _validate_m1_result(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SmallSampleUserReviewInputError("M1.2 result must be an object")
    unknown = sorted(set(value) - _SOURCE_FIELDS)
    missing = sorted(_SOURCE_FIELDS - set(value))
    if unknown:
        raise SmallSampleUserReviewInputError(
            f"M1.2 result contains unknown fields: {unknown}"
        )
    if missing:
        raise SmallSampleUserReviewInputError(
            f"M1.2 result is missing fields: {missing}"
        )
    if (
        value["schema_version"] != SOURCE_SCHEMA_VERSION
        or value["artifact_type"] != "fixture/reference"
        or value["mode"] != "simulated/development"
        or value["capability_status"] != "not_evidence"
        or value["gate_status"] != "not_passed"
    ):
        raise SmallSampleUserReviewInputError(
            "M1.3 accepts only fixture/reference simulated/development M1.2 results"
        )
    for key in ("run_id", "profile_version", "as_of", "input_ticker_set_hash"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise SmallSampleUserReviewInputError(f"M1.2 {key} is required")
    if not _SAFE_RUN_ID.fullmatch(value["run_id"]):
        raise SmallSampleUserReviewInputError(
            "M1.2 run_id must be a safe non-empty filename token"
        )
    provenance = value["provenance"]
    if not isinstance(provenance, Mapping):
        raise SmallSampleUserReviewInputError("M1.2 provenance must be an object")
    unknown_provenance = sorted(set(provenance) - _PROVENANCE_FIELDS)
    if unknown_provenance:
        raise SmallSampleUserReviewInputError(
            f"M1.2 provenance contains unknown fields: {unknown_provenance}"
        )
    if (
        provenance.get("source") != "fixture/reference"
        or provenance.get("not_live_provider_evidence") is not True
    ):
        raise SmallSampleUserReviewInputError(
            "M1.2 provenance must be non-live fixture/reference"
        )
    for key, item in provenance.items():
        if key == "not_live_provider_evidence":
            continue
        if not isinstance(item, str) or not item.strip():
            raise SmallSampleUserReviewInputError(
                f"M1.2 provenance.{key} must be a non-empty string"
            )
        if isinstance(item, str) and any(
            marker in item.casefold()
            for marker in ("live", "provider", "production")
        ):
            raise SmallSampleUserReviewInputError(
                "M1.2 provenance contains forbidden live/provider/production marker"
            )
    if not isinstance(value["summary"], Mapping) or not isinstance(
        value["staged_evidence"], Mapping
    ):
        raise SmallSampleUserReviewInputError(
            "M1.2 summary and staged_evidence must be objects"
        )
    rows = value["tickers"]
    if not isinstance(rows, list) or not rows:
        raise SmallSampleUserReviewInputError("M1.2 tickers must be a non-empty list")
    canonical_tickers: list[str] = []
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise SmallSampleUserReviewInputError(
                "M1.2 ticker result must be an object"
            )
        row_unknown = sorted(set(row) - _TICKER_FIELDS)
        row_missing = sorted(_TICKER_FIELDS - set(row))
        if row_unknown:
            raise SmallSampleUserReviewInputError(
                f"M1.2 ticker result contains unknown fields: {row_unknown}"
            )
        if row_missing:
            raise SmallSampleUserReviewInputError(
                f"M1.2 ticker result is missing fields: {row_missing}"
            )
        try:
            ticker = canonical_ticker(row["ticker"])
        except (TypeError, ValueError) as exc:
            raise SmallSampleUserReviewInputError(
                "M1.2 ticker result has invalid ticker"
            ) from exc
        if row["ticker"] != ticker:
            raise SmallSampleUserReviewInputError(
                f"M1.2 ticker result must already be canonical: {row['ticker']!r}"
            )
        if ticker in canonical_tickers:
            raise SmallSampleUserReviewInputError(
                f"M1.2 contains duplicate canonical ticker: {ticker}"
            )
        if (
            not isinstance(row["stage_statuses"], Mapping)
            or set(row["stage_statuses"]) != {"A", "B", "C"}
            or any(
                not isinstance(status, str)
                or status not in {"passed", "failed", "not_reached"}
                for status in row["stage_statuses"].values()
            )
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 stage_statuses are invalid for {ticker}"
            )
        if not isinstance(row["candidate"], bool):
            raise SmallSampleUserReviewInputError(
                f"M1.2 candidate must be boolean for {ticker}"
            )
        if not isinstance(row["details"], Mapping) or not isinstance(
            row["scores"], Mapping
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 details and scores must be objects for {ticker}"
            )
        if row["exclusion"] is not None and not isinstance(
            row["exclusion"], Mapping
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 exclusion must be object or null for {ticker}"
            )
        if row["quality_status"] not in {
            "complete",
            "degraded",
            "failed",
            "not_evaluable",
        }:
            raise SmallSampleUserReviewInputError(
                f"M1.2 quality_status is invalid for {ticker}"
            )
        _validate_ticker_semantics(row, ticker)
        _validate_result_payload(row, ticker, prefix="M1.2")
        canonical_tickers.append(ticker)
        normalized_rows.append({**dict(row), "ticker": ticker})
    expected_hash = compute_input_ticker_set_hash(canonical_tickers)
    if value["input_ticker_set_hash"] != expected_hash:
        raise SmallSampleUserReviewInputError(
            "M1.2 input_ticker_set_hash does not match canonical ticker results"
        )
    if len(canonical_tickers) < 5 or len(canonical_tickers) > 20:
        raise SmallSampleUserReviewInputError(
            "M1.2 ticker count is outside the 5-20 small-sample range"
        )
    normalized = {
        **dict(value),
        "provenance": dict(provenance),
        "tickers": sorted(normalized_rows, key=lambda row: row["ticker"]),
    }
    _validate_source_summary(normalized)
    _validate_staged_evidence(normalized)
    _validate_cross_source_semantics(normalized)
    return normalized


def _canonical_project_root() -> Path:
    runtime_root = Path(__file__).resolve().parents[1]
    worktree_root = runtime_root.parent
    git_entry = worktree_root / ".git"
    if git_entry.is_file():
        try:
            content = git_entry.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise SmallSampleUserReviewInputError(
                "cannot resolve canonical project root from linked worktree"
            ) from exc
        prefix = "gitdir:"
        if not content.lower().startswith(prefix):
            raise SmallSampleUserReviewInputError(
                "cannot resolve canonical project root from linked worktree"
            )
        gitdir = Path(content[len(prefix) :].strip())
        if not gitdir.is_absolute():
            gitdir = git_entry.parent / gitdir
        common_git_dir = gitdir.resolve().parents[1]
        project_root = common_git_dir.parent
        if not (project_root / "value-screener").is_dir():
            raise SmallSampleUserReviewInputError(
                "cannot resolve canonical project root from linked worktree"
            )
        return project_root
    return worktree_root


def _reject_symlink_components(path: str | Path) -> None:
    absolute = Path(path).expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        if part in {"", "."}:
            continue
        if part == "..":
            current = current.parent
            continue
        current = current / part
        if current.is_symlink():
            raise SmallSampleUserReviewInputError(
                f"output_dir contains symlink path component: {current}"
            )


def _validate_result_payload(
    row: Mapping[str, Any],
    ticker: str,
    *,
    prefix: str,
) -> None:
    expected_details = {
        "name",
        "industry",
        "f_score",
        "pe_ttm",
        "pb",
        "graham_number",
        "pledge_ratio",
    }
    expected_scores = {
        "factor_scores",
        "anti_trap",
        "heat_filter",
        "adjusted_composite",
    }
    details = row["details"]
    scores = row["scores"]
    if not isinstance(details, Mapping) or set(details) != expected_details:
        raise SmallSampleUserReviewInputError(
            f"{prefix} details fields are invalid for {ticker}"
        )
    if not isinstance(scores, Mapping) or set(scores) != expected_scores:
        raise SmallSampleUserReviewInputError(
            f"{prefix} scores fields are invalid for {ticker}"
        )
    if (
        not isinstance(details["name"], (str, type(None)))
        or not isinstance(details["industry"], (str, type(None)))
        or any(
            details[key] is not None
            and (
                isinstance(details[key], bool)
                or not isinstance(details[key], (int, float))
            )
            for key in (
                "f_score",
                "pe_ttm",
                "pb",
                "graham_number",
                "pledge_ratio",
            )
        )
    ):
        raise SmallSampleUserReviewInputError(
            f"{prefix} details values are invalid for {ticker}"
        )
    for key in ("factor_scores", "anti_trap", "heat_filter"):
        if scores[key] is not None and not isinstance(scores[key], Mapping):
            raise SmallSampleUserReviewInputError(
                f"{prefix} scores.{key} is invalid for {ticker}"
            )
    if scores["factor_scores"] is not None:
        factor = scores["factor_scores"]
        if set(factor) != {
            "quality",
            "value",
            "safety_margin",
            "composite",
            "f_score",
            "dcf_note",
        } or any(
            not isinstance(factor[key], (int, float))
            or isinstance(factor[key], bool)
            for key in ("quality", "value", "safety_margin", "composite", "f_score")
        ) or not isinstance(factor["dcf_note"], str):
            raise SmallSampleUserReviewInputError(
                f"{prefix} factor_scores is invalid for {ticker}"
            )
    if scores["anti_trap"] is not None:
        anti_trap = scores["anti_trap"]
        if (
            set(anti_trap) != {"score", "flags"}
            or not isinstance(anti_trap["score"], (int, float))
            or isinstance(anti_trap["score"], bool)
            or not isinstance(anti_trap["flags"], list)
            or any(not isinstance(flag, str) for flag in anti_trap["flags"])
        ):
            raise SmallSampleUserReviewInputError(
                f"{prefix} anti_trap is invalid for {ticker}"
            )
    if scores["heat_filter"] is not None:
        heat = scores["heat_filter"]
        if (
            set(heat) != {"pass", "not_evaluable", "failed_filters"}
            or not isinstance(heat["pass"], bool)
            or not isinstance(heat["not_evaluable"], bool)
            or not isinstance(heat["failed_filters"], list)
            or any(not isinstance(item, str) for item in heat["failed_filters"])
        ):
            raise SmallSampleUserReviewInputError(
                f"{prefix} heat_filter is invalid for {ticker}"
            )
    if scores["adjusted_composite"] is not None and (
        isinstance(scores["adjusted_composite"], bool)
        or not isinstance(scores["adjusted_composite"], (int, float))
    ):
        raise SmallSampleUserReviewInputError(
            f"{prefix} scores.adjusted_composite is invalid for {ticker}"
        )
    if row["candidate"] and (
        any(details[key] is None for key in ("name", "industry", "f_score"))
        or any(
            scores[key] is None
            for key in ("factor_scores", "anti_trap", "heat_filter", "adjusted_composite")
        )
    ):
        raise SmallSampleUserReviewInputError(
            f"{prefix} candidate payload is incomplete for {ticker}"
        )


def _validate_dimension_payload(
    dimension: str,
    value: Any,
    ticker: str,
    stage_name: str,
) -> None:
    if not isinstance(value, Mapping):
        raise SmallSampleUserReviewInputError(
            f"M1.2 {stage_name} dimension payload is invalid for {ticker}"
        )
    if value.get("__error__") is True:
        if set(value) != {"__error__", "error"} or not isinstance(
            value.get("error"), str
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 {stage_name} error payload is invalid for {ticker}"
            )
        return
    expected = {
        "basic": {"name", "price", "pe", "pb", "market_cap", "industry"},
        "financials": {"years", "income", "balance_sheet", "cash_flow"},
        "risk": {"pledge_ratio", "pledge_status", "audit_opinion"},
        "valuation": {"pe_ttm", "pb", "pe_percentile_5y", "pe_history"},
        "kline": {"close", "turnover_rate"},
    }[dimension]
    if set(value) != expected:
        raise SmallSampleUserReviewInputError(
            f"M1.2 {stage_name} {dimension} payload fields are invalid for {ticker}"
        )
    if dimension == "basic":
        _validate_number_or_none(value["price"], stage_name, dimension, ticker)
        _validate_number_or_none(value["pe"], stage_name, dimension, ticker)
        _validate_number_or_none(value["pb"], stage_name, dimension, ticker)
        _validate_number_or_none(
            value["market_cap"], stage_name, dimension, ticker
        )
        _validate_string_or_none(value["name"], stage_name, dimension, ticker)
        _validate_string_or_none(value["industry"], stage_name, dimension, ticker)
    elif dimension == "financials":
        if (
            not isinstance(value["years"], list)
            or any(not isinstance(year, str) for year in value["years"])
            or not isinstance(value["income"], Mapping)
            or set(value["income"]) != {"net_profit"}
            or not isinstance(value["balance_sheet"], Mapping)
            or set(value["balance_sheet"])
            != {"TOTAL_ASSETS", "TOTAL_CURRENT_LIAB", "TOTAL_NONCURRENT_LIAB"}
            or not isinstance(value["cash_flow"], Mapping)
            or set(value["cash_flow"]) != {"NETCASH_OPERATE"}
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 {stage_name} financials nested fields are invalid for {ticker}"
            )
        for nested in (
            value["income"]["net_profit"],
            value["balance_sheet"]["TOTAL_ASSETS"],
            value["balance_sheet"]["TOTAL_CURRENT_LIAB"],
            value["balance_sheet"]["TOTAL_NONCURRENT_LIAB"],
            value["cash_flow"]["NETCASH_OPERATE"],
        ):
            _validate_number_list(nested, stage_name, dimension, ticker)
        expected_length = len(value["years"])
        if any(
            len(nested) != expected_length
            for nested in (
                value["income"]["net_profit"],
                value["balance_sheet"]["TOTAL_ASSETS"],
                value["balance_sheet"]["TOTAL_CURRENT_LIAB"],
                value["balance_sheet"]["TOTAL_NONCURRENT_LIAB"],
                value["cash_flow"]["NETCASH_OPERATE"],
            )
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 {stage_name} financials series lengths are invalid for {ticker}"
            )
    elif dimension == "risk":
        _validate_number_or_none(
            value["pledge_ratio"], stage_name, dimension, ticker
        )
        _validate_string_or_none(
            value["pledge_status"], stage_name, dimension, ticker
        )
        _validate_string_or_none(
            value["audit_opinion"], stage_name, dimension, ticker
        )
    elif dimension == "valuation":
        for key in ("pe_ttm", "pb", "pe_percentile_5y"):
            _validate_number_or_none(value[key], stage_name, dimension, ticker)
        _validate_number_list(
            value["pe_history"], stage_name, dimension, ticker
        )
    else:
        _validate_number_list(value["close"], stage_name, dimension, ticker)
        _validate_number_list(
            value["turnover_rate"], stage_name, dimension, ticker
        )


def _validate_number_or_none(
    value: Any,
    stage_name: str,
    dimension: str,
    ticker: str,
) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise SmallSampleUserReviewInputError(
            f"M1.2 {stage_name} {dimension} nested value is invalid for {ticker}"
        )


def _validate_string_or_none(
    value: Any,
    stage_name: str,
    dimension: str,
    ticker: str,
) -> None:
    if value is not None and not isinstance(value, str):
        raise SmallSampleUserReviewInputError(
            f"M1.2 {stage_name} {dimension} nested value is invalid for {ticker}"
        )


def _validate_number_list(
    value: Any,
    stage_name: str,
    dimension: str,
    ticker: str,
) -> None:
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, (int, float))
        for item in value
    ):
        raise SmallSampleUserReviewInputError(
            f"M1.2 {stage_name} {dimension} nested list is invalid for {ticker}"
        )


def _validate_ticker_semantics(
    row: Mapping[str, Any],
    ticker: str,
) -> None:
    stage_statuses = row["stage_statuses"]
    if row["candidate"]:
        if (
            dict(stage_statuses) != {"A": "passed", "B": "passed", "C": "passed"}
            or row["quality_status"] != "complete"
            or row["exclusion"] is not None
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 candidate/stage/exclusion semantics are invalid for {ticker}"
            )
    elif row["exclusion"] is None:
        raise SmallSampleUserReviewInputError(
            f"M1.2 non-candidate must expose exclusion for {ticker}"
        )
    if row["exclusion"] is not None:
        _validate_exclusion(row["exclusion"], ticker)
    if stage_statuses["A"] != "passed" and (
        stage_statuses["B"] != "not_reached"
        or stage_statuses["C"] != "not_reached"
    ):
        raise SmallSampleUserReviewInputError(
            f"M1.2 stage progression is invalid for {ticker}"
        )
    if stage_statuses["B"] != "passed" and stage_statuses["C"] != "not_reached":
        raise SmallSampleUserReviewInputError(
            f"M1.2 stage progression is invalid for {ticker}"
        )


def _validate_source_summary(source: Mapping[str, Any]) -> None:
    summary = source["summary"]
    required = {
        "input_count",
        "stage_counts",
        "candidate_count",
        "quality_status_counts",
        "exclusion_reason_counts",
    }
    if not isinstance(summary, Mapping) or set(summary) != required:
        raise SmallSampleUserReviewInputError("M1.2 summary fields are invalid")
    rows = source["tickers"]
    if (
        not isinstance(summary["input_count"], int)
        or summary["input_count"] != len(rows)
        or not isinstance(summary["candidate_count"], int)
        or isinstance(summary["candidate_count"], bool)
        or summary["candidate_count"] != sum(row["candidate"] for row in rows)
    ):
        raise SmallSampleUserReviewInputError(
            "M1.2 summary counts are inconsistent"
        )
    actual_quality = summary["quality_status_counts"]
    if (
        not isinstance(actual_quality, Mapping)
        or any(
            not isinstance(key, str)
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for key, value in actual_quality.items()
        )
        or dict(sorted(actual_quality.items()))
        != dict(sorted(Counter(row["quality_status"] for row in rows).items()))
    ):
        raise SmallSampleUserReviewInputError(
            "M1.2 summary quality_status_counts is inconsistent"
        )
    actual_exclusion = summary["exclusion_reason_counts"]
    if (
        not isinstance(actual_exclusion, Mapping)
        or any(
            not isinstance(key, str)
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for key, value in actual_exclusion.items()
        )
        or dict(sorted(actual_exclusion.items()))
        != dict(
            sorted(
                Counter(
                    row["exclusion"]["reason_code"]
                    for row in rows
                    if row["exclusion"] is not None
                ).items()
            )
        )
    ):
        raise SmallSampleUserReviewInputError(
            "M1.2 summary exclusion_reason_counts is inconsistent"
        )
    stage_counts = summary["stage_counts"]
    if not isinstance(stage_counts, Mapping) or set(stage_counts) != {"A", "B", "C"}:
        raise SmallSampleUserReviewInputError(
            "M1.2 summary stage_counts is invalid"
        )
    for stage in ("A", "B", "C"):
        counts = stage_counts[stage]
        if (
            not isinstance(counts, Mapping)
            or set(counts) != {"input_count", "passed_count", "failed_count"}
            or any(
                not isinstance(counts[key], int)
                or isinstance(counts[key], bool)
                or counts[key] < 0
                for key in counts
            )
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 summary stage_counts.{stage} is invalid"
            )
        expected_input = sum(
            row["stage_statuses"][stage] != "not_reached" for row in rows
        )
        expected_passed = sum(
            row["stage_statuses"][stage] == "passed" for row in rows
        )
        if (
            counts["input_count"] != expected_input
            or counts["passed_count"] != expected_passed
            or counts["failed_count"] != expected_input - expected_passed
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 summary stage_counts.{stage} is inconsistent"
            )


def _validate_exclusion(
    exclusion: Mapping[str, Any],
    ticker: str,
) -> None:
    required = {"stage", "dimension", "status", "reason", "reason_code"}
    optional = {"failed_filters", "failed_gates"}
    if set(exclusion) - required - optional or not required.issubset(exclusion):
        raise SmallSampleUserReviewInputError(
            f"M1.2 exclusion structure is invalid for {ticker}"
        )
    if (
        exclusion["stage"] not in {"A", "B", "C"}
        or not isinstance(exclusion["dimension"], (str, type(None)))
        or not isinstance(exclusion["status"], str)
        or not isinstance(exclusion["reason"], str)
        or not isinstance(exclusion["reason_code"], str)
    ):
        raise SmallSampleUserReviewInputError(
            f"M1.2 exclusion values are invalid for {ticker}"
        )
    allowed_dimensions = {
        "A": {"basic", None},
        "B": {"financials", "risk", "financials/risk", None},
        "C": {"valuation", "kline", "valuation/kline", "screening", None},
    }[exclusion["stage"]]
    if exclusion["dimension"] not in allowed_dimensions:
        raise SmallSampleUserReviewInputError(
            f"M1.2 exclusion dimension is invalid for {ticker}"
        )
    for key in optional:
        if key in exclusion and (
            not isinstance(exclusion[key], list)
            or any(not isinstance(item, str) for item in exclusion[key])
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 exclusion.{key} is invalid for {ticker}"
            )


def _candidate_view(row: Mapping[str, Any]) -> dict[str, Any]:
    details = row["details"]
    scores = row["scores"]
    return {
        "ticker": row["ticker"],
        "name": details["name"],
        "industry": details["industry"],
        "factor_scores": scores["factor_scores"],
        "anti_trap": scores["anti_trap"],
        "adjusted_composite": scores["adjusted_composite"],
        "f_score": details["f_score"],
        "graham_number": details["graham_number"],
        "pe_ttm": details["pe_ttm"],
        "pb": details["pb"],
        "pledge_ratio": details["pledge_ratio"],
        "heat_filter": scores["heat_filter"],
    }


def _validate_canonical_fields(
    canonical_fields: Mapping[str, Any],
    ticker: str,
) -> None:
    for field_name, field in canonical_fields.items():
        if (
            not isinstance(field_name, str)
            or field_name not in _CANONICAL_FIELD_NAMES
            or not isinstance(field, Mapping)
            or set(field) != _CANONICAL_FIELD_FIELDS
            or not isinstance(field["status"], str)
            or field["status"] not in _CANONICAL_STATUSES
            or not isinstance(field["eligibility"], (str, type(None)))
            or field["eligibility"] not in _CANONICAL_ELIGIBILITIES
            or not isinstance(field["reason"], (str, type(None)))
            or not isinstance(field["provenance"], Mapping)
            or not isinstance(field["as_of"], (str, type(None)))
            or not isinstance(field["freshness"], (str, type(None)))
            or field["freshness"] not in _CANONICAL_FRESHNESS
            or not isinstance(field["available"], bool)
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 canonical_fields are invalid for {ticker}"
            )
        provenance = field["provenance"]
        if not provenance or (
            set(provenance) - _PROVENANCE_FIELDS
            or provenance.get("source") != "fixture/reference"
            or provenance.get("not_live_provider_evidence") is not True
            or any(
                key != "not_live_provider_evidence"
                and (
                    not isinstance(value, str)
                    or not value.strip()
                    or any(
                        marker in value.casefold()
                        for marker in ("live", "provider", "production")
                    )
                )
                for key, value in provenance.items()
            )
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 canonical_fields provenance is invalid for {ticker}"
            )
        if field["available"] and (
            field["status"] != "available" or field["freshness"] != "fresh"
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 canonical_fields availability is invalid for {ticker}"
            )
        _strict_json(field["value"])
        _strict_json(provenance)


def _validate_staged_evidence(source: Mapping[str, Any]) -> None:
    evidence = source["staged_evidence"]
    expected_keys = {
        "run_id",
        "input_ticker_set_hash",
        "stages",
        "ticker_evidence",
        "candidates",
        "evidence_path",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != expected_keys:
        raise SmallSampleUserReviewInputError(
            "M1.2 staged_evidence fields are invalid"
        )
    source_rows = source["tickers"]
    source_tickers = {row["ticker"] for row in source_rows}
    raw_by_canonical: dict[str, str] = {}
    if (
        evidence["run_id"] != source["run_id"]
        or evidence["input_ticker_set_hash"] != source["input_ticker_set_hash"]
        or not isinstance(evidence["stages"], Mapping)
        or set(evidence["stages"]) != {"A", "B", "C"}
        or not isinstance(evidence["ticker_evidence"], Mapping)
        or set(evidence["ticker_evidence"]) != source_tickers
        or not isinstance(evidence["candidates"], list)
    ):
        raise SmallSampleUserReviewInputError(
            "M1.2 staged_evidence identity or candidate set is inconsistent"
        )
    for ticker, item in evidence["ticker_evidence"].items():
        canonical_fields = (
            item.get("canonical_fields") if isinstance(item, Mapping) else None
        )
        if (
            not isinstance(item, Mapping)
            or set(item) != _TICKER_EVIDENCE_FIELDS
            or not isinstance(item["raw_ticker"], str)
            or canonical_ticker(item["raw_ticker"]) != ticker
            or not isinstance(canonical_fields, Mapping)
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 ticker_evidence is invalid for {ticker}"
            )
        _validate_canonical_fields(canonical_fields, ticker)
        if ticker in raw_by_canonical:
            raise SmallSampleUserReviewInputError(
                f"M1.2 ticker_evidence duplicates {ticker}"
            )
        raw_by_canonical[ticker] = item["raw_ticker"]
    actual_candidates: list[dict[str, Any]] = []
    for item in evidence["candidates"]:
        if not isinstance(item, Mapping) or set(item) != _CANDIDATE_FIELDS:
            raise SmallSampleUserReviewInputError(
                "M1.2 candidate structure is invalid"
            )
        try:
            candidate_ticker = canonical_ticker(item["ticker"])
        except (TypeError, ValueError) as exc:
            raise SmallSampleUserReviewInputError(
                "M1.2 candidate ticker is invalid"
            ) from exc
        if candidate_ticker != item["ticker"]:
            raise SmallSampleUserReviewInputError(
                "M1.2 candidate ticker must be canonical"
            )
        actual_candidates.append(dict(item))
    expected_candidates = [
        _candidate_view(row)
        for row in sorted(source_rows, key=lambda row: row["ticker"])
        if row["candidate"]
    ]
    if actual_candidates != expected_candidates:
        raise SmallSampleUserReviewInputError(
            "M1.2 candidate content is inconsistent"
        )
    expected_inputs = {
        "A": source_tickers,
        "B": {
            row["ticker"]
            for row in source_rows
            if row["stage_statuses"]["A"] == "passed"
        },
        "C": {
            row["ticker"]
            for row in source_rows
            if row["stage_statuses"]["B"] == "passed"
        },
    }
    expected_dimensions = {
        "A": ["basic"],
        "B": ["financials", "risk"],
        "C": ["valuation", "kline"],
    }
    expected_outputs = {
        stage_name: sorted(
            row["ticker"]
            for row in source_rows
            if row["stage_statuses"][stage_name] == "passed"
        )
        for stage_name in ("A", "B", "C")
    }
    for stage_name in ("A", "B", "C"):
        stage = evidence["stages"][stage_name]
        if not isinstance(stage, Mapping) or set(stage) != _STAGE_FIELDS:
            raise SmallSampleUserReviewInputError(
                f"M1.2 staged_evidence.{stage_name} structure is invalid"
            )
        if (
            stage["stage"] != stage_name
            or stage["run_id"] != source["run_id"]
            or not isinstance(stage["input_tickers"], list)
            or not isinstance(stage["output_tickers"], list)
            or not isinstance(stage["requested_dimensions"], list)
            or not all(isinstance(item, str) for item in stage["requested_dimensions"])
            or not isinstance(stage["canonical_input_tickers"], list)
            or not isinstance(stage["canonical_output_tickers"], list)
            or any(
                not isinstance(item, str)
                or item != canonical_ticker(item)
                for item in stage["canonical_input_tickers"]
            )
            or any(
                not isinstance(item, str)
                or item != canonical_ticker(item)
                for item in stage["canonical_output_tickers"]
            )
            or not isinstance(stage["passed_count"], int)
            or isinstance(stage["passed_count"], bool)
            or not isinstance(stage["failed_count"], int)
            or isinstance(stage["failed_count"], bool)
            or stage["canonical_input_tickers"] != sorted(expected_inputs[stage_name])
            or stage["canonical_output_tickers"] != expected_outputs[stage_name]
            or stage["canonical_output_tickers"]
            != sorted(set(stage["canonical_output_tickers"]))
            or not set(stage["canonical_output_tickers"]).issubset(
                set(stage["canonical_input_tickers"])
            )
            or stage["passed_count"]
            != len(stage["canonical_output_tickers"])
            or stage["failed_count"]
            != len(stage["canonical_input_tickers"])
            - stage["passed_count"]
            or not isinstance(stage["requests"], list)
            or not isinstance(stage["provider_calls"], list)
            or not isinstance(stage["cache_hits"], list)
            or stage["provider_calls"]
            or stage["cache_hits"]
            or not isinstance(stage["failures"], list)
            or not isinstance(stage["dimension_results"], Mapping)
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 staged_evidence.{stage_name} semantics are invalid"
            )
        expected_input_list = sorted(expected_inputs[stage_name])
        expected_output_list = expected_outputs[stage_name]
        expected_raw_input = [
            raw_by_canonical[ticker] for ticker in expected_input_list
        ]
        expected_raw_output = [
            raw_by_canonical[ticker] for ticker in expected_output_list
        ]
        if (
            stage["requested_dimensions"] != expected_dimensions[stage_name]
            or stage["input_tickers"] != expected_raw_input
            or stage["output_tickers"] != expected_raw_output
            or stage["requests"]
            != [
                {
                    "tickers": expected_raw_input,
                    "dimensions": expected_dimensions[stage_name],
                }
            ]
            or set(stage["dimension_results"]) != set(expected_raw_input)
            or any(
                not isinstance(result, Mapping)
                or set(result) != set(expected_dimensions[stage_name])
                for result in stage["dimension_results"].values()
            )
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 staged_evidence.{stage_name} ticker/dimension binding is invalid"
            )
        for raw_ticker, result in stage["dimension_results"].items():
            for dimension in expected_dimensions[stage_name]:
                _validate_dimension_payload(
                    dimension,
                    result[dimension],
                    canonical_ticker(raw_ticker),
                    stage_name,
                )
        for failure in stage["failures"]:
            if (
                not isinstance(failure, Mapping)
                or set(failure) - _FAILURE_FIELDS - _FAILURE_OPTIONAL_FIELDS
                or not _FAILURE_FIELDS.issubset(failure)
                or not isinstance(failure["ticker"], str)
                or canonical_ticker(failure["ticker"])
                not in set(stage["canonical_input_tickers"])
                or not isinstance(failure["dimension"], (str, type(None)))
                or (
                    failure["dimension"] is not None
                    and failure["dimension"]
                    not in set(expected_dimensions[stage_name])
                    | {"financials/risk", "valuation/kline", "screening"}
                )
                or not isinstance(failure["status"], str)
                or failure["status"] not in _FAILURE_STATUSES
                or not all(
                    isinstance(failure[key], str)
                    for key in ("status", "reason")
                )
                or (
                    "failed_filters" in failure
                    and (
                        not isinstance(failure["failed_filters"], list)
                        or any(
                            not isinstance(item, str)
                            for item in failure["failed_filters"]
                        )
                    )
                )
            ):
                raise SmallSampleUserReviewInputError(
                    f"M1.2 staged_evidence.{stage_name} failure is invalid"
                )
        _validate_failure_payload_bindings(stage, stage_name)
        expected_failures = []
        for row in source_rows:
            exclusion = row["exclusion"]
            if exclusion is None or exclusion["stage"] != stage_name:
                continue
            expected_failures.append(
                {
                    "ticker": raw_by_canonical[row["ticker"]],
                    "dimension": exclusion["dimension"],
                    "status": exclusion["status"],
                    "reason": exclusion["reason"],
                    "reason_code": exclusion["reason_code"],
                    **(
                        {"failed_filters": exclusion["failed_filters"]}
                        if "failed_filters" in exclusion
                        else {}
                    ),
                }
            )
        if len(stage["failures"]) != len(expected_failures):
            raise SmallSampleUserReviewInputError(
                f"M1.2 staged_evidence.{stage_name} failures are not bound to results"
            )
        for actual, expected in zip(stage["failures"], expected_failures):
            if any(
                actual[key] != expected[key]
                for key in ("ticker", "dimension", "status")
            ):
                raise SmallSampleUserReviewInputError(
                    f"M1.2 staged_evidence.{stage_name} failure binding is invalid"
                )
            reason_matches = actual["reason"] == expected["reason"] or (
                expected["reason_code"] == "hard_gates_failed"
                and actual["reason"] == f"stage_{stage_name}_filter_failed"
            )
            if not reason_matches:
                raise SmallSampleUserReviewInputError(
                    f"M1.2 staged_evidence.{stage_name} failure reason is invalid"
                )
            if actual.get("failed_filters") != expected.get("failed_filters"):
                raise SmallSampleUserReviewInputError(
                    f"M1.2 staged_evidence.{stage_name} failure metadata is invalid"
                )
    if evidence["evidence_path"] is not None and not isinstance(
        evidence["evidence_path"], str
    ):
        raise SmallSampleUserReviewInputError(
            "M1.2 staged_evidence.evidence_path is invalid"
        )


def _validate_cross_source_semantics(source: Mapping[str, Any]) -> None:
    rows = source["tickers"]
    evidence = source["staged_evidence"]
    for stage_name, stage in evidence["stages"].items():
        failure_tickers = {
            canonical_ticker(failure["ticker"])
            for failure in stage["failures"]
        }
        for raw_ticker, result in stage["dimension_results"].items():
            if any(
                isinstance(value, Mapping) and value.get("__error__") is True
                for value in result.values()
            ) and canonical_ticker(raw_ticker) not in failure_tickers:
                raise SmallSampleUserReviewInputError(
                    f"M1.2 dimension error is not represented by staged failure: "
                    f"{raw_ticker}"
                )
    for row in rows:
        ticker = row["ticker"]
        statuses = row["stage_statuses"]
        first_failed = next(
            (stage for stage in ("A", "B", "C") if statuses[stage] != "passed"),
            None,
        )
        if row["candidate"]:
            if first_failed is not None:
                raise SmallSampleUserReviewInputError(
                    f"M1.2 candidate has a failed stage: {ticker}"
                )
            if any(
                canonical_ticker(failure["ticker"]) == ticker
                for stage in evidence["stages"].values()
                for failure in stage["failures"]
            ):
                raise SmallSampleUserReviewInputError(
                    f"M1.2 candidate has a staged failure: {ticker}"
                )
            continue
        if first_failed is None:
            raise SmallSampleUserReviewInputError(
                f"M1.2 non-candidate has no failed stage: {ticker}"
            )
        exclusion = row["exclusion"]
        if exclusion["stage"] != first_failed:
            raise SmallSampleUserReviewInputError(
                f"M1.2 exclusion is not first failure for {ticker}"
            )
        matching = [
            failure
            for failure in evidence["stages"][first_failed]["failures"]
            if canonical_ticker(failure["ticker"]) == ticker
        ]
        if len(matching) != 1:
            raise SmallSampleUserReviewInputError(
                f"M1.2 exclusion has no unique staged failure for {ticker}"
            )
        failure = matching[0]
        if any(
            failure[key] != exclusion[key]
            for key in ("dimension", "status")
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 exclusion does not match staged failure for {ticker}"
            )
        if not (
            failure["reason"] == exclusion["reason"]
            or (
                exclusion["reason_code"] == "hard_gates_failed"
                and failure["reason"] == f"stage_{first_failed}_filter_failed"
            )
        ):
            raise SmallSampleUserReviewInputError(
                f"M1.2 exclusion reason does not match staged failure for {ticker}"
            )
        if (
            failure["reason"] == f"stage_{first_failed}_filter_failed"
            and exclusion["reason"].startswith("hard_gates_failed:")
        ):
            expected_reason_code = "hard_gates_failed"
        elif failure["reason"].endswith("_filter_failed"):
            expected_reason_code = failure["reason"]
        else:
            expected_reason_code = failure["status"]
        if exclusion["reason_code"] != expected_reason_code:
            raise SmallSampleUserReviewInputError(
                f"M1.2 exclusion reason_code does not match staged failure for {ticker}"
            )
        if exclusion["reason_code"] == "hard_gates_failed":
            failed_gates = exclusion.get("failed_gates")
            if (
                not isinstance(failed_gates, list)
                or not failed_gates
                or any(
                    not isinstance(gate, str)
                    or not re.fullmatch(r"H[1-8]", gate)
                    for gate in failed_gates
                )
                or len(set(failed_gates)) != len(failed_gates)
            ):
                raise SmallSampleUserReviewInputError(
                    f"M1.2 exclusion failed_gates are invalid for {ticker}"
                )
            expected_gates = _recompute_failed_gates(
                first_failed,
                source,
                ticker,
            )
            if failed_gates != expected_gates or (
                exclusion["reason"] != f"hard_gates_failed:{','.join(expected_gates)}"
            ):
                raise SmallSampleUserReviewInputError(
                    f"M1.2 exclusion failed_gates do not match rules for {ticker}"
                )
        if "failed_filters" in exclusion:
            if "failed_filters" not in failure or (
                exclusion["failed_filters"] != failure["failed_filters"]
            ):
                raise SmallSampleUserReviewInputError(
                    f"M1.2 exclusion failed_filters do not match staged failure for {ticker}"
                )
        if "failed_gates" in exclusion:
            if not exclusion["reason"].startswith("hard_gates_failed:"):
                raise SmallSampleUserReviewInputError(
                    f"M1.2 exclusion failed_gates are not bound for {ticker}"
                )
            expected_gates = exclusion["reason"].split(":", 1)[1].split(",")
            if exclusion["failed_gates"] != expected_gates:
                raise SmallSampleUserReviewInputError(
                    f"M1.2 exclusion failed_gates are not bound for {ticker}"
                )
    if evidence["evidence_path"] is not None and not isinstance(
        evidence["evidence_path"], str
    ):
        raise SmallSampleUserReviewInputError(
            "M1.2 staged_evidence.evidence_path is invalid"
        )


def _validate_failure_payload_bindings(
    stage: Mapping[str, Any],
    stage_name: str,
) -> None:
    for failure in stage["failures"]:
        dimension = failure["dimension"]
        if dimension is None or failure["status"] == "not_evaluated":
            continue
        result = stage["dimension_results"][failure["ticker"]]
        components = dimension.split("/")
        has_unavailable_payload = any(
            isinstance(result.get(component), Mapping)
            and (
                result[component].get("__error__") is True
                or result[component].get("status") in _FAILURE_STATUSES
            )
            for component in components
        )
        if not has_unavailable_payload:
            raise SmallSampleUserReviewInputError(
                f"M1.2 staged_evidence.{stage_name} failure has no matching "
                f"unavailable payload for {failure['ticker']}"
            )


def _recompute_failed_gates(
    stage_name: str,
    source: Mapping[str, Any],
    ticker: str,
) -> list[str]:
    evidence = source["staged_evidence"]
    raw_ticker = evidence["ticker_evidence"][ticker]["raw_ticker"]
    basic = evidence["stages"]["A"]["dimension_results"][raw_ticker]["basic"]
    if stage_name == "A":
        gates: list[str] = []
        if "ST" in str(basic["name"]).upper():
            gates.append("H1")
        if basic["market_cap"] < 5e9:
            gates.append("H3")
        if basic["industry"] in {"银行", "证券", "保险", "多元金融"}:
            gates.append("H4")
        if basic["pe"] < 0:
            gates.append("H8")
        return gates
    if stage_name == "B":
        b_results = evidence["stages"]["B"]["dimension_results"][raw_ticker]
        financials = b_results["financials"]
        risk = b_results["risk"]
        gates = []
        name = basic["name"]
        if "ST" in name.upper():
            gates.append("H1")
        years = financials["years"]
        if len(years) < 3:
            gates.append("H2")
        if basic["market_cap"] < 5e9:
            gates.append("H3")
        if basic["industry"] in {"银行", "证券", "保险", "多元金融"}:
            gates.append("H4")
        if risk["pledge_ratio"] is not None and risk["pledge_ratio"] > 70:
            gates.append("H6")
        if risk["audit_opinion"] in {"保留意见", "无法表示意见", "否定意见"}:
            gates.append("H7")
        if basic["pe"] < 0:
            gates.append("H8")
        return gates
    return []


def _validate_optional_markdown(
    markdown_path: str | Path | None,
    source: Mapping[str, Any],
) -> str | None:
    if markdown_path is None:
        return None
    path = Path(markdown_path)
    if not path.is_file():
        raise SmallSampleUserReviewInputError(
            "optional M1.2 Markdown path must point to an existing file"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SmallSampleUserReviewInputError(
            "optional M1.2 Markdown cannot be read"
        ) from exc
    expected_markers = {
        "run_id": f"- run_id: `{source['run_id']}`",
        "profile_version": f"- profile_version: `{source['profile_version']}`",
        "input_ticker_set_hash": (
            f"- input_ticker_set_hash: `{source['input_ticker_set_hash']}`"
        ),
        "as_of": f"- as_of: `{source['as_of']}`",
        "artifact_type": "- artifact_type: `fixture/reference`",
        "mode": "- mode: `simulated/development`",
        "capability_status": "- capability_status: `not_evidence`",
        "gate_status": "- gate_status: `not_passed`",
    }
    for key, expected in expected_markers.items():
        identity_lines = [
            line for line in text.splitlines() if line.startswith(f"- {key}: ")
        ]
        if identity_lines != [expected]:
            raise SmallSampleUserReviewInputError(
                "optional M1.2 Markdown identity does not match JSON"
            )
    if text != _render_m1_small_sample_markdown(source):
        raise SmallSampleUserReviewInputError(
            "optional M1.2 Markdown content does not match JSON"
        )
    return str(path.resolve())


def _render_m1_small_sample_markdown(result: Mapping[str, Any]) -> str:
    """纯标准库复现 M1.2 renderer，避免加载 provider runtime。"""
    summary = result["summary"]
    lines = [
        "# G1 小样本筛选结果",
        "",
        f"- run_id: `{result['run_id']}`",
        f"- profile_version: `{result['profile_version']}`",
        f"- input_ticker_set_hash: `{result['input_ticker_set_hash']}`",
        f"- as_of: `{result['as_of']}`",
        "- artifact_type: `fixture/reference`",
        "- mode: `simulated/development`",
        "- capability_status: `not_evidence`",
        "- gate_status: `not_passed`",
        *[
            f"- provenance.{key}: `{_m1_provenance_value(value)}`"
            for key, value in sorted(result["provenance"].items())
        ],
        "",
        "## 汇总",
        "",
        f"- 输入股票：{summary['input_count']}",
        f"- 最终候选：{summary['candidate_count']}",
        f"- 质量状态：{_m1_format_counts(summary['quality_status_counts'])}",
        "",
        "## 逐票结果",
        "",
        "| ticker | A | B | C | quality | candidate | composite | f_score | PE/PB | exclusion |",
        "|---|---|---|---|---|---:|---:|---:|---|---|",
    ]
    for item in result["tickers"]:
        exclusion = item["exclusion"] or {}
        reason = exclusion.get("reason", "")
        score = item["scores"].get("adjusted_composite")
        details = item["details"]
        pe_pb = "/".join(
            _m1_display_number(details.get(key))
            for key in ("pe_ttm", "pb")
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    item["ticker"],
                    item["stage_statuses"]["A"],
                    item["stage_statuses"]["B"],
                    item["stage_statuses"]["C"],
                    item["quality_status"],
                    "yes" if item["candidate"] else "no",
                    _m1_display_number(score),
                    _m1_display_number(details.get("f_score")),
                    pe_pb,
                    _m1_markdown_cell(reason),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Fixture 边界",
            "",
            "本产物仅用于离线小样本 MVP 的人工阅读与复核，不是 provider evidence，也不代表 G1 Capability Gate 通过。",
            "",
        ]
    )
    return "\n".join(lines)


def _m1_format_counts(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def _m1_markdown_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def _m1_display_number(value: Any) -> str:
    return "" if value is None else str(value)


def _m1_provenance_value(value: Any) -> str:
    if isinstance(value, str):
        return value.replace("`", "\\`")
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _build_ticker_reviews(
    rows: list[Mapping[str, Any]],
    reviews: Mapping[str, Mapping[str, Mapping[str, Any]]] | None,
) -> list[dict[str, Any]]:
    source_tickers = [row["ticker"] for row in rows]
    if reviews is None:
        return [
            {
                "ticker": ticker,
                "source_result": deepcopy(row),
                "dimensions": {
                    dimension: _template_feedback()
                    for dimension in REVIEW_DIMENSIONS
                },
            }
            for ticker, row in zip(source_tickers, rows)
        ]
    if not isinstance(reviews, Mapping):
        raise SmallSampleUserReviewInputError("reviews must be an object")
    normalized_reviews: dict[str, Mapping[str, Any]] = {}
    for raw_ticker, dimensions in reviews.items():
        try:
            ticker = canonical_ticker(raw_ticker)
        except (TypeError, ValueError) as exc:
            raise SmallSampleUserReviewInputError(
                f"review ticker is invalid: {raw_ticker!r}"
            ) from exc
        if ticker in normalized_reviews:
            raise SmallSampleUserReviewInputError(
                f"reviews contain duplicate canonical ticker: {ticker}"
            )
        normalized_reviews[ticker] = dimensions
    if set(normalized_reviews) != set(source_tickers):
        raise SmallSampleUserReviewInputError(
            "reviews must contain exactly the M1.2 canonical tickers"
        )
    result: list[dict[str, Any]] = []
    for ticker in source_tickers:
        dimensions = normalized_reviews[ticker]
        if not isinstance(dimensions, Mapping) or set(dimensions) != set(
            REVIEW_DIMENSIONS
        ):
            raise SmallSampleUserReviewInputError(
                f"reviews.{ticker} must contain exactly the four dimensions"
            )
        result.append(
            {
                "ticker": ticker,
                "source_result": deepcopy(
                    next(row for row in rows if row["ticker"] == ticker)
                ),
                "dimensions": {
                    dimension: _validate_feedback(
                        ticker,
                        dimension,
                        dimensions[dimension],
                    )
                    for dimension in REVIEW_DIMENSIONS
                },
            }
        )
    return result


def _template_feedback() -> dict[str, Any]:
    return {
        "status": "not_evaluable",
        "feedback": "",
        "question": "",
        "issue": "",
        "corrected_value": None,
        "suggested_action": "",
    }


def _validate_feedback(
    ticker: str,
    dimension: str,
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SmallSampleUserReviewInputError(
            f"reviews.{ticker}.{dimension} must be an object"
        )
    unknown = sorted(set(value) - _FEEDBACK_FIELDS)
    if unknown:
        raise SmallSampleUserReviewInputError(
            f"reviews.{ticker}.{dimension} contains unknown fields: {unknown}"
        )
    status = value.get("status")
    if not isinstance(status, str) or status not in FEEDBACK_STATUSES:
        raise SmallSampleUserReviewInputError(
            f"reviews.{ticker}.{dimension}.status is invalid"
        )
    feedback = value.get("feedback", "")
    question = value.get("question", "")
    issue = value.get("issue", "")
    suggested_action = value.get("suggested_action", "")
    for field, field_value in (
        ("feedback", feedback),
        ("question", question),
        ("issue", issue),
        ("suggested_action", suggested_action),
    ):
        if not isinstance(field_value, str):
            raise SmallSampleUserReviewInputError(
                f"reviews.{ticker}.{dimension}.{field} must be a string"
            )
    if not feedback.strip():
        raise SmallSampleUserReviewInputError(
            f"reviews.{ticker}.{dimension}.feedback is required"
        )
    if status != "accepted" and not question.strip() and not issue.strip():
        raise SmallSampleUserReviewInputError(
            f"reviews.{ticker}.{dimension} requires question or issue"
        )
    corrected_value = value.get("corrected_value")
    _strict_json(corrected_value)
    return {
        "status": status,
        "feedback": feedback,
        "question": question,
        "issue": issue,
        "corrected_value": deepcopy(corrected_value),
        "suggested_action": suggested_action,
    }


def _validate_summary(value: Mapping[str, Any] | None) -> dict[str, list[str]]:
    if value is None:
        return {key: [] for key in sorted(_SUMMARY_FIELDS)}
    if not isinstance(value, Mapping):
        raise SmallSampleUserReviewInputError("summary must be an object")
    unknown = sorted(set(value) - _SUMMARY_FIELDS)
    if unknown:
        raise SmallSampleUserReviewInputError(
            f"summary contains unknown fields: {unknown}"
        )
    result: dict[str, list[str]] = {}
    for key in sorted(_SUMMARY_FIELDS):
        raw_items = value.get(key, [])
        if not isinstance(raw_items, list) or any(
            not isinstance(item, str) or not item.strip()
            for item in raw_items
        ):
            raise SmallSampleUserReviewInputError(
                f"summary.{key} must be a list of non-empty strings"
            )
        if key.endswith("_tickers"):
            normalized: list[str] = []
            for item in raw_items:
                try:
                    normalized.append(canonical_ticker(item))
                except (TypeError, ValueError) as exc:
                    raise SmallSampleUserReviewInputError(
                        f"summary.{key} contains invalid ticker"
                    ) from exc
            result[key] = sorted(set(normalized))
        else:
            result[key] = sorted(raw_items)
    return result


def _summarize_feedback(
    ticker_reviews: list[Mapping[str, Any]],
) -> dict[str, Any]:
    statuses = Counter(
        dimension["status"]
        for item in ticker_reviews
        for dimension in item["dimensions"].values()
    )
    dimension_status_counts: dict[str, dict[str, int]] = {}
    for dimension in REVIEW_DIMENSIONS:
        counts = Counter(
            item["dimensions"][dimension]["status"]
            for item in ticker_reviews
        )
        dimension_status_counts[dimension] = {
            status: counts.get(status, 0) for status in FEEDBACK_STATUSES
        }
    return {
        "status_counts": {
            status: statuses.get(status, 0)
            for status in FEEDBACK_STATUSES
        },
        "dimension_status_counts": dimension_status_counts,
        "question_or_problem_tickers": sorted(
            {
                item["ticker"]
                for item in ticker_reviews
                if any(
                    dimension["status"] in {"question", "problem"}
                    for dimension in item["dimensions"].values()
                )
            }
        ),
    }


def _markdown_list(items: list[str]) -> list[str]:
    return [
        f"- {_markdown_cell(item)}" if item else "- （未填写）"
        for item in items
    ] or ["- （未填写）"]


def _markdown_cell(value: Any) -> str:
    if value is None or value == "":
        return "（未填写）"
    if isinstance(value, (Mapping, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    escaped = html.escape(str(value), quote=False)
    return (
        escaped.replace("\\", "&#92;")
        .replace("`", "&#96;")
        .replace("|", "\\|")
        .replace("\r\n", "<br>")
        .replace("\r", "<br>")
        .replace("\n", "<br>")
    )


def _sha256(value: Any) -> str:
    serialized = _strict_json(value)
    return hashlib.sha256(
        json.dumps(
            serialized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _strict_json(value: Any) -> Any:
    try:
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SmallSampleUserReviewInputError(
            "review value must be strict JSON"
        ) from exc
    return value
