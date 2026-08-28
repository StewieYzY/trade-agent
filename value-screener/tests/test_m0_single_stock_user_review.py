from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from cli import app
from council import thesis_draft
from council.user_review import (
    UserReviewInputError,
    write_user_review_record,
)
from council.thesis_draft import compute_thesis_draft_artifact_digest
from data.lib.frozen_growth_diagnostic import compute_frozen_growth_artifact_digest
from test_m0_strong_agent_thesis_draft import (
    _agent_response,
    _input_envelope,
    _run,
)


DIMENSIONS = ("facts", "assumptions", "growth_expectation", "thesis_draft")


def _review_fields(*, status: str = "completed") -> dict:
    dimensions = {
        "facts": {
            "conclusion_status": "accepted",
            "feedback": "来源、报告期和核心数值可以追溯。",
            "issues_or_corrections": [],
            "not_evaluable_reason": "",
        },
        "assumptions": {
            "conclusion_status": "question",
            "feedback": "维护性资本开支比例仍需要继续核对。",
            "issues_or_corrections": ["补充假设来源说明"],
            "not_evaluable_reason": "",
        },
        "growth_expectation": {
            "conclusion_status": "not_evaluable",
            "feedback": "暂时无法判断可信增长区间是否足够稳健。",
            "issues_or_corrections": [],
            "not_evaluable_reason": "缺少跨周期经营数据",
        },
        "thesis_draft": {
            "conclusion_status": "problem",
            "feedback": "核心判断可读，但反证还不够具体。",
            "issues_or_corrections": ["补充需求下行情景"],
            "not_evaluable_reason": "",
        },
    }
    if status == "template":
        dimensions = {
            name: {
                "conclusion_status": "not_evaluable",
                "feedback": "",
                "issues_or_corrections": [],
                "not_evaluable_reason": "",
            }
            for name in DIMENSIONS
        }
    return {
        "review_status": status,
        "dimensions": dimensions,
        "key_issues": (
            ["需要补充跨周期证据"] if status == "completed" else []
        ),
        "accepted_content": (
            ["事实来源和报告期展示清楚"] if status == "completed" else []
        ),
        "residual_risk": (
            ["诊断对资本开支假设敏感"] if status == "completed" else []
        ),
        "next_decision": (
            "先补充跨周期数据，再决定是否进入下一轮研究。"
            if status == "completed"
            else ""
        ),
    }


def _review_input(tmp_path, monkeypatch, *, status: str = "completed") -> dict:
    draft_input = _input_envelope(tmp_path / "source")
    _run(
        draft_input,
        tmp_path / "draft",
        monkeypatch,
        response=_agent_response(),
    )
    draft_path = tmp_path / "draft" / "600519.SH-m0-run-001.json"
    draft_artifact = json.loads(draft_path.read_text(encoding="utf-8"))
    return {
        "schema_version": "m0-single-stock-user-review-input-v1",
        "canonical_ticker": draft_input["canonical_ticker"],
        "run_id": draft_input["run_id"],
        "dossier_snapshot": draft_input["dossier_snapshot"],
        "profile_version": draft_input["profile_version"],
        "artifact_paths": {
            "diagnostic": str(
                tmp_path / "source" / "diagnostic" / "600519.SH-m0-run-001.json"
            ),
            "thesis_draft": str(draft_path),
        },
        "diagnostic_artifact": draft_input["diagnostic_artifact"],
        "thesis_draft_artifact": draft_artifact,
        "dossier": draft_input["dossier"],
        "user_review": _review_fields(status=status),
    }


def test_completed_review_preserves_four_dimensions_and_user_decision(
    tmp_path, monkeypatch
):
    payload = _review_input(tmp_path, monkeypatch)

    result = write_user_review_record(payload, tmp_path / "review")

    record = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert record["artifact_type"] == "m0_single_stock_user_review"
    assert record["capability_status"] == "mvp_evidence"
    assert record["gate_status"] == "not_passed"
    assert record["review_status"] == "completed"
    assert set(record["user_review"]["dimensions"]) == set(DIMENSIONS)
    assert (
        record["user_review"]["dimensions"]["growth_expectation"][
            "not_evaluable_reason"
        ]
        == "缺少跨周期经营数据"
    )
    assert record["user_review"]["next_decision"] == payload["user_review"]["next_decision"]
    assert record["user_review_owner"] == "user"
    assert "target_price" not in record
    assert "position" not in record
    assert "buy" not in record
    assert "sell" not in record

    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "人工复核记录" in markdown
    assert "M0.3 是 MVP evidence，不是正式 G2 Capability Gate evidence" in markdown
    assert "缺少跨周期经营数据" in markdown
    assert "先补充跨周期数据，再决定是否进入下一轮研究。" in markdown


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value["user_review"]["dimensions"][
            "facts"
        ].update(conclusion_status="not_evaluable", not_evaluable_reason=""),
        lambda value: value["user_review"].update(next_decision=""),
        lambda value: value.update(unexpected="reject"),
        lambda value: value.update(run_id="other-run"),
        lambda value: value["thesis_draft_artifact"].update(
            artifact_digest="0" * 64
        ),
    ],
)
def test_invalid_review_input_fails_before_output_directory(
    tmp_path, monkeypatch, mutator
):
    payload = _review_input(tmp_path, monkeypatch)
    mutator(payload)
    output_dir = tmp_path / "review"

    with pytest.raises(UserReviewInputError):
        write_user_review_record(payload, output_dir)

    assert not output_dir.exists()


@pytest.mark.parametrize(
    ("status", "capability_status", "marker"),
    [
        ("template", "not_evidence", "M0 product loop = pending user review"),
        ("completed", "mvp_evidence", "M0.3 是 MVP evidence，不是正式 G2 Capability Gate evidence"),
    ],
)
def test_template_and_completed_status_are_distinct(
    tmp_path, monkeypatch, status, capability_status, marker
):
    payload = _review_input(tmp_path, monkeypatch, status=status)

    result = write_user_review_record(payload, tmp_path / "review")

    record = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert record["capability_status"] == capability_status
    assert record["gate_status"] == "not_passed"
    assert marker in result.markdown_path.read_text(encoding="utf-8")


def test_same_input_renders_identical_traceable_artifacts(
    tmp_path, monkeypatch
):
    payload = _review_input(tmp_path, monkeypatch)

    first = write_user_review_record(payload, tmp_path / "one")
    second = write_user_review_record(copy.deepcopy(payload), tmp_path / "two")

    assert first.json_path.read_text(encoding="utf-8") == second.json_path.read_text(
        encoding="utf-8"
    )
    assert first.markdown_path.read_text(encoding="utf-8") == second.markdown_path.read_text(
        encoding="utf-8"
    )
    record = json.loads(first.json_path.read_text(encoding="utf-8"))
    assert record["reviewed_artifacts"]["diagnostic"]["path"] == payload[
        "artifact_paths"
    ]["diagnostic"]
    assert record["reviewed_artifacts"]["thesis_draft"]["artifact_digest"] == payload[
        "thesis_draft_artifact"
    ]["artifact_digest"]
    assert record["reviewed_artifacts"]["diagnostic"]["canonical_ticker"] == "600519.SH"


def test_artifact_paths_must_point_to_existing_files(tmp_path, monkeypatch):
    payload = _review_input(tmp_path, monkeypatch)
    payload["artifact_paths"]["diagnostic"] = str(tmp_path / "missing.json")
    output_dir = tmp_path / "review"

    with pytest.raises(UserReviewInputError, match="must point to an existing file"):
        write_user_review_record(payload, output_dir)

    assert not output_dir.exists()


def test_changed_dossier_cannot_be_used_for_existing_thesis(
    tmp_path, monkeypatch
):
    payload = _review_input(tmp_path, monkeypatch)
    payload["dossier"]["research_dossier"]["research"]["consensus_eps"] = 9.9

    with pytest.raises(UserReviewInputError, match="input_digest"):
        write_user_review_record(payload, tmp_path / "review")


def test_user_text_is_preserved_without_normalizing_whitespace(
    tmp_path, monkeypatch
):
    payload = _review_input(tmp_path, monkeypatch)
    feedback = "  原始反馈\n第二行  "
    decision = "  原始下一步决策  "
    payload["user_review"]["dimensions"]["facts"]["feedback"] = feedback
    payload["user_review"]["next_decision"] = decision

    result = write_user_review_record(payload, tmp_path / "review")

    record = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert record["user_review"]["dimensions"]["facts"]["feedback"] == feedback
    assert record["user_review"]["next_decision"] == decision


@pytest.mark.parametrize("artifact_name", ["diagnostic_artifact", "thesis_draft_artifact"])
def test_unknown_artifact_fields_fail_closed_even_with_recomputed_digest(
    tmp_path, monkeypatch, artifact_name
):
    payload = _review_input(tmp_path, monkeypatch)
    artifact = payload[artifact_name]
    artifact["unexpected_field"] = "must reject"
    if artifact_name == "diagnostic_artifact":
        artifact["artifact_digest"] = compute_frozen_growth_artifact_digest(artifact)
    else:
        artifact["artifact_digest"] = compute_thesis_draft_artifact_digest(artifact)

    with pytest.raises(UserReviewInputError, match="unknown fields"):
        write_user_review_record(payload, tmp_path / "review")


@pytest.mark.parametrize(
    ("artifact_name", "field"),
    [
        ("diagnostic_artifact", "gate_status"),
        ("thesis_draft_artifact", "quality_status"),
    ],
)
def test_missing_artifact_fields_fail_closed_even_with_recomputed_digest(
    tmp_path, monkeypatch, artifact_name, field
):
    payload = _review_input(tmp_path, monkeypatch)
    artifact = payload[artifact_name]
    artifact.pop(field)
    if artifact_name == "diagnostic_artifact":
        artifact["artifact_digest"] = compute_frozen_growth_artifact_digest(artifact)
    else:
        artifact["artifact_digest"] = compute_thesis_draft_artifact_digest(artifact)

    with pytest.raises(UserReviewInputError, match="missing fields"):
        write_user_review_record(payload, tmp_path / "review")


def test_changed_diagnostic_summary_fails_closed_with_recomputed_digest(
    tmp_path, monkeypatch
):
    payload = _review_input(tmp_path, monkeypatch)
    thesis = payload["thesis_draft_artifact"]
    thesis["diagnostic_summary"]["quality_status"] = "clean"
    thesis["artifact_digest"] = compute_thesis_draft_artifact_digest(thesis)

    with pytest.raises(UserReviewInputError, match="diagnostic_summary"):
        write_user_review_record(payload, tmp_path / "review")


def test_non_default_agent_id_fails_closed_with_recomputed_digests(
    tmp_path, monkeypatch
):
    payload = _review_input(tmp_path, monkeypatch)
    thesis = payload["thesis_draft_artifact"]
    thesis["agent_id"] = "munger"
    thesis["input_digest"] = hashlib.sha256(
        json.dumps(
            {
                "canonical_ticker": payload["canonical_ticker"],
                "run_id": payload["run_id"],
                "dossier_snapshot": payload["dossier_snapshot"],
                "profile_version": payload["profile_version"],
                "diagnostic_artifact": payload["diagnostic_artifact"],
                "dossier": payload["dossier"],
                "agent_id": thesis["agent_id"],
                "model": thesis["model"],
                "prompt_version": thesis["prompt_version"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    thesis["artifact_digest"] = compute_thesis_draft_artifact_digest(thesis)

    with pytest.raises(UserReviewInputError, match="agent_id"):
        write_user_review_record(payload, tmp_path / "review")


@pytest.mark.parametrize(
    ("raw", "encoded"),
    [
        ("用户输入\r# 伪造标题", "用户输入&#13;# 伪造标题"),
        ("用户输入\r\n# 伪造标题", "用户输入&#10;# 伪造标题"),
        ("用户输入\n# 伪造标题", "用户输入&#10;# 伪造标题"),
    ],
)
def test_markdown_escapes_line_breaks_in_user_list_text(
    tmp_path, monkeypatch, raw, encoded
):
    payload = _review_input(tmp_path, monkeypatch)
    payload["user_review"]["key_issues"] = [raw]

    result = write_user_review_record(payload, tmp_path / "review")

    markdown = result.markdown_path.read_text(encoding="utf-8")
    record = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert encoded in markdown
    assert record["user_review"]["key_issues"] == [raw]


def test_user_review_module_import_does_not_load_provider_modules():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import council.user_review; "
                "assert not any(name.startswith('data.fetchers') for name in sys.modules); "
                "assert 'council.debate' not in sys.modules"
            ),
        ],
        cwd=str(__import__("pathlib").Path.cwd()),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_cli_uses_explicit_paths_and_does_not_need_provider(
    tmp_path, monkeypatch
):
    payload = _review_input(tmp_path, monkeypatch)
    calls = []

    async def forbidden_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("M0.3 must not call LLM")

    monkeypatch.setattr(thesis_draft, "call_llm", forbidden_call)
    input_path = tmp_path / "review-input.json"
    input_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "single-stock-user-review",
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "cli-output"),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "JSON:" in result.stdout
    assert (tmp_path / "cli-output" / "600519.SH-m0-run-001.json").is_file()
    assert (tmp_path / "cli-output" / "600519.SH-m0-run-001.md").is_file()
    assert calls == []


def test_cli_subprocess_does_not_load_council_or_provider_modules(
    tmp_path, monkeypatch
):
    payload = _review_input(tmp_path, monkeypatch)
    input_path = tmp_path / "review-input.json"
    output_dir = tmp_path / "cli-output"
    input_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    script = """
import sys
from typer.testing import CliRunner
from cli import app

result = CliRunner().invoke(
    app,
    [
        "single-stock-user-review",
        "--input",
        sys.argv[1],
        "--output-dir",
        sys.argv[2],
    ],
)
assert result.exit_code == 0, result.output
assert "council.debate" not in sys.modules
assert not any(name.startswith("data.fetchers") for name in sys.modules)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", script, str(input_path), str(output_dir)],
        cwd=str(tmp_path.cwd()),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_cli_missing_input_does_not_create_output(tmp_path):
    output_dir = tmp_path / "cli-output"

    result = CliRunner().invoke(
        app,
        [
            "single-stock-user-review",
            "--input",
            str(tmp_path / "missing.json"),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code != 0
    assert "input file not found" in result.output
    assert not output_dir.exists()


def test_cli_points_output_errors_to_output_dir(tmp_path, monkeypatch):
    payload = _review_input(tmp_path, monkeypatch)
    input_path = tmp_path / "review-input.json"
    input_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("occupied", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "single-stock-user-review",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_file),
        ],
    )

    assert result.exit_code != 0
    assert "--output-dir" in result.output
