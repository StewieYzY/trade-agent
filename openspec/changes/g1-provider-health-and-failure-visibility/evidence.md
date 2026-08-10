# R-G1-004 implementation evidence

Repair ID: `R-G1-004`
Change: `g1-provider-health-and-failure-visibility`
Branch: `codex/r-g1-004-production-path-isolation-mainline`
Worktree: `.worktrees/r-g1-004-production-path-isolation-mainline`
Baseline: `main@b6db756`
Date: `2026-08-10`

## Root cause and implementation

The prior health/promotion guards constructed protected paths from the repository root,
while the runtime production directories live below `value-screener`. The repair adds
`value-screener/data/lib/production_paths.py` with:

- `resolve_g1_production_roots()`;
- `validate_g1_output_root()`;
- stable `ProductionPathViolation`;
- lexical absolute and resolved-path containment checks;
- exact, descendant, ancestor, and symlink/realpath escape rejection;
- external caller-owned run-scoped root acceptance.

The shared validator is used by:

- `scripts.provider_qualification.QualificationRunner`;
- `scripts.promote_provider_snapshot`;
- `data.lib.provider_batch_adapter.BatchAdapter`;
- `data.lib.canonical_snapshot.write_snapshot`.

Validation occurs before provider invocation, qualification evaluation, run-directory
creation, or snapshot artifact writing.

## RED evidence

The new focused test file was run before adding the shared module and failed at collection
with `ModuleNotFoundError: No module named 'data.lib.production_paths'`. This confirmed
the tests were exercising the missing production interface rather than passing against
existing behavior.

## Verification

- R-G1-004 + related provider health/qualification/promotion/canonical/batch and prior
  G1 repair tests: `157 passed`;
- repository-wide pytest: `719 passed in 53.97s`;
- `value-screener/.venv/bin/python -m compileall -q value-screener`: passed using the
  main project venv because the linked worktree has no separate `.venv`;
- `openspec validate --all --strict`: `28 passed, 0 failed`;
- `git diff --check`: passed;
- generated target-worktree `debate/`, `watchlist/`, and prior test runtime artifacts were
  inspected and removed; the main worktree's three protected untracked assets were not
  touched.

The subsequent independent CR found one P1: the historical `data/snapshots` and
`snapshots` roots were omitted from the shared protected set. This follow-up adds both
roots and regression tests. R-G1-004 remains in `independent_review` pending fresh
review. The normal post-validation TOCTOU window remains a residual risk; G2 fallback
consumption remains R-G2-003 scope.

No real provider or LLM was called. No G1/G2 Capability was passed. The owner Change
remains active and is not archived.
