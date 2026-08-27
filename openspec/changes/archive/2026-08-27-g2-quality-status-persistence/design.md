## Context

G2 4.1 introduced quality gates and terminal fields on `CouncilResult`, but the persistence boundary is still distributed across debate markdown, watchlist JSON, fallback manifests, and quality records. The existing `g2-run-quality-status` contract already defines the closed vocabulary and run-scoped path shape; this child closes the runtime read/write behavior around that contract.

The implementation must remain within the current Python 3.10+ codebase, use the existing JSON filesystem layout, preserve root WIP, and avoid changing the 4.1 gate decisions. A quality record is diagnostic evidence first; only a complete, passed, mode- and artifact-bound record can qualify a cache hit.

The 4.1 baseline already contains the Council/fallback/L4 status fields and most
terminal propagation. This child changes the shared persistence contract and
the specific consumer proof checks; existing 4.1 behavior is reused where it
already satisfies the contract and is covered by regression tests.

## Goals / Non-Goals

**Goals:**

- Make quality records the authoritative terminal status for a run, while retaining reasons and completed stages.
- Preserve status across Council/fallback/watchlist/L4 reads with canonical ticker and `run_id` isolation.
- Fail closed on missing, malformed, or misbound quality proof.
- Ensure interrupted runs are persisted as `incomplete` and non-clean runs cannot enter success cache.
- Add RED-first regression coverage for persistence, recovery, corruption, and cache qualification.

**Non-Goals:**

- No rewrite of G2 4.1 gate logic or introduction of G2 4.3 pollution proof.
- No changes to growth expectation, G1, prompts, provider/LLM behavior, G3, or capability acceptance.
- No database or new dependency; no migration of legacy artifacts beyond diagnostic reads.

## Decisions

1. **Quality record is authoritative for terminal quality.** Consumer fields are copied from a validated record when the path and identity match; artifact-local fields cannot upgrade a non-clean or unproven run.

2. **Run identity is the storage boundary.** Records remain at `quality_status/{canonical_ticker}/{run_id}/record.json`; debate and watchlist artifacts must resolve under the same ticker/run directory. Writes are exclusive for first creation and monotonic for terminal downgrade/update.

3. **Read failures are fail-closed but diagnostic reads remain possible.** A missing record yields no cache hit; malformed JSON, invalid schema, or identity mismatch raises/marks proof invalid rather than falling back to an older successful run. L4 may expose the artifact as incomplete.

4. **Status reasons and stages are append-preserved.** Replacements retain prior reasons and use the latest non-upgradable terminal status plus the union of completed stages. A record cannot move from a less-safe status back to `complete`.

5. **Cache qualification is conjunctive.** It requires `complete`, `final_quality_gate=passed`, required stages, expected execution mode, current-date artifact, and a path binding to the same canonical ticker/run. Directional output alone is insufficient.

## Risks / Trade-offs

- [Risk] Legacy flat artifacts lack quality proof → keep them readable for diagnosis but mark them incomplete and never use them as clean cache.
- [Risk] A crash can occur between artifact and record writes → persist an incomplete record at stage boundaries and make missing/invalid proof a cache miss.
- [Risk] Strict record validation may expose old malformed files → this is intentional fail-closed behavior; callers must surface diagnostic status rather than silently recover an older cache.
- [Trade-off] Filesystem JSON remains simple and dependency-free but does not provide cross-process transactions → exclusive creation, atomic replacement, and run-scoped paths limit overwrite and mix-up risk.
