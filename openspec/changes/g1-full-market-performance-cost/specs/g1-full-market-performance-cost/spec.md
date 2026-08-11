## ADDED Requirements

### Requirement: Full-market performance/cost evidence orchestration

The evidence orchestrator SHALL wrap `screen_a_shares` (L1) and `scout_batch` (L2) without modifying their function signatures or return structures, and SHALL record total elapsed time, L1 elapsed time, and L2 elapsed time as separate measurements. The orchestrator MUST NOT alter L1 screening rules, L2 scout logic, provider adapters, or ScreeningProfile. Evidence SHALL identify whether the input is `partial_market` or `full_market`; only a complete current tradable A-share universe may support the full-market Gate conclusion.

#### Scenario: Timing is recorded per stage

- **WHEN** the evidence orchestrator runs a full-market L1+L2 pipeline
- **THEN** the output SHALL contain `timing.total_elapsed_seconds`, `timing.l1_elapsed_seconds`, and `timing.l2_elapsed_seconds` as non-negative numeric values, and `total_elapsed_seconds` SHALL be greater than or equal to `l1_elapsed_seconds + l2_elapsed_seconds`

#### Scenario: L1/L2 production logic is unmodified

- **WHEN** the evidence orchestrator wraps `screen_a_shares` and `scout_batch`
- **THEN** it MUST NOT change their function signatures, return structures, or internal behavior, and existing tests for L1/L2 SHALL pass without modification

### Requirement: Key field availability independent calculation

The evidence orchestrator SHALL independently calculate key field availability from L1 output candidates and field status, not from `stats` derived counts. The key fields SHALL be `ticker`, `f_score`, `adjusted_composite`, `pe_ttm`, `pb`, and `pledge_ratio`. Availability rate SHALL be the count of usable field slots divided by the total count of candidate-field slots. For `pledge_ratio=None`, `pledge_status=record_not_found` SHALL count as usable according to the canonical data-minimum-contract; `source_failed`, `invalid_value`, or missing status SHALL count as missing. Missing fields SHALL be explicitly counted.

#### Scenario: All fields present yields full availability

- **WHEN** all candidates have non-null values for every key field
- **THEN** `field_availability.rate` SHALL be `1.0` and `field_availability.missing_count` SHALL be `0`

#### Scenario: Missing fields reduce availability proportionally

- **WHEN** a candidate has `None` or empty string for one or more key fields
- **THEN** `field_availability.missing_count` SHALL increment by the number of missing fields, and `field_availability.rate` SHALL equal `(total_fields - missing_count) / total_fields`

### Requirement: Pledge ratio canonical status preservation

`screen_a_shares` SHALL preserve the canonical `pledge_ratio` value and `pledge_status` provenance. When `risk.pledge_status` is `record_not_found`, `pledge_ratio` SHALL remain `None` and the status SHALL identify the known-zero condition; the candidate projection MUST NOT rewrite it to `0.0`. When `pledge_status` is `source_failed`, `pledge_ratio` SHALL remain `None` and the status SHALL identify provider failure. When `pledge_status` is `record_found` or absent, the original value SHALL be preserved. The evidence availability calculation SHALL interpret `record_not_found` as usable without changing the candidate value.

#### Scenario: Record not found preserves status

- **WHEN** a candidate's `risk.pledge_status` is `record_not_found`
- **THEN** the candidate's L1 projection SHALL contain `pledge_ratio=None` and `pledge_status=record_not_found`, and evidence availability SHALL count the field as usable

#### Scenario: Source failed stays None

- **WHEN** a candidate's `risk.pledge_status` is `source_failed`
- **THEN** the candidate's `pledge_ratio` SHALL remain `None`

#### Scenario: Normal value preserved

- **WHEN** a candidate's `risk.pledge_status` is `record_found` or absent and `pledge_ratio` has a numeric value
- **THEN** the candidate's `pledge_ratio` SHALL preserve the original numeric value

### Requirement: Cache warmth pre-check

The evidence orchestrator SHALL perform a cache warmth pre-check before running the pipeline, counting cache hits, expired entries, and missing entries across all tickers and G1 quant dimensions. The pre-check result SHALL be persisted in the evidence bundle as `cache_status` with `warm_cache`, `cache_hits`, `cache_expired`, `cache_missing`, and `total_slots` fields. The pre-check MUST not create missing cache directories or call a private path helper with filesystem side effects. `warm_cache` SHALL describe L1 data-cache warmth only; L2 scout-cache hits SHALL be reported separately in `cost.cache_hits`.

#### Scenario: All caches warm

- **WHEN** all ticker-dimension cache entries are unexpired
- **THEN** `cache_status.warm_cache` SHALL be `true`, `cache_expired` and `cache_missing` SHALL be `0`

#### Scenario: Some caches expired or missing

- **WHEN** some ticker-dimension cache entries are expired or missing
- **THEN** `cache_status.warm_cache` SHALL be `false`, and `cache_expired` or `cache_missing` SHALL reflect the actual counts

### Requirement: L2 cost dual-oracle measurement

The evidence orchestrator SHALL record two cost measurements: measured cost based on actual `usage_summary.total_tokens` multiplied by the AD-03 token price, and equivalent full cost based on `(call_count + cache_hits)` multiplied by average tokens per call and the same price. Both measurements SHALL be in yuan and SHALL be persisted in the evidence bundle.

#### Scenario: Dual cost is present

- **WHEN** the evidence orchestrator completes an L2 run
- **THEN** the output SHALL contain `cost.measured_yuan`, `cost.equivalent_full_yuan`, `cost.call_count`, `cost.cache_hits`, and `cost.total_tokens`

#### Scenario: Cost below gate threshold

- **WHEN** `cost.measured_yuan` is at or below the gate threshold of 2.0 yuan
- **THEN** the cost dimension of `gate_passed` SHALL be satisfied

#### Scenario: Equivalent cost is undefined without a real call

- **WHEN** `call_count` is `0` and `cache_hits` is greater than `0`
- **THEN** `cost.equivalent_full_yuan` SHALL be `null` because no observed per-call token basis exists, and the evidence notes SHALL state that the full-cost estimate is unavailable

### Requirement: Unhandled exception visibility

The evidence orchestrator SHALL read `failure_summary["unhandled_exceptions"]` from the L2 output and persist it as `exceptions.unhandled_count`. When `unhandled_count` is greater than zero, `gate_passed` SHALL be `false`. Error details from `failure_summary["errors"]` SHALL be persisted in `exceptions.error_details`.

#### Scenario: Zero unhandled exceptions passes gate dimension

- **WHEN** `failure_summary["unhandled_exceptions"]` is `0`
- **THEN** `exceptions.unhandled_count` SHALL be `0` and the exception dimension of `gate_passed` SHALL be satisfied

#### Scenario: Non-zero unhandled exceptions fail gate

- **WHEN** `failure_summary["unhandled_exceptions"]` is greater than `0`
- **THEN** `gate_passed` SHALL be `false` and `exceptions.unhandled_count` SHALL reflect the actual count

### Requirement: Evidence bundle completeness

The evidence bundle SHALL contain `schema_version`, run identity (`run_id`, `profile_version`, `input_ticker_set_hash` inherited from L1), the exact `input_tickers` list, run metadata (`run_date`, `warm_cache`, `cache_status`, `coverage`, `mode`), timing, funnel (total, after_hard_gates, after_factors, after_heat_filter, l2_input, l2_deep_dive, l2_watch, l2_skip, l2_error, l2_degraded), field availability, cost, exceptions, run configuration (`exclude_cyclicals`, `force_l2`, `semaphore_concurrency`, `l2_timeout_seconds`, `ticker_count`, `ticker_source`), gate thresholds, `evidence_notes`, `metrics_gate_passed`, and `gate_passed`. The bundle SHALL be saveable as a JSON file to `data/evidence/`. `metrics_gate_passed` describes the four thresholds for the current input set; `gate_passed` SHALL be true only when `coverage=full_market` and all four thresholds pass.

#### Scenario: Bundle contains all required top-level keys

- **WHEN** the evidence orchestrator completes successfully
- **THEN** the output SHALL contain `schema_version`, `run_id`, `profile_version`, `input_ticker_set_hash`, `input_tickers`, `run_date`, `warm_cache`, `cache_status`, `coverage`, `mode`, `timing`, `funnel`, `field_availability`, `cost`, `exceptions`, `run_config`, `gate_thresholds`, `evidence_notes`, `metrics_gate_passed`, and `gate_passed`

#### Scenario: Funnel contains complete distribution

- **WHEN** the evidence orchestrator completes an L1+L2 run
- **THEN** `funnel` SHALL contain `total`, `after_hard_gates`, `after_factors`, `after_heat_filter`, `l2_input`, `l2_deep_dive`, `l2_watch`, `l2_skip`, `l2_error`, and `l2_degraded`

### Requirement: Gate judgment with four dimensions

`metrics_gate_passed` SHALL be `true` only when all four dimensions are satisfied for the current input set: total elapsed time at or below 15 minutes, key field availability rate at or above 0.95, measured L2 cost at or below 2.0 yuan, and unhandled exceptions count at or below 0. `gate_passed` SHALL additionally require `coverage=full_market`; a partial-market run MUST NOT close the full-market Gate. Gate thresholds SHALL be explicitly recorded in the evidence bundle.

#### Scenario: All dimensions pass on full market

- **WHEN** timing, availability, cost, and exceptions all meet their thresholds and coverage is `full_market`
- **THEN** `gate_passed` SHALL be `true`

#### Scenario: Metrics pass on partial market

- **WHEN** all four dimensions meet their thresholds but coverage is `partial_market`
- **THEN** `metrics_gate_passed` SHALL be `true` and `gate_passed` SHALL be `false`

#### Scenario: Any dimension fails

- **WHEN** any one of the four dimensions does not meet its threshold
- **THEN** `gate_passed` SHALL be `false`

### Requirement: Real run failure evidence preservation

When the full-market run fails due to provider unavailability, timeout, or other exceptions, the evidence orchestrator SHALL save a failure evidence bundle with a unique artifact identifier, `run_failed=true`, `gate_passed=false`, the error message, traceback, and elapsed time before failure. The orchestrator MUST NOT substitute default values to fabricate success.

#### Scenario: Run failure produces failure evidence

- **WHEN** the full-market run raises an exception before completing
- **THEN** the evidence bundle SHALL be saved with `run_failed=true`, `gate_passed=false`, the error string, traceback, and `elapsed_seconds_before_failure`
