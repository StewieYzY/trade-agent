## Context

The G2 umbrella `g2-deep-investment-thesis` leaves task 6.1 open for a
strong-single-agent baseline. M0.2
`m0-strong-agent-thesis-draft` already owns the trusted diagnostic/dossier
binding, one-call heavy-model boundary, `AgentOutput` validation, and
failure/skip/degraded Thesis draft semantics. M2.1 must make repeated M0.2
attempts auditable and comparable without duplicating those validators or
turning fixture results into G2 Capability Gate evidence.

This child is the M2.1 engineering experiment named
`g2-strong-agent-baseline`. It follows AD-04, AD-05, AD-09, and AD-10:
reasoning level remains explicit, no orchestration framework is introduced,
the strong-agent path is established before Council A/B, and completion of
this child does not complete the umbrella Gate.

## Goals / Non-Goals

**Goals:**

- Bind every baseline attempt to the same canonical ticker, `run_id`, M0.1
  diagnostic, dossier/input digest, prompt/profile version, model, heavy
  reasoning level, budget, and input artifact identity.
- Reuse M0.2 as the only strong-agent execution and validation boundary.
- Persist one deterministic baseline record per attempt, including usage,
  quality, failure/skip/degraded reason, output digest, and attempt identity.
- Compare two or more records deterministically and distinguish must-stay-
  stable identity fields from permitted model/usage drift.
- Preserve structural, provider, schema, dossier, diagnostic, skip,
  out-of-circle, and degraded outcomes as visible comparable states.
- Keep all tests provider-free and assert the real M0.2 call signature through
  its fake seam.

**Non-Goals:**

- No Council A/B, additional agents, R2, DA, R4, Synthesizer, or debate changes.
- No M2.2 `view_signal` or `investment_eligibility` contract.
- No prompt/model tuning, growth diagnostic recalculation, position advice,
  G3 runtime, HoldingContract, frontend, database, queue, or trading.
- No new dependency and no real provider/LLM invocation in verification.
- No claim that mock artifacts, green tests, archive, or merge pass the G2
  Capability Gate.

## Decisions

### 1. Wrap M0.2 instead of adding a second agent runner

Add `council/strong_agent_baseline.py`. Its runner calls
`run_strong_agent_thesis_draft(...)` with the exact bound M0.2 input and
explicit model. It then validates and reads the M0.2 artifact to build the
baseline record. Tests patch the existing M0.2 `call_llm` seam, so the
production call path and exact `(system_prompt, user_message, "heavy",
model=...)` signature are exercised without a provider.

The rejected alternative is to copy prompt assembly, diagnostic/dossier
validation, `AgentOutput` parsing, or the HTTP client into the baseline module.
That would create two authorities for the same strong-agent behavior.

### 2. Use a versioned envelope with stable and attempt identity

The input schema is `g2-strong-agent-baseline-input-v1`. It contains:

- `canonical_ticker`, `run_id`, and positive `attempt_index`;
- `diagnostic_digest`, `dossier_digest`, and `input_digest`;
- fixed `prompt_version`, `profile_version`, `model`, and
  `reasoning_level=heavy`;
- `budget` with positive `max_total_tokens` and optional non-negative
  `max_cost`/currency;
- `input_artifact_identity` with artifact type, schema version, and digest;
- the complete `thesis_draft_input` consumed by M0.2.

The module recomputes all digests with canonical sorted-key JSON and invokes
`ThesisDraftInput.from_dict(...)` for the authoritative nested identity and
diagnostic/dossier checks. `baseline_input_digest` excludes `attempt_index`, so
repeated attempts share one input identity. `attempt_id` is derived from that
digest and the attempt index.

Malformed envelopes that cannot provide safe canonical file identity raise
without side effects. Once safe top-level identity is established, nested
identity/digest/dossier preflight failures are written as
`execution_status=failed` baseline records with structural failure codes and
zero provider calls.

### 3. Normalize records without hiding the M0.2 result

Record schema `g2-strong-agent-baseline-record-v1` preserves:

- all stable input identity fields and the effective budget;
- `attempt_index`, deterministic `attempt_id`, and provider call count;
- normalized usage keys for prompt/completion/total tokens, cost, and currency;
- M0.2 `quality_status`, `failure_kind`, diagnostic status, agent signal, and
  out-of-circle state;
- normalized `execution_status=completed|degraded|skipped|failed` and explicit
  status reasons;
- raw-response `output_digest` plus the M0.2 draft artifact digest;
- `engineering_status=experiment_recorded`,
  `capability_status=not_evidence`, and `gate_status=not_passed`.

Token or cost budget overruns are visible as degraded outcomes. Missing cost
data remains `unknown`; it is not fabricated as zero.

### 4. Make comparison a pure deterministic operation

`compare_strong_agent_baseline_records(...)` accepts record mappings, validates
them, sorts by `attempt_index`, and never invokes the provider. The comparison
schema explicitly reports:

- `stable_field_results` for fields that must match;
- `allowed_drift_fields` for output, usage, quality, and outcome fields;
- structural failures, including duplicate attempts and identity mismatch;
- quality transitions, output digest changes, and token/cost deltas;
- `comparison_status=stable|drifted|structural_failure`.

JSON and Markdown are rendered from the same comparison mapping using sorted
keys and no timestamp. Attempt artifacts live under
`<output_dir>/attempt-<NNN>/`; comparison artifacts live directly under the
explicit comparison output directory. No default project/runtime directory is
used.

### 5. Expose public Python entrypoints

The minimum runnable interface is the public async baseline runner and the
public deterministic comparison function. This satisfies the M2.1 runnable
entry requirement without expanding `cli.py`; a CLI can be added later only
if a real workflow demonstrates the need.

## Risks / Trade-offs

- [Risk] M0.2 artifact fields evolve and break record extraction. → Validate
  the returned M0.2 artifact and fail visibly instead of guessing defaults.
- [Risk] An invalid envelope could choose an unsafe output filename. → Require
  canonical ticker, safe `run_id`, and positive attempt index before any write.
- [Risk] Usage payloads differ by provider. → Preserve normalized known fields,
  represent missing token/cost values as `null`, and never infer missing cost.
- [Risk] Output digest changes on harmless prose variation. → Treat output
  digest as allowed drift and report it separately from structural identity.
- [Risk] A baseline record is mistaken for capability evidence. → Persist
  `capability_status=not_evidence` and `gate_status=not_passed` in every record
  and comparison Markdown.

## Migration Plan

This is additive. Add the child spec, focused tests, and one council module.
Existing M0.2 artifacts and CLI behavior remain unchanged. Rollback removes the
new module/tests/spec because no existing consumer or persisted schema is
modified.

## Open Questions

- A real model, frozen stock sample, repetition count, and user review protocol
  remain later experiment inputs; this child does not choose or execute them.
- M2.2 owns the stable investment eligibility semantics. This baseline records
  M0.2 output states without promoting them to that interface.
