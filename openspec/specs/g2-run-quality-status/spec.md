# G2 Run Quality Status Specification

## Purpose

定义 G2 深研运行的完整性、质量状态、成功缓存资格与 run-scoped 诊断读取边界，
阻止不完整、warning、失败或降级结果伪装为 clean success。
## Requirements
### Requirement: Closed G2 run-quality status vocabulary
The system SHALL accept only `complete`, `warning`, `failed`, `incomplete`,
`runtime_degraded`, and `da_skipped` as G2 run-quality statuses. A
`complete` status SHALL require `final_quality_gate="passed"` and every stage
required by the execution mode to have completed. Unknown statuses, a complete
record with a non-passing gate, or invalid stage declarations MUST be rejected.

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

#### Scenario: Fallback terminal reasons are visible
- **WHEN** fallback writes a result or terminal manifest
- **THEN** the artifact SHALL include `run_quality_status`, `run_quality_reasons`,
  and `quality_record_path`

### Requirement: Cache and artifact identity are mode- and run-bound
Council cache lookup SHALL require the requested execution mode to match the
quality record. The record payload, its canonical ticker/run path, and its
debate artifact path MUST bind to the same ticker and run ID; mismatches SHALL
be treated as invalid diagnostic evidence and MUST NOT be cache eligible. A
success cache artifact SHALL also have the current run date.

#### Scenario: Single-agent cache cannot satisfy Council
- **WHEN** a complete `single_agent` record exists for a ticker and a later request requires `council`
- **THEN** the later request SHALL miss cache and execute or resolve a `council` run

#### Scenario: Misbound artifact is rejected
- **WHEN** a complete record points outside `debate/{canonical_ticker}/{run_id}/`
- **THEN** cache lookup SHALL miss even if the pointed markdown is parseable

#### Scenario: Cross-date cache is rejected
- **WHEN** a complete record points to a prior-date debate markdown
- **THEN** the current-date request SHALL miss cache and create or resolve a new run

### Requirement: Run-scoped L4 consumption preserves incompleteness
L4 aggregation SHALL discover run-scoped Council outputs under
`watchlist/{canonical_ticker}/{run_id}/{date}.json`, select the newest run for a
ticker/date, and preserve its quality status fields. A non-complete or
non-passed result SHALL be marked incomplete for monitoring and MUST NOT be
treated as clean success because it contains a directional verdict.

#### Scenario: Degraded run is visible to L4
- **WHEN** the newest run-scoped Council output has
  `run_quality_status="runtime_degraded"`
- **THEN** L4 SHALL preserve its status and reasons and mark the candidate
  `l3_incomplete=true`

#### Scenario: Legacy output without quality proof is incomplete
- **WHEN** an older flat L3 artifact has a directional verdict but no
  `run_quality_status`, `final_quality_gate`, and `success_cache_eligible` proof
- **THEN** L4 SHALL allow diagnostic reading but mark it `l3_incomplete=true`

### Requirement: Clean G2 success SHALL require complete, warning-free quality evidence
The terminal quality record SHALL be `complete` with `final_quality_gate="passed"` only when every stage required by the execution mode completed and all integrated R1, R2, DA, and R4 quality checks completed without hard failure, warning, skip, or runtime degradation. Any such non-clean outcome SHALL remain visible through its status and reasons and SHALL be ineligible for success-cache lookup.

#### Scenario: Fully clean Council is cache eligible
- **WHEN** all required Council stages and all quality checks complete without warnings, skips, degradation, or failures
- **THEN** the terminal record SHALL be `complete/passed` and `is_success_cache_eligible` SHALL return true

#### Scenario: Warning result is not cache eligible
- **WHEN** any integrated quality check returns a soft warning
- **THEN** the terminal record SHALL be `warning` with the warning reason and SHALL NOT be cache eligible

#### Scenario: Degraded or skipped result is not cache eligible
- **WHEN** runtime degradation occurs or DA is skipped for any declared reason
- **THEN** the terminal record SHALL preserve the corresponding status/reason and SHALL NOT be cache eligible

#### Scenario: Failed or incomplete result is not cache eligible
- **WHEN** a hard quality failure or stage interruption occurs
- **THEN** the terminal record SHALL be `failed` or `incomplete` with the unfinished/failed stage and SHALL NOT be cache eligible

#### Scenario: Consumer artifact cannot upgrade status
- **WHEN** a directional verdict, readable markdown, or watchlist artifact exists for a non-clean run
- **THEN** consumers SHALL preserve the terminal non-clean status and SHALL NOT infer complete success from artifact existence
