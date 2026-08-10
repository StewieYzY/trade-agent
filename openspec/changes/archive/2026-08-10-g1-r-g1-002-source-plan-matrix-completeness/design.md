## Context

This is the active implementation carrier for `R-G1-002`, following the archived
`g1-field-qualification-canonical-promotion` change. The qualification runner
already writes a frozen probe plan and run-scoped artifacts, while the promotion
loader only checks `manifest.json`, `evidence.json`, completion status, and an
evidence count. The repair must make the existing source contract self-verifying
without changing eligibility semantics or downstream consumers.

## Goals / Non-Goals

**Goals:**

- Make a completed source run acceptable only when `plan.json`, `evidence.json`,
  and `manifest.json` are valid, internally consistent, and hash-verifiable.
- Verify every evidence item's run/ticker/method/field identity against the
  frozen plan and manifest.
- Evaluate the full policy-required `(method, field)` matrix and reject missing
  groups as a deterministic blocked decision.
- Make the promotion CLI explicitly use the runner's `PROBE_PLAN_VERSION`.
- Keep source files unchanged and preserve their bytes through promotion.

**Non-Goals:**

- No provider calls, LLM calls, retries, cache writes, watchlist/debate/ranking
  changes, provider eligibility changes, canonical policy changes, or consumer
  implementation.
- No weakening of existing policy checks and no default values for missing data.
- No changes to the archived OpenSpec change.

## Decisions

1. **Source validation remains at the loader boundary.** `load_qualification_run`
   will load and validate the three source artifacts before policy evaluation.
   This prevents callers from bypassing plan/hash/identity checks while retaining
   the existing evaluator API.
2. **Artifact hashes are byte-derived.** Hashes are computed from the exact UTF-8
   bytes on disk, with a canonical JSON hash only where the runner already needs
   a semantic plan hash. Manifest fields record the artifact paths and hashes;
   mismatches fail closed.
3. **The plan is authoritative for coverage.** A plan case expands to the
   expected ticker/method/field identities. Evidence outside the plan is
   rejected, and every planned field group must be represented before any group
   can be promoted.
4. **Probe version is a shared explicit constant.** The promotion CLI imports
   `PROBE_PLAN_VERSION` and passes it into the policy as the required
   `probe_plan_version`; a user-supplied mismatching policy version is rejected
   rather than silently creating a new plan identity.
5. **Source immutability is tested at bytes level.** Promotion continues to write
   only to its isolated output root; tests snapshot all source artifact bytes
   before and after promotion.

## Risks / Trade-offs

- [Historical fixture runs lack new hashes] → They are rejected as incomplete
  source runs; tests and future runner output use the complete contract.
- [Policy matrix is larger than a fixture] → Tests use a small explicit matrix,
  while the validator checks all declared plan/policy groups without defaults.
- [Manifest JSON formatting changes] → Hash validation uses the bytes recorded by
  the runner, so only artifact tampering or mismatched metadata is rejected.

## Migration Plan

1. Add the active child artifacts and RED tests.
2. Update the runner to emit plan/evidence/manifest hash metadata and update the
   loader/promotion/CLI to validate it.
3. Run focused tests, related tests, strict OpenSpec validation, compileall, and
   diff checks.
4. Keep `R-G1-002` in independent-review state; do not archive or mark closed.

Rollback is limited to reverting this child implementation; source qualification
runs and production consumers are not modified.
