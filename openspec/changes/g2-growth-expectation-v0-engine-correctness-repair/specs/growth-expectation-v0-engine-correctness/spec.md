## ADDED Requirements

### Requirement: Reverse solutions must satisfy the valuation equation

The engine SHALL use a separately defined normalized earnings basis for reverse valuation, SHALL bracket each solution within the allowed duration/growth domain, and SHALL reject any result whose discounted value does not match current market value within a documented residual tolerance. A target below the zero-growth terminal floor SHALL be treated as no finite reverse solution rather than as a zero-year numeric conclusion.

#### Scenario: Fixed growth result has bounded residual
- **WHEN** fixed-growth reverse returns a duration
- **THEN** evaluating the same scenario with the engine's frozen assumptions SHALL reproduce current market value within tolerance

#### Scenario: Fixed duration result has bounded residual
- **WHEN** fixed-duration reverse returns a growth rate
- **THEN** evaluating the same scenario with the frozen duration SHALL reproduce current market value within tolerance

#### Scenario: Unbracketed target fails closed
- **WHEN** target market value is outside the finite solver domain
- **THEN** the engine SHALL return a computation failure with a solver reason and no numeric conclusions

### Requirement: Sensitivity is single-variable and complete

The engine SHALL perturb one validated assumption at a time while holding other assumptions at deterministic base values, and SHALL expose reproducible, metric-labelled impact ranges for current-business value, reverse base, expectation gap, expectation overdraft rank and value-pulled-forward years required by the archived V0 spec.

#### Scenario: Different assumptions produce different impacts
- **WHEN** maintenance capex ratio and cost of equity are varied over the same input
- **THEN** their sensitivity outputs SHALL be computed from their own perturbation and SHALL NOT be copied from one another

#### Scenario: Midpoint overdraft is classified
- **WHEN** the base implied growth exceeds credible midpoint but does not exceed credible upper bound
- **THEN** expectation overdraft SHALL be `above_base_case`

### Requirement: Failure artifacts preserve identity without conclusions

The engine SHALL return a contract-valid failure/not-evaluable artifact for contract-valid but economically inapplicable inputs such as negative normalized net profit. Such artifacts SHALL preserve the exact input snapshot, assumptions, provenance, digests, reason codes and reasons, while carrying no numeric conclusions.

#### Scenario: Negative net profit returns failure artifact
- **WHEN** normalized net profit is finite but negative
- **THEN** the engine SHALL return a contract-valid `not_evaluable` or `failed` artifact instead of leaking a construction exception

#### Scenario: Facade validates its own binding
- **WHEN** the engine returns any artifact
- **THEN** the facade SHALL validate its own input/output/provenance/digest binding before returning
