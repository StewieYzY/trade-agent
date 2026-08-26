from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from council.shared_diagnostic_proof import (
    SharedDiagnosticProofError,
    build_shared_diagnostic_proof,
    classify_council_increment,
)
from data.lib.growth_expectation_engine import FORMULA_VERSION

from test_g2_growth_expectation_engine import (
    assumptions,
    input_payload,
    compute,
)


def _artifact() -> dict:
    return compute().to_dict()


def _envelope(artifact: dict, *, run_id: str = "run-34") -> dict:
    return {
        "ticker": artifact["ticker"],
        "run_id": run_id,
        "dossier_snapshot": artifact["provenance"]["dossier_snapshot"],
        "diagnostic_digest": artifact["diagnostic_digest"],
        "assumption_snapshot_digest": _assumption_digest(artifact["assumption_snapshot"]),
    }


def _assumption_digest(snapshot: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _proof_kwargs(artifact: dict) -> dict:
    return {
        "ticker": artifact["ticker"],
        "run_id": "run-34",
        "input_payload": input_payload(),
        "assumption_snapshot": assumptions(),
        "formula_version": FORMULA_VERSION,
        "dossier_snapshot": "dossier-v1",
        "profile_version": "profile-v1",
        "diagnostic_identity": {
            "ticker": "600519.SH",
            "run_id": "run-34",
            "dossier_snapshot": "dossier-v1",
            "diagnostic_digest": artifact["diagnostic_digest"],
            "assumption_snapshot_digest": "08e015e395c5b1fa713588ae3f102897f03aa491050ee61905a8b3e8065f3a07",
        },
        "path_envelopes": {
            "strong_single_agent": _envelope(artifact),
            "council": _envelope(artifact),
        },
    }


def test_proof_accepts_same_artifact_and_assumption_snapshot_for_both_paths():
    artifact = _artifact()

    proof = build_shared_diagnostic_proof(
        diagnostic=artifact,
        **_proof_kwargs(artifact),
    )

    assert proof["status"] == "passed"
    assert proof["identity"] == {
        "ticker": "600519.SH",
        "run_id": "run-34",
        "dossier_snapshot": "dossier-v1",
        "diagnostic_digest": artifact["diagnostic_digest"],
        "assumption_snapshot_digest": "08e015e395c5b1fa713588ae3f102897f03aa491050ee61905a8b3e8065f3a07",
    }
    assert proof["paths"] == ("council", "strong_single_agent")


def test_proof_rejects_replaced_artifact_without_recomputed_digest():
    artifact = _artifact()
    replaced = deepcopy(artifact)
    replaced["priced_growth_value_range"] = [1.0, 2.0]

    with pytest.raises(SharedDiagnosticProofError, match="diagnostic_digest"):
        build_shared_diagnostic_proof(
            diagnostic=replaced,
            **_proof_kwargs(artifact),
        )


def test_proof_rejects_different_assumption_snapshot_content():
    artifact = _artifact()
    kwargs = _proof_kwargs(artifact)
    kwargs["path_envelopes"]["council"]["assumption_snapshot_digest"] = "0" * 64

    with pytest.raises(SharedDiagnosticProofError, match="assumption_snapshot"):
        build_shared_diagnostic_proof(diagnostic=artifact, **kwargs)


def test_proof_rejects_ticker_run_dossier_or_digest_chain_mismatch():
    artifact = _artifact()
    cases = [
        ("ticker", "600900.SH"),
        ("run_id", "run-other"),
        ("dossier_snapshot", "dossier-other"),
        ("diagnostic_digest", "0" * 64),
    ]

    for field, value in cases:
        kwargs = _proof_kwargs(artifact)
        if field == "ticker":
            kwargs["path_envelopes"]["council"][field] = value
        elif field == "run_id":
            kwargs["path_envelopes"]["council"][field] = value
        elif field == "dossier_snapshot":
            kwargs["path_envelopes"]["council"][field] = value
        else:
            kwargs["path_envelopes"]["council"][field] = value
        with pytest.raises(SharedDiagnosticProofError, match=field):
            build_shared_diagnostic_proof(diagnostic=artifact, **kwargs)


def test_proof_rejects_mismatched_diagnostic_identity_sidecar():
    artifact = _artifact()
    kwargs = _proof_kwargs(artifact)
    kwargs["diagnostic_identity"]["run_id"] = "run-forged"

    with pytest.raises(SharedDiagnosticProofError, match="diagnostic_identity"):
        build_shared_diagnostic_proof(diagnostic=artifact, **kwargs)


def test_proof_does_not_recompute_or_rewrite_the_shared_artifact(monkeypatch):
    artifact = _artifact()
    original = deepcopy(artifact)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("proof must not recompute the diagnostic")

    monkeypatch.setattr(
        "data.lib.growth_expectation_engine.compute_growth_expectation_diagnostic",
        forbidden,
    )
    build_shared_diagnostic_proof(diagnostic=artifact, **_proof_kwargs(artifact))

    assert artifact == original


def test_shared_diagnostic_finding_is_excluded_from_council_increment():
    result = classify_council_increment(
        baseline=[
            {"fingerprint": "baseline-risk", "kind": "risk", "summary": "已有风险"},
        ],
        council=[
            {
                "fingerprint": "growth-share",
                "kind": "shared_diagnostic",
                "summary": "未来价值占比 50%",
                "diagnostic_digest": "d" * 64,
                "metric": "future_value_share",
            },
            {"fingerprint": "baseline-risk", "kind": "risk", "summary": "已有风险"},
        ],
        diagnostic_digest="d" * 64,
    )

    assert result["increment_count"] == 0
    assert result["excluded_shared"] == ("growth-share",)
    assert result["duplicates"] == ("baseline-risk",)


def test_only_new_substantive_findings_count_as_council_increment():
    result = classify_council_increment(
        baseline=[],
        council=[
            {"fingerprint": "counter-1", "kind": "counter_evidence", "summary": "反证"},
            {"fingerprint": "risk-1", "kind": "risk", "summary": "风险"},
            {"fingerprint": "variable-1", "kind": "key_variable", "summary": "变量"},
            {
                "fingerprint": "assumption-1",
                "kind": "assumption_challenge",
                "summary": "质疑假设",
            },
        ],
    )

    assert result["increment_count"] == 4
    assert result["accepted"] == (
        "assumption-1",
        "counter-1",
        "risk-1",
        "variable-1",
    )


def test_unsupported_council_finding_kind_fails_closed():
    with pytest.raises(SharedDiagnosticProofError, match="kind"):
        classify_council_increment(
            baseline=[],
            council=[
                {"fingerprint": "style-only", "kind": "rewritten", "summary": "改写"},
            ],
        )


def test_duplicate_council_findings_are_preserved_in_audit_classification():
    result = classify_council_increment(
        baseline=[],
        council=[
            {"fingerprint": "same", "kind": "risk", "summary": "风险"},
            {"fingerprint": "same", "kind": "risk", "summary": "风险重复"},
        ],
    )

    assert result["increment_count"] == 1
    assert result["accepted"] == ("same",)
    assert result["duplicates"] == ("same",)


def test_shared_diagnostic_finding_requires_matching_metric_and_digest():
    with pytest.raises(SharedDiagnosticProofError, match="supported metric"):
        classify_council_increment(
            baseline=[],
            council=[
                {
                    "fingerprint": "not-shared",
                    "kind": "shared_diagnostic",
                    "summary": "冒充共享计算",
                    "diagnostic_digest": "d" * 64,
                    "metric": "not-a-diagnostic-metric",
                }
            ],
            diagnostic_digest="d" * 64,
        )


def test_shared_diagnostic_classifier_rejects_malformed_digest():
    with pytest.raises(SharedDiagnosticProofError, match="diagnostic_digest"):
        classify_council_increment(
            baseline=[],
            council=[
                {
                    "fingerprint": "shared",
                    "kind": "shared_diagnostic",
                    "summary": "共享计算",
                    "diagnostic_digest": "short",
                    "metric": "future_value_share",
                }
            ],
            diagnostic_digest="short",
        )


def test_duplicate_shared_finding_is_validated_before_duplicate_classification():
    with pytest.raises(SharedDiagnosticProofError, match="diagnostic_digest"):
        classify_council_increment(
            baseline=[
                {"fingerprint": "same", "kind": "risk", "summary": "基线风险"},
            ],
            council=[
                {
                    "fingerprint": "same",
                    "kind": "shared_diagnostic",
                    "summary": "伪造共享诊断",
                    "diagnostic_digest": "x" * 64,
                    "metric": "future_value_share",
                }
            ],
            diagnostic_digest="d" * 64,
        )
