## ADDED Requirements

### Requirement: Batch adapters use explicit provider boundaries

The batch adapter SHALL receive an explicitly registered provider implementation, a canonical ticker set, and a method/dimension request, and SHALL NOT discover SDKs or make hidden network calls.

#### Scenario: Provider is explicitly registered
- **WHEN** a batch run starts
- **THEN** only registered providers and requested methods SHALL be invoked, with provider/method call identity recorded

#### Scenario: Provider is unavailable
- **WHEN** a provider adapter is missing, disabled, or lacks credentials
- **THEN** the run SHALL produce `not_evaluated`/blocked evidence and SHALL NOT fabricate values or silently switch providers

### Requirement: Batch results become field-level evidence

Every batch response SHALL be converted into provider contract evidence bound to canonical ticker, field, method, response hash, status, provenance, and eligibility.

#### Scenario: One batch contains multiple tickers
- **WHEN** a provider returns records for multiple tickers
- **THEN** each ticker/field evidence SHALL preserve its canonical identity and SHALL be independently mergeable

#### Scenario: Response omits one ticker
- **WHEN** a batch response succeeds but omits one requested ticker
- **THEN** the omitted ticker SHALL receive `record_not_found` evidence without discarding other ticker evidence

### Requirement: Provider and ticker failures are isolated

A failure for one provider, method, ticker, or field SHALL NOT cancel independent requests in the same batch; failure status and reason SHALL remain visible in sidecar evidence.

#### Scenario: One provider fails
- **WHEN** one provider raises a transport/schema/permission/rate-limit error
- **THEN** other registered providers SHALL still run and the failed provider SHALL produce classified evidence

#### Scenario: One ticker fails
- **WHEN** one ticker cannot be normalized or parsed
- **THEN** other canonical tickers SHALL continue and the invalid ticker SHALL be reported without writing a production value

### Requirement: Merge is evidence-preserving and fail closed

The merge SHALL retain all source evidence and SHALL NOT use first-non-empty, silent defaults, mechanical averages, or stale overrides to select a canonical value.

#### Scenario: Providers agree
- **WHEN** multiple eligible providers return the same normalized value/unit/time basis
- **THEN** the canonical snapshot MAY contain that value while retaining all provider evidence

#### Scenario: Providers conflict
- **WHEN** providers disagree in value, unit, currency, report period, or freshness
- **THEN** the canonical value SHALL be null/conflict until an explicit policy resolves it

### Requirement: Shadow providers cannot enter production values

Candidate or shadow providers SHALL be represented in evidence but SHALL NOT override or populate production canonical values unless an explicit later qualification policy marks the field production eligible.

#### Scenario: LongPort or Longbridge runs in shadow mode
- **WHEN** a candidate provider returns a value
- **THEN** the value SHALL remain shadow/not_qualified in sidecar and SHALL be null in production canonical values

### Requirement: Batch call identity is auditable

Each batch invocation SHALL record provider, method, requested ticker-set hash, batch size, call count, response hash, status summary, and generated run_id.

#### Scenario: Batch call statistics are reported
- **WHEN** a batch run completes or partially fails
- **THEN** the evidence manifest SHALL include requested/returned/missing tickers and provider/method call counts
