"""f3f historical R1 crosstalk failure-repro harness tests.

覆盖：冻结失败快照的 ticker/source hash/fixture hash/run_id fail-closed、
显性串台 fixture 回放、历史 insufficient_data 输入 dry-run fail-closed，
以及 fixture/dry-run 与 live 复现的边界。

不执行真实 LLM 调用。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.repro_out.f3f_failure_repro_exp import (
    EXPECTED_FIXTURE_SHA256_BY_TICKER,
    create_failure_repro_envelope,
    load_verified_failure_snapshot,
    reproduce_explicit_crosstalk,
    run_fixture_diagnosis,
    run_mismatch_fail_closed,
    verify_historical_input_path,
    write_f3f_report,
)


REPRO_DIR = Path(__file__).resolve().parent.parent / "scripts/repro_out"
SOURCE_SHA256 = "244d063bbbf152621008b1d9606890cd84f3ad81e128755e73e53cdd89be7d4b"
MODEL_CONFIGURATION = {
    "heavy_model": "deepseek-v4-pro",
    "moderate_model": "deepseek-v4-flash",
    "reasoning_levels": ["heavy", "moderate"],
}


def _snapshot(ticker: str) -> dict:
    path = REPRO_DIR / f"f3f_{ticker}_failure_snapshot.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict, name: str = "snapshot.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class TestFrozenSnapshotLoad:
    def test_load_accepts_frozen_600519(self, tmp_path: Path):
        snapshot = load_verified_failure_snapshot(
            _write(tmp_path, _snapshot("600519")),
            expected_ticker="600519.SH",
            source_root=REPRO_DIR,
        )

        assert snapshot["freeze"]["canonical_ticker"] == "600519.SH"
        assert snapshot["freeze"]["source_sha256"] == SOURCE_SHA256

    def test_load_rejects_wrong_ticker(self, tmp_path: Path):
        snapshot = _snapshot("600519")
        snapshot["freeze"]["canonical_ticker"] = "600900.SH"

        with pytest.raises(ValueError, match="600519.SH"):
            load_verified_failure_snapshot(
                _write(tmp_path, snapshot, "wrong.json"),
                expected_ticker="600519.SH",
                source_root=REPRO_DIR,
            )

    def test_load_rejects_missing_freeze(self, tmp_path: Path):
        snapshot = _snapshot("600519")
        snapshot.pop("freeze")

        with pytest.raises(ValueError, match="freeze"):
            load_verified_failure_snapshot(
                _write(tmp_path, snapshot, "nofreeze.json"),
                expected_ticker="600519.SH",
                source_root=REPRO_DIR,
            )

    def test_load_rejects_source_hash_mismatch(self, tmp_path: Path):
        snapshot = _snapshot("600519")
        snapshot["input_snapshot"]["guard"] = "tampered"

        with pytest.raises(ValueError, match="source"):
            load_verified_failure_snapshot(
                _write(tmp_path, snapshot, "tampered-source.json"),
                expected_ticker="600519.SH",
                source_root=REPRO_DIR,
            )

    def test_load_rejects_wrong_source_hash(self, tmp_path: Path):
        snapshot = _snapshot("600519")
        snapshot["freeze"]["source_sha256"] = "0" * 64

        with pytest.raises(ValueError, match="source"):
            load_verified_failure_snapshot(
                _write(tmp_path, snapshot, "wrong-source.json"),
                expected_ticker="600519.SH",
                source_root=REPRO_DIR,
            )


class TestEnvelopeIdentity:
    def test_envelope_binds_ticker_run_id_and_hashes(self, tmp_path: Path):
        snapshot = _snapshot("600519")

        envelope = create_failure_repro_envelope(
            snapshot,
            "600519.SH",
            "run-123",
            tmp_path / "out",
            MODEL_CONFIGURATION,
        )

        assert envelope["canonical_ticker"] == "600519.SH"
        assert envelope["run_id"] == "run-123"
        assert envelope["source_sha256"] == SOURCE_SHA256
        assert envelope["fixture_sha256"] == EXPECTED_FIXTURE_SHA256_BY_TICKER["600519.SH"]
        assert envelope["input_snapshot_sha256"] == SOURCE_SHA256
        assert envelope["output_root"] == (tmp_path / "out").resolve()


class TestMismatchFailClosed:
    def test_mismatch_branch_fails_closed_without_llm(self, tmp_path: Path):
        with patch(
            "scripts.repro_out.f3f_failure_repro_exp.call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            result = run_mismatch_fail_closed(
                _snapshot("600519"),
                "600519.SH",
                "run-123",
                tmp_path / "out",
                MODEL_CONFIGURATION,
            )

        mock_llm.assert_not_awaited()
        assert result["status"] == "fail_closed_ok"
        assert {case["case"] for case in result["mismatch_cases"]} >= {
            "ticker_mismatch",
            "source_hash_mismatch",
            "fixture_hash_mismatch",
            "run_id_mismatch",
            "freeze_missing",
        }
        assert all(case["status"] == "fail_closed" for case in result["mismatch_cases"])


class TestReproduceCrosstalk:
    def test_600519_four_agent_ring_is_reproduced(self):
        result = reproduce_explicit_crosstalk(_snapshot("600519"))

        assert result["reproduced"] is True
        assert result["explicit_crosstalk_rate"] == 1.0
        assert len(result["per_agent"]) == 4
        assert all(item["circular_reference_detected"] for item in result["per_agent"])

    def test_600900_single_agent_munger_reference_is_reproduced(self):
        result = reproduce_explicit_crosstalk(_snapshot("600900"))

        assert result["reproduced"] is True
        assert result["explicit_crosstalk_rate"] == 1.0
        assert len(result["per_agent"]) == 1
        assert result["per_agent"][0]["agent"] == "buffett"
        assert result["per_agent"][0]["circular_reference_detected"] is True


class TestHistoricalInputPath:
    @pytest.mark.parametrize("ticker", ["600519", "600900"])
    def test_insufficient_data_input_fail_closed(self, ticker: str):
        result = verify_historical_input_path(_snapshot(ticker), f"{ticker}.SH")

        assert result["status"] == "fail_closed_ok"
        assert result["llm_reachable"] is False
        assert "insufficient_data" in result["reason"]


class TestDiagnosisBoundary:
    def test_fixture_diagnosis_records_root_cause_and_residual_risks(self, tmp_path: Path):
        with patch(
            "scripts.repro_out.f3f_failure_repro_exp.call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            result = run_fixture_diagnosis(
                _snapshot("600519"),
                "600519.SH",
                "run-123",
                tmp_path / "out",
                MODEL_CONFIGURATION,
            )

        mock_llm.assert_not_awaited()
        assert result["mode"] == "fixture_dry_run"
        assert result["crosstalk"]["reproduced"] is True
        assert result["input_path"]["llm_reachable"] is False
        assert result["conclusion"]["status"] == "root_cause_located"
        assert any("live" in risk for risk in result["residual_risks"])
        assert any("implicit" in risk for risk in result["residual_risks"])


class TestReport:
    def test_report_lists_boundary_and_does_not_claim_g2_pass(self, tmp_path: Path):
        payload = {
            "mode": "fixture_dry_run",
            "canonical_ticker": "600519.SH",
            "run_id": "run-123",
            "conclusion": {"status": "root_cause_located"},
            "residual_risks": [
                "live LLM reproduction not authorized",
                "implicit crosstalk escape remains",
            ],
        }

        report = write_f3f_report(tmp_path, payload)

        assert "fixture" in report
        assert "live" in report
        assert "implicit" in report
        assert "G2" in report
        assert "capability passed" not in report
        assert (tmp_path / "f3f_failure_repro_report.md").exists()
