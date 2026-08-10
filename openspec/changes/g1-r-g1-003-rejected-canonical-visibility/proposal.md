## Why

Repair `R-G1-003` in the archived `g1-field-qualification-canonical-promotion` flow. Promotion currently forwards only `decision["promoted_evidence"]` to the canonical snapshot writer, so rejected in-policy fields disappear and downstream readers cannot distinguish an explicit qualification failure from missing data.

## What Changes

- Pass all in-policy evaluated evidence from promotion to the canonical snapshot writer.
- Preserve qualified fields as `production_eligible` with their canonical values.
- Preserve rejected fields as `not_qualified` with an explicit `null` canonical value, rejection reason, provenance, and sidecar evidence.
- Cover qualified/rejected mixtures, all-rejected runs, rejection statuses, identity consistency, source immutability, and reader-only snapshot consumption with regression tests.
- Keep the existing snapshot schema, status enums, qualification policy, ranking, and downstream consumers unchanged.

## Capabilities

### New Capabilities

- None. This is a repair to the archived field qualification/canonical promotion contract, not a new product capability.

### Modified Capabilities

- None. The archived capability remains the contract owner; this child records and repairs its rejected-evidence visibility gap.

## Impact

- Affected code: `value-screener/scripts/promote_provider_snapshot.py`, existing canonical snapshot and field qualification tests, and the active child OpenSpec artifacts.
- No new dependency, provider call, LLM call, ranking change, production-path validator, or canonical snapshot consumer migration.
- Canonical promotion output will expose rejected in-policy evidence instead of omitting it.
