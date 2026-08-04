## ADDED Requirements

### Requirement: Qualification uses a fixed representative A-share probe plan

The qualification runner SHALL use a versioned probe plan containing at least five canonical A-share tickers covering multiple exchange/type categories, and SHALL execute only read-only provider methods.

#### Scenario: Probe plan is reproducible
- **WHEN** the same probe plan version and ticker set are used twice
- **THEN** both runs SHALL record the same plan hash and canonical ticker identities

#### Scenario: Provider operation is read-only
- **WHEN** a probe method is registered
- **THEN** the method SHALL be marked read-only and SHALL NOT place orders, write account state, subscribe to feeds, or mutate provider data

### Requirement: Qualification records field-level evidence

For every provider/method/ticker/field probe, the runner SHALL record provider family, provider, method, market, canonical ticker, raw field name, normalized value when safely parseable, unit, currency, as-of or report period, status, and provenance metadata.

#### Scenario: Available field is traceable
- **WHEN** a provider returns a field with a valid value
- **THEN** the evidence SHALL include the raw field identity, normalized value, unit/currency, time basis, response hash, and provider method

#### Scenario: Unit or period cannot be aligned
- **WHEN** a returned field lacks a trustworthy unit, currency, as-of, or report period
- **THEN** the field SHALL be marked `not_evaluated` or `invalid_value` with a reason and SHALL NOT be reported as qualified

### Requirement: Qualification distinguishes provider failure states

The runner SHALL use explicit field or method statuses including `available`, `partial`, `record_not_found`, `source_failed`, `permission_denied`, `rate_limited`, `not_supported_for_market`, `invalid_value`, and `not_evaluated`, and SHALL preserve a redacted raw error or failure reason.

#### Scenario: Provider request fails
- **WHEN** a provider request raises a transport, schema, permission, or rate-limit error
- **THEN** the evidence SHALL retain the failure classification, attempted provider/method, redacted reason, and run_id without converting the result to an empty success

#### Scenario: Ticker has no provider record
- **WHEN** the provider request succeeds but contains no record for the canonical ticker
- **THEN** the field or method SHALL be marked `record_not_found`, distinct from `source_failed`

### Requirement: Candidate providers remain isolated from production data paths

Qualification evidence SHALL be written to a run-scoped qualification output and SHALL NOT write or alter production cache JSON, ranking inputs, canonical snapshots, debate outputs, watchlist outputs, or growth diagnostic inputs.

#### Scenario: Candidate probe completes
- **WHEN** a LongPort or Longbridge candidate probe returns available, partial, or failed evidence
- **THEN** only qualification artifacts and reports SHALL be created, and existing production data paths SHALL remain unchanged

#### Scenario: Candidate provider is not qualified
- **WHEN** a candidate lacks credentials, A-share support, or field-level evidence
- **THEN** its fields SHALL remain non-qualified and SHALL NOT be used as an implicit fallback or merged into baseline data

### Requirement: Qualification produces a comparison report and manifest

Each run SHALL produce a manifest and a field-level comparison report that distinguish documentation capability, callable code path, observed A-share runtime result, and eligibility for later formal integration.

#### Scenario: Evidence bundle is complete
- **WHEN** a probe run finishes or is stopped
- **THEN** the output SHALL include run_id, code version, plan hash, provider/method coverage, per-field statuses, raw/evidence hashes, stop reason if any, and report paths

#### Scenario: Rate limit stops a provider safely
- **WHEN** a provider reaches a rate-limit condition
- **THEN** the runner SHALL stop or back off according to the plan, persist the partial evidence and stop reason, and SHALL NOT continue with silent retries that obscure the provider state

### Requirement: Qualification does not unlock capability gates

Passing probe tests or producing a non-empty qualification report SHALL NOT by itself mark a provider qualified for ranking, canonical snapshot, growth diagnostic, G1, G2, or G3.

#### Scenario: Probe report is consumed by a later change
- **WHEN** a later adapter or provenance change reads qualification evidence
- **THEN** it SHALL apply an explicit field-level eligibility decision and retain the original qualification provenance
