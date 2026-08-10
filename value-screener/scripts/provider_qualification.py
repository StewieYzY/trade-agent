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
import multiprocessing as mp
import os
import queue as queue_module
import re
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from data.lib.production_paths import validate_g1_output_root

PROBE_PLAN_VERSION = "a-share-provider-qualification-v1"
RAW_MAX_BYTES = 200_000
EXECUTION_MODES = {"direct", "isolated"}
STOP_POLICIES = {"continue", "stop_on_timeout"}
DEFAULT_CASE_TIMEOUT_SECONDS = 60.0
DEFAULT_ADAPTER_LOAD_TIMEOUT_SECONDS = 5.0
TERMINATION_GRACE_SECONDS = 0.2
RUNTIME_CODE_ROOTS = (
    "value-screener/scripts",
    "value-screener/data",
)

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


class _RunTerminated(Exception):
    """Internal control flow for a SIGTERM received by the parent runner."""


def _sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_hash", None)
    payload.pop("artifact_hashes", None)
    return _sha256(payload)


def _code_provenance() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]

    def is_runtime_path(relative_path: str) -> bool:
        normalized = Path(relative_path).as_posix()
        return any(
            normalized == root or normalized.startswith(f"{root}/")
            for root in RUNTIME_CODE_ROOTS
        )

    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        tracked_diff = subprocess.check_output(
            ["git", "diff", "HEAD", "--binary", "--", *RUNTIME_CODE_ROOTS],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
        )
        untracked_payload = bytearray()
        runtime_dirty = False
        for line in status.splitlines():
            relative_path = line[3:] if len(line) >= 4 else ""
            if not is_runtime_path(relative_path):
                continue
            runtime_dirty = True
            if not line.startswith("?? "):
                continue
            path = repo_root / relative_path
            if path.is_file():
                untracked_payload.extend(relative_path.encode("utf-8"))
                untracked_payload.extend(b"\0")
                untracked_payload.extend(path.read_bytes())
        diff_hash = hashlib.sha256(
            tracked_diff + bytes(untracked_payload)
        ).hexdigest()
        return {
            "code_version": head,
            "code_dirty": runtime_dirty or bool(tracked_diff),
            "code_diff_hash": diff_hash,
        }
    except (OSError, subprocess.CalledProcessError):
        return {
            "code_version": "unknown",
            "code_dirty": True,
            "code_diff_hash": "unknown",
        }


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


def _validate_output_root(root: Path) -> None:
    validate_g1_output_root(root)


def _redact_text(message: str) -> str:
    text = str(message)
    text = re.sub(r"(?i)(https?://)[^/\s@]+@", r"\1<redacted>@", text)
    text = re.sub(
        r"(?i)\bauthorization\s*[:=]\s*(?:basic|bearer|token)\s+\S+",
        "Authorization=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|client[_-]?secret|refresh[_-]?token|password|passwd|secret|token)\s*[=:]\s*\S+",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\bsecret[-_][A-Za-z0-9_-]+\b",
        "<redacted>",
        text,
    )
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+\b", "sk-<redacted>", text)
    return text


def _redact_error(message: str) -> str:
    return _redact_text(message)[:2_000]


def _sensitive_mapping_key(value: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return normalized in {
        "authorization",
        "api_key",
        "apikey",
        "access_token",
        "client_secret",
        "refresh_token",
        "password",
        "passwd",
        "secret",
        "token",
    }


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


def _validate_execution_options(
    execution_mode: str,
    case_timeout_seconds: float,
    stop_policy: str,
) -> None:
    if execution_mode not in EXECUTION_MODES:
        raise ValueError(
            f"execution_mode must be one of {sorted(EXECUTION_MODES)}"
        )
    if (
        not isinstance(case_timeout_seconds, (int, float))
        or isinstance(case_timeout_seconds, bool)
        or not math.isfinite(float(case_timeout_seconds))
        or case_timeout_seconds <= 0
    ):
        raise ValueError("case timeout must be a finite positive number")
    if stop_policy not in STOP_POLICIES:
        raise ValueError(f"stop_policy must be one of {sorted(STOP_POLICIES)}")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {
            str(k): (
                "<redacted>"
                if _sensitive_mapping_key(k)
                else _json_safe(v)
            )
            for k, v in value.items()
        }
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


def _bounded_worker_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    safe = _json_safe(payload)
    encoded = json.dumps(
        safe,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    if len(encoded) <= RAW_MAX_BYTES:
        return dict(safe)
    return {
        "ok": False,
        "status": "source_failed",
        "failure_class": "payload_too_large",
        "reason": "isolated child payload exceeded safety limit",
    }


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
    safe_metadata = _json_safe(dict(metadata or {}))
    meta = dict(safe_metadata) if isinstance(safe_metadata, Mapping) else {}
    retrieved_at = datetime.now(timezone.utc).isoformat()
    raw_field = meta.pop("raw_field", field)
    return {
        "provider_family": adapter.provider_family,
        "provider": adapter.provider,
        "method": case.method,
        "market": case.market,
        "ticker": case.ticker,
        "security_type": case.security_type,
        "field": field,
        "raw_field": raw_field,
        "value": _json_safe(value),
        "unit": meta.pop("unit", None),
        "currency": meta.pop("currency", None),
        "as_of": meta.pop("as_of", None),
        "report_period": meta.pop("report_period", None),
        "status": status,
        "reason": reason,
        "documentation_status": adapter.documentation_status,
        "response_hash": response_hash,
        "retrieved_at": retrieved_at,
        "provenance": {
            **meta,
            "provider_family": adapter.provider_family,
            "provider": adapter.provider,
            "method": case.method,
            "market": case.market,
            "ticker": case.ticker,
            "raw_field": raw_field,
            "response_hash": response_hash,
            "run_scoped": True,
            "retrieved_at": retrieved_at,
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
    except _RunTerminated:
        raise
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


def _case_from_dict(payload: Mapping[str, Any]) -> ProbeCase:
    return ProbeCase(
        ticker=str(payload["ticker"]),
        market=str(payload["market"]),
        security_type=str(payload["security_type"]),
        method=str(payload["method"]),
        fields=tuple(str(field) for field in payload["fields"]),
    )


def _isolated_adapter_placeholder(_case: ProbeCase) -> Any:
    raise RuntimeError("isolated adapter placeholder must not run in parent")


def _isolated_adapter_loader_worker(
    result_queue: Any,
    adapter_module: str,
) -> None:
    try:
        adapters = load_adapters(adapter_module)
        result_queue.put(
            _bounded_worker_payload({
                "ok": True,
                "adapters": [
                    {
                        "provider_family": adapter.provider_family,
                        "provider": adapter.provider,
                        "available": adapter.available,
                        "documentation_status": adapter.documentation_status,
                        "availability_reason": adapter.availability_reason,
                    }
                    for adapter in adapters
                ],
            })
        )
    except BaseException as exc:
        result_queue.put(
            _bounded_worker_payload({
                "ok": False,
                "status": _status_from_error(exc),
                "reason": _redact_error(f"{type(exc).__name__}: {exc}"),
            })
        )


def _load_adapters_isolated(
    adapter_module: str,
    timeout_seconds: float,
) -> list[ProviderAdapter]:
    context = mp.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_isolated_adapter_loader_worker,
        args=(result_queue, adapter_module),
    )
    started = time.monotonic()
    try:
        process.start()
        deadline = started + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_process(process)
                raise TimeoutError("adapter factory timeout")
            try:
                payload = result_queue.get(timeout=min(remaining, 0.05))
                break
            except queue_module.Empty:
                if not _process_is_alive(process):
                    raise RuntimeError(
                        "isolated adapter factory exited with code "
                        f"{process.exitcode}"
                    )
        process.join(TERMINATION_GRACE_SECONDS)
        if _process_is_alive(process):
            _terminate_process(process)
        if not payload.get("ok"):
            raise RuntimeError(
                str(payload.get("reason", "isolated adapter factory failed"))
            )
        adapters: list[ProviderAdapter] = []
        for descriptor in payload.get("adapters", []):
            available = bool(descriptor.get("available", False))
            adapters.append(
                ProviderAdapter(
                    provider_family=str(descriptor["provider_family"]),
                    provider=str(descriptor["provider"]),
                    invoke=(
                        _isolated_adapter_placeholder
                        if available
                        else None
                    ),
                    available=available,
                    documentation_status=str(
                        descriptor.get("documentation_status", "unknown")
                    ),
                    availability_reason=(
                        str(descriptor["availability_reason"])
                        if descriptor.get("availability_reason") is not None
                        else None
                    ),
                )
            )
        return adapters
    finally:
        if _process_is_alive(process):
            _terminate_process(process)
        try:
            process.close()
        except ValueError:
            pass
        result_queue.close()
        result_queue.join_thread()


def _isolated_probe_worker(
    result_queue: Any,
    adapter_module: str,
    adapter_index: int,
    case_payload: Mapping[str, Any],
) -> None:
    try:
        adapters = load_adapters(adapter_module)
        adapter = adapters[adapter_index]
        evidence, method_result = _probe_case(adapter, _case_from_dict(case_payload))
        result_queue.put(
            _bounded_worker_payload({
                "ok": True,
                "evidence": evidence,
                "method_result": method_result,
            })
        )
    except BaseException as exc:
        result_queue.put(
            _bounded_worker_payload({
                "ok": False,
                "status": _status_from_error(exc),
                "reason": _redact_error(f"{type(exc).__name__}: {exc}"),
            })
        )


def _process_is_alive(process: Any) -> bool:
    try:
        return process.is_alive()
    except AssertionError:
        return False


def _terminate_process(process: Any) -> bool:
    terminated = False
    if _process_is_alive(process):
        process.terminate()
        terminated = True
        process.join(TERMINATION_GRACE_SECONDS)
    if _process_is_alive(process):
        process.kill()
        terminated = True
        process.join(TERMINATION_GRACE_SECONDS)
    return terminated


def _timeout_case(
    adapter: ProviderAdapter,
    case: ProbeCase,
    *,
    elapsed_seconds: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reason = "provider probe case exceeded timeout"
    response_hash = _sha256(
        {
            "provider": adapter.provider,
            "method": case.method,
            "ticker": case.ticker,
            "failure_class": "timeout",
        }
    )
    evidence = [
        _field_evidence(
            adapter,
            case,
            field,
            status="source_failed",
            reason=reason,
            response_hash=response_hash,
        )
        for field in case.fields
    ]
    return evidence, {
        "status": "source_failed",
        "reason": reason,
        "failure_class": "timeout",
        "terminated": True,
        "elapsed_seconds": elapsed_seconds,
        "response_hash": response_hash,
    }


def _child_error_case(
    adapter: ProviderAdapter,
    case: ProbeCase,
    *,
    status: str,
    reason: str,
    elapsed_seconds: float,
    failure_class: str = "child_error",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    safe_reason = _redact_error(reason)
    response_hash = _sha256(
        {
            "provider": adapter.provider,
            "method": case.method,
            "ticker": case.ticker,
            "status": status,
            "reason": safe_reason,
        }
    )
    evidence = [
        _field_evidence(
            adapter,
            case,
            field,
            status=status,
            reason=safe_reason,
            response_hash=response_hash,
        )
        for field in case.fields
    ]
    return evidence, {
        "status": status,
        "reason": safe_reason,
        "failure_class": failure_class,
        "terminated": False,
        "elapsed_seconds": elapsed_seconds,
        "response_hash": response_hash,
    }


def _run_isolated_case(
    *,
    adapter: ProviderAdapter,
    adapter_index: int,
    adapter_module: str,
    case: ProbeCase,
    timeout_seconds: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    context = mp.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_isolated_probe_worker,
        args=(result_queue, adapter_module, adapter_index, case.to_dict()),
    )
    started = time.monotonic()
    try:
        process.start()
        deadline = started + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if not _process_is_alive(process):
                    elapsed = time.monotonic() - started
                    return _child_error_case(
                        adapter,
                        case,
                        status="source_failed",
                        reason=(
                            "isolated child exited with code "
                            f"{process.exitcode}"
                        ),
                        elapsed_seconds=elapsed,
                        failure_class="child_exit",
                    )
                terminated = _terminate_process(process)
                elapsed = time.monotonic() - started
                evidence, method_result = _timeout_case(
                    adapter,
                    case,
                    elapsed_seconds=elapsed,
                )
                method_result["terminated"] = terminated
                return evidence, method_result
            try:
                payload = result_queue.get(timeout=min(remaining, 0.05))
                break
            except queue_module.Empty:
                if not _process_is_alive(process):
                    elapsed = time.monotonic() - started
                    return _child_error_case(
                        adapter,
                        case,
                        status="source_failed",
                        reason=(
                            "isolated child exited with code "
                            f"{process.exitcode}"
                        ),
                        elapsed_seconds=elapsed,
                        failure_class="child_exit",
                    )
        process.join(TERMINATION_GRACE_SECONDS)
        if _process_is_alive(process):
            _terminate_process(process)
        elapsed = time.monotonic() - started
        if not payload.get("ok"):
            return _child_error_case(
                adapter,
                case,
                status=str(payload.get("status", "source_failed")),
                reason=str(payload.get("reason", "isolated child failed")),
                elapsed_seconds=elapsed,
                failure_class=str(
                    payload.get("failure_class", "child_error")
                ),
            )
        method_result = dict(payload["method_result"])
        method_result["elapsed_seconds"] = elapsed
        return list(payload["evidence"]), method_result
    except KeyboardInterrupt:
        _terminate_process(process)
        raise
    except _RunTerminated:
        _terminate_process(process)
        raise
    except BaseException as exc:
        _terminate_process(process)
        elapsed = time.monotonic() - started
        return _child_error_case(
            adapter,
            case,
            status=_status_from_error(exc),
            reason=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=elapsed,
            failure_class="process_error",
        )
    finally:
        if _process_is_alive(process):
            _terminate_process(process)
        try:
            process.close()
        except ValueError:
            pass
        result_queue.close()
        result_queue.join_thread()


def _append_event(path: Path, event: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                _json_safe(event),
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            + "\n"
        )
        handle.flush()


class QualificationRunner:
    def __init__(
        self,
        *,
        adapters: Iterable[ProviderAdapter] | None = None,
        cases: Iterable[ProbeCase] | None = None,
        plan_version: str = PROBE_PLAN_VERSION,
        adapter_module: str | None = None,
        execution_mode: str = "direct",
        case_timeout_seconds: float = DEFAULT_CASE_TIMEOUT_SECONDS,
        adapter_load_timeout_seconds: float = (
            DEFAULT_ADAPTER_LOAD_TIMEOUT_SECONDS
        ),
        stop_policy: str = "continue",
    ):
        _validate_execution_options(
            execution_mode,
            case_timeout_seconds,
            stop_policy,
        )
        if (
            not isinstance(adapter_load_timeout_seconds, (int, float))
            or isinstance(adapter_load_timeout_seconds, bool)
            or not math.isfinite(float(adapter_load_timeout_seconds))
            or adapter_load_timeout_seconds <= 0
        ):
            raise ValueError(
                "adapter load timeout must be a finite positive number"
            )
        self.adapter_module = adapter_module
        self.execution_mode = execution_mode
        self.case_timeout_seconds = float(case_timeout_seconds)
        self.adapter_load_timeout_seconds = float(
            adapter_load_timeout_seconds
        )
        self.stop_policy = stop_policy
        self.adapter_load_error: str | None = None
        self._adapter_discovery_pending = bool(
            adapter_module and execution_mode == "isolated"
        )
        if self._adapter_discovery_pending:
            self.adapters = []
        elif adapter_module:
            try:
                self.adapters = load_adapters(adapter_module)
            except Exception as exc:
                self.adapters = []
                self.adapter_load_error = _redact_error(
                    f"{type(exc).__name__}: {exc}"
                )
            if not self.adapters and self.adapter_load_error is None:
                self.adapter_load_error = "adapter registry returned no adapters"
        elif adapters is None:
            self.adapters = unavailable_adapters()
        else:
            self.adapters = list(adapters)
        if (
            execution_mode == "isolated"
            and not adapter_module
            and any(adapter.available and adapter.invoke for adapter in self.adapters)
        ):
            raise ValueError("adapter_module is required for isolated execution")
        self.cases = list(build_probe_plan() if cases is None else cases)
        if not self.cases:
            raise ValueError("qualification probe plan must not be empty")
        self.plan_version = plan_version
        if execution_mode == "isolated" and not adapter_module:
            self.execution_mode = "direct"

    def _execute_case(
        self,
        *,
        adapter: ProviderAdapter,
        adapter_index: int,
        case: ProbeCase,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.monotonic()
        if self.execution_mode == "direct" or not self.adapter_module:
            evidence, method_result = _probe_case(adapter, case)
            method_result = dict(method_result)
            method_result["elapsed_seconds"] = time.monotonic() - started
            return evidence, method_result
        return _run_isolated_case(
            adapter=adapter,
            adapter_index=adapter_index,
            adapter_module=self.adapter_module or "",
            case=case,
            timeout_seconds=self.case_timeout_seconds,
        )

    def run(
        self,
        *,
        output_root: str | Path,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        safe_id = _safe_run_id(run_id)
        root = validate_g1_output_root(output_root)
        if not self.adapters and not self.adapter_module:
            raise ValueError("at least one provider adapter must be configured")
        run_dir = (root / safe_id).resolve()
        try:
            run_dir.relative_to(root)
        except ValueError as exc:
            raise ValueError("run_id escapes output_root") from exc
        run_dir.mkdir(parents=True, exist_ok=False)

        plan = [case.to_dict() for case in self.cases]
        plan_hash = _sha256({"version": self.plan_version, "cases": plan})
        total_cases = len(self.adapters) * len(self.cases)
        evidence: list[dict[str, Any]] = []
        method_results: list[dict[str, Any]] = []
        raw_by_hash: dict[str, Any] = {}
        stop_reasons: list[str] = []
        completed_cases = 0
        timed_out_cases = 0
        interrupted_cases = 0
        terminal_cases = 0
        status_counts: dict[str, int] = {}
        case_status_counts: dict[str, int] = {}
        stop_requested = False
        run_interrupted = False
        events_path = run_dir / "events.ndjson"
        events_path.touch()

        manifest = {
            "schema_version": "a-share-provider-qualification-v1",
            "run_id": safe_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **_code_provenance(),
            "plan_version": self.plan_version,
            "plan_hash": plan_hash,
            "ticker_set_hash": _sha256(sorted({case.ticker for case in self.cases})),
            "provider_count": len(self.adapters),
            "adapter_load_error": self.adapter_load_error,
            "provider_methods": [
                {
                    "provider_family": adapter.provider_family,
                    "provider": adapter.provider,
                    "documentation_status": adapter.documentation_status,
                    "available": adapter.available and adapter.invoke is not None,
                }
                for adapter in self.adapters
            ],
            "execution_mode": self.execution_mode,
            "case_timeout_seconds": self.case_timeout_seconds,
            "adapter_load_timeout_seconds": (
                self.adapter_load_timeout_seconds
            ),
            "stop_policy": self.stop_policy,
            "completion_status": "running",
            "total_cases": total_cases,
            "completed_cases": 0,
            "timed_out_cases": 0,
            "interrupted_cases": 0,
            "not_started_cases": total_cases,
            "status_counts": {},
            "field_status_counts": {},
            "case_status_counts": {},
            "stop_reason": None,
            "stop_reasons": stop_reasons,
            "artifact_status": {
                "plan": "written",
                "events": "written",
                "manifest": "written",
                "evidence": "pending",
                "raw": "pending",
                "comparison": "pending",
                "method_results": "pending",
            },
            "artifacts": {
                "plan": "plan.json",
                "events": "events.ndjson",
                "evidence": "evidence.json",
                "raw": "raw.json",
                "comparison": "comparison.json",
                "method_results": "method-results.json",
                "manifest": "manifest.json",
            },
        }

        def persist_running_manifest() -> None:
            manifest.update(
                {
                    "completion_status": "running",
                    "completed_cases": completed_cases,
                    "timed_out_cases": timed_out_cases,
                    "interrupted_cases": interrupted_cases,
                    "not_started_cases": max(total_cases - terminal_cases, 0),
                    "status_counts": dict(status_counts),
                    "field_status_counts": dict(status_counts),
                    "case_status_counts": dict(case_status_counts),
                    "stop_reason": stop_reasons[0] if stop_reasons else None,
                    "stop_reasons": list(stop_reasons),
                }
            )
            _write_json(run_dir / "manifest.json", manifest)

        _write_json(
            run_dir / "plan.json",
            {
                "run_id": safe_id,
                "version": self.plan_version,
                "plan_hash": plan_hash,
                "cases": plan,
            },
        )
        _write_json(run_dir / "manifest.json", manifest)

        active_adapter: ProviderAdapter | None = None
        active_case: ProbeCase | None = None
        active_case_started: float | None = None
        previous_sigterm_handler: Any = None
        sigterm_handler_installed = False
        if threading.current_thread() is threading.main_thread():
            previous_sigterm_handler = signal.getsignal(signal.SIGTERM)

            def handle_sigterm(_signum: int, _frame: Any) -> None:
                raise _RunTerminated

            signal.signal(signal.SIGTERM, handle_sigterm)
            sigterm_handler_installed = True

        def record_interruption(
            adapter: ProviderAdapter,
            case: ProbeCase,
            *,
            reason: str,
            elapsed_seconds: float,
        ) -> None:
            nonlocal interrupted_cases, terminal_cases, stop_requested
            interrupted_cases += 1
            terminal_cases += 1
            stop_requested = True
            if reason not in stop_reasons:
                stop_reasons.append(reason)
            case_status_counts["source_failed"] = (
                case_status_counts.get("source_failed", 0) + 1
            )
            event = {
                "run_id": safe_id,
                "provider_family": adapter.provider_family,
                "provider": adapter.provider,
                "method": case.method,
                "ticker": case.ticker,
                "fields": list(case.fields),
                "execution_mode": self.execution_mode,
                "status": "source_failed",
                "failure_class": "interrupted",
                "terminated": True,
                "elapsed_seconds": elapsed_seconds,
            }
            _append_event(events_path, event)
            persist_running_manifest()

        try:
            if self._adapter_discovery_pending:
                try:
                    self.adapters = _load_adapters_isolated(
                        self.adapter_module or "",
                        self.adapter_load_timeout_seconds,
                    )
                except _RunTerminated:
                    raise
                except Exception as exc:
                    self.adapters = []
                    self.adapter_load_error = _redact_error(
                        f"{type(exc).__name__}: {exc}"
                    )
                if not self.adapters and self.adapter_load_error is None:
                    self.adapter_load_error = (
                        "adapter registry returned no adapters"
                    )
                self._adapter_discovery_pending = False
                total_cases = len(self.adapters) * len(self.cases)
                manifest.update(
                    {
                        "provider_count": len(self.adapters),
                        "adapter_load_error": self.adapter_load_error,
                        "provider_methods": [
                            {
                                "provider_family": adapter.provider_family,
                                "provider": adapter.provider,
                                "documentation_status": (
                                    adapter.documentation_status
                                ),
                                "available": (
                                    adapter.available
                                    and adapter.invoke is not None
                                ),
                            }
                            for adapter in self.adapters
                        ],
                        "total_cases": total_cases,
                    }
                )
                persist_running_manifest()
            for adapter_index, adapter in enumerate(self.adapters):
                for case in self.cases:
                    active_adapter = adapter
                    active_case = case
                    active_case_started = time.monotonic()
                    try:
                        case_evidence, method_result = self._execute_case(
                            adapter=adapter,
                            adapter_index=adapter_index,
                            case=case,
                        )
                    except KeyboardInterrupt:
                        record_interruption(
                            adapter,
                            case,
                            reason="interrupted",
                            elapsed_seconds=(
                                time.monotonic() - active_case_started
                                if active_case_started is not None
                                else 0.0
                            ),
                        )
                        active_adapter = None
                        active_case = None
                        active_case_started = None
                        break
                    active_adapter = None
                    active_case = None
                    active_case_started = None

                    evidence.extend(case_evidence)
                    method_result = dict(method_result)
                    method_result.update(
                        {
                            "provider_family": adapter.provider_family,
                            "provider": adapter.provider,
                            "method": case.method,
                            "ticker": case.ticker,
                        }
                    )
                    method_results.append(method_result)
                    for item in case_evidence:
                        status = item["status"]
                        status_counts[status] = status_counts.get(status, 0) + 1
                    case_status = str(method_result.get("status", "source_failed"))
                    case_status_counts[case_status] = (
                        case_status_counts.get(case_status, 0) + 1
                    )
                    failure_class = method_result.get("failure_class")
                    if failure_class == "timeout":
                        timed_out_cases += 1
                        if (
                            self.stop_policy == "stop_on_timeout"
                            and "timeout" not in stop_reasons
                        ):
                            stop_reasons.append("timeout")
                    else:
                        completed_cases += 1
                    terminal_cases += 1
                    event = {
                        "run_id": safe_id,
                        "provider_family": adapter.provider_family,
                        "provider": adapter.provider,
                        "method": case.method,
                        "ticker": case.ticker,
                        "fields": list(case.fields),
                        "execution_mode": self.execution_mode,
                        "status": method_result.get("status"),
                        "elapsed_seconds": method_result.get("elapsed_seconds", 0.0),
                    }
                    for key in ("failure_class", "terminated", "reason"):
                        if method_result.get(key) is not None:
                            event[key] = method_result[key]
                    _append_event(events_path, event)
                    persist_running_manifest()
                    if method_result.get("response_hash") and "raw" in method_result:
                        raw_by_hash[method_result["response_hash"]] = {
                            "provider": adapter.provider,
                            "method": case.method,
                            "ticker": case.ticker,
                            "raw": method_result["raw"],
                            "raw_truncated": method_result.get("raw_truncated", False),
                        }
                    if method_result.get("status") == "rate_limited":
                        stop_reasons.append(
                            f"rate_limited:{adapter.provider}:{case.method}:{case.ticker}"
                        )
                        break
                    if (
                        failure_class == "timeout"
                        and self.stop_policy == "stop_on_timeout"
                    ):
                        if "timeout" not in stop_reasons:
                            stop_reasons.append("timeout")
                        stop_requested = True
                        break
                if stop_requested:
                    break
        except _RunTerminated:
            run_interrupted = True
            if active_adapter is not None and active_case is not None:
                record_interruption(
                    active_adapter,
                    active_case,
                    reason="terminated",
                    elapsed_seconds=(
                        time.monotonic() - active_case_started
                        if active_case_started is not None
                        else 0.0
                    ),
                )
            elif "terminated" not in stop_reasons:
                stop_reasons.append("terminated")
        except KeyboardInterrupt:
            run_interrupted = True
            if active_adapter is not None and active_case is not None:
                record_interruption(
                    active_adapter,
                    active_case,
                    reason="interrupted",
                    elapsed_seconds=(
                        time.monotonic() - active_case_started
                        if active_case_started is not None
                        else 0.0
                    ),
                )
            elif "interrupted" not in stop_reasons:
                stop_reasons.append("interrupted")
        except BaseException:
            if sigterm_handler_installed:
                signal.signal(signal.SIGTERM, previous_sigterm_handler)
            raise
        if sigterm_handler_installed:
            signal.signal(signal.SIGTERM, previous_sigterm_handler)

        not_started_cases = max(total_cases - terminal_cases, 0)
        stop_reason = stop_reasons[0] if stop_reasons else None
        if self.adapter_load_error:
            stop_reason = "adapter_load_failed"
        adapters_unavailable = bool(self.adapters) and all(
            not adapter.available or adapter.invoke is None
            for adapter in self.adapters
        )
        if not stop_reason and adapters_unavailable and evidence and all(
            item["status"] == "not_evaluated" for item in evidence
        ):
            stop_reason = "no_runtime_provider_adapter_available"
        if not stop_reason and timed_out_cases:
            stop_reason = "completed_with_timeout"
        all_cases_terminal = terminal_cases == total_cases
        completion_status = (
            "completed"
            if (
                not self.adapter_load_error
                and all_cases_terminal
                and not timed_out_cases
                and not interrupted_cases
                and not run_interrupted
            )
            else "incomplete"
        )
        aggregate_artifact_status = (
            "written" if completion_status == "completed" else "not_written"
        )
        manifest["artifact_status"] = {
            "plan": "written",
            "events": "written",
            "manifest": "written",
            "evidence": aggregate_artifact_status,
            "raw": aggregate_artifact_status,
            "comparison": aggregate_artifact_status,
            "method_results": aggregate_artifact_status,
        }
        manifest.update(
            {
                "completion_status": completion_status,
                "completed_cases": completed_cases,
                "timed_out_cases": timed_out_cases,
                "interrupted_cases": interrupted_cases,
                "not_started_cases": not_started_cases,
                "status_counts": status_counts,
                "field_status_counts": status_counts,
                "case_status_counts": case_status_counts,
                "stop_reason": stop_reason,
                "stop_reasons": stop_reasons,
            }
        )
        comparison = (
            _build_comparison(evidence)
            if completion_status == "completed"
            else None
        )
        if completion_status == "completed":
            _write_json(run_dir / "evidence.json", {"run_id": safe_id, "evidence": evidence})
            _write_json(run_dir / "raw.json", {"run_id": safe_id, "responses": list(raw_by_hash.values())})
            _write_json(run_dir / "comparison.json", {"run_id": safe_id, "comparison": comparison})
            _write_json(run_dir / "method-results.json", {"run_id": safe_id, "results": method_results})
            manifest["artifact_hashes"] = {
                "plan": _sha256_bytes((run_dir / "plan.json").read_bytes()),
                "evidence": _sha256_bytes((run_dir / "evidence.json").read_bytes()),
            }
            manifest["manifest_hash"] = _manifest_hash(manifest)
        _write_json(run_dir / "manifest.json", manifest)
        return {
            "run_id": safe_id,
            "run_dir": str(run_dir),
            "manifest": manifest,
            "evidence": (
                evidence
                if completion_status == "completed"
                else None
            ),
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


def _positive_finite_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "case timeout must be a finite positive number"
        ) from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError(
            "case timeout must be a finite positive number"
        )
    return timeout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run read-only A-share provider qualification"
    )
    parser.add_argument("--output-root", default="qualification_runs")
    parser.add_argument("--run-id")
    parser.add_argument("--adapter-module")
    parser.add_argument(
        "--execution-mode",
        choices=sorted(EXECUTION_MODES),
        default="isolated",
    )
    parser.add_argument(
        "--case-timeout-seconds",
        type=_positive_finite_timeout,
        default=DEFAULT_CASE_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--stop-policy",
        choices=sorted(STOP_POLICIES),
        default="continue",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = QualificationRunner(
        adapter_module=args.adapter_module,
        execution_mode=args.execution_mode,
        case_timeout_seconds=args.case_timeout_seconds,
        stop_policy=args.stop_policy,
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
