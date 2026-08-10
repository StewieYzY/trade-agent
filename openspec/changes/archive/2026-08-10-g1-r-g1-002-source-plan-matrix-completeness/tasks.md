## 1. OpenSpec contract

- [x] 1.1 Record `R-G1-002`, the archived Change reference, scope boundaries, source artifact contract, and probe-plan binding.
- [x] 1.2 Define deterministic rejection reasons and required matrix semantics in the active spec.

## 2. RED tests

- [x] 2.1 Add tests for missing/truncated plan artifacts and source identity mismatches.
- [x] 2.2 Add tests for plan/evidence/manifest hash mismatch and evidence tampering.
- [x] 2.3 Add tests for missing/partial required field groups and wrong or unbound CLI probe-plan versions.
- [x] 2.4 Add tests for a complete legal source run and byte-for-byte source immutability through promotion.

## 3. Minimal implementation

- [x] 3.1 Make the runner persist plan/evidence/manifest artifact hashes and explicit source identities.
- [x] 3.2 Make the qualification loader validate frozen plan, artifact hashes, and run/ticker/field/evidence identity.
- [x] 3.3 Make evaluator decisions cover the full policy-required field matrix and fail closed on missing groups.
- [x] 3.4 Bind promotion CLI policy construction to `PROBE_PLAN_VERSION` with explicit mismatch errors.

## 4. Verification and evidence

- [x] 4.1 Run R-G1-002 focused RED/GREEN tests and related qualification/promotion tests.
- [x] 4.2 Run strict OpenSpec validation, compileall, and `git diff --check`.
- [x] 4.3 Inspect the worktree for generated live provider, LLM, cache, watchlist, debate, or canonical runtime artifacts.
- [x] 4.4 Record implementation/test evidence while keeping `R-G1-002` open for independent review; do not archive or claim G1/G2 capability passage.
