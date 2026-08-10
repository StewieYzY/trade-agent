## 1. Contract and RED tests

- [x] 1.1 Add staged runtime test fixtures with complete, degraded, failed,
  record-not-found, invalid, not-evaluated, stale, and cache-hit outcomes.
- [x] 1.2 Add RED tests proving Stage A/B/C receive only the intended ticker
  sets and requested dimensions, including exclusion of all G2 dossier dimensions.
- [x] 1.3 Add RED tests for single-ticker failure isolation, monotonic ticker
  counts, auditable provider/cache evidence, and canonical field metadata retention.
- [x] 1.4 Add RED tests proving the runtime performs no LLM/network/production
  writes when using injected fakes.

## 2. Minimal staged runtime implementation

- [x] 2.1 Add a narrow fetch telemetry contract to `BatchFetcher` that records
  requested ticker, dimension, provider-call, cache-hit, and failure outcomes
  without changing existing fetch semantics.
- [x] 2.2 Add `screener/staged_runtime.py` with explicit Stage A/B/C allowlists,
  input/output ticker propagation, failure-visible status handling, and run-scoped
  in-memory evidence.
- [x] 2.3 Reuse existing hard gates, factor scores, anti-trap, and heat filter
  functions at their stage-specific dependency boundaries without changing ranking
  formulas or downstream G2 modules.
- [x] 2.4 Add the canonical consumer adapter needed to retain
  value/status/reason/provenance/as_of/freshness metadata without writing or
  mutating snapshots.

## 3. Verification and handoff

- [x] 3.1 Run focused staged runtime RED/GREEN tests and related screener,
  BatchFetcher, canonical snapshot, identity, and production-path tests.
- [x] 3.2 Run the full `value-screener/.venv/bin/pytest` suite if the project
  virtual environment and pytest executable are present; otherwise record the
  exact environment limitation and remaining risk.
- [x] 3.3 Run `openspec validate --all --strict`, compileall, and `git diff --check`.
- [x] 3.4 Perform independent scope/risk review, update the rolling handoff with
  Stage A/B/C evidence, and leave the child unarchived and unpushed.
