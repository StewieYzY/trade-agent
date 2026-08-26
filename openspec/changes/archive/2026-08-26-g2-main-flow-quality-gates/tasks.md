## 1. OpenSpec and contract tests

- [x] 1.1 Finalize proposal/design and modified capability delta specs for G2 4.1 only
- [x] 1.2 Add RED tests for normal R1→R2→DA→R4 quality-check invocation and mock call signatures
- [x] 1.3 Add RED tests for warning, skip, degraded, failed, interruption, and polluted-result cache-blocking behavior

## 2. Main-flow implementation

- [x] 2.1 Add a small internal quality-result aggregation path in `debate.py` without changing external LLM/provider interfaces
- [x] 2.2 Consume R1 grounding, R2 evidence, DA fact-check, and R4 divergence validators at their normal stage boundaries
- [x] 2.3 Propagate gate warnings/failures/skips/degradation to CouncilResult, quality record, and output metadata
- [x] 2.4 Ensure hard quality failures terminate before later stages and non-clean artifacts cannot be success-cache eligible

## 3. Verification and closure

- [x] 3.1 Run focused tests and confirm RED→GREEN evidence, then run the full test suite
- [x] 3.2 Run compileall, `openspec validate --all --strict`, and `git diff --check`
- [x] 3.3 Perform an independent child-only review of current diff, tests, scope, and residual risks
- [x] 3.4 Archive the completed change, commit the child, merge into main, push origin, and clean the child worktree/branch
