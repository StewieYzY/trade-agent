## ADDED Requirements

### Requirement: Every started G2 run has an authoritative run-scoped quality record

The system SHALL persist a quality record for every non-preflight Council or fallback run, bound to canonical ticker and `run_id`, containing terminal status, reasons, completed stages, final-quality-gate result, execution mode, and artifact reference where applicable. The record SHALL remain readable regardless of cache eligibility.

#### Scenario: Warning record remains readable

- **WHEN** a started run finishes with a soft warning
- **THEN** a run-scoped record SHALL preserve `warning`, the warning reason, completed stages, and `final_quality_gate="warning"` for independent reads

#### Scenario: Interrupted run records unfinished stage

- **WHEN** an active run is interrupted during R2, DA, synthesis, final validation, or publishing
- **THEN** the record SHALL be `incomplete`, preserve completed stages, include the interrupted stage reason, and remain ineligible for success cache

### Requirement: Quality persistence is isolated and monotonic by ticker and run

The system SHALL store different `run_id` values independently under the requested canonical ticker, reject conflicting first writes, and refuse status upgrades that could turn a non-clean record into a clean success. Replacement SHALL preserve prior reasons and completed-stage evidence.

#### Scenario: Same ticker runs do not overwrite

- **WHEN** two runs for one canonical ticker use distinct `run_id` values
- **THEN** both records SHALL remain independently readable and neither write SHALL replace the other

#### Scenario: Status downgrade preserves reasons

- **WHEN** an existing run is later determined to be incomplete after a prior skip or warning
- **THEN** the replacement SHALL retain prior reasons and SHALL NOT upgrade the run back to `complete`

### Requirement: Corrupt, missing, or misbound quality proof fails closed

Cache and consumer recovery SHALL treat missing, malformed, schema-invalid, ticker-mismatched, `run_id`-mismatched, mode-mismatched, or artifact-path-mismatched quality records as invalid proof. Such evidence MUST NOT cause an older clean record to be selected for the same ticker.

#### Scenario: Corrupt latest record blocks older cache

- **WHEN** the newest quality record for a ticker is malformed while an older complete record exists
- **THEN** cache lookup SHALL miss rather than fall back to the older record

#### Scenario: Misbound artifact is rejected

- **WHEN** a complete record points outside `debate/{canonical_ticker}/{run_id}/` or to a non-current-date artifact
- **THEN** the record SHALL be diagnostic-only and cache lookup SHALL miss

### Requirement: Consumers restore terminal status and never infer clean success

Council cache reads, fallback artifacts/manifests, run-scoped watchlist outputs, and L4 aggregation SHALL expose the persisted status, reasons, and quality-record reference when available. Consumers SHALL not upgrade a non-clean, missing-proof, or legacy artifact to clean success because a directional verdict or readable markdown exists.

#### Scenario: L4 preserves degraded status

- **WHEN** the newest run-scoped watchlist artifact has `runtime_degraded`, `da_skipped`, `warning`, `failed`, or `incomplete`
- **THEN** L4 SHALL preserve its status and reasons and mark the candidate incomplete

#### Scenario: Clean cache requires validated proof

- **WHEN** a cache lookup sees a directional artifact
- **THEN** it SHALL return a clean cache result only if the matching current-date quality record is `complete/passed` with required stages and matching mode/ticker/run identity
