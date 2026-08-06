## ADDED Requirements

### Requirement: Qualification runner SHALL emit canonical provenance-compatible evidence

The qualification runner SHALL copy the canonical field identity and response hash
(`market`, `ticker`, `raw_field`, and `response_hash`) into each evidence item's
`provenance` object, using the same values as the evidence top level. This SHALL
hold for available and non-available field evidence so the downstream validator
can distinguish provider failure from a malformed provenance contract.

#### Scenario: Available runner evidence remains eligible for evaluation

- **WHEN** a completed `QualificationRunner` output contains an available field
  with valid value, unit, time basis, and response hash
- **THEN** `validate_field_evidence()` SHALL keep the field `available`, and the
  evaluator-to-promotion path SHALL be able to qualify it without reconstructing
  provenance at a later layer

#### Scenario: Runner provenance mirrors top-level identity

- **WHEN** the runner emits field evidence
- **THEN** `provenance.market`, `provenance.ticker`, `provenance.raw_field`, and
  `provenance.response_hash` SHALL equal the corresponding top-level values

#### Scenario: Response metadata cannot override canonical provenance

- **WHEN** a provider response envelope contains `_meta` or field metadata with
  values for provenance-reserved keys
- **THEN** the runner SHALL preserve its canonical provider, method, market, ticker,
  raw field, response hash, `retrieved_at`, and `run_scoped` values in `provenance`
  while retaining only non-reserved metadata as additional provenance
 ### Requirement: Promotion SHALL consume only complete qualification runs

The promotion evaluator SHALL read a run-scoped qualification manifest and evidence
artifact, require a completed run with matching evidence counts and a valid frozen
probe plan, and SHALL reject missing, incomplete, or malformed source artifacts
without writing a canonical snapshot.

#### Scenario: Incomplete qualification run is blocked

- **WHEN** the source manifest has `completion_status` other than `completed`, or
  `evidence.json` is absent or not a list
- **THEN** promotion SHALL return a blocked decision and SHALL NOT write
  `decision.json` or canonical records

#### Scenario: Evidence count mismatch is blocked

- **WHEN** the manifest evidence count does not match the loaded evidence length
- **THEN** promotion SHALL fail closed with an explicit source-artifact reason

### Requirement: Promotion SHALL evaluate an explicit versioned field policy

The evaluator SHALL apply a named policy containing the canonical ticker set and
required method/field coverage, and SHALL record the policy version and policy hash
in its decision output.

#### Scenario: Frozen ticker and field coverage is reproducible

- **WHEN** the same evidence, policy version, and evaluation reference are evaluated
  twice
- **THEN** the policy hash and per-group decision reasons SHALL be stable

#### Scenario: Unexpected ticker or field is isolated

- **WHEN** evidence contains a ticker, method, or field outside the policy matrix
- **THEN** that evidence SHALL be rejected as `invalid_value` and SHALL NOT make an
  in-policy field eligible

### Requirement: A field group SHALL require complete, valid, consistent evidence

For each `(provider_family, provider, method, field)` group, promotion SHALL require
one evidence item per required canonical ticker with status `available`, explicit
provenance, valid `retrieved_at`, valid unit/currency and time basis for numeric
fields, and consistent value metadata across tickers.

#### Scenario: Complete group is promoted

- **WHEN** every required ticker has exactly one valid available evidence item and
  all policy constraints pass
- **THEN** every item in the group SHALL be copied with
  `eligibility=production_eligible` and the decision SHALL be `qualified`

#### Scenario: Missing or failed ticker blocks whole group

- **WHEN** one required ticker is missing or has `record_not_found`,
  `source_failed`, `invalid_value`, or `not_evaluated`
- **THEN** the group decision SHALL be `rejected` and no item in that group SHALL
  become production eligible

#### Scenario: Metadata conflict blocks whole group

- **WHEN** group evidence has conflicting unit, currency, as-of, report period,
  freshness, or normalized value metadata
- **THEN** the group decision SHALL be `rejected` with a conflict reason and the
  canonical value for that group SHALL remain null

### Requirement: Promotion SHALL preserve source evidence and failure semantics

The evaluator SHALL never overwrite the source qualification run, SHALL preserve
all source statuses and redacted reasons in a decision sidecar, and SHALL not
replace failures with defaults or implicit fallback values.

#### Scenario: Rejected evidence remains auditable

- **WHEN** a field group is rejected
- **THEN** its original evidence SHALL remain unchanged in the source run and the
  decision sidecar SHALL include the rejection reason and source evidence identity

#### Scenario: Candidate provider does not fall back to baseline

- **WHEN** a candidate provider group is rejected or unavailable
- **THEN** promotion SHALL not copy a baseline provider value into that candidate
  group's decision or claim the candidate field is qualified

### Requirement: Promotion output SHALL be immutable and isolated

The promotion entrypoint SHALL write a separate run-scoped output containing a
decision artifact and canonical snapshot artifacts, reject duplicate or unsafe run
identities, and refuse protected production paths.

#### Scenario: Successful promotion writes auditable artifacts

- **WHEN** at least one field group is qualified
- **THEN** the output SHALL contain the source run identity, policy hash, decision
  hash, canonical snapshot identity, and field provenance sidecar

#### Scenario: Duplicate promotion run is rejected

- **WHEN** the target promotion run directory already exists
- **THEN** the entrypoint SHALL fail without modifying existing files

#### Scenario: Protected output root is rejected

- **WHEN** the requested output root is a legacy cache, ranking, watchlist, debate,
  or canonical production root
- **THEN** the entrypoint SHALL fail before creating any artifact

### Requirement: Promotion SHALL NOT unlock downstream capability gates

The change SHALL remain an isolated evidence/promotion artifact and SHALL NOT alter
ranking, cache, watchlist, debate, diagnostic, G1, G2, or G3 runtime state.

#### Scenario: Promotion completes without consumer migration

- **WHEN** a promotion run completes
- **THEN** no legacy consumer artifact SHALL be changed and no capability gate SHALL
  be marked passed
