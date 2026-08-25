## ADDED Requirements

### Requirement: Deterministic V0 valuation anchors

The engine SHALL consume validated contract input and assumptions and compute an EPV proxy range from normalized earnings basis, confirmed maintenance capex ratio, cost of equity, and maintenance growth; it SHALL also compute a mature-PE cross-anchor range from normalized net profit and confirmed mature PE. The engine MUST preserve signed priced-growth value and share and MUST NOT silently substitute defaults.

#### Scenario: Valid positive input produces both anchors
- **WHEN** validated positive input and confirmed assumptions have finite discount spread
- **THEN** the engine SHALL return EPV and mature-PE ranges, signed priced-growth ranges, and a diagnostic-grade artifact

#### Scenario: Discount spread is not positive
- **WHEN** any required EPV interval combination has cost of equity less than or equal to maintenance growth
- **THEN** the engine SHALL return a non-clean status with an explicit machine-readable reason and MUST NOT emit fabricated EPV numbers

#### Scenario: Negative priced growth is retained
- **WHEN** current market value is below the current-business-value anchor range
- **THEN** priced-growth value and share SHALL remain negative rather than being clamped to zero

### Requirement: Mutually exclusive reverse solving

The engine SHALL honor the validated `reverse_mode` and solve exactly one reverse input family at a time: fixed growth rate SHALL produce conservative/base/optimistic implied high-growth durations; fixed duration SHALL produce conservative/base/optimistic implied growth rates. It MUST use a finite horizon no greater than the contract cap and MUST report no finite solution explicitly.

#### Scenario: Fixed growth rate solves duration
- **WHEN** reverse mode is `fixed_growth_rate` and three positive growth-rate inputs are confirmed
- **THEN** the artifact SHALL contain exactly three named scenarios whose growth rates equal the frozen inputs and whose durations are finite and non-negative

#### Scenario: Fixed duration solves growth rate
- **WHEN** reverse mode is `fixed_duration` and three positive duration inputs within the cap are confirmed
- **THEN** the artifact SHALL contain exactly three named scenarios whose durations equal the frozen inputs and whose growth rates are finite

#### Scenario: Reverse mode is not mixed
- **WHEN** the validated snapshot selects one reverse mode
- **THEN** the artifact SHALL not contain scenarios from the other mode or claim both unique implied growth and duration

#### Scenario: No finite reverse solution
- **WHEN** no bounded duration or no positive growth rate can reconcile the market value under the frozen model
- **THEN** the engine SHALL return `not_evaluable` or `failed` with `no_finite_solution`/solver reason codes and no numeric conclusions

### Requirement: Sensitivity and expectation interpretation

The engine SHALL compute assumption-bound sensitivity for valuation/reverse outputs, credible growth range, expectation gap, expectation overdraft, and value pulled forward years. Sensitivity values MUST remain inside validated assumption bounds, and the artifact SHALL retain whether the result is `clean`, `degraded`, `not_evaluable`, or `failed`.

#### Scenario: Sensitivity changes with discount assumptions
- **WHEN** cost of equity or maintenance capex ratio changes within its confirmed range
- **THEN** the output SHALL expose a reproducible impact range and higher discount/capex assumptions SHALL NOT increase the EPV proxy

#### Scenario: Credible growth gap is visible
- **WHEN** the reverse base case is above the credible growth range
- **THEN** `expectation_gap` and `expectation_overdraft` SHALL explicitly show the excess rather than hiding it in prose

#### Scenario: Industry uncertainty is visible
- **WHEN** the validated input has no industry but otherwise passes applicability
- **THEN** the engine SHALL retain `industry_unknown` as a warning/degraded status and SHALL preserve it in the artifact

### Requirement: Immutable provenance-bound artifact

The engine SHALL produce an immutable, serializable diagnostic artifact containing the exact input snapshot, assumption snapshot, formula/profile/dossier provenance, evidence context fields, status/reasons/warnings, input digest and diagnostic digest. The generated artifact SHALL pass the archived contract's binding validation; repeated computation with identical inputs SHALL produce identical serialized output.

#### Scenario: Provenance binds output
- **WHEN** an artifact is computed with explicit dossier snapshot, profile version, and formula version
- **THEN** `validate_diagnostic_binding` SHALL accept it and mutation of input, assumptions, provenance, or output values SHALL be rejected

#### Scenario: Identical inputs are reproducible
- **WHEN** the same validated inputs and provenance are computed twice
- **THEN** canonical serialized artifacts and digests SHALL be equal

#### Scenario: Invalid input fails closed
- **WHEN** input or assumption payload is missing, malformed, non-finite, unit-inconsistent, or unconfirmed
- **THEN** the engine SHALL raise the contract error or return an explicit not-evaluable artifact and MUST NOT perform a partial successful calculation
