"""f3e input-assembly hypothesis harness tests.

覆盖：frozen dossier 的 canonical ticker / source hash / run_id 绑定、
ticker/dossier/run_id mismatch 在 LLM 前 fail-closed、角色分发 vs 全员共享
user message 装配差异、per-agent 指标契约与报告边界。

不执行真实 LLM 调用（未授权时不得触发 provider/LLM Gate）。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.schema import AgentOutput, CouncilResult
from data.lib.audit_chain import payload_sha256
from scripts.repro_out.f3e_input_assembly_exp import (
    AGENT_IDS,
    BRANCHES,
    build_branch_user_message,
    compute_branch_metrics,
    create_run_envelope,
    load_verified_dossier,
    run_live_experiment,
    run_mismatch_fail_closed,
    run_orchestration_branch,
    write_f3e_report,
)


SOURCE_SHA256 = "f588d5bf911aefd90348d9a7d150280847b9af938bf5b06d8548a3afeb2a00c9"
FROZEN_DOSSIER_PATH = (
    Path(__file__).resolve().parent.parent / "scripts/repro_out/600009_frozen_dossier.json"
)
MODEL_CONFIGURATION = {
    "heavy_model": "deepseek-v4-pro",
    "moderate_model": "deepseek-v4-flash",
    "reasoning_levels": ["heavy", "moderate"],
}


def _frozen_dossier() -> dict:
    """Return the tracked provider-frozen 600009.SH dossier (f3c source hash)."""
    return json.loads(FROZEN_DOSSIER_PATH.read_text(encoding="utf-8"))


def _write_dossier(tmp_path: Path, dossier: dict, name: str = "dossier.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(dossier), encoding="utf-8")
    return path


def _agent(agent_id: str, core_thesis: str = "独立判断") -> AgentOutput:
    return AgentOutput(
        name=agent_id,
        signal="bullish",
        conviction=75,
        core_thesis=core_thesis,
        what_would_change_my_mind="业绩下滑",
        out_of_circle=False,
    )


class TestFrozenDossierEnvelope:
    def test_load_verified_dossier_accepts_frozen_600009(self, tmp_path: Path):
        path = _write_dossier(tmp_path, _frozen_dossier())

        dossier = load_verified_dossier(path)

        assert dossier["freeze"]["canonical_ticker"] == "600009.SH"
        assert dossier["freeze"]["source_sha256"] == SOURCE_SHA256

    def test_load_verified_dossier_rejects_wrong_ticker(self, tmp_path: Path):
        dossier = _frozen_dossier()
        dossier["core_snapshot"]["ticker"] = "600519.SH"
        dossier["freeze"]["canonical_ticker"] = "600519.SH"

        with pytest.raises(ValueError, match="600009.SH"):
            load_verified_dossier(_write_dossier(tmp_path, dossier, "wrong.json"))

    def test_load_verified_dossier_rejects_missing_freeze(self, tmp_path: Path):
        dossier = _frozen_dossier()
        dossier.pop("freeze")

        with pytest.raises(ValueError, match="freeze"):
            load_verified_dossier(_write_dossier(tmp_path, dossier, "nofreeze.json"))

    def test_create_run_envelope_binds_run_id_and_input_hash(self, tmp_path: Path):
        dossier = _frozen_dossier()

        envelope = create_run_envelope(
            dossier,
            "run-123",
            tmp_path / "out",
            MODEL_CONFIGURATION,
        )

        assert envelope["canonical_ticker"] == "600009.SH"
        assert envelope["run_id"] == "run-123"
        assert envelope["identity"].input_hash == payload_sha256(dossier)
        assert envelope["source_sha256"] == SOURCE_SHA256


class TestMismatchFailClosed:
    def test_mismatch_branch_fails_closed_without_llm(self, tmp_path: Path):
        with patch(
            "scripts.repro_out.f3e_input_assembly_exp.call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            result = run_mismatch_fail_closed(
                _frozen_dossier(),
                "run-123",
                tmp_path / "out",
                MODEL_CONFIGURATION,
            )

        mock_llm.assert_not_awaited()
        assert result["branch"] == "mismatch_fail_closed"
        assert result["status"] == "fail_closed_ok"
        assert {case["case"] for case in result["mismatch_cases"]} >= {
            "ticker_mismatch",
            "dossier_hash_mismatch",
            "run_id_mismatch",
            "freeze_missing",
            "source_hash_mismatch",
            "dossier_content_tamper",
        }
        assert all(case["status"] == "fail_closed" for case in result["mismatch_cases"])


class TestBranchAssembly:
    def test_role_distribution_and_all_shared_differ(self):
        dossier = _frozen_dossier()

        role = build_branch_user_message(
            "600009.SH", dossier, "buffett", "role_distribution"
        )
        shared = build_branch_user_message(
            "600009.SH", dossier, "buffett", "all_shared"
        )

        assert role != shared
        assert "consensus_eps" not in role
        assert "consensus_eps" in shared


class TestMetrics:
    def test_metrics_include_per_agent_input_consistency(self):
        dossier = _frozen_dossier()
        outputs = [_agent("buffett"), _agent("munger")]
        records = [
            {
                "agent": "buffett",
                "run_id": "r1",
                "dossier_sha256": payload_sha256(dossier),
                "canonical_ticker": "600009.SH",
                "model": "m",
                "status": "ok",
            },
            {
                "agent": "munger",
                "run_id": "r1",
                "dossier_sha256": payload_sha256(dossier),
                "canonical_ticker": "600009.SH",
                "model": "m",
                "status": "ok",
            },
        ]

        metrics = compute_branch_metrics(
            outputs, dossier, records, run_id="r1", model="m"
        )

        assert metrics["input_consistency"] == 1.0
        assert "mean_distance" in metrics["citation_divergence"]
        assert "explicit_crosstalk_rate" in metrics
        assert "implicit_crosstalk_rate" in metrics
        assert "grounding_unverified_rate" in metrics

        mismatched = [dict(record, run_id="other") for record in records]
        assert (
            compute_branch_metrics(
                outputs, dossier, mismatched, run_id="r1", model="m"
            )["input_consistency"]
            == 0.0
        )


class TestReport:
    def test_report_lists_four_branches_and_boundary(self, tmp_path: Path):
        payload = {
            "mode": "live",
            "run_id": "r1",
            "canonical_ticker": "600009.SH",
            "source_sha256": SOURCE_SHA256,
            "profile_version": "g2-council-v1",
            "prompt_version": "council-prompt-v1",
            "model_configuration": {"heavy_model": "deepseek-v4-pro"},
            "branches": {
                "role_distribution": {
                    "status": "complete",
                    "metrics": {
                        "explicit_crosstalk_rate": 0.0,
                        "implicit_crosstalk_rate": 0.0,
                        "grounding_unverified_rate": 0.0,
                        "citation_divergence": {"mean_distance": 0.5},
                        "input_consistency": 1.0,
                    },
                },
                "all_shared": {
                    "status": "complete",
                    "metrics": {
                        "explicit_crosstalk_rate": 0.0,
                        "implicit_crosstalk_rate": 0.0,
                        "grounding_unverified_rate": 0.0,
                        "citation_divergence": {"mean_distance": 0.6},
                        "input_consistency": 1.0,
                    },
                },
                "mismatch_fail_closed": {
                    "status": "fail_closed_ok",
                    "mismatch_cases": [
                        {"case": "ticker_mismatch", "status": "fail_closed"}
                    ],
                },
                "existing_orchestration": {
                    "status": "incomplete",
                    "metrics": {"input_consistency": 0.0},
                    "evidence_gaps": ["raw R1 response not exposed by run_debate"],
                },
            },
        }

        report = write_f3e_report(tmp_path, payload)

        assert all(branch in report for branch in BRANCHES)
        assert "G2" in report
        assert "repair" in report
        assert "grounding_unverified" in report
        assert (tmp_path / "f3e_input_assembly_report.md").exists()


class TestLiveGate:
    def test_live_requires_explicit_authorization(self, tmp_path: Path):
        dossier_path = _write_dossier(tmp_path, _frozen_dossier())
        env = tmp_path / ".env"
        env.write_text(
            "LLM_API_KEY=x\nLLM_API_BASE=http://example\n"
            "LLM_MODEL=weak\nLLM_MODEL_HEAVY=strong\n"
            "LLM_MODEL_MODERATE=mid\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="authoriz"):
            asyncio.run(
                run_live_experiment(
                    tmp_path / "out", env, dossier_path, authorize_live=False
                )
            )

    def test_live_requires_verified_dossier_before_llm(self, tmp_path: Path):
        env = tmp_path / ".env"
        env.write_text(
            "LLM_API_KEY=x\nLLM_API_BASE=http://example\n"
            "LLM_MODEL=weak\nLLM_MODEL_HEAVY=strong\n"
            "LLM_MODEL_MODERATE=mid\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="dossier"):
            asyncio.run(
                run_live_experiment(
                    tmp_path / "out",
                    env,
                    tmp_path / "missing.json",
                    authorize_live=True,
                )
            )


class TestOrchestrationEvidenceGap:
    @pytest.mark.anyio
    async def test_preflight_failure_recorded_as_evidence_gap(self, tmp_path: Path):
        dossier = _frozen_dossier()
        envelope = create_run_envelope(
            dossier,
            "run-orch-gap",
            tmp_path / "out",
            MODEL_CONFIGURATION,
        )

        with patch(
            "scripts.repro_out.f3e_input_assembly_exp.run_debate",
            side_effect=ValueError(
                "insufficient_data: core_snapshot missing required facts "
                "['roe_3y', 'net_margin']"
            ),
        ):
            branch = await run_orchestration_branch(envelope)

        assert branch["status"] == "incomplete"
        assert branch["evidence_gaps"]
        assert "roe_3y" in branch["evidence_gaps"][0]
        assert branch["records"] == []

    @pytest.mark.anyio
    async def test_orchestration_success_reads_prompt_artifact(self, tmp_path: Path):
        import council.debate as debate_module

        dossier = _frozen_dossier()
        envelope = create_run_envelope(
            dossier,
            "run-orch-ok",
            tmp_path / "out",
            MODEL_CONFIGURATION,
        )
        identity = envelope["identity"]
        run_root = tmp_path / "out" / "audit" / identity.run_id
        run_root.mkdir(parents=True)
        prompts = []
        for agent_id in AGENT_IDS:
            user = build_branch_user_message(
                "600009.SH", dossier, agent_id, "role_distribution"
            )
            prompts.append(
                {
                    "agent": agent_id,
                    "stage": "r1",
                    "round": "heavy",
                    "system_prompt": "sp",
                    "user_message": user,
                }
            )
        (run_root / "02-prompt.json").write_text(
            json.dumps({"payload": {"prompts": prompts}}), encoding="utf-8"
        )

        async def fake_run_debate(ticker, **kwargs):
            for agent_id in AGENT_IDS:
                user = build_branch_user_message(
                    ticker, dossier, agent_id, "role_distribution"
                )
                await debate_module.call_llm(
                    "sp", user, "heavy", model=MODEL_CONFIGURATION["heavy_model"]
                )
            return CouncilResult(
                ticker=ticker,
                round1=[_agent(agent_id) for agent_id in AGENT_IDS],
                final_verdict="bullish",
            )

        with patch(
            "scripts.repro_out.f3e_input_assembly_exp.run_debate",
            side_effect=fake_run_debate,
        ), patch(
            "council.debate.call_llm",
            new_callable=AsyncMock,
            return_value=(
                '{"signal":"bullish","conviction":75,"core_thesis":"独立判断",'
                '"what_would_change_my_mind":"x","out_of_circle":false}',
                {"total_tokens": 10},
            ),
        ):
            branch = await run_orchestration_branch(envelope)

        assert branch["status"] == "complete"
        assert len(branch["records"]) == len(AGENT_IDS)
        assert all(record["status"] == "ok" for record in branch["records"])
        assert branch["input_assembly_mismatches"] == []
        assert branch["evidence_gaps"] == []

    @pytest.mark.anyio
    async def test_orchestration_input_mismatch_marks_incomplete(self, tmp_path: Path):
        import council.debate as debate_module

        dossier = _frozen_dossier()
        envelope = create_run_envelope(
            dossier,
            "run-orch-mismatch",
            tmp_path / "out",
            MODEL_CONFIGURATION,
        )
        identity = envelope["identity"]
        run_root = tmp_path / "out" / "audit" / identity.run_id
        run_root.mkdir(parents=True)
        prompts = []
        for agent_id in AGENT_IDS:
            user = build_branch_user_message(
                "600009.SH", dossier, agent_id, "role_distribution"
            )
            if agent_id == "buffett":
                user = user + " EXTRA"
            prompts.append(
                {
                    "agent": agent_id,
                    "stage": "r1",
                    "round": "heavy",
                    "system_prompt": "sp",
                    "user_message": user,
                }
            )
        (run_root / "02-prompt.json").write_text(
            json.dumps({"payload": {"prompts": prompts}}), encoding="utf-8"
        )

        async def fake_run_debate(ticker, **kwargs):
            for agent_id in AGENT_IDS:
                user = build_branch_user_message(
                    ticker, dossier, agent_id, "role_distribution"
                )
                await debate_module.call_llm(
                    "sp", user, "heavy", model=MODEL_CONFIGURATION["heavy_model"]
                )
            return CouncilResult(
                ticker=ticker,
                round1=[_agent(agent_id) for agent_id in AGENT_IDS],
                final_verdict="bullish",
            )

        with patch(
            "scripts.repro_out.f3e_input_assembly_exp.run_debate",
            side_effect=fake_run_debate,
        ), patch(
            "council.debate.call_llm",
            new_callable=AsyncMock,
            return_value=(
                '{"signal":"bullish","conviction":75,"core_thesis":"独立判断",'
                '"what_would_change_my_mind":"x","out_of_circle":false}',
                {"total_tokens": 10},
            ),
        ):
            branch = await run_orchestration_branch(envelope)

        assert branch["status"] == "incomplete"
        assert branch["input_assembly_mismatches"]

    @pytest.mark.anyio
    async def test_orchestration_missing_prompt_artifact_records_gap(self, tmp_path: Path):
        dossier = _frozen_dossier()
        envelope = create_run_envelope(
            dossier,
            "run-orch-noartifact",
            tmp_path / "out",
            MODEL_CONFIGURATION,
        )

        async def fake_run_debate(ticker, **kwargs):
            return CouncilResult(
                ticker=ticker,
                round1=[_agent(agent_id) for agent_id in AGENT_IDS],
                final_verdict="bullish",
            )

        with patch(
            "scripts.repro_out.f3e_input_assembly_exp.run_debate",
            side_effect=fake_run_debate,
        ):
            branch = await run_orchestration_branch(envelope)

        assert branch["status"] == "incomplete"
        assert any(
            "prompt artifact missing" in gap for gap in branch["evidence_gaps"]
        )

    @pytest.mark.anyio
    async def test_orchestration_raw_not_exposed_marks_incomplete(self, tmp_path: Path):
        dossier = _frozen_dossier()
        envelope = create_run_envelope(
            dossier,
            "run-orch-noraw",
            tmp_path / "out",
            MODEL_CONFIGURATION,
        )
        identity = envelope["identity"]
        run_root = tmp_path / "out" / "audit" / identity.run_id
        run_root.mkdir(parents=True)
        prompts = []
        for agent_id in AGENT_IDS:
            user = build_branch_user_message(
                "600009.SH", dossier, agent_id, "role_distribution"
            )
            prompts.append(
                {
                    "agent": agent_id,
                    "stage": "r1",
                    "round": "heavy",
                    "system_prompt": "sp",
                    "user_message": user,
                }
            )
        (run_root / "02-prompt.json").write_text(
            json.dumps({"payload": {"prompts": prompts}}), encoding="utf-8"
        )

        async def fake_run_debate(ticker, **kwargs):
            # 不调用 call_llm → raw_by_prompt_hash 为空 → raw not exposed evidence gap。
            return CouncilResult(
                ticker=ticker,
                round1=[_agent(agent_id) for agent_id in AGENT_IDS],
                final_verdict="bullish",
            )

        with patch(
            "scripts.repro_out.f3e_input_assembly_exp.run_debate",
            side_effect=fake_run_debate,
        ):
            branch = await run_orchestration_branch(envelope)

        assert branch["status"] == "incomplete"
        assert any(
            "raw R1 response not exposed" in gap for gap in branch["evidence_gaps"]
        )
