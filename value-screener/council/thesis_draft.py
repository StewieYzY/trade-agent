"""M0.2 strong single-agent Thesis 草稿 adapter.

该模块只消费已冻结且已绑定的 M0.1 diagnostic artifact 与显式 dossier。
它执行一次 strong LLM 调用，并把 AgentOutput 包装成可供人工复核的
deterministic 草稿；不进入 Council、fallback cache 或稳定 InvestmentThesis。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from council.agents import get_prompt_builder
from council.debate import _build_user_message, _validate_council_input
from council.fact_grounding import evaluate_dossier_quality
from council.verify_quality_gate import verify_r1_feature_grounding
from council.llm import call_llm_once as call_llm
from council.schema import AgentOutput, ValidationError
from data.lib.frozen_growth_diagnostic import (
    FROZEN_GROWTH_BUNDLE_SCHEMA_VERSION,
    FrozenInputBundleError,
    validate_frozen_growth_diagnostic_artifact,
)
from data.lib.identity import canonical_ticker
from data.lib.provenance import redact_sensitive_text, redact_sensitive_value


THESIS_DRAFT_INPUT_SCHEMA_VERSION = "m0-strong-agent-thesis-draft-input-v1"
THESIS_DRAFT_ARTIFACT_SCHEMA_VERSION = "m0-strong-agent-thesis-draft-v1"
THESIS_DRAFT_PROMPT_VERSION = "m0-strong-agent-thesis-draft-prompt-v1"
DEFAULT_AGENT = "buffett"


class ThesisDraftInputError(ValueError):
    """Raised when a Thesis draft input cannot be trusted."""


@dataclass(frozen=True)
class ThesisDraftInput:
    canonical_ticker: str
    run_id: str
    dossier_snapshot: str
    profile_version: str
    diagnostic_artifact: dict[str, Any]
    dossier: dict[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ThesisDraftInput":
        if not isinstance(value, Mapping):
            raise ThesisDraftInputError("Thesis draft input must be a mapping")
        allowed = {
            "schema_version",
            "canonical_ticker",
            "run_id",
            "dossier_snapshot",
            "profile_version",
            "diagnostic_artifact",
            "dossier",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ThesisDraftInputError(
                f"Thesis draft input contains unknown fields: {unknown}"
            )
        try:
            if value["schema_version"] != THESIS_DRAFT_INPUT_SCHEMA_VERSION:
                raise ThesisDraftInputError(
                    "unsupported Thesis draft input schema_version"
                )
            ticker = _canonical_text("canonical_ticker", value["canonical_ticker"])
            if ticker != value["canonical_ticker"]:
                raise ThesisDraftInputError("canonical_ticker must be canonical")
            run_id = _safe_leaf("run_id", value["run_id"])
            dossier_snapshot = _required_text(
                "dossier_snapshot", value["dossier_snapshot"]
            )
            profile_version = _required_text(
                "profile_version", value["profile_version"]
            )
            artifact = _required_mapping(
                "diagnostic_artifact", value["diagnostic_artifact"]
            )
            dossier = _required_mapping("dossier", value["dossier"])
        except ThesisDraftInputError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ThesisDraftInputError(
                f"Thesis draft input is invalid: {exc}"
            ) from exc

        diagnostic = artifact.get("diagnostic")
        if not isinstance(diagnostic, Mapping):
            raise ThesisDraftInputError(
                "diagnostic_artifact.diagnostic must be a mapping"
            )
        input_snapshot = diagnostic.get("input_snapshot")
        assumption_snapshot = diagnostic.get("assumption_snapshot")
        if not isinstance(input_snapshot, Mapping) or not isinstance(
            assumption_snapshot, Mapping
        ):
            raise ThesisDraftInputError(
                "diagnostic artifact must contain validated input and assumption snapshots"
            )
        bundle = {
            "schema_version": FROZEN_GROWTH_BUNDLE_SCHEMA_VERSION,
            "canonical_ticker": ticker,
            "run_id": run_id,
            "dossier_snapshot": dossier_snapshot,
            "profile_version": profile_version,
            "diagnostic_input": dict(input_snapshot),
            "assumption_snapshot": dict(assumption_snapshot),
        }
        try:
            validate_frozen_growth_diagnostic_artifact(artifact, bundle)
        except (FrozenInputBundleError, ValueError, TypeError, KeyError) as exc:
            raise ThesisDraftInputError(
                f"diagnostic artifact binding is invalid: {exc}"
            ) from exc
        for field, expected in (
            ("canonical_ticker", ticker),
            ("run_id", run_id),
            ("dossier_snapshot", dossier_snapshot),
            ("profile_version", profile_version),
        ):
            if artifact.get(field) != expected:
                raise ThesisDraftInputError(
                    f"diagnostic artifact {field} does not match draft input"
                )
        if diagnostic.get("ticker") != ticker:
            raise ThesisDraftInputError("diagnostic ticker does not match draft input")
        if artifact.get("gate_status") != "not_passed":
            raise ThesisDraftInputError(
                "diagnostic artifact must retain gate_status=not_passed"
            )
        try:
            _validate_council_input(ticker, dossier)
        except (ValueError, TypeError) as exc:
            raise ThesisDraftInputError(
                f"dossier is not eligible for Thesis drafting: {exc}"
            ) from exc
        return cls(
            canonical_ticker=ticker,
            run_id=run_id,
            dossier_snapshot=dossier_snapshot,
            profile_version=profile_version,
            diagnostic_artifact=dict(artifact),
            dossier=dict(dossier),
        )


@dataclass(frozen=True)
class ThesisDraftArtifacts:
    json_path: Path
    markdown_path: Path


async def run_strong_agent_thesis_draft(
    input_payload: Mapping[str, Any],
    output_dir: str | Path,
    *,
    model: str | None = None,
    agent_id: str = DEFAULT_AGENT,
) -> ThesisDraftArtifacts:
    """执行一次 strong agent 并写出 JSON/Markdown Thesis 草稿。"""
    draft_input = ThesisDraftInput.from_dict(input_payload)
    if agent_id != DEFAULT_AGENT:
        raise ThesisDraftInputError(
            f"M0.2 only supports the default strong agent: {DEFAULT_AGENT}"
        )

    diagnostic = draft_input.diagnostic_artifact["diagnostic"]
    dossier_quality_status, dossier_quality_reasons, _ = evaluate_dossier_quality(
        draft_input.dossier,
        ticker=draft_input.canonical_ticker,
    )
    if dossier_quality_status == "failed":
        raise ThesisDraftInputError(
            "dossier quality is failed; Thesis draft is blocked before LLM"
        )
    directory = _validate_output_dir(output_dir)
    system_prompt = _build_system_prompt(agent_id)
    user_message = _build_user_message(
        draft_input.canonical_ticker,
        draft_input.dossier,
        agent_id=agent_id,
    )
    user_message = _append_diagnostic_context(user_message, diagnostic)
    model_name = model or os.environ.get("LLM_MODEL_HEAVY")
    request_input = {
        "canonical_ticker": draft_input.canonical_ticker,
        "run_id": draft_input.run_id,
        "dossier_snapshot": draft_input.dossier_snapshot,
        "profile_version": draft_input.profile_version,
        "diagnostic_artifact": draft_input.diagnostic_artifact,
        "dossier": draft_input.dossier,
        "agent_id": agent_id,
        "model": model_name,
        "prompt_version": THESIS_DRAFT_PROMPT_VERSION,
    }
    input_digest = _sha256(request_input)
    prompt_digest = _sha256(
        {"system_prompt": system_prompt, "user_message": user_message}
    )

    raw_response = ""
    response_digest = _sha256(raw_response)
    failure_kind: str | None = None
    failure_reason: str | None = None
    usage: dict[str, Any] = {}
    parsed_output: AgentOutput | None = None
    grounding_issues: list[str] = []
    try:
        raw_response, usage = await call_llm(
            system_prompt,
            user_message,
            "heavy",
            model=model_name,
        )
        response_digest = _sha256(raw_response)
        parsed_output = AgentOutput.from_json(agent_id, raw_response)
        try:
            _validate_m0_agent_output(
                parsed_output,
                dossier=draft_input.dossier,
                diagnostic=diagnostic,
                require_normalized=False,
            )
        except ThesisDraftInputError as exc:
            grounding_issues = [str(exc)]
    except Exception as exc:
        failure_kind = _classify_failure(exc)
        failure_reason = _redact_error(exc)

    if parsed_output is None:
        effective_output = _safe_skip_output(
            reason=failure_reason or "strong agent output unavailable"
        )
    elif grounding_issues:
        failure_kind = "grounding"
        failure_reason = "; ".join(grounding_issues)
        effective_output = _safe_skip_output(
            reason="AgentOutput grounding/schema quality check failed",
            pending=grounding_issues,
            risks=list(parsed_output.risks) + grounding_issues,
        )
    elif parsed_output.signal == "skip" or parsed_output.out_of_circle:
        effective_output = _safe_skip_output(
            reason="Agent declined directional conclusion or is out of circle",
            pending=[parsed_output.what_would_change_my_mind],
            risks=list(parsed_output.risks),
        )
    else:
        effective_output = parsed_output

    diagnostic_status = diagnostic["calculation_status"]
    if diagnostic_status in {"not_evaluable", "failed"}:
        effective_output = _safe_skip_output(
            reason=(
                "growth diagnostic is "
                f"{diagnostic_status}; directional conclusion is withheld"
            ),
            pending=list(diagnostic.get("unknowns") or [])
            + list(diagnostic.get("reasons") or []),
            risks=list(effective_output.risks),
        )
        if failure_kind is None:
            failure_kind = "diagnostic_blocked"
            failure_reason = (
                f"diagnostic calculation_status={diagnostic_status}"
            )

    quality_status = _quality_status(
        diagnostic_status=diagnostic_status,
        dossier_quality_status=dossier_quality_status,
        output=effective_output,
        failure_kind=failure_kind,
    )
    quality_reasons = _unique(
        list(diagnostic.get("warnings") or [])
        + list(diagnostic.get("reasons") or [])
        + list(dossier_quality_reasons)
        + ([failure_reason] if failure_reason else [])
    )
    pending_verification = _unique(
        list(diagnostic.get("unknowns") or [])
        + list(diagnostic.get("what_would_change_my_mind") or [])
        + (list(effective_output.risks) if quality_status != "clean" else [])
        + ([failure_reason] if failure_reason else [])
    )
    artifact = {
        "artifact_type": "strong_agent_thesis_draft",
        "artifact_schema_version": THESIS_DRAFT_ARTIFACT_SCHEMA_VERSION,
        "canonical_ticker": draft_input.canonical_ticker,
        "run_id": draft_input.run_id,
        "dossier_snapshot": draft_input.dossier_snapshot,
        "profile_version": draft_input.profile_version,
        "diagnostic_digest": diagnostic["diagnostic_digest"],
        "agent_id": agent_id,
        "model": model_name,
        "prompt_version": THESIS_DRAFT_PROMPT_VERSION,
        "input_digest": input_digest,
        "prompt_digest": prompt_digest,
        "response_digest": response_digest,
        "diagnostic_status": diagnostic_status,
        "diagnostic": redact_sensitive_value(diagnostic),
        "diagnostic_summary": _diagnostic_summary(diagnostic),
        "dossier_quality_status": dossier_quality_status,
        "dossier_quality_reasons": dossier_quality_reasons,
        "agent_output": effective_output.to_dict(),
        "quality_status": quality_status,
        "quality_reasons": quality_reasons,
        "pending_verification": pending_verification,
        "failure_kind": failure_kind,
        "usage": usage or {},
        "capability_status": "mvp_evidence",
        "gate_status": "not_passed",
    }
    artifact["artifact_digest"] = compute_thesis_draft_artifact_digest(artifact)
    json_path = directory / f"{draft_input.canonical_ticker}-{draft_input.run_id}.json"
    markdown_path = directory / f"{draft_input.canonical_ticker}-{draft_input.run_id}.md"
    _write_json(json_path, artifact)
    _write_text(markdown_path, render_thesis_draft_markdown(artifact))
    return ThesisDraftArtifacts(json_path=json_path, markdown_path=markdown_path)


def validate_thesis_draft_artifact(
    artifact: Mapping[str, Any],
    input_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """校验已生成草稿的 envelope、digest 和 AgentOutput。"""
    draft_input = ThesisDraftInput.from_dict(input_payload)
    if not isinstance(artifact, Mapping):
        raise ThesisDraftInputError("Thesis draft artifact must be a mapping")
    required = {
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
        "agent_output",
        "quality_status",
        "quality_reasons",
        "pending_verification",
        "capability_status",
        "gate_status",
        "artifact_digest",
    }
    missing = sorted(required - set(artifact))
    if missing:
        raise ThesisDraftInputError(f"Thesis draft artifact missing fields: {missing}")
    if (
        artifact["artifact_type"] != "strong_agent_thesis_draft"
        or artifact["artifact_schema_version"] != THESIS_DRAFT_ARTIFACT_SCHEMA_VERSION
        or artifact["capability_status"] != "mvp_evidence"
        or artifact["gate_status"] != "not_passed"
    ):
        raise ThesisDraftInputError("Thesis draft artifact envelope is invalid")
    for field, expected in (
        ("canonical_ticker", draft_input.canonical_ticker),
        ("run_id", draft_input.run_id),
        ("dossier_snapshot", draft_input.dossier_snapshot),
        ("profile_version", draft_input.profile_version),
        (
            "diagnostic_digest",
            draft_input.diagnostic_artifact["diagnostic"]["diagnostic_digest"],
        ),
    ):
        if artifact[field] != expected:
            raise ThesisDraftInputError(f"Thesis draft artifact {field} mismatch")
    if artifact["artifact_digest"] != compute_thesis_draft_artifact_digest(artifact):
        raise ThesisDraftInputError("Thesis draft artifact digest mismatch")
    expected_diagnostic = draft_input.diagnostic_artifact["diagnostic"]
    if dict(artifact["diagnostic"]) != dict(expected_diagnostic):
        raise ThesisDraftInputError(
            "nested diagnostic does not match the bound M0.1 artifact"
        )
    if artifact["diagnostic_summary"] != _diagnostic_summary(expected_diagnostic):
        raise ThesisDraftInputError("diagnostic_summary does not match diagnostic")
    if artifact["agent_id"] != DEFAULT_AGENT:
        raise ThesisDraftInputError("unsupported agent_id in Thesis draft artifact")
    output = _validate_m0_agent_output(
        artifact["agent_output"],
        dossier=draft_input.dossier,
        diagnostic=artifact["diagnostic"],
        require_normalized=True,
    )
    return {**dict(artifact), "agent_output": output.to_dict()}


def compute_thesis_draft_artifact_digest(artifact: Mapping[str, Any]) -> str:
    if not isinstance(artifact, Mapping):
        raise ThesisDraftInputError("artifact must be a mapping")
    payload = dict(artifact)
    payload.pop("artifact_digest", None)
    return _sha256(payload)


def render_thesis_draft_markdown(artifact: Mapping[str, Any]) -> str:
    """从同一份 artifact deterministic 渲染人工复核用 Markdown。"""
    output = artifact["agent_output"]
    diagnostic = artifact["diagnostic"]
    lines = [
        f"# Strong-agent Thesis 草稿 — {artifact['canonical_ticker']}",
        "",
        "> 本产物供人工复核；不是正式 InvestmentThesis、不是交易指令、不是 G2 Capability Gate evidence。",
        "",
        "## 运行身份",
        "",
        f"- run_id: `{artifact['run_id']}`",
        f"- dossier_snapshot: `{artifact['dossier_snapshot']}`",
        f"- profile_version: `{artifact['profile_version']}`",
        f"- agent_id: `{artifact['agent_id']}`",
        f"- model: `{artifact['model']}`",
        f"- diagnostic_digest: `{artifact['diagnostic_digest']}`",
        "",
        "## 输入与诊断状态",
        "",
        f"- calculation_status: `{artifact['diagnostic_status']}`",
        f"- diagnostic_quality_status: `{diagnostic['quality_status']}`",
        f"- draft_quality_status: `{artifact['quality_status']}`",
        f"- capability_status: `{artifact['capability_status']}`",
        f"- gate_status: `{artifact['gate_status']}`",
        f"- report_period: `{diagnostic['report_period']}`",
        f"- as_of: `{diagnostic['as_of']}`",
        f"- currency/value_scale: `{diagnostic['currency']}` / `{diagnostic['value_scale']}`",
        "",
        "### 来源",
        "",
    ]
    for source in (diagnostic.get("input_snapshot") or {}).get("sources", []):
        lines.append(
            "- `{source_id}` / field `{field}` / provider `{provider}` / "
            "report_period `{report_period}` / as_of `{as_of}`".format(**source)
        )
    lines.extend(
        [
            "",
            "## Growth diagnostic 摘要",
            "",
            f"- expectation_overdraft: `{diagnostic.get('expectation_overdraft')}`",
            f"- credible_growth_range: `{diagnostic.get('credible_growth_range')}`",
            f"- priced_growth_share_range: `{diagnostic.get('priced_growth_share_range')}`",
            f"- warnings: `{diagnostic.get('warnings') or []}`",
            f"- reasons: `{diagnostic.get('reasons') or []}`",
            "",
            "## Agent 草稿",
            "",
            f"- signal: `{output['signal']}`",
            f"- conviction: `{output['conviction']}`",
            f"- core_thesis: {output['core_thesis']}",
            f"- out_of_circle: `{output['out_of_circle']}`",
            "",
            "### Key metrics",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in output.get("key_metrics", []))
    lines.extend(["", "### Risks", ""])
    lines.extend(f"- {item}" for item in output.get("risks", []))
    lines.extend(
        [
            "",
            "### What would change my mind",
            "",
            output["what_would_change_my_mind"],
            "",
            "## 质量与待验证",
            "",
            "### Quality reasons",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in artifact.get("quality_reasons", []))
    lines.extend(["", "### Pending verification", ""])
    lines.extend(f"- {item}" for item in artifact.get("pending_verification", []))
    if not artifact.get("pending_verification"):
        lines.append("- 无额外待验证项。")
    lines.extend(
        [
            "",
            "## 当前无法证明",
            "",
            "- 本草稿不证明增长一定兑现，不提供目标价，不提供仓位或买卖指令。",
            "- `signal` 只是本次 Agent 的研究观点，不等于稳定投资资格或用户最终决策。",
            "",
            "## 绑定摘要",
            "",
            f"- input_digest: `{artifact['input_digest']}`",
            f"- prompt_digest: `{artifact['prompt_digest']}`",
            f"- response_digest: `{artifact['response_digest']}`",
            f"- artifact_digest: `{artifact['artifact_digest']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_system_prompt(agent_id: str) -> str:
    base = get_prompt_builder(agent_id)()
    return (
        f"{base}\n\n"
        "## M0.2 Thesis 草稿边界\n"
        "你只解释给定 dossier 和 growth diagnostic。不得调用工具、补造事实、"
        "修改 diagnostic 数值或输出目标价、仓位、买卖指令。"
        "如果数据不足、诊断失败或超出能力圈，使用 signal=skip、conviction=0、"
        "out_of_circle=true，并在 risks 和 what_would_change_my_mind 中说明原因。"
    )


def _append_diagnostic_context(user_message: str, diagnostic: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            user_message,
            "",
            "## 固定 growth expectation diagnostic",
            "以下诊断是已校验的冻结输入，只能解释，不能重算、修改或隐藏 warning/reason。",
            json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, indent=2),
            "",
            "请只返回 AgentOutput JSON；不要输出 Markdown、target_price、仓位或交易指令。",
        ]
    )


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


def _safe_skip_output(
    reason: str,
    pending: list[str] | None = None,
    risks: list[str] | None = None,
) -> AgentOutput:
    return AgentOutput.from_dict(
        DEFAULT_AGENT,
        {
            "signal": "skip",
            "conviction": 0,
            "core_thesis": "当前无法形成可发布的方向性研究判断。",
            "key_metrics": [],
            "risks": _unique([reason] + list(risks or [])),
            "what_would_change_my_mind": "补充并核验缺失事实后重新运行。",
            "out_of_circle": True,
            "new_evidence": [],
            "evidence_exhausted": False,
        },
    )


def _m0_agent_output_issues(
    output: AgentOutput,
    *,
    dossier: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    require_normalized: bool = False,
) -> list[str]:
    issues: list[str] = []
    if any(not isinstance(item, str) for item in output.key_metrics):
        issues.append("schema: key_metrics must be a list of strings")
    if output.extra:
        issues.append(
            "schema: AgentOutput contains unsupported M0.2 fields: "
            + ", ".join(sorted(output.extra))
        )
    if not issues:
        _, issues = verify_r1_feature_grounding(
            output,
            {"dossier": dossier, "diagnostic": diagnostic},
        )
        issues = [f"grounding: {issue}" for issue in issues]
    if require_normalized and (output.signal == "skip" or output.out_of_circle):
        if output.signal != "skip" or output.conviction != 0:
            issues.append(
                "schema: skip or out_of_circle AgentOutput must use conviction=0"
            )
    return issues


def _validate_m0_agent_output(
    value: Mapping[str, Any] | AgentOutput,
    *,
    dossier: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    require_normalized: bool,
) -> AgentOutput:
    if isinstance(value, AgentOutput):
        output = value
    else:
        try:
            output = AgentOutput.from_dict(DEFAULT_AGENT, value)
        except (ValidationError, TypeError, KeyError) as exc:
            raise ThesisDraftInputError(f"invalid agent_output: {exc}") from exc
    issues = _m0_agent_output_issues(
        output,
        dossier=dossier,
        diagnostic=diagnostic,
        require_normalized=require_normalized,
    )
    if issues:
        raise ThesisDraftInputError("agent_output validation failed: " + "; ".join(issues))
    if diagnostic["calculation_status"] in {"not_evaluable", "failed"}:
        if output.signal != "skip" or output.conviction != 0:
            raise ThesisDraftInputError(
                "blocked diagnostic cannot publish directional agent output"
            )
    return output


def _quality_status(
    *,
    diagnostic_status: str,
    dossier_quality_status: str,
    output: AgentOutput,
    failure_kind: str | None,
) -> str:
    if failure_kind or diagnostic_status in {"not_evaluable", "failed"}:
        return "failed"
    if (
        diagnostic_status == "degraded"
        or dossier_quality_status != "clean"
        or output.signal == "skip"
        or output.out_of_circle
    ):
        return "warning"
    return "clean"


def _classify_failure(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "schema"
    return "transport" if exc.__class__.__module__.startswith("httpx") else "internal"


def _redact_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {redact_sensitive_text(str(exc))}"


def _sha256(value: Any) -> str:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=str,
        )
    except (TypeError, ValueError) as exc:
        raise ThesisDraftInputError("Thesis draft value is not strict JSON") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _required_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ThesisDraftInputError(f"{name} is required")
    return value.strip()


def _canonical_text(name: str, value: Any) -> str:
    text = _required_text(name, value)
    try:
        return canonical_ticker(text)
    except (TypeError, ValueError) as exc:
        raise ThesisDraftInputError(f"{name} is not a valid ticker") from exc


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
        raise ThesisDraftInputError(
            f"{name} must be a non-empty relative path leaf"
        )
    return text


def _required_mapping(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ThesisDraftInputError(f"{name} must be a non-empty mapping")
    return dict(value)


def _validate_output_dir(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ThesisDraftInputError("output_dir is required")
    directory = Path(value)
    if directory.exists() and not directory.is_dir():
        raise ThesisDraftInputError("output_dir must be a directory")
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ThesisDraftInputError("output_dir is not writable") from exc
    return directory


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _write_text(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def _write_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in result:
            result.append(value)
    return result
