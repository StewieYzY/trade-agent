## ADDED Requirements

### Requirement: Growth expectation diagnostic input contract

The system SHALL accept a versioned `growth_expectation_diagnostic` input payload with the required fields `schema_version`, `ticker`, `valuation_date`, `report_period`, `as_of`, `currency`, `value_scale`, `current_market_value`, `normalized_operating_cashflow`, `normalized_earnings`, `total_capex`, `normalized_net_profit`, and `sources`, plus optional `industry`. `schema_version` SHALL be `g2-growth-expectation-input-v1`. `ticker` SHALL be canonical. `currency` SHALL be one of `CNY`, `HKD`, `USD`; `value_scale` SHALL be one of `absolute`, `thousand`, `million`, `hundred_million`. `report_period` SHALL be a valid calendar ISO date (`YYYY-MM-DD`) or quarter (`YYYYQn`) with a constructible year and whose period end is not after `as_of`; `as_of` SHALL NOT be after `valuation_date`. `current_market_value` SHALL be a finite positive number; `total_capex` SHALL be a finite number greater than or equal to zero. `normalized_operating_cashflow`, `normalized_earnings`, and `normalized_net_profit` SHALL be finite numbers. Each source SHALL carry `ticker`, `source_id`, `provider`, `field`, `raw_field`, `raw_payload_hash`, `report_period`, `as_of`, `freshness`, `currency`, `value_scale`, `published_at`, and `degradation_status`; `raw_payload_hash` SHALL be a lowercase sha256 digest, source `ticker` SHALL match the payload ticker, source `published_at` SHALL NOT be after source `as_of`, and source `report_period` SHALL NOT end after `published_at`. A source claiming `fresh` SHALL have a publication age no greater than the contract freshness cap. Every monetary input field, including `normalized_earnings`, SHALL have exactly one source, source_id values SHALL be unique, source units SHALL match the payload units, and source `report_period` and `as_of` SHALL match the payload-level values. Unknown input fields SHALL be rejected.

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
- **WHEN** a date field such as `valuation_date`, `report_period`, or `as_of` is not a real calendar date
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Source mismatch fails closed
- **WHEN** a source `report_period`, `as_of`, `currency`, or `value_scale` does not match the payload-level values
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Source provenance fields are required
- **WHEN** a source is missing `provider`, `raw_field`, or `raw_payload_hash`, or has a malformed `raw_payload_hash`
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Field-level source coverage is enforced
- **WHEN** a monetary input field has no source or has more than one source
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Unknown input field fails closed
- **WHEN** an input payload contains a field outside the frozen contract
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Malformed container fails closed
- **WHEN** a required list field such as `sources` or `assumptions` is not iterable
- **THEN** the contract SHALL raise `ContractError` and MUST NOT leak a raw `TypeError`

#### Scenario: Source ticker mismatch fails closed
- **WHEN** a source `ticker` does not match the payload-level ticker
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Source publication ordering fails closed
- **WHEN** a source `published_at` is after its `as_of`
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Future report period fails closed
- **WHEN** a report period ends after the payload `as_of`
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Stale source cannot claim fresh
- **WHEN** a source publication age exceeds the freshness cap but `freshness` is `fresh`
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Source identity is unique
- **WHEN** two field-level sources use the same `source_id`
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Input strings are normalized
- **WHEN** a text field such as `valuation_date`, `report_period`, or `currency` has surrounding whitespace
- **THEN** the contract SHALL strip it before storing the validated value

### Requirement: Growth expectation diagnostic output contract

The system SHALL freeze a versioned `growth_expectation_diagnostic` output with `calculation_status` of exactly `clean`, `degraded`, `not_evaluable`, or `failed`, and SHALL always carry `quality_status` of `warning` or `failed`, `decision_grade` of `diagnostic`, and an `assumptions` mapping derived from the assumption snapshot when one exists. The output SHALL require the PRD context fields `evidence`, `counter_evidence`, `unknowns`, and `what_would_change_my_mind` to be present explicitly, even when their values are empty; these fields MUST NOT be silently defaulted. Evidence records SHALL carry source identity fields bound to the input snapshot. A `clean` or `degraded` result SHALL contain a positive `current_market_value`, a complete `input_snapshot`, an `as_of`, and `report_period_end <= as_of <= valuation_date`, non-negative `current_business_value` ranges, signed `priced_growth_value_range` and `priced_growth_share_range`, exactly one named conservative/base/optimistic reverse scenario for each frozen reverse input, a non-negative `credible_growth_range`, `expectation_gap`, a non-negative finite `value_pulled_forward_years`, a resolved `expectation_overdraft`, and a non-empty `sensitivity` whose values SHALL remain within the referenced assumption bounds. A `clean` result SHALL have empty `warnings` and `reasons`; a `degraded` result SHALL have a non-empty `warnings` list. Every result SHALL carry a `diagnostic_digest` over the canonical serialized output. A `not_evaluable` or `failed` result SHALL carry `failure_kind`, non-empty `reason_codes`, non-empty `reasons`, `provenance`, `input_digest`, and `diagnostic_digest`, and MUST NOT contain numeric conclusions. A `not_evaluable` result MAY omit `assumption_snapshot`; when it is absent, canonical serialization SHALL omit `assumptions`, and omission SHALL be digest-equivalent to an explicit `assumptions=null`.

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

#### Scenario: Sensitivity references unknown assumption
- **WHEN** a sensitivity scenario refers to an assumption key not present in the snapshot
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: PRD context fields cannot be omitted
- **WHEN** any of `evidence`, `counter_evidence`, `unknowns`, or `what_would_change_my_mind` is missing
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Economically meaningless clean result is rejected
- **WHEN** a `clean` result has a negative market value, negative reverse year, or negative credible growth rate
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Clean result requires clean sources
- **WHEN** a `clean` result binds to a source whose `degradation_status` is not `clean`
- **THEN** `validate_diagnostic_binding` SHALL raise `ContractError`

#### Scenario: Degraded result rejects failed sources
- **WHEN** a `degraded` result binds to a source whose `degradation_status` is `failed`
- **THEN** `validate_diagnostic_binding` SHALL raise `ContractError`

#### Scenario: Complete output digest rejects mutation
- **WHEN** a bound diagnostic's value range, reverse result, sensitivity, or evidence is changed without recomputing `diagnostic_digest`
- **THEN** `validate_diagnostic_binding` SHALL raise `ContractError`

#### Scenario: Failure without assumptions round-trips
- **WHEN** a `not_evaluable` result omits `assumption_snapshot`
- **THEN** serializing and parsing the result SHALL remain valid, canonical serialization SHALL omit `assumptions`, and the digest SHALL remain stable

#### Scenario: Output date order is validated independently
- **WHEN** `report_period_end > as_of` or `as_of > valuation_date` in an output
- **THEN** the output contract SHALL raise `ContractError`

#### Scenario: Clean and degraded results require assumptions mapping
- **WHEN** a `clean` or `degraded` result omits the `assumptions` mapping
- **THEN** the contract SHALL raise `ContractError`

### Requirement: User assumption snapshot

The system SHALL represent user assumptions in a versioned `assumption_snapshot` with `version`, `created_at`, and explicit `assumptions`. Each assumption SHALL carry `key`, `value`, `unit`, `source`, `confirmed_by_user`, and `version`. The V0 required assumption keys SHALL be `normalized_earnings_basis`, `maintenance_capex_ratio`, `cost_of_equity`, `maintenance_growth`, `credible_growth_rate`, `mature_pe`, and `reverse_mode`. `normalized_earnings_basis` SHALL be one of `normalized_operating_cashflow` or `normalized_net_profit`. `maintenance_capex_ratio`, `cost_of_equity`, and `mature_pe` SHALL be ordered two-value ranges; `credible_growth_rate` SHALL be a conservative/base/optimistic three-value range. The reverse mode SHALL also freeze the actual reverse input: `reverse_fixed_growth_rate` as a conservative/base/optimistic three-value range whose values are all positive for `fixed_growth_rate`, and `reverse_fixed_duration_years` as a short/mid/long three-value range, each positive and not exceeding `50`, for `fixed_duration`. Assumption values SHALL be immutable after validation, and each key SHALL use a frozen unit: `ratio` for `maintenance_capex_ratio`, `decimal` for `cost_of_equity`, `maintenance_growth`, `credible_growth_rate`, and `reverse_fixed_growth_rate`, `x` for `mature_pe`, `years` for `reverse_fixed_duration_years`, and empty unit for `normalized_earnings_basis` and `reverse_mode`. Missing required keys, duplicate keys, unconfirmed assumptions, conflicting assumptions, wrong units, invalid earnings basis, unordered or out-of-range intervals, an over-cap reverse duration, and a missing or conflicting reverse input SHALL fail closed and MUST NOT be replaced by silent defaults.

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

#### Scenario: Invalid earnings basis fails closed
- **WHEN** `normalized_earnings_basis` is not a frozen V0 basis
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Over-cap reverse duration fails closed
- **WHEN** `reverse_fixed_duration_years` or a reverse scenario duration exceeds `50`
- **THEN** the contract SHALL raise `ContractError`

### Requirement: Model applicability and failure semantics

The system SHALL distinguish `data_insufficient`, `model_not_applicable`, and `computation_failed` without masquerading any failure as success. `evaluate_applicability` SHALL consume a validated `DiagnosticInput` and a validated `AssumptionSnapshot`, derive industry, unit and report-period alignment and normalized-earnings positivity from those validated artifacts, and SHALL return `not_evaluable` for a confirmed financial industry, non-positive `normalized_earnings`, non-positive earnings under the snapshot's `normalized_earnings_basis`, or any source whose `degradation_status` is `failed`. Missing or unvalidated assumption snapshots SHALL return `not_evaluable` with `failure_kind=data_insufficient` and reason code `data_missing`. Industry matching SHALL use token boundaries so `non-financial` is not classified as financial solely because it contains the word `financial`. Missing industry SHALL NOT hard-block; it SHALL instead return an applicable verdict with warning `industry_unknown`. A caller-supplied industry that conflicts with the validated input SHALL fail closed. A computation failure SHALL map to `calculation_status=failed` with `failure_kind=computation_failed`, `quality_status=failed`, and a preserved `assumption_snapshot`. Failure results SHALL carry machine-readable `reason_codes` from the PRD and `FAILURE_REASON_CODES` vocabulary consistent with their `failure_kind`, and SHALL retain `provenance` and both digests.

#### Scenario: Financial industry is not applicable
- **WHEN** the input industry is financial
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=model_not_applicable` and reason code `model_not_applicable`

#### Scenario: Missing normalized earnings is not applicable
- **WHEN** normalized earnings are absent or non-positive
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=data_insufficient` and reason code `invalid_value`

#### Scenario: Selected normalized earnings basis is not applicable
- **WHEN** `normalized_earnings` is positive but the validated assumption snapshot selects a non-positive `normalized_net_profit` or `normalized_operating_cashflow`
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=data_insufficient` and reason code `invalid_value`

#### Scenario: Negative operating cashflow is not applicable
- **WHEN** normalized earnings are positive but normalized operating cashflow is negative
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=data_insufficient` and reason code `invalid_value`

#### Scenario: Non-finite or non-numeric earnings is not applicable
- **WHEN** normalized earnings is `NaN`, infinite, boolean, or non-numeric
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=data_insufficient`

#### Scenario: Computation failure maps to failed
- **WHEN** the engine encounters a computation error
- **THEN** the result SHALL use `calculation_status=failed`, `failure_kind=computation_failed`, and `quality_status=failed`

#### Scenario: Failure reason codes are required and consistent
- **WHEN** a failure result has missing, unknown, or failure-kind-inconsistent reason codes
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Missing industry degrades to warning
- **WHEN** `industry` is missing and normalized earnings are positive and finite
- **THEN** `evaluate_applicability` SHALL return an applicable verdict with warning `industry_unknown`

#### Scenario: Non-financial label is not financial
- **WHEN** the input industry is `non-financial`
- **THEN** `evaluate_applicability` SHALL not classify it as financial solely because of the substring `financial`

#### Scenario: Failed source is not evaluable
- **WHEN** any input source has `degradation_status=failed`
- **THEN** `evaluate_applicability` SHALL return `not_evaluable` with `failure_kind=data_insufficient`

#### Scenario: Failed result preserves assumptions
- **WHEN** `calculation_status` is `failed` and no `assumption_snapshot` is present
- **THEN** the contract SHALL raise `ContractError`

#### Scenario: Failure may carry the not-evaluable overdraft marker
- **WHEN** `calculation_status` is `not_evaluable` or `failed`
- **THEN** `expectation_overdraft` SHALL be either null or the literal marker `not_evaluable`, and MUST NOT be a resolved overdraft level

### Requirement: Provenance and input digest binding

The system SHALL bind every diagnostic to one identity: `ticker`, `dossier_snapshot`, `profile_version`, `formula_version`, `assumption_snapshot_version`, the input payload including `industry`, and the assumption snapshot. `provenance` SHALL carry `dossier_snapshot`, `profile_version`, `formula_version`, and `assumption_snapshot_version`. `compute_input_digest` SHALL derive a canonical sha256 digest over that full input identity, and `compute_diagnostic_digest` SHALL derive a canonical sha256 digest over the complete serialized output. `validate_diagnostic_binding` SHALL reject any identity-field mismatch, either digest mismatch, a diagnostic `current_market_value` or `input_snapshot` that differs from the input payload, or a `clean` result whose sources are not all `fresh`.

#### Scenario: Digest matches bound identity
- **WHEN** the diagnostic `input_digest` equals the digest of the supplied ticker, input, assumptions, formula version, dossier snapshot, and profile version
- **THEN** `validate_diagnostic_binding` SHALL return the validated diagnostic

#### Scenario: Identity mismatch fails closed
- **WHEN** the diagnostic ticker, dossier snapshot, profile version, formula version, `current_market_value`, or a shared input field does not match the supplied identity
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
