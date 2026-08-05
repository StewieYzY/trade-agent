from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.canonical_snapshot import (  # noqa: E402
    SnapshotError,
    build_snapshot,
    read_snapshot,
    write_snapshot,
)


def _evidence(
    *,
    ticker: str = "600519.SH",
    value: float | None = 123.4,
    provider: str = "fixture",
    eligibility: str = "production_eligible",
    status: str = "available",
    response_hash: str = "a" * 64,
    retrieved_at: str = "2026-08-04T09:00:00+00:00",
):
    return {
        "provider_family": "baseline",
        "provider": provider,
        "method": "quote",
        "market": "SH",
        "ticker": ticker,
        "field": "last_price",
        "raw_field": "最新价",
        "value": value,
        "unit": "CNY/share",
        "currency": "CNY",
        "as_of": "2026-08-04",
        "report_period": None,
        "status": status,
        "eligibility": eligibility,
        "response_hash": response_hash,
        "retrieved_at": retrieved_at,
        "provenance": {
            "provider_family": "baseline",
            "provider": provider,
            "method": "quote",
            "market": "SH",
            "ticker": ticker,
            "raw_field": "最新价",
            "response_hash": response_hash,
            "retrieved_at": retrieved_at,
        },
    }


def test_production_eligible_value_enters_canonical_record():
    snapshot = build_snapshot(
        [_evidence()],
        tickers=["600519"],
        plan_version="test-v1",
        run_id="run-a",
    )

    assert snapshot["records"]["600519.SH"]["last_price"] == 123.4
    assert snapshot["conflict_count"] == 0
    assert snapshot["source_set_hash"]


@pytest.mark.parametrize("eligibility", ["not_qualified", "shadow_only"])
def test_unqualified_value_is_visible_but_not_consumable(eligibility):
    snapshot = build_snapshot(
        [_evidence(eligibility=eligibility)],
        tickers=["600519.SH"],
        plan_version="test-v1",
        run_id="run-b",
    )

    assert snapshot["records"]["600519.SH"]["last_price"] is None
    assert snapshot["provenance"][0]["canonical_consumable"] is False


def test_conflict_preserves_evidence_and_nulls_canonical_value():
    snapshot = build_snapshot(
        [
            _evidence(provider="a", response_hash="a" * 64, value=123.4),
            _evidence(provider="b", response_hash="b" * 64, value=130.0),
        ],
        tickers=["600519.SH"],
        plan_version="test-v1",
        run_id="run-c",
    )

    assert snapshot["conflict_count"] >= 1
    assert snapshot["records"]["600519.SH"]["last_price"] is None
    assert len(snapshot["provenance"]) == 2


def test_writer_is_immutable_and_reader_round_trips(tmp_path):
    run_dir = write_snapshot(
        [_evidence()],
        tickers=["600519.SH"],
        plan_version="test-v1",
        output_root=tmp_path,
        run_id="immutable-run",
    )
    loaded = read_snapshot(run_dir)

    assert loaded["manifest"]["source_set_hash"]
    assert loaded["records"]["600519.SH"]["last_price"] == 123.4
    with pytest.raises(SnapshotError, match="already exists"):
        write_snapshot(
            [_evidence()],
            tickers=["600519.SH"],
            plan_version="test-v1",
            output_root=tmp_path,
            run_id="immutable-run",
        )


def test_snapshot_does_not_touch_legacy_cache(tmp_path):
    legacy = tmp_path / "data" / "cache" / "600519" / "basic.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"price": 1}), encoding="utf-8")

    write_snapshot(
        [_evidence()],
        tickers=["600519.SH"],
        plan_version="test-v1",
        output_root=tmp_path / "snapshots",
        run_id="isolated-run",
    )

    assert json.loads(legacy.read_text()) == {"price": 1}


def test_single_stale_production_evidence_is_not_canonical_consumable():
    snapshot = build_snapshot(
        [_evidence(retrieved_at="a" * 64)],
        tickers=["600519.SH"],
        plan_version="test-v1",
        run_id="single-stale",
        freshness_seconds=60,
    )

    assert snapshot["records"]["600519.SH"]["last_price"] is None
    assert any(
        conflict["kind"] == "freshness"
        for conflict in snapshot["conflicts"]
    )
