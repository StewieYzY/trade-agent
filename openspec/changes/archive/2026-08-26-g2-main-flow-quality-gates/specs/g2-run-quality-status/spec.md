## ADDED Requirements

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
