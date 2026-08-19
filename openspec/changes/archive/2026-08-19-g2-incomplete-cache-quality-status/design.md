## Context

G2 umbrella milestone 1.2 follows the archived `g2-identity-audit-chain` child.
The identity contract already isolates canonical ticker and `run_id`, but it
does not decide whether a runtime result is complete or eligible for reuse.
Today Council's date-scoped markdown cache accepts an R1-only parse as a hit;
fallback emits a local manifest with `passed`/`blocked`; and watchlist fields
can preserve DA/degraded flags without making them a cache barrier.

This child establishes the G2 1.2 runtime-quality boundary only. It consumes
the existing identity contract and does not redefine the future
`InvestmentThesis` interface.

## Goals / Non-Goals

**Goals:**

- Define one closed status vocabulary:
  `complete`、`warning`、`failed`、`incomplete`、`runtime_degraded`、
  `da_skipped`.
- Persist a read-only, run-scoped quality record with canonical ticker,
  `run_id`, status, reasons and the completed stages.
- Make `complete` plus a passed final quality gate the sole success-cache
  eligibility condition.
- Record R2, DA, Synthesizer and final-validation interruptions as
  `incomplete`; preserve warnings, DA skips, runtime degradation and failures
  as independently readable diagnostic records.
- Ensure Council cache, fallback artifacts and watchlist outputs carry or
  resolve the same record without overwriting another run of the same ticker.

**Non-Goals:**

- No G2 1.3 crosstalk-root-cause work, dossier data-quality, growth
  expectation, prompt/A-B harness, G3 runtime, or G2 capability verdict.
- No new provider/LLM call, data migration, or broad refactor of legacy G1/L2
  cache semantics.
- No change to the identity audit-chain schema or its transaction semantics.

## Decisions

### D1. Use an explicit run-quality record instead of inferring state from markdown

Introduce a small `data.lib` contract that validates and persists one JSON
record per `{canonical_ticker, run_id}`. It is authoritative for reuse and
consumer visibility; markdown remains append-only diagnostic evidence.

The record contains schema version, canonical ticker, run_id, status,
reasons, completed stages, final-quality-gate result, and references to
existing debate/fallback/watchlist artifacts when present. Record creation
uses exclusive writes and run-scoped paths.

Alternative considered: derive status by parsing `debate/*.md` on every read.
This is rejected because partial markdown is intentionally durable for
recovery but is not a reliable declaration of successful completion.

### D2. Status is closed and precedence is fail-safe

Writers must reject unknown statuses. A run is `complete` only when R1/R2/DA/
Synthesizer/final validation required by its execution mode have completed,
the final validation passes, and no warning/degraded/DA-skip condition
remains. `incomplete` represents interruption before a required stage;
`failed` represents a completed validation or execution failure;
`runtime_degraded` represents error-rate degradation; `da_skipped` represents
a deliberate skipped DA; `warning` represents a non-blocking quality warning.

When multiple observations exist, the persisted state must retain all reasons
but select the least-safe status: `failed`/`incomplete` first,
`runtime_degraded`, `da_skipped`, `warning`, then `complete`. A reader never
upgrades a non-complete record based on a parseable debate artifact.

### D3. Success cache is separate from diagnostic persistence

Only a `complete` record with `final_quality_gate="passed"` can produce or
serve a Council success cache hit. All other records remain readable from a
run-scoped diagnostic location and may be referenced by watchlist/fallback,
but cache lookup treats them as misses.

Alternative considered: cache warning results with an extra boolean. This is
rejected because legacy callers can omit or ignore the boolean, recreating
clean-success ambiguity.

### D4. Integrate at stage boundaries, not inside prompt or dossier code

Council records `r1`, `r2`, `da`, `synthesizer`, and `final_validation`
progress at orchestration boundaries. Exceptions after a run begins persist
an `incomplete` record before re-raising. Final validation derives the
terminal status and controls both Council cache promotion and watchlist
publication labeling.

Fallback uses the same contract for its deterministic fact-check and result
manifest. It never enters the Council success cache; its status record remains
diagnostic and run-scoped.

### D5. Keep run isolation strict and legacy reads conservative

New records use canonical ticker and run ID. Legacy ticker/date markdown has
no G2 quality record and therefore cannot be promoted to a G2 clean cache hit;
it remains readable only where legacy compatibility explicitly requires it.
Different `run_id` values for one ticker must use different record paths and
must not overwrite a prior diagnostic or success record.

## Risks / Trade-offs

- [Risk] Existing tests rely on R1-only markdown cache hits → Mitigation:
  update tests to create a qualifying record for clean-cache tests and add
  negative coverage for all partial/degraded cases.
- [Risk] A legitimate single-agent execution has no R2/DA/R4 → Mitigation:
  final validation receives an explicit execution mode and only treats stages
  required for that mode as completion requirements; it still cannot be
  labeled `complete` if its quality gate is not passed.
- [Risk] Exception handlers might mask the original error → Mitigation:
  persist only best-effort diagnostic state, preserve the original exception,
  and never convert it to a success response.
- [Risk] Watchlist consumers may ignore new fields → Mitigation: include the
  status record reference and terminal status in every newly written output;
  do not use the presence of watchlist JSON as cache qualification.

## Migration Plan

1. Add RED tests for the record validator, persistence, state precedence,
   cache eligibility and same-ticker/different-run isolation.
2. Implement the isolated quality-status module and make its own tests GREEN.
3. Integrate Council interruption handling, cache lookup/promotion and
   watchlist labeling; then integrate fallback diagnostic records.
4. Re-run focused and full regressions. Existing legacy artifacts are neither
   modified nor promoted; rollback is removal of the new record usage while
   retaining generated run-scoped diagnostics outside tracked source.

## Open Questions

- None for this child. Whether a future stable `InvestmentThesis` surface maps
  these statuses into a broader product schema belongs to the output-interface
  child, not G2 1.2.
