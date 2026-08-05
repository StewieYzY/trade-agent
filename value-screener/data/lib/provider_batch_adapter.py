"""Explicit provider batch adapter and evidence-preserving merge boundary."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .canonical_snapshot import build_snapshot, write_snapshot
from .identity import canonical_ticker
from .provenance import ELIGIBILITIES, STATUSES, redact_sensitive_text


def _canonical_a_share_ticker(raw: Any) -> str:
    ticker = canonical_ticker(raw)
    if not ticker.endswith((".SH", ".SZ", ".BJ")):
        raise ValueError(f"ticker {raw!r} is not an A-share security")
    return ticker


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _classify_error(exc: Exception) -> str:
    code = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    message = str(exc).lower()
    if isinstance(exc, (ImportError, ModuleNotFoundError, NotImplementedError)):
        return "not_evaluated"
    if isinstance(exc, PermissionError) or code in {401, 403}:
        return "permission_denied"
    if code == 429 or "rate limit" in message or "too many requests" in message:
        return "rate_limited"
    if "not supported" in message or "unsupported" in message:
        return "not_supported_for_market"
    if "no record" in message or "not found" in message:
        return "source_failed"
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return "invalid_value"
    return "source_failed"


def _redact(value: Any) -> str:
    return redact_sensitive_text(value)


@dataclass(frozen=True)
class BatchRequest:
    provider_family: str
    provider: str
    method: str
    tickers: tuple[str, ...]
    fields: tuple[str, ...]
    run_id: str
    shadow: bool

    @property
    def ticker_set_hash(self) -> str:
        return _hash(self.tickers)

    @property
    def fields_hash(self) -> str:
        return _hash(self.fields)

    @property
    def request_id(self) -> str:
        return ":".join(
            (
                self.run_id,
                self.provider,
                self.method,
                self.ticker_set_hash,
                self.fields_hash,
            )
        )


@dataclass(frozen=True)
class ProviderSpec:
    provider_family: str
    provider: str
    fetch_batch: Callable[[BatchRequest], Any] | None
    shadow: bool = False
    available: bool = True
    eligibility: str = "not_qualified"


class BatchAdapter:
    """Run explicitly registered providers once per method/ticker set."""

    def __init__(self, providers: Iterable[ProviderSpec]):
        self.providers = list(providers)
        for provider in self.providers:
            if not provider.provider_family or not provider.provider:
                raise ValueError("provider family and provider must be non-empty")
            if not provider.eligibility in ELIGIBILITIES:
                raise ValueError(f"unknown provider eligibility: {provider.eligibility!r}")
            if provider.fetch_batch is not None and not callable(provider.fetch_batch):
                raise TypeError("fetch_batch must be callable or None")

    def run(
        self,
        *,
        tickers: Iterable[str],
        method: str,
        fields: Iterable[str],
        run_id: str | None = None,
        output_root: str | Path | None = None,
        plan_version: str = "g1-provider-batch-adapter-v1",
        freshness_seconds: int | None = None,
    ) -> dict[str, Any]:
        safe_id = _safe_run_id(run_id)
        if freshness_seconds is not None and freshness_seconds < 0:
            raise ValueError("freshness_seconds must be non-negative")
        if not isinstance(method, str) or not method.strip():
            raise ValueError("method must be a non-empty string")
        method = method.strip()
        if fields is None or isinstance(fields, (str, bytes)):
            raise ValueError("fields must be an iterable of non-empty strings")
        if tickers is None or isinstance(tickers, (str, bytes)):
            raise ValueError("tickers must be an iterable of A-share tickers")
        try:
            raw_tickers = tuple(tickers)
        except TypeError as exc:
            raise ValueError(
                "tickers must be an iterable of A-share tickers"
            ) from exc
        canonical_tickers, invalid_tickers = _normalize_requested_tickers(raw_tickers)
        if not canonical_tickers:
            if invalid_tickers:
                raise ValueError("invalid ticker set: no valid A-share ticker")
            raise ValueError("ticker set must not be empty")
        try:
            raw_fields = tuple(fields)
        except TypeError as exc:
            raise ValueError(
                "fields must be an iterable of non-empty strings"
            ) from exc
        if any(
            not isinstance(field, str) or not field.strip()
            for field in raw_fields
        ):
            raise ValueError("fields must contain only non-empty strings")
        requested_fields = tuple(dict.fromkeys(field.strip() for field in raw_fields))
        if not requested_fields:
            raise ValueError("field set must not be empty")

        evidence: list[dict[str, Any]] = []
        stats: dict[str, int] = {}
        provider_summaries: list[dict[str, Any]] = []
        freshness_reference = datetime.now(timezone.utc)

        for provider in self.providers:
            key = f"{provider.provider_family}:{provider.provider}:{method}"
            request = BatchRequest(
                provider_family=provider.provider_family,
                provider=provider.provider,
                method=method,
                tickers=canonical_tickers,
                fields=requested_fields,
                run_id=safe_id,
                shadow=provider.shadow,
            )
            base = {
                "provider_family": provider.provider_family,
                "provider": provider.provider,
                "method": method,
                "market": "A",
                "security_type": "A-share",
                "eligibility": "shadow_only" if provider.shadow else provider.eligibility,
            }
            if not provider.available or provider.fetch_batch is None:
                reason = "provider adapter unavailable"
                error_hash = _hash(
                    {
                        "request_id": request.request_id,
                        "status": "not_evaluated",
                        "reason": reason,
                    }
                )
                evidence.extend(
                    _failure_evidence(
                        base,
                        canonical_tickers,
                        requested_fields,
                        status="not_evaluated",
                        reason=reason,
                        response_hash=error_hash,
                    )
                )
                provider_summaries.append(
                    _provider_summary(
                        provider,
                        request,
                        canonical_tickers,
                        (),
                        reason,
                        call_count=0,
                        response_hash=error_hash,
                        status_summary=_status_summary_for(
                            "not_evaluated",
                            len(canonical_tickers) * len(requested_fields),
                        ),
                    )
                )
                continue

            try:
                provider_evidence_start = len(evidence)
                stats[key] = stats.get(key, 0) + 1
                response = provider.fetch_batch(request)
                response_hash = _hash(response)
                records, response_issues = _records_by_ticker(response)
                issues_by_ticker = {
                    issue["ticker"]: issue
                    for issue in response_issues
                    if issue.get("ticker") in canonical_tickers
                }
                unbound_issues = [
                    issue for issue in response_issues if issue.get("ticker") is None
                ]
                for issue in issues_by_ticker.values():
                    evidence.extend(
                        _failure_evidence(
                            {**base, "ticker": issue["ticker"]},
                            (issue["ticker"],),
                            requested_fields,
                            status=issue["status"],
                            reason=issue["reason"],
                            response_hash=response_hash,
                        )
                    )
                returned = tuple(sorted(records))
                missing = tuple(ticker for ticker in canonical_tickers if ticker not in records)
                for ticker in canonical_tickers:
                    if ticker in issues_by_ticker:
                        continue
                    record = records.get(ticker)
                    if record is None:
                        if unbound_issues:
                            evidence.extend(
                                _failure_evidence(
                                    {**base, "ticker": ticker},
                                    (ticker,),
                                    requested_fields,
                                    status="invalid_value",
                                    reason=unbound_issues[0]["reason"],
                                    response_hash=response_hash,
                                )
                            )
                            continue
                        evidence.extend(
                            _failure_evidence(
                                {**base, "ticker": ticker},
                                (ticker,),
                                requested_fields,
                                status="record_not_found",
                                reason="provider response omitted ticker",
                                response_hash=response_hash,
                            )
                        )
                        continue
                    evidence.extend(
                        _record_evidence(
                            base,
                            ticker,
                            record,
                            requested_fields,
                            response_hash,
                            freshness_seconds=freshness_seconds,
                            freshness_reference=freshness_reference,
                        )
                    )
                provider_summaries.append(
                    _provider_summary(
                        provider,
                        request,
                        returned,
                        missing,
                        None,
                        call_count=1,
                        response_hash=response_hash,
                        status_summary=_status_summary(evidence[provider_evidence_start:]),
                    )
                )
            except Exception as exc:
                status = _classify_error(exc)
                reason = _redact(f"{type(exc).__name__}: {exc}")
                error_hash = _hash(
                    {
                        "request_id": request.request_id,
                        "status": status,
                        "reason": reason,
                    }
                )
                stats[key] = stats.get(key, 0) + 1
                evidence.extend(
                    _failure_evidence(
                        base,
                        canonical_tickers,
                        requested_fields,
                        status=status,
                        reason=reason,
                        response_hash=error_hash,
                    )
                )
                provider_summaries.append(
                    _provider_summary(
                        provider,
                        request,
                        (),
                        canonical_tickers,
                        reason,
                        call_count=1,
                        response_hash=error_hash,
                        status_summary=_status_summary_for(
                            status,
                            len(canonical_tickers) * len(requested_fields),
                        ),
                    )
                )

        manifest = {
            "schema_version": "g1-provider-batch-adapter-v1",
            "run_id": safe_id,
            "method": method,
            "requested_tickers": list(canonical_tickers),
            "requested_ticker_set_hash": _hash(canonical_tickers),
            "requested_fields": list(requested_fields),
            "requested_fields_hash": _hash(requested_fields),
            "invalid_tickers": invalid_tickers,
            "provider_method_calls": stats,
            "batch_size": len(canonical_tickers),
            "status_summary": _status_summary(evidence),
            "providers": provider_summaries,
            "evidence_count": len(evidence),
            "freshness_seconds": freshness_seconds,
            "freshness_evaluated_at": (
                freshness_reference.isoformat()
                if freshness_seconds is not None
                else None
            ),
            "snapshot_output": None,
        }
        snapshot = build_snapshot(
            evidence,
            tickers=canonical_tickers,
            plan_version=plan_version,
            run_id=safe_id,
            freshness_seconds=freshness_seconds,
            freshness_as_of=(
                freshness_reference if freshness_seconds is not None else None
            ),
        )
        output_path = None
        if output_root is not None:
            output_path = str(
                write_snapshot(
                    evidence,
                    tickers=canonical_tickers,
                    plan_version=plan_version,
                    output_root=output_root,
                    run_id=safe_id,
                    freshness_seconds=freshness_seconds,
                    freshness_as_of=(
                        freshness_reference if freshness_seconds is not None else None
                    ),
                    manifest_extra={
                        key: value
                        for key, value in manifest.items()
                        if key
                        not in {
                            "run_id",
                            "schema_version",
                            "status_summary",
                            "snapshot_output",
                            "freshness_evaluated_at",
                        }
                    },
                )
            )
        manifest["snapshot_output"] = output_path
        return {
            "run_id": safe_id,
            "manifest": manifest,
            "evidence": evidence,
            "snapshot": snapshot,
        }


def _normalize_requested_tickers(
    tickers: Iterable[Any],
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    canonical: set[str] = set()
    invalid: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_ticker in tickers:
        try:
            normalized = _canonical_a_share_ticker(raw_ticker)
            if normalized in seen:
                invalid.append(
                    {
                        "raw_ticker": raw_ticker,
                        "status": "invalid_value",
                        "reason": f"duplicate canonical ticker {normalized}",
                    }
                )
                continue
            seen.add(normalized)
            canonical.add(normalized)
        except (TypeError, ValueError) as exc:
            invalid.append(
                {
                    "raw_ticker": raw_ticker,
                    "status": "invalid_value",
                    "reason": _redact(str(exc)),
                }
            )
    return tuple(sorted(canonical)), invalid


def _records_by_ticker(
    response: Any,
) -> tuple[dict[str, Mapping[str, Any]], list[dict[str, Any]]]:
    if isinstance(response, Mapping) and isinstance(response.get("records"), list):
        rows = response["records"]
    elif isinstance(response, Mapping):
        if not response:
            raise RuntimeError("provider response is empty")
        if (
            any(key in response for key in ("status", "data", "error", "message"))
            and any(not isinstance(value, Mapping) for value in response.values())
        ):
            raise ValueError(
                "batch response schema must be a ticker mapping or records list"
            )
        rows = response.items()
    elif isinstance(response, list):
        rows = response
    else:
        raise TypeError("batch response must be a mapping or list")
    if not rows:
        raise RuntimeError("provider response is empty")

    result: dict[str, Mapping[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(response, Mapping) and response.get("records") is None:
            raw_key, record = row
            if not isinstance(record, Mapping):
                try:
                    ticker = _canonical_a_share_ticker(str(raw_key))
                except ValueError:
                    ticker = None
                issues.append(
                    {
                        "ticker": ticker,
                        "raw_ticker": raw_key,
                        "status": "invalid_value",
                        "reason": "response record must be a mapping",
                    }
                )
                continue
        else:
            if not isinstance(row, Mapping):
                issues.append(
                    {
                        "ticker": None,
                        "raw_ticker": None,
                        "status": "invalid_value",
                        "reason": "batch response row must be a mapping",
                    }
                )
                continue
            raw_key = row.get("ticker") or row.get("code") or row.get("symbol")
            record = row
        if raw_key is None:
            issues.append(
                {
                    "ticker": None,
                    "raw_ticker": None,
                    "status": "invalid_value",
                    "reason": "batch response row is missing ticker",
                }
            )
            continue
        try:
            ticker = _canonical_a_share_ticker(str(raw_key))
        except ValueError as exc:
            embedded_raw = (
                record.get("ticker")
                or record.get("code")
                or record.get("symbol")
            ) if isinstance(record, Mapping) else None
            embedded_ticker = None
            if embedded_raw is not None:
                try:
                    embedded_ticker = _canonical_a_share_ticker(str(embedded_raw))
                except ValueError:
                    pass
            issues.append(
                {
                    "ticker": embedded_ticker,
                    "raw_ticker": raw_key,
                    "status": "invalid_value",
                    "reason": (
                        f"invalid response mapping key {raw_key!r}"
                        + (
                            f" for embedded ticker {embedded_ticker}"
                            if embedded_ticker
                            else f" (unbindable): {_redact(str(exc))}"
                        )
                    ),
                }
            )
            continue
        embedded_raw = (
            record.get("ticker")
            or record.get("code")
            or record.get("symbol")
        )
        if embedded_raw is not None:
            try:
                embedded_ticker = _canonical_a_share_ticker(str(embedded_raw))
            except ValueError as exc:
                issues.append(
                    {
                        "ticker": ticker,
                        "raw_ticker": embedded_raw,
                        "status": "invalid_value",
                        "reason": _redact(str(exc)),
                    }
                )
                continue
            if embedded_ticker != ticker:
                issues.append(
                    {
                        "ticker": ticker,
                        "raw_ticker": embedded_raw,
                        "status": "invalid_value",
                        "reason": (
                            f"response ticker {embedded_ticker} does not match "
                            f"mapping key {ticker}"
                        ),
                    }
                )
                continue
        if ticker in result:
            issues.append(
                {
                    "ticker": ticker,
                    "raw_ticker": raw_key,
                    "status": "invalid_value",
                    "reason": f"duplicate response ticker {ticker}",
                }
            )
            continue
        result[ticker] = record
    return result, issues


def _record_evidence(
    base: Mapping[str, Any],
    ticker: str,
    record: Mapping[str, Any],
    fields: tuple[str, ...],
    response_hash: str,
    *,
    freshness_seconds: int | None = None,
    freshness_reference: datetime | None = None,
) -> list[dict[str, Any]]:
    field_meta = record.get("_fields", {})
    result = []
    for field in fields:
        raw = record.get(field)
        metadata_error = None
        if not isinstance(field_meta, Mapping):
            metadata = {}
            metadata_error = "field metadata container must be a mapping"
        else:
            metadata = field_meta.get(field, {})
            if not isinstance(metadata, Mapping):
                metadata = {}
                metadata_error = "field metadata must be a mapping"
        if isinstance(raw, Mapping) and "value" in raw:
            value = raw.get("value")
            metadata = {**metadata, **raw}
        else:
            value = raw
        reason = metadata_error
        status = "invalid_value" if metadata_error else (
            metadata.get("status") or record.get("_status")
        )
        if status is None:
            if field not in record:
                status = "not_evaluated"
                reason = "provider record omitted field"
            elif value is None:
                status = "not_evaluated"
                reason = "provider field has no value"
            else:
                status = "available"
        elif status == "available" and value is None:
            status = "not_evaluated"
            reason = reason or "provider field has no value"
        if status not in STATUSES:
            reason = f"unknown provider field status: {status!r}"
            status = "invalid_value"
        item = _make_evidence(
            {**base, "ticker": ticker},
            field,
            value,
            metadata,
            status=status,
            response_hash=response_hash,
            reason=reason,
        )
        retrieved_at = metadata.get("retrieved_at")
        parsed_retrieved_at = _parse_timestamp(retrieved_at)
        if item["status"] == "available" and parsed_retrieved_at is None:
            item["freshness_status"] = "unknown"
            item["reason"] = (
                "retrieved_at is missing or invalid for freshness evaluation"
            )
        elif (
            freshness_seconds is not None
            and item["status"] == "available"
        ):
            if _is_stale(
                retrieved_at,
                freshness_seconds,
                now=freshness_reference,
            ):
                item["freshness_status"] = "stale"
                item["reason"] = (
                    f"evidence older than freshness window ({freshness_seconds}s)"
                )
        result.append(item)
    return result


def _failure_evidence(
    base: Mapping[str, Any],
    tickers: Iterable[str],
    fields: tuple[str, ...],
    *,
    status: str,
    reason: str,
    response_hash: str | None = None,
) -> list[dict[str, Any]]:
    result = []
    for ticker in tickers:
        for field in fields:
            result.append(
                _make_evidence(
                    {**base, "ticker": ticker},
                    field,
                    None,
                    {},
                    status=status,
                    reason=reason,
                    response_hash=response_hash,
                )
            )
    return result


def _make_evidence(
    base: Mapping[str, Any],
    field: str,
    value: Any,
    metadata: Mapping[str, Any],
    *,
    status: str,
    response_hash: str | None,
    reason: str | None = None,
) -> dict[str, Any]:
    retrieved_at = metadata.get("retrieved_at")
    return {
        **base,
        "field": field,
        "raw_field": metadata.get("raw_field", field),
        "value": value,
        "unit": metadata.get("unit"),
        "currency": metadata.get("currency"),
        "as_of": metadata.get("as_of"),
        "report_period": metadata.get("report_period"),
        "status": status,
        "eligibility": base.get("eligibility", "not_qualified"),
        "response_hash": response_hash or _hash({"status": status, "reason": reason}),
        "retrieved_at": retrieved_at,
        "reason": reason,
        "provenance": {
            "provider_family": base.get("provider_family"),
            "provider": base.get("provider"),
            "method": base.get("method"),
            "market": base.get("market"),
            "ticker": base.get("ticker"),
            "raw_field": metadata.get("raw_field", field),
            "response_hash": response_hash or _hash({"status": status, "reason": reason}),
            "retrieved_at": retrieved_at,
        },
    }


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_stale(
    retrieved_at: Any,
    freshness_seconds: int,
    *,
    now: datetime | None = None,
) -> bool:
    parsed = _parse_timestamp(retrieved_at)
    if parsed is None:
        return True
    reference = now or datetime.now(timezone.utc)
    return (reference - parsed).total_seconds() > freshness_seconds


def _status_summary_for(status: str, count: int) -> dict[str, int]:
    return {status: count}


def _status_summary(
    evidence: Iterable[Mapping[str, Any]],
    provider: str | None = None,
    method: str | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in evidence:
        if provider is not None and item.get("provider") != provider:
            continue
        if method is not None and item.get("method") != method:
            continue
        status = str(item.get("status"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _provider_summary(
    provider: ProviderSpec,
    request: BatchRequest,
    returned: Iterable[str],
    missing: Iterable[str],
    reason: str | None,
    *,
    call_count: int,
    response_hash: str,
    status_summary: Mapping[str, int],
) -> dict[str, Any]:
    returned_tuple = tuple(sorted(returned))
    missing_tuple = tuple(sorted(missing))
    return {
        "provider": provider.provider,
        "provider_family": provider.provider_family,
        "shadow": provider.shadow,
        "method": request.method,
        "run_id": request.run_id,
        "request_id": request.request_id,
        "requested_fields": list(request.fields),
        "requested_fields_hash": request.fields_hash,
        "requested_tickers": list(request.tickers),
        "batch_size": len(request.tickers),
        "call_count": call_count,
        "returned_tickers": list(returned_tuple),
        "missing_tickers": list(missing_tuple),
        "ticker_set_hash": request.ticker_set_hash,
        "response_hash": response_hash,
        "status_summary": dict(status_summary),
        "reason": _redact(reason) if reason else None,
    }
