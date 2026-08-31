## 1. Contract fixtures and RED tests

- [x] 1.1 Define the M1.2 fixture envelope, five-dimensional fetch result shape, canonical identity, and fixture provenance test helpers.
- [x] 1.2 Add RED tests for explicit input/hash/provenance validation and provider/LLM/cache isolation.
- [x] 1.3 Add RED tests for Stage A/B/C boundaries, single-ticker failure visibility, and candidate/non-candidate score semantics.
- [x] 1.4 Add RED tests for deterministic ordering, quality-status aggregation, and run-scoped output filenames.

## 2. Minimal offline implementation

- [x] 2.1 Implement the in-memory fixture fetcher and input adapter without changing existing L1 rules or `BatchFetcher`.
- [x] 2.2 Implement per-ticker result aggregation with stage statuses, exclusion reason, quality status, candidate flag, and available scores.
- [x] 2.3 Implement deterministic JSON/Markdown renderers with explicit fixture and `capability_status=not_evidence` markers.
- [x] 2.4 Add the `small-sample-run --input --output-dir` CLI command with safe input validation and run-scoped writes.

## 3. Regression and boundary verification

- [x] 3.1 Verify M1.1 selector/identity contracts remain compatible and the protected root `build_validation_sample.py` is untouched.
- [x] 3.2 Add integration tests proving no production cache, watchlist, debate, live evidence, provider, or LLM side effect.
- [x] 3.3 Run focused and related regression tests, preserving existing staged-runtime and screening behavior.

## 4. Closure

- [x] 4.1 Run `compileall`, `git diff --check`, and applicable OpenSpec strict validation.
- [x] 4.2 Perform one fresh child-only review from the current diff and resolve P0/P1/P2 findings within scope.
- [ ] 4.3 Archive the child, merge and push to `origin/main`, re-run merged-main validation, then remove only this child branch/worktree.
- [ ] 4.4 Record `engineering_status=merged`, `capability_status=not_evidence`, M1.3 pending, and G1 Capability Gate not passed.
