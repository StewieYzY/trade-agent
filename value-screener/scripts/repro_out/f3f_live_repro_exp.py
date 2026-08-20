#!/usr/bin/env python3
"""f3f live LLM final reproduction harness.

This is the bounded live follow-up authorized after the fixture/dry-run diagnosis.
It does not modify the main prompt or debate orchestration. It calls the LLM
directly with the current prompt builders and an insufficient-features proxy for
the historical flat-features path, then records raw/parsed output, usage, and
the current crosstalk/grounding detectors.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

VALUE_SCREENER_ROOT = Path(__file__).resolve().parents[2]
if str(VALUE_SCREENER_ROOT) not in sys.path:
    sys.path.insert(0, str(VALUE_SCREENER_ROOT))

from council.agents import AGENT_REGISTRY, get_prompt_builder
from council.debate import _build_user_message
from council.llm import call_llm
from council.schema import AgentOutput
from council.verify_quality_gate import detect_circular_reference, verify_r1_feature_grounding
from data.lib.audit_chain import payload_sha256
from data.lib.identity import canonical_ticker


REQUIRED_ENV_KEYS = (
    "LLM_API_KEY",
    "LLM_API_BASE",
    "LLM_MODEL",
    "LLM_MODEL_HEAVY",
    "LLM_MODEL_MODERATE",
)


def _load_env(env_path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def model_configuration(env_values: dict[str, str]) -> dict[str, str]:
    missing = [key for key in REQUIRED_ENV_KEYS if not env_values.get(key)]
    if missing:
        raise ValueError(f"live experiment env missing required keys: {missing}")
    return {
        "heavy_model": env_values["LLM_MODEL_HEAVY"],
        "moderate_model": env_values["LLM_MODEL_MODERATE"],
        "reasoning_levels": ["heavy", "moderate"],
    }


def _provider_hostname(api_base: str) -> str:
    """Return only the provider hostname; never log keys, paths, or userinfo."""
    parsed = urlparse(api_base)
    return parsed.hostname or "unknown-provider"


def insufficient_features() -> dict[str, Any]:
    """Historical flat-features proxy: the pre-f1 path could reach the LLM with
    critical basic dimensions missing. The exact historical bytes were not
    committed, so an empty feature dict is used as the most conservative proxy.
    """
    return {}


def build_live_user_message(ticker: str, features: dict[str, Any]) -> str:
    return _build_user_message(ticker, features, other_opinions=None, agent_id=None)


async def _run_r1_round(
    ticker: str,
    agents: list[str],
    features: dict[str, Any],
    heavy_model: str,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for agent_id in agents:
        system_prompt = get_prompt_builder(agent_id)()
        user_message = build_live_user_message(ticker, features)
        raw, usage = await call_llm(system_prompt, user_message, "heavy", model=heavy_model)
        try:
            output = AgentOutput.from_json(agent_id, raw)
            parse_status = "ok"
        except Exception as exc:  # pragma: no cover - depends on live model output
            output = None
            parse_status = f"parse_failed: {exc}"
        circ_ok = True
        circ_issues: list[str] = []
        ground_ok = True
        ground_issues: list[str] = []
        if output is not None:
            circ_ok, circ_issues = detect_circular_reference(output)
            ground_ok, ground_issues = verify_r1_feature_grounding(output, features)
        records.append(
            {
                "agent": agent_id,
                "ticker": canonical_ticker(ticker),
                "system_prompt_sha256": payload_sha256({"system_prompt": system_prompt}),
                "user_message_sha256": payload_sha256({"user_message": user_message}),
                "model": heavy_model,
                "usage": usage,
                "parse_status": parse_status,
                "raw_response": raw,
                "parsed_output": output.to_dict() if output is not None else None,
                "circular_reference_detected": not circ_ok,
                "circular_reference_issues": circ_issues,
                "grounding_passed": ground_ok,
                "grounding_issues": ground_issues,
            }
        )
    return {
        "ticker": canonical_ticker(ticker),
        "features_sha256": payload_sha256(features),
        "records": records,
    }


async def run_live_experiment(
    output_root: str | Path,
    env_path: str | Path,
    *,
    authorize_live: bool,
    modes: dict[str, list[str]] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run the authorized live R1 reproduction and write evidence safely."""
    if not authorize_live:
        raise ValueError("live LLM requires explicit authorization")
    env_values = _load_env(env_path)
    config = model_configuration(env_values)
    os.environ.update(env_values)
    heavy_model = config["heavy_model"]
    modes = modes or {
        "600900.SH": ["buffett"],
        "600519.SH": ["buffett", "munger", "duan", "feng_liu"],
    }

    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    branches: dict[str, Any] = {}
    for ticker, agents in modes.items():
        ticker = canonical_ticker(ticker)
        features = insufficient_features()
        branch = await _run_r1_round(ticker, agents, features, heavy_model)
        branches[ticker] = branch

    payload = {
        "mode": "live",
        "authorized": True,
        "run_id": run_id or "f3f-live-diagnostic",
        "provider": _provider_hostname(env_values["LLM_API_BASE"]),
        "model_configuration": {
            "heavy_model": heavy_model,
            "moderate_model": config["moderate_model"],
            "reasoning_levels": config["reasoning_levels"],
        },
        "input_note": "insufficient-features proxy for historical flat-features path",
        "branches": branches,
    }
    data_path = output_root / "f3f_live_repro_data.json"
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_live_report(output_root, payload)
    return payload


def write_live_report(output_root: str | Path, payload: dict[str, Any]) -> str:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    lines = [
        "# f3f live LLM 最终复现报告",
        "",
        "## 边界",
        "- 这是授权后的受控 live R1 调用，使用当前 prompt builder + insufficient-features 代理。",
        "- 不修改主 prompt/debate，不调用 provider 数据源，不宣称 G2 capability passed。",
        f"- provider: {payload.get('provider', '')}",
        f"- heavy_model: {payload.get('model_configuration', {}).get('heavy_model', '')}",
        "",
        "## 输入边界",
        str(payload.get("input_note", "")),
        "",
        "## 结果",
    ]
    for ticker, branch in payload.get("branches", {}).items():
        lines.append(f"### {ticker}")
        for record in branch.get("records", []):
            lines.append(
                f"- {record.get('agent')}: circular={record.get('circular_reference_detected')} "
                f"grounding={record.get('grounding_passed')} parse={record.get('parse_status')}"
            )
    report = "\n".join(lines)
    (output_root / "f3f_live_repro_report.md").write_text(report, encoding="utf-8")
    return report


async def _async_main() -> int:
    parser = argparse.ArgumentParser(description="f3f authorized live R1 reproduction")
    parser.add_argument("--env", default="value-screener/.env")
    parser.add_argument("--output-root", default="value-screener/scripts/repro_out/f3f_live_repro")
    parser.add_argument("--authorize-live", action="store_true")
    parser.add_argument("--run-id", default="f3f-live-diagnostic")
    args = parser.parse_args()
    result = await run_live_experiment(
        args.output_root,
        args.env,
        authorize_live=args.authorize_live,
        run_id=args.run_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
