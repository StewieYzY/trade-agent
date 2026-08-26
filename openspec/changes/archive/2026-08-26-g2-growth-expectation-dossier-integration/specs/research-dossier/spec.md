## ADDED Requirements

### Requirement: Dossier preserves a bound growth diagnostic artifact

`build_research_dossier` SHALL accept an optional already-computed `growth_expectation_diagnostic` and, when supplied, SHALL validate its complete contract binding against the canonical dossier identity before returning. The returned dossier SHALL preserve the artifact as JSON-compatible data under `growth_expectation_diagnostic` and expose the same data as `valuation_expectation` without recomputation or numeric field rewriting.

#### Scenario: Valid artifact is injected and preserved

- **WHEN** a valid diagnostic artifact for the requested ticker is supplied with matching dossier/profile/formula provenance
- **THEN** the dossier SHALL contain the artifact, its `valuation_expectation` view, both digests, the assumption snapshot, provenance and the original calculation/quality status

#### Scenario: Identity or digest mismatch fails closed

- **WHEN** the supplied artifact ticker, input snapshot, assumption snapshot, provenance or input/diagnostic digest does not match the requested dossier identity
- **THEN** dossier construction SHALL raise a contract validation error and SHALL NOT return a partially bound dossier

#### Scenario: Legacy dossier call remains compatible

- **WHEN** no growth diagnostic is supplied
- **THEN** dossier construction SHALL retain its existing fact sections and SHALL NOT invoke the growth expectation engine implicitly

### Requirement: Dossier preserves diagnostic quality and failure semantics

The dossier SHALL retain `clean`, `degraded`, `not_evaluable` and `failed` `calculation_status` values, diagnostic `quality_status`, warnings/reasons, failure kind/reason codes, assumption snapshot and provenance exactly as supplied by the validated artifact. A `not_evaluable` or `failed` artifact SHALL not be transformed into a numeric conclusion.

#### Scenario: Degraded warnings remain visible

- **WHEN** the diagnostic has `calculation_status=degraded`
- **THEN** the dossier SHALL expose its non-empty warnings and preserve `quality_status=warning` without promoting it to clean

#### Scenario: Failure result contains no numeric conclusion

- **WHEN** the diagnostic has `calculation_status=not_evaluable` or `failed`
- **THEN** the dossier diagnostic and valuation view SHALL contain no current market value, business value, growth range, reverse scenario or sensitivity conclusion
