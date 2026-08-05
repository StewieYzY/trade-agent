from __future__ import annotations

import os
import time
from typing import Any

from scripts.provider_qualification import ProviderAdapter, ProbeCase


def _payload(case: ProbeCase) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    field_meta: dict[str, dict[str, str]] = {}
    for field in case.fields:
        if field in {"last_price", "pe_ttm", "pb"}:
            payload[field] = 1.0
            field_meta[field] = {
                "unit": "multiple",
                "as_of": "2026-08-05",
            }
        else:
            payload[field] = f"fixture-{field}"
            field_meta[field] = {"as_of": "2026-08-05"}
    payload["_fields"] = field_meta
    return payload


def _fast(case: ProbeCase) -> dict[str, Any]:
    return _payload(case)


def _slow(case: ProbeCase) -> dict[str, Any]:
    time.sleep(float(os.environ.get("PROVIDER_HEALTH_SLEEP_SECONDS", "1")))
    return _payload(case)


def _interruptible(_case: ProbeCase) -> dict[str, Any]:
    while True:
        time.sleep(0.01)


def _crashing(_case: ProbeCase) -> dict[str, Any]:
    os._exit(17)


def _failing(_case: ProbeCase) -> dict[str, Any]:
    raise RuntimeError(
        "Authorization: Bearer secret-token "
        "https://user:pass@example.com"
    )


def _secret_payload(_case: ProbeCase) -> dict[str, Any]:
    return {
        "data": {
            "last_price": 1.0,
            "_fields": {
                "last_price": {
                    "unit": "CNY/share",
                    "as_of": "2026-08-05",
                }
            },
        },
        "_meta": {
            "Authorization": "Bearer secret-token",
            "access_token": "secret-token",
            "endpoint": "https://user:pass@example.com",
        },
    }


def _large_payload(_case: ProbeCase) -> dict[str, Any]:
    return {
        "data": {
            "last_price": 1.0,
            "_fields": {
                "last_price": {
                    "unit": "CNY/share",
                    "as_of": "2026-08-05",
                }
            },
        },
        "_meta": {
            "diagnostic": "x" * 500_000,
        },
    }


def get_provider_adapters() -> list[ProviderAdapter]:
    mode = os.environ.get("PROVIDER_HEALTH_MODE", "fast")
    if mode == "factory_failure":
        raise RuntimeError("factory failed with secret-token")
    if mode == "factory_hang":
        time.sleep(float(os.environ.get("PROVIDER_HEALTH_SLEEP_SECONDS", "1")))
        mode = "fast"
    invoke = {
        "fast": _fast,
        "slow": _slow,
        "interruptible": _interruptible,
        "crashing": _crashing,
        "failing": _failing,
        "secret_payload": _secret_payload,
        "large_payload": _large_payload,
    }.get(mode)
    if mode == "empty":
        return []
    if invoke is None:
        raise ValueError(f"unknown provider health fixture mode: {mode}")
    return [ProviderAdapter("fixture", "provider-health", invoke=invoke)]
