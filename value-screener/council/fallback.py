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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from council.agents import AGENT_REGISTRY, get_prompt_builder
from council.debate import _build_user_message, _prepare_council_input
from council.llm import call_llm
from council.schema import AgentOutput, ValidationError
from data.lib.production_paths import validate_g1_output_root
from data.lib.provenance import redact_sensitive_text, redact_sensitive_value
from council.verify_quality_gate import (
    detect_circular_reference,
    verify_r1_feature_grounding,
)
from data.lib.audit_chain import (
    AuditChainWriter,
    AuditIdentity,
    AuditIdentityError,
    create_audit_identity,
    payload_sha256,
    validate_audit_identity,
    validate_audit_identity_structure,
)
from data.lib.quality_status import (
    RunQualityRecord,
    quality_record_path as build_quality_record_path,
    replace_quality_record,
    write_quality_record,
)

DEFAULT_AGENT = "buffett"


def _sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _redact_error(message: object) -> str:
    return redact_sensitive_text(message)


def _redact_raw_response(raw_response: object) -> str:
    try:
        parsed = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError):
        return redact_sensitive_text(raw_response)
    return json.dumps(
        redact_sensitive_value(parsed),
        ensure_ascii=False,
        separators=(",", ":"),
    )


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
    run_quality_status: str | None = None,
    run_quality_reasons: list[str] | tuple[str, ...] | None = None,
    quality_record_path: Path | None = None,
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
    if run_quality_status is not None:
        payload["run_quality_status"] = run_quality_status
    if run_quality_reasons is not None:
        payload["run_quality_reasons"] = list(run_quality_reasons)
    if quality_record_path is not None:
        payload["quality_record_path"] = str(quality_record_path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _staged_fallback_result_path(result_path: Path) -> Path:
    return result_path.parent / ".staging" / result_path.name


def _write_staged_fallback_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def _promote_staged_fallback_result(staged_path: Path, result_path: Path) -> None:
    try:
        os.link(staged_path, result_path)
    except FileExistsError as exc:
        raise FileExistsError(
            f"refusing to overwrite fallback result: {result_path}"
        ) from exc
    staged_path.unlink()


def _is_promoted_staging_result(staged_path: Path, result_path: Path) -> bool:
    try:
        return staged_path.exists() and result_path.exists() and os.path.samefile(
            staged_path, result_path
        )
    except OSError:
        return False


async def run_fallback(
    *,
    ticker: str,
    features: dict | None = None,
    agent_id: str = DEFAULT_AGENT,
    model: str | None = None,
    output_root: str | Path | None = None,
    run_id: str | None = None,
    audit_root: str | Path | None = None,
    audit_identity: AuditIdentity | None = None,
    profile_version: str | None = None,
    prompt_version: str | None = None,
) -> dict:
    """运行一次 strong single-agent fallback。"""
    if audit_identity is not None:
        validate_audit_identity_structure(audit_identity)
    canonical_ticker = _canonical_ticker(ticker)
    if agent_id not in AGENT_REGISTRY:
        raise ValueError(f"unknown fallback agent: {agent_id}")

    # 必须在 dossier/provider preflight 和任意 LLM side effect 前拒绝 protected root。
    if audit_identity is not None and run_id is None:
        run_id = audit_identity.run_id
    elif audit_root is not None and run_id is None:
        run_id = str(uuid.uuid4())
    run_id, run_dir = _resolve_run_dir(output_root, run_id)
    if audit_root is not None and Path(audit_root).resolve() == run_dir.parent:
        raise AuditIdentityError("audit_root must differ from fallback output_root")

    dossier = _prepare_council_input(canonical_ticker, features)
    selected_model = model or os.environ.get("LLM_MODEL_HEAVY")
    if not selected_model or not selected_model.strip():
        raise ValueError("missing strong model: provide model or LLM_MODEL_HEAVY")

    audit_writer: AuditChainWriter | None = None
    if audit_identity is not None:
        if audit_identity.run_id != run_id:
            raise AuditIdentityError("fallback run_id does not match audit identity")
        if profile_version is not None and profile_version != audit_identity.profile_version:
            raise AuditIdentityError("fallback profile_version does not match audit identity")
        if prompt_version is not None and prompt_version != audit_identity.prompt_version:
            raise AuditIdentityError("fallback prompt_version does not match audit identity")
        runtime_model_configuration = {
            "model": selected_model,
            "reasoning_level": "heavy",
        }
        if runtime_model_configuration != audit_identity.model_configuration:
            raise AuditIdentityError(
                "fallback model_configuration does not match audit identity"
            )
        validate_audit_identity(
            audit_identity,
            ticker=canonical_ticker,
            dossier=dossier,
        )
    elif audit_root is not None:
        audit_identity = create_audit_identity(
            canonical_ticker,
            dossier=dossier,
            profile_version=profile_version or "g2-fallback-v1",
            prompt_version=prompt_version or "council-prompt-v1",
            model_configuration={
                "model": selected_model,
                "reasoning_level": "heavy",
            },
            run_id=run_id,
        )
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    result_path = run_dir / "result.json"
    code_version = _code_version()
    quality_root = output_root or "fallback_runs"

    def persist_terminal_quality(
        status: str,
        reason: str,
        *,
        final_quality_gate: str,
        manifest_state: str,
    ) -> None:
        quality_record = RunQualityRecord(
            canonical_ticker=canonical_ticker,
            run_id=run_id,
            status=status,
            reasons=(reason,),
            completed_stages=(),
            final_quality_gate=final_quality_gate,
            artifact_path=str(result_path),
            execution_mode="fallback",
        )
        quality_path = write_quality_record(quality_root, quality_record)
        _write_manifest(
            manifest_path,
            run_id=run_id,
            state=manifest_state,
            code_version=code_version,
            run_quality_status=status,
            run_quality_reasons=[reason],
            quality_record_path=quality_path,
        )

    def persist_setup_failure(reason: str) -> None:
        persist_terminal_quality(
            "failed",
            reason,
            final_quality_gate="failed",
            manifest_state="failed",
        )

    try:
        _write_manifest(
            manifest_path,
            run_id=run_id,
            state="running",
            code_version=code_version,
        )
        if audit_identity is not None:
            audit_writer = AuditChainWriter(
                audit_root or run_dir / "audit",
                audit_identity,
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
    except asyncio.CancelledError:
        if audit_writer is not None:
            audit_writer.abort()
        persist_terminal_quality(
            "incomplete",
            "fallback_setup_cancelled",
            final_quality_gate="not_run",
            manifest_state="incomplete",
        )
        raise
    except Exception:
        if audit_writer is not None:
            audit_writer.abort()
        persist_setup_failure("fallback_setup_failed")
        raise
    if audit_writer is not None:
        prompt_binding = {
            "ticker": canonical_ticker,
            "run_id": audit_identity.run_id,
            "profile_version": audit_identity.profile_version,
            "input_hash": audit_identity.input_hash,
            "dossier_snapshot": audit_identity.dossier_snapshot,
            "prompt_version": audit_identity.prompt_version,
            "model_configuration": audit_identity.model_configuration,
            "prompts": [
                {
                    "agent": agent_id,
                    "stage": "fallback",
                    "round": "heavy",
                    "system_prompt": system_prompt,
                    "user_message": user_message,
                }
            ],
        }
        try:
            audit_writer.write(
                "dossier",
                {
                    "ticker": canonical_ticker,
                    "run_id": audit_identity.run_id,
                    "profile_version": audit_identity.profile_version,
                    "input_hash": audit_identity.input_hash,
                    "dossier_snapshot": audit_identity.dossier_snapshot,
                    "prompt_version": audit_identity.prompt_version,
                    "model_configuration": audit_identity.model_configuration,
                    "dossier": dossier,
                    "dossier_sha256": payload_sha256(dossier),
                },
            )
            audit_writer.write(
                "prompt",
                {
                    "ticker": canonical_ticker,
                    "run_id": audit_identity.run_id,
                    "profile_version": audit_identity.profile_version,
                    "input_hash": audit_identity.input_hash,
                    "dossier_snapshot": audit_identity.dossier_snapshot,
                    "prompt_version": audit_identity.prompt_version,
                    "model_configuration": audit_identity.model_configuration,
                    "system_prompt": system_prompt,
                    "user_message": user_message,
                    "agent_id": agent_id,
                    "prompt_stage": "fallback",
                    "reasoning_level": "heavy",
                    "prompt_binding_sha256": payload_sha256(prompt_binding),
                    "system_prompt_sha256": common["system_prompt_sha256"],
                    "user_message_sha256": common["user_message_sha256"],
                },
            )
        except asyncio.CancelledError:
            audit_writer.abort()
            persist_terminal_quality(
                "incomplete",
                "fallback_audit_prompt_cancelled",
                final_quality_gate="not_run",
                manifest_state="incomplete",
            )
            raise
        except Exception:
            audit_writer.abort()
            persist_setup_failure("fallback_audit_prompt_failed")
            raise

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
        raw = _redact_raw_response(raw_response)
        response_sha256 = _sha256(raw)
        agent_output = AgentOutput.from_json(agent_id, raw_response)
    except asyncio.CancelledError:
        if audit_writer is not None:
            audit_writer.abort()
        persist_terminal_quality(
            "incomplete",
            "fallback_cancelled",
            final_quality_gate="not_run",
            manifest_state="incomplete",
        )
        raise
    except Exception as exc:
        failure_kind = _classify_exception(exc)
        error = f"{type(exc).__name__}: {_redact_error(str(exc))}"
    if response_sha256 is None:
        response_sha256 = _sha256(raw)
    persisted_agent_output = None
    if agent_output is not None:
        try:
            persisted_agent_output = AgentOutput.from_json(agent_id, raw).to_dict()
        except Exception:
            persisted_agent_output = redact_sensitive_value(agent_output.to_dict())

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
    result = redact_sensitive_value({
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
    })
    run_quality_status = "complete" if quality_status == "passed" else "failed"
    quality_reasons = tuple(fact_check.get("issues") or ())
    if failure_kind and not quality_reasons:
        quality_reasons = (error or failure_kind,)
    quality_record = RunQualityRecord(
        canonical_ticker=canonical_ticker,
        run_id=run_id,
        status=run_quality_status,
        reasons=quality_reasons,
        completed_stages=("agent", "fact_check", "synthesis", "final_validation"),
        final_quality_gate="passed" if run_quality_status == "complete" else "failed",
        artifact_path=str(result_path),
        execution_mode="fallback",
    )
    quality_record_path = build_quality_record_path(
        quality_root,
        canonical_ticker,
        run_id,
    )
    result["run_quality_status"] = run_quality_status
    result["run_quality_reasons"] = list(quality_record.reasons)
    result["final_quality_gate"] = quality_record.final_quality_gate
    # Fallback is diagnostic-only in this child and never enters Council success cache.
    result["success_cache_eligible"] = False
    result["quality_record_path"] = str(quality_record_path)
    audit_manifest_path: Path | None = None
    if audit_writer is not None:
        audit_manifest_path = audit_writer.run_root / "manifest.json"
        result.update(audit_identity.to_dict())
        result["audit_identity"] = audit_identity.to_dict()
        result["audit_manifest_path"] = str(audit_manifest_path)
        result["result_path"] = str(result_path)
        result["manifest_path"] = str(manifest_path)
        staged_result_path = _staged_fallback_result_path(result_path)
        try:
            _write_staged_fallback_result(staged_result_path, result)
            audit_writer.write(
                "debate",
                {
                    "ticker": canonical_ticker,
                    "run_id": audit_identity.run_id,
                    "profile_version": audit_identity.profile_version,
                    "input_hash": audit_identity.input_hash,
                    "dossier_snapshot": audit_identity.dossier_snapshot,
                    "prompt_version": audit_identity.prompt_version,
                    "model_configuration": audit_identity.model_configuration,
                    "response": raw,
                    "agent_id": agent_id,
                    "agent_output": persisted_agent_output,
                    "response_sha256": response_sha256,
                    "agent_output_sha256": payload_sha256(
                        persisted_agent_output
                    ),
                },
            )
            audit_writer.write(
                "quality_report",
                {
                    "ticker": canonical_ticker,
                    "run_id": audit_identity.run_id,
                    "profile_version": audit_identity.profile_version,
                    "input_hash": audit_identity.input_hash,
                    "dossier_snapshot": audit_identity.dossier_snapshot,
                    "prompt_version": audit_identity.prompt_version,
                    "model_configuration": audit_identity.model_configuration,
                    "quality_status": quality_status,
                    "fact_check": fact_check,
                },
            )
            audit_writer.write(
                "final_result",
                {
                    "ticker": canonical_ticker,
                    "run_id": audit_identity.run_id,
                    "profile_version": audit_identity.profile_version,
                    "input_hash": audit_identity.input_hash,
                    "dossier_snapshot": audit_identity.dossier_snapshot,
                    "prompt_version": audit_identity.prompt_version,
                    "model_configuration": audit_identity.model_configuration,
                    "quality_status": quality_status,
                    "result": result,
                    "result_sha256": payload_sha256(result),
                },
            )
            audit_writer.finalize()
            _promote_staged_fallback_result(staged_result_path, result_path)
        except (Exception, asyncio.CancelledError):
            if _is_promoted_staging_result(staged_result_path, result_path):
                result_path.unlink(missing_ok=True)
            staged_result_path.unlink(missing_ok=True)
            audit_writer.abort()
            persist_terminal_quality(
                "incomplete",
                "fallback_publish_interrupted",
                final_quality_gate="not_run",
                manifest_state="incomplete",
            )
            raise
    quality_record_written = False
    try:
        if audit_writer is None:
            write_quality_record(quality_root, quality_record)
            quality_record_written = True
            result_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            write_quality_record(quality_root, quality_record)
            quality_record_written = True
        _write_manifest(
            manifest_path,
            run_id=run_id,
            state=quality_status,
            code_version=code_version,
            result_path=result_path,
            run_quality_status=run_quality_status,
            run_quality_reasons=list(quality_record.reasons),
            quality_record_path=quality_record_path,
        )
    except (Exception, asyncio.CancelledError):
        result_path.unlink(missing_ok=True)
        failed_record = RunQualityRecord(
            canonical_ticker=canonical_ticker,
            run_id=run_id,
            status="incomplete",
            reasons=("fallback_quality_persistence_interrupted",),
            completed_stages=(),
            final_quality_gate="not_run",
            artifact_path=str(result_path),
            execution_mode="fallback",
        )
        if quality_record_written:
            replace_quality_record(quality_root, failed_record)
        else:
            write_quality_record(quality_root, failed_record)
        _write_manifest(
            manifest_path,
            run_id=run_id,
            state="incomplete",
            code_version=code_version,
            run_quality_status="incomplete",
            run_quality_reasons=list(failed_record.reasons),
            quality_record_path=build_quality_record_path(
                quality_root,
                canonical_ticker,
                run_id,
            ),
        )
        raise
    result.setdefault("result_path", str(result_path))
    result.setdefault("manifest_path", str(manifest_path))
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
