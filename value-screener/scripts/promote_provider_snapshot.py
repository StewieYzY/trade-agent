"""Promote qualified provider evidence into an isolated canonical snapshot."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.lib.canonical_snapshot import write_snapshot
from data.lib.field_qualification import (
    FieldQualificationPolicy,
    evaluate_qualification_run,
)
from data.lib.production_paths import validate_g1_output_root
from scripts.provider_qualification import PROBE_PLAN_VERSION

def _safe_run_id(run_id: str | None) -> str:
    value = run_id or datetime.now(timezone.utc).strftime("promotion-%Y%m%dT%H%M%SZ")
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or Path(value).is_absolute()
        or "/" in value
        or "\\" in value
    ):
        raise ValueError("run_id must be a non-empty relative path leaf")
    return value


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _validate_output_root(output_root: Path, source_dir: Path) -> None:
    validate_g1_output_root(output_root)
    try:
        output_root.relative_to(source_dir)
    except ValueError:
        return
    raise ValueError("promotion output root cannot be inside source qualification run")


def promote_provider_snapshot(
    source_dir: str | Path,
    *,
    output_root: str | Path,
    policy: FieldQualificationPolicy,
    run_id: str | None = None,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    safe_id = _safe_run_id(run_id)
    source = Path(source_dir).resolve()
    root = validate_g1_output_root(output_root)
    _validate_output_root(root, source)
    root.mkdir(parents=True, exist_ok=True)
    run_dir = (root / safe_id).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("promotion run directory escapes output root") from exc
    if run_dir.exists():
        raise ValueError(f"promotion run already exists: {safe_id}")

    decision = evaluate_qualification_run(
        source,
        policy=policy,
        evaluated_at=evaluated_at,
    )
    decision["promotion_run_id"] = safe_id
    decision["output_root"] = str(root)

    evaluated_evidence = decision.get("evaluated_evidence", [])
    if not evaluated_evidence:
        run_dir.mkdir(parents=True)
        _write_json(run_dir / "decision.json", decision)
        return {
            "status": decision["status"],
            "run_id": safe_id,
            "run_dir": str(run_dir),
            "decision": decision,
            "snapshot_output": None,
        }

    snapshot_dir = write_snapshot(
        evaluated_evidence,
        tickers=policy.required_tickers,
        plan_version=policy.version,
        output_root=root,
        run_id=safe_id,
        freshness_seconds=policy.freshness_seconds,
        freshness_as_of=evaluated_at,
        manifest_extra={
            "promotion_status": decision["status"],
            "source_run_id": decision["source_run_id"],
            "source_evidence_hash": decision["source_evidence_hash"],
            "policy_version": policy.version,
            "policy_hash": policy.policy_hash,
            "decision_hash": decision["decision_hash"],
        },
    )
    _write_json(snapshot_dir / "decision.json", decision)
    return {
        "status": decision["status"],
        "run_id": safe_id,
        "run_dir": str(snapshot_dir),
        "decision": decision,
        "snapshot_output": str(snapshot_dir),
    }


def _positive_or_zero_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("freshness seconds must be non-negative")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote completed provider qualification evidence into a canonical snapshot."
    )
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--provider", action="append", required=True)
    parser.add_argument(
        "--ticker",
        action="append",
        default=["600519.SH", "600009.SH", "000858.SZ", "300750.SZ", "601318.SH"],
    )
    parser.add_argument(
        "--method-field",
        action="append",
        required=True,
        metavar="METHOD:FIELD",
    )
    parser.add_argument("--freshness-seconds", type=_positive_or_zero_int)
    parser.add_argument("--policy-version", default="g1-field-qualification-policy-v1")
    parser.add_argument(
        "--probe-plan-version",
        default=PROBE_PLAN_VERSION,
        choices=(PROBE_PLAN_VERSION,),
        help="Frozen provider qualification probe plan version.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    methods: dict[str, list[str]] = {}
    for value in args.method_field:
        method, separator, field = value.partition(":")
        if not separator or not method.strip() or not field.strip():
            raise SystemExit("--method-field must use METHOD:FIELD")
        methods.setdefault(method.strip(), []).append(field.strip())
    policy = FieldQualificationPolicy.from_mapping(
        version=args.policy_version,
        tickers=args.ticker,
        methods=methods,
        allowed_providers=args.provider,
        freshness_seconds=args.freshness_seconds,
        probe_plan_version=args.probe_plan_version,
    )
    result = promote_provider_snapshot(
        args.source_dir,
        output_root=args.output_root,
        policy=policy,
        run_id=args.run_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
