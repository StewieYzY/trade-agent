"""G1 Stage A/B/C staged screening runtime."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from data.lib.batch_fetcher import BatchFetcher, FetchTelemetry
from data.lib.identity import (
    canonical_code,
    canonical_ticker,
    compute_input_ticker_set_hash,
    generate_run_id,
)
from data.lib.industry_mapper import compute_industry_median_pe
from .anti_trap import compute_anti_trap
from .factor_scores import compute_factor_scores
from .hard_gates import check_hard_gates
from .heat_filter import check_heat_filter

G1_STAGE_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "A": ("basic",),
    "B": ("financials", "risk"),
    "C": ("valuation", "kline"),
}
_UNAVAILABLE = {
    "conflict",
    "degraded",
    "partial",
    "permission_denied",
    "rate_limited",
    "not_supported_for_market",
    "record_not_found",
    "source_failed",
    "invalid_value",
    "not_evaluated",
    "stale",
}
_AVAILABLE_DIMENSION_STATUSES = {"available", "complete"}
_CANONICAL_STAGE_FIELDS = {
    "A": {"name", "price", "last_price", "pe", "pb", "market_cap", "industry"},
    "B": {
        "years",
        "net_profit",
        "TOTAL_ASSETS",
        "TOTAL_CURRENT_LIAB",
        "TOTAL_NONCURRENT_LIAB",
        "NETCASH_OPERATE",
        "pledge_ratio",
        "pledge_status",
        "audit_opinion",
    },
    "C": {
        "pe_ttm",
        "pb",
        "pe_percentile_5y",
        "pe_history",
        "close",
        "turnover_rate",
    },
}


@dataclass
class StageEvidence:
    stage: str
    run_id: str
    input_tickers: list[str]
    output_tickers: list[str]
    requested_dimensions: tuple[str, ...]
    canonical_input_tickers: list[str] = field(default_factory=list)
    canonical_output_tickers: list[str] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)
    provider_calls: list[dict] = field(default_factory=list)
    cache_hits: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    dimension_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    passed_count: int = 0
    failed_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class StagedScreeningResult:
    run_id: str
    input_ticker_set_hash: str
    stages: dict[str, StageEvidence]
    ticker_evidence: dict[str, dict[str, Any]]
    candidates: list[dict[str, Any]] = field(default_factory=list)
    evidence_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "run_id": self.run_id,
                "input_ticker_set_hash": self.input_ticker_set_hash,
                "stages": {
                    name: evidence.to_dict()
                    for name, evidence in self.stages.items()
                },
                "ticker_evidence": self.ticker_evidence,
                "candidates": self.candidates,
                "evidence_path": self.evidence_path,
            }
        )


def run_staged_screening(
    tickers: list[str],
    *,
    fetcher: BatchFetcher | Any | None = None,
    run_id: str | None = None,
    canonical_fields: Mapping[tuple[str, str], Any] | Any | None = None,
    exclude_cyclicals: bool = False,
) -> StagedScreeningResult:
    """Run G1 through explicit stage-specific fetch boundaries.

    A fetcher must be supplied by the caller. This prevents the runtime from
    silently creating a live BatchFetcher and writing cache as an implicit
    side effect.
    """
    if fetcher is None:
        raise ValueError("fetcher must be explicitly supplied")
    raw_tickers, canonical_by_raw = _validate_tickers(tickers)
    canonical_tickers = [canonical_by_raw[ticker] for ticker in raw_tickers]
    run_id = run_id or generate_run_id()
    input_hash = compute_input_ticker_set_hash(raw_tickers)
    canonical_map = _coerce_canonical_fields(
        canonical_fields,
        raw_tickers=raw_tickers,
        canonical_by_raw=canonical_by_raw,
    )
    ticker_evidence = {
        canonical_by_raw[ticker]: {
            "raw_ticker": ticker,
            "canonical_fields": canonical_map.get(canonical_by_raw[ticker], {}),
        }
        for ticker in raw_tickers
    }
    all_data: dict[str, dict[str, Any]] = {ticker: {} for ticker in raw_tickers}
    stages: dict[str, StageEvidence] = {}

    stage_a, data_a = _run_stage(
        "A",
        raw_tickers,
        all_data,
        ticker_evidence,
        canonical_by_raw,
        canonical_map,
        fetcher,
        run_id,
        _stage_a_pass,
        exclude_cyclicals=exclude_cyclicals,
    )
    all_data.update(data_a)
    stages["A"] = stage_a

    stage_b, data_b = _run_stage(
        "B",
        stage_a.output_tickers,
        all_data,
        ticker_evidence,
        canonical_by_raw,
        canonical_map,
        fetcher,
        run_id,
        lambda data: _stage_b_pass(
            data,
            exclude_cyclicals=exclude_cyclicals,
        ),
        exclude_cyclicals=exclude_cyclicals,
    )
    all_data.update(data_b)
    stages["B"] = stage_b

    stage_c, data_c = _run_stage(
        "C",
        stage_b.output_tickers,
        all_data,
        ticker_evidence,
        canonical_by_raw,
        canonical_map,
        fetcher,
        run_id,
        _stage_c_complete,
        exclude_cyclicals=exclude_cyclicals,
    )
    all_data.update(data_c)
    stages["C"] = stage_c

    candidates, heat_failures = _score_final_candidates(
        all_data,
        stage_c.output_tickers,
        canonical_by_raw=canonical_by_raw,
    )
    for failure in heat_failures:
        _append_failure(stage_c.failures, failure)
    stage_c.output_tickers = [
        _raw_ticker_for_candidate(candidate, canonical_by_raw)
        for candidate in candidates
    ]
    stage_c.canonical_output_tickers = [
        candidate["ticker"] for candidate in candidates
    ]
    stage_c.passed_count = len(stage_c.output_tickers)
    stage_c.failed_count = len(stage_c.input_tickers) - stage_c.passed_count
    return StagedScreeningResult(
        run_id=run_id,
        input_ticker_set_hash=input_hash,
        stages=stages,
        ticker_evidence=ticker_evidence,
        candidates=candidates,
    )


def _run_stage(
    stage: str,
    input_tickers: list[str],
    all_data: dict[str, dict[str, Any]],
    ticker_evidence: dict[str, dict[str, Any]],
    canonical_by_raw: Mapping[str, str],
    canonical_fields: Mapping[str, Mapping[str, dict[str, Any]]],
    fetcher: Any,
    run_id: str,
    passes: Any,
    *,
    exclude_cyclicals: bool,
) -> tuple[StageEvidence, dict[str, dict[str, Any]]]:
    del exclude_cyclicals
    dimensions = G1_STAGE_DIMENSIONS[stage]
    telemetry = FetchTelemetry()
    fetched = fetcher.fetch_all(
        input_tickers,
        dimensions=dimensions,
        telemetry=telemetry,
    )
    stage_data = {
        ticker: dict(all_data.get(ticker, {}))
        for ticker in input_tickers
    }
    evidence = StageEvidence(
        stage=stage,
        run_id=run_id,
        input_tickers=list(input_tickers),
        output_tickers=[],
        requested_dimensions=dimensions,
        canonical_input_tickers=[
            canonical_by_raw[ticker] for ticker in input_tickers
        ],
        requests=list(telemetry.requests),
        provider_calls=list(telemetry.provider_calls),
        cache_hits=list(telemetry.cache_hits),
        failures=list(telemetry.failures),
    )
    for ticker in input_tickers:
        current = stage_data[ticker]
        current.update(fetched.get(ticker, {}))
        evidence.dimension_results[ticker] = {
            dimension: current.get(dimension)
            for dimension in dimensions
        }
        failure = _first_failure(
            current,
            dimensions,
            canonical_fields.get(canonical_by_raw[ticker], {}),
            stage,
        )
        if failure is not None:
            _append_failure(
                evidence.failures,
                {"ticker": ticker, **failure},
            )
            continue
        try:
            passes_stage = bool(passes(current))
        except (TypeError, ValueError, KeyError, OverflowError):
            passes_stage = False
        if passes_stage:
            evidence.output_tickers.append(ticker)
        else:
            _append_failure(
                evidence.failures,
                {
                    "ticker": ticker,
                    "dimension": None,
                    "status": "not_evaluated",
                    "reason": f"stage_{stage}_filter_failed",
                },
            )
    evidence.canonical_output_tickers = [
        canonical_by_raw[ticker] for ticker in evidence.output_tickers
    ]
    evidence.passed_count = len(evidence.output_tickers)
    evidence.failed_count = len(input_tickers) - evidence.passed_count
    return evidence, stage_data


def _stage_a_pass(data: dict[str, Any]) -> bool:
    basic = data.get("basic")
    if not isinstance(basic, dict):
        return False
    if not _required_basic_fields_available(basic):
        return False
    if "ST" in str(basic["name"]).upper():
        return False
    if basic["market_cap"] < 5e9:
        return False
    if basic["industry"] in {"银行", "证券", "保险", "多元金融"}:
        return False
    return basic["pe"] >= 0


def _required_basic_fields_available(basic: Mapping[str, Any]) -> bool:
    required = ("name", "price", "pe", "pb", "market_cap", "industry")
    if any(key not in basic for key in required):
        return False
    if any(not _finite_number(basic[key]) for key in ("price", "pe", "pb", "market_cap")):
        return False
    if not isinstance(basic["name"], str) or not basic["name"].strip():
        return False
    if not isinstance(basic["industry"], str) or not basic["industry"].strip():
        return False
    return basic.get("industry_status", "available") not in _UNAVAILABLE


def _stage_b_pass(data: dict[str, Any], *, exclude_cyclicals: bool) -> bool:
    financials = data.get("financials")
    risk = data.get("risk")
    if not _required_financial_fields_available(financials):
        return False
    if not _required_risk_fields_available(risk):
        return False
    result = check_hard_gates(data, exclude_cyclicals=exclude_cyclicals)
    return bool(result["pass"])


def _required_financial_fields_available(financials: Any) -> bool:
    if not isinstance(financials, Mapping):
        return False
    if (
        financials.get("status") is not None
        and financials.get("status") not in _AVAILABLE_DIMENSION_STATUSES
    ):
        return False
    if not isinstance(financials.get("years"), list) or len(financials["years"]) < 3:
        return False
    income = financials.get("income")
    balance = financials.get("balance_sheet")
    cash_flow = financials.get("cash_flow")
    if not isinstance(income, Mapping) or not isinstance(balance, Mapping):
        return False
    if not isinstance(cash_flow, Mapping):
        return False
    required_lists = (
        income.get("net_profit"),
        balance.get("TOTAL_ASSETS"),
        balance.get("TOTAL_CURRENT_LIAB"),
        balance.get("TOTAL_NONCURRENT_LIAB"),
        cash_flow.get("NETCASH_OPERATE"),
    )
    return all(
        _complete_numeric_series(value, minimum=len(financials["years"]))
        and len(value) == len(financials["years"])
        for value in required_lists
    )


def _required_risk_fields_available(risk: Any) -> bool:
    if not isinstance(risk, Mapping):
        return False
    if "pledge_status" not in risk or "audit_opinion" not in risk:
        return False
    if (
        risk.get("status") is not None
        and risk.get("status") not in _AVAILABLE_DIMENSION_STATUSES
    ):
        return False
    pledge_status = risk.get("pledge_status")
    if pledge_status not in {"record_found", "record_not_found"}:
        return False
    pledge_ratio = risk.get("pledge_ratio")
    if pledge_status == "record_found" and not _finite_number(pledge_ratio):
        return False
    if pledge_status == "record_not_found" and pledge_ratio is not None:
        return False
    return risk.get("audit_opinion") is None or isinstance(risk.get("audit_opinion"), str)


def _stage_c_complete(data: dict[str, Any]) -> bool:
    if not _dimensions_available(data, G1_STAGE_DIMENSIONS["C"]):
        return False
    valuation = data["valuation"]
    kline = data["kline"]
    if (
        not _complete_numeric_series(valuation.get("pe_history"), minimum=1)
        or not _finite_number(valuation.get("pe_percentile_5y"))
    ):
        return False
    for optional_value in ("pe_ttm", "pb", "pb_percentile_5y"):
        if optional_value in valuation and valuation[optional_value] is not None:
            if not _finite_number(valuation[optional_value]):
                return False
    return (
        _complete_numeric_series(kline.get("close"), minimum=60)
        and _complete_numeric_series(kline.get("turnover_rate"), minimum=60)
    )


def _complete_numeric_series(value: Any, *, minimum: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= minimum
        and all(_finite_number(item) for item in value[-minimum:])
    )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _score_final_candidates(
    ticker_data: dict[str, dict[str, Any]],
    tickers: list[str],
    *,
    canonical_by_raw: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Preserve the legacy score -> top 300 -> heat-filter order."""
    eligible_data = {
        ticker: data
        for ticker, data in ticker_data.items()
        if _required_basic_fields_available(data.get("basic", {}))
    }
    try:
        industry_pe_map = compute_industry_median_pe(eligible_data)
    except (TypeError, ValueError, KeyError, OverflowError):
        industry_pe_map = {}
    scored: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for ticker in tickers:
        data = ticker_data[ticker]
        try:
            factor_scores = compute_factor_scores(data, industry_pe_map)
            anti_trap = compute_anti_trap(data)
            adjusted = factor_scores["composite"] * (anti_trap["score"] / 100.0)
            if not _finite_number(adjusted):
                raise ValueError("non-finite adjusted composite")
            scored.append(
                {
                    "ticker": (
                        canonical_by_raw[ticker]
                        if canonical_by_raw is not None
                        else ticker
                    ),
                    "_raw_ticker": ticker,
                    "name": data.get("basic", {}).get("name", ""),
                    "industry": data.get("basic", {}).get("industry", ""),
                    "factor_scores": factor_scores,
                    "anti_trap": anti_trap,
                    "adjusted_composite": adjusted,
                    "f_score": factor_scores.get("f_score"),
                    "graham_number": data.get("valuation", {}).get("graham_number"),
                    "pe_ttm": data.get("valuation", {}).get("pe_ttm"),
                    "pb": data.get("valuation", {}).get("pb"),
                    "pledge_ratio": data.get("risk", {}).get("pledge_ratio"),
                }
            )
        except (TypeError, ValueError, KeyError, OverflowError):
            failures.append(
                {
                    "ticker": ticker,
                    "dimension": "screening",
                    "status": "invalid_value",
                    "reason": "scoring_failed",
                }
            )
    scored.sort(key=lambda item: item["adjusted_composite"], reverse=True)
    top_300 = scored[:300]
    candidates: list[dict[str, Any]] = []
    heat_failures: list[dict[str, str]] = []
    for candidate in top_300:
        raw_ticker = candidate["_raw_ticker"]
        heat = check_heat_filter(ticker_data[raw_ticker])
        if not heat["pass"]:
            heat_failures.append(
                {
                    "ticker": raw_ticker,
                    "dimension": "kline",
                    "status": "not_evaluated",
                    "reason": "heat_filter_failed",
                    "failed_filters": list(heat.get("failed_filters", [])),
                }
            )
            continue
        candidate = dict(candidate)
        candidate.pop("_raw_ticker", None)
        candidate["heat_filter"] = heat
        candidates.append(candidate)
    return candidates, failures + heat_failures


def _dimensions_available(data: dict[str, Any], dimensions: tuple[str, ...]) -> bool:
    return all(
        isinstance(data.get(dimension), dict)
        and not data[dimension].get("__error__")
        and data[dimension].get("status") not in _UNAVAILABLE
        for dimension in dimensions
    )


def _first_failure(
    data: dict[str, Any],
    dimensions: tuple[str, ...],
    canonical_fields: Mapping[str, dict[str, Any]],
    stage: str,
) -> dict[str, str] | None:
    for dimension in dimensions:
        value = data.get(dimension)
        if not isinstance(value, dict):
            return {
                "dimension": dimension,
                "status": "not_evaluated",
                "reason": "dimension_missing",
            }
        if value.get("__error__"):
            return {
                "dimension": dimension,
                "status": "source_failed",
                "reason": str(value.get("error") or f"fetch failed: {dimension}"),
            }
        status = value.get("status")
        if status is not None and status not in _AVAILABLE_DIMENSION_STATUSES:
            return {
                "dimension": dimension,
                "status": str(status),
                "reason": str(value.get("reason") or f"dimension status: {status}"),
            }
    for field_name, field_value in canonical_fields.items():
        if field_name not in _CANONICAL_STAGE_FIELDS[stage]:
            continue
        if (
            field_value.get("status") in _UNAVAILABLE
            or field_value.get("available") is False
            or field_value.get("value") is None
        ):
            return {
                "dimension": field_name,
                "status": str(field_value.get("status") or "not_evaluated"),
                "reason": str(field_value.get("reason") or "canonical field unavailable"),
            }
    if stage == "A" and not _required_basic_fields_available(data.get("basic", {})):
        return {
            "dimension": "basic",
            "status": "not_evaluated",
            "reason": "required_basic_field_missing",
        }
    if stage == "B" and (
        not _required_financial_fields_available(data.get("financials"))
        or not _required_risk_fields_available(data.get("risk"))
    ):
        return {
            "dimension": "financials/risk",
            "status": "not_evaluated",
            "reason": "required_stage_field_missing",
        }
    if stage == "C" and not _stage_c_complete(data):
        return {
            "dimension": "valuation/kline",
            "status": "not_evaluated",
            "reason": "required_stage_field_missing",
        }
    return None


def _append_failure(failures: list[dict], failure: dict) -> None:
    key = (
        failure.get("ticker"),
        failure.get("dimension"),
        failure.get("status"),
        failure.get("reason"),
    )
    if not any(
        (
            existing.get("ticker"),
            existing.get("dimension"),
            existing.get("status"),
            existing.get("reason"),
        )
        == key
        for existing in failures
    ):
        failures.append(failure)


def _coerce_canonical_fields(
    source: Any,
    *,
    raw_tickers: list[str],
    canonical_by_raw: Mapping[str, str],
) -> dict[str, dict[str, dict[str, Any]]]:
    if source is None:
        return {}
    result: dict[str, dict[str, dict[str, Any]]] = {}
    if hasattr(source, "fields_for"):
        for raw_ticker in raw_tickers:
            canonical = canonical_by_raw[raw_ticker]
            fields = source.fields_for(canonical)
            result[canonical] = {
                str(field_name): _serialize_canonical_field(field)
                for field_name, field in fields.items()
            }
        return result
    if not isinstance(source, Mapping):
        raise TypeError("canonical_fields must be a field mapping or consumer")
    for key, field in source.items():
        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError("canonical_fields keys must be (ticker, field)")
        raw_ticker, field_name = key
        canonical = canonical_ticker(raw_ticker)
        result.setdefault(canonical, {})[str(field_name)] = _serialize_canonical_field(field)
    return result


def _serialize_canonical_field(field: Any) -> dict[str, Any]:
    value = getattr(field, "value", field.get("value") if isinstance(field, Mapping) else None)
    status = getattr(field, "status", field.get("status") if isinstance(field, Mapping) else None)
    eligibility = getattr(
        field,
        "eligibility",
        field.get("eligibility") if isinstance(field, Mapping) else None,
    )
    reason = getattr(field, "reason", field.get("reason") if isinstance(field, Mapping) else None)
    provenance = getattr(
        field,
        "provenance",
        field.get("provenance", {}) if isinstance(field, Mapping) else {},
    )
    as_of = getattr(field, "as_of", field.get("as_of") if isinstance(field, Mapping) else None)
    freshness = getattr(
        field,
        "freshness",
        field.get("freshness") if isinstance(field, Mapping) else None,
    )
    available = getattr(field, "available", None)
    if available is None:
        available = (
            value is not None
            and status == "available"
            and eligibility == "production_eligible"
            and freshness == "fresh"
        )
    return _json_safe(
        {
            "value": value,
            "status": status or "not_evaluated",
            "eligibility": eligibility,
            "reason": reason,
            "provenance": provenance,
            "as_of": as_of,
            "freshness": freshness,
            "available": bool(available),
        }
    )


def _validate_tickers(tickers: list[str]) -> tuple[list[str], dict[str, str]]:
    if not isinstance(tickers, list) or not tickers:
        raise ValueError("tickers must be a non-empty list")
    raw_tickers: list[str] = []
    canonical_by_raw: dict[str, str] = {}
    seen: set[str] = set()
    for ticker in tickers:
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("tickers must contain non-empty strings")
        raw = ticker.strip()
        canonical = canonical_ticker(raw)
        provider_ticker = canonical_code(raw)
        if canonical in seen:
            continue
        seen.add(canonical)
        raw_tickers.append(provider_ticker)
        canonical_by_raw[provider_ticker] = canonical
    if not raw_tickers:
        raise ValueError("tickers must contain at least one valid ticker")
    return raw_tickers, canonical_by_raw


def _raw_ticker_for_candidate(
    candidate: Mapping[str, Any],
    canonical_by_raw: Mapping[str, str],
) -> str:
    canonical = candidate["ticker"]
    return next(raw for raw, value in canonical_by_raw.items() if value == canonical)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def serialize_evidence(result: StagedScreeningResult) -> str:
    """Return JSON evidence without writing any file."""
    return json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)
