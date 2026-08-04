## ADDED Requirements

### Requirement: Snapshot run is immutable and reproducible

Each snapshot sync SHALL create a unique run-scoped directory with a manifest, plan hash, ticker-set hash, source-set hash, schema version, and generation time, and SHALL reject overwriting an existing run.

#### Scenario: Duplicate run_id is rejected
- **WHEN** a snapshot is written with a run_id that already exists
- **THEN** the writer SHALL fail without modifying the existing run

#### Scenario: Manifest identifies the input
- **WHEN** a snapshot run completes
- **THEN** the manifest SHALL record the plan hash, ticker-set hash, source-set hash, code/schema version, as-of, and status summary

### Requirement: Raw evidence and canonical values are separated

The snapshot SHALL preserve field-level provenance/status separately from canonical consumer values, and SHALL NOT convert unqualified, failed, conflicted, or stale evidence into a clean value.

#### Scenario: Qualified value enters canonical record
- **WHEN** field evidence is available and explicitly eligible under the contract
- **THEN** the canonical record SHALL contain the normalized value and the sidecar SHALL retain its provenance

#### Scenario: Unqualified value remains visible but not consumable
- **WHEN** field evidence is `not_qualified`, `shadow_only`, `source_failed`, `conflict`, or `not_evaluated`
- **THEN** the canonical value SHALL be `null` and the sidecar SHALL preserve status/reason/provenance

### Requirement: Source-set identity reflects provenance

The source-set hash SHALL include provider, method, response hash, field status, and eligibility for all evidence participating in the snapshot.

#### Scenario: Provider or response changes hash
- **WHEN** a provider, method, response hash, status, or eligibility changes
- **THEN** the generated source-set hash SHALL change even if the final canonical value is unchanged

#### Scenario: Field ordering does not change hash
- **WHEN** the same evidence set is supplied in a different order
- **THEN** the source-set hash SHALL remain stable

### Requirement: Snapshot failures remain isolated

A failed ticker or field SHALL be represented in the snapshot sidecar and SHALL NOT prevent other tickers from being written; the failure SHALL NOT mutate legacy cache or ranking inputs.

#### Scenario: One ticker has source failure
- **WHEN** one ticker/field source fails during sync
- **THEN** the run SHALL preserve that failure status and continue writing independent ticker records

#### Scenario: Legacy cache remains unchanged
- **WHEN** a snapshot run is generated from legacy or qualification evidence
- **THEN** the writer SHALL not overwrite or delete existing `data/cache` files

### Requirement: Reader preserves metadata compatibility

The snapshot reader SHALL return a legacy-like value mapping together with sidecar metadata, and SHALL expose null/status for fields that are not eligible rather than silently omitting them.

#### Scenario: Consumer reads a sparse snapshot
- **WHEN** a requested field is not eligible
- **THEN** the reader SHALL return a visible null/status representation and SHALL not supply a zero/default value
