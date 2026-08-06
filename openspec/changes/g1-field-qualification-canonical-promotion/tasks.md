## 1. OpenSpec contract

- [x] 1.1 Freeze the field qualification policy version, five canonical tickers, method/field matrix, and group-level decision statuses.
- [x] 1.2 Define source-run completeness checks, policy hash, decision schema, promotion manifest, and protected output boundary.

## 2. Field qualification evaluator

- [x] 2.1 Add failing tests for incomplete source runs, evidence count mismatch, unexpected ticker/field, missing provenance/time basis, and rejected statuses.
- [x] 2.2 Implement source-run loading and explicit policy validation without modifying source artifacts.
- [x] 2.3 Add failing tests for complete groups, missing ticker coverage, duplicate evidence, metadata conflicts, stale/unknown freshness, and candidate-provider isolation.
- [x] 2.4 Implement deterministic group evaluation and promoted evidence copies with explicit rejection reasons.

## 3. Canonical promotion entrypoint

- [x] 3.1 Add failing tests for decision artifact, canonical snapshot output, duplicate run IDs, protected paths, and source-run immutability.
- [x] 3.2 Implement the run-scoped promotion script using the existing canonical snapshot writer.
- [x] 3.3 Add CLI argument validation and stable decision/source hashes.

## 4. Verification and handoff

- [x] 4.1 Run focused field qualification, canonical snapshot, and provenance tests with the repository venv.
- [x] 4.2 Run strict OpenSpec validation, compileall, full pytest, and git diff check; clean generated runtime artifacts.
- [x] 4.3 Write the dated implementation decision and update this task list only for verified tasks.

## 5. R-G1-001 repair: qualification runner provenance compatibility

- [x] 5.1 Add the minimal RED fixture covering `QualificationRunner output → evaluator → promotion`, and verify the current output is blocked by the missing provenance contract fields.
- [x] 5.2 Update `_field_evidence()` to mirror `market`, `ticker`, `raw_field`, and `response_hash` into `provenance` without changing evaluator or promotion policy.
- [x] 5.3 Add regression assertions for runner provenance mirroring and an integration assertion that promotion leaves the source qualification run byte-for-byte unchanged.
- [x] 5.4 Complete the repair attempt with focused tests, relevant full tests, strict validation, artifact/secret/live-output checks, and `git diff --check`; leave independent review as the next Repair state.

## 6. R-G1-001 independent-review follow-up

- [x] 6.1 Reproduce the review finding with `_meta`/field metadata that attempts to override provenance-reserved keys.
- [x] 6.2 Make canonical provenance fields authoritative by writing them after non-reserved metadata.
- [x] 6.3 Extend the runner-to-promotion integration test to assert final `provenance.json` identity/hash consistency and re-run the repair verification suite.
