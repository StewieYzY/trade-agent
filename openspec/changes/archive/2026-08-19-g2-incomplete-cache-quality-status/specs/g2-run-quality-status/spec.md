## ADDED Requirements

### Requirement: Closed G2 run-quality status vocabulary
The system SHALL accept only `complete`, `warning`, `failed`, `incomplete`,
`runtime_degraded`, and `da_skipped` as G2 run-quality statuses. A
`complete` status SHALL require `final_quality_gate="passed"` and every stage
required by the execution mode to have completed. Unknown statuses, a complete
record with a non-passing gate, non-empty reasons, or invalid stage declarations
MUST be rejected.

#### Scenario: Complete clean result
- **WHEN** a Council run completes all required stages and final validation passes
- **THEN** its terminal record SHALL be `complete` with `final_quality_gate="passed"`

#### Scenario: Invalid complete claim
- **WHEN** a writer attempts to persist `status="complete"` while final validation is warning, failed, or absent
- **THEN** the writer MUST reject the record and MUST NOT create a success-cache entry

#### Scenario: Unknown status is rejected
- **WHEN** a caller provides a status outside the closed vocabulary
- **THEN** persistence MUST fail closed with a clear validation error

### Requirement: Run-scoped diagnostic persistence and isolation
Every non-preflight G2 run SHALL persist a quality record bound to canonical
ticker and `run_id`, including terminal status, reasons, completed stages and
final-quality-gate result. The record path SHALL isolate different runs of one
ticker, use exclusive persistence, and remain readable even when the status is
not cache-eligible.

#### Scenario: Same ticker different runs do not overwrite
- **WHEN** two runs for `600009.SH` use different run IDs
- **THEN** each SHALL retain a separate readable quality record and neither write may overwrite the other

#### Scenario: Warning remains visible
- **WHEN** final validation produces a non-blocking warning
- **THEN** the run SHALL persist `warning` with its reason and consumers SHALL be able to read it independently of the success cache

#### Scenario: Failed runtime remains visible
- **WHEN** a run fails after it has started
- **THEN** it SHALL persist `failed` or `incomplete` with an explicit reason and MUST NOT be represented as clean success

### Requirement: Interrupted stages are incomplete, not cache hits
An interruption before R2, DA, Synthesizer or final validation SHALL persist
`incomplete`, record the unfinished stage, and preserve only diagnostic
evidence. A later run MUST NOT use that artifact as a complete Council cache
result.

#### Scenario: R2 interruption
- **WHEN** Round 2 raises after Round 1 was recorded
- **THEN** the run SHALL persist `incomplete` with `r2` unfinished and Council cache lookup SHALL miss

#### Scenario: DA interruption
- **WHEN** the DA call raises after R1/R2 completed
- **THEN** the run SHALL persist `incomplete` with `da` unfinished and SHALL not publish a clean success cache entry

#### Scenario: Synthesizer or final-validation interruption
- **WHEN** Synthesizer or final validation does not complete
- **THEN** the run SHALL persist `incomplete` with the respective unfinished stage and later reads MUST NOT treat the debate markdown as a success cache hit

### Requirement: Degraded, skipped and warning outcomes are not clean success
`warning`, `runtime_degraded`, and `da_skipped` outcomes SHALL each preserve
their own terminal status and reasons. None SHALL be eligible for a success
cache hit, even if a debate or fallback result contains a directional verdict.

#### Scenario: Runtime degradation
- **WHEN** Council error rate triggers runtime degradation
- **THEN** the record SHALL be `runtime_degraded`, include the degradation reason, and MUST NOT be cache eligible

#### Scenario: DA skipped
- **WHEN** DA is skipped for a declared orchestration reason
- **THEN** the record SHALL be `da_skipped`, retain the skip reason, and MUST NOT be cache eligible

#### Scenario: Soft warning
- **WHEN** a quality gate returns a non-blocking warning
- **THEN** the record SHALL be `warning`, retain all warnings, and MUST NOT be cache eligible

### Requirement: Consumer outputs preserve quality status
Council watchlist output and fallback runtime artifacts SHALL carry the terminal
G2 run-quality status, reasons, and a quality-record reference when one
exists. Consumers MUST NOT infer clean success from a directional verdict,
the existence of a watchlist file, or a readable diagnostic artifact.

#### Scenario: Watchlist labels non-complete result
- **WHEN** Council writes a watchlist artifact for a warning, DA-skipped, or degraded run
- **THEN** the artifact SHALL expose the terminal status and reasons and SHALL not advertise cache eligibility

#### Scenario: Fallback result is diagnostic
- **WHEN** fallback completes with blocked fact-check, warning, failure, or any non-complete status
- **THEN** its result and manifest SHALL expose that status and remain outside the Council success cache

#### Scenario: Started fallback interruption is terminally visible
- **WHEN** a fallback run is cancelled or its audited result publication fails after run setup
- **THEN** it SHALL persist an `incomplete` quality record and update the manifest to
  the same terminal status before re-raising
