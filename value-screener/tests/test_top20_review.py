"""g1-top20-style-review RED/GREEN 测试.

覆盖 G1 umbrella 6.1/6.2 产品 Gate 的最小合同：
- Top 20 必须绑定固定（pinned）run 的 profile_version / input_ticker_set_hash / 漏斗
- Top 20 最多 20 只，顺序为 derivation 候选顺序；不足不凑数
- 每只记录必须包含完整 identity；逐只复核记录完整才允许计算 Gate
- worth_research_count >= 70%（14/20）才通过；不足必须失败
- 缺失记录 / 非法标签 / 空理由 / 身份不一致 → 阻断或 not_evaluable
- 失败与不可判定 MUST NOT 被写成 capability passed
- evidence 保留逐只记录与汇总统计

测试不访问真实 data/cache、provider、LLM；全部使用注入的 fake L1 输出与 tmp_path。
"""
from __future__ import annotations

import json

import pytest

from data.lib.identity import compute_input_ticker_set_hash
from screener.top20_review import (
    REVIEW_LABELS,
    Top20ValidationError,
    build_review_template,
    derive_top20,
    evaluate_gate,
    finalize_top20,
    load_pinned_run,
    validate_user_review,
)

PINNED_RUN_ID = "7887d515-157d-4d17-bcb5-fab54c7fbee3"
PROFILE_VERSION = "g1-2026-07-21"


def _tickers(n: int) -> list[str]:
    """生成 n 个合法沪深 canonical ticker."""
    out = []
    for i in range(n):
        code = f"{600000 + i}"
        out.append(f"{code}.SH")
    return out


def _pinned_bundle(tickers: list[str], funnel_overrides: dict | None = None) -> dict:
    """构造最小合法 pinned bundle（与 full-market evidence bundle 同构的 identity 字段）."""
    funnel = {
        "total": len(tickers),
        "after_hard_gates": max(len(tickers) - 2, 1),
        "after_factors": max(len(tickers) - 3, 1),
        "after_heat_filter": max(len(tickers) - 4, 1),
        "l2_input": max(len(tickers) - 4, 1),
    }
    if funnel_overrides:
        funnel.update(funnel_overrides)
    return {
        "schema_version": "g1-full-market-performance-cost.v2",
        "run_id": PINNED_RUN_ID,
        "profile_version": PROFILE_VERSION,
        "input_ticker_set_hash": compute_input_ticker_set_hash(tickers),
        "input_tickers": list(tickers),
        "run_date": "2026-08-12",
        "coverage": "full_market",
        "funnel": funnel,
        "hard_gate_passed": True,
        "gate_passed": True,
    }


def _l1_output(
    tickers: list[str],
    n_candidates: int,
    run_id: str = "derivation-run-0001",
    profile_version: str = PROFILE_VERSION,
    input_hash: str | None = None,
    stats_overrides: dict | None = None,
) -> dict:
    """构造 S5 schema 的 fake L1 输出（candidates 按 adjusted_composite 降序）."""
    input_hash = input_hash if input_hash is not None else compute_input_ticker_set_hash(tickers)
    candidates = []
    for i in range(n_candidates):
        candidates.append({
            "ticker": tickers[i],
            "factor_scores": {"composite": 90.0 - i, "quality": 80.0, "valuation": 70.0},
            "anti_trap": {"score": 95.0, "flags": []},
            "adjusted_composite": (90.0 - i) * 0.95,
        })
    stats = {
        "total": len(tickers),
        "after_hard_gates": max(len(tickers) - 2, 1),
        "after_factors": max(len(tickers) - 3, 1),
        "after_heat_filter": n_candidates,
        "excluded_by_gates": {},
    }
    if stats_overrides:
        stats.update(stats_overrides)
    return {
        "run_id": run_id,
        "run_date": "2026-08-13",
        "profile_version": profile_version,
        "input_ticker_set_hash": input_hash,
        "candidates": candidates,
        "stats": stats,
    }


def _make_pinned(n_input: int = 30, n_candidates: int = 25) -> tuple[dict, dict]:
    """构造一致的 pinned bundle 与 fake L1 输出.

    pinned bundle 的 funnel.after_heat_filter/l2_input 必须等于 L1 候选数，
    否则漏斗交叉验证会（正确地）判为漂移。
    """
    tickers = _tickers(n_input)
    bundle = _pinned_bundle(tickers, funnel_overrides={
        "after_heat_filter": n_candidates,
        "l2_input": n_candidates,
    })
    pinned = load_pinned_run(bundle)
    l1 = _l1_output(tickers, n_candidates)
    return pinned, l1


def _valid_review_records(derivation: dict, labels: list[str]) -> dict:
    """按 derivation Top 20 构造合法复核文档（labels 长度必须等于 top20 数量）."""
    top20 = derivation["top20"]
    assert len(labels) == len(top20)
    reviews = []
    for item, label in zip(top20, labels):
        reviews.append({
            "rank": item["rank"],
            "ticker": item["ticker"],
            "label": label,
            "reason": f"理由-{item['rank']}",
        })
    return {
        "schema_version": "g1-top20-user-review.v1",
        "pinned_run_id": derivation["pinned_run"]["run_id"],
        "derivation_run_id": derivation["derivation_run"]["run_id"],
        "profile_version": derivation["pinned_run"]["profile_version"],
        "input_ticker_set_hash": derivation["pinned_run"]["input_ticker_set_hash"],
        "reviews": reviews,
    }


# ---------------------------------------------------------------------------
# 2.1 pinned bundle 解析
# ---------------------------------------------------------------------------

def test_load_pinned_run_extracts_identity():
    tickers = _tickers(30)
    bundle = _pinned_bundle(tickers)
    pinned = load_pinned_run(bundle)
    assert pinned["run_id"] == PINNED_RUN_ID
    assert pinned["profile_version"] == PROFILE_VERSION
    assert pinned["input_ticker_set_hash"] == bundle["input_ticker_set_hash"]
    assert pinned["input_tickers"] == tickers
    assert pinned["funnel"]["after_heat_filter"] == bundle["funnel"]["after_heat_filter"]


def test_load_pinned_run_accepts_file_path(tmp_path):
    tickers = _tickers(10)
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(_pinned_bundle(tickers)), encoding="utf-8")
    pinned = load_pinned_run(path)
    assert pinned["run_id"] == PINNED_RUN_ID


@pytest.mark.parametrize("missing_field", ["run_id", "profile_version", "input_ticker_set_hash", "input_tickers"])
def test_load_pinned_run_rejects_missing_identity(missing_field):
    bundle = _pinned_bundle(_tickers(10))
    del bundle[missing_field]
    with pytest.raises(Top20ValidationError):
        load_pinned_run(bundle)


def test_load_pinned_run_rejects_empty_input_tickers():
    bundle = _pinned_bundle(_tickers(10))
    bundle["input_tickers"] = []
    with pytest.raises(Top20ValidationError):
        load_pinned_run(bundle)


def test_load_pinned_run_rejects_hash_mismatch():
    """input_tickers 与声明 hash 不一致（bundle 损坏/被改）→ 报错."""
    bundle = _pinned_bundle(_tickers(10))
    bundle["input_tickers"] = _tickers(12)  # 集合变了但 hash 未变
    with pytest.raises(Top20ValidationError):
        load_pinned_run(bundle)


# ---------------------------------------------------------------------------
# 2.2 派生绑定
# ---------------------------------------------------------------------------

def test_derive_top20_binds_pinned_run_identity():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    assert derivation["status"] == "derived"
    assert derivation["pinned_run"]["run_id"] == PINNED_RUN_ID
    assert derivation["derivation_run"]["run_id"] == "derivation-run-0001"
    assert derivation["derivation_run"]["derivation_kind"] == "deterministic_l1_replay"
    for item in derivation["top20"]:
        assert item["pinned_run_id"] == PINNED_RUN_ID
        assert item["profile_version"] == PROFILE_VERSION
        assert item["input_ticker_set_hash"] == pinned["input_ticker_set_hash"]


def test_derive_top20_profile_mismatch_not_evaluable():
    pinned, l1 = _make_pinned()
    l1["profile_version"] = "g1-9999-99-99"
    derivation = derive_top20(pinned, l1)
    assert derivation["status"] == "not_evaluable"
    assert "profile_version" in " ".join(derivation["reason"])
    assert "top20" not in derivation or not derivation.get("top20")


def test_derive_top20_input_hash_mismatch_not_evaluable():
    pinned, l1 = _make_pinned()
    l1["input_ticker_set_hash"] = "deadbeef0000"
    derivation = derive_top20(pinned, l1)
    assert derivation["status"] == "not_evaluable"
    assert any("input_ticker_set_hash" in r for r in derivation["reason"])


def test_derive_top20_funnel_drift_not_evaluable():
    pinned, l1 = _make_pinned()
    l1["stats"]["after_hard_gates"] = pinned["funnel"]["after_hard_gates"] + 1
    derivation = derive_top20(pinned, l1)
    assert derivation["status"] == "not_evaluable"
    assert any("after_hard_gates" in r for r in derivation["reason"])


# ---------------------------------------------------------------------------
# 2.3 数量与排序
# ---------------------------------------------------------------------------

def test_derive_top20_takes_first_20_in_candidate_order():
    pinned, l1 = _make_pinned(n_input=40, n_candidates=25)
    derivation = derive_top20(pinned, l1)
    top20 = derivation["top20"]
    assert len(top20) == 20
    assert [item["rank"] for item in top20] == list(range(1, 21))
    assert [item["ticker"] for item in top20] == [c["ticker"] for c in l1["candidates"][:20]]
    composites = [item["adjusted_composite"] for item in top20]
    assert composites == sorted(composites, reverse=True)


def test_derive_top20_no_padding_when_fewer_candidates():
    pinned, l1 = _make_pinned(n_input=12, n_candidates=5)
    derivation = derive_top20(pinned, l1)
    assert derivation["status"] == "derived"
    assert len(derivation["top20"]) == 5


# ---------------------------------------------------------------------------
# 2.4 / 2.5 复核记录校验
# ---------------------------------------------------------------------------

def test_validate_review_accepts_complete_records():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    labels = ["worth_further_research"] * 20
    doc = _valid_review_records(derivation, labels)
    records = validate_user_review(doc, derivation)
    assert len(records) == 20
    assert all(r["label"] == "worth_further_research" for r in records)


def test_validate_review_rejects_missing_ticker():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    doc = _valid_review_records(derivation, ["worth_further_research"] * 20)
    doc["reviews"] = doc["reviews"][:-1]  # 缺最后一只
    with pytest.raises(Top20ValidationError):
        validate_user_review(doc, derivation)


def test_validate_review_rejects_duplicate_ticker():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    doc = _valid_review_records(derivation, ["worth_further_research"] * 20)
    doc["reviews"].append(dict(doc["reviews"][0]))  # 重复 rank1
    with pytest.raises(Top20ValidationError):
        validate_user_review(doc, derivation)


def test_validate_review_rejects_rank_ticker_mismatch():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    doc = _valid_review_records(derivation, ["worth_further_research"] * 20)
    doc["reviews"][0]["ticker"] = derivation["top20"][1]["ticker"]  # rank1 配了 rank2 的 ticker
    with pytest.raises(Top20ValidationError):
        validate_user_review(doc, derivation)


def test_validate_review_rejects_invalid_label():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    labels = ["worth_further_research"] * 20
    labels[3] = "maybe_good"
    doc = _valid_review_records(derivation, labels)
    with pytest.raises(Top20ValidationError) as exc_info:
        validate_user_review(doc, derivation)
    msg = str(exc_info.value)
    assert "maybe_good" in msg
    assert derivation["top20"][3]["ticker"] in msg


def test_validate_review_rejects_empty_reason():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    doc = _valid_review_records(derivation, ["worth_further_research"] * 20)
    doc["reviews"][5]["reason"] = "   "
    with pytest.raises(Top20ValidationError) as exc_info:
        validate_user_review(doc, derivation)
    assert derivation["top20"][5]["ticker"] in str(exc_info.value)


def test_validate_review_rejects_identity_mismatch():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    doc = _valid_review_records(derivation, ["worth_further_research"] * 20)
    doc["pinned_run_id"] = "some-other-run"
    with pytest.raises(Top20ValidationError):
        validate_user_review(doc, derivation)


def test_validate_review_rejects_summary_only_input():
    """只有汇总比例没有逐只记录 → 拒绝（不得出 Gate 结论）."""
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    doc = {
        "schema_version": "g1-top20-user-review.v1",
        "pinned_run_id": PINNED_RUN_ID,
        "derivation_run_id": derivation["derivation_run"]["run_id"],
        "profile_version": PROFILE_VERSION,
        "input_ticker_set_hash": pinned["input_ticker_set_hash"],
        "summary": {"worth_ratio": 0.85},
    }
    with pytest.raises(Top20ValidationError):
        validate_user_review(doc, derivation)


def test_review_labels_enum_exposes_three_required_labels():
    assert "worth_further_research" in REVIEW_LABELS
    assert "not_worth_further_research" in REVIEW_LABELS
    assert any("unable" in label for label in REVIEW_LABELS)


# ---------------------------------------------------------------------------
# 2.6 Gate 阈值
# ---------------------------------------------------------------------------

def test_gate_passed_at_exactly_14_of_20():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    labels = ["worth_further_research"] * 14 + ["not_worth_further_research"] * 6
    doc = _valid_review_records(derivation, labels)
    evidence = finalize_top20(derivation, doc)
    assert evidence["gate_verdict"] == "passed"
    assert evidence["statistics"]["worth_research_count"] == 14
    assert evidence["statistics"]["total_reviewed"] == 20


def test_gate_failed_at_13_of_20():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    labels = ["worth_further_research"] * 13 + ["not_worth_further_research"] * 7
    doc = _valid_review_records(derivation, labels)
    evidence = finalize_top20(derivation, doc)
    assert evidence["gate_verdict"] == "failed"
    assert evidence["statistics"]["worth_research_count"] == 13


def test_failed_evidence_never_claims_capability_passed():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    labels = ["worth_further_research"] * 10 + ["unable_to_judge_insufficient_data"] * 10
    doc = _valid_review_records(derivation, labels)
    evidence = finalize_top20(derivation, doc)
    assert evidence["gate_verdict"] == "failed"
    serialized = json.dumps(evidence, ensure_ascii=False)
    assert "capability_passed" not in serialized.replace("capability passed", "capability_passed")
    assert evidence.get("capability_passed") is not True


def test_gate_threshold_scales_with_fewer_candidates():
    pinned, l1 = _make_pinned(n_input=12, n_candidates=5)
    derivation = derive_top20(pinned, l1)
    # 4/5 = 80% >= 70% → passed
    doc = _valid_review_records(derivation, ["worth_further_research"] * 4 + ["not_worth_further_research"])
    evidence = finalize_top20(derivation, doc)
    assert evidence["gate_verdict"] == "passed"
    # 3/5 = 60% < 70% → failed
    doc = _valid_review_records(derivation, ["worth_further_research"] * 3 + ["not_worth_further_research"] * 2)
    evidence = finalize_top20(derivation, doc)
    assert evidence["gate_verdict"] == "failed"


def test_evaluate_gate_counts_all_labels():
    records = [
        {"ticker": f"60000{i}.SH", "label": label}
        for i, label in enumerate(
            ["worth_further_research"] * 14
            + ["not_worth_further_research"] * 4
            + ["unable_to_judge_insufficient_data"] * 2
        )
    ]
    stats = evaluate_gate(records)
    assert stats["worth_research_count"] == 14
    assert stats["not_worth_research_count"] == 4
    assert stats["unable_to_judge_count"] == 2
    assert stats["total_reviewed"] == 20
    assert stats["gate_verdict"] == "passed"


# ---------------------------------------------------------------------------
# 2.8 evidence 内容与三态
# ---------------------------------------------------------------------------

def test_evidence_contains_per_ticker_audit_chain():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    labels = ["worth_further_research"] * 14 + ["not_worth_further_research"] * 6
    doc = _valid_review_records(derivation, labels)
    evidence = finalize_top20(derivation, doc)
    assert evidence["schema_version"] == "g1-top20-style-review.v1"
    assert evidence["pinned_run"]["run_id"] == PINNED_RUN_ID
    assert evidence["derivation_run"]["run_id"] == derivation["derivation_run"]["run_id"]
    reviewed = evidence["reviews"]
    assert len(reviewed) == 20
    for item in reviewed:
        assert item["rank"] in range(1, 21)
        assert item["ticker"]
        assert item["label"] in REVIEW_LABELS
        assert item["reason"].strip()
        assert item["pinned_run_id"] == PINNED_RUN_ID
    assert "statistics" in evidence
    assert evidence["gate_verdict"] in {"passed", "failed", "not_evaluable"}


def test_not_evaluable_derivation_finalize_never_passed():
    pinned, l1 = _make_pinned()
    l1["profile_version"] = "g1-9999-99-99"
    derivation = derive_top20(pinned, l1)
    evidence = finalize_top20(derivation, review_doc=None)
    assert evidence["gate_verdict"] == "not_evaluable"
    assert evidence["reason"]


def test_finalize_rejects_invalid_review_without_pass():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    labels = ["worth_further_research"] * 20
    labels[0] = "bogus_label"
    doc = _valid_review_records(derivation, labels)
    with pytest.raises(Top20ValidationError):
        finalize_top20(derivation, doc)


def test_build_review_template_has_empty_labels_and_full_context():
    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    template = build_review_template(derivation)
    assert template["schema_version"] == "g1-top20-user-review.v1"
    assert template["pinned_run_id"] == PINNED_RUN_ID
    assert len(template["reviews"]) == len(derivation["top20"])
    for item in template["reviews"]:
        assert item["label"] is None
        assert item["reason"] in (None, "")
        assert item["rank"] and item["ticker"]


def test_save_and_load_roundtrip(tmp_path):
    from screener.top20_review import save_json

    pinned, l1 = _make_pinned()
    derivation = derive_top20(pinned, l1)
    out = save_json(derivation, tmp_path / "nested" / "derivation.json")
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["status"] == "derived"
