## Why

G2 4.1 now computes terminal quality outcomes, but persistence and recovery are not yet a complete contract: warning, skip, degraded, failed, and incomplete evidence must survive process boundaries and remain isolated by ticker and `run_id`. Without that closure, cache and downstream readers can mistake a directional artifact for a clean success.

## What Changes

- Persist every started G2 runtime outcome with canonical ticker, `run_id`, terminal status, reasons, completed stages, final gate, execution mode, and artifact reference.
- Make quality records readable independently of cache eligibility and fail closed on missing, malformed, or identity-mismatched records.
- Restore quality status and reasons into Council, fallback, watchlist, and L4 reads; never infer clean success from artifact existence or directional verdicts.
- Require cache eligibility to be proven by a matching current-date, mode-bound, run-scoped quality record and artifact.
- Add behavior tests for all closed statuses, interruption, isolation, recovery, corruption, and cache qualification.

## Capabilities

### New Capabilities

- `g2-quality-status-persistence`: Run-scoped persistence and consumer recovery for G2 quality outcomes.

### Modified Capabilities

- None.

## Impact

- Affects `value-screener/data/lib/quality_status.py`, `council/debate.py`, `council/fallback.py`, `monitor/aggregation.py`, and focused G2 tests.
- No new dependencies, provider calls, prompt changes, or changes to G2 4.1 gate rules.
- Existing legacy artifacts remain diagnostic-only unless they carry verifiable quality proof.
