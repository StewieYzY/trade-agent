## 1. Adapter contract and tests

- [x] 1.1 Define explicit batch provider protocol, request identity, provider family, shadow flag, and call statistics.
- [x] 1.2 Add RED tests for multi-ticker response mapping, omitted ticker, unavailable provider, and duplicate provider calls.
- [x] 1.3 Add RED tests for provider/ticker failure isolation and classified sidecar evidence.

## 2. Evidence-preserving merge

- [x] 2.1 Implement batch invocation and canonical ticker validation without hidden SDK discovery.
- [x] 2.2 Convert batch responses to field-level provenance/status evidence with response hashes.
- [x] 2.3 Implement provider merge with agreement, conflict, unit/time mismatch, and stale handling.
- [x] 2.4 Keep shadow/not-qualified provider values out of production canonical values.

## 3. Snapshot integration

- [x] 3.1 Feed merged evidence into canonical snapshot writer without mutating legacy cache/ranking.
- [x] 3.2 Persist requested/returned/missing ticker sets, provider/method call counts, and run identity.
- [x] 3.3 Verify one provider failure or one ticker failure does not block independent records.

## 4. Verification and handoff

- [x] 4.1 Run focused adapter/snapshot/provenance tests and the existing 27-test boundary suite.
- [x] 4.2 Run strict OpenSpec validation, compile check, diff check, and inspect production path isolation.
- [x] 4.3 Execute real provider calls only if explicitly configured; otherwise preserve not_evaluated evidence.
- [x] 4.4 Produce a dated adapter decision and leave staged screening/performance Gate for separate children.
