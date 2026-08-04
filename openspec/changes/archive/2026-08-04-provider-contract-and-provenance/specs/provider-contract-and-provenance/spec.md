## ADDED Requirements

### Requirement: Field evidence has explicit provenance and status

Every normalized field used as a candidate input SHALL carry provider family, provider, method, market, canonical ticker, raw field, response hash, retrieval time, status, and a separate integration eligibility value.

#### Scenario: Available field is not automatically production eligible
- **WHEN** a provider response parses successfully for a field
- **THEN** the evidence SHALL use `status=available` and SHALL keep `eligibility` as `not_qualified` or `shadow_only` unless a later qualification policy explicitly promotes it

#### Scenario: Missing provenance is visible
- **WHEN** a field lacks provider, method, raw field, or response identity
- **THEN** the validator SHALL mark it `not_evaluated` or reject it, and SHALL NOT emit a clean production-eligible field

### Requirement: Time, unit, and currency are field-level metadata

Financial, valuation, price, and ratio fields SHALL record the applicable unit/currency and `as_of` or `report_period`; ambiguous or missing metadata SHALL prevent production eligibility.

#### Scenario: Report period is required for financial data
- **WHEN** an income statement, balance sheet, or cash flow field is normalized
- **THEN** the field SHALL carry a report period or be marked `not_evaluated`

#### Scenario: Unit mismatch is not silently normalized
- **WHEN** two evidence values use incompatible or unknown units/currencies
- **THEN** the contract SHALL preserve the raw evidence and mark the normalized field `not_evaluated` or `conflict`

### Requirement: Provider failures remain distinct from missing records

The contract SHALL preserve distinct statuses for `record_not_found`, `source_failed`, `permission_denied`, `rate_limited`, `not_supported_for_market`, `invalid_value`, and `not_evaluated`.

#### Scenario: Provider endpoint is empty or unavailable
- **WHEN** a provider request fails, returns an empty endpoint response, or cannot be called
- **THEN** the field SHALL be marked `source_failed` or `not_evaluated` with a redacted reason, not `record_not_found`

#### Scenario: Successful request has no ticker record
- **WHEN** a provider request succeeds and explicitly contains no record for the canonical ticker
- **THEN** the field SHALL be marked `record_not_found`

### Requirement: Conflicting provider evidence fails closed

When multiple provider evidence values for the same canonical ticker, field, and time basis conflict in value, unit, currency, or report period, the contract SHALL preserve all evidence and emit a conflict state.

#### Scenario: Numeric values disagree
- **WHEN** two available providers return different normalized numeric values for the same field and time basis
- **THEN** the merged field SHALL be `conflict` or `not_evaluated` until an explicit policy resolves it

#### Scenario: One provider is stale
- **WHEN** one provider value is outside the field freshness policy
- **THEN** the stale value SHALL remain in provenance but SHALL NOT override a fresh value implicitly

### Requirement: Provenance metadata is non-sensitive and serializable

The contract SHALL serialize to JSON-safe data and SHALL exclude API keys, authorization headers, URL userinfo, and secret tokens.

#### Scenario: Sensitive provider error is persisted
- **WHEN** an adapter raises an error containing credentials or authenticated URL data
- **THEN** the stored reason SHALL be redacted while preserving error class and failure status

#### Scenario: Sidecar does not mutate legacy consumers
- **WHEN** contract metadata is generated for an existing fetcher result
- **THEN** the legacy consumer payload SHALL remain unchanged and metadata SHALL be available as a separate sidecar

### Requirement: Contract metadata cannot unlock downstream capability gates

Contract validation SHALL not mark a field eligible for ranking, canonical snapshot, growth diagnostic, G1, G2, or G3 unless a later explicit qualification policy provides that decision.

#### Scenario: Candidate provider metadata is attached
- **WHEN** a LongPort or Longbridge field is represented in the contract
- **THEN** it SHALL remain `not_qualified` or `shadow_only` until runtime qualification and downstream policy both pass
