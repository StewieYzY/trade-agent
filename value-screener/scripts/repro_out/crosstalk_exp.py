#!/usr/bin/env python3
"""f3c D1 controlled-experiment scaffold.

This module deliberately refuses live calls unless supplied a verified,
frozen 600009.SH dossier.  It never edits ``council/prompt.py``.
"""
from __future__ import annotations

import json
import hashlib
import re
import sys
import os
import asyncio
import uuid
from pathlib import Path
from typing import Any

VALUE_SCREENER_ROOT = Path(__file__).resolve().parents[2]
if str(VALUE_SCREENER_ROOT) not in sys.path:
    sys.path.insert(0, str(VALUE_SCREENER_ROOT))

from council.agents import get_prompt_builder  # noqa: E402
from council.llm import call_llm  # noqa: E402
from council.schema import AgentOutput  # noqa: E402
from council.verify_quality_gate import (  # noqa: E402
    compute_citation_divergence,
    detect_circular_reference,
    verify_r1_feature_grounding,
)


CONTROL_GROUPS = (
    {"id": "group1", "features": "sufficient", "prompt": "retained", "model": "weak"},
    {"id": "group2", "features": "missing", "prompt": "retained", "model": "weak"},
    {"id": "group3", "features": "missing", "prompt": "stripped", "model": "weak"},
    {"id": "group4", "features": "missing", "prompt": "retained", "model": "strong"},
)

_CASE_SECTIONS = {
    "buffett": (r"### 护城河分类.*?(?=### 你不会买的股票)", re.S),
    "munger": (r"### 你的核心案例.*?(?=### 你的内在矛盾)", re.S),
    "duan": (r"### 你实际买过的股票.*?(?=### 你不会买的股票)", re.S),
    "feng_liu": (r"### 真实案例锚定.*?(?=### 你的内在矛盾)", re.S),
}

REQUIRED_CACHE_FILES = (
    "basic.json",
    "financials.json",
    "kline.json",
    "main_business.json",
    "research.json",
    "risk.json",
    "valuation.json",
)


def write_live_report(output_root: Path, payload: dict[str, Any]) -> str:
    """Write a bounded D1/D3 report and return its markdown."""
    groups = payload["groups"]
    baseline = groups["group2"]["metrics"]["explicit_crosstalk_rate"]
    g3 = groups["group3"]["metrics"]["explicit_crosstalk_rate"]
    g4 = groups["group4"]["metrics"]["explicit_crosstalk_rate"]
    if g3 < baseline and g4 >= baseline:
        conclusion = "A_prompt_design"
    elif g4 < baseline and g3 >= baseline:
        conclusion = "B_model"
    elif g3 < baseline and g4 < baseline:
        conclusion = "A+B_mixed"
    else:
        conclusion = "neither"
    lines = [
        "# f3c D1/D3 R1 串台根因实验报告",
        "",
        "> 使用真实 LLM 调用；输入为由根目录 600009 cache 只读拼装并冻结的 dossier。",
        "> 未执行 provider refresh；结论不外推为全 provider/runtime capability。",
        "",
        f"- 模式：`{payload['mode']}`",
        f"- 输入模式：`{payload['input_mode']}`",
        f"- source dossier sha256：`{payload['source_sha256']}`",
        f"- D1 分叉：`{conclusion}`",
        "",
        "| group | features | prompt | model | status | explicit | implicit | Jaccard | fabricated |",
        "|---|---|---|---|---|---:|---:|---:|---:|",
    ]
    for group in CONTROL_GROUPS:
        item = groups[group["id"]]
        metrics = item["metrics"]
        lines.append(
            f"| {group['id']} | {group['features']} | {group['prompt']} | {group['model']} | "
            f"{item['status']} | {metrics['explicit_crosstalk_rate']:.2f} | "
            f"{metrics['implicit_crosstalk_rate']:.2f} | "
            f"{metrics['citation_divergence']['mean_distance']:.2f} | "
            f"{metrics['fabricated_number_rate']:.2f} |"
        )
    g2_implicit = groups["group2"]["metrics"]["implicit_crosstalk_rate"]
    lines.extend([
        "",
        "## D3",
        "",
        f"- group2 隐性串台占比：`{g2_implicit:.2f}`（4 条 R1 `core_thesis` 的规则采样）。",
        "- 规则：core_thesis 命中「其他/另一位/共识/也看好/大家/都看好」即候选。",
        f"- >0.25 建议独立语义检测；本次判断："
        f"`{'建议开独立语义检测 change' if g2_implicit > 0.25 else '字符串检测暂够用（低样本、规则级结论，不等于语义排除）'}`。",
        "",
        "## 边界",
        "",
        "prompt/model 修复不在本 change 实施。若四态为皆否，后续开独立 f3e；"
        "若为 A/B/混合，按 proposal 分叉开独立 f3d。",
    ])
    report = "\n".join(lines) + "\n"
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "crosstalk_exp_report.md").write_text(report, encoding="utf-8")
    return report


def build_prompt_variant(agent_id: str, mode: str) -> str:
    """Build an experiment-local prompt variant without mutating prompt.py."""
    prompt = get_prompt_builder(agent_id)()
    if mode == "retained":
        return prompt
    if mode != "stripped":
        raise ValueError(f"unknown prompt mode: {mode}")
    pattern, flags = _CASE_SECTIONS[agent_id]
    stripped = re.sub(pattern, "", prompt, count=1, flags=flags)
    if stripped == prompt:
        raise ValueError(f"case-anchor section not found for {agent_id}")
    return stripped


def load_verified_dossier(path: Path) -> dict[str, Any]:
    """Load only a frozen, identity-bound 600009.SH dossier for live D1."""
    if not path.is_file():
        raise ValueError(f"verified dossier missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "error" in data:
        raise ValueError("verified dossier required; insufficient/error snapshot is rejected")
    snapshot = data.get("core_snapshot")
    research = data.get("research_dossier")
    ticker = snapshot.get("ticker") if isinstance(snapshot, dict) else None
    if ticker != "600009.SH":
        raise ValueError("verified dossier must bind to canonical ticker 600009.SH")
    if not isinstance(research, dict) or not research.get("main_business"):
        raise ValueError("verified dossier must include research_dossier.main_business")
    return data


def build_frozen_dossier(source_dir: Path, output_path: Path) -> dict[str, Any]:
    """Read 600009 cache files without mutation and write a hashed dossier envelope."""
    source_dir = source_dir.resolve()
    output_path = output_path.resolve()
    if not source_dir.is_dir():
        raise ValueError(f"cache source directory missing: {source_dir}")

    raw: dict[str, Any] = {}
    source_hash = hashlib.sha256()
    source_files: list[str] = []
    for filename in REQUIRED_CACHE_FILES:
        path = source_dir / filename
        if not path.is_file():
            raise ValueError(f"cache source missing required file: {filename}")
        content = path.read_bytes()
        source_hash.update(filename.encode("utf-8"))
        source_hash.update(b"\0")
        source_hash.update(content)
        raw[filename.removesuffix(".json")] = json.loads(content)
        source_files.append(filename)

    basic = raw["basic"]
    valuation = raw["valuation"]
    financials = raw["financials"]
    risk = raw["risk"]
    main_business = raw["main_business"]
    research = raw["research"]

    income = financials.get("income", {}) if isinstance(financials, dict) else {}
    balance = financials.get("balance_sheet", {}) if isinstance(financials, dict) else {}
    cash_flow = financials.get("cash_flow", {}) if isinstance(financials, dict) else {}
    roe_series = (
        income.get("roe_3y")
        or income.get("roe")
        or income.get("ROE")
        or []
    )
    net_margin = (
        income.get("net_margin")
        or income.get("net_margin_3y")
        or income.get("NET_PROFIT_MARGIN")
    )
    revenue_growth = (
        income.get("revenue_growth")
        or income.get("revenue_growth_3y")
        or income.get("YOY_NET_PROFIT")
    )
    core_snapshot = {
        "ticker": "600009.SH",
        "name": basic.get("name"),
        "industry": basic.get("industry"),
        "price": basic.get("price"),
        "pe_ttm": valuation.get("pe_ttm", basic.get("pe")),
        "pb": valuation.get("pb", basic.get("pb")),
        "market_cap": basic.get("market_cap"),
        "pe_percentile_5y": valuation.get("pe_percentile_5y"),
        "pb_percentile_5y": valuation.get("pb_percentile_5y"),
        "roe_3y": roe_series,
        "net_margin": net_margin,
        "revenue_growth": revenue_growth,
        "debt_ratio": balance.get("debt_ratio"),
        "operating_cashflow": cash_flow.get("operating_cashflow"),
        "net_profit": income.get("net_profit"),
    }
    dossier = {
        "core_snapshot": core_snapshot,
        "research_dossier": {
            "main_business": main_business,
            "research": research,
            "peers": {"__error__": True, "reason": "not present in frozen source"},
            "capex_proxy": {
                "series": cash_flow.get("CONSTRUCT_LONG_ASSET", []),
                "years": financials.get("years", []),
            },
            "degraded_fields": ["peers"],
        },
        "pledge": risk.get("pledge_ratio"),
        "freeze": {
            "canonical_ticker": "600009.SH",
            "source_ticker": "600009",
            "source_dir": str(source_dir),
            "source_files": source_files,
            "source_sha256": source_hash.hexdigest(),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dossier, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dossier


async def run_live_experiment(
    output_root: Path,
    env_path: Path,
    dossier_path: Path,
) -> dict[str, Any]:
    """Run four R1 groups against one verified frozen dossier."""
    dossier = load_verified_dossier(dossier_path)
    values = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = ("LLM_API_KEY", "LLM_API_BASE", "LLM_MODEL", "LLM_MODEL_HEAVY")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError(f"live experiment env missing required keys: {missing}")

    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        run_id = str(uuid.uuid4())
        output_root.mkdir(parents=True, exist_ok=True)
        raw_dir = output_root / "crosstalk_exp_raw"
        raw_dir.mkdir(exist_ok=True)
        groups = {}
        for group in CONTROL_GROUPS:
            features = dossier if group["features"] == "sufficient" else {}
            model = values["LLM_MODEL"] if group["model"] == "weak" else values["LLM_MODEL_HEAVY"]
            outputs = []
            records = []
            for agent_id in ("buffett", "munger", "duan", "feng_liu"):
                system_prompt = build_prompt_variant(agent_id, group["prompt"])
                user_message = (
                    f"请分析股票 600009.SH。\n"
                    f"特征数据：{json.dumps(features, ensure_ascii=False)}\n"
                    "请独立判断，不参考其他分析师观点。"
                )
                try:
                    raw, usage = await call_llm(system_prompt, user_message, "heavy", model=model)
                    output = AgentOutput.from_json(agent_id, raw)
                    outputs.append(output)
                    records.append({
                        "agent": agent_id,
                        "run_id": run_id,
                        "status": "ok",
                        "model": model,
                        "system_prompt_sha256": hashlib.sha256(
                            system_prompt.encode("utf-8")
                        ).hexdigest(),
                        "user_message_sha256": hashlib.sha256(
                            user_message.encode("utf-8")
                        ).hexdigest(),
                        "dossier_sha256": dossier["freeze"]["source_sha256"],
                        "raw_response": raw,
                        "output": output.to_dict(),
                        "usage": usage,
                    })
                except Exception as exc:
                    records.append({
                        "agent": agent_id,
                        "run_id": run_id,
                        "status": "error",
                        "model": model,
                        "system_prompt_sha256": hashlib.sha256(
                            system_prompt.encode("utf-8")
                        ).hexdigest(),
                        "user_message_sha256": hashlib.sha256(
                            user_message.encode("utf-8")
                        ).hexdigest(),
                        "dossier_sha256": dossier["freeze"]["source_sha256"],
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:500],
                    })
            metrics = {}
            if outputs:
                explicit = [not detect_circular_reference(o)[0] for o in outputs]
                fabricated = [
                    not verify_r1_feature_grounding(o, features)[0]
                    for o in outputs
                ]
                implicit_terms = ("其他", "另一位", "共识", "也看好", "大家", "都看好")
                implicit = [any(term in o.core_thesis for term in implicit_terms) for o in outputs]
                metrics = {
                    "explicit_crosstalk_rate": sum(explicit) / len(outputs),
                    "implicit_crosstalk_rate": sum(implicit) / len(outputs),
                    "fabricated_number_rate": sum(fabricated) / len(outputs),
                    "citation_divergence": compute_citation_divergence(outputs),
                }
            payload = {**group, "status": "complete" if len(outputs) == 4 else "incomplete",
                       "input_mode": "frozen_dossier", "records": records, "metrics": metrics}
            groups[group["id"]] = payload
            (raw_dir / f"{group['id']}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        result = {
            "mode": "live",
            "run_id": run_id,
            "input_mode": "frozen_dossier",
            "dossier_path": str(dossier_path),
            "source_sha256": dossier["freeze"]["source_sha256"],
            "groups": groups,
        }
        (output_root / "crosstalk_exp_data.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        write_live_report(output_root, result)
        return result
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def repair_live_bundle(output_root: Path, dossier_path: Path) -> dict[str, Any]:
    """Enrich an existing live bundle without issuing new LLM calls."""
    dossier = load_verified_dossier(dossier_path)
    data_path = output_root / "crosstalk_exp_data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    run_id = data.setdefault("run_id", str(uuid.uuid4()))
    for group in CONTROL_GROUPS:
        group_path = output_root / "crosstalk_exp_raw" / f"{group['id']}.json"
        payload = json.loads(group_path.read_text(encoding="utf-8"))
        features = dossier if group["features"] == "sufficient" else {}
        for record in payload["records"]:
            agent_id = record["agent"]
            prompt = build_prompt_variant(agent_id, group["prompt"])
            user_message = (
                "请分析股票 600009.SH。\n"
                f"特征数据：{json.dumps(features, ensure_ascii=False)}\n"
                "请独立判断，不参考其他分析师观点。"
            )
            record["system_prompt_sha256"] = hashlib.sha256(
                prompt.encode("utf-8")
            ).hexdigest()
            record["user_message_sha256"] = hashlib.sha256(
                user_message.encode("utf-8")
            ).hexdigest()
            record["dossier_sha256"] = dossier["freeze"]["source_sha256"]
            record["run_id"] = run_id
            if record["status"] == "ok" and "output" not in record:
                record["output"] = AgentOutput.from_json(
                    agent_id, record["raw_response"]
                ).to_dict()
        group_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        data["groups"][group["id"]] = payload
    data["source_sha256"] = dossier["freeze"]["source_sha256"]
    data_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_live_report(output_root, data)
    return data


def main() -> None:
    raise SystemExit(
        "D1 live execution requires --dossier <verified frozen 600009.SH dossier>; "
        "no verified dossier is bundled in this clean worktree."
    )


if __name__ == "__main__":
    main()
