## 1. RED coverage

- [x] 1.1 Add a promotion integration fixture with one qualified field group and one `source_failed` field group, asserting both reach canonical records and sidecar.
- [x] 1.2 Add rejection-status coverage for `record_not_found`, `invalid_value`, and `not_evaluated`, asserting explicit null values and preserved status/reason/provenance.
- [x] 1.3 Add all-rejected and reader-only snapshot tests covering self-sufficient status visibility, snapshot identity, ticker/run/source hashes, and source evidence immutability.
- [x] 1.4 Run the new focused tests against the baseline and record the expected RED failures caused by the current `promoted_evidence` boundary.

## 2. Minimal implementation

- [x] 2.1 Extend the qualification decision payload with all in-policy evaluated evidence while preserving qualified/rejected eligibility semantics and source immutability.
- [x] 2.2 Change promotion to pass all evaluated evidence to the existing canonical snapshot writer and write an explicit not-qualified snapshot when no field is production eligible.
- [x] 2.3 Preserve existing schema, status enums, provenance, sidecar, run identity, and protected output behavior without changing ranking or consumers.

## 3. Verification and handoff

- [x] 3.1 Run focused R-G1-003 tests and the related qualification, canonical snapshot, and promotion tests.
- [x] 3.2 Run the relevant full pytest scope, `compileall`, `git diff --check`, and `openspec validate --all --strict`; record exact results.
- [x] 3.3 Perform an independent read-only review of diff, tests, OpenSpec contract, and output semantics; resolve findings before changing R-G1-003 status.
- [x] 3.4 Update the R-G1-003 rolling handoff/evidence with branch, worktree, commit, tests, residual risks, and the fact that archive and closure remain pending review.

## 4. Review follow-up

- [x] 4.1 Add fail-closed top-level/provenance identity mismatch validation and rejected-status coverage for all existing non-available status enums.
- [x] 4.2 Run fresh full verification and complete a new independent read-only review before any closure/archive decision.
