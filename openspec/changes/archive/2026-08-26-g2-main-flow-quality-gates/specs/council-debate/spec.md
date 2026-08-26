## ADDED Requirements

### Requirement: Council SHALL execute the complete quality-gated main flow
`run_debate` SHALL execute the configured Council stages in their existing order and SHALL invoke the corresponding quality checks after successful stage outputs: R1 grounding/circular-reference checks, R2 new-evidence checks, DA fact-check checks when DA runs, and R4 divergence-report checks when a Synthesizer output exists. The orchestrator SHALL preserve existing low/extreme divergence, evidence-exhausted, runtime-degraded, single-agent, and interruption branches.

#### Scenario: Normal Council executes all quality checks
- **WHEN** a multi-agent Council completes R1, R2, DA, and Synthesizer
- **THEN** the orchestrator SHALL call the R1, R2, DA, and R4 quality checks with the stage outputs and dossier context before publishing the final result

#### Scenario: R1 hard contamination blocks the flow
- **WHEN** an R1 output contains a circular reference to another agent
- **THEN** the orchestrator SHALL persist failed quality status, SHALL NOT call later stages, and SHALL NOT publish a clean success artifact

#### Scenario: R1 grounding warning remains visible
- **WHEN** an R1 output contains a number not grounded in the dossier but has no circular reference
- **THEN** the orchestrator SHALL continue the configured flow while preserving an explicit warning in the terminal quality reasons and SHALL NOT mark the run complete/passed

#### Scenario: R2 evidence warning propagates
- **WHEN** an R2 output has neither new evidence nor `evidence_exhausted=true`, or contains suspected fabricated evidence
- **THEN** the orchestrator SHALL preserve the R2 warning and SHALL NOT treat the final run as clean success

#### Scenario: DA skip has explicit semantics
- **WHEN** DA is skipped because of low/extreme divergence, evidence exhaustion, or runtime degradation
- **THEN** `CouncilResult` and the terminal quality record SHALL retain the declared skip/degradation reason, and the result SHALL NOT be success-cache eligible

#### Scenario: R4 invalid divergence report blocks clean publication
- **WHEN** a Synthesizer output lacks `divergence_level`, lacks `key_disagreements` for high/extreme divergence, or has a non-uncalibrated calibration status
- **THEN** the orchestrator SHALL persist failed quality status and SHALL NOT publish the result as complete/passed

#### Scenario: External call shape is preserved
- **WHEN** the main flow invokes R1, R2, DA, and Synthesizer callables
- **THEN** each mock SHALL receive the expected ticker, dossier/features, visible prior-round outputs, reasoning level, and stage/model keyword arguments without unsupported or malformed parameters
