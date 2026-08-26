# investment-thesis Specification

## Purpose
TBD - created by archiving change g2-growth-expectation-dossier-integration. Update Purpose after archive.
## Requirements
### Requirement: InvestmentThesis consumes dossier valuation expectation

The integration adapter SHALL construct an `InvestmentThesis` mapping from an existing thesis/base mapping and a validated research dossier, adding `valuation_expectation` from the dossier without recomputation. The mapping SHALL preserve diagnostic identity, assumption snapshot, provenance, calculation status, quality status, warnings/reasons and failure metadata.

#### Scenario: Thesis receives the exact bound artifact view

- **WHEN** a dossier contains a validated growth diagnostic
- **THEN** the resulting thesis SHALL expose `valuation_expectation` with the same canonical serialized artifact and matching input/diagnostic digests

#### Scenario: Assumptions and provenance are not dropped

- **WHEN** the diagnostic contains a confirmed assumption snapshot and provenance
- **THEN** the thesis valuation expectation SHALL retain the assumptions mapping, snapshot version, dossier/profile/formula provenance and source identity fields

### Requirement: InvestmentThesis fail-closed numeric publication

The adapter MUST preserve the diagnostic status and MUST reject any dossier or diagnostic view that attempts to publish numeric conclusions for `not_evaluable` or `failed` statuses. Such a thesis may retain non-numeric reasons and pending verification, but SHALL NOT become a passed or clean valuation conclusion.

#### Scenario: Not evaluable thesis is explicit

- **WHEN** diagnostic calculation status is `not_evaluable`
- **THEN** the thesis SHALL expose `calculation_status=not_evaluable`, explicit failure reason metadata and no numeric valuation fields

#### Scenario: Failed thesis is explicit

- **WHEN** diagnostic calculation status is `failed`
- **THEN** the thesis SHALL expose `calculation_status=failed`, `quality_status=failed`, failure kind/reasons/digests and no numeric valuation fields
