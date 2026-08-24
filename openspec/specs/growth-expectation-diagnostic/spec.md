# growth-expectation-diagnostic Specification

## Purpose

冻结成长预期资本化诊断 `growth_expectation_diagnostic` 的输入、输出、用户 assumption snapshot、
模型适用性、失败语义与 provenance/input digest 绑定，覆盖可计算、不可评估、失败和降级路径的
golden cases，保证强单 Agent 与 Council A/B 共享同一确定性诊断口径，不实现计算引擎。

## Requirements

### Requirement: Growth expectation diagnostic input contract

The system SHALL accept a versioned `growth_expectation_diagnostic` input payload with the required fields `schema_version`, `ticker`, `valuation_date`, `report_period`, `as_of`, `currency`, `value_scale`, `current_market_value`, `normalized_operating_cashflow`, `total_capex`, `normalized_net_profit`, and `sources`. `schema_version` SHALL be `g2-growth-expectation-input-v1`. `ticker` SHALL be canonical. `currency` SHALL be one of `CNY`, `HKD`, `USD`; `value_scale` SHALL be one of `absolute`, `thousand`, `million`, `hundred_million`. `report_period` SHALL be an ISO date (`YYYY-MM-DD`) or quarter (`YYYYQn`). `current_market_value` and `total_capex` SHALL be finite numbers greater than or equal to zero; `normalized_operating_cashflow` and `normalized_net_profit` SHALL be finite numbers. Each source SHALL carry `source_id`, `field`, `report_period`, `as_of`, `freshness`, `currency`, `value_scale`, `published_at`, and `degradation_status`; every monetary input field SHALL have exactly one source, source units SHALL match the payload units, and source `report_period` and `as_of` SHALL match the payload-level values. Unknown input fields SHALL be rejected.

#### Scenario: Valid input is accepted
- **WHEN** a payload contains all required fields, canonical ticker, supported units, finite monetary values, and complete matching field-level source metadata
- **THEN** the contract SHALL parse it into a validated `DiagnosticInput`

#### Scenario: Missing required field fails closed
- **WHEN** any required input field is absent or blank
- **THEN** the contract SHALL raise `ContractError` and MUST NOT return a partial input object

#### Scenario: Unknown unit fails closed
- **WHEN** `currency` or `value_scale` is not a supported value
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Illegal numeric value fails closed
- **WHEN** a monetary input is negative where non-negativity is required, or any monetary input is `NaN` or infinite
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Invalid calendar date fails closed
- **WHEN** a date field such as `valuation_date` or `as_of` is not a real calendar date
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Source mismatch fails closed
- **WHEN** a source `report_period`, `as_of`, `currency`, or `value_scale` does not match the payload-level values
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Field-level source coverage is enforced
- **WHEN** a monetary input field has no source or has more than one source
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Unknown input field fails closed
- **WHEN** an input payload contains a field outside the frozen contract
- **THEN** the contract SHALL raise `ContractError`

### Requirement: Growth expectation diagnostic output contract

The system SHALL freeze a versioned `growth_expectation_diagnostic` output with `calculation_status` of exactly `clean`, `degraded`, `not_evaluable`, or `failed`, and SHALL always carry `quality_status` of `warning` or `failed`, `decision_grade` of `diagnostic`, and an `assumptions` mapping derived from the assumption snapshot. A `clean` or `degraded` result SHALL contain a non-negative `current_market_value`, non-negative `current_business_value` ranges, signed `priced_growth_value_range` and `priced_growth_share_range`, at least one reverse scenario with non-negative rates and years, a non-negative `credible_growth_range`, `expectation_gap`, a resolved `expectation_overdraft`, and a non-empty `sensitivity`. A `clean` result SHALL have empty `warnings` and `reasons`; a `degraded` result SHALL have a non-empty `warnings` list. A `not_evaluable` or `failed` result SHALL carry `failure_kind`, non-empty `reason_codes`, non-empty `reasons`, `provenance`, and `input_digest`, and MUST NOT contain numeric conclusions.

#### Scenario: Clean result has complete output
- **WHEN** `calculation_status` is `clean`
- **THEN** the output SHALL contain all required numeric intervals, at least one reverse scenario, sensitivity, and `quality_status=warning` with `decision_grade=diagnostic`

#### Scenario: Degraded result keeps warnings visible
- **WHEN** `calculation_status` is `degraded`
- **THEN** `warnings` SHALL be non-empty and `failure_kind` SHALL be null

#### Scenario: Not evaluable result has no fabricated numbers
- **WHEN** `calculation_status` is `not_evaluable` or `failed`
- **THEN** numeric conclusions SHALL be absent, and `reason_codes` and `reasons` SHALL be non-empty

#### Scenario: Half-finished result is rejected
- **WHEN** a result claims `clean` but omits a required field, sensitivity, or a reverse scenario
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Economically meaningless clean result is rejected
- **WHEN** a `clean` result has a negative market value, negative reverse year, or negative credible growth rate
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Clean result requires clean sources
- **WHEN** a `clean` result binds to a source whose `degradation_status` is not `clean`
- **THEN** `validate_diagnostic_binding` SHALL raise `ContractError`

### Requirement: User assumption snapshot

The system SHALL represent user assumptions in a versioned `assumption_snapshot` with `version`, `created_at`, and explicit `assumptions`. Each assumption SHALL carry `key`, `value`, `unit`, `source`, `confirmed_by_user`, and `version`. The V0 required assumption keys SHALL be `normalized_earnings_basis`, `maintenance_capex_ratio`, `cost_of_equity`, `maintenance_growth`, `credible_growth_rate`, `mature_pe`, and `reverse_mode`. The reverse mode SHALL also freeze the actual reverse input: `reverse_fixed_growth_rate` for `fixed_growth_rate` and `reverse_fixed_duration_years` for `fixed_duration`. Assumption values SHALL be immutable after validation, and each key SHALL use a frozen unit: `ratio` for `maintenance_capex_ratio`, `decimal` for `cost_of_equity`, `maintenance_growth`, `credible_growth_rate`, and `reverse_fixed_growth_rate`, `x` for `mature_pe`, `years` for `reverse_fixed_duration_years`, and empty unit for `normalized_earnings_basis` and `reverse_mode`. Missing required keys, duplicate keys, unconfirmed assumptions, conflicting assumptions, wrong units, and a missing or conflicting reverse input SHALL fail closed and MUST NOT be replaced by silent defaults.

#### Scenario: All required assumptions present
- **WHEN** an assumption snapshot contains all required keys with correct units, the matching reverse input, and `confirmed_by_user=True`
- **THEN** the contract SHALL validate the snapshot and accept it

#### Scenario: Missing required assumption fails closed
- **WHEN** a required assumption key is absent
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Unconfirmed assumption fails closed
- **WHEN** any assumption has `confirmed_by_user=False`
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Duplicate or conflicting assumption fails closed
- **WHEN** a snapshot contains duplicate keys or conflicting values for the same key
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Wrong assumption unit fails closed
- **WHEN** an assumption carries a unit that does not match the frozen unit for its key
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Missing reverse input fails closed
- **WHEN** `reverse_mode` is fixed but its actual growth rate or duration years is absent or conflicting
- **THEN** the contract SHALL raise `ContractError`

### Requirement: Model applicability and failure semantics

The system SHALL distinguish `data_insufficient`, `model_not_applicable`, and `computation_failed` without masquerading any failure as success. `evaluate_applicability` SHALL return `not_evaluable` for financial industries, negative or missing normalized earnings, non-finite or non-numeric normalized earnings, non-boolean alignment flags, or unit/report-period misalignment. A computation failure SHALL map to `calculation_status=failed` with `failure_kind=computation_failed`, `quality_status=failed`, and a preserved `assumption_snapshot`. Failure results SHALL carry machine-readable `reason_codes` from the `FAILURE_REASON_CODES` vocabulary consistent with their `failure_kind`, and SHALL retain `provenance` and `input_digest`.

#### Scenario: Financial industry is not applicable
- **WHEN** the input industry is financial
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=model_not_applicable`

#### Scenario: Missing normalized earnings is not applicable
- **WHEN** normalized earnings are absent or non-positive
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=data_insufficient`

#### Scenario: Non-finite or non-numeric earnings is not applicable
- **WHEN** normalized earnings is `NaN`, infinite, boolean, or non-numeric
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=data_insufficient`

#### Scenario: Computation failure maps to failed
- **WHEN** the engine encounters a computation error
- **THEN** the result SHALL use `calculation_status=failed`, `failure_kind=computation_failed`, and `quality_status=failed`

#### Scenario: Failure reason codes are required and consistent
- **WHEN** a failure result has missing, unknown, or failure-kind-inconsistent reason codes
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Non-boolean alignment flag is not applicable
- **WHEN** `units_aligned` or `periods_aligned` is not a boolean
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=data_insufficient`

#### Scenario: Failed result preserves assumptions
- **WHEN** `calculation_status` is `failed` and no `assumption_snapshot` is present
- **THEN** the contract SHALL raise `ContractError`

### Requirement: Provenance and input digest binding

The system SHALL bind every diagnostic to one identity: `ticker`, `dossier_snapshot`, `profile_version`, `formula_version`, `assumption_snapshot_version`, the input payload, and the assumption snapshot. `provenance` SHALL carry `dossier_snapshot`, `profile_version`, `formula_version`, and `assumption_snapshot_version`. `compute_input_digest` SHALL derive a canonical sha256 digest over the full identity, and `validate_diagnostic_binding` SHALL reject any identity-field mismatch, digest mismatch, or a `clean` result whose sources are not all `fresh`.

#### Scenario: Digest matches bound identity
- **WHEN** the diagnostic `input_digest` equals the digest of the supplied ticker, input, assumptions, formula version, dossier snapshot, and profile version
- **THEN** `validate_diagnostic_binding` SHALL return the validated diagnostic

#### Scenario: Identity mismatch fails closed
- **WHEN** the diagnostic ticker, dossier snapshot, profile version, formula version, or a shared input field does not match the supplied identity
- **THEN** `validate_diagnostic_binding` SHALL raise `ContractError`

#### Scenario: Digest mismatch fails closed
- **WHEN** the diagnostic `input_digest` does not match the supplied input
- **THEN** `validate_diagnostic_binding` SHALL raise `ContractError`

#### Scenario: Clean result requires fresh sources
- **WHEN** a `clean` diagnostic binds to an input whose sources are `stale` or `unknown`
- **THEN** `validate_diagnostic_binding` SHALL raise `ContractError`

### Requirement: Golden cases cover contract paths

The contract SHALL be verified with positive and negative golden cases covering computable, not evaluable, failed, and degraded paths. Golden cases SHALL include round-trip serialization, mutation detection, reverse-mode exclusivity, fixed-duration coverage, identity binding, unknown-field rejection, and economic-meaning checks.

#### Scenario: Computable positive case
- **WHEN** a fully confirmed input and complete output are supplied
- **THEN** the golden case SHALL assert `calculation_status=clean` and all numeric intervals present

#### Scenario: Not evaluable negative case
- **WHEN** a financial-industry input is supplied
- **THEN** the golden case SHALL assert `calculation_status=not_evaluable` and no numeric conclusions

#### Scenario: Failed negative case
- **WHEN** a computation failure is supplied
- **THEN** the golden case SHALL assert `calculation_status=failed` and no numeric conclusions

#### Scenario: Degraded negative case
- **WHEN** a computable result carries a warning
- **THEN** the golden case SHALL assert `calculation_status=degraded` and the warning is retained

#### Scenario: Round-trip and mutation are covered
- **WHEN** a valid diagnostic is serialized and parsed again, or its digest is tampered
- **THEN** round-trip SHALL be stable and tampering SHALL be detected
