## Why

Provider qualification currently produces auditable field evidence, and the canonical
snapshot boundary can preserve eligible versus non-eligible values, but no independent
policy turns a completed qualification run into a field-level decision. Without that
step, downstream code cannot distinguish “returned by a provider” from “qualified
for a canonical snapshot” in a reproducible way.

This child is needed now because the provider health runner is frozen and the next
handoff step is to consume its run-scoped evidence without expanding the runner or
silently promoting incomplete A-share data.

## What Changes

- Add a versioned, explicit field qualification policy for the frozen A-share probe
  plan, including allowed statuses, provenance/time-basis requirements, freshness,
  ticker coverage, and cross-provider consistency.
- Add a pure evaluator that reads completed qualification evidence and emits an
  immutable field-level decision sidecar with explicit rejection reasons.
- Add a run-scoped promotion entrypoint that marks only policy-approved evidence as
  `production_eligible` and writes an immutable canonical snapshot.
- Preserve original qualification artifacts and all rejected/failed evidence; never
  use implicit fallback, default values, ranking, cache, watchlist, debate, or G2/G3
  consumers.
- Add deterministic fixture tests and a dated decision record. No real provider call,
  new dependency, LongPort/Longbridge integration, retry, scheduler, or capability
  gate change is included.

## Capabilities

### New Capabilities

- `g1-field-qualification-canonical-promotion`: Evaluate run-scoped A-share
  qualification evidence under an explicit field policy and produce an auditable,
  fail-closed canonical snapshot promotion artifact.

### Modified Capabilities

None.

## Impact

- New `value-screener/data/lib/field_qualification.py` policy/evaluator module.
- New `value-screener/scripts/promote_provider_snapshot.py` run-scoped promotion
  entrypoint.
- New deterministic tests under `value-screener/tests/`.
- Reuses the existing provenance contract and canonical snapshot writer; does not
  change their consumer surface or add dependencies.
