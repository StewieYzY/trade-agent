## ADDED Requirements

### Requirement: Fixed baseline input identity
The system SHALL accept a versioned M2.1 baseline envelope that explicitly
binds canonical ticker, `run_id`, attempt index, M0.1 diagnostic digest,
dossier digest, complete input digest, prompt version, profile version, model,
heavy reasoning level, budget configuration, and input artifact identity to a
complete M0.2 Thesis draft input.

#### Scenario: Valid fixed baseline input
- **WHEN** every declared identity and digest matches the recomputed M0.2 input
- **THEN** the system accepts the envelope and derives one stable baseline input digest plus a deterministic attempt identity

#### Scenario: Identity or digest mismatch
- **WHEN** ticker, run, profile, diagnostic, dossier, input, prompt, or artifact identity does not match the bound M0.2 input
- **THEN** the system records a structural failed attempt after safe envelope parsing and performs zero provider calls

### Requirement: Reused M0.2 execution boundary
The system SHALL execute a valid baseline attempt through the existing M0.2
strong-agent Thesis draft boundary and MUST NOT duplicate its diagnostic,
dossier, prompt, `AgentOutput`, provider, or quality validation logic.

#### Scenario: One valid baseline attempt
- **WHEN** a valid baseline envelope is run with a fake provider seam
- **THEN** the M0.2 boundary is called once with the bound input, explicit model, heavy reasoning level, and existing exact provider call signature

#### Scenario: Provider or AgentOutput failure
- **WHEN** the provider transport fails or the response violates the existing AgentOutput contract
- **THEN** the baseline record preserves the M0.2 failed state, reason, zero-success semantics, and output digest without presenting the attempt as completed

### Requirement: Auditable baseline record
The system SHALL generate one deterministic record per safely identified
attempt with stable identity, attempt identity, budget, normalized token/cost
usage, quality status, execution status, failure/skip/degraded reasons, output
digest, and M0.2 artifact digest.

#### Scenario: Successful record
- **WHEN** M0.2 returns a valid non-skip output within budget
- **THEN** the record is completed and includes the exact fixed identity, usage, output digest, and attempt index

#### Scenario: Degraded or budget-exceeded record
- **WHEN** M0.2 returns a warning/degraded output or measured usage exceeds the fixed budget
- **THEN** the record is degraded and states each reason without altering the underlying M0.2 output

#### Scenario: Skip, out-of-circle, or blocked diagnostic
- **WHEN** the agent skips, is out of circle, or the diagnostic is `not_evaluable` or `failed`
- **THEN** the record is skipped or failed as defined by the existing M0.2 semantics and retains the explicit reason

#### Scenario: Dossier or diagnostic preflight failure
- **WHEN** the existing M0.2 preflight rejects dossier or diagnostic quality after safe baseline identity parsing
- **THEN** the system writes a structural failed record, writes no success artifact, and performs zero provider calls

### Requirement: Deterministic repeated-run comparison
The system SHALL compare two or more validated records deterministically,
sorting attempts by attempt index and separating must-stay-stable identity
fields from permitted model-output and usage drift.

#### Scenario: Stable repeated output
- **WHEN** all stable fields, quality states, output digests, and usage values match
- **THEN** the comparison status is `stable` and reports no structural failure or drift

#### Scenario: Permitted model or usage drift
- **WHEN** stable identity matches but output digest, quality status, token usage, or cost changes
- **THEN** the comparison status is `drifted` and explicitly reports output, quality, token, and cost changes

#### Scenario: Structurally incomparable records
- **WHEN** a must-stay-stable field differs, an attempt index is duplicated, or a record is malformed
- **THEN** the comparison status is `structural_failure` and identifies every structural reason

### Requirement: Deterministic isolated artifacts
The system SHALL render record and comparison JSON/Markdown from the same
validated mappings using deterministic serialization, explicit output
directories, and no provider-dependent timestamp.

#### Scenario: Record artifact isolation
- **WHEN** an attempt is run with an explicit output directory
- **THEN** its M0.2 draft and baseline record are confined to the deterministic attempt subdirectory

#### Scenario: Comparison artifact determinism
- **WHEN** the same validated records are compared more than once
- **THEN** JSON and Markdown bytes are identical and state that the artifact is not G2 Capability Gate evidence

### Requirement: Engineering and capability status separation
The system SHALL mark M2.1 records and comparisons as engineering experiment
artifacts with `capability_status=not_evidence` and
`gate_status=not_passed`.

#### Scenario: Engineering closure does not pass G2
- **WHEN** tests, validation, archive, merge, and push complete
- **THEN** the artifacts and completion report still do not claim that G2 Capability Gate passed or that real user review occurred
