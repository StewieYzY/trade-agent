"""G2 strong single-agent fallback foundation.

该模块不进入 Council 的 cache/watchlist 成功路径，只输出 run-scoped fallback
artifact。它复用 Council dossier preflight 和事实校验，但只进行一次 strong
agent 调用；synthesis 是 deterministic envelope，不再调用第二个 LLM。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from council.agents import AGENT_REGISTRY, get_prompt_builder
from council.debate import _build_user_message, _prepare_council_input
from council.llm import call_llm
from council.schema import AgentOutput, ValidationError
from data.lib.production_paths import validate_g1_output_root
from data.lib.provenance import redact_sensitive_text
from council.verify_quality_gate import (
    detect_circular_reference,
    verify_r1_feature_grounding,
)

DEFAULT_AGENT = "buffett"


def _sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _redact_error(message: object) -> str:
    return redact_sensitive_text(message)


def _canonical_ticker(ticker: str) -> str:
    from data.lib.identity import canonical_ticker

    return canonical_ticker(ticker)


def _resolve_run_dir(
    output_root: str | Path | None,
    run_id: str | None,
) -> tuple[str, Path]:
    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if (
        not isinstance(run_id, str)
        or not run_id
        or run_id in {".", ".."}
        or Path(run_id).is_absolute()
        or "/" in run_id
        or "\\" in run_id
    ):
        raise ValueError("run_id must be a non-empty relative path leaf")
    root = validate_g1_output_root(output_root or "fallback_runs")
    run_dir = (root / run_id).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("run_id escapes output_root") from exc
    return run_id, run_dir


def _code_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _provider_host() -> str | None:
    return urlsplit(os.environ.get("LLM_API_BASE", "")).hostname


def check_agent_facts(output: AgentOutput, features: dict) -> dict:
    """独立 deterministic fact checker：grounding + R1 circular reference。"""
    issues: list[str] = []
    circular_ok, circular_issues = detect_circular_reference(
        output,
        agent_ids=tuple(AGENT_REGISTRY.keys()),
    )
    if not circular_ok:
        issues.extend(circular_issues)

    grounding_ok, grounding_issues = verify_r1_feature_grounding(output, features)
    if not grounding_ok:
        issues.extend(grounding_issues)

    return {
        "status": "passed" if not issues else "blocked",
        "circular_reference_ok": circular_ok,
        "grounding_ok": grounding_ok,
        "issues": issues,
    }


def build_fallback_synthesis(
    *,
    ticker: str,
    agent_id: str,
    output: AgentOutput | None,
    fact_check: dict,
) -> dict:
    """只复制通过校验的 agent 字段；失败时输出安全 skip envelope。"""
    if output is None or fact_check.get("status") != "passed":
        issues = list(fact_check.get("issues") or [])
        return {
            "ticker": ticker,
            "agent_id": agent_id,
            "signal": "skip",
            "conviction": 0,
            "core_thesis": "fallback 质量门未通过，暂不发布方向性判断",
            "key_metrics": [],
            "risks": [],
            "what_would_change_my_mind": "补充可核验事实并重新运行质量检查",
            "pending_verification": issues,
            "quality_status": "blocked",
            "synthesis_source": "deterministic_fallback",
        }

    return {
        "ticker": ticker,
        "agent_id": agent_id,
        "signal": output.signal,
        "conviction": output.conviction,
        "core_thesis": output.core_thesis,
        "key_metrics": list(output.key_metrics),
        "risks": list(output.risks),
        "what_would_change_my_mind": output.what_would_change_my_mind,
        "pending_verification": [],
        "quality_status": "passed",
        "synthesis_source": "deterministic_fallback",
    }


def _classify_exception(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "schema"
    if isinstance(exc, (httpx.HTTPError, TimeoutError, OSError)):
        return "transport"
    return "internal"


def _write_manifest(
    path: Path,
    *,
    run_id: str,
    state: str,
    code_version: str,
    result_path: Path | None = None,
) -> None:
    payload = {
        "schema_version": "g2-strong-single-agent-fallback-v1",
        "run_id": run_id,
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "code_version": code_version,
    }
    if result_path is not None:
        payload["result_path"] = str(result_path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_fallback(
    *,
    ticker: str,
    features: dict | None = None,
    agent_id: str = DEFAULT_AGENT,
    model: str | None = None,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> dict:
    """运行一次 strong single-agent fallback。"""
    canonical_ticker = _canonical_ticker(ticker)
    if agent_id not in AGENT_REGISTRY:
        raise ValueError(f"unknown fallback agent: {agent_id}")

    # 必须在 run directory 和任意 LLM side effect 前完成 preflight。
    dossier = _prepare_council_input(canonical_ticker, features)

    selected_model = model or os.environ.get("LLM_MODEL_HEAVY")
    if not selected_model or not selected_model.strip():
        raise ValueError("missing strong model: provide model or LLM_MODEL_HEAVY")

    run_id, run_dir = _resolve_run_dir(output_root, run_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    result_path = run_dir / "result.json"
    code_version = _code_version()
    _write_manifest(
        manifest_path,
        run_id=run_id,
        state="running",
        code_version=code_version,
    )

    system_prompt = get_prompt_builder(agent_id)()
    user_message = _build_user_message(
        canonical_ticker,
        dossier,
        agent_id=agent_id,
    )
    common = {
        "ticker": canonical_ticker,
        "agent_id": agent_id,
        "model": selected_model,
        "provider_host": _provider_host(),
        "features_sha256": _sha256(dossier),
        "system_prompt_sha256": _sha256(system_prompt),
        "user_message_sha256": _sha256(user_message),
        "request_fingerprint": _sha256(
            {
                "ticker": canonical_ticker,
                "agent_id": agent_id,
                "model": selected_model,
                "features": dossier,
                "system_prompt": system_prompt,
                "user_message": user_message,
            }
        ),
    }

    raw = ""
    usage: dict = {}
    agent_output: AgentOutput | None = None
    failure_kind: str | None = None
    error: str | None = None
    response_sha256: str | None = None
    try:
        raw_response, usage = await call_llm(
            system_prompt,
            user_message,
            "heavy",
            model=selected_model,
        )
        raw = redact_sensitive_text(raw_response)
        response_sha256 = _sha256(raw)
        agent_output = AgentOutput.from_json(agent_id, raw_response)
    except Exception as exc:
        failure_kind = _classify_exception(exc)
        error = f"{type(exc).__name__}: {_redact_error(str(exc))}"

    if agent_output is None:
        fact_check = {
            "status": "blocked",
            "circular_reference_ok": False,
            "grounding_ok": False,
            "issues": [error or "agent output unavailable"],
        }
    else:
        fact_check = check_agent_facts(agent_output, dossier)

    synthesis = build_fallback_synthesis(
        ticker=canonical_ticker,
        agent_id=agent_id,
        output=agent_output,
        fact_check=fact_check,
    )
    quality_status = synthesis["quality_status"]
    result = {
        "schema_version": "g2-strong-single-agent-fallback-v1",
        "run_id": run_id,
        "execution_status": "completed" if failure_kind is None else "blocked",
        "quality_status": quality_status,
        **common,
        "usage": usage,
        "response_sha256": response_sha256,
        "raw": raw,
        "error": error,
        "failure_kind": failure_kind,
        "agent_output": agent_output.to_dict() if agent_output else None,
        "fact_check": fact_check,
        "synthesis": synthesis,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_manifest(
        manifest_path,
        run_id=run_id,
        state=quality_status,
        code_version=code_version,
        result_path=result_path,
    )
    result["result_path"] = str(result_path)
    result["manifest_path"] = str(manifest_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--features-json")
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    parser.add_argument("--model")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", default="fallback_runs")
    args = parser.parse_args()

    features = None
    if args.features_json:
        features = json.loads(Path(args.features_json).read_text(encoding="utf-8"))
    result = asyncio.run(
        run_fallback(
            ticker=args.ticker,
            features=features,
            agent_id=args.agent,
            model=args.model,
            output_root=args.output_root,
            run_id=args.run_id,
        )
    )
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "quality_status": result["quality_status"],
                "result_path": result["result_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
