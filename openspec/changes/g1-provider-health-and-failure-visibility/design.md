## Context

The qualification runner currently invokes provider adapters synchronously inside one
process and writes its manifest only after every probe case returns. AkShare calls can
wait indefinitely, so an interrupted or hung run leaves no auditable distinction between
completed evidence, timed-out work, and cases that were never started.

The change is limited to the read-only qualification boundary. Existing provider
field statuses, provenance contracts, canonical promotion policy, legacy cache, ranking,
and candidate-provider eligibility remain unchanged.

## Goals / Non-Goals

**Goals:**

- Bound each live qualification case with an explicit timeout.
- Ensure a stuck case can be terminated without blocking later cases.
- Persist progress and failure metadata before the whole run completes.
- Preserve partial evidence and distinguish completed, timed-out, interrupted, and
  not-started cases.
- Keep fixture/unit-test execution deterministic without requiring subprocess pickling
  for local closures.

**Non-Goals:**

- No automatic retry or backoff policy.
- No provider-specific SDK changes or new dependency.
- No promotion of fields to `production_eligible`.
- No writes to legacy cache, ranking, canonical snapshots, watchlists, or debates.
- No LongPort/Longbridge production integration.

## Decisions

### D1. Use a subprocess boundary for live execution

The CLI/live path SHALL execute one probe case in a child process and terminate the
child when its deadline expires. A thread timeout is rejected because Python cannot
reliably stop a blocked provider call after the parent marks it timed out. A signal-only
timeout is rejected because it is process-global and does not provide the same isolation
for provider code.

The existing direct in-process path remains available for deterministic unit tests and
callers that explicitly set `execution_mode="direct"`. The CLI defaults to
`execution_mode="isolated"`.

### D2. Use a serial case scheduler with explicit per-case timeout

The runner SHALL schedule cases serially in plan order. Each case has one timeout
deadline; no hidden retries are attempted. Serial execution keeps provider call count,
ordering, and partial artifacts easy to audit while the health child is being validated.
Parallelism remains a later performance decision.

### D3. Persist append-only events and atomically update manifest

Each case emits one terminal event to `events.ndjson` containing run_id, case identity,
execution mode, status, elapsed seconds, and non-sensitive failure metadata. The runner
flushes each event before starting the next case. The manifest is atomically rewritten
after each event and includes `completed_cases`, `timed_out_cases`,
`interrupted_cases`, `not_started_cases`, and `stop_reason`.

The existing `evidence.json`, `raw.json`, `comparison.json`, and `method-results.json`
remain final aggregate artifacts when the process reaches normal completion. On timeout
or interruption, the partial event/manifest artifacts are authoritative and the runner
must not claim `completed`.

### D4. Keep timeout as failure metadata, not a new field status

Timed-out fields use existing `source_failed` semantics with
`failure_class="timeout"` and `terminated=true`. This avoids changing the canonical
status enum while preserving the distinction needed for provider health analysis.
Missing or never-started cases are represented in manifest/events and are not fabricated
as field evidence.

### D5. Child communication is bounded and JSON-safe

The child returns a bounded JSON payload through a multiprocessing pipe/queue. Raw
responses continue to use the existing bounded serialization and redaction rules.
Parent-side timeout/termination paths create only metadata events; they never copy
untrusted child exceptions into unsanitized manifest fields.

## Risks / Trade-offs

- [Risk] Process startup makes live probes slower → Mitigation: default serial mode is
  intentionally bounded; performance/parallelism remains a separate child.
- [Risk] A provider adapter may not be picklable → Mitigation: isolated mode loads
  adapters by module name in the child; direct mode remains for fixtures/tests.
- [Risk] Parent termination can leave a child descendant → Mitigation: terminate,
  join with a short grace period, then kill the child; record `terminated=true`.
- [Risk] A process can be interrupted during manifest rewrite → Mitigation: atomic
  temp-file replacement and append-only events as the recovery source.
- [Risk] Partial artifacts could be mistaken for success → Mitigation: explicit
  `completion_status` and `stop_reason`; no final aggregate artifacts on incomplete runs.

## Migration Plan

1. Add deterministic tests for direct mode, isolated timeout, partial events, and
   interrupted/not-started accounting.
2. Implement the execution envelope without changing existing qualification field
   normalization.
3. Run the existing full qualification/unit suite.
4. Run one bounded real baseline probe in the project venv and inspect its partial/final
   artifacts before any field-level promotion decision.
5. Rollback is limited to using the existing direct qualification runner; no production
   data path is changed.

## Open Questions

- A provider-specific timeout/backoff profile and parallel batch scheduler remain
  separate follow-up work after bounded execution is evidenced.
