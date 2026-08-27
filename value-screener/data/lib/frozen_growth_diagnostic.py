"""M0.1 frozen-input adapter for the deterministic growth diagnostic."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from data.lib.growth_expectation_contract import (
    AssumptionSnapshot,
    ContractError,
    DiagnosticInput,
    validate_assumption_snapshot,
    validate_diagnostic_input,
)
from data.lib.growth_expectation_engine import (
    FORMULA_VERSION,
    compute_growth_expectation_diagnostic,
    validate_growth_expectation_artifact,
)
from data.lib.identity import canonical_ticker


FROZEN_GROWTH_BUNDLE_SCHEMA_VERSION = "m0-frozen-growth-diagnostic-bundle-v1"
FROZEN_GROWTH_ARTIFACT_SCHEMA_VERSION = "m0-frozen-growth-diagnostic-artifact-v1"


class FrozenInputBundleError(ValueError):
    """Raised when the explicit M0.1 input envelope cannot be trusted."""


@dataclass(frozen=True)
class FrozenGrowthDiagnosticBundle:
    canonical_ticker: str
    run_id: str
    dossier_snapshot: str
    profile_version: str
    diagnostic_input: DiagnosticInput
    assumption_snapshot: AssumptionSnapshot

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FrozenGrowthDiagnosticBundle":
        if not isinstance(value, Mapping):
            raise FrozenInputBundleError("frozen input bundle must be a mapping")
        allowed = {
            "schema_version",
            "canonical_ticker",
            "run_id",
            "dossier_snapshot",
            "profile_version",
            "diagnostic_input",
            "assumption_snapshot",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise FrozenInputBundleError(
                f"frozen input bundle contains unknown fields: {unknown}"
            )
        try:
            schema_version = _require_text("schema_version", value["schema_version"])
            if schema_version != FROZEN_GROWTH_BUNDLE_SCHEMA_VERSION:
                raise FrozenInputBundleError("unsupported frozen input bundle schema_version")
            raw_ticker = _require_text("canonical_ticker", value["canonical_ticker"])
            ticker = canonical_ticker(raw_ticker)
            if ticker != raw_ticker:
                raise FrozenInputBundleError("canonical_ticker must be canonical")
            run_id = _validate_run_id(value["run_id"])
            dossier_snapshot = _require_text("dossier_snapshot", value["dossier_snapshot"])
            profile_version = _require_text("profile_version", value["profile_version"])
            diagnostic_input = validate_diagnostic_input(value["diagnostic_input"])
            assumption_snapshot = validate_assumption_snapshot(value["assumption_snapshot"])
        except (ContractError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, FrozenInputBundleError):
                raise
            detail = exc.args[0] if exc.args else str(exc)
            raise FrozenInputBundleError(f"frozen input bundle is invalid: {detail}") from exc
        if diagnostic_input.ticker != ticker:
            raise FrozenInputBundleError(
                "canonical_ticker does not match diagnostic_input.ticker"
            )
        return cls(
            canonical_ticker=ticker,
            run_id=run_id,
            dossier_snapshot=dossier_snapshot,
            profile_version=profile_version,
            diagnostic_input=diagnostic_input,
            assumption_snapshot=assumption_snapshot,
        )


@dataclass(frozen=True)
class FrozenGrowthDiagnosticArtifacts:
    json_path: Path
    markdown_path: Path


def run_frozen_input_growth_diagnostic(
    bundle_payload: Mapping[str, Any],
    output_dir: str | Path,
) -> FrozenGrowthDiagnosticArtifacts:
    """Run the existing deterministic diagnostic from an explicit frozen bundle."""
    bundle = FrozenGrowthDiagnosticBundle.from_dict(bundle_payload)
    directory = _validate_output_dir(output_dir)

    diagnostic = compute_growth_expectation_diagnostic(
        bundle.diagnostic_input,
        bundle.assumption_snapshot,
        dossier_snapshot=bundle.dossier_snapshot,
        profile_version=bundle.profile_version,
    )
    validated = validate_growth_expectation_artifact(
        diagnostic.to_dict(),
        ticker=bundle.canonical_ticker,
        input_payload=bundle.diagnostic_input.to_dict(),
        assumption_snapshot=bundle.assumption_snapshot.to_dict(),
        formula_version=FORMULA_VERSION,
        dossier_snapshot=bundle.dossier_snapshot,
        profile_version=bundle.profile_version,
    )
    artifact = _artifact_payload(bundle, validated.to_dict())
    validate_frozen_growth_diagnostic_artifact(artifact, bundle_payload)
    json_path = directory / f"{bundle.canonical_ticker}-{bundle.run_id}.json"
    markdown_path = directory / f"{bundle.canonical_ticker}-{bundle.run_id}.md"
    _write_json(json_path, artifact)
    _write_text(markdown_path, render_frozen_growth_diagnostic_markdown(artifact))
    return FrozenGrowthDiagnosticArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
    )


def validate_frozen_growth_diagnostic_artifact(
    artifact: Mapping[str, Any],
    bundle_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate envelope identity, envelope digest, and existing diagnostic binding."""
    bundle = FrozenGrowthDiagnosticBundle.from_dict(bundle_payload)
    if not isinstance(artifact, Mapping):
        raise FrozenInputBundleError("frozen diagnostic artifact must be a mapping")
    required = {
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
    missing = sorted(required - set(artifact))
    if missing:
        raise FrozenInputBundleError(
            f"frozen diagnostic artifact is missing fields: {missing}"
        )
    if (
        artifact["artifact_type"] != "growth_expectation_diagnostic"
        or artifact["artifact_schema_version"] != FROZEN_GROWTH_ARTIFACT_SCHEMA_VERSION
        or artifact["capability_status"] != "mvp_evidence"
        or artifact["gate_status"] != "not_passed"
    ):
        raise FrozenInputBundleError("frozen diagnostic artifact envelope is invalid")
    for field, expected in (
        ("canonical_ticker", bundle.canonical_ticker),
        ("run_id", bundle.run_id),
        ("dossier_snapshot", bundle.dossier_snapshot),
        ("profile_version", bundle.profile_version),
    ):
        if artifact[field] != expected:
            raise FrozenInputBundleError(f"frozen diagnostic artifact {field} mismatch")
    if artifact["artifact_digest"] != compute_frozen_growth_artifact_digest(artifact):
        raise FrozenInputBundleError("frozen diagnostic artifact digest mismatch")
    try:
        validated = validate_growth_expectation_artifact(
            artifact["diagnostic"],
            ticker=bundle.canonical_ticker,
            input_payload=bundle.diagnostic_input.to_dict(),
            assumption_snapshot=bundle.assumption_snapshot.to_dict(),
            formula_version=FORMULA_VERSION,
            dossier_snapshot=bundle.dossier_snapshot,
            profile_version=bundle.profile_version,
        )
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        raise FrozenInputBundleError(
            f"frozen diagnostic artifact binding is invalid: {exc}"
        ) from exc
    return {
        **dict(artifact),
        "diagnostic": validated.to_dict(),
    }


def compute_frozen_growth_artifact_digest(artifact: Mapping[str, Any]) -> str:
    """Compute the envelope digest, including run identity and diagnostic digest."""
    if not isinstance(artifact, Mapping):
        raise FrozenInputBundleError("frozen diagnostic artifact must be a mapping")
    payload = dict(artifact)
    payload.pop("artifact_digest", None)
    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FrozenInputBundleError("frozen diagnostic artifact is not strict JSON") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def render_frozen_growth_diagnostic_markdown(artifact: Mapping[str, Any]) -> str:
    """Render one deterministic, non-advisory diagnostic summary."""
    diagnostic = artifact["diagnostic"]
    lines = [
        f"# Growth expectation diagnostic — {artifact['canonical_ticker']}",
        "",
        "## 状态",
        "",
        f"- calculation_status: `{diagnostic['calculation_status']}`",
        f"- quality_status: `{diagnostic['quality_status']}`",
        f"- decision_grade: `{diagnostic['decision_grade']}`",
        f"- capability_status: `{artifact['capability_status']}`",
        f"- gate_status: `{artifact['gate_status']}`",
        "",
        "## 输入身份与来源",
        "",
        f"- run_id: `{artifact['run_id']}`",
        f"- dossier_snapshot: `{artifact['dossier_snapshot']}`",
        f"- profile_version: `{artifact['profile_version']}`",
        f"- report_period: `{diagnostic['report_period']}`",
        f"- as_of: `{diagnostic['as_of']}`",
        f"- currency/value_scale: `{diagnostic['currency']}` / `{diagnostic['value_scale']}`",
    ]
    input_snapshot = diagnostic.get("input_snapshot")
    if input_snapshot:
        for source in input_snapshot["sources"]:
            lines.append(
                "- source_id: `{source_id}`; field: `{field}`; provider: `{provider}`; "
                "report_period: `{report_period}`; as_of: `{as_of}`".format(**source)
            )

    lines.extend(["", "## 用户确认的假设", ""])
    assumption_snapshot = diagnostic.get("assumption_snapshot")
    if assumption_snapshot:
        for assumption in assumption_snapshot["assumptions"]:
            lines.append(
                f"- `{assumption['key']}`: `{_format_value(assumption['value'])}` "
                f"{assumption['unit']} (source: `{assumption['source']}`, "
                f"confirmed_by_user: `{assumption['confirmed_by_user']}`)"
            )
    else:
        lines.append("- 无可用 assumption snapshot。")

    lines.extend(["", "## 诊断结果", ""])
    if diagnostic["calculation_status"] in {"clean", "degraded"}:
        business = diagnostic["current_business_value"]
        lines.extend(
            [
                f"- 当前市值: `{diagnostic['current_market_value']}`",
                f"- EPV proxy: `{_format_value(business['epv_proxy_range'])}`",
                f"- 成熟期估值交叉锚: `{_format_value(business['mature_multiple_range'])}`",
                f"- 未来增长价值区间: `{_format_value(diagnostic['priced_growth_value_range'])}`",
                f"- 未来增长价值占比: `{_format_value(diagnostic['priced_growth_share_range'])}`",
                f"- 可信增长区间: `{_format_value(diagnostic['credible_growth_range'])}`",
                f"- 预期透支等级: `{diagnostic['expectation_overdraft']}`",
                f"- 已前置兑现年限: `{diagnostic['value_pulled_forward_years']}`",
                "",
                "### Reverse scenarios",
                "",
            ]
        )
        for scenario in diagnostic["reverse_scenarios"]:
            if scenario["mode"] == "fixed_growth_rate":
                lines.append(
                    f"- {scenario['scenario']}: growth_rate=`{scenario['growth_rate']}`, "
                    "implied_high_growth_duration="
                    f"`{scenario['implied_high_growth_duration']}`"
                )
            else:
                lines.append(
                    f"- {scenario['scenario']}: duration_years=`{scenario['duration_years']}`, "
                    f"implied_growth_rate=`{scenario['implied_growth_rate']}`"
                )
    else:
        lines.extend(
            [
                f"- failure_kind: `{diagnostic['failure_kind']}`",
                f"- reason_codes: `{', '.join(diagnostic['reason_codes'])}`",
            ]
        )

    lines.extend(["", "## Warnings 与原因", ""])
    for warning in diagnostic["warnings"]:
        lines.append(f"- warning: `{warning}`")
    for reason in diagnostic["reasons"]:
        lines.append(f"- reason: {reason}")
    if not diagnostic["warnings"] and not diagnostic["reasons"]:
        lines.append("- 无额外 warning 或 failure reason。")

    lines.extend(
        [
            "",
            "## 当前无法证明",
            "",
            "- 本诊断不证明未来增长一定兑现，也不证明任何投资或交易结论。",
            "",
            "## 绑定与边界",
            "",
            f"- input_digest: `{diagnostic['input_digest']}`",
            f"- diagnostic_digest: `{diagnostic['diagnostic_digest']}`",
            "- 本产物仅为 diagnostic，不是目标价、投资建议或 G2 Capability Gate evidence。",
        ]
    )
    return "\n".join(lines) + "\n"


def _artifact_payload(
    bundle: FrozenGrowthDiagnosticBundle,
    diagnostic: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "artifact_type": "growth_expectation_diagnostic",
        "artifact_schema_version": FROZEN_GROWTH_ARTIFACT_SCHEMA_VERSION,
        "canonical_ticker": bundle.canonical_ticker,
        "run_id": bundle.run_id,
        "dossier_snapshot": bundle.dossier_snapshot,
        "profile_version": bundle.profile_version,
        "capability_status": "mvp_evidence",
        "gate_status": "not_passed",
        "diagnostic": dict(diagnostic),
    }
    payload["artifact_digest"] = compute_frozen_growth_artifact_digest(payload)
    return payload


def _validate_run_id(value: Any) -> str:
    run_id = _require_text("run_id", value)
    path = Path(run_id)
    if (
        run_id in {".", ".."}
        or path.is_absolute()
        or "/" in run_id
        or "\\" in run_id
        or path.name != run_id
    ):
        raise FrozenInputBundleError("run_id must be a non-empty relative path leaf")
    return run_id


def _validate_output_dir(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise FrozenInputBundleError("output_dir is required")
    try:
        directory = Path(value)
        if directory.exists() and not directory.is_dir():
            raise FrozenInputBundleError("output_dir must be a directory")
        directory.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise FrozenInputBundleError("output_dir is not a valid writable directory") from exc
    return directory


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FrozenInputBundleError(f"{name} is required")
    return value.strip()


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


def _format_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)
