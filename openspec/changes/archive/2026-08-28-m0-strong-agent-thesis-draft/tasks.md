## 1. OpenSpec and input contract

- [x] 1.1 Review the child boundary against the current M0 handoff, M0.1 artifact contract, G2 umbrella, and existing dossier/AgentOutput contracts.
- [x] 1.2 Implement the explicit `m0-strong-agent-thesis-draft-input-v1` envelope and fail-closed identity/digest validation.

## 2. RED tests

- [x] 2.1 Add valid draft-input fixtures and tests for one strong call, complete AgentOutput preservation, and deterministic JSON/Markdown artifacts.
- [x] 2.2 Add tests for diagnostic warning/failure preservation, agent skip/out-of-circle downgrade, invalid identity/digest/dossier inputs, and zero side effects before validation.
- [x] 2.3 Add tests asserting the exact LLM call signature, one-call boundary, transport/schema failure semantics, output-directory confinement, and CLI provider-free behavior.

## 3. Minimal implementation

- [x] 3.1 Implement the strong single-agent draft adapter using the existing dossier preflight, prompt builder, `AgentOutput`, and heavy LLM client.
- [x] 3.2 Implement deterministic Thesis draft envelope validation and JSON/Markdown renderers without changing the diagnostic artifact.
- [x] 3.3 Add the minimal `strong-agent-thesis-draft` CLI command with explicit input/output/model options.

## 4. Verification and closure

- [x] 4.1 Run focused RED→GREEN tests and related Council, dossier, diagnostic, and CLI regressions.
- [x] 4.2 Run compileall, strict OpenSpec validation, and `git diff --check`; document that no npm lint script exists if applicable.
- [x] 4.3 Perform one independent child-only review from fresh read-only context and process only in-scope findings.
- [x] 4.4 Archive, commit, merge, push, and clean only this child worktree after review and final verification.
