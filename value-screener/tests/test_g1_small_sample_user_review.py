from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import app
from screener.small_sample import run_small_sample
from screener.small_sample import render_small_sample_markdown
from test_g1_mvp_small_sample_run import _bundle, _complete_dimensions

from council.small_sample_user_review import (
    REVIEW_DIMENSIONS,
    SmallSampleUserReviewInputError,
    build_small_sample_user_review_record,
    render_small_sample_user_review_json,
    render_small_sample_user_review_markdown,
    validate_small_sample_user_review_record,
    write_small_sample_user_review_record,
)


def test_build_template_binds_m1_2_identity_and_four_review_dimensions():
    source = run_small_sample(_bundle(tickers=["600005", "600001", "600004", "600002", "600003"]))

    module_spec = importlib.util.find_spec("council.small_sample_user_review")
    assert module_spec is not None, "M1.3 review module is not implemented"
    module = __import__(
        "council.small_sample_user_review",
        fromlist=["build_small_sample_user_review_record", "REVIEW_DIMENSIONS"],
    )
    record = module.build_small_sample_user_review_record(source)

    assert record["artifact_type"] == "g1_small_sample_user_review"
    assert record["review_status"] == "template"
    assert record["capability_status"] == "not_evidence"
    assert record["gate_status"] == "not_passed"
    assert record["run_id"] == source["run_id"]
    assert record["profile_version"] == source["profile_version"]
    assert record["input_ticker_set_hash"] == source["input_ticker_set_hash"]
    assert [item["ticker"] for item in record["ticker_reviews"]] == [
        "600001.SH",
        "600002.SH",
        "600003.SH",
        "600004.SH",
        "600005.SH",
    ]
    for item in record["ticker_reviews"]:
        assert set(item["dimensions"]) == set(module.REVIEW_DIMENSIONS)
        assert set(item["source_result"]) >= {
            "candidate",
            "quality_status",
            "exclusion",
        }
        assert {
            dimension["status"]
            for dimension in item["dimensions"].values()
        } == {"not_evaluable"}


def _completed_reviews(source: dict) -> dict:
    statuses = ("accepted", "question", "problem", "not_evaluable")
    reviews = {}
    for index, item in enumerate(source["tickers"]):
        reviews[item["ticker"]] = {}
        for dimension_index, dimension in enumerate(REVIEW_DIMENSIONS):
            status = statuses[(index + dimension_index) % len(statuses)]
            reviews[item["ticker"]][dimension] = {
                "status": status,
                "feedback": f"  原始反馈 {item['ticker']}|{dimension}\n第二行`  ",
                "question": "需要核对阈值" if status != "accepted" else "",
                "issue": "通过理由需要补证据" if status == "problem" else "",
                "corrected_value": {"status": status},
                "suggested_action": "补充校验",
            }
    return reviews


def test_completed_review_preserves_user_text_and_explicit_issue_categories():
    source = run_small_sample(_bundle())
    reviews = _completed_reviews(source)
    summary = {
        "threshold_issues": ["阈值过严"],
        "false_positive_tickers": ["600001.SH"],
        "false_negative_tickers": ["600005.SH"],
        "data_insufficiency": ["600003.SH 的财务数据失败"],
        "next_steps": ["人工复核后再决定是否修筛选器"],
    }

    record = build_small_sample_user_review_record(
        source,
        reviews,
        summary=summary,
    )

    assert record["review_status"] == "completed"
    assert record["capability_status"] == "mvp_evidence"
    assert record["gate_status"] == "not_passed"
    assert record["source_artifact_digest"]
    first = record["ticker_reviews"][0]
    assert first["dimensions"]["candidate"]["feedback"].startswith("  原始反馈")
    assert record["issue_categories"] == summary
    assert record["feedback_summary"]["status_counts"]
    assert record["ticker_reviews"][0]["ticker"] == "600001.SH"
    assert record["ticker_reviews"][-1]["ticker"] == "600005.SH"


def test_partial_issue_summary_defaults_unspecified_categories_to_empty():
    source = run_small_sample(_bundle())
    reviews = _completed_reviews(source)

    record = build_small_sample_user_review_record(
        source,
        reviews,
        summary={"threshold_issues": ["阈值过严"]},
    )

    assert record["issue_categories"] == {
        "data_insufficiency": [],
        "false_negative_tickers": [],
        "false_positive_tickers": [],
        "next_steps": [],
        "threshold_issues": ["阈值过严"],
    }


@pytest.mark.parametrize(
    "mutator",
    [
        lambda source: source.update(artifact_type="live/provider"),
        lambda source: source.update(mode="production"),
        lambda source: source["tickers"].append("600006"),
        lambda source: source["tickers"][0].update(unexpected="reject"),
        lambda source: source.update(unexpected="reject"),
    ],
)
def test_invalid_m1_2_artifact_fails_before_output_directory(tmp_path, mutator):
    source = run_small_sample(_bundle())
    mutator(source)

    with pytest.raises(SmallSampleUserReviewInputError):
        write_small_sample_user_review_record(source, tmp_path / "review")

    assert not (tmp_path / "review").exists()


def test_noncanonical_m1_2_ticker_is_rejected():
    source = run_small_sample(_bundle())
    source["tickers"][0]["ticker"] = "600001"

    with pytest.raises(SmallSampleUserReviewInputError, match="canonical"):
        build_small_sample_user_review_record(source)


def test_m1_2_provenance_field_types_are_validated():
    source = run_small_sample(_bundle())
    source["provenance"]["reader"] = 7

    with pytest.raises(SmallSampleUserReviewInputError, match="provenance"):
        build_small_sample_user_review_record(source)


def test_m1_2_stage_status_values_are_validated():
    source = run_small_sample(_bundle())
    source["tickers"][0]["stage_statuses"]["A"] = "unknown"

    with pytest.raises(SmallSampleUserReviewInputError, match="stage_statuses"):
        build_small_sample_user_review_record(source)


def test_optional_markdown_must_match_m1_2_identity(tmp_path):
    source = run_small_sample(_bundle())
    markdown_path = tmp_path / "source.md"
    markdown_path.write_text(render_small_sample_markdown(source), encoding="utf-8")
    valid = build_small_sample_user_review_record(
        source,
        markdown_path=markdown_path,
    )
    assert valid["source_markdown_path"] == str(markdown_path)

    markdown_path.write_text(
        render_small_sample_markdown(source)
        + "- run_id: `different-run`\n",
        encoding="utf-8",
    )
    with pytest.raises(SmallSampleUserReviewInputError, match="Markdown"):
        build_small_sample_user_review_record(source, markdown_path=markdown_path)

    markdown_path.write_text(
        "\n".join(
            [
                f"- run_id: `{source['run_id']}`",
                f"- profile_version: `{source['profile_version']}`",
                f"- input_ticker_set_hash: `{source['input_ticker_set_hash']}`",
                f"- as_of: `{source['as_of']}`",
                "- artifact_type: `fixture/reference`",
                "- mode: `simulated/development`",
                "- capability_status: `not_evidence`",
                "- gate_status: `not_passed`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SmallSampleUserReviewInputError, match="Markdown"):
        build_small_sample_user_review_record(source, markdown_path=markdown_path)


def test_optional_markdown_validation_does_not_import_provider_runtime(tmp_path):
    source = run_small_sample(_bundle())
    input_path = tmp_path / "m1-2.json"
    markdown_path = tmp_path / "m1-2.md"
    output_dir = tmp_path / "review"
    input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(
        render_small_sample_markdown(source),
        encoding="utf-8",
    )
    script = """
import builtins
import sys

blocked = (
    "akshare",
    "data.fetchers",
    "data.lib.batch_fetcher",
    "screener.small_sample",
)
original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if any(name == item or name.startswith(item + ".") for item in blocked):
        raise AssertionError(f"provider runtime import: {name}")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
from cli import app
app(
    [
        "small-sample-user-review",
        "--input",
        sys.argv[1],
        "--markdown",
        sys.argv[2],
        "--output-dir",
        sys.argv[3],
    ],
    standalone_mode=False,
)
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(input_path),
            str(markdown_path),
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={"PYTHONPATH": "."},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_completed_feedback_requires_explanation_for_non_accepted_status():
    source = run_small_sample(_bundle())
    reviews = _completed_reviews(source)
    reviews["600001.SH"]["candidate"]["status"] = "question"
    reviews["600001.SH"]["candidate"]["question"] = ""
    reviews["600001.SH"]["candidate"]["issue"] = ""

    with pytest.raises(SmallSampleUserReviewInputError, match="question or issue"):
        build_small_sample_user_review_record(source, reviews)


def test_renderers_are_deterministic_and_escape_feedback():
    source = run_small_sample(_bundle(tickers=["600005", "600001", "600004", "600002", "600003"]))
    reviews = _completed_reviews(source)
    first = build_small_sample_user_review_record(source, reviews)
    reordered = copy.deepcopy(reviews)
    reordered = dict(reversed(list(reordered.items())))
    second = build_small_sample_user_review_record(source, reordered)

    assert render_small_sample_user_review_json(first) == render_small_sample_user_review_json(second)
    markdown = render_small_sample_user_review_markdown(first)
    assert "\\|" in markdown
    assert "<br>" in markdown
    assert "&#96;" in markdown
    assert "（未填写）" in markdown or "accepted" in markdown


def test_tampered_review_record_fails_digest_validation():
    source = run_small_sample(_bundle())
    record = build_small_sample_user_review_record(source)
    record["ticker_reviews"][0]["dimensions"]["candidate"]["feedback"] = "tampered"

    with pytest.raises(SmallSampleUserReviewInputError, match="digest"):
        validate_small_sample_user_review_record(record)


def test_recomputed_digest_does_not_make_unknown_review_structure_valid():
    malformed = {"foo": "bar"}
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    malformed["artifact_digest"] = compute_small_sample_user_review_digest(malformed)

    with pytest.raises(SmallSampleUserReviewInputError, match="structure"):
        validate_small_sample_user_review_record(malformed)


def test_review_record_rejects_source_result_ticker_cross_binding():
    source = run_small_sample(_bundle())
    record = build_small_sample_user_review_record(source)
    record["ticker_reviews"][0]["source_result"]["ticker"] = "600002.SH"
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    record["artifact_digest"] = compute_small_sample_user_review_digest(record)

    with pytest.raises(SmallSampleUserReviewInputError, match="identity"):
        validate_small_sample_user_review_record(record)


def test_review_record_rejects_invalid_ticker_inside_source_snapshot():
    source = run_small_sample(_bundle())
    record = build_small_sample_user_review_record(source)
    record["source_snapshot"]["staged_evidence"]["ticker_evidence"][
        "600001.SH"
    ]["raw_ticker"] = "not-a-ticker"
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    record["artifact_digest"] = compute_small_sample_user_review_digest(record)

    with pytest.raises(SmallSampleUserReviewInputError, match="source snapshot"):
        validate_small_sample_user_review_record(record)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda record: record["ticker_reviews"][0]["dimensions"]["candidate"].update(
            status="accepted", feedback=""
        ),
        lambda record: record["provenance"].update(source="live/provider"),
        lambda record: record["issue_categories"].update(
            threshold_issues="not-a-list"
        ),
        lambda record: record["feedback_summary"].update(status_counts="not-a-map"),
        lambda record: record["ticker_reviews"][0]["source_result"][
            "stage_statuses"
        ].update(A=["invalid"]),
        lambda record: record["feedback_summary"]["status_counts"].update(
            accepted=False
        ),
    ],
)
def test_recomputed_digest_does_not_bypass_review_semantic_validation(mutator):
    source = run_small_sample(_bundle())
    record = build_small_sample_user_review_record(source)
    mutator(record)
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    record["artifact_digest"] = compute_small_sample_user_review_digest(record)

    with pytest.raises(SmallSampleUserReviewInputError, match="structure|semantic"):
        validate_small_sample_user_review_record(record)


def test_record_rebinds_ticker_set_hash_after_digest_recomputation():
    source = run_small_sample(_bundle())
    record = build_small_sample_user_review_record(source)
    record["input_ticker_set_hash"] = "tampered-hash"
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    record["artifact_digest"] = compute_small_sample_user_review_digest(record)

    with pytest.raises(SmallSampleUserReviewInputError, match="identity"):
        validate_small_sample_user_review_record(record)


def test_record_requires_canonical_ticker_order_after_digest_recomputation():
    source = run_small_sample(_bundle())
    record = build_small_sample_user_review_record(source)
    record["ticker_reviews"].reverse()
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    record["artifact_digest"] = compute_small_sample_user_review_digest(record)

    with pytest.raises(SmallSampleUserReviewInputError, match="order"):
        validate_small_sample_user_review_record(record)


def test_record_rejects_non_string_review_status_after_digest_recomputation():
    source = run_small_sample(_bundle())
    record = build_small_sample_user_review_record(source)
    record["review_status"] = []
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    record["artifact_digest"] = compute_small_sample_user_review_digest(record)

    with pytest.raises(SmallSampleUserReviewInputError, match="structure"):
        validate_small_sample_user_review_record(record)


def test_summary_text_categories_are_sorted_for_deterministic_artifacts():
    source = run_small_sample(_bundle())
    reviews = _completed_reviews(source)
    first_summary = {
        "threshold_issues": ["z", "a"],
        "false_positive_tickers": [],
        "false_negative_tickers": [],
        "data_insufficiency": ["z-data", "a-data"],
        "next_steps": ["z-next", "a-next"],
    }
    second_summary = {
        "threshold_issues": ["a", "z"],
        "false_positive_tickers": [],
        "false_negative_tickers": [],
        "data_insufficiency": ["a-data", "z-data"],
        "next_steps": ["a-next", "z-next"],
    }

    first = build_small_sample_user_review_record(
        source, reviews, summary=first_summary
    )
    second = build_small_sample_user_review_record(
        source, reviews, summary=second_summary
    )

    assert render_small_sample_user_review_json(first) == render_small_sample_user_review_json(second)
    assert render_small_sample_user_review_markdown(first) == render_small_sample_user_review_markdown(second)


def test_non_string_stage_status_is_rejected_as_input_error():
    source = run_small_sample(_bundle())
    source["tickers"][0]["stage_statuses"]["A"] = ["invalid"]

    with pytest.raises(SmallSampleUserReviewInputError, match="stage_statuses"):
        build_small_sample_user_review_record(source)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda source: source["summary"].update(input_count=99),
        lambda source: source["staged_evidence"].update(run_id="wrong-run"),
        lambda source: source["staged_evidence"].update(
            input_ticker_set_hash="wrong-hash"
        ),
        lambda source: source["tickers"][0].update(quality_status="unknown"),
        lambda source: source["tickers"][2].update(candidate=True),
    ],
)
def test_m1_2_summary_and_per_ticker_semantics_are_fail_closed(mutator):
    source = run_small_sample(_bundle())
    mutator(source)

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda source: source["staged_evidence"]["stages"].update(A={}),
        lambda source: source["staged_evidence"]["ticker_evidence"].update(
            {"600001.SH": {}}
        ),
        lambda source: source["staged_evidence"]["candidates"].append("bad"),
        lambda source: source["tickers"][2]["exclusion"].pop("reason_code"),
        lambda source: source["summary"]["quality_status_counts"].update(
            complete=4.0
        ),
    ],
)
def test_m1_2_nested_evidence_semantics_are_fail_closed(mutator):
    source = run_small_sample(_bundle())
    mutator(source)

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda source: source["staged_evidence"]["stages"]["A"][
            "dimension_results"
        ]["600001"].update(
            basic={"__error__": True, "error": "forged"}
        ),
        lambda source: source["staged_evidence"]["stages"]["A"][
            "dimension_results"
        ]["600001"].update(basic=["forged"]),
        lambda source: source["staged_evidence"]["candidates"][0].update(
            {
                "name": None,
                "industry": None,
                "factor_scores": None,
                "anti_trap": None,
                "adjusted_composite": None,
                "f_score": None,
            }
        ),
        lambda source: source["tickers"][2]["exclusion"].update(
            dimension="forged"
        ),
    ],
)
def test_m1_2_deep_payload_semantics_are_fail_closed(mutator):
    source = run_small_sample(_bundle())
    mutator(source)

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


def test_m1_2_candidate_nested_types_are_fail_closed():
    source = run_small_sample(_bundle())
    candidate = source["staged_evidence"]["candidates"][0]
    candidate["name"] = 7
    candidate["factor_scores"]["composite"] = "forged"
    candidate["anti_trap"]["score"] = "forged"
    candidate["heat_filter"]["pass"] = "forged"
    row = source["tickers"][0]
    row["details"]["name"] = 7
    row["scores"]["factor_scores"]["composite"] = "forged"
    row["scores"]["anti_trap"]["score"] = "forged"
    row["scores"]["heat_filter"]["pass"] = "forged"

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda source: source["staged_evidence"]["stages"]["A"][
            "dimension_results"
        ]["600001"]["basic"].update(forged_extra="reject"),
        lambda source: source["staged_evidence"]["stages"]["B"][
            "dimension_results"
        ]["600001"]["financials"]["income"].update(forged_extra="reject"),
        lambda source: source["staged_evidence"]["ticker_evidence"]["600001.SH"][
            "canonical_fields"
        ].update(forged_field="reject"),
    ],
)
def test_m1_2_nested_unknown_fields_are_fail_closed(mutator):
    source = run_small_sample(_bundle())
    mutator(source)

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


def test_m1_2_canonical_field_provenance_is_offline_and_strict():
    source = run_small_sample(_bundle())
    source["staged_evidence"]["ticker_evidence"]["600001.SH"][
        "canonical_fields"
    ]["price"] = {
        "value": 1,
        "status": "available",
        "eligibility": "not_qualified",
        "reason": None,
        "provenance": {"provider": "live/provider"},
        "as_of": None,
        "freshness": None,
        "available": True,
    }

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


@pytest.mark.parametrize(
    "field_update",
    [
        {"eligibility": "production_eligible"},
        {"status": "unknown"},
        {"freshness": "unknown"},
        {"provenance": {}},
    ],
)
def test_m1_2_canonical_field_production_and_metadata_are_fail_closed(
    field_update,
):
    source = run_small_sample(_bundle())
    field = {
        "value": 1,
        "status": "available",
        "eligibility": "not_qualified",
        "reason": None,
        "provenance": {
            "source": "fixture/reference",
            "not_live_provider_evidence": True,
        },
        "as_of": None,
        "freshness": "fresh",
        "available": True,
    }
    field.update(field_update)
    source["staged_evidence"]["ticker_evidence"]["600001.SH"][
        "canonical_fields"
    ]["price"] = field

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


def test_m1_2_failure_must_match_error_payload_and_financial_series_lengths():
    source = run_small_sample(_bundle())
    source["staged_evidence"]["stages"]["B"]["dimension_results"]["600003"][
        "financials"
    ] = copy.deepcopy(
        source["staged_evidence"]["stages"]["B"]["dimension_results"]["600001"][
            "financials"
        ]
    )

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)

    source = run_small_sample(_bundle())
    financials = source["staged_evidence"]["stages"]["B"]["dimension_results"][
        "600001"
    ]["financials"]
    financials["income"]["net_profit"] = [10.0]

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


def test_m1_2_failed_gates_are_required_and_recomputed():
    data = {ticker: copy.deepcopy(value) for ticker, value in {
        ticker: {
            "basic": {
                "name": "正常股",
                "price": 10.0,
                "pe": 12.0,
                "pb": 1.5,
                "market_cap": 10e9,
                "industry": "制造业",
            },
            "financials": {
                "years": ["2022", "2023", "2024"],
                "income": {"net_profit": [10.0, 11.0, 12.0]},
                "balance_sheet": {
                    "TOTAL_ASSETS": [100.0, 105.0, 110.0],
                    "TOTAL_CURRENT_LIAB": [20.0, 20.0, 20.0],
                    "TOTAL_NONCURRENT_LIAB": [20.0, 20.0, 20.0],
                },
                "cash_flow": {"NETCASH_OPERATE": [12.0, 13.0, 14.0]},
            },
            "risk": {
                "pledge_ratio": 5.0,
                "pledge_status": "record_found",
                "audit_opinion": "标准无保留意见",
            },
            "valuation": {
                "pe_ttm": 12.0,
                "pb": 1.5,
                "pe_percentile_5y": 30.0,
                "pe_history": [10.0, 11.0, 12.0],
            },
            "kline": {
                "close": [10.0] * 60,
                "turnover_rate": [2.0] * 60,
            },
        }
        for ticker in ["600001", "600002", "600003", "600004", "600005"]
    }.items()}
    data["600001"]["basic"]["market_cap"] = 1e9
    source = run_small_sample(_bundle(data=data))
    row = next(row for row in source["tickers"] if row["ticker"] == "600001.SH")
    assert row["exclusion"]["reason"] == "hard_gates_failed:H3"
    assert row["exclusion"]["failed_gates"] == ["H3"]

    row["exclusion"].pop("failed_gates")
    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)

    source = run_small_sample(_bundle(data=data))
    row = next(row for row in source["tickers"] if row["ticker"] == "600001.SH")
    row["exclusion"]["reason"] = "hard_gates_failed:H999"
    row["exclusion"]["failed_gates"] = ["H999"]
    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


def test_m1_2_heat_filter_exclusion_is_accepted():
    tickers = ["600001", "600002", "600003", "600004", "600005"]
    data = {ticker: _complete_dimensions() for ticker in tickers}
    data["600001"]["kline"]["close"] = [10.0] * 59 + [13.0]
    source = run_small_sample(_bundle(tickers=tickers, data=data))

    row = next(row for row in source["tickers"] if row["ticker"] == "600001.SH")
    assert row["exclusion"]["reason"] == "heat_filter_failed"
    assert row["exclusion"]["reason_code"] == "heat_filter_failed"
    build_small_sample_user_review_record(source)


def test_stage_b_gate_recomputation_does_not_import_provider_runtime():
    tickers = ["600001", "600002", "600003", "600004", "600005"]
    data = {ticker: _complete_dimensions() for ticker in tickers}
    data["600001"]["risk"]["pledge_ratio"] = 80.0
    source = run_small_sample(_bundle(tickers=tickers, data=data))
    script = """
import builtins
import json
import sys

blocked = (
    "akshare",
    "data.fetchers",
    "data.lib.batch_fetcher",
    "screener.main",
    "screener.small_sample",
)
original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if any(name == item or name.startswith(item + ".") for item in blocked):
        raise AssertionError(f"provider runtime import: {name}")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
from council.small_sample_user_review import build_small_sample_user_review_record
build_small_sample_user_review_record(json.loads(sys.stdin.read()))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={"PYTHONPATH": "."},
        input=json.dumps(source, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_lock_symlink_is_rejected_without_writing_outside_output_dir(tmp_path):
    source = run_small_sample(_bundle())
    output_dir = tmp_path / "review"
    output_dir.mkdir()
    outside = tmp_path / "outside-lock-target"
    lock_path = output_dir / ".m1-2-fixture-run.review.lock"
    lock_path.symlink_to(outside)

    with pytest.raises(SmallSampleUserReviewInputError, match="output_dir"):
        write_small_sample_user_review_record(source, output_dir)

    assert not outside.exists()
    assert lock_path.is_symlink()
    assert not (output_dir / "m1-2-fixture-run-review.json").exists()
    assert not (output_dir / "m1-2-fixture-run-review.md").exists()


def test_existing_review_artifact_symlink_is_rejected(tmp_path):
    source = run_small_sample(_bundle())
    output_dir = tmp_path / "review"
    output_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    (output_dir / "m1-2-fixture-run-review.json").symlink_to(outside)

    with pytest.raises(SmallSampleUserReviewInputError, match="output_dir"):
        write_small_sample_user_review_record(source, output_dir)

    assert outside.read_text(encoding="utf-8") == "outside"


def test_pair_write_uses_locked_directory_fd_for_rename(tmp_path, monkeypatch):
    source = run_small_sample(_bundle())
    import council.small_sample_user_review as review_module

    original_replace = review_module.os.replace
    replace_calls = []

    def checked_replace(*args, **kwargs):
        replace_calls.append(kwargs)
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(review_module.os, "replace", checked_replace)
    write_small_sample_user_review_record(source, tmp_path / "review")

    assert len(replace_calls) == 2
    assert all(
        isinstance(call.get("src_dir_fd"), int)
        and isinstance(call.get("dst_dir_fd"), int)
        and call["src_dir_fd"] == call["dst_dir_fd"]
        for call in replace_calls
    )


def test_output_directory_symlink_is_rejected(tmp_path):
    source = run_small_sample(_bundle())
    target = tmp_path / "target"
    target.mkdir()
    output_dir = tmp_path / "review-link"
    output_dir.symlink_to(target, target_is_directory=True)

    with pytest.raises(SmallSampleUserReviewInputError, match="output_dir"):
        write_small_sample_user_review_record(source, output_dir)

    assert not (target / "m1-2-fixture-run-review.json").exists()
    assert not (target / "m1-2-fixture-run-review.md").exists()


def test_markdown_escapes_backslash_before_pipe():
    source = run_small_sample(_bundle())
    reviews = _completed_reviews(source)
    reviews["600001.SH"]["candidate"]["feedback"] = r"a\|b"

    record = build_small_sample_user_review_record(source, reviews)
    markdown = render_small_sample_user_review_markdown(record)

    assert r"a&#92;\|b" in markdown


def test_review_record_rejects_source_result_tampering_after_digest_recomputation():
    source = run_small_sample(_bundle())
    record = build_small_sample_user_review_record(source)
    record["ticker_reviews"][0]["source_result"]["details"]["name"] = "tampered"
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    record["artifact_digest"] = compute_small_sample_user_review_digest(record)

    with pytest.raises(SmallSampleUserReviewInputError, match="source"):
        validate_small_sample_user_review_record(record)


def test_review_record_normalizes_markdown_path_for_cross_cwd_validation(
    tmp_path,
    monkeypatch,
):
    source = run_small_sample(_bundle())
    markdown_path = tmp_path / "source.md"
    markdown_path.write_text(
        render_small_sample_markdown(source),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    record = build_small_sample_user_review_record(source, markdown_path="source.md")

    assert Path(record["source_markdown_path"]).is_absolute()
    monkeypatch.chdir(tmp_path.parent)
    validate_small_sample_user_review_record(record)


def test_review_record_rejects_recomputed_digest_with_replaced_markdown(tmp_path):
    source = run_small_sample(_bundle())
    markdown_path = tmp_path / "source.md"
    fake_path = tmp_path / "fake.md"
    markdown_path.write_text(
        render_small_sample_markdown(source),
        encoding="utf-8",
    )
    fake_path.write_text("not M1.2 markdown", encoding="utf-8")
    record = build_small_sample_user_review_record(
        source,
        markdown_path=markdown_path,
    )
    from council.small_sample_user_review import _sha256
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    record["source_markdown_path"] = str(fake_path.resolve())
    record["source_markdown_digest"] = _sha256(
        fake_path.read_text(encoding="utf-8")
    )
    record["artifact_digest"] = compute_small_sample_user_review_digest(record)

    with pytest.raises(SmallSampleUserReviewInputError, match="Markdown"):
        validate_small_sample_user_review_record(record)


def test_review_record_rejects_invalid_summary_ticker_as_input_error():
    source = run_small_sample(_bundle())
    record = build_small_sample_user_review_record(source)
    record["feedback_summary"]["question_or_problem_tickers"] = ["not-a-ticker"]
    from council.small_sample_user_review import (
        compute_small_sample_user_review_digest,
    )

    record["artifact_digest"] = compute_small_sample_user_review_digest(record)

    with pytest.raises(SmallSampleUserReviewInputError, match="ticker"):
        validate_small_sample_user_review_record(record)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda source: source["tickers"][0].update(
            candidate=False,
            exclusion={
                "stage": "A",
                "dimension": "basic",
                "status": "source_failed",
                "reason": "arbitrary",
                "reason_code": "source_failed",
            },
        ),
        lambda source: source["tickers"][2]["exclusion"].update(
            stage="A", reason="arbitrary"
        ),
        lambda source: source["staged_evidence"]["stages"]["A"]["failures"].append(
            {
                "ticker": "600001",
                "dimension": "basic",
                "status": "source_failed",
                "reason": "unexpected failure",
            }
        ),
        lambda source: source["staged_evidence"]["stages"]["A"].update(
            dimension_results={}
        ),
        lambda source: source["staged_evidence"]["stages"]["A"].update(
            input_tickers=[]
        ),
        lambda source: source["staged_evidence"]["stages"]["B"]["failures"][0].update(
            status="unknown"
        ),
    ],
)
def test_m1_2_candidate_failure_binding_and_nested_content_are_fail_closed(mutator):
    source = run_small_sample(_bundle())
    mutator(source)

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


def test_exclusion_reason_code_and_metadata_are_bound_to_staged_failure():
    source = run_small_sample(_bundle())
    row = next(row for row in source["tickers"] if row["exclusion"] is not None)
    old_reason_code = row["exclusion"]["reason_code"]
    row["exclusion"]["reason_code"] = "forged_reason_code"
    counts = source["summary"]["exclusion_reason_counts"]
    counts[old_reason_code] -= 1
    if counts[old_reason_code] == 0:
        del counts[old_reason_code]
    counts["forged_reason_code"] = 1

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)

def test_malformed_candidate_source_result_is_a_controlled_input_error():
    source = run_small_sample(_bundle())
    source["tickers"][0]["details"].pop("name")

    with pytest.raises(SmallSampleUserReviewInputError, match="M1.2"):
        build_small_sample_user_review_record(source)


def test_write_is_run_scoped_immutable_and_does_not_touch_production_roots(tmp_path):
    source = run_small_sample(_bundle())
    output_dir = tmp_path / "reviews"
    first = write_small_sample_user_review_record(source, output_dir)
    second = write_small_sample_user_review_record(source, output_dir)

    assert first == second
    assert first.json_path.name == "m1-2-fixture-run-review.json"
    assert first.markdown_path.name == "m1-2-fixture-run-review.md"
    original = first.json_path.read_text(encoding="utf-8")

    changed = run_small_sample(_bundle())
    changed_reviews = _completed_reviews(changed)
    with pytest.raises(SmallSampleUserReviewInputError, match="immutable"):
        write_small_sample_user_review_record(
            changed,
            output_dir,
            changed_reviews,
        )
    assert first.json_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "watchlist").exists()
    assert not (tmp_path / "debate").exists()
    assert not list(output_dir.glob(".*.review.lock"))


def test_write_does_not_leave_global_or_output_lock_files(tmp_path, monkeypatch):
    source = run_small_sample(_bundle())
    import council.small_sample_user_review as review_module

    temp_root = tmp_path / "system-temp"
    monkeypatch.setattr(review_module.tempfile, "gettempdir", lambda: str(temp_root))
    output_dir = tmp_path / "review"

    write_small_sample_user_review_record(source, output_dir)

    assert not (temp_root / "trade-agent-g1-review-locks").exists()
    assert not list(output_dir.glob(".*.review.lock"))


def test_protected_output_root_is_rejected_before_write():
    source = run_small_sample(_bundle())
    repo_root = Path(__file__).resolve().parents[2]
    protected = repo_root / "value-screener" / "data" / "cache"

    with pytest.raises(SmallSampleUserReviewInputError, match="protected"):
        write_small_sample_user_review_record(source, protected)


def test_canonical_project_production_root_is_rejected_before_write():
    source = run_small_sample(_bundle())
    canonical_root = Path(__file__).resolve().parents[4]
    protected = canonical_root / "value-screener" / "data" / "cache"

    with pytest.raises(SmallSampleUserReviewInputError, match="protected"):
        write_small_sample_user_review_record(source, protected)


@pytest.mark.parametrize("protected_name", ["evidence", "live_runs"])
def test_evidence_and_live_run_roots_are_rejected_before_write(
    tmp_path, protected_name
):
    source = run_small_sample(_bundle())
    protected = (
        Path(__file__).resolve().parents[2]
        / "value-screener"
        / "data"
        / protected_name
    )

    with pytest.raises(SmallSampleUserReviewInputError, match="protected"):
        write_small_sample_user_review_record(source, protected)

    assert not (protected / "m1-2-fixture-run-review.json").exists()
    assert not (protected / "m1-2-fixture-run-review.md").exists()


def test_different_run_ids_get_distinct_files(tmp_path):
    first = run_small_sample(_bundle())
    second = run_small_sample(_bundle())
    second["run_id"] = "another-run"
    second["staged_evidence"]["run_id"] = "another-run"
    for stage in second["staged_evidence"]["stages"].values():
        stage["run_id"] = "another-run"
    output_dir = tmp_path / "reviews"

    first_artifacts = write_small_sample_user_review_record(first, output_dir)
    second_artifacts = write_small_sample_user_review_record(second, output_dir)

    assert first_artifacts.json_path != second_artifacts.json_path
    assert first_artifacts.json_path.exists()
    assert second_artifacts.json_path.exists()


def test_cli_creates_template_without_loading_provider_or_council_runtime(tmp_path):
    source = run_small_sample(_bundle())
    input_path = tmp_path / "m1-2.json"
    markdown_path = tmp_path / "m1-2.md"
    input_path.write_text(
        json.dumps(source, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_small_sample_markdown(source),
        encoding="utf-8",
    )
    output_dir = tmp_path / "review"

    result = CliRunner().invoke(
        app,
        [
            "small-sample-user-review",
            "--input",
            str(input_path),
            "--markdown",
            str(markdown_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (output_dir / "m1-2-fixture-run-review.json").exists()
    assert (output_dir / "m1-2-fixture-run-review.md").exists()
    record = json.loads(
        (output_dir / "m1-2-fixture-run-review.json").read_text(encoding="utf-8")
    )
    assert record["review_status"] == "template"
    assert record["capability_status"] == "not_evidence"


def test_cli_attributes_protected_output_error_to_output_dir(tmp_path):
    source = run_small_sample(_bundle())
    input_path = tmp_path / "m1-2.json"
    input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    protected = Path(__file__).resolve().parents[2] / "value-screener" / "data" / "cache"

    result = CliRunner().invoke(
        app,
        [
            "small-sample-user-review",
            "--input",
            str(input_path),
            "--output-dir",
            str(protected),
        ],
    )

    assert result.exit_code == 2
    assert "--output-dir" in result.output


def test_cli_attributes_mismatched_markdown_error_to_markdown(tmp_path):
    source = run_small_sample(_bundle())
    input_path = tmp_path / "m1-2.json"
    markdown_path = tmp_path / "wrong.md"
    input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text("not the M1.2 markdown", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "small-sample-user-review",
            "--input",
            str(input_path),
            "--markdown",
            str(markdown_path),
            "--output-dir",
            str(tmp_path / "review"),
        ],
    )

    assert result.exit_code == 2
    assert "--markdown" in result.output


def test_cli_attributes_output_parent_error_to_output_dir(tmp_path):
    source = run_small_sample(_bundle())
    input_path = tmp_path / "m1-2.json"
    input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("occupied", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "small-sample-user-review",
            "--input",
            str(input_path),
            "--output-dir",
            str(parent_file / "review"),
        ],
    )

    assert result.exit_code == 2
    assert "--output-dir" in result.output


def test_cli_attributes_invalid_markdown_encoding_to_markdown(tmp_path):
    source = run_small_sample(_bundle())
    input_path = tmp_path / "m1-2.json"
    markdown_path = tmp_path / "invalid.md"
    input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_bytes(b"\xff\xfe\x00")

    result = CliRunner().invoke(
        app,
        [
            "small-sample-user-review",
            "--input",
            str(input_path),
            "--markdown",
            str(markdown_path),
            "--output-dir",
            str(tmp_path / "review"),
        ],
    )

    assert result.exit_code == 2
    assert "--markdown" in result.output


def test_cli_attributes_invalid_nested_ticker_to_input(tmp_path):
    source = run_small_sample(_bundle())
    source["staged_evidence"]["ticker_evidence"]["600001.SH"][
        "raw_ticker"
    ] = "not-a-ticker"
    input_path = tmp_path / "m1-2.json"
    input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "small-sample-user-review",
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "review"),
        ],
    )

    assert result.exit_code == 2
    assert "--input" in result.output


def test_pair_write_rolls_back_when_second_artifact_replace_fails(tmp_path, monkeypatch):
    source = run_small_sample(_bundle())
    import council.small_sample_user_review as review_module

    original_replace = review_module.os.replace
    calls = 0

    def fail_second_replace(source_path, target_path, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second replace failure")
        return original_replace(source_path, target_path, **kwargs)

    monkeypatch.setattr(review_module.os, "replace", fail_second_replace)

    with pytest.raises(SmallSampleUserReviewInputError, match="output_dir"):
        write_small_sample_user_review_record(source, tmp_path / "review")

    output_dir = tmp_path / "review"
    assert not (output_dir / "m1-2-fixture-run-review.json").exists()
    assert not (output_dir / "m1-2-fixture-run-review.md").exists()


def test_review_module_import_does_not_load_provider_or_council_modules():
    script = """
import sys
import council.small_sample_user_review
assert 'council.debate' not in sys.modules
assert 'council.llm' not in sys.modules
assert 'data.fetchers.basic' not in sys.modules
assert 'akshare' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={"PYTHONPATH": "."},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
