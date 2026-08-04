## ADDED Requirements

### Requirement: Clean mainline contains cache runtime source

The mainline checkout SHALL contain the `data.cache` Python package required by Council
and fallback imports, while runtime cache JSON remains local-only.

#### Scenario: Cache manager imports from a clean checkout

- **WHEN** tests run in a clean checkout with no `data/cache/{ticker}/*.json`
- **THEN** `from data.cache.manager import CacheManager` SHALL succeed

#### Scenario: Cache data is not part of the integration commit

- **WHEN** the integration change is staged
- **THEN** cache JSON outputs SHALL remain excluded from Git

### Requirement: Fallback uses the mainline dossier preflight

The fallback path SHALL reuse the Council dossier preflight before creating a fallback
artifact or calling an LLM.

#### Scenario: Invalid input has zero side effects

- **WHEN** fallback receives empty, guarded, insufficient, or ticker-mismatched input
- **THEN** it SHALL fail closed without an LLM call or fallback artifact

#### Scenario: Valid input remains bounded

- **WHEN** a valid dossier enters fallback
- **THEN** it SHALL call one strong agent at most once and keep output isolated from
  Council cache, debate, and watchlist paths

### Requirement: Integration preserves quality-state semantics

The clean integration SHALL preserve deterministic fallback quality states and SHALL
not convert foundation verification into a G2 capability pass.

#### Scenario: Failed quality gate is safe

- **WHEN** schema, transport, grounding, or circular-reference checks fail
- **THEN** synthesis SHALL be `signal=skip`, `conviction=0`, and `quality_status=blocked`

#### Scenario: Foundation is not a capability pass

- **WHEN** focused/full tests and strict validation pass
- **THEN** handoff SHALL still record G2 A/B, cost evidence, and human blind review as
  pending
