## Why

Repair `R-G1-002` closes a completeness gap in the archived
`g1-field-qualification-canonical-promotion` implementation: promotion currently
accepts a completed manifest and evidence count without proving that the frozen
source plan, run/ticker/field identities, artifact hashes, and required policy
matrix are intact. This can turn truncated, tampered, or partial source evidence
into a qualified decision.

## What Changes

- Require a valid frozen `plan.json` for every completed source qualification run.
- Recompute and compare plan, evidence, and manifest artifact hashes.
- Validate run, ticker, method, field, and evidence identities against the plan and
  manifest before evaluation.
- Reject any missing policy-required field group; partial field presence cannot
  qualify a group.
- Bind the promotion CLI to the explicit provider qualification probe-plan version.
- Preserve source artifacts byte-for-byte and record deterministic rejected
  decisions; do not change provider eligibility, canonical snapshot policy, or
  downstream ranking.

## Capabilities

### New Capabilities

- `g1-r-g1-002-source-plan-matrix-completeness`: Fail-closed validation of source
  plan, hashes, identities, and required field-group completeness before field
  qualification promotion.

### Modified Capabilities

None.

## Impact

- `value-screener/data/lib/field_qualification.py`
- `value-screener/scripts/provider_qualification.py`
- `value-screener/scripts/promote_provider_snapshot.py`
- Focused field qualification and provider qualification tests.
- No new dependencies and no production runtime artifacts.
