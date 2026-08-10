## ADDED Requirements

### Requirement: Runtime executes three real staged fetch boundaries
The runtime SHALL execute Stage A, Stage B, and Stage C in order, with Stage A
requesting only `basic`, Stage B requesting only `financials` and `risk`, and
Stage C requesting only `valuation` and `kline`. The runtime MUST NOT request
`main_business`, `peers`, or `research` in any G1 stage.

#### Scenario: Stage dimensions are isolated
- **WHEN** a staged run is executed for an input ticker set
- **THEN** the fetch calls SHALL use exactly the stage allowlists and no G2
  dossier dimension SHALL appear in any call

#### Scenario: Historical valuation is deferred
- **WHEN** Stage A and Stage B execute
- **THEN** no `valuation` fetch SHALL occur before Stage C

### Requirement: Stage ticker sets are passed monotonically
Each stage SHALL receive only the output ticker set of the preceding stage.
The runtime SHALL expose the input and output ticker identities for every stage,
and the stage counts SHALL be monotonically non-increasing.

#### Scenario: Failed Stage A ticker is excluded from Stage B
- **WHEN** a ticker fails a required Stage A dimension or Stage A gate
- **THEN** that ticker SHALL NOT be present in Stage B input or fetch calls

#### Scenario: Failed Stage B ticker is excluded from Stage C
- **WHEN** a ticker fails a required Stage B dimension or Stage B hard gate
- **THEN** that ticker SHALL NOT be present in Stage C input or fetch calls

#### Scenario: Monotonic evidence is verifiable
- **WHEN** a staged run completes
- **THEN** evidence SHALL prove `A.input >= B.input >= C.input >= C.output`
  by ticker-set cardinality and identity

### Requirement: Screening dependencies preserve existing L1 semantics
The runtime SHALL reuse the existing hard-gate, factor-score, anti-trap, and
heat-filter functions without changing their ranking rules. Stage A SHALL use
basic/current valuation data for preliminary filtering, Stage B SHALL apply the
financials/risk-dependent hard gates, and Stage C SHALL calculate the complete
factor, anti-trap, and heat result. Final scoring SHALL preserve the legacy
order of score calculation, descending sort, top-300 truncation, and heat filter.

#### Scenario: Existing ranking output remains stable
- **WHEN** a ticker has complete data in all three stages
- **THEN** its final factor scores, adjusted composite ordering, and heat-filter
  decision SHALL match the existing L1 functions, including top-300 truncation

#### Scenario: Missing later-stage data is not treated as a pass
- **WHEN** a ticker lacks a required Stage B or Stage C field
- **THEN** it SHALL be marked not evaluated/degraded or failed and SHALL NOT be
  promoted by a default value

### Requirement: Failure visibility and batch isolation
The runtime SHALL preserve complete, degraded, record_not_found, source_failed,
invalid_value, not_evaluated, and stale states when present. A failure for one
ticker SHALL not abort processing of other tickers.

#### Scenario: One ticker failure does not block the batch
- **WHEN** one ticker returns a provider failure in a stage
- **THEN** other tickers SHALL continue through that stage and the failed ticker
  SHALL not enter the next stage

#### Scenario: Unavailable values remain unavailable
- **WHEN** a field has source_failed, record_not_found, invalid_value,
  not_evaluated, stale, or degraded status
- **THEN** the runtime SHALL expose null/unavailable value plus the original
  status/reason and SHALL NOT substitute a default

### Requirement: Stage execution evidence is auditable
Every completed stage SHALL emit run-scoped evidence containing stage name,
input_tickers, output_tickers, requested_dimensions, provider_calls, cache_hits,
and failures. Provider calls and cache hits SHALL be distinguishable.

#### Scenario: Evidence records actual boundary calls
- **WHEN** a stage invokes the fetcher
- **THEN** evidence SHALL identify each requested dimension and the ticker set
  passed to that fetch boundary

#### Scenario: Cache hit is not reported as provider call
- **WHEN** a dimension result is served from cache
- **THEN** evidence SHALL count it as a cache hit and SHALL NOT count it as a
  provider call

### Requirement: Canonical field metadata is retained
When canonical snapshot fields are supplied to the runtime, the runtime SHALL
preserve each field's value, status, reason, provenance, as_of, and freshness
metadata in the ticker/stage evidence. The runtime MUST NOT write or mutate the
canonical snapshot. Any represented field used by the current stage whose status
is unavailable, rejected, stale, degraded, partial, or otherwise not fresh SHALL
fail closed and prevent that ticker from entering the next stage.

#### Scenario: Available canonical field is retained
- **WHEN** a field is available through the read-only consumer
- **THEN** evidence SHALL retain its value and all associated identity metadata

#### Scenario: Rejected canonical field remains explicit
- **WHEN** a field is rejected, stale, degraded, or not evaluated
- **THEN** evidence SHALL retain null value and its status/reason/provenance and
  the ticker SHALL not be promoted by raw fetch data

### Requirement: Runtime has no unauthorized side effects
The staged runtime SHALL not call LLMs, write watchlist/debate/cache/production
canonical artifacts, or create files outside an explicitly supplied evidence
destination. A fetcher SHALL be explicitly supplied by the caller; the runtime
MUST NOT create a default live `BatchFetcher`. Tests SHALL be able to run with
injected fakes and no network.

#### Scenario: Offline execution is deterministic
- **WHEN** tests provide a fake fetcher and frozen ticker inputs
- **THEN** the runtime SHALL complete without provider, LLM, or network calls

#### Scenario: No implicit production writes
- **WHEN** no evidence destination is supplied
- **THEN** the runtime SHALL return in-memory evidence without writing files

### Requirement: Evidence is serializable and identity-bound
The runtime SHALL expose run identity, input ticker-set hash, canonical ticker
identities, stage requests, provider/cache telemetry, stage-scoped dimension
results, and deduplicated failures through a JSON-serializable evidence object.
The runtime SHALL generate a unique run identity when the caller does not supply
one and SHALL canonicalize duplicate ticker forms.

#### Scenario: Evidence round-trips through JSON
- **WHEN** a staged run result is serialized
- **THEN** `json.dumps(result.to_dict())` SHALL succeed and preserve run identity
  and stage dimension results

#### Scenario: Duplicate ticker forms collapse
- **WHEN** input contains `600001` and `600001.SH`
- **THEN** the runtime SHALL fetch one canonical ticker identity and expose one
  input-set hash
