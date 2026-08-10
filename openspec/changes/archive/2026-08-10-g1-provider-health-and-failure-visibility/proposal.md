## Why

The corrected provider qualification runner can still wait indefinitely inside an AkShare
fetcher call. A hanging request leaves no complete run artifact, so the project cannot
distinguish completed evidence, timed-out work, and work that was never evaluated. This
blocks the next real A-share qualification run and makes provider health failures
non-auditable.

## What Changes

- Add a bounded execution envelope for live qualification cases with an explicit timeout.
- Isolate each live probe case so a stuck provider call can be terminated without
  fabricating field evidence or blocking the rest of the run.
- Persist append-only progress/failure events and a partial manifest when a run finishes,
  times out, or is interrupted.
- Preserve existing field statuses and add non-sensitive failure metadata such as
  `failure_class`, `terminated`, `elapsed_seconds`, and `stop_reason`.
- Add a shared resolved-path validator for G1 production roots. Health,
  qualification/promotion, batch, and canonical entrypoints must reject protected roots,
  descendants, ancestors, and symlink escapes before provider/evaluation/artifact work.
- Keep retry policy, provider eligibility, canonical promotion, ranking, cache, and
  LongPort/Longbridge production integration out of scope.

## Capabilities

### New Capabilities

- `provider-health-and-failure-visibility`: bounded live qualification execution,
  termination semantics, partial evidence artifacts, and provider health visibility.

### Modified Capabilities

<!-- No existing root capability requirements are modified; this child adds an
     execution/observability boundary around the archived qualification runner. -->

## Impact

- Affects `value-screener/scripts/provider_qualification.py`,
  `value-screener/scripts/promote_provider_snapshot.py`,
  `value-screener/data/lib/provider_batch_adapter.py`,
  `value-screener/data/lib/canonical_snapshot.py`, and their boundary tests.
- Adds run-scoped event/partial-manifest artifacts under the caller-provided qualification
  output root.
- Uses only Python standard-library process, timing, and JSON facilities; no new dependency.
- Enables a future real baseline probe to terminate predictably, but does not itself
  qualify any provider or write canonical production snapshots.
