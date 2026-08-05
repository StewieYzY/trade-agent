## Context

The frozen provider qualification runner writes a completed run as
`manifest.json` plus `evidence.json`. Each evidence item already carries provider,
method, canonical ticker, field, normalized value, status, time basis, retrieval
timestamp, response hash, and provenance. The existing canonical snapshot module
can preserve evidence and only consume `production_eligible` records, but its
eligibility input is intentionally supplied by a later policy.

This child supplies that missing policy boundary. It must be independent from the
provider health runner and must not infer qualification from a non-empty response,
a passing unit test, or a provider's documentation. It also must not mutate the
qualification run or any legacy production path.

## Goals / Non-Goals

**Goals:**

- Load only completed, run-scoped qualification artifacts.
- Freeze a policy version and required probe coverage for the five canonical A-share
  tickers and the selected provider/method/field set.
- Evaluate each `(provider, method, field)` group across all requested tickers.
- Require explicit provenance, valid time basis, accepted status, finite normalized
  values, and consistent units/currency/time basis before promotion.
- Preserve every source evidence record and emit a decision record for both accepted
  and rejected fields.
- Write a separate immutable promotion run containing decision metadata and the
  existing canonical snapshot artifacts.

**Non-Goals:**

- No provider calls, retries, concurrency, scheduler, adapter discovery, or sandbox.
- No new provider eligibility for LongPort/Longbridge based on documentation.
- No ranking, cache, watchlist, debate, G2/G3 runtime, or capability gate change.
- No automatic selection among conflicting providers; conflicts fail closed.
- No field-specific business thresholds beyond the explicit policy input.

## Decisions

### D1. Policy is explicit and versioned

`FieldQualificationPolicy` is a frozen data object containing the plan version,
required tickers, required method/field matrix, allowed providers, minimum ticker
coverage, and freshness window. The evaluator accepts the policy as an argument and
records a stable policy hash. This is preferred over hidden module constants because
the decision must be reproducible and auditable.

### D2. Qualification is group-based and fail-closed

The smallest promotable unit is `(provider_family, provider, method, field)`.
All required tickers must have one valid `available` evidence item for that group.
Any missing ticker, duplicate item, failed status, invalid provenance, invalid time
basis, stale/unknown freshness, or inconsistent unit/currency/time basis rejects the
whole group. This is preferred over per-ticker promotion because a canonical field
would otherwise have mixed coverage and an unrecorded selection rule.

### D3. The evaluator never edits source evidence

The evaluator returns deep-copied evidence with `eligibility=production_eligible`
only for accepted groups. Rejected evidence remains `not_qualified`, retains its
original status/reason, and is included in the decision sidecar. This avoids
overwriting the source qualification result and allows later review to reconstruct
the decision.

### D4. Promotion has a separate run identity

The promotion output root contains `<promotion_run_id>/decision.json` and the
canonical snapshot files. The source qualification run path and evidence hash are
recorded in the promotion manifest. Duplicate IDs, missing source artifacts, and
output paths inside protected production roots fail before writing.

### D5. Existing canonical snapshot remains the only value writer

The promotion entrypoint delegates canonical value construction and immutable
artifact writing to `data.lib.canonical_snapshot`. The new module only decides
eligibility and prepares evidence. This keeps provider policy separate from
snapshot serialization and avoids duplicate conflict/freshness behavior.

## Risks / Trade-offs

- [Incomplete real evidence] → The policy can produce zero promoted fields; this is
  valid and remains an explicit blocked result rather than a fallback.
- [Provider schema drift] → Missing/duplicate/malformed evidence is rejected at the
  group level and retained in `decision.json`.
- [Stale timestamps] → The policy records a single evaluation reference and rejects
  stale or unknown freshness; no per-record “best effort” selection is allowed.
- [Large evidence files] → The evaluator streams no external data and keeps the
  existing run-scoped JSON contract; raw response payloads are not duplicated.
- [False sense of readiness] → The decision document and manifest explicitly state
  that promotion is a field-policy artifact, not a G1 capability pass.

## Migration Plan

1. Create the active OpenSpec child and implement deterministic policy tests.
2. Run promotion only against fixture or previously recorded qualification evidence.
3. Inspect `decision.json`, canonical sidecar, and source run immutability.
4. Keep the output outside protected production roots and do not migrate consumers.
5. Future live evidence can be evaluated by the same entrypoint after explicit user
   authorization, without changing the policy contract.

Rollback is deleting the separate promotion run directory; source qualification and
legacy production artifacts are untouched.

## Open Questions

- The minimum cross-ticker coverage policy is intentionally strict for this child:
  all five frozen tickers are required. A future full-market qualification child may
  define a different policy version rather than weakening this one.
- Whether a field is useful to ranking remains a downstream consumer decision and is
  not inferred here.
