#!/usr/bin/env python3
"""f3f historical R1 crosstalk failure-repro harness.

G2 1.3 有界诊断：冻结并复现 600519.SH / 600900.SH 历史 R1 串台失败快照。
只做 fixture 回放与 dry-run，不改主 prompt、不改 debate 主流程、不调用真实
LLM；live 调用必须显式授权，未授权时本 harness 不会触碰 provider/LLM Gate。
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

VALUE_SCREENER_ROOT = Path(__file__).resolve().parents[2]
if str(VALUE_SCREENER_ROOT) not in sys.path:
    sys.path.insert(0, str(VALUE_SCREENER_ROOT))

from council.debate import _prepare_council_input
from council.llm import call_llm
from council.schema import AgentOutput
from council.verify_quality_gate import detect_circular_reference
from data.lib.audit_chain import payload_sha256
from data.lib.identity import canonical_ticker


EXPECTED_TICKERS = ("600519.SH", "600900.SH")
EXPECTED_SOURCE_SHA256 = (
    "244d063bbbf152621008b1d9606890cd84f3ad81e128755e73e53cdd89be7d4b"
)
EXPECTED_FIXTURE_SHA256_BY_TICKER = {
    "600519.SH": "56d30a120ffa434ca2e593ed640bd44959e40b5799110e2c52652c621d20d360",
    "600900.SH": "af11485cd574441ef7b70ea65d98b9f84b7ad0e3b48aeb3da9d218e7544d655e",
}
FIXTURE_PATHS = {
    "600519.SH": Path(__file__).resolve().parent / "f3f_600519_failure_snapshot.json",
    "600900.SH": Path(__file__).resolve().parent / "f3f_600900_failure_snapshot.json",
}


def _validate_sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return value


def _safe_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string")
    run_id = run_id.strip()
    if run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise ValueError("run_id must be a relative path leaf")
    return run_id


def load_verified_failure_snapshot(
    path: str | Path,
    expected_ticker: str | None = None,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    """Load a frozen historical failure snapshot and verify its binding."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"failure snapshot missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"failure snapshot is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError("failure snapshot must be a JSON object")

    freeze = data.get("freeze")
    if not isinstance(freeze, dict):
        raise ValueError("failure snapshot must include a freeze envelope")

    declared_ticker = freeze.get("canonical_ticker")
    if not isinstance(declared_ticker, str) or not declared_ticker.strip():
        raise ValueError("freeze.canonical_ticker is required")
    try:
        normalized_ticker = canonical_ticker(declared_ticker)
    except ValueError as exc:
        raise ValueError(f"freeze.canonical_ticker is invalid: {declared_ticker!r}") from exc
    if expected_ticker is not None and normalized_ticker != expected_ticker:
        raise ValueError(
            f"failure snapshot must bind to canonical ticker {expected_ticker}"
        )

    source_sha256 = _validate_sha256(freeze.get("source_sha256"), "freeze.source_sha256")
    if source_sha256 != EXPECTED_SOURCE_SHA256:
        raise ValueError("freeze.source_sha256 does not match expected source hash")
    input_snapshot = data.get("input_snapshot")
    if not isinstance(input_snapshot, dict) or "error" not in input_snapshot:
        raise ValueError("failure snapshot must include an insufficient_data input_snapshot")
    if payload_sha256(input_snapshot) != source_sha256:
        raise ValueError("input_snapshot does not match freeze.source_sha256")

    source_path = freeze.get("source_path")
    if source_root is not None and isinstance(source_path, str) and source_path:
        source_file = Path(source_root) / source_path
        if source_file.is_file():
            try:
                source_data = json.loads(source_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"source snapshot is not valid JSON: {source_file}") from exc
            if payload_sha256(source_data) != source_sha256:
                raise ValueError("source snapshot does not match freeze.source_sha256")

    return data


def create_failure_repro_envelope(
    snapshot: dict[str, Any],
    ticker: str,
    run_id: str,
    output_root: str | Path,
    model_configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind one frozen failure snapshot to a unique run identity and output root."""
    canonical = canonical_ticker(ticker)
    if canonical not in EXPECTED_FIXTURE_SHA256_BY_TICKER:
        raise ValueError(f"unsupported failure snapshot ticker: {canonical}")

    freeze = snapshot.get("freeze")
    if not isinstance(freeze, dict):
        raise ValueError("failure snapshot must include a freeze envelope")
    if canonical_ticker(freeze.get("canonical_ticker")) != canonical:
        raise ValueError(
            f"ticker mismatch: expected {canonical}, got {freeze.get('canonical_ticker')}"
        )
    source_sha256 = _validate_sha256(freeze.get("source_sha256"), "freeze.source_sha256")
    if source_sha256 != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            "source hash mismatch: expected "
            f"{EXPECTED_SOURCE_SHA256}, got {source_sha256}"
        )
    if payload_sha256(snapshot) != EXPECTED_FIXTURE_SHA256_BY_TICKER[canonical]:
        raise ValueError("frozen snapshot payload hash mismatch")

    input_snapshot = snapshot.get("input_snapshot")
    if not isinstance(input_snapshot, dict) or payload_sha256(input_snapshot) != source_sha256:
        raise ValueError("input_snapshot does not match freeze.source_sha256")

    safe_run_id = _safe_run_id(run_id)
    model_config = dict(model_configuration or {})
    return {
        "canonical_ticker": canonical,
        "run_id": safe_run_id,
        "source_sha256": source_sha256,
        "fixture_sha256": payload_sha256(snapshot),
        "input_snapshot_sha256": payload_sha256(input_snapshot),
        "output_root": Path(output_root).resolve(),
        "model_configuration": model_config,
    }


def run_mismatch_fail_closed(
    snapshot: dict[str, Any],
    ticker: str,
    run_id: str,
    output_root: str | Path,
    model_configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic branch: every envelope mismatch must fail before any LLM call."""
    cases: list[dict[str, str]] = []
    canonical = canonical_ticker(ticker)
    other_ticker = (
        "600900.SH" if canonical == "600519.SH" else "600519.SH"
    )

    def _check(case: str, data: dict[str, Any], run: str) -> None:
        try:
            create_failure_repro_envelope(
                data, ticker, run, output_root, model_configuration
            )
        except (ValueError, KeyError) as exc:
            cases.append({"case": case, "status": "fail_closed", "reason": str(exc)[:300]})
        else:
            cases.append({"case": case, "status": "leaked", "reason": "envelope accepted mismatch"})

    ticker_mismatch = copy.deepcopy(snapshot)
    ticker_mismatch["freeze"]["canonical_ticker"] = other_ticker
    _check("ticker_mismatch", ticker_mismatch, run_id)

    source_mismatch = copy.deepcopy(snapshot)
    source_mismatch["freeze"]["source_sha256"] = "0" * 64
    _check("source_hash_mismatch", source_mismatch, run_id)

    fixture_mismatch = copy.deepcopy(snapshot)
    fixture_mismatch["observed_r1"][0]["core_thesis"] = "tampered crosstalk"
    _check("fixture_hash_mismatch", fixture_mismatch, run_id)

    _check("run_id_mismatch", snapshot, f"{run_id}/../nested")

    no_freeze = copy.deepcopy(snapshot)
    no_freeze.pop("freeze", None)
    _check("freeze_missing", no_freeze, run_id)

    all_closed = all(item["status"] == "fail_closed" for item in cases)
    return {
        "branch": "mismatch_fail_closed",
        "status": "fail_closed_ok" if all_closed else "incomplete",
        "mismatch_cases": cases,
    }


def parse_observed_r1(snapshot: dict[str, Any]) -> list[AgentOutput]:
    """Reconstruct detector-ready R1 outputs from documented historical evidence.

    The historical replay only recorded `agent`/`core_thesis`/`key_metrics`;
    signal/conviction are detector placeholders and must not be read as evidence.
    """
    outputs: list[AgentOutput] = []
    for record in snapshot.get("observed_r1") or []:
        outputs.append(
            AgentOutput(
                name=record.get("agent", ""),
                signal="neutral",
                conviction=50,
                core_thesis=record.get("core_thesis", ""),
                key_metrics=list(record.get("key_metrics") or []),
                risks=[],
                what_would_change_my_mind="历史失败快照（检测器占位）",
                out_of_circle=False,
            )
        )
    return outputs


def reproduce_explicit_crosstalk(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Replay documented historical R1 outputs against the current detector."""
    outputs = parse_observed_r1(snapshot)
    per_agent: list[dict[str, Any]] = []
    for agent in outputs:
        ok, issues = detect_circular_reference(agent)
        per_agent.append(
            {
                "agent": agent.name,
                "core_thesis": agent.core_thesis,
                "circular_reference_detected": not ok,
                "issues": issues,
            }
        )
    hits = sum(1 for item in per_agent if item["circular_reference_detected"])
    return {
        "reproduced": hits > 0,
        "explicit_crosstalk_rate": hits / len(per_agent) if per_agent else 0.0,
        "per_agent": per_agent,
    }


def verify_historical_input_path(snapshot: dict[str, Any], ticker: str) -> dict[str, Any]:
    """Dry-run: prove the historical insufficient_data input fail-closes today."""
    try:
        _prepare_council_input(canonical_ticker(ticker), snapshot["input_snapshot"])
    except ValueError as exc:
        return {"status": "fail_closed_ok", "reason": str(exc), "llm_reachable": False}
    return {"status": "leaked", "reason": "input reached council preflight", "llm_reachable": True}


def run_fixture_diagnosis(
    snapshot: dict[str, Any],
    ticker: str,
    run_id: str,
    output_root: str | Path,
    model_configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the bounded fixture/dry-run diagnosis and record the conclusion."""
    envelope = create_failure_repro_envelope(
        snapshot, ticker, run_id, output_root, model_configuration
    )
    crosstalk = reproduce_explicit_crosstalk(snapshot)
    input_path = verify_historical_input_path(snapshot, ticker)

    if crosstalk["reproduced"] and input_path["llm_reachable"] is False:
        conclusion = {
            "status": "root_cause_located",
            "root_cause_path": (
                "insufficient_data -> prompt case anchoring -> explicit circular crosstalk"
            ),
            "note": (
                "current code fail-closes the historical input before LLM and hard-fails "
                "explicit circular reference after R1; no new crosstalk child is opened"
            ),
        }
    else:
        conclusion = {
            "status": "not_reproduced_or_leaked",
            "note": "historical failure was not reproduced or the input path leaked",
        }

    return {
        "mode": "fixture_dry_run",
        "envelope": envelope,
        "crosstalk": crosstalk,
        "input_path": input_path,
        "conclusion": conclusion,
        "residual_risks": [
            "live LLM reproduction not authorized; evidence is fixture/dry-run only",
            "implicit crosstalk escape remains: string detector can be bypassed by non-agent-id phrasing",
            "prompt case-anchoring design review is a separate fix child, not implemented here",
        ],
    }


def write_f3f_report(output_root: str | Path, payload: dict[str, Any]) -> str:
    """Write a bounded diagnostic report and return its markdown text."""
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    canonical = payload.get("canonical_ticker", "600519.SH")
    lines = [
        "# f3f R1 串台历史失败复现报告",
        "",
        "## 边界",
        "- 本报告是 fixture 回放 + dry-run，不是真实 LLM 复现。",
        "- live LLM reproduction not authorized。",
        "- 本报告不构成 G2 capability 证据，不宣称 G2 已通过。",
        "",
        f"- canonical_ticker: {canonical}",
        f"- run_id: {payload.get('run_id', '')}",
        "",
        "## 结论",
        str(payload.get("conclusion", {})),
        "",
        "## 残余风险",
    ]
    for risk in payload.get("residual_risks", []):
        lines.append(f"- {risk}")
    lines.extend(["", "## 修复边界", "- 修复另开独立 child，本 change 不实施。"])
    report = "\n".join(lines)
    (output_root / "f3f_failure_repro_report.md").write_text(report, encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="f3f historical crosstalk failure repro")
    parser.add_argument("--ticker", default="600519.SH")
    parser.add_argument("--run-id", default="f3f-fixture-dry-run")
    parser.add_argument("--output-root", default="value-screener/scripts/repro_out/f3f_failure_repro_fixture")
    args = parser.parse_args()

    ticker = canonical_ticker(args.ticker)
    snapshot_path = FIXTURE_PATHS[ticker]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    result = run_fixture_diagnosis(
        snapshot,
        ticker,
        args.run_id,
        args.output_root,
        model_configuration={},
    )
    report_payload = {
        "mode": result["mode"],
        "canonical_ticker": ticker,
        "run_id": args.run_id,
        "conclusion": result["conclusion"],
        "residual_risks": result["residual_risks"],
    }
    write_f3f_report(args.output_root, report_payload)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
