"""G1 规模预检的离线 contract-fixture 样本选择。

本模块只消费调用方注入的 spot 形状 records 与行业映射，不读取缓存，也不调用
provider 或 LLM。输出仅可作为 fixture/reference 或 simulated/development 使用。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import math
import random
from typing import Any, Iterable, Mapping

from data.lib.identity import canonical_ticker, compute_input_ticker_set_hash


_FIELD_STATUSES = {
    "complete",
    "degraded",
    "source_failed",
    "record_not_found",
    "invalid_value",
}
_EVALUABLE_FIELD_STATUSES = {"complete", "degraded"}


@dataclass(frozen=True)
class SampleSelectionConfig:
    """确定性抽样配置；所有配额均由调用方显式传入或使用默认值。"""

    industry_quota_total: int = 240
    industry_cap: int = 8
    risk_st_max: int = 20
    risk_smallcap_max: int = 30
    risk_negative_pe_max: int = 20
    risk_overheat_max: int = 20
    smallcap_threshold: float = 50e8
    minimum_full_market_size: int = 300


def select_validation_sample(
    spot_records: Iterable[Mapping[str, Any]],
    industry_mapping: Mapping[str, Any],
    *,
    run_id: str,
    profile_version: str,
    as_of: str,
    seed: int = 20260806,
    config: SampleSelectionConfig | None = None,
) -> dict[str, Any]:
    """选择可复放的 G1 验证样本，不产生任何 live 或 runtime artifact。"""
    if not run_id:
        raise ValueError("run_id is required")
    if not profile_version:
        raise ValueError("profile_version is required")
    if not as_of:
        raise ValueError("as_of is required")

    config = config or SampleSelectionConfig()
    _validate_config(config)
    normalized_records = _normalize_records(spot_records)
    mapping = _normalize_industry_mapping(industry_mapping)
    records = _deduplicate_records(normalized_records)
    rng = random.Random(seed)
    selected: dict[str, dict[str, Any]] = {}

    def add(record: dict[str, Any], stratum: str) -> None:
        item = selected.setdefault(
            record["ticker"],
            {
                "ticker": record["ticker"],
                "industry": record["industry"],
                "industry_status": record["industry_status"],
                "status": record["status"],
                "field_statuses": dict(record["field_statuses"]),
                "provenance": dict(record["provenance"]),
                "strata": [],
            },
        )
        if stratum not in item["strata"]:
            item["strata"].append(stratum)

    _attach_industries(records, mapping)
    by_industry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_industry[record["industry"]].append(record)

    total_records = len(records)
    for industry in sorted(by_industry):
        pool = by_industry[industry]
        quota = _industry_quota(pool_size=len(pool), total=total_records, config=config)
        for record in rng.sample(pool, quota):
            add(record, f"industry:{industry}")

    strata_summary = {
        "industry": _empty_stratum_summary(),
        "risk:st_h1": _empty_stratum_summary(),
        "risk:smallcap_h3": _empty_stratum_summary(),
        "risk:negative_pe_h8": _empty_stratum_summary(),
        "risk:overheat_60d": _empty_stratum_summary(),
    }
    strata_summary["industry"]["eligible"] = sum(len(pool) for pool in by_industry.values())
    strata_summary["industry"]["selected"] = sum(
        1 for record in selected.values() if any(tag.startswith("industry:") for tag in record["strata"])
    )

    _select_st_risk(records, add, rng, config.risk_st_max, strata_summary["risk:st_h1"])
    _select_numeric_risk(
        records,
        add,
        rng,
        config.risk_smallcap_max,
        "market_cap",
        "risk:smallcap_h3",
        lambda value: value < config.smallcap_threshold,
        strata_summary["risk:smallcap_h3"],
    )
    _select_numeric_risk(
        records,
        add,
        rng,
        config.risk_negative_pe_max,
        "pe_ttm",
        "risk:negative_pe_h8",
        lambda value: value < 0,
        strata_summary["risk:negative_pe_h8"],
    )
    _select_overheat_risk(
        records,
        add,
        rng,
        config.risk_overheat_max,
        strata_summary["risk:overheat_60d"],
    )

    sample = [selected[ticker] for ticker in sorted(selected)]
    sample_size = len(sample)
    full_market_qualified_size = sum(
        item["industry"] != "_unmapped" and item["industry_status"] == "complete"
        for item in sample
    )
    full_market_eligible = (
        full_market_qualified_size >= config.minimum_full_market_size
    )
    return {
        "schema_version": "g1-validation-sample/v1",
        "artifact_type": "fixture/reference",
        "mode": "simulated/development",
        "run_id": run_id,
        "profile_version": profile_version,
        "input_ticker_set_hash": compute_input_ticker_set_hash(
            [record["ticker"] for record in records]
        ),
        "as_of": as_of,
        "provenance": {
            "source": "fixture/reference",
            "attempted_sources": list(mapping["attempted_sources"]),
            "not_live_provider_evidence": True,
            "input_record_count": len(records),
            "industry_mapping_status": mapping["status"],
        },
        "sample": sample,
        "design": {
            "seed": seed,
            "sample_size": sample_size,
            "full_market_qualified_size": full_market_qualified_size,
            "full_market_eligible": full_market_eligible,
            "sample_size_semantics": (
                "full_market" if full_market_eligible else "insufficient/development"
            ),
            "minimum_full_market_size": config.minimum_full_market_size,
            "industry_mapping_status": mapping["status"],
            "real_industry_coverage": len(
                [industry for industry in by_industry if industry != "_unmapped"]
            ),
            "unmapped_count": len(by_industry.get("_unmapped", [])),
            "status_counts": dict(sorted(Counter(record["status"] for record in records).items())),
            "strata": strata_summary,
        },
    }


def _validate_config(config: SampleSelectionConfig) -> None:
    for name in (
        "industry_quota_total",
        "industry_cap",
        "risk_st_max",
        "risk_smallcap_max",
        "risk_negative_pe_max",
        "risk_overheat_max",
        "minimum_full_market_size",
    ):
        if getattr(config, name) < 0:
            raise ValueError(f"{name} must be non-negative")
    if config.minimum_full_market_size < 300:
        raise ValueError("minimum_full_market_size must be at least 300")
    if config.smallcap_threshold < 0:
        raise ValueError("smallcap_threshold must be non-negative")


def _normalize_records(spot_records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for raw in spot_records:
        ticker = canonical_ticker(str(raw.get("ticker", "")))
        status = _normalize_status(raw.get("status", "complete"))
        fields = {
            name: _normalize_field(raw, name)
            for name in ("market_cap", "pe_ttm", "chg_60d")
        }
        normalized.append(
            {
                "ticker": ticker,
                "name": str(raw.get("name") or ""),
                "status": status,
                "fields": fields,
                "field_statuses": {name: field["status"] for name, field in fields.items()},
                "provenance": _normalize_provenance(raw.get("provenance")),
                "_sort_key": _record_sort_key(raw),
            }
        )
    return normalized


def _normalize_industry_mapping(raw: Mapping[str, Any]) -> dict[str, Any]:
    status = _normalize_status(raw.get("status", "complete"))
    normalized_mapping: dict[str, str] = {}
    source_mapping = raw.get("mapping", {})
    if not isinstance(source_mapping, Mapping):
        status = "invalid_value"
        source_mapping = {}
    for raw_ticker, industry in source_mapping.items():
        if not isinstance(industry, str) or not industry.strip():
            continue
        normalized_mapping[canonical_ticker(str(raw_ticker))] = industry.strip()
    attempted_sources = raw.get("attempted_sources", [])
    if not isinstance(attempted_sources, list):
        attempted_sources = []
    return {
        "status": status,
        "mapping": normalized_mapping,
        "attempted_sources": [str(value) for value in attempted_sources],
    }


def _deduplicate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: dict[str, dict[str, Any]] = {}
    for record in sorted(records, key=lambda item: (item["ticker"], item["_sort_key"])):
        deduplicated.setdefault(record["ticker"], record)
    return [deduplicated[ticker] for ticker in sorted(deduplicated)]


def _attach_industries(records: list[dict[str, Any]], mapping: dict[str, Any]) -> None:
    for record in records:
        industry = mapping["mapping"].get(record["ticker"])
        if industry:
            record["industry"] = industry
            record["industry_status"] = "complete"
        else:
            record["industry"] = "_unmapped"
            record["industry_status"] = (
                mapping["status"] if mapping["status"] != "complete" else "record_not_found"
            )


def _industry_quota(*, pool_size: int, total: int, config: SampleSelectionConfig) -> int:
    if not pool_size or not total:
        return 0
    quota = max(1, round(pool_size / total * config.industry_quota_total))
    return min(quota, config.industry_cap, pool_size)


def _empty_stratum_summary() -> dict[str, Any]:
    return {
        "eligible": 0,
        "selected": 0,
        "unavailable": 0,
        "unavailable_reasons": {},
    }


def _select_st_risk(
    records: list[dict[str, Any]],
    add,
    rng: random.Random,
    cap: int,
    summary: dict[str, Any],
) -> None:
    pool = [record for record in records if "ST" in record["name"].upper()]
    summary["eligible"] = len(pool)
    picked = rng.sample(pool, min(cap, len(pool)))
    for record in picked:
        add(record, "risk:st_h1")
    summary["selected"] = len(picked)


def _select_numeric_risk(
    records: list[dict[str, Any]],
    add,
    rng: random.Random,
    cap: int,
    field: str,
    stratum: str,
    predicate,
    summary: dict[str, Any],
) -> None:
    pool = []
    reasons: Counter[str] = Counter()
    for record in records:
        value, status = record["fields"][field]["value"], record["fields"][field]["status"]
        if status not in _EVALUABLE_FIELD_STATUSES:
            reasons[status] += 1
            continue
        if predicate(value):
            pool.append(record)
    summary["eligible"] = len(pool)
    summary["unavailable"] = sum(reasons.values())
    summary["unavailable_reasons"] = dict(sorted(reasons.items()))
    picked = rng.sample(pool, min(cap, len(pool)))
    for record in picked:
        add(record, stratum)
    summary["selected"] = len(picked)


def _select_overheat_risk(
    records: list[dict[str, Any]],
    add,
    rng: random.Random,
    cap: int,
    summary: dict[str, Any],
) -> None:
    eligible = []
    reasons: Counter[str] = Counter()
    for record in records:
        value, status = record["fields"]["chg_60d"]["value"], record["fields"]["chg_60d"]["status"]
        if status not in _EVALUABLE_FIELD_STATUSES:
            reasons[status] += 1
            continue
        eligible.append(record)
    eligible.sort(key=lambda record: (-record["fields"]["chg_60d"]["value"], record["ticker"]))
    pool = eligible[: max(1, len(eligible) // 10)] if eligible else []
    summary["eligible"] = len(pool)
    summary["unavailable"] = sum(reasons.values())
    summary["unavailable_reasons"] = dict(sorted(reasons.items()))
    picked = rng.sample(pool, min(cap, len(pool)))
    for record in picked:
        add(record, "risk:overheat_60d")
    summary["selected"] = len(picked)


def _normalize_field(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    status = _normalize_status(raw.get("field_statuses", {}).get(name, raw.get("status", "complete")))
    value = raw.get(name)
    if status in _EVALUABLE_FIELD_STATUSES:
        value = _coerce_number(value)
        if value is None:
            status = "invalid_value"
    return {"value": value, "status": status}


def _normalize_status(value: Any) -> str:
    return str(value) if str(value) in _FIELD_STATUSES else "invalid_value"


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _normalize_provenance(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, Mapping) else {}


def _record_sort_key(record: Mapping[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
