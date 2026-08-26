## ADDED Requirements

### Requirement: Quality gate results SHALL be consumed by the normal Council flow
The four existing quality dimensions SHALL be executable from the normal Council orchestrator, not only from an offline verification script. R1 circular-reference failures and invalid DA/R4 structures SHALL be hard failures; R1 grounding and R2 evidence deficiencies SHALL remain explicit soft warnings; DA skip reasons SHALL follow the existing low/extreme versus evidence-exhausted/runtime-degraded distinction.

#### Scenario: Gate functions are called with the correct shape
- **WHEN** a normal Council run reaches each quality-gate stage
- **THEN** the corresponding validator SHALL receive the actual `AgentOutput`/`SynthesizerOutput`, the raw dossier/features, active agent IDs where applicable, and the actual DA skip reason

#### Scenario: Soft warnings do not disappear
- **WHEN** a validator returns `pass=True` with warnings
- **THEN** the warnings SHALL be included in terminal run-quality reasons and SHALL prevent `complete`/`passed` status

#### Scenario: Hard failures do not become directional success
- **WHEN** a validator returns `pass=False`
- **THEN** the run SHALL be failed or incomplete according to whether execution can safely terminate, and no success-cache entry SHALL be created
