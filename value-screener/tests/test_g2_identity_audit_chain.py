from __future__ import annotations

import asyncio
import json
import os
from datetime import date

import pytest

from council import fallback
from council import debate
from council.schema import AgentOutput
from data.lib import audit_chain
from data.lib.audit_chain import (
    AuditIdentity,
    AuditIdentityError,
    AuditChainWriter,
    create_audit_identity,
    payload_sha256,
    verify_audit_chain,
)


def _fallback_dossier() -> dict:
    return {
        "core_snapshot": {
            "ticker": "600009.SH",
            "name": "测试公司",
            "market_cap": 1_000_000_000,
            "pe_ttm": 20.0,
            "roe_3y": [10.0, 11.0, 12.0],
            "net_margin": 8.0,
        },
        "research_dossier": {
            "main_business": {"by_industry": [{"industry": "测试行业"}]},
            "peers": {"peer_avg_pe": 22.0},
            "research": {"consensus_eps": 1.2},
        },
    }


def _artifact_payload(identity, **extra) -> dict:
    payload = {
        "ticker": identity.canonical_ticker,
        "run_id": identity.run_id,
        "profile_version": identity.profile_version,
        "input_hash": identity.input_hash,
        "dossier_snapshot": identity.dossier_snapshot,
        "prompt_version": identity.prompt_version,
        "model_configuration": identity.model_configuration,
    }
    payload.update(extra)
    return payload


def _artifact_payload_for_type(identity, artifact_type: str, dossier: dict) -> dict:
    prompt_records = [
        {
            "agent": "fixture",
            "stage": "r1",
            "round": "heavy",
            "system_prompt": "system",
            "user_message": "user",
        }
    ]
    content = {
        "dossier": {
            "dossier": dossier,
            "dossier_sha256": payload_sha256(dossier),
        },
        "prompt": {
            "prompts": prompt_records,
            "prompt_binding_sha256": payload_sha256(
                {
                    "ticker": identity.canonical_ticker,
                    "run_id": identity.run_id,
                    "profile_version": identity.profile_version,
                    "input_hash": identity.input_hash,
                    "dossier_snapshot": identity.dossier_snapshot,
                    "prompt_version": identity.prompt_version,
                    "model_configuration": identity.model_configuration,
                    "prompts": prompt_records,
                }
            ),
        },
        "debate": {
            "debate_text": "## Round 1\nfixture debate",
            "debate_text_sha256": payload_sha256("## Round 1\nfixture debate"),
        },
        "quality_report": {"quality_status": "passed"},
        "final_result": {
            "result": _artifact_payload(
                identity,
                status="passed",
            ),
            "result_sha256": payload_sha256(
                _artifact_payload(
                    identity,
                    status="passed",
                )
            ),
        },
    }
    return _artifact_payload(identity, **content[artifact_type])


def _recorded_agent(output):
    async def fake_agent(*_args, **kwargs):
        prompt_recorder = kwargs.get("prompt_recorder")
        if prompt_recorder is not None:
            prompt_recorder.append(
                {
                    "agent": "buffett",
                    "stage": kwargs["prompt_stage"],
                    "round": kwargs["reasoning_level"],
                    "system_prompt": "fixture system",
                    "user_message": "fixture user",
                }
            )
        return output

    return fake_agent


def test_fallback_audit_uses_shared_identity_and_writes_full_chain(tmp_path, monkeypatch):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0", "ROE 12.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    async def fake_call(*_args, **_kwargs):
        return output.to_json(), {}

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009",
            features=_fallback_dossier(),
            output_root=tmp_path / "fallback",
            audit_root=tmp_path / "audit",
            run_id="fallback-a",
            model="fixture-model",
        )
    )

    assert result["audit_identity"]["canonical_ticker"] == "600009.SH"
    manifest = verify_audit_chain(tmp_path / "audit" / "fallback-a")
    assert manifest["identity"]["run_id"] == "fallback-a"
    persisted = json.loads((tmp_path / "fallback" / "fallback-a" / "result.json").read_text())
    assert persisted["run_id"] == manifest["identity"]["run_id"]
    debate_payload = json.loads(
        (tmp_path / "audit" / "fallback-a" / "03-debate.json").read_text()
    )["payload"]
    assert debate_payload["response"]
    assert debate_payload["agent_output"]


def test_fallback_debate_evidence_is_persisted_and_hash_bound(tmp_path, monkeypatch):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    async def fake_call(*_args, **_kwargs):
        return output.to_json(), {}

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")

    asyncio.run(
        fallback.run_fallback(
            ticker="600009",
            features=_fallback_dossier(),
            output_root=tmp_path / "fallback",
            audit_root=tmp_path / "audit",
            run_id="fallback-a",
            model="fixture-model",
        )
    )
    debate_path = tmp_path / "audit" / "fallback-a" / "03-debate.json"
    debate_artifact = json.loads(debate_path.read_text())
    debate_artifact["payload"]["response"] = "tampered"
    debate_path.write_text(json.dumps(debate_artifact))

    with pytest.raises(AuditIdentityError, match="payload hash"):
        verify_audit_chain(tmp_path / "audit" / "fallback-a")


def test_fallback_rejects_mismatched_identity_before_creating_run_dir(tmp_path):
    identity = create_audit_identity(
        "600009.SH",
        dossier=_fallback_dossier(),
        profile_version="g2-fallback-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="other-run",
    )

    with pytest.raises(AuditIdentityError, match="run_id"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009.SH",
                features=_fallback_dossier(),
                output_root=tmp_path / "fallback",
                audit_identity=identity,
                run_id="requested-run",
                model="fixture-model",
            )
        )

    assert not (tmp_path / "fallback" / "requested-run").exists()


def test_fallback_writer_setup_failure_records_failed_runtime_manifest(
    tmp_path, monkeypatch
):
    class FailingAuditWriter:
        def __init__(self, *_args, **_kwargs):
            raise OSError("audit root unavailable")

    monkeypatch.setattr(fallback, "AuditChainWriter", FailingAuditWriter)

    with pytest.raises(OSError, match="audit root unavailable"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009.SH",
                features=_fallback_dossier(),
                output_root=tmp_path / "fallback",
                audit_root=tmp_path / "audit",
                run_id="writer-init-failure",
                model="fixture-model",
            )
        )

    run_dir = tmp_path / "fallback" / "writer-init-failure"
    runtime_manifest = json.loads((run_dir / "manifest.json").read_text())
    assert runtime_manifest["state"] == "failed"
    assert not (tmp_path / "audit" / ".staging" / "writer-init-failure").exists()


def test_direct_audit_identity_rejects_path_traversal_run_id():
    with pytest.raises(AuditIdentityError, match="run_id"):
        AuditIdentity(
            canonical_ticker="600009.SH",
            run_id="../../../outside-audit-root",
            profile_version="g2-fallback-v1",
            input_hash=payload_sha256(_fallback_dossier()),
            dossier_snapshot="dossier-1",
            prompt_version="council-prompt-v1",
            model_configuration={"model": "fixture-model"},
        )


def test_create_identity_requires_canonical_dossier_ticker():
    with pytest.raises(AuditIdentityError, match="dossier ticker"):
        create_audit_identity(
            "600009.SH",
            dossier={"snapshot_version": "dossier-1"},
            profile_version="g2-fallback-v1",
            prompt_version="council-prompt-v1",
            model_configuration={"model": "fixture-model"},
        )


def test_shared_dossier_artifact_rejects_nested_ticker_conflict(tmp_path):
    dossier = {
        "core_snapshot": {"ticker": "600009.SH"},
        "research_dossier": {"ticker": "600519.SH"},
    }
    identity = create_audit_identity(
        "600009.SH",
        dossier={"core_snapshot": {"ticker": "600009.SH"}},
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )

    with pytest.raises(AuditIdentityError, match="dossier ticker"):
        AuditChainWriter(tmp_path, identity).write(
            "dossier",
            _artifact_payload(
                identity,
                dossier=dossier,
                dossier_sha256=payload_sha256(dossier),
            ),
        )


def test_fallback_validates_supplied_identity_before_resolving_run_dir(
    tmp_path, monkeypatch
):
    identity = object.__new__(AuditIdentity)
    for field, value in {
        "canonical_ticker": "600009.SH",
        "run_id": "../../../outside-audit-root",
        "profile_version": "g2-fallback-v1",
        "input_hash": payload_sha256(_fallback_dossier()),
        "dossier_snapshot": "dossier-1",
        "prompt_version": "council-prompt-v1",
        "model_configuration": {"model": "fixture-model", "reasoning_level": "heavy"},
    }.items():
        object.__setattr__(identity, field, value)

    def must_not_resolve(*_args, **_kwargs):
        raise AssertionError("run directory must not be resolved")

    monkeypatch.setattr(fallback, "_resolve_run_dir", must_not_resolve)

    with pytest.raises(AuditIdentityError, match="run_id"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009",
                features=_fallback_dossier(),
                output_root=tmp_path / "fallback",
                audit_identity=identity,
                model="fixture-model",
            )
        )


def test_fallback_rejects_same_output_and_audit_root_before_run_creation(
    tmp_path, monkeypatch
):
    async def must_not_call_llm(*_args, **_kwargs):
        raise AssertionError("same-root conflict must fail before LLM")

    monkeypatch.setattr(fallback, "call_llm", must_not_call_llm)

    with pytest.raises(AuditIdentityError, match="audit_root"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009",
                features=_fallback_dossier(),
                output_root=tmp_path,
                audit_root=tmp_path,
                run_id="same-root",
                model="fixture-model",
            )
        )

    assert not (tmp_path / "same-root").exists()


def test_fallback_reuses_supplied_identity_run_id_when_run_id_is_omitted(tmp_path, monkeypatch):
    identity = create_audit_identity(
        "600009.SH",
        dossier=_fallback_dossier(),
        profile_version="g2-fallback-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model", "reasoning_level": "heavy"},
        run_id="shared-run",
    )
    monkeypatch.setattr(fallback, "call_llm", lambda *_args, **_kwargs: None)

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009.SH",
            features=_fallback_dossier(),
            output_root=tmp_path / "fallback",
            audit_root=tmp_path / "audit",
            audit_identity=identity,
            model="fixture-model",
        )
    )
    assert result["run_id"] == "shared-run"
    assert (tmp_path / "fallback" / "shared-run").exists()


def test_fallback_removes_audit_manifest_and_staged_result_when_promotion_fails(
    tmp_path, monkeypatch
):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    async def fake_call(*_args, **_kwargs):
        return output.to_json(), {}

    def fail_promote(*_args, **_kwargs):
        raise OSError("result promotion failed")

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setattr(fallback, "_promote_staged_fallback_result", fail_promote)

    with pytest.raises(OSError, match="result promotion failed"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009",
                features=_fallback_dossier(),
                output_root=tmp_path / "fallback",
                audit_root=tmp_path / "audit",
                run_id="fallback-a",
                model="fixture-model",
            )
        )

    assert not (tmp_path / "fallback" / "fallback-a" / "result.json").exists()
    assert not list((tmp_path / "fallback" / "fallback-a" / ".staging").glob("*"))
    assert not (tmp_path / "audit" / "fallback-a" / "manifest.json").exists()
    assert json.loads(
        (tmp_path / "fallback" / "fallback-a" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["state"] == "failed"


def test_fallback_does_not_delete_result_written_by_a_racing_publisher(
    tmp_path, monkeypatch
):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    async def fake_call(*_args, **_kwargs):
        return output.to_json(), {}

    def race_then_fail(_staged_path, result_path):
        result_path.write_text('{"publisher":"other"}', encoding="utf-8")
        raise OSError("result promotion failed")

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setattr(fallback, "_promote_staged_fallback_result", race_then_fail)

    with pytest.raises(OSError, match="result promotion failed"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009",
                features=_fallback_dossier(),
                output_root=tmp_path / "fallback",
                audit_root=tmp_path / "audit",
                run_id="fallback-a",
                model="fixture-model",
            )
        )

    result_path = tmp_path / "fallback" / "fallback-a" / "result.json"
    assert json.loads(result_path.read_text(encoding="utf-8")) == {"publisher": "other"}
    assert not (tmp_path / "audit" / "fallback-a" / "manifest.json").exists()
    assert json.loads(
        (tmp_path / "fallback" / "fallback-a" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["state"] == "failed"


def test_council_audited_entrypoint_binds_result_to_same_run(tmp_path, monkeypatch):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0", "ROE 12.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(debate, "call_agent", _recorded_agent(output))

    result = asyncio.run(
        debate.run_debate(
            "600009",
            features=_fallback_dossier(),
            agents=["buffett"],
            audit_root=tmp_path / "audit",
        )
    )

    assert result.run_id
    assert result.ticker == "600009.SH"
    manifest = verify_audit_chain(tmp_path / "audit" / result.run_id)
    assert manifest["identity"]["canonical_ticker"] == "600009.SH"
    assert manifest["identity"]["run_id"] == result.run_id
    debate_path = tmp_path / "debate" / "600009.SH" / result.run_id
    watchlist_path = tmp_path / "watchlist" / "600009.SH" / result.run_id
    assert list(debate_path.glob("*.md"))
    assert list(watchlist_path.glob("*.json"))
    final_payload = json.loads(
        (tmp_path / "audit" / result.run_id / "05-final_result.json").read_text()
    )["payload"]["published_output"]
    published = json.loads(next(watchlist_path.glob("*.json")).read_text())
    assert final_payload == published


def test_two_audited_council_runs_same_day_keep_separate_outputs(tmp_path, monkeypatch):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0", "ROE 12.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(debate, "call_agent", _recorded_agent(output))
    first = asyncio.run(
        debate.run_debate(
            "600009",
            features=_fallback_dossier(),
            agents=["buffett"],
            audit_root=tmp_path / "audit",
        )
    )
    second = asyncio.run(
        debate.run_debate(
            "600009",
            features=_fallback_dossier(),
            agents=["buffett"],
            audit_root=tmp_path / "audit",
        )
    )

    assert first.run_id != second.run_id
    assert len(
        list(
            (tmp_path / "debate" / "600009.SH").glob(
                f"*/{date.today().isoformat()}.md"
            )
        )
    ) == 2
    assert len(list((tmp_path / "watchlist" / "600009.SH").glob("*/*.json"))) == 2


def test_audited_council_does_not_finalize_before_publish_failure(
    tmp_path, monkeypatch
):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    def fail_publish(*_args, **_kwargs):
        raise OSError("publish failed")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(debate, "call_agent", _recorded_agent(output))
    monkeypatch.setattr(debate, "_write_council_output", fail_publish)

    with pytest.raises(OSError, match="publish failed"):
        asyncio.run(
            debate.run_debate(
                "600009",
                features=_fallback_dossier(),
                agents=["buffett"],
                audit_root=tmp_path / "audit",
            )
        )

    assert not list((tmp_path / "audit").glob("*/manifest.json"))


def test_audited_council_hides_staged_output_when_audit_finalization_fails(
    tmp_path, monkeypatch
):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    def fail_finalize(self):
        raise OSError("audit finalize failed")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(debate, "call_agent", _recorded_agent(output))
    monkeypatch.setattr(audit_chain.AuditChainWriter, "finalize", fail_finalize)

    with pytest.raises(OSError, match="audit finalize failed"):
        asyncio.run(
            debate.run_debate(
                "600009",
                features=_fallback_dossier(),
                agents=["buffett"],
                audit_root=tmp_path / "audit",
            )
        )

    assert not list((tmp_path / "watchlist" / "600009.SH").glob("*/*.json"))
    assert not list((tmp_path / "watchlist" / ".staging").rglob("*.json"))
    assert not list((tmp_path / "audit").glob("*/0*-*.json"))


def test_audited_council_aborts_staging_on_quality_gate_failure(tmp_path, monkeypatch):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "munger 看好该公司",
            "key_metrics": ["PE 20.0"],
            "risks": ["风险"],
            "what_would_change_my_mind": "新证据",
            "out_of_circle": False,
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(debate, "call_agent", _recorded_agent(output))

    with pytest.raises(ValueError, match="circular_reference"):
        asyncio.run(
            debate.run_debate(
                "600009",
                features=_fallback_dossier(),
                agents=["buffett"],
                audit_root=tmp_path / "audit",
            )
        )

    assert not list((tmp_path / "audit" / ".staging").rglob("*"))
    assert not list((tmp_path / "audit").glob("*/manifest.json"))


def test_audited_council_aborts_staging_when_r2_fails(tmp_path, monkeypatch):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实",
            "key_metrics": ["PE 20.0"],
            "risks": ["风险"],
            "what_would_change_my_mind": "新证据",
            "out_of_circle": False,
        },
    )

    async def fail_r2(*_args, **kwargs):
        if kwargs.get("prompt_stage") == "r2":
            raise RuntimeError("r2 failed")
        return output

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(debate, "call_agent", fail_r2)

    with pytest.raises(RuntimeError, match="r2 failed"):
        asyncio.run(
            debate.run_debate(
                "600009",
                features=_fallback_dossier(),
                agents=["buffett"],
                mock_opinions={"buffett": output},
                audit_root=tmp_path / "audit",
            )
        )

    assert not list((tmp_path / "audit" / ".staging").rglob("*"))


def test_fallback_marks_setup_failure_failed_and_aborts_audit_staging(
    tmp_path, monkeypatch
):
    def fail_prompt(_agent):
        raise RuntimeError("prompt setup failed")

    monkeypatch.setattr(fallback, "get_prompt_builder", fail_prompt)

    with pytest.raises(RuntimeError, match="prompt setup failed"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009",
                features=_fallback_dossier(),
                output_root=tmp_path / "fallback",
                audit_root=tmp_path / "audit",
                run_id="setup-failed",
                model="fixture-model",
            )
        )

    runtime_manifest = tmp_path / "fallback" / "setup-failed" / "manifest.json"
    assert json.loads(runtime_manifest.read_text())["state"] == "failed"
    assert not list((tmp_path / "audit" / ".staging").rglob("*"))


def test_audited_council_removes_published_output_when_promotion_cleanup_fails(
    tmp_path, monkeypatch
):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    def publish_then_fail(staged_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        os.link(staged_path, output_path)
        raise OSError("staging cleanup failed")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(debate, "call_agent", _recorded_agent(output))
    monkeypatch.setattr(debate, "_promote_staged_output", publish_then_fail)

    with pytest.raises(OSError, match="staging cleanup failed"):
        asyncio.run(
            debate.run_debate(
                "600009",
                features=_fallback_dossier(),
                agents=["buffett"],
                audit_root=tmp_path / "audit",
            )
        )

    assert not list((tmp_path / "watchlist" / "600009.SH").glob("*/*.json"))
    assert not list((tmp_path / "audit").glob("*/manifest.json"))


def test_audited_council_does_not_delete_output_written_by_a_racing_publisher(
    tmp_path, monkeypatch
):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )

    def race_then_fail(_staged_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('{"publisher":"other"}', encoding="utf-8")
        raise OSError("staging cleanup failed")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(debate, "call_agent", _recorded_agent(output))
    monkeypatch.setattr(debate, "_promote_staged_output", race_then_fail)

    with pytest.raises(OSError, match="staging cleanup failed"):
        asyncio.run(
            debate.run_debate(
                "600009",
                features=_fallback_dossier(),
                agents=["buffett"],
                audit_root=tmp_path / "audit",
            )
        )

    published = next((tmp_path / "watchlist" / "600009.SH").glob("*/*.json"))
    assert json.loads(published.read_text(encoding="utf-8")) == {"publisher": "other"}
    assert not list((tmp_path / "audit").glob("*/manifest.json"))


def test_writer_rejects_invalid_dossier_artifact_before_finalize(tmp_path):
    dossier = {"ticker": "600519.SH"}
    identity = create_audit_identity(
        "600519.SH",
        dossier=dossier,
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )

    with pytest.raises(AuditIdentityError, match="dossier"):
        AuditChainWriter(tmp_path, identity).write(
            "dossier",
            _artifact_payload(identity),
        )


@pytest.mark.parametrize(
    ("artifact_type", "invalid_extra", "message"),
    [
        ("prompt", {"prompts": []}, "prompt"),
        (
            "debate",
            {"debate_text": "recorded", "debate_text_sha256": "not-a-real-hash"},
            "debate text hash",
        ),
        (
            "final_result",
            {
                "result": {"status": "passed"},
                "result_sha256": "not-a-real-hash",
            },
            "final result identity",
        ),
    ],
)
def test_writer_rejects_unverifiable_artifact_content_at_write_time(
    tmp_path, artifact_type, invalid_extra, message
):
    dossier = {"ticker": "600519.SH", "snapshot_version": "dossier-1"}
    identity = create_audit_identity(
        "600519.SH",
        dossier=dossier,
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )
    writer = AuditChainWriter(tmp_path, identity)
    ordered_types = ("dossier", "prompt", "debate", "quality_report", "final_result")
    for prior_type in ordered_types[: ordered_types.index(artifact_type)]:
        writer.write(
            prior_type,
            _artifact_payload_for_type(identity, prior_type, dossier),
        )

    with pytest.raises(AuditIdentityError, match=message):
        writer.write(artifact_type, _artifact_payload(identity, **invalid_extra))


def test_writer_rejects_prompt_binding_mismatch(tmp_path):
    dossier = {"ticker": "600519.SH", "snapshot_version": "dossier-1"}
    identity = create_audit_identity(
        "600519.SH",
        dossier=dossier,
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )
    writer = AuditChainWriter(tmp_path, identity)
    writer.write("dossier", _artifact_payload_for_type(identity, "dossier", dossier))

    with pytest.raises(AuditIdentityError, match="prompt binding"):
        writer.write(
            "prompt",
            _artifact_payload(
                identity,
                prompts=[
                    {
                        "agent": "buffett",
                        "stage": "r1",
                        "round": "heavy",
                        "system_prompt": "system",
                        "user_message": "user",
                    }
                ],
                prompt_binding_sha256="not-a-real-hash",
            ),
        )


def test_writer_rejects_fallback_response_output_rebinding(tmp_path):
    dossier = {"ticker": "600519.SH", "snapshot_version": "dossier-1"}
    identity = create_audit_identity(
        "600519.SH",
        dossier=dossier,
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )
    writer = AuditChainWriter(tmp_path, identity)
    writer.write("dossier", _artifact_payload_for_type(identity, "dossier", dossier))
    writer.write("prompt", _artifact_payload_for_type(identity, "prompt", dossier))
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": [],
            "risks": ["风险"],
            "what_would_change_my_mind": "新证据",
            "out_of_circle": False,
        },
    )

    with pytest.raises(AuditIdentityError, match="binding"):
        writer.write(
            "debate",
            _artifact_payload(
                identity,
                agent_id="buffett",
                response='{"signal":"neutral"}',
                agent_output=output.to_dict(),
                response_sha256=payload_sha256('{"signal":"neutral"}'),
                agent_output_sha256=payload_sha256(output.to_dict()),
            ),
        )


def test_writer_rejects_final_result_nested_identity_mismatch(tmp_path):
    dossier = {"ticker": "600519.SH", "snapshot_version": "dossier-1"}
    identity = create_audit_identity(
        "600519.SH",
        dossier=dossier,
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )
    writer = AuditChainWriter(tmp_path, identity)
    for artifact_type in ("dossier", "prompt", "debate", "quality_report"):
        writer.write(
            artifact_type,
            _artifact_payload_for_type(identity, artifact_type, dossier),
        )

    published_output = _artifact_payload(
        identity,
        final_verdict="neutral",
        ticker="600009.SH",
    )
    with pytest.raises(AuditIdentityError, match="final result identity"):
        writer.write(
            "final_result",
            _artifact_payload(
                identity,
                published_output=published_output,
                published_output_sha256=payload_sha256(published_output),
            ),
        )


def test_council_rejects_reasoning_level_override(tmp_path):
    with pytest.raises(ValueError, match="reasoning_levels"):
        asyncio.run(
            debate.run_debate(
                "600009",
                features=_fallback_dossier(),
                agents=["buffett"],
                audit_root=tmp_path / "audit",
                model_configuration={
                    "reasoning_levels": ["moderate", "heavy"],
                },
            )
        )


def test_call_agent_forwards_explicit_model_configuration(monkeypatch):
    output = AgentOutput.from_dict(
        "buffett",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "基于当前可核验事实保持中性",
            "key_metrics": ["PE 20.0"],
            "risks": ["估值与需求变化"],
            "what_would_change_my_mind": "补充连续期经营数据",
            "out_of_circle": False,
        },
    )
    calls = []

    async def fake_llm(*args, **kwargs):
        calls.append((args, kwargs))
        return output.to_json(), {}

    monkeypatch.setattr(debate, "call_llm", fake_llm)
    monkeypatch.setattr(debate, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setattr(debate, "_build_user_message", lambda *args, **kwargs: "user")

    result = asyncio.run(
        debate.call_agent(
            "buffett",
            "600009.SH",
            _fallback_dossier(),
            model="frozen-heavy-model",
        )
    )

    assert result.signal == "neutral"
    assert calls[0][1]["model"] == "frozen-heavy-model"


def test_audited_identity_canonicalizes_ticker_and_generates_one_run_id():
    identity = create_audit_identity(
        "600519",
        dossier={"ticker": "600519.SH", "snapshot_version": "dossier-1"},
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model", "temperature": 0},
    )

    assert identity.canonical_ticker == "600519.SH"
    assert identity.run_id
    assert identity.profile_version == "g2-profile-v1"
    assert identity.dossier_snapshot == "dossier-1"
    assert identity.model_configuration == {"model": "fixture-model", "temperature": 0}


def test_writer_creates_verifiable_five_stage_chain(tmp_path):
    dossier = {"ticker": "600519.SH", "snapshot_version": "dossier-1", "facts": [1, 2]}
    identity = create_audit_identity(
        "600519.SH",
        dossier=dossier,
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )
    writer = AuditChainWriter(tmp_path, identity)
    for artifact_type in ("dossier", "prompt", "debate", "quality_report", "final_result"):
        writer.write(artifact_type, _artifact_payload_for_type(identity, artifact_type, dossier))

    manifest = writer.finalize()
    assert [item["artifact_type"] for item in manifest["artifacts"]] == [
        "dossier",
        "prompt",
        "debate",
        "quality_report",
        "final_result",
    ]
    assert verify_audit_chain(tmp_path / "run-a") == manifest


def test_identity_mismatch_fails_closed_before_artifact_write(tmp_path):
    identity = create_audit_identity(
        "600519.SH",
        dossier={"ticker": "600519.SH"},
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )
    writer = AuditChainWriter(tmp_path, identity)

    with pytest.raises(AuditIdentityError, match="ticker"):
        writer.write("dossier", _artifact_payload(identity, ticker="600009.SH"))

    assert not list((tmp_path / "run-a").glob("*.json"))


def test_identity_payload_must_be_complete_and_input_hash_must_match_dossier(tmp_path):
    dossier = {"ticker": "600519.SH", "snapshot_version": "dossier-1"}
    with pytest.raises(AuditIdentityError, match="input_hash"):
        create_audit_identity(
            "600519.SH",
            dossier=dossier,
            profile_version="g2-profile-v1",
            prompt_version="council-prompt-v1",
            model_configuration={"model": "fixture-model"},
            input_hash="not-the-dossier-hash",
        )

    identity = create_audit_identity(
        "600519.SH",
        dossier=dossier,
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )
    with pytest.raises(AuditIdentityError, match="incomplete"):
        AuditChainWriter(tmp_path, identity).write("dossier", {"ticker": "600519.SH"})


def test_tampered_payload_and_broken_parent_fail_closed(tmp_path):
    dossier = {"ticker": "600519.SH"}
    identity = create_audit_identity(
        "600519.SH",
        dossier=dossier,
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )
    writer = AuditChainWriter(tmp_path, identity)
    for artifact_type in ("dossier", "prompt", "debate", "quality_report", "final_result"):
        writer.write(artifact_type, _artifact_payload_for_type(identity, artifact_type, dossier))
    writer.finalize()

    final_path = tmp_path / "run-a" / "05-final_result.json"
    payload = json.loads(final_path.read_text())
    payload["payload"]["ticker"] = "600009.SH"
    final_path.write_text(json.dumps(payload))

    with pytest.raises(AuditIdentityError, match="payload hash"):
        verify_audit_chain(tmp_path / "run-a")


@pytest.mark.parametrize("field", ["payload_sha256", "parent_hashes", "path"])
def test_manifest_metadata_tampering_fails_closed(tmp_path, field):
    dossier = {"ticker": "600519.SH"}
    identity = create_audit_identity(
        "600519.SH",
        dossier=dossier,
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
        run_id="run-a",
    )
    writer = AuditChainWriter(tmp_path, identity)
    for artifact_type in ("dossier", "prompt", "debate", "quality_report", "final_result"):
        writer.write(artifact_type, _artifact_payload_for_type(identity, artifact_type, dossier))
    writer.finalize()
    manifest_path = tmp_path / "run-a" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if field == "payload_sha256":
        manifest["artifacts"][0][field] = "tampered"
    elif field == "parent_hashes":
        manifest["artifacts"][1][field] = ["tampered"]
    else:
        manifest["artifacts"][0][field] = "../01-dossier.json"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(AuditIdentityError):
        verify_audit_chain(tmp_path / "run-a")


def test_same_day_runs_are_isolated_and_existing_artifact_is_not_overwritten(tmp_path):
    kwargs = dict(
        dossier={"ticker": "600519.SH", "snapshot_version": "dossier-1"},
        profile_version="g2-profile-v1",
        prompt_version="council-prompt-v1",
        model_configuration={"model": "fixture-model"},
    )
    first = create_audit_identity("600519.SH", run_id="run-a", **kwargs)
    second = create_audit_identity("600519.SH", run_id="run-b", **kwargs)
    assert first.run_id != second.run_id

    dossier = kwargs["dossier"]
    AuditChainWriter(tmp_path, first).write(
        "dossier", _artifact_payload_for_type(first, "dossier", dossier)
    )
    AuditChainWriter(tmp_path, second).write(
        "dossier", _artifact_payload_for_type(second, "dossier", dossier)
    )
    assert (tmp_path / ".staging" / "run-a" / "01-dossier.json").exists()
    assert (tmp_path / ".staging" / "run-b" / "01-dossier.json").exists()

    with pytest.raises(FileExistsError):
        AuditChainWriter(tmp_path, first).write(
            "dossier", _artifact_payload_for_type(first, "dossier", dossier)
        )
