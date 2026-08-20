#!/usr/bin/env python3
"""f3e R1 input-assembly / orchestration hypothesis harness.

f3c 的 D1 四组实验结论为「neither」，本 harness 承接下一轮新假设诊断：
验证输入装配、角色分发、ticker/dossier/run identity 绑定与编排状态是否导致
R1 串台。固定 provider-frozen dossier、canonical ticker、run_id、source hash
和安全 output root；比较角色分发、全员共享、输入错配 fail-closed 与现有
编排路径。不修改主 prompt、不切换模型、不启动 G3；live 调用必须显式授权。
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

VALUE_SCREENER_ROOT = Path(__file__).resolve().parents[2]
if str(VALUE_SCREENER_ROOT) not in sys.path:
    sys.path.insert(0, str(VALUE_SCREENER_ROOT))

from council.agents import AGENT_REGISTRY, get_prompt_builder
from council.debate import _build_user_message, run_debate
from council.llm import call_llm
from council.schema import AgentOutput
from council.verify_quality_gate import (
    compute_citation_divergence,
    detect_circular_reference,
    verify_r1_feature_grounding,
)
from data.lib.audit_chain import (
    AuditIdentityError,
    create_audit_identity,
    payload_sha256,
    validate_audit_identity,
)
from data.lib.identity import canonical_ticker, generate_run_id


EXPECTED_TICKER = "600009.SH"
EXPECTED_SOURCE_SHA256 = (
    "f588d5bf911aefd90348d9a7d150280847b9af938bf5b06d8548a3afeb2a00c9"
)
EXPECTED_DOSSIER_SHA256 = (
    "556120be447b8800ab37b676443c7f8501791c3d812d101c41ed2ab8a2e2678f"
)
AGENT_IDS = tuple(AGENT_REGISTRY.keys())
BRANCHES = (
    "role_distribution",
    "all_shared",
    "mismatch_fail_closed",
    "existing_orchestration",
)
REQUIRED_ENV_KEYS = (
    "LLM_API_KEY",
    "LLM_API_BASE",
    "LLM_MODEL",
    "LLM_MODEL_HEAVY",
    "LLM_MODEL_MODERATE",
)
IMPLICIT_CROSSTALK_TERMS = ("其他", "另一位", "共识", "也看好", "大家", "都看好")
_PROFILE_VERSION = "g2-council-v1"
_PROMPT_VERSION = "council-prompt-v1"


def _plain_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_env(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _model_configuration(env_values: dict[str, str]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_ENV_KEYS if not env_values.get(key)]
    if missing:
        raise ValueError(f"live experiment env missing required keys: {missing}")
    return {
        "heavy_model": env_values["LLM_MODEL_HEAVY"],
        "moderate_model": env_values["LLM_MODEL_MODERATE"],
        "reasoning_levels": ["heavy", "moderate"],
    }


def load_verified_dossier(
    path: str | Path,
    expected_source_sha256: str | None = EXPECTED_SOURCE_SHA256,
) -> dict[str, Any]:
    """Load only a frozen, identity-bound 600009.SH dossier for live f3e."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"verified dossier missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"verified dossier is not valid JSON: {path}") from exc
    if not isinstance(data, dict) or "error" in data:
        raise ValueError("verified dossier required; insufficient/error snapshot is rejected")

    freeze = data.get("freeze")
    if not isinstance(freeze, dict):
        raise ValueError("verified dossier must include freeze envelope")
    declared_ticker = freeze.get("canonical_ticker")
    if not isinstance(declared_ticker, str):
        raise ValueError("freeze.canonical_ticker is required")
    try:
        normalized_ticker = canonical_ticker(declared_ticker)
    except ValueError as exc:
        raise ValueError(f"verified dossier ticker is invalid: {declared_ticker!r}") from exc
    if normalized_ticker != EXPECTED_TICKER:
        raise ValueError(f"verified dossier must bind to canonical ticker {EXPECTED_TICKER}")

    core = data.get("core_snapshot")
    if not isinstance(core, dict) or core.get("ticker") != EXPECTED_TICKER:
        raise ValueError(f"dossier core_snapshot.ticker must be {EXPECTED_TICKER}")
    research = data.get("research_dossier")
    if not isinstance(research, dict) or not research.get("main_business"):
        raise ValueError("verified dossier must include research_dossier.main_business")

    source_sha256 = freeze.get("source_sha256")
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
    ):
        raise ValueError("freeze.source_sha256 must be a sha256 digest")
    if expected_source_sha256 is not None and source_sha256 != expected_source_sha256:
        raise ValueError("freeze.source_sha256 does not match expected source hash")
    if payload_sha256(data) != EXPECTED_DOSSIER_SHA256:
        raise ValueError("verified dossier content does not match the frozen f3c dossier hash")
    return data


def create_run_envelope(
    dossier: dict[str, Any],
    run_id: str,
    output_root: str | Path,
    model_configuration: dict[str, Any],
) -> dict[str, Any]:
    """Bind one frozen dossier to a unique run identity and safe output root."""
    freeze = dossier.get("freeze")
    if not isinstance(freeze, dict) or not isinstance(freeze.get("source_sha256"), str):
        raise AuditIdentityError("f3e envelope requires freeze.source_sha256")
    if freeze["source_sha256"] != EXPECTED_SOURCE_SHA256:
        raise AuditIdentityError(
            "f3e envelope source hash mismatch: expected "
            f"{EXPECTED_SOURCE_SHA256}, got {freeze['source_sha256']}"
        )
    if payload_sha256(dossier) != EXPECTED_DOSSIER_SHA256:
        raise AuditIdentityError(
            "f3e envelope dossier content mismatch: payload hash does not match "
            "the frozen f3c dossier"
        )
    try:
        identity = create_audit_identity(
            EXPECTED_TICKER,
            dossier=dossier,
            profile_version=_PROFILE_VERSION,
            prompt_version=_PROMPT_VERSION,
            model_configuration=model_configuration,
            run_id=run_id,
        )
        validate_audit_identity(identity, ticker=EXPECTED_TICKER, dossier=dossier)
    except AuditIdentityError as exc:
        raise AuditIdentityError(f"f3e envelope rejected: {exc}") from exc
    return {
        "canonical_ticker": EXPECTED_TICKER,
        "run_id": identity.run_id,
        "identity": identity,
        "dossier": dossier,
        "dossier_sha256": payload_sha256(dossier),
        "source_sha256": freeze["source_sha256"],
        "output_root": Path(output_root).resolve(),
        "profile_version": _PROFILE_VERSION,
        "prompt_version": _PROMPT_VERSION,
        "model_configuration": identity.model_configuration,
    }


def build_branch_user_message(
    ticker: str,
    dossier: dict[str, Any],
    agent_id: str,
    branch: str,
) -> str:
    """Build the experiment-local user message for a non-live branch."""
    if branch == "role_distribution":
        return _build_user_message(ticker, dossier, other_opinions=None, agent_id=agent_id)
    if branch == "all_shared":
        return _build_user_message(ticker, dossier, other_opinions=None, agent_id=None)
    if branch == "existing_orchestration":
        # 标准编排路径的 R1 装配与 role_distribution 相同，此处只生成对照预期。
        return _build_user_message(ticker, dossier, other_opinions=None, agent_id=agent_id)
    raise ValueError(f"branch {branch!r} does not build a user message")


def run_mismatch_fail_closed(
    dossier: dict[str, Any],
    run_id: str,
    output_root: str | Path,
    model_configuration: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic branch: every envelope mismatch must fail before any LLM call."""
    cases: list[dict[str, str]] = []

    wrong_ticker = copy.deepcopy(dossier)
    wrong_ticker["core_snapshot"]["ticker"] = "600519.SH"
    wrong_ticker["freeze"]["canonical_ticker"] = "600519.SH"
    try:
        create_run_envelope(wrong_ticker, run_id, output_root, model_configuration)
    except (AuditIdentityError, ValueError) as exc:
        cases.append({"case": "ticker_mismatch", "status": "fail_closed", "reason": str(exc)[:300]})
    else:
        cases.append({"case": "ticker_mismatch", "status": "leaked", "reason": "envelope accepted wrong ticker"})

    try:
        create_audit_identity(
            EXPECTED_TICKER,
            dossier=dossier,
            profile_version=_PROFILE_VERSION,
            prompt_version=_PROMPT_VERSION,
            model_configuration=model_configuration,
            run_id=run_id,
            input_hash="0" * 64,
        )
    except AuditIdentityError as exc:
        cases.append({"case": "dossier_hash_mismatch", "status": "fail_closed", "reason": str(exc)[:300]})
    else:
        cases.append({"case": "dossier_hash_mismatch", "status": "leaked", "reason": "envelope accepted wrong input hash"})

    try:
        create_run_envelope(dossier, f"{run_id}/nested", output_root, model_configuration)
    except AuditIdentityError as exc:
        cases.append({"case": "run_id_mismatch", "status": "fail_closed", "reason": str(exc)[:300]})
    else:
        cases.append({"case": "run_id_mismatch", "status": "leaked", "reason": "envelope accepted unsafe run_id"})

    no_freeze = copy.deepcopy(dossier)
    no_freeze.pop("freeze", None)
    try:
        create_run_envelope(no_freeze, run_id, output_root, model_configuration)
    except AuditIdentityError as exc:
        cases.append({"case": "freeze_missing", "status": "fail_closed", "reason": str(exc)[:300]})
    else:
        cases.append({"case": "freeze_missing", "status": "leaked", "reason": "envelope accepted dossier without freeze"})

    wrong_source = copy.deepcopy(dossier)
    wrong_source["freeze"]["source_sha256"] = "0" * 64
    try:
        create_run_envelope(wrong_source, run_id, output_root, model_configuration)
    except AuditIdentityError as exc:
        cases.append({"case": "source_hash_mismatch", "status": "fail_closed", "reason": str(exc)[:300]})
    else:
        cases.append({"case": "source_hash_mismatch", "status": "leaked", "reason": "envelope accepted wrong source hash"})

    tampered = copy.deepcopy(dossier)
    tampered["core_snapshot"]["net_margin"] = 99.0
    try:
        create_run_envelope(tampered, run_id, output_root, model_configuration)
    except AuditIdentityError as exc:
        cases.append({"case": "dossier_content_tamper", "status": "fail_closed", "reason": str(exc)[:300]})
    else:
        cases.append({"case": "dossier_content_tamper", "status": "leaked", "reason": "envelope accepted tampered dossier"})

    all_closed = all(item["status"] == "fail_closed" for item in cases)
    return {
        "branch": "mismatch_fail_closed",
        "run_id": run_id,
        "status": "fail_closed_ok" if all_closed else "incomplete",
        "mismatch_cases": cases,
        "records": [],
        "outputs": [],
        "metrics": {"input_consistency": 0.0},
    }


def compute_branch_metrics(
    outputs: list[AgentOutput],
    dossier: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    run_id: str,
    model: str,
) -> dict[str, Any]:
    """Per-branch metrics: crosstalk, Jaccard, grounding and input consistency."""
    explicit = [not detect_circular_reference(output)[0] for output in outputs]
    implicit = [
        any(term in output.core_thesis for term in IMPLICIT_CROSSTALK_TERMS)
        for output in outputs
    ]
    fabricated = [not verify_r1_feature_grounding(output, dossier)[0] for output in outputs]
    expected_dossier_hash = payload_sha256(dossier)
    consistent = 0
    inconsistency_reasons: list[str] = []
    for record in records:
        ok = (
            record.get("status") == "ok"
            and record.get("run_id") == run_id
            and record.get("dossier_sha256") == expected_dossier_hash
            and record.get("canonical_ticker") == EXPECTED_TICKER
            and record.get("model") == model
        )
        if ok:
            consistent += 1
        else:
            inconsistency_reasons.append(
                f"{record.get('agent', '?')}: run_id/dossier/model/ticker mismatch"
            )
    return {
        "explicit_crosstalk_rate": sum(explicit) / len(outputs) if outputs else 0.0,
        "implicit_crosstalk_rate": sum(implicit) / len(outputs) if outputs else 0.0,
        "grounding_unverified_rate": sum(fabricated) / len(outputs) if outputs else 0.0,
        "citation_divergence": (
            compute_citation_divergence(outputs)
            if outputs
            else {"pairwise_distances": {}, "mean_distance": 0.0}
        ),
        "input_consistency": consistent / len(records) if records else 0.0,
        "input_consistency_reasons": inconsistency_reasons,
    }


def _prompt_key(system_prompt: str, user_message: str) -> str:
    return payload_sha256({"system_prompt": system_prompt, "user_message": user_message})


async def run_direct_branch(
    branch: str,
    envelope: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    """Run one non-orchestration branch through the same prompt/model."""
    ticker = envelope["canonical_ticker"]
    dossier = envelope["dossier"]
    records: list[dict[str, Any]] = []
    outputs: list[AgentOutput] = []
    for agent_id in AGENT_IDS:
        system_prompt = get_prompt_builder(agent_id)()
        user_message = build_branch_user_message(ticker, dossier, agent_id, branch)
        base = {
            "branch": branch,
            "agent": agent_id,
            "run_id": envelope["run_id"],
            "canonical_ticker": ticker,
            "model": model,
            "dossier_sha256": envelope["dossier_sha256"],
            "source_sha256": envelope["source_sha256"],
            "system_prompt_sha256": _plain_sha256(system_prompt),
            "user_message_sha256": _plain_sha256(user_message),
        }
        try:
            raw_json, usage = await call_llm(system_prompt, user_message, "heavy", model=model)
            output = AgentOutput.from_json(agent_id, raw_json)
            outputs.append(output)
            records.append(
                {**base, "status": "ok", "raw_response": raw_json, "output": output.to_dict(), "usage": usage}
            )
        except Exception as exc:
            records.append(
                {**base, "status": "error", "error_type": type(exc).__name__, "error": str(exc)[:500]}
            )
    metrics = compute_branch_metrics(
        outputs, dossier, records, run_id=envelope["run_id"], model=model
    )
    return {
        "branch": branch,
        "run_id": envelope["run_id"],
        "status": "complete" if len(outputs) == len(AGENT_IDS) else "incomplete",
        "records": records,
        "outputs": [output.to_dict() for output in outputs],
        "metrics": metrics,
    }


async def run_orchestration_branch(envelope: dict[str, Any]) -> dict[str, Any]:
    """Run the standard run_debate path and compare its R1 assembly with direct calls."""
    import council.debate as debate_module

    identity = envelope["identity"]
    ticker = envelope["canonical_ticker"]
    dossier = envelope["dossier"]
    model = envelope["model_configuration"]["heavy_model"]
    output_root = envelope["output_root"]
    audit_root = output_root / "audit"
    run_root = audit_root / identity.run_id
    sandbox = output_root / "runtime_sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)

    raw_by_prompt_hash: dict[str, dict[str, Any]] = {}
    original_call_llm = debate_module.call_llm

    async def recording_call_llm(system_prompt, user_message, reasoning_level="heavy", model=None):
        raw_json, usage = await original_call_llm(
            system_prompt, user_message, reasoning_level, model=model
        )
        raw_by_prompt_hash[_prompt_key(system_prompt, user_message)] = {
            "raw_response": raw_json,
            "usage": usage,
        }
        return raw_json, usage

    previous_cwd = Path.cwd()
    debate_module.call_llm = recording_call_llm
    result = None
    orchestration_error: str | None = None
    try:
        os.chdir(sandbox)
        try:
            result = await run_debate(
                ticker,
                features=dossier,
                agents=list(AGENT_IDS),
                force=True,
                audit_root=audit_root,
                audit_identity=identity,
                prompt_version=envelope["prompt_version"],
                model_configuration=envelope["model_configuration"],
            )
        except Exception as exc:
            orchestration_error = f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        debate_module.call_llm = original_call_llm
        os.chdir(previous_cwd)

    if orchestration_error is not None:
        return {
            "branch": "existing_orchestration",
            "run_id": identity.run_id,
            "status": "incomplete",
            "records": [],
            "outputs": [],
            "metrics": {"input_consistency": 0.0},
            "input_assembly_mismatches": [],
            "evidence_gaps": [f"run_debate did not complete: {orchestration_error}"],
            "error": orchestration_error,
        }

    prompt_paths = sorted(run_root.glob("0*-prompt.json"))
    if not prompt_paths:
        return {
            "branch": "existing_orchestration",
            "run_id": identity.run_id,
            "status": "incomplete",
            "records": [],
            "outputs": [],
            "metrics": {"input_consistency": 0.0},
            "input_assembly_mismatches": [],
            "evidence_gaps": [f"audit prompt artifact missing under {run_root}"],
            "error": "audit prompt artifact missing",
        }
    artifact = json.loads(prompt_paths[0].read_text(encoding="utf-8"))
    prompts = artifact.get("payload", {}).get("prompts", [])
    r1_prompts = [item for item in prompts if item.get("stage") == "r1"]

    records: list[dict[str, Any]] = []
    outputs: list[AgentOutput] = []
    evidence_gaps: list[str] = []
    for item in r1_prompts:
        agent_id = item["agent"]
        system_prompt = item["system_prompt"]
        user_message = item["user_message"]
        parsed = next((output for output in result.round1 if output.name == agent_id), None)
        base = {
            "branch": "existing_orchestration",
            "agent": agent_id,
            "run_id": identity.run_id,
            "canonical_ticker": ticker,
            "model": model,
            "dossier_sha256": payload_sha256(dossier),
            "source_sha256": dossier["freeze"]["source_sha256"],
            "system_prompt_sha256": _plain_sha256(system_prompt),
            "user_message_sha256": _plain_sha256(user_message),
        }
        raw_record = raw_by_prompt_hash.get(_prompt_key(system_prompt, user_message))
        if parsed is None:
            records.append(
                {**base, "status": "incomplete", "evidence_gap": "run_debate round1 missing parsed output"}
            )
            evidence_gaps.append(f"{agent_id}: parsed output missing")
            continue
        if raw_record is None:
            records.append(
                {
                    **base,
                    "status": "incomplete",
                    "evidence_gap": "raw R1 response not exposed by run_debate",
                    "output": parsed.to_dict(),
                }
            )
            evidence_gaps.append(f"{agent_id}: raw R1 response not exposed")
        else:
            records.append(
                {
                    **base,
                    "status": "ok",
                    "raw_response": raw_record["raw_response"],
                    "output": parsed.to_dict(),
                    "usage": raw_record["usage"],
                }
            )
        outputs.append(parsed)

    input_assembly_mismatches: list[dict[str, str]] = []
    for agent_id in AGENT_IDS:
        recorded = next((item for item in r1_prompts if item["agent"] == agent_id), None)
        if recorded is None:
            input_assembly_mismatches.append({"agent": agent_id, "reason": "r1 prompt record missing"})
            continue
        expected_user_message = build_branch_user_message(
            ticker, dossier, agent_id, "role_distribution"
        )
        if recorded["user_message"] != expected_user_message:
            input_assembly_mismatches.append(
                {
                    "agent": agent_id,
                    "reason": "user message differs from role_distribution direct branch",
                    "expected_user_message_sha256": _plain_sha256(expected_user_message),
                    "actual_user_message_sha256": _plain_sha256(recorded["user_message"]),
                }
            )

    metrics = compute_branch_metrics(
        outputs, dossier, records, run_id=identity.run_id, model=model
    )
    complete = (
        len(outputs) == len(AGENT_IDS)
        and all(record["status"] == "ok" for record in records)
        and not input_assembly_mismatches
        and not evidence_gaps
    )
    return {
        "branch": "existing_orchestration",
        "run_id": identity.run_id,
        "status": "complete" if complete else "incomplete",
        "records": records,
        "outputs": [output.to_dict() for output in outputs],
        "metrics": metrics,
        "input_assembly_mismatches": input_assembly_mismatches,
        "evidence_gaps": evidence_gaps,
    }


def write_f3e_report(output_root: str | Path, payload: dict[str, Any]) -> str:
    """Write a bounded f3e report and return its markdown."""
    branches = payload["branches"]
    lines = [
        "# f3e R1 输入装配/编排状态假设实验报告",
        "",
        f"> 输入：`{payload.get('canonical_ticker')}` provider-frozen dossier，source sha256 "
        f"`{payload.get('source_sha256')}`；未执行 provider refresh。",
        "> 结论与 evidence gap 分开记录；本报告不宣称 G2 capability passed。",
        "",
        f"- 模式：`{payload.get('mode')}`",
        f"- run_id：`{payload.get('run_id')}`",
        f"- profile_version：`{payload.get('profile_version')}` / prompt_version：`{payload.get('prompt_version')}`",
        f"- heavy model：`{payload.get('model_configuration', {}).get('heavy_model')}`",
        "",
        "| branch | status | explicit | implicit | Jaccard_dist | grounding_unverified | input_consistency |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for branch in BRANCHES:
        item = branches.get(branch, {})
        metrics = item.get("metrics", {})
        divergence = metrics.get("citation_divergence", {})
        lines.append(
            f"| {branch} | {item.get('status', 'missing')} | "
            f"{metrics.get('explicit_crosstalk_rate', 'n/a')} | "
            f"{metrics.get('implicit_crosstalk_rate', 'n/a')} | "
            f"{divergence.get('mean_distance', 'n/a')} | "
            f"{metrics.get('grounding_unverified_rate', 'n/a')} | "
            f"{metrics.get('input_consistency', 'n/a')} |"
        )
    lines.extend([
        "",
        "> `grounding_unverified` 为 `verify_r1_feature_grounding` 反向校验未通过率；",
        "> 未通过多由单位/派生值未归一导致（如 9.34亿 vs 934000000、54% vs 0.540988、",
        "> 77% vs 0.7698、年份 2023-2025 等），1.0 不代表全部数字凭空编造。",
        "> 显性串台：`detect_circular_reference` 字符串命中（core_thesis 含其他 agent_id）；",
        "> 隐性串台：core_thesis 词表采样候选率（其他/另一位/共识/也看好/大家/都看好），",
        "> 属有界字符串检测，不等于语义排除，不升级为 hard gate。",
    ])

    mismatch = branches.get("mismatch_fail_closed", {})
    lines.extend(["", "## 错配 fail-closed", ""])
    if mismatch.get("mismatch_cases"):
        for case in mismatch["mismatch_cases"]:
            lines.append(f"- `{case['case']}`: {case['status']} — {case.get('reason', '')}")
    else:
        lines.append("- 未执行 mismatch 分支。")

    orchestration = branches.get("existing_orchestration", {})
    lines.extend(["", "## 编排路径对照", ""])
    if orchestration.get("input_assembly_mismatches"):
        for mismatch_item in orchestration["input_assembly_mismatches"]:
            lines.append(f"- input assembly mismatch: {json.dumps(mismatch_item, ensure_ascii=False)}")
    else:
        lines.append(
            "- 现有编排路径未产出可对照的 R1 user message（未运行或预检失败，见 evidence gaps）。"
        )
    gaps = orchestration.get("evidence_gaps") or []
    if gaps:
        lines.extend(["", "### evidence gaps"])
        lines.extend(f"- {gap}" for gap in gaps)

    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- 本 change 不修改主 prompt、不切换模型、不启动 G3。",
            "- 输入错配、dossier 缺失或 run identity 不一致不计入 clean success。",
            "- 找到明确根因后，另开独立 runtime/provider repair change；本报告不宣称 G2 capability passed。",
        ]
    )
    report = "\n".join(lines) + "\n"
    (Path(output_root) / "f3e_input_assembly_report.md").write_text(report, encoding="utf-8")
    return report


async def run_live_experiment(
    output_root: str | Path,
    env_path: str | Path,
    dossier_path: str | Path,
    run_id: str | None = None,
    authorize_live: bool = False,
) -> dict[str, Any]:
    """Run the four-branch f3e experiment under an explicitly authorized gate."""
    if not authorize_live:
        raise ValueError("live LLM calls require explicit authorization; pass authorize_live=True")
    dossier = load_verified_dossier(Path(dossier_path))
    env_values = _load_env(Path(env_path))
    model_configuration = _model_configuration(env_values)
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    data_path = output_root / "f3e_input_assembly_data.json"
    if data_path.exists():
        raise FileExistsError(f"refusing to overwrite experiment data: {data_path}")
    run_id = run_id or generate_run_id()
    envelope = create_run_envelope(dossier, run_id, output_root, model_configuration)

    previous = {key: os.environ.get(key) for key in env_values}
    os.environ.update(env_values)
    try:
        branches: dict[str, Any] = {}
        for branch in ("role_distribution", "all_shared"):
            branches[branch] = await run_direct_branch(
                branch, envelope, env_values["LLM_MODEL_HEAVY"]
            )
        branches["mismatch_fail_closed"] = run_mismatch_fail_closed(
            dossier, run_id, output_root, model_configuration
        )
        branches["existing_orchestration"] = await run_orchestration_branch(envelope)
        payload = {
            "mode": "live",
            "run_id": run_id,
            "input_mode": "frozen_dossier",
            "canonical_ticker": EXPECTED_TICKER,
            "source_sha256": dossier["freeze"]["source_sha256"],
            "dossier_path": str(dossier_path),
            "profile_version": envelope["profile_version"],
            "prompt_version": envelope["prompt_version"],
            "model_configuration": model_configuration,
            "branches": branches,
        }
        raw_dir = output_root / "f3e_input_assembly_raw"
        raw_dir.mkdir(exist_ok=True)
        for name, branch in branches.items():
            (raw_dir / f"{name}.json").write_text(
                json.dumps(branch, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        data_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_f3e_report(output_root, payload)
        return payload
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", required=True, help="provider-frozen 600009.SH dossier JSON")
    parser.add_argument("--env", required=True, help="value-screener .env with LLM credentials")
    parser.add_argument("--output-root", required=True, help="run-scoped safe output root")
    parser.add_argument("--run-id", default=None, help="unique run id (default: uuid4)")
    parser.add_argument(
        "--authorize-live",
        action="store_true",
        help="explicit authorization for live LLM calls",
    )
    args = parser.parse_args()
    if not args.authorize_live:
        parser.error("live LLM calls require explicit authorization; pass --authorize-live")
    asyncio.run(
        run_live_experiment(
            args.output_root,
            args.env,
            args.dossier,
            run_id=args.run_id,
            authorize_live=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
