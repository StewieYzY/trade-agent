## 1. Snapshot model and identity

- [x] 1.1 Define canonical snapshot record, sidecar, manifest, schema version, and immutable run identity.
- [x] 1.2 Implement stable ticker-set hash and source-set hash from provenance/status evidence.
- [x] 1.3 Reject unsafe or duplicate run_id/output paths before writing.

## 2. Sync and reader

- [x] 2.1 Implement conversion from provider contract evidence to canonical value plus sidecar metadata.
- [x] 2.2 Implement atomic run writer for manifest, plan, records, and provenance artifacts.
- [x] 2.3 Preserve failed, conflicted, stale, shadow, and not-evaluated fields as visible null/status.
- [x] 2.4 Implement legacy-like reader without changing existing cache or ranking consumers.

## 3. Isolation and compatibility

- [x] 3.1 Ensure snapshot sync never mutates legacy cache, ranking inputs, debate, watchlist, or diagnostic paths.
- [x] 3.2 Preserve source-set and field evidence hashes across write/read round trips.
- [x] 3.3 Keep LongPort/Longbridge shadow evidence out of production canonical values.

## 4. Verification and handoff

- [x] 4.1 Add deterministic tests for immutable runs, duplicate ids, hashes, sparse records, conflicts, and failures.
- [x] 4.2 Add tests for legacy reader compatibility and no cache mutation.
- [x] 4.3 Run focused tests, strict OpenSpec validation, compile check, and diff check.
- [x] 4.4 Produce a dated snapshot decision; keep batch adapter and staged screening as separate children.
