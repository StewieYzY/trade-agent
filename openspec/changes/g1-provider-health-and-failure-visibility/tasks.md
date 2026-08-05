## 1. Contract and test harness

- [x] 1.1 Add deterministic test helpers for slow, successful, failing, and interruptible probe adapters without introducing dependencies.
- [x] 1.2 Add RED tests for isolated execution completion, timeout termination, and continuation/stop policy.
- [x] 1.3 Add RED tests for append-only terminal events, partial manifest state, and not-started case accounting.
- [x] 1.4 Add RED tests for redacted timeout/provider failure metadata and production-path isolation.

## 2. Bounded execution

- [x] 2.1 Define explicit execution options for timeout, execution mode, and stop policy with stable validation errors.
- [x] 2.2 Implement child-process case execution that returns bounded JSON-safe results and does not require fixture closures to be picklable in direct mode.
- [x] 2.3 Implement parent-side timeout termination, short join grace period, forced kill fallback, and `failure_class=timeout` metadata.
- [x] 2.4 Preserve existing qualification normalization and status semantics for successful, provider-failed, rate-limited, and unavailable cases.

## 3. Partial artifact persistence

- [x] 3.1 Implement append-only `events.ndjson` terminal events with run/case identity, elapsed time, execution mode, status, and safe failure metadata.
- [x] 3.2 Atomically persist a partial manifest after every terminal case with completed/timed-out/interrupted/not-started counts.
- [x] 3.3 Mark normal runs completed only after all cases finish and write the existing aggregate artifacts.
- [x] 3.4 Mark timeout/interruption runs incomplete and ensure partial artifacts never claim qualification or capability completion.

## 4. CLI and compatibility

- [x] 4.1 Add CLI flags for execution mode, per-case timeout, and stop policy with bounded defaults and explicit help text.
- [x] 4.2 Keep direct mode compatible with existing unit tests and existing adapter-module loading.
- [x] 4.3 Verify no writes occur under `data/cache`, `watchlist`, `debate`, canonical production snapshot roots, or ranking outputs.

## 5. Verification and runtime probe

- [x] 5.1 Run focused health/qualification tests and the existing qualification/provenance/canonical boundary suites.
- [x] 5.2 Run full pytest with the project venv, compileall, diff check, and strict OpenSpec validation.
- [x] 5.3 Execute one bounded real baseline probe using the approved project venv and inspect completed/partial artifacts.
- [x] 5.4 Record runtime result, timeout behavior, remaining field-level qualification status, and next handoff without claiming G1 pass.
