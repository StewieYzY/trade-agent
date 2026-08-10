## ADDED Requirements

### Requirement: Completed source runs are plan-complete and hash-verifiable

The promotion loader MUST require valid `manifest.json`, `plan.json`, and
`evidence.json` artifacts for a completed source run. It MUST recompute the
recorded artifact hashes and reject any missing, malformed, truncated, or
tampered artifact before qualification evaluation.

#### Scenario: Missing plan is rejected

- **WHEN** a completed source run has `manifest.json` and `evidence.json` but no
  `plan.json`
- **THEN** loading the source run fails closed with a source completeness error

#### Scenario: Truncated plan is rejected

- **WHEN** `plan.json` is not valid JSON or does not contain a valid frozen plan
- **THEN** loading the source run fails closed without evaluating evidence

#### Scenario: Artifact hash mismatch is rejected

- **WHEN** a manifest-recorded plan, evidence, or manifest hash does not match the
  bytes currently on disk
- **THEN** loading the source run fails closed as tampered or inconsistent

### Requirement: Source identity must be internally consistent

The source validator MUST require run identity, ticker identity, method identity,
field identity, and evidence identity to agree across manifest, plan, and evidence.

#### Scenario: Run identity mismatch is rejected

- **WHEN** the run ID in evidence or plan differs from the manifest run ID
- **THEN** the source run is rejected before policy evaluation

#### Scenario: Evidence outside the frozen plan is rejected

- **WHEN** an evidence item has a ticker, method, or field not declared by its plan
- **THEN** the item causes a rejected source decision and cannot be promoted

#### Scenario: Response tampering is rejected

- **WHEN** evidence content or its response hash is changed after the source run
  was completed
- **THEN** the source run is rejected before any snapshot is written

### Requirement: Required policy matrix is complete

The evaluator MUST validate every policy-required field group across the declared
plan/ticker matrix. A group with only some fields or some tickers MUST be rejected;
the evaluator MUST NOT fill defaults, skip missing groups, or qualify the partial
set.

#### Scenario: Missing field group is rejected

- **WHEN** a policy requires a method/field group that has no valid evidence
- **THEN** the decision is blocked and includes a missing-field-group reason

#### Scenario: Partial field presence is not qualified

- **WHEN** only part of a required method's field set is available
- **THEN** the entire required group remains rejected

#### Scenario: Complete legal source run qualifies

- **WHEN** all plan, identity, hash, ticker, status, provenance, and matrix checks
  pass
- **THEN** the source group is qualified for promotion

### Requirement: Probe plan version is explicit and bound

The promotion CLI MUST bind the policy to the provider qualification runner's
explicit probe plan version and MUST reject an omitted, unknown, or mismatching
plan version rather than silently evaluating another plan.

#### Scenario: Wrong plan version is rejected

- **WHEN** the CLI policy version does not match the source probe plan version
- **THEN** promotion returns a blocked decision

#### Scenario: Unbound plan version is rejected

- **WHEN** the CLI cannot identify the runner's explicit probe plan version
- **THEN** argument validation fails before promotion

### Requirement: Source evidence is immutable through promotion

Promotion MUST write isolated decision/snapshot artifacts without modifying any
source run file.

#### Scenario: Source bytes are unchanged

- **WHEN** a complete legal source run is promoted
- **THEN** every source artifact remains byte-for-byte identical before and after
  promotion
