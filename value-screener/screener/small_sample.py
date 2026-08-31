"""离线小样本 G1 MVP runner。

该模块只消费调用方提供的 fixture envelope，并把它接入已有的
``run_staged_screening``。不会创建 BatchFetcher、读取全局缓存或调用外部服务。
"""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from data.lib.identity import canonical_ticker, compute_input_ticker_set_hash
from data.lib.production_paths import validate_g1_output_root
from .hard_gates import check_hard_gates
from .staged_runtime import (
    _score_candidates,
    run_staged_screening,
)


SCHEMA_VERSION = "g1-small-sample-run/v1"
_STAGES = ("A", "B", "C")
_FAILURE_STATUSES = {
    "conflict",
    "invalid_value",
    "not_evaluated",
    "not_supported_for_market",
    "permission_denied",
    "rate_limited",
    "record_not_found",
    "source_failed",
    "stale",
}
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_PROVENANCE_KEYS = {
    "source",
    "not_live_provider_evidence",
    "fixture_id",
    "dataset_hash",
    "reader",
}


class FixtureFetcher:
    """为 staged runtime 提供内存 fixture，不具备 provider/cache 能力。"""

    def __init__(self, data: Mapping[str, Mapping[str, Any]]) -> None:
        self._data = dict(data)
        self.collected: dict[str, dict[str, Any]] = {}

    def fetch_all(
        self,
        tickers: list[str],
        *,
        dimensions: tuple[str, ...],
        telemetry: Any | None = None,
    ) -> dict[str, dict[str, Any]]:
        if telemetry is not None:
            telemetry.record_request(list(tickers), tuple(dimensions))
        result: dict[str, dict[str, Any]] = {}
        for ticker in tickers:
            canonical = canonical_ticker(ticker)
            ticker_data = self._data.get(canonical, {})
            result[ticker] = {}
            for dimension in dimensions:
                value = ticker_data.get(dimension)
                if value is None:
                    value = {
                        "__error__": True,
                        "error": f"fixture dimension missing: {dimension}",
                    }
                result[ticker][dimension] = value
                self.collected.setdefault(ticker, {})[dimension] = value
                if telemetry is not None and isinstance(value, Mapping) and value.get("__error__"):
                    telemetry.record_failure(
                        ticker,
                        dimension,
                        status="source_failed",
                        reason=str(value.get("error") or f"fixture failed: {dimension}"),
                    )
        return result


def run_small_sample(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """运行离线小样本 G1 筛选并返回完整、可渲染的结果。"""
    normalized = _validate_and_normalize_bundle(bundle)
    fixture_fetcher = FixtureFetcher(normalized["data"])
    staged = run_staged_screening(
        normalized["tickers"],
        fetcher=fixture_fetcher,
        run_id=normalized["run_id"],
    )
    raw_tickers = staged.stages["C"].input_tickers
    canonical_by_raw = {
        raw_ticker: canonical_ticker(raw_ticker)
        for raw_ticker in raw_tickers
    }
    scored_rows, _ = _score_candidates(
        fixture_fetcher.collected,
        raw_tickers,
        canonical_by_raw=canonical_by_raw,
    )
    preheat_scores = {item["ticker"]: item for item in scored_rows}
    ticker_results = _build_ticker_results(
        staged,
        normalized["tickers"],
        normalized["data"],
        preheat_scores,
    )
    stage_summary = {
        stage: {
            "input_count": len(staged.stages[stage].canonical_input_tickers),
            "passed_count": staged.stages[stage].passed_count,
            "failed_count": staged.stages[stage].failed_count,
        }
        for stage in _STAGES
    }
    quality_counts = Counter(item["quality_status"] for item in ticker_results)
    exclusion_counts = Counter(
        item["exclusion"]["reason_code"]
        for item in ticker_results
        if item["exclusion"] is not None
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "fixture/reference",
        "mode": "simulated/development",
        "capability_status": "not_evidence",
        "gate_status": "not_passed",
        "run_id": normalized["run_id"],
        "profile_version": normalized["profile_version"],
        "input_ticker_set_hash": normalized["input_ticker_set_hash"],
        "as_of": normalized["as_of"],
        "provenance": normalized["provenance"],
        "summary": {
            "input_count": len(normalized["tickers"]),
            "stage_counts": stage_summary,
            "candidate_count": sum(item["candidate"] for item in ticker_results),
            "quality_status_counts": dict(sorted(quality_counts.items())),
            "exclusion_reason_counts": dict(sorted(exclusion_counts.items())),
        },
        "tickers": ticker_results,
        "staged_evidence": staged.to_dict(),
    }


def render_small_sample_json(result: Mapping[str, Any]) -> str:
    """确定性 JSON renderer。"""
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_small_sample_markdown(result: Mapping[str, Any]) -> str:
    """确定性、面向用户复核的 Markdown renderer。"""
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
            f"- provenance.{key}: `{_markdown_cell(_provenance_value(value))}`"
            for key, value in sorted(result["provenance"].items())
        ],
        "",
        "## 汇总",
        "",
        f"- 输入股票：{summary['input_count']}",
        f"- 最终候选：{summary['candidate_count']}",
        f"- 质量状态：{_format_counts(summary['quality_status_counts'])}",
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
            _display_number(details.get(key))
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
                    _display_number(score),
                    _display_number(details.get("f_score")),
                    pe_pb,
                    _markdown_cell(reason),
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


def write_small_sample_artifacts(
    bundle: Mapping[str, Any],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """写入 run-scoped JSON/Markdown 产物。"""
    output_path = validate_g1_output_root(output_dir)
    result = run_small_sample(bundle)
    json_path = output_path / f"{result['run_id']}.json"
    markdown_path = output_path / f"{result['run_id']}.md"
    json_text = render_small_sample_json(result)
    markdown_text = render_small_sample_markdown(result)
    for path, expected in ((json_path, json_text), (markdown_path, markdown_text)):
        if path.exists() and path.read_text(encoding="utf-8") != expected:
            raise ValueError(
                f"immutable run artifact already exists with different content: {path}"
            )
    output_path.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output_path,
        prefix=f".{result['run_id']}.staging-",
    ) as staging_dir:
        staged_files = []
        for path, expected in (
            (json_path, json_text),
            (markdown_path, markdown_text),
        ):
            if path.exists():
                continue
            staged_path = Path(staging_dir) / path.name
            staged_path.write_text(expected, encoding="utf-8")
            staged_files.append((staged_path, path))
        for staged_path, path in staged_files:
            os.replace(staged_path, path)
    return json_path, markdown_path


def _validate_and_normalize_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, Mapping):
        raise ValueError("input bundle must be an object")
    required = (
        "schema_version",
        "artifact_type",
        "mode",
        "run_id",
        "profile_version",
        "input_ticker_set_hash",
        "as_of",
        "provenance",
        "tickers",
        "data",
    )
    missing = [key for key in required if key not in bundle]
    if missing:
        raise ValueError(f"input bundle missing required fields: {', '.join(missing)}")
    if bundle["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {bundle['schema_version']!r}")
    if bundle["artifact_type"] != "fixture/reference" or bundle["mode"] != "simulated/development":
        raise ValueError("input bundle must be fixture/reference and simulated/development")
    run_id = bundle["run_id"]
    if not isinstance(run_id, str) or not _SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a safe non-empty filename token")
    profile_version = bundle["profile_version"]
    as_of = bundle["as_of"]
    if not isinstance(profile_version, str) or not profile_version.strip():
        raise ValueError("profile_version is required")
    if not isinstance(as_of, str) or not as_of.strip():
        raise ValueError("as_of is required")

    provenance = bundle["provenance"]
    if not isinstance(provenance, Mapping):
        raise ValueError("provenance must be an object")
    if provenance.get("not_live_provider_evidence") is not True:
        raise ValueError("provenance must set not_live_provider_evidence=true")
    source = str(provenance.get("source", "")).strip().casefold()
    if source != "fixture/reference":
        raise ValueError(
            "provenance.source must be fixture/reference; "
            "live/provider/production sources are rejected"
        )
    unknown_keys = set(provenance) - _ALLOWED_PROVENANCE_KEYS
    if unknown_keys:
        raise ValueError(
            "provenance contains unknown fields: "
            + ", ".join(sorted(str(key) for key in unknown_keys))
        )
    for key, value in provenance.items():
        if key == "not_live_provider_evidence":
            continue
        if not isinstance(value, str):
            raise ValueError(f"provenance.{key} must be a string")
        if any(
            token in value.casefold()
            for token in ("live", "provider", "production")
        ):
            raise ValueError("fixture provenance contains forbidden marker")

    raw_tickers = bundle["tickers"]
    if not isinstance(raw_tickers, list) or not raw_tickers:
        raise ValueError("tickers must be a non-empty list")
    canonical_tickers = sorted({canonical_ticker(ticker) for ticker in raw_tickers})
    if len(canonical_tickers) < 5:
        raise ValueError("small sample requires at least 5 unique tickers")
    if len(canonical_tickers) > 20:
        raise ValueError("small sample supports at most 20 unique tickers")
    expected_hash = compute_input_ticker_set_hash(canonical_tickers)
    if bundle["input_ticker_set_hash"] != expected_hash:
        raise ValueError("input_ticker_set_hash does not match canonical ticker set")

    raw_data = bundle["data"]
    if not isinstance(raw_data, Mapping):
        raise ValueError("data must be an object")
    normalized_data: dict[str, Mapping[str, Any]] = {}
    for raw_ticker, dimensions in raw_data.items():
        canonical = canonical_ticker(str(raw_ticker))
        if not isinstance(dimensions, Mapping):
            raise ValueError(f"data[{raw_ticker!r}] must be an object")
        if canonical in normalized_data and normalized_data[canonical] != dimensions:
            raise ValueError(f"duplicate canonical data for {canonical}")
        normalized_data[canonical] = dimensions
    return {
        "run_id": run_id,
        "profile_version": profile_version,
        "as_of": as_of,
        "input_ticker_set_hash": expected_hash,
        "provenance": dict(provenance),
        "tickers": canonical_tickers,
        "data": normalized_data,
    }


def _build_ticker_results(
    staged: Any,
    tickers: list[str],
    data: Mapping[str, Mapping[str, Any]],
    preheat_scores: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates = {
        item["ticker"]: item
        for item in staged.candidates
        if isinstance(item, Mapping) and item.get("ticker")
    }
    results: list[dict[str, Any]] = []
    for ticker in sorted({canonical_ticker(value) for value in tickers}):
        candidate = candidates.get(ticker)
        exclusion = _first_exclusion(staged, ticker, data.get(ticker, {}))
        scored = preheat_scores.get(ticker)
        scores = {
            "factor_scores": (
                candidate.get("factor_scores")
                if candidate
                else scored.get("factor_scores") if scored else None
            ),
            "anti_trap": (
                candidate.get("anti_trap")
                if candidate
                else scored.get("anti_trap") if scored else None
            ),
            "heat_filter": candidate.get("heat_filter") if candidate else None,
            "adjusted_composite": (
                candidate.get("adjusted_composite")
                if candidate
                else scored.get("adjusted_composite") if scored else None
            ),
        }
        details = {
            "name": (
                candidate.get("name")
                if candidate
                else scored.get("name") if scored else None
            ),
            "industry": (
                candidate.get("industry")
                if candidate
                else scored.get("industry") if scored else None
            ),
            "f_score": (
                candidate.get("f_score")
                if candidate
                else scored.get("f_score") if scored else None
            ),
            "pe_ttm": (
                candidate.get("pe_ttm")
                if candidate
                else scored.get("pe_ttm") if scored else None
            ),
            "pb": (
                candidate.get("pb")
                if candidate
                else scored.get("pb") if scored else None
            ),
            "graham_number": (
                candidate.get("graham_number")
                if candidate
                else scored.get("graham_number") if scored else None
            ),
            "pledge_ratio": (
                candidate.get("pledge_ratio")
                if candidate
                else scored.get("pledge_ratio") if scored else None
            ),
        }
        results.append(
            {
                "ticker": ticker,
                "stage_statuses": {
                    stage: _stage_status(staged.stages[stage], ticker)
                    for stage in _STAGES
                },
                "candidate": candidate is not None,
                "quality_status": _quality_status(exclusion),
                "details": details,
                "scores": scores,
                "exclusion": exclusion,
            }
        )
    return results


def _stage_status(evidence: Any, ticker: str) -> str:
    if ticker in evidence.canonical_output_tickers:
        return "passed"
    if ticker in evidence.canonical_input_tickers:
        return "failed"
    return "not_reached"


def _first_exclusion(
    staged: Any,
    ticker: str,
    ticker_data: Mapping[str, Any],
) -> dict[str, Any] | None:
    for stage in _STAGES:
        evidence = staged.stages[stage]
        for failure in evidence.failures:
            raw_ticker = failure.get("ticker")
            if raw_ticker is None:
                continue
            if canonical_ticker(str(raw_ticker)) != ticker:
                continue
            exclusion = {
                "stage": stage,
                "dimension": failure.get("dimension"),
                "status": failure.get("status"),
                "reason": failure.get("reason"),
                "reason_code": _reason_code(failure),
            }
            if failure.get("failed_filters"):
                exclusion["failed_filters"] = list(failure["failed_filters"])
            if failure.get("reason") == f"stage_{stage}_filter_failed":
                failed_gates = _stage_filter_gates(stage, ticker_data)
                if failed_gates:
                    exclusion["failed_gates"] = failed_gates
                    exclusion["reason"] = (
                        f"hard_gates_failed:{','.join(failed_gates)}"
                    )
                    exclusion["reason_code"] = "hard_gates_failed"
            return exclusion
    return None


def _reason_code(failure: Mapping[str, Any]) -> str:
    reason = str(failure.get("reason") or "")
    if reason.endswith("_filter_failed"):
        return reason
    return str(failure.get("status") or "not_evaluated")


def _stage_filter_gates(stage: str, ticker_data: Mapping[str, Any]) -> list[str]:
    if stage == "A":
        basic = ticker_data.get("basic", {})
        if not isinstance(basic, Mapping):
            return []
        gates: list[str] = []
        name = str(basic.get("name") or "").upper()
        if "ST" in name:
            gates.append("H1")
        if basic.get("market_cap") is not None and basic["market_cap"] < 5e9:
            gates.append("H3")
        if basic.get("industry") in {"银行", "证券", "保险", "多元金融"}:
            gates.append("H4")
        if basic.get("pe") is not None and basic["pe"] < 0:
            gates.append("H8")
        return gates
    if stage == "B":
        result = check_hard_gates(dict(ticker_data))
        return list(result.get("failed_gates") or [])
    return []


def _quality_status(exclusion: Mapping[str, Any] | None) -> str:
    if exclusion is None or str(exclusion.get("reason", "")).endswith("_filter_failed"):
        return "complete"
    status = exclusion.get("status")
    if status in {"degraded", "partial", "stale"}:
        return "degraded"
    if status in _FAILURE_STATUSES:
        return "failed" if status == "source_failed" else "not_evaluable"
    return "not_evaluable"


def _format_counts(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def _markdown_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def _display_number(value: Any) -> str:
    return "" if value is None else str(value)


def _provenance_value(value: Any) -> str:
    if isinstance(value, str):
        return value.replace("`", "\\`")
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
