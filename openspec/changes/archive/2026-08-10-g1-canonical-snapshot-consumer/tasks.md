## 1. Contract and RED tests

- [x] 1.1 Add consumer test fixtures for complete, mixed, rejected, stale, degraded, and malformed snapshots.
- [x] 1.2 Add RED tests for required files, schema version, run/plan/ticker/ticker-set identity, and records/provenance field identity.
- [x] 1.3 Add RED tests for available values, explicit null rejected fields, unavailable statuses, read-only behavior, and absence of provider/LLM/production side effects.

## 2. Minimal consumer implementation

- [x] 2.1 Add an independent read-only consumer module and explicit contract error type.
- [x] 2.2 Implement manifest/records/provenance loading and fail-closed structural and identity validation.
- [x] 2.3 Implement field-level output preserving value, status, reason, provenance, as_of, and freshness.
- [x] 2.4 Ensure non-qualified, rejected, not-evaluated, failed, invalid, stale, and degraded fields remain explicit null and unavailable.

## 3. Verification and handoff

- [x] 3.1 Run focused consumer tests and related canonical snapshot, provenance, identity, and screener tests.
- [x] 3.2 Run strict OpenSpec validation, compileall, and git diff checks; confirm no runtime artifacts or external calls were produced.
- [x] 3.3 Perform independent scope/risk review and update the Track A rolling handoff without claiming any G1/G2 Capability pass.
