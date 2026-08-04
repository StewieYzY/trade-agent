## Context

`g2-strong-single-agent-fallback` was implemented in the f3c worktree, where two
uncommitted/local prerequisites happened to exist: `data/cache/manager.py` and the f3c
Council input preflight in `council/debate.py`. A clean checkout from `main` therefore
failed during test collection before fallback behavior could be evaluated.

This change makes the fallback foundation independently portable from latest `main`.
It deliberately imports only the prerequisite runtime behavior needed by fallback; it
does not merge the f3c experiment harness or its live artifacts.

## Goals / Non-Goals

**Goals:**

- Track the existing `CacheManager` source package while excluding cache JSON data.
- Integrate the validated Council dossier preflight into the clean mainline.
- Keep fallback input validation before artifact creation and any LLM call.
- Prove fallback import, invalid-input zero side effect, and valid single-call behavior
  from a clean checkout.

**Non-Goals:**

- Do not merge the complete f3c branch or any f3c experiment code.
- Do not change the four-round Council protocol or AgentOutput schema.
- Do not add live fallback capability evidence.
- Do not write cache JSON, debate, watchlist, or crosstalk run artifacts to Git.
- Do not claim G2/G3 capability pass.

## Decisions

### D1: Track source, not runtime cache

Add `value-screener/data/cache/__init__.py` and `manager.py` as source files. Keep
`value-screener/data/cache/` JSON outputs ignored. The missing import is a source
packaging defect, not a request to commit local data.

### D2: Transplant only the preflight prerequisite

Bring the f3c Council input preflight helpers and their focused tests into mainline,
without cherry-picking the f3c measurement harness, live experiment scripts, or
dynamic handoff files. Fallback continues to call the single preflight boundary before
creating its own run directory.

### D3: Preserve fallback isolation

The fallback module remains a separate path: one strong-agent call, deterministic
fact checking, deterministic synthesis, and run-scoped fallback artifacts only. No
Council cache, debate, or watchlist writes are introduced by this integration.

### D4: Verification order

Run the new cache/preflight/fallback focused tests first, then the full Python suite,
OpenSpec strict validation, and `git diff --check`. A clean checkout must be the
verification environment; local cache JSON is not a prerequisite.

## Risks / Trade-offs

- [Preflight is currently an internal Council helper] → Keep the integration scoped to
  the existing helper and add behavior tests; a public API rename is deferred.
- [Mainline may expose other ignored-source gaps] → Treat each new import failure as a
  separate evidence-backed integration issue rather than copying the whole worktree.
- [Fallback remains single-agent] → Mark this as foundation only; G2 A/B and human
  review remain separate capability Gates.

## Migration Plan

1. Add RED tests in the clean G2 worktree.
2. Add tracked cache source and transplant the minimal preflight implementation/tests.
3. Run focused and full tests plus strict validation.
4. Commit this child separately from f3c live artifacts.
5. Use the resulting branch as the clean G2 integration checkpoint.

## Open Questions

- Whether the preflight helper should later become a public `council.input` module is
  deferred until the G2 integration checkpoint is independently reviewed.
