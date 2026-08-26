## ADDED Requirements

### Requirement: Shared diagnostic artifact proof

The system SHALL provide a deterministic proof boundary that accepts an already-computed and contract-validated `growth_expectation_diagnostic` artifact without invoking the growth expectation engine or modifying the artifact. The proof SHALL verify that the strong single-agent and Council envelopes reference the same canonical diagnostic artifact and the same canonical `assumption_snapshot`.

#### Scenario: Both paths consume the same artifact and assumptions

- **WHEN** both path envelopes carry matching ticker, run_id, dossier_snapshot, diagnostic_digest, and assumption_snapshot_digest for one valid diagnostic artifact
- **THEN** the proof SHALL return a passed result with shared artifact and assumption digests

#### Scenario: Different assumption snapshots fail closed

- **WHEN** the path envelopes reference assumption snapshots with different canonical content
- **THEN** the proof SHALL raise a proof error and SHALL NOT return a passed result

#### Scenario: Artifact replacement fails closed

- **WHEN** the diagnostic payload is changed without recomputing its canonical diagnostic digest
- **THEN** the proof SHALL raise a proof error before producing an audit result

### Requirement: End-to-end identity chain

The proof SHALL require an explicit audit sidecar identity containing canonical ticker, run_id, dossier_snapshot, diagnostic_digest, and assumption_snapshot_digest. It SHALL require exact equality of these fields across the sidecar and both path envelopes. Missing, blank, or mismatched identity fields SHALL fail closed; the sidecar SHALL be retained as the run-to-artifact binding evidence because the existing diagnostic contract intentionally does not add run_id to the computed artifact.

#### Scenario: Identity chain is complete

- **WHEN** ticker, run_id, dossier_snapshot, diagnostic_digest, and assumption_snapshot_digest match across the audit sidecar, both paths, and the artifact provenance
- **THEN** the proof SHALL expose the complete identity chain in its result

#### Scenario: Ticker or run mismatch fails closed

- **WHEN** either path has a different ticker or run_id from the shared identity
- **THEN** the proof SHALL raise a proof error

#### Scenario: Run sidecar mismatch fails closed

- **WHEN** the supplied diagnostic identity sidecar has a run_id different from the run_id argument
- **THEN** the proof SHALL raise a proof error

#### Scenario: Dossier or diagnostic digest mismatch fails closed

- **WHEN** either path has a different dossier_snapshot or diagnostic_digest from the shared artifact
- **THEN** the proof SHALL raise a proof error

### Requirement: Council incremental evidence classification

The system SHALL classify Council findings against a strong-single-agent baseline using stable fingerprints. Findings already present in the baseline SHALL NOT count as Council increment. Findings of kind `shared_diagnostic` SHALL NOT count as Council increment only when they carry the matching diagnostic digest and one of the supported diagnostic metrics `future_value_share`, `implied_growth_rate`, or `value_pulled_forward_years`. Only new findings of kind `counter_evidence`, `risk`, `key_variable`, or `assumption_challenge` SHALL count as valid Council increment.

#### Scenario: Shared deterministic calculation is excluded

- **WHEN** Council adds a finding that only restates a shared diagnostic value or derived metric
- **AND** the finding carries the shared diagnostic digest and a supported metric name
- **THEN** the finding SHALL be classified as excluded shared calculation and SHALL contribute zero Council increment

#### Scenario: New substantive finding counts

- **WHEN** Council adds a new finding of an allowed substantive kind not present in the baseline
- **THEN** the finding SHALL count as one valid Council increment

#### Scenario: Baseline duplicate does not count

- **WHEN** Council repeats a baseline finding with the same stable fingerprint
- **THEN** the finding SHALL be classified as duplicate and SHALL contribute zero Council increment

#### Scenario: Unsupported finding kind fails closed

- **WHEN** a Council finding uses an unrecognized kind
- **THEN** the classifier SHALL raise a proof error rather than counting it
