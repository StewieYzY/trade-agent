## ADDED Requirements

### Requirement: Canonical snapshot consumer validates run identity
The consumer SHALL read `manifest.json`, `records.json`, and `provenance.json`
from one snapshot run and SHALL fail closed when any required file is missing,
malformed, or has an unsupported `schema_version`.

#### Scenario: Complete snapshot is consumable
- **WHEN** all three files exist and the schema version is supported
- **THEN** the consumer returns a read-only consumer object for the requested run

#### Scenario: Required file is missing
- **WHEN** manifest, records, or provenance is absent
- **THEN** the consumer rejects the snapshot with a contract error

#### Scenario: Schema version is unsupported
- **WHEN** manifest schema_version does not equal the supported consumer schema
- **THEN** the consumer rejects the snapshot before exposing any field value

### Requirement: Consumer binds expected run, plan, ticker and ticker-set identity
The consumer SHALL verify `run_id`, `plan_version`, canonical ticker identity, and
`ticker_set_hash` against explicit caller expectations and SHALL reject mismatches.

#### Scenario: Run or plan identity mismatches
- **WHEN** manifest run_id or plan_version differs from the expected values
- **THEN** the consumer rejects the snapshot

#### Scenario: Ticker identity mismatches
- **WHEN** a requested ticker is not represented by its canonical ticker identity
- **THEN** the consumer rejects the snapshot

#### Scenario: Ticker-set hash mismatches
- **WHEN** manifest ticker_set_hash differs from the canonical expected ticker set
- **THEN** the consumer rejects the snapshot

#### Scenario: Snapshot ticker-set hash uses the snapshot identity contract
- **WHEN** the caller supplies `compute_snapshot_ticker_set_hash` for the expected
  canonical ticker set
- **THEN** a matching snapshot is accepted, and the separate
  `compute_input_ticker_set_hash` contract is not required or substituted

### Requirement: Consumer returns field-level value and provenance contract
For each requested ticker and field, the consumer SHALL return `value`, `status`,
`reason`, `provenance`, `as_of`, and `freshness` without requiring downstream callers
to inspect `decision.json` or infer state from missing keys.

#### Scenario: Production-eligible field is available
- **WHEN** a field has available status, production eligibility, and fresh evidence
- **THEN** the consumer returns its canonical value and associated provenance metadata

#### Scenario: Rejected field is explicit
- **WHEN** a field is rejected or not evaluated
- **THEN** the consumer returns `value` as null together with status, reason, and provenance

#### Scenario: Mixed qualified and rejected fields are consumed
- **WHEN** a snapshot contains both qualified and rejected fields
- **THEN** each field preserves its own value/state independently

### Requirement: Unavailable statuses never become available
The consumer SHALL treat `record_not_found`, `source_failed`, `invalid_value`,
`not_evaluated`, `stale`, `degraded`, and other non-qualified states as unavailable.
Unavailable fields MUST return explicit null and MUST NOT be substituted by defaults,
first-non-empty selection, or fallback values.

#### Scenario: Failure and invalid statuses remain unavailable
- **WHEN** a field has record_not_found, source_failed, invalid_value, or not_evaluated status
- **THEN** the consumer returns null and the original status/reason

#### Scenario: Stale or degraded evidence remains unavailable
- **WHEN** a field is stale or degraded
- **THEN** the consumer does not expose it as available

#### Scenario: Freshness metadata is missing
- **WHEN** a field has otherwise eligible evidence but no freshness status
- **THEN** the consumer returns explicit null and `available` is false

### Requirement: Records and provenance identity must agree
The consumer SHALL reject snapshots when a provenance field identity, ticker identity,
or run identity does not match the corresponding records and manifest identity.

#### Scenario: Field identity mismatch fails closed
- **WHEN** provenance identifies a different ticker or field than the records entry
- **THEN** the consumer rejects the snapshot

#### Scenario: Records value differs from provenance value
- **WHEN** a snapshot-consumable field has a records value different from its
  provenance value
- **THEN** the consumer rejects the snapshot

### Requirement: Consumer is read-only and has no production side effects
The consumer SHALL not call providers or LLMs and SHALL not write or modify canonical
snapshot, cache, watchlist, debate, ranking, or production snapshot artifacts.

#### Scenario: Input files remain unchanged
- **WHEN** a valid snapshot is consumed
- **THEN** all input file bytes remain unchanged

#### Scenario: No external execution path is triggered
- **WHEN** a snapshot is consumed
- **THEN** provider, LLM, cache, and production-path calls are not made

#### Scenario: Consumer metadata is deeply read-only
- **WHEN** a caller attempts to mutate nested manifest or provenance metadata
- **THEN** the consumer raises a read-only error and its state remains unchanged
