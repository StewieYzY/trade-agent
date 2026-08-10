# R-G1-004 Production-Path Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all G1 health, qualification/promotion, batch, and canonical snapshot entrypoints reject paths that can mutate resolved production roots while allowing caller-owned external run-scoped output roots.

**Architecture:** Add one standard-library-only path boundary module under `data/lib`. It resolves the `value-screener` production roots once and compares both lexical absolute paths and `realpath` paths, rejecting protected roots, descendants, ancestors, and symlink escapes. The four G1 entrypoints call this validator before provider/evaluation/artifact work.

**Tech Stack:** Python 3.10+, pathlib, pytest, OpenSpec.

## Global Constraints

- Work only in `codex/r-g1-004-production-path-isolation-mainline`.
- Preserve the main worktree's three untracked assets.
- Do not add dependencies, call real providers/LLMs, change ranking/provider eligibility/canonical field policy, implement R-G2-003, archive, or push.
- Keep fixture/reference evidence separate from live capability evidence.
- Use RED → minimal implementation → focused GREEN → related/full verification → strict validation → independent review.

### Task 1: Shared validator contract and RED coverage

**Files:**
- Create: `value-screener/data/lib/production_paths.py`
- Create: `value-screener/tests/test_production_path_isolation.py`

**Interfaces:**
- Produce `ProductionPathViolation`, `resolve_g1_production_roots()`, and `validate_g1_output_root()`.
- The validator returns the resolved allowed root and raises a stable exception before side effects.

- [ ] Write tests for exact, descendant, ancestor, symlink, and normal external output paths.
- [ ] Write entrypoint tests proving health, promotion, batch, and canonical paths reuse the validator.
- [ ] Write fail-closed assertions for no artifact creation and no provider/evaluation calls.
- [ ] Run the focused test file and confirm RED failures are caused by the missing shared interface.

### Task 2: Minimal G1 entrypoint integration

**Files:**
- Modify: `value-screener/scripts/provider_qualification.py`
- Modify: `value-screener/scripts/promote_provider_snapshot.py`
- Modify: `value-screener/data/lib/provider_batch_adapter.py`
- Modify: `value-screener/data/lib/canonical_snapshot.py`

- [ ] Implement the shared resolver and containment checks.
- [ ] Replace duplicated output-root guards with the shared validator.
- [ ] Ensure validation occurs before provider invocation, qualification evaluation, snapshot writes, or run-directory creation.
- [ ] Run the new focused tests and related provider health/qualification/promotion/canonical tests.

### Task 3: OpenSpec and handoff evidence

**Files:**
- Modify: `openspec/changes/g1-provider-health-and-failure-visibility/proposal.md`
- Modify: `openspec/changes/g1-provider-health-and-failure-visibility/design.md`
- Modify: `openspec/changes/g1-provider-health-and-failure-visibility/tasks.md`
- Modify: `openspec/changes/g1-provider-health-and-failure-visibility/specs/provider-health-and-failure-visibility/spec.md`
- Create: `openspec/changes/g1-provider-health-and-failure-visibility/evidence.md`
- Modify: `design/capability-gate-and-execution-handoff-2026-08-06.md`
- Create: `design/m1-m2-g1-r-g1-004-production-path-isolation-rolling-handoff-2026-08-10.md`

- [ ] Record R-G1-004 requirements, tasks, verification evidence, and remaining independent-review status.
- [ ] Keep the repair open until independent review; do not archive or claim capability passage.
- [ ] Run focused/related/full pytest, compileall, strict OpenSpec validation, and diff check.
