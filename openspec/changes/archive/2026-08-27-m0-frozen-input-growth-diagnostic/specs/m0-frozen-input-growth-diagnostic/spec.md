# m0-frozen-input-growth-diagnostic Specification

## Purpose

为 G2 / M0.1 提供一个只消费显式冻结 input bundle 的 deterministic growth
diagnostic 入口和 JSON/Markdown 产物。该 capability 产生 MVP evidence，不代表
G2 Capability Gate 通过。

## ADDED Requirements

### Requirement: Frozen input bundle is explicit and bound

The system SHALL accept only a versioned JSON bundle with
`schema_version=m0-frozen-growth-diagnostic-bundle-v1`, `canonical_ticker`, `run_id`,
`dossier_snapshot`, `profile_version`, `diagnostic_input`, and `assumption_snapshot`.
It SHALL construct `DiagnosticInput` and `AssumptionSnapshot` through the existing
validators. The envelope ticker SHALL match the validated diagnostic input ticker,
and the run ID SHALL be a safe relative path leaf.

#### Scenario: Valid bundle is accepted

- WHEN a bundle contains matching canonical identity and valid existing contract payloads
- THEN the adapter SHALL return validated input objects and execute the diagnostic

#### Scenario: Invalid envelope fails closed

- WHEN a required envelope field is absent, unknown, malformed, or identity-mismatched
- THEN the adapter SHALL raise a bundle validation error and SHALL NOT write artifacts

### Requirement: Diagnostic execution reuses existing semantics

The system SHALL call `compute_growth_expectation_diagnostic()` with the validated
objects and SHALL validate the returned artifact using the existing binding/digest
validation. It SHALL not call any provider, LLM, Council, or fallback implementation.

#### Scenario: Both reverse modes execute

- WHEN a valid bundle uses `fixed_growth_rate` or `fixed_duration`
- THEN the artifact SHALL contain the corresponding three reverse scenarios

#### Scenario: Deterministic execution

- WHEN the same bundle is executed more than once
- THEN the diagnostic fields and `input_digest`/`diagnostic_digest` SHALL be identical

### Requirement: Artifacts preserve evidence and status

The JSON artifact SHALL preserve the full diagnostic, including input sources with
source/report-period/as-of/currency/value-scale, assumption snapshot, provenance,
calculation status, quality status, reasons, warnings, and both digests. The envelope
SHALL identify the artifact as `growth_expectation_diagnostic`, `mvp_evidence`, and
`gate_status=not_passed`.

#### Scenario: Human-readable artifacts are generated

- WHEN execution succeeds or produces a valid non-clean diagnostic
- THEN deterministic JSON and Markdown files SHALL be written only below the explicit
  output directory

#### Scenario: Failure has no numeric conclusions

- WHEN the existing engine returns `not_evaluable` or `failed`
- THEN the artifacts SHALL preserve failure reason/provenance/digests and SHALL NOT
  contain numeric diagnostic conclusions

### Requirement: CLI is provider-free

The CLI SHALL read `--input`, accept `--output-dir`, invoke only the frozen-input
adapter, and print the generated paths. It SHALL not initialize provider or LLM clients.

#### Scenario: CLI help and execution are available

- WHEN the user invokes `growth-diagnostic --help` or supplies a valid bundle
- THEN the command SHALL show its options or generate the two artifacts

## Out of Scope

This capability SHALL NOT generate Investment Thesis, modify G2 umbrella Gate
conclusions, implement M0.2/M1/M2/M3/G3, or create formal Gate evidence.
