## ADDED Requirements

### Requirement: Promotion SHALL preserve evaluated rejected evidence in canonical snapshots

For every in-policy evaluated field, promotion SHALL provide the field evidence to the canonical snapshot writer. A qualified field SHALL retain `status=available`, `eligibility=production_eligible`, and its canonical value. A rejected field SHALL retain `eligibility=not_qualified`, an explicit `null` canonical value, its original rejection status and reason, and its complete provenance/sidecar evidence.

#### Scenario: Qualified and source-failed fields are both visible

- **WHEN** one in-policy field group qualifies and another in-policy field group contains `source_failed` evidence
- **THEN** the qualified field is consumable with its value and the rejected field is present in canonical records with a `null` value and `not_qualified` sidecar status

#### Scenario: Rejected evidence is not silently converted to available

- **WHEN** an in-policy evidence item has `record_not_found`, `invalid_value`, `not_evaluated`, or `source_failed` status
- **THEN** the canonical snapshot preserves that status and rejection reason and does not write a value

#### Scenario: All fields rejected still produce explicit snapshot semantics

- **WHEN** every in-policy evaluated field is rejected
- **THEN** promotion writes a canonical snapshot whose records contain explicit `null` values and whose snapshot/provenance semantics identify the fields as `not_qualified`

### Requirement: Canonical snapshot readers SHALL be self-sufficient

The canonical snapshot records and provenance sidecar SHALL contain enough status, reason, provenance, source identity, ticker identity, and run identity for a reader to determine field qualification without loading `decision.json`.

#### Scenario: Reader determines field status from snapshot only

- **WHEN** a reader loads `records.json` and `provenance.json` from a promoted snapshot
- **THEN** it can distinguish `production_eligible` from `not_qualified`, recover the rejection reason and provenance, and verify the snapshot `run_id`, ticker identity, and source evidence identity without reading `decision.json`

### Requirement: Promotion SHALL preserve source and identity contracts

Promotion SHALL not modify source qualification artifacts. Snapshot identity, ticker identity, run identity, provenance, and source evidence hashes SHALL remain consistent between the source evidence, decision sidecar, and canonical snapshot output.

#### Scenario: Source qualification evidence remains immutable

- **WHEN** promotion processes mixed or rejected evidence
- **THEN** all source manifest, plan, and evidence bytes remain unchanged

#### Scenario: Snapshot identity remains bound to the source run

- **WHEN** promotion writes a canonical snapshot
- **THEN** its `run_id`, ticker set hash, source evidence hash, and provenance identities match the evaluated source evidence and promotion decision

#### Scenario: Top-level and provenance identities disagree

- **WHEN** an evidence item has different values for any of `provider_family`, `provider`, `method`, `market`, `ticker`, `raw_field`, `response_hash`, or `retrieved_at` between its top-level fields and `provenance`
- **THEN** an available item is downgraded to `not_evaluated` and cannot be promoted, while an already rejected item retains its original rejection status and receives an explicit provenance mismatch reason
