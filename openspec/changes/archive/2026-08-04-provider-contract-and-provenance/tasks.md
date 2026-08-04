## 1. Contract model

- [x] 1.1 Define provider status, integration eligibility, provenance, and field evidence schemas without adding dependencies.
- [x] 1.2 Define required metadata rules for numeric, financial, valuation, price, ratio, text, and historical fields.
- [x] 1.3 Define JSON-safe serialization and sensitive error redaction.

## 2. Validation and conflict handling

- [x] 2.1 Implement field evidence validation with explicit missing metadata and failure-state semantics.
- [x] 2.2 Implement multi-provider conflict detection for value, unit, currency, report period, and freshness.
- [x] 2.3 Preserve all source evidence while preventing implicit first-non-empty or stale-value override.
- [x] 2.4 Keep candidate provider eligibility at `not_qualified`/`shadow_only` unless an explicit later policy promotes it.

## 3. Compatibility boundary

- [x] 3.1 Implement sidecar metadata generation for existing fetcher payloads without changing legacy consumer payloads.
- [x] 3.2 Add qualification-evidence to contract conversion while preserving response hashes and provider provenance.
- [x] 3.3 Ensure contract artifacts cannot write or mutate production cache, ranking, snapshot, debate, watchlist, or diagnostic paths.

## 4. Verification and handoff

- [x] 4.1 Add deterministic tests for valid evidence, missing provenance, time/unit/currency gaps, and all failure statuses.
- [x] 4.2 Add tests for sensitive error redaction, JSON serialization, conflict detection, stale data, and sidecar compatibility.
- [x] 4.3 Run focused tests, strict OpenSpec validation, compile check, and diff check.
- [x] 4.4 Produce a dated contract decision and keep canonical snapshot sync as a separate child.
