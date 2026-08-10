from __future__ import annotations

import sys
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.canonical_snapshot import write_snapshot  # noqa: E402
from data.lib.production_paths import (  # noqa: E402
    ProductionPathViolation,
    resolve_g1_production_roots,
    validate_g1_output_root,
)
from data.lib.provider_batch_adapter import BatchAdapter, ProviderSpec  # noqa: E402
from scripts.provider_qualification import (  # noqa: E402
    ProbeCase,
    ProviderAdapter,
    QualificationRunner,
)
from scripts.promote_provider_snapshot import promote_provider_snapshot  # noqa: E402
from data.lib.field_qualification import FieldQualificationPolicy  # noqa: E402


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _case() -> ProbeCase:
    return ProbeCase(
        ticker="600519.SH",
        market="SH",
        security_type="consumer",
        method="quote",
        fields=("last_price",),
    )


def _policy() -> FieldQualificationPolicy:
    return FieldQualificationPolicy.from_mapping(
        version="test-policy",
        tickers=["600519.SH"],
        methods={"quote": ["last_price"]},
        allowed_providers=["fixture"],
    )


@pytest.mark.parametrize(
    "candidate_factory",
    [
        lambda root: root,
        lambda root: root / "run-001",
        lambda root: root.parent,
    ],
    ids=["exact-root", "descendant", "ancestor"],
)
def test_production_roots_reject_exact_descendant_and_ancestor(candidate_factory):
    protected = _repo_root() / "value-screener" / "watchlist"

    with pytest.raises(
        ProductionPathViolation,
        match="G1 protected production output root rejected",
    ):
        validate_g1_output_root(candidate_factory(protected))


def test_production_root_rejects_symlink_escape(tmp_path):
    protected = _repo_root() / "value-screener" / "watchlist"
    escaped = tmp_path / "external-link"
    escaped.symlink_to(protected, target_is_directory=True)

    with pytest.raises(
        ProductionPathViolation,
        match="G1 protected production output root rejected",
    ):
        validate_g1_output_root(escaped / "run-001")


def test_external_run_scoped_root_is_allowed(tmp_path):
    root = tmp_path / "qualification-output"

    assert validate_g1_output_root(root) == root.resolve()


def test_all_declared_g1_production_roots_are_protected():
    roots = resolve_g1_production_roots()

    assert any(root.name == "cache" for root in roots)
    assert any(root.name == "watchlist" for root in roots)
    assert any(root.name == "debate" for root in roots)
    assert any("ranking" in root.name for root in roots)
    assert any("canonical" in root.name for root in roots)
    assert any("diagnostic" in root.name for root in roots)
    for root in roots:
        with pytest.raises(ProductionPathViolation):
            validate_g1_output_root(root)


@pytest.mark.parametrize("relation", ["exact", "descendant", "ancestor"])
def test_every_declared_root_rejects_each_path_relationship(relation):
    for root in resolve_g1_production_roots():
        candidate = {
            "exact": root,
            "descendant": root / "run-001",
            "ancestor": root.parent,
        }[relation]
        with pytest.raises(ProductionPathViolation):
            validate_g1_output_root(candidate)


def test_symlink_loop_raises_stable_production_path_violation(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.symlink_to(second)
    second.symlink_to(first)

    with pytest.raises(
        ProductionPathViolation,
        match=r"^G1 protected production output root rejected: relation=unresolvable$",
    ):
        validate_g1_output_root(first / "run-001")


def test_relative_symlink_target_with_parent_components_cannot_escape(
    tmp_path,
):
    protected = _repo_root() / "value-screener" / "watchlist"
    link = tmp_path / "relative-link"
    link.symlink_to(os.path.relpath(protected, start=tmp_path))

    with pytest.raises(ProductionPathViolation):
        validate_g1_output_root(link / "run-001")


def test_production_path_error_does_not_expose_absolute_paths():
    protected = _repo_root() / "value-screener" / "watchlist"

    with pytest.raises(ProductionPathViolation) as error:
        validate_g1_output_root(protected)

    assert str(error.value) == (
        "G1 protected production output root rejected: relation=exact"
    )


def test_health_runner_rejects_before_provider_or_artifact_creation(tmp_path):
    invoke = Mock(return_value={"last_price": 1.0})
    protected = _repo_root() / "value-screener" / "watchlist"
    runner = QualificationRunner(
        adapters=[
            ProviderAdapter(
                "fixture",
                "fixture",
                invoke=invoke,
            )
        ],
        cases=[_case()],
        execution_mode="direct",
    )

    with pytest.raises(ProductionPathViolation):
        runner.run(output_root=protected, run_id="health-rejected")

    invoke.assert_not_called()
    assert not (protected / "health-rejected").exists()


def test_promotion_rejects_before_evaluation_or_artifact_creation(tmp_path, monkeypatch):
    evaluate = Mock(side_effect=AssertionError("evaluation must not run"))
    monkeypatch.setattr(
        "scripts.promote_provider_snapshot.evaluate_qualification_run",
        evaluate,
    )
    protected = _repo_root() / "value-screener" / "data" / "cache"

    with pytest.raises(ProductionPathViolation):
        promote_provider_snapshot(
            tmp_path / "qualification-run",
            output_root=protected,
            policy=_policy(),
            run_id="promotion-rejected",
        )

    evaluate.assert_not_called()
    assert not (protected / "promotion-rejected").exists()


def test_batch_rejects_before_provider_call_or_snapshot_write(tmp_path):
    fetch = Mock(return_value={"600519.SH": {"last_price": 1.0}})
    protected = _repo_root() / "value-screener" / "debate"
    adapter = BatchAdapter(
        [ProviderSpec("fixture", "fixture", fetch)],
    )

    with pytest.raises(ProductionPathViolation):
        adapter.run(
            tickers=["600519.SH"],
            method="quote",
            fields=["last_price"],
            output_root=protected,
            run_id="batch-rejected",
        )

    fetch.assert_not_called()
    assert not (protected / "batch-rejected").exists()


def test_canonical_entrypoint_rejects_before_writing_snapshot(tmp_path):
    protected = _repo_root() / "value-screener" / "data" / "canonical_snapshots"
    evidence = [
        {
            "ticker": "600519.SH",
            "field": "last_price",
            "value": 1.0,
            "status": "available",
            "eligibility": "production_eligible",
        }
    ]

    with pytest.raises(ProductionPathViolation):
        write_snapshot(
            evidence,
            tickers=["600519.SH"],
            plan_version="test",
            output_root=protected,
            run_id="canonical-rejected",
        )

    assert not (protected / "canonical-rejected").exists()
