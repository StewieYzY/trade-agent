## 1. OpenSpec and baseline contract

- [x] 1.1 Validate the M2.1 child artifacts against G2 umbrella task 6.1, the M0.2 reuse boundary, and the explicit non-goals.
- [x] 1.2 Define the public fixed baseline input, record, comparison, rendering, and output-isolation contracts through focused tests.

## 2. RED-first vertical slices

- [x] 2.1 RED→GREEN baseline input identity/digest binding and structural preflight records with zero provider calls.
- [x] 2.2 RED→GREEN one-attempt M0.2 execution record with exact fake LLM call signature, model/reasoning/budget identity, usage, status, and output digest.
- [x] 2.3 RED→GREEN repeated-run comparison for stable fields, allowed output drift, quality transitions, structural failures, and token/cost deltas.
- [x] 2.4 RED→GREEN deterministic JSON/Markdown record and comparison artifacts confined to explicit output directories.
- [x] 2.5 RED→GREEN provider/schema failure, output degraded, agent skip/out-of-circle, dossier failure, and diagnostic `not_evaluable`/`failed` semantics.
- [x] 2.6 Verify the public Python runner/comparison entrypoints and that comparison never invokes a provider.

## 3. Regression and verification

- [x] 3.1 Run the focused M2.1 test file and M0.2 regression test.
- [x] 3.2 Run the full pytest suite and compileall with the approved project virtual environment.
- [x] 3.3 Run strict OpenSpec validation and `git diff --check`; record that npm lint is not applicable because no matching package script exists.

## 4. Independent review and closure

- [x] 4.1 Perform one fresh read-only child-only review and resolve or explicitly retain each in-scope P0/P1/P2 finding.
- [x] 4.2 Re-run focused/full verification after review, then archive the OpenSpec child and commit only child-scoped files.
- [x] 4.3 Merge the child into `main`, push `origin/main`, and re-run key tests plus strict OpenSpec validation on merged main.
- [x] 4.4 Remove only the child branch/worktree, verify root WIP is unchanged, and report engineering/capability/Gate/provider/user-review/M2.2 status separately.

## 5. Real-provider evidence repair

- [x] 5.1 Record the fixed-input three-attempt real-provider result and restore this same change for an evidence-driven repair without creating another child change.
- [x] 5.2 Perform one bounded diagnostic call that captures the raw AgentOutput outside Git and identifies one root cause without changing prompt, profile, or model.
- [x] 5.3 RED→GREEN the smallest grounding regression that distinguishes supported input-unit normalization from fabricated numbers.
- [x] 5.4 Re-run M2.1 focused tests, M0.2/grounding regressions, full pytest, compileall, strict OpenSpec validation, and diff checks.
- [x] 5.5 Re-run the same frozen real input once under a new attempt identity when the repair changes real output validation; preserve the prior failed evidence.
- [x] 5.6 Perform one fresh read-only review limited to this repair and resolve or explicitly retain every in-scope finding.
- [x] 5.7 Re-archive this same change and commit only repair-scoped files.
- [x] 5.8 Merge into `main`, push `origin/main`, verify merged main, remove only the repair branch/worktree, and retain `capability_status=not_evidence` plus `gate_status=not_passed`.
