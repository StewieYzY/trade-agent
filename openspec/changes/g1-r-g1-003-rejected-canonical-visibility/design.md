## Context

This child repairs `R-G1-003` under the archived `g1-field-qualification-canonical-promotion` change. The qualification evaluator already validates source evidence, returns `promoted_evidence` for qualified groups, and retains rejected decisions in `decision.json`. The promotion entrypoint currently passes only `promoted_evidence` to `write_snapshot`, so rejected in-policy evidence never reaches `canonical_snapshot.build_snapshot()`.

The existing snapshot writer already supports fail-closed records: non-eligible evidence produces an explicit `null` record value and a provenance sidecar. The smallest safe repair is therefore at the promotion-to-writer boundary, while preserving the existing schema, status enums, qualification policy, and source-run immutability.

## Goals / Non-Goals

**Goals:**

- Pass all in-policy evaluated evidence into the canonical writer for a promotion that has evaluated field groups.
- Mark qualified evidence `production_eligible` and retain its value.
- Mark rejected evidence `not_qualified`, retain its source status/reason/provenance, and expose it in canonical records and sidecar with an explicit `null` value.
- Preserve mixed qualified/rejected fields, all-rejected semantics, source immutability, and snapshot identity.
- Make `read_snapshot()` sufficient for determining field status without reading `decision.json`.

**Non-Goals:**

- No changes to qualification policy, status/eligibility enums, ranking, cache, provider adapters, LLM calls, production-path isolation, or downstream canonical consumers.
- No default values, fallback provider values, live runs, runtime artifacts, or archived Change edits.

## Decisions

### D1. Reuse evaluated evidence as the writer input

Add a decision payload containing all evaluated in-policy evidence, with qualified items carrying `production_eligible` and rejected items carrying `not_qualified`. The promotion entrypoint passes that payload to `write_snapshot()`.

Alternative rejected: reconstructing rejected items from decision summaries. That would lose the original field-level status, reason, provenance, response hash, and ticker identity.

### D2. Keep canonical writer semantics unchanged

Do not add a second status model or special promotion-only serialization path. Existing `build_snapshot()` logic remains responsible for deciding whether each evidence item is consumable; rejected items become `null` records and remain in `provenance.json`.

Alternative rejected: changing the snapshot schema or making the reader join `decision.json`. That would preserve the visibility bug at the consumer boundary and widen scope.

### D3. Separate promotion status from snapshot visibility

Promotion may remain `blocked` when no group qualifies, but when evaluated evidence exists it SHALL still write a clear `not_qualified` snapshot containing all rejected evidence. This makes “no production-eligible values” distinct from “no snapshot was produced”.

Alternative rejected: keeping the current decision-only output for all-rejected runs. It leaves downstream readers unable to distinguish an absent snapshot from an explicit rejected snapshot.

### D4. Lock the boundary with integration tests

Add focused tests at the promotion boundary for mixed and all-rejected runs, each rejection status, explicit nulls, sidecar/provenance, identity hashes, reader-only consumption, and source immutability. Preserve existing lower-level canonical snapshot tests.

### D5. Keep the decision schema version and make the additive field explicit

Keep `g1-field-qualification-decision-v1` because `evaluated_evidence` is an additive field and existing readers can ignore unknown JSON keys; the canonical snapshot schema and status/eligibility enums remain unchanged. The active child spec and tests treat the field as part of the v1 decision contract, so future incompatible decision changes must use a new schema version.

## Risks / Trade-offs

- [Existing callers rely on blocked promotion having no records] → Update only the R-G1-003 promotion contract and test the new explicit not-qualified snapshot semantics; do not alter unrelated callers.
- [Rejected evidence has malformed fields] → Continue using `validate_field_evidence()` and fail closed; never synthesize values or provenance.
- [Decision and snapshot can diverge] → Include source run/evidence hashes and snapshot identity in the snapshot manifest and assert them in integration tests.

## Migration Plan

1. Add RED tests to the active child test module.
2. Change only the promotion-to-writer evidence selection and all-rejected output path.
3. Run focused promotion/canonical/qualification tests, then related full tests and strict validation.
4. Perform an independent read-only review before changing the repair status or considering archive.

Rollback is reverting the active child commit; qualification source artifacts remain untouched.
