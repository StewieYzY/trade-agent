"""只读 A 股 provider qualification runner.

该模块只生成 run-scoped qualification evidence，不读取或写入生产 cache、
ranking、canonical snapshot、debate、watchlist 或 diagnostic。

真实 provider 通过显式 adapter 注入：

    def get_provider_adapters() -> list[ProviderAdapter]:
        return [ProviderAdapter(...)]

CLI 的 ``--adapter-module`` 会加载该函数；没有 SDK/凭据时，默认输出
``not_evaluated`` evidence，不能把缺少 runtime probe 误判为 provider 可用。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

PROBE_PLAN_VERSION = "a-share-provider-qualification-v1"
RAW_MAX_BYTES = 200_000

STATUSES = {
    "available",
    "partial",
    "record_not_found",
    "source_failed",
    "permission_denied",
    "rate_limited",
    "not_supported_for_market",
    "invalid_value",
    "not_evaluated",
}

DEFAULT_TICKERS = (
    ("600519.SH", "SH", "consumer"),
    ("600009.SH", "SH", "transport"),
    ("000858.SZ", "SZ", "consumer"),
    ("300750.SZ", "SZ", "growth"),
    ("601318.SH", "SH", "financial"),
)

METHOD_FIELDS: dict[str, tuple[str, ...]] = {
    "static_info": ("code", "name", "market"),
    "quote": ("last_price", "previous_close", "volume", "turnover_rate"),
    "calc_indexes": ("pe_ttm", "pb", "dividend_yield"),
    "historical_kline": ("dates", "close", "volume", "turnover_rate"),
    "income_statement": ("report_period", "revenue", "net_profit"),
    "balance_sheet": ("report_period", "total_assets", "total_liabilities", "cash"),
    "cash_flow": ("report_period", "operating_cash_flow", "capital_expenditure"),
    "historical_valuation": ("as_of", "pe_ttm", "pb"),
    "industry_valuation": ("as_of", "industry", "pe_median"),
    "consensus": ("report_period", "eps_consensus", "revenue_consensus"),
}

_NUMERIC_FIELDS = {
    "last_price",
    "previous_close",
    "volume",
    "turnover_rate",
    "pe_ttm",
    "pb",
    "dividend_yield",
    "revenue",
    "net_profit",
    "total_assets",
    "total_liabilities",
    "cash",
    "operating_cash_flow",
    "capital_expenditure",
    "pe_median",
    "eps_consensus",
    "revenue_consensus",
}
_TIME_FIELDS = {"dates", "report_period", "as_of"}


@dataclass(frozen=True)
class ProbeCase:
    ticker: str
    market: str
    security_type: str
    method: str
    fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "market": self.market,
            "security_type": self.security_type,
            "method": self.method,
            "fields": list(self.fields),
        }


@dataclass(frozen=True)
class ProviderAdapter:
    provider_family: str
    provider: str
    invoke: Callable[[ProbeCase], Any] | None = None
    available: bool = True
    documentation_status: str = "unknown"
    availability_reason: str | None = None


def _sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _code_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _canonical_ticker(raw: str) -> str:
    from data.lib.identity import canonical_ticker

    return canonical_ticker(raw)


def _safe_run_id(run_id: str | None) -> str:
    value = run_id or str(uuid.uuid4())
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


def _redact_error(message: str) -> str:
    text = str(message)
    text = re.sub(r"(?i)(https?://)[^/\s@]+@", r"\1<redacted>@", text)
    text = re.sub(
        r"(?i)\bauthorization\s*:\s*(?:basic|bearer|token)\s+\S+",
        "Authorization: <redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(api[_-]?key|secret|token)\s*[=:]\s*\S+",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+\b", "sk-<redacted>", text)
    return text[:2_000]


def _status_from_error(exc: BaseException) -> str:
    code = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    message = str(exc).lower()
    if isinstance(exc, (ImportError, ModuleNotFoundError, NotImplementedError)):
        return "not_evaluated"
    if isinstance(exc, PermissionError) or code in {401, 403}:
        return "permission_denied"
    if code == 429 or any(term in message for term in ("rate limit", "too many requests", "限流")):
        return "rate_limited"
    if any(term in message for term in ("not supported", "unsupported", "market not", "不支持")):
        return "not_supported_for_market"
    if any(term in message for term in ("not found", "no record", "查无", "不存在")):
        return "record_not_found"
    if "empty" in message:
        return "source_failed"
    if isinstance(exc, KeyError):
        return "source_failed"
    if isinstance(exc, (ValueError, TypeError)):
        return "invalid_value"
    return "source_failed"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _json_safe(to_dict())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "to_dict"):
        try:
            return _json_safe(value.to_dict(orient="records"))
        except (TypeError, ValueError):
            pass
    return _redact_error(repr(value))


def _bounded_raw(value: Any) -> tuple[Any, str, bool]:
    safe = _json_safe(value)
    encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True, default=str)
    response_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    raw_bytes = encoded.encode("utf-8")
    if len(raw_bytes) <= RAW_MAX_BYTES:
        return safe, response_hash, False
    truncated = raw_bytes[:RAW_MAX_BYTES].decode("utf-8", errors="ignore")
    return {
        "__truncated__": True,
        "prefix": truncated,
        "original_bytes": len(raw_bytes),
    }, response_hash, True


def _unwrap_response(response: Any) -> tuple[Any, Mapping[str, Any]]:
    if isinstance(response, Mapping) and "data" in response:
        metadata = response.get("_meta") or response.get("meta") or {}
        return response["data"], metadata if isinstance(metadata, Mapping) else {}
    return response, {}


def _field_value(payload: Any, field: str) -> tuple[Any, Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        value = payload.get(field)
        metadata = payload.get("_fields", {})
        field_meta = metadata.get(field, {}) if isinstance(metadata, Mapping) else {}
        return value, field_meta if isinstance(field_meta, Mapping) else {}
    return None, {}


def _normalize_field(
    field: str,
    value: Any,
    metadata: Mapping[str, Any],
    *,
    method: str,
) -> tuple[str, Any, str | None]:
    if value is None or value == "" or value == []:
        return "record_not_found", None, "field is absent or empty"
    if field in _NUMERIC_FIELDS:
        if isinstance(value, bool):
            return "invalid_value", None, "boolean is not a numeric field value"
        if isinstance(value, str):
            try:
                value = float(value.replace(",", "").strip())
            except ValueError:
                return "invalid_value", None, "numeric field is not parseable"
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return "invalid_value", None, "numeric field is not finite"
        if not metadata.get("unit") and not metadata.get("currency"):
            return "not_evaluated", value, "numeric field has no unit/currency metadata"
        return "available", value, None
    if field in _TIME_FIELDS and not isinstance(value, (str, list, tuple)):
        return "invalid_value", None, f"{method}.{field} has invalid time shape"
    if isinstance(value, Mapping) and not value:
        return "record_not_found", None, "field mapping is empty"
    return "available", _json_safe(value), None


def build_probe_plan(
    tickers: Iterable[tuple[str, str, str]] = DEFAULT_TICKERS,
) -> list[ProbeCase]:
    cases: list[ProbeCase] = []
    for raw_ticker, market, security_type in tickers:
        ticker = _canonical_ticker(raw_ticker)
        for method, fields in METHOD_FIELDS.items():
            cases.append(
                ProbeCase(
                    ticker=ticker,
                    market=market,
                    security_type=security_type,
                    method=method,
                    fields=fields,
                )
            )
    return cases


def unavailable_adapters() -> list[ProviderAdapter]:
    """返回不触网的默认 adapter，便于生成 blocked/not_evaluated evidence。"""
    return [
        ProviderAdapter(
            "baseline", "akshare-eastmoney", invoke=None, available=False,
            documentation_status="documented", availability_reason="runtime adapter not configured",
        ),
        ProviderAdapter(
            "baseline", "akshare-ths", invoke=None, available=False,
            documentation_status="documented", availability_reason="runtime adapter not configured",
        ),
        ProviderAdapter(
            "baseline", "akshare-sina", invoke=None, available=False,
            documentation_status="documented", availability_reason="runtime adapter not configured",
        ),
        ProviderAdapter(
            "candidate", "longport", invoke=None, available=False,
            documentation_status="candidate", availability_reason="SDK/credentials not configured",
        ),
        ProviderAdapter(
            "candidate", "longbridge", invoke=None, available=False,
            documentation_status="candidate", availability_reason="SDK/credentials not configured",
        ),
    ]


def _field_evidence(
    adapter: ProviderAdapter,
    case: ProbeCase,
    field: str,
    *,
    status: str,
    value: Any = None,
    metadata: Mapping[str, Any] | None = None,
    reason: str | None = None,
    response_hash: str | None = None,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"unknown qualification status: {status}")
    meta = dict(metadata or {})
    return {
        "provider_family": adapter.provider_family,
        "provider": adapter.provider,
        "method": case.method,
        "market": case.market,
        "ticker": case.ticker,
        "security_type": case.security_type,
        "field": field,
        "raw_field": meta.pop("raw_field", field),
        "value": _json_safe(value),
        "unit": meta.pop("unit", None),
        "currency": meta.pop("currency", None),
        "as_of": meta.pop("as_of", None),
        "report_period": meta.pop("report_period", None),
        "status": status,
        "reason": reason,
        "documentation_status": adapter.documentation_status,
        "response_hash": response_hash,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "provider_family": adapter.provider_family,
            "provider": adapter.provider,
            "method": case.method,
            "run_scoped": True,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            **meta,
        },
    }


def _probe_case(adapter: ProviderAdapter, case: ProbeCase) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not adapter.available or adapter.invoke is None:
        reason = adapter.availability_reason or "provider adapter unavailable"
        return (
            [
                _field_evidence(adapter, case, field, status="not_evaluated", reason=reason)
                for field in case.fields
            ],
            {"status": "not_evaluated", "reason": reason},
        )

    try:
        response = adapter.invoke(case)
    except BaseException as exc:  # provider boundary must preserve all adapter failures
        status = _status_from_error(exc)
        reason = _redact_error(f"{type(exc).__name__}: {exc}")
        return (
            [
                _field_evidence(adapter, case, field, status=status, reason=reason)
                for field in case.fields
            ],
            {"status": status, "reason": reason},
        )

    raw, response_hash, truncated = _bounded_raw(response)
    payload, response_meta = _unwrap_response(response)
    if response is None or payload is None or payload == {} or payload == []:
        return (
            [
                _field_evidence(
                    adapter,
                    case,
                    field,
                    status="record_not_found",
                    reason="provider returned an empty response",
                    response_hash=response_hash,
                )
                for field in case.fields
            ],
            {"status": "record_not_found", "response_hash": response_hash, "raw_truncated": truncated},
        )

    evidence: list[dict[str, Any]] = []
    statuses: list[str] = []
    for field in case.fields:
        value, field_meta = _field_value(payload, field)
        merged_meta = {**response_meta, **field_meta}
        status, normalized, reason = _normalize_field(
            field, value, merged_meta, method=case.method
        )
        statuses.append(status)
        evidence.append(
            _field_evidence(
                adapter,
                case,
                field,
                status=status,
                value=normalized,
                metadata=merged_meta,
                reason=reason,
                response_hash=response_hash,
            )
        )
    method_status = "available" if all(s == "available" for s in statuses) else "partial"
    if all(s == "record_not_found" for s in statuses):
        method_status = "record_not_found"
    return evidence, {
        "status": method_status,
        "response_hash": response_hash,
        "raw": raw,
        "raw_truncated": truncated,
    }


class QualificationRunner:
    def __init__(
        self,
        *,
        adapters: Iterable[ProviderAdapter] | None = None,
        cases: Iterable[ProbeCase] | None = None,
        plan_version: str = PROBE_PLAN_VERSION,
    ):
        self.adapters = list(adapters or unavailable_adapters())
        self.cases = list(cases or build_probe_plan())
        if not self.cases:
            raise ValueError("qualification probe plan must not be empty")
        self.plan_version = plan_version

    def run(self, *, output_root: str | Path, run_id: str | None = None) -> dict[str, Any]:
        safe_id = _safe_run_id(run_id)
        root = Path(output_root).resolve()
        run_dir = (root / safe_id).resolve()
        try:
            run_dir.relative_to(root)
        except ValueError as exc:
            raise ValueError("run_id escapes output_root") from exc
        run_dir.mkdir(parents=True, exist_ok=False)

        plan = [case.to_dict() for case in self.cases]
        plan_hash = _sha256({"version": self.plan_version, "cases": plan})
        evidence: list[dict[str, Any]] = []
        method_results: list[dict[str, Any]] = []
        raw_by_hash: dict[str, Any] = {}
        stop_reasons: list[str] = []

        for adapter in self.adapters:
            for case in self.cases:
                case_evidence, method_result = _probe_case(adapter, case)
                evidence.extend(case_evidence)
                method_results.append(
                    {
                        **method_result,
                        "provider_family": adapter.provider_family,
                        "provider": adapter.provider,
                        "method": case.method,
                        "ticker": case.ticker,
                    }
                )
                if method_result.get("status") == "rate_limited":
                    stop_reasons.append(
                        f"rate_limited:{adapter.provider}:{case.method}:{case.ticker}"
                    )
                    break
                if method_result.get("response_hash") and "raw" in method_result:
                    raw_by_hash[method_result["response_hash"]] = {
                        "provider": adapter.provider,
                        "method": case.method,
                        "ticker": case.ticker,
                        "raw": method_result["raw"],
                        "raw_truncated": method_result.get("raw_truncated", False),
                    }

        comparison = _build_comparison(evidence)
        status_counts: dict[str, int] = {}
        for item in evidence:
            status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
        stop_reason = stop_reasons[0] if stop_reasons else None
        if all(item["status"] == "not_evaluated" for item in evidence):
            stop_reason = "no_runtime_provider_adapter_available"

        manifest = {
            "schema_version": "a-share-provider-qualification-v1",
            "run_id": safe_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "code_version": _code_version(),
            "plan_version": self.plan_version,
            "plan_hash": plan_hash,
            "ticker_set_hash": _sha256(sorted({case.ticker for case in self.cases})),
            "provider_count": len(self.adapters),
            "provider_methods": [
                {
                    "provider_family": adapter.provider_family,
                    "provider": adapter.provider,
                    "documentation_status": adapter.documentation_status,
                    "available": adapter.available and adapter.invoke is not None,
                }
                for adapter in self.adapters
            ],
            "status_counts": status_counts,
            "stop_reason": stop_reason,
            "stop_reasons": stop_reasons,
            "artifacts": {
                "plan": "plan.json",
                "evidence": "evidence.json",
                "raw": "raw.json",
                "comparison": "comparison.json",
                "method_results": "method-results.json",
            },
        }
        _write_json(run_dir / "plan.json", {"version": self.plan_version, "plan_hash": plan_hash, "cases": plan})
        _write_json(run_dir / "evidence.json", {"run_id": safe_id, "evidence": evidence})
        _write_json(run_dir / "raw.json", {"run_id": safe_id, "responses": list(raw_by_hash.values())})
        _write_json(run_dir / "comparison.json", {"run_id": safe_id, "comparison": comparison})
        _write_json(run_dir / "method-results.json", {"run_id": safe_id, "results": method_results})
        _write_json(run_dir / "manifest.json", manifest)
        return {
            "run_id": safe_id,
            "run_dir": str(run_dir),
            "manifest": manifest,
            "evidence": evidence,
            "comparison": comparison,
        }


def _build_comparison(evidence: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for item in evidence:
        key = (str(item["ticker"]), str(item["method"]), str(item["field"]))
        groups.setdefault(key, []).append(item)
    report = []
    for (ticker, method, field), items in sorted(groups.items()):
        report.append(
            {
                "ticker": ticker,
                "method": method,
                "field": field,
                "providers": [
                    {
                        "provider_family": item["provider_family"],
                        "provider": item["provider"],
                        "documentation_status": item["documentation_status"],
                        "status": item["status"],
                        "value": item["value"],
                        "unit": item["unit"],
                        "currency": item["currency"],
                        "as_of": item["as_of"],
                        "report_period": item["report_period"],
                        "response_hash": item["response_hash"],
                    }
                    for item in items
                ],
                "integration_eligibility": "not_qualified_by_this_change",
            }
        )
    return report


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_adapters(module_name: str | None) -> list[ProviderAdapter]:
    if not module_name:
        return unavailable_adapters()
    module = importlib.import_module(module_name)
    factory = getattr(module, "get_provider_adapters", None)
    if not callable(factory):
        raise ValueError(f"{module_name} must expose get_provider_adapters()")
    adapters = list(factory())
    required = ("provider_family", "provider", "invoke", "available")
    if not all(all(hasattr(adapter, field) for field in required) for adapter in adapters):
        raise TypeError(
            "get_provider_adapters() must return ProviderAdapter-compatible objects"
        )
    return adapters


def main() -> None:
    parser = argparse.ArgumentParser(description="Run read-only A-share provider qualification")
    parser.add_argument("--output-root", default="qualification_runs")
    parser.add_argument("--run-id")
    parser.add_argument("--adapter-module")
    args = parser.parse_args()
    result = QualificationRunner(
        adapters=load_adapters(args.adapter_module)
    ).run(output_root=args.output_root, run_id=args.run_id)
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "run_dir": result["run_dir"],
                "status_counts": result["manifest"]["status_counts"],
                "stop_reason": result["manifest"]["stop_reason"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
