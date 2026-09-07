## 1. OpenSpec and contract

- [x] 1.1 Confirm G1/M1.3 scope, M1.2 input identity, no-provider boundary, output states, and engineering/capability/Gate separation in proposal/design/spec.
- [x] 1.2 Define the public review record API, four feedback dimensions, strict input/output fields, issue categories, source digest binding, and run-scoped filenames in the design/spec.

## 2. RED-first focused tests

- [x] 2.1 Add a legal M1.2 result fixture helper and a failing template test for four dimensions, `template/not_evidence`, canonical sorting, source identity, and no output side effect on validation failure.
- [x] 2.2 Add failing feedback tests for all four statuses, preserved user text, required question/issue semantics, issue-category summary, and no automatic candidate/rule changes.
- [x] 2.3 Add failing renderer/digest/CLI tests for Markdown escaping, deterministic output, protected-path rejection, immutable same-run writes, different-run separation, and absence of provider/LLM/Council imports/calls.
- [x] 2.4 Run `PYTHONPATH=. /Users/admin/Documents/trade-agent/value-screener/.venv/bin/pytest -q tests/test_g1_small_sample_user_review.py` and record the expected feature-missing RED failure before production implementation.

## 3. Minimal implementation

- [x] 3.1 Implement strict M1.2 artifact validation, canonical ticker/hash/identity checks, optional Markdown identity validation, and deterministic source digest calculation in `value-screener/council/small_sample_user_review.py`.
- [x] 3.2 Implement template/completed feedback validation and record construction with four dimensions, raw user text preservation, status/capability/Gate semantics, explicit issue categories, and stable ticker ordering.
- [x] 3.3 Implement deterministic JSON/Markdown renderers with safe escaping, record digest validation, production-path isolation, atomic run-scoped writes, and immutable overwrite protection.
- [x] 3.4 Add the `small-sample-user-review` CLI command in `value-screener/cli.py` with required explicit paths and no external runtime initialization.

## 4. GREEN and regression

- [x] 4.1 Run focused M1.3 tests and iterate until GREEN without weakening fail-closed assertions.
- [x] 4.2 Run related regression:
  `PYTHONPATH=. /Users/admin/Documents/trade-agent/value-screener/.venv/bin/pytest -q tests/test_g1_small_sample_user_review.py tests/test_g1_mvp_small_sample_run.py tests/test_m0_single_stock_user_review.py`.
- [x] 4.3 Run full pytest, compileall, CLI help, `openspec validate --all --strict`, and `git diff --check`; record any unavailable npm lint script as not applicable.

## 5. Review and engineering closure

- [x] 5.1 Perform one fresh child-only review against baseline `0379bc531668489b0df7432af9176c39117a29ea`, focusing on scope, fail-closed validation, raw-text/Markdown safety, overwrite isolation, and missing tests; do not inspect or modify root WIP.
- [x] 5.2 Fix any P0/P1/P2 findings with RED-first regression tests; otherwise record no findings and residual risks.
- [x] 5.3 Re-run focused/related/full verification and strict validation after review fixes.
- [x] 5.4 Archive the OpenSpec change only after tasks/tests/review are complete; verify archive spec consistency.
- [x] 5.5 Commit child, merge into `main`, push `origin/main`, rerun merged-main verification, and remove only this child branch/worktree; preserve root user WIP.
- [x] 5.6 Record final states: `engineering_status=merged`, `capability_status=not_evidence`, `gate_status=not_passed`, `M0.3 real user review=completed`, `G1 Capability Gate=not_passed`.
