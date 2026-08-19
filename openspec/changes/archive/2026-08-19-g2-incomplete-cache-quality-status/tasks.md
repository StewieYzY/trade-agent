## 1. Contract and RED coverage

- [x] 1.1 Add RED tests for the closed six-state vocabulary, invalid complete claims, terminal precedence, and run-scoped exclusive persistence.
- [x] 1.2 Add RED tests that incomplete R2, DA, Synthesizer, and final-validation paths cannot be read as Council success-cache hits.
- [x] 1.3 Add RED integration tests for warning, DA skipped, runtime degraded, fallback, watchlist labeling, and same-ticker/different-run isolation.

## 2. Quality-status persistence

- [x] 2.1 Implement the minimal G2 run-quality record validator, writer, reader, and success-cache eligibility predicate using canonical ticker and run ID.
- [x] 2.2 Make record persistence fail closed for unknown state, invalid complete claims, unsafe path components, and conflicting writes.
- [x] 2.3 Keep non-complete records independently readable as diagnostic evidence without promoting them to success cache.

## 3. Council and fallback integration

- [x] 3.1 Integrate Council stage-boundary progress and interruption records for R2, DA, Synthesizer, and final validation.
- [x] 3.2 Require a qualifying complete quality record for Council cache lookup and promotion; preserve legacy artifacts without treating them as clean hits.
- [x] 3.3 Add run-quality fields and record references to Council watchlist output.
- [x] 3.4 Integrate fallback runtime manifest/result with the shared diagnostic status contract while keeping fallback outside Council success cache.

## 4. Verification and closure boundary

- [x] 4.1 Make RED tests GREEN and run focused quality-status, Council, fallback, and watchlist regressions.
- [x] 4.2 Run `value-screener/.venv/bin/python -m pytest value-screener/tests -q`, `value-screener/.venv/bin/python -m compileall -q value-screener`, `openspec validate --all --strict`, and `git diff --check`.
- [x] 4.3 Perform an independent child-only review, archive only after review evidence is clean, and retain `G2 capability = not passed`.

## 5. Fresh CR remediation

- [x] 5.1 Add RED coverage for execution-mode cache isolation, record payload/path identity binding, and run-scoped L3-to-L4 quality propagation.
- [x] 5.2 Make Council publication and cancellation fail closed: persist an incomplete record before re-raising and never leave a clean output or cache claim after final publication fails.
- [x] 5.3 Preserve all terminal observations while deriving status from actual degradation thresholds, and make fallback setup/audit failures persist a readable terminal record and manifest.
- [x] 5.4 Re-run focused and full regressions, strict OpenSpec validation, diff checks, then perform a fresh independent review before archive.
- [x] 5.5 Add RED coverage for R1 cancellation objects returned by `gather(return_exceptions=True)`, fallback cancellation, and fallback audit publication failure.
- [x] 5.6 Make every started Council/fallback run terminally diagnosable, mark legacy L4 artifacts without quality proof incomplete, and keep all published path specifications run-scoped.
- [x] 5.7 Add cross-date cache isolation, audit dossier failure, fallback final quality persistence, L4 proof binding, manifest reasons, and CLI artifact-path coverage.
- [x] 5.8 Make cache, Council audit startup, fallback terminal publication, L4 proof validation, and CLI artifact references fail closed.
