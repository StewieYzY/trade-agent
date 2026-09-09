## Why

M0.2 can produce one strong-agent Thesis draft, but it does not yet provide a
repeatable, auditable baseline for deciding whether the single-agent path is
stable enough to serve as the G2 comparison reference. M2.1 addresses umbrella
`g2-deep-investment-thesis` task 6.1 by freezing the relevant input and model
identity, recording each run, and making repeated runs comparable without
claiming that the G2 Capability Gate has passed.

## What Changes

- Add the `g2-strong-agent-baseline` child capability for M2.1.
- Define a versioned baseline input envelope that binds canonical ticker,
  `run_id`, M0.1 diagnostic digest, dossier/input digest, prompt/profile
  versions, model, reasoning level, budget, and input artifact identity.
- Record each M0.2 strong-agent attempt with deterministic identity, usage,
  quality, failure/skip/degraded state, and output digest.
- Compare repeated runs of the same bound input with explicit stable fields,
  permitted model-output drift, structural failures, quality changes, output
  digest changes, and token/cost changes.
- Render deterministic JSON and Markdown review artifacts in an explicit
  run-scoped output directory.
- Reuse M0.2 validation, strong-agent call, `AgentOutput`, dossier quality, and
  failure semantics; do not create a second LLM/dossier/diagnostic validator.
- Repair the existing M0.2 grounding reuse boundary so an explicitly labeled
  percentage can match a decimal-stored ratio field without allowing unlabeled
  or unrelated numbers to bypass fabricated-number rejection.
- Keep tests provider-free by using a fake seam and asserting the exact call
  signature and parameter shape.

## Capabilities

### New Capabilities

- `g2-strong-agent-baseline`: M2.1 fixed-input strong-agent baseline records,
  repeated-run comparison, and deterministic review artifacts.

### Modified Capabilities

- None. This child adds an experimental baseline contract and does not change
  the requirements of the stable `investment-thesis` capability.

## Impact

- Adds focused baseline contract, execution, comparison, and rendering code
  under `value-screener/council/`.
- Adds `value-screener/tests/test_g2_strong_agent_baseline.py` and, if needed,
  a minimal public CLI entrypoint under `value-screener/cli.py`.
- Adds only this child OpenSpec change and its capability spec.
- No new dependencies, provider calls during tests, Council A/B, Council
  orchestration, DA/R2/R4/Synthesizer, G3 runtime, frontend, database, or
  trading behavior.
