## 1. Contract and RED tests

- [x] 1.1 Finalize the G2 4.2 proposal, design, capability spec, and scoped task list.
- [x] 1.2 Add RED tests for all closed statuses, reasons, completed stages, run isolation, exclusive writes, and monotonic replacement.
- [x] 1.3 Add RED tests for Council/fallback/watchlist/L4 recovery, missing/corrupt/misbound records, interruption, and success-cache qualification.

## 2. Minimal persistence and consumer implementation

- [x] 2.1 Complete strict quality-record validation/read behavior and preserve reasons/stages across updates without changing 4.1 gate decisions.
- [x] 2.2 Make Council cache and output recovery use authoritative run-scoped quality records and fail closed on invalid latest proof.
- [x] 2.3 Make fallback and L4 consumers expose persisted quality status/reasons/reference and mark non-clean or legacy evidence incomplete.
- [x] 2.4 Verify clean-cache qualification is conjunctive on status, gate, required stages, mode, ticker/run identity, and current-date artifact.

## 3. Verification and closure

- [x] 3.1 Run focused RED→GREEN tests, then the full test suite.
- [x] 3.2 Run compileall, OpenSpec strict validation, and `git diff --check`.
- [x] 3.3 Perform one independent child-only review of the current diff, tests, scope, and residual risks.
- [x] 3.4 Archive the completed change, commit the child, merge into main, push origin, and clean the child worktree/branch without touching root WIP.
