# g1-mvp-small-sample-run Specification

## Purpose
TBD - created by archiving change g1-mvp-small-sample-run. Update Purpose after archive.
## Requirements
### Requirement: Explicit offline small-sample execution

The small-sample runner SHALL accept an explicit JSON fixture envelope containing 5–20 unique tickers, five-dimensional G1 screening data, run identity, and fixture provenance. It MUST execute through the existing staged screening boundaries without calling a provider, LLM, Scout, Council, or global cache.

#### Scenario: Fixture input runs through all applicable stages

- **WHEN** the input contains valid fixture data for multiple tickers
- **THEN** the runner SHALL execute Stage A, Stage B, and Stage C only for the tickers that reach each stage and SHALL preserve the existing stage dimension whitelist

#### Scenario: External side effects are absent

- **WHEN** the runner executes an in-memory fixture fetcher
- **THEN** it MUST complete without provider/LLM calls and MUST NOT write cache, watchlist, debate, or live evidence files

#### Scenario: Fixture size stays within M1 scope

- **WHEN** the input contains fewer than 5 or more than 20 unique canonical tickers
- **THEN** the runner SHALL reject the input before executing any screening stage

### Requirement: Identity and provenance are fail-closed

The runner SHALL require and validate canonical tickers, `run_id`, `profile_version`, `input_ticker_set_hash`, `as_of`, schema version, and fixture provenance. The computed canonical ticker-set hash MUST equal the caller-provided hash, and live/provider/production provenance MUST be rejected.

#### Scenario: Mismatched input hash is rejected

- **WHEN** the caller-provided hash does not match the canonical deduplicated ticker set
- **THEN** the runner SHALL fail before executing any screening stage

#### Scenario: Live provenance is rejected

- **WHEN** the fixture envelope identifies its source or mode as live, provider, or production
- **THEN** the runner SHALL reject the input before producing an output artifact

### Requirement: Per-ticker result visibility

The runner SHALL output one canonical result for each unique input ticker, including stage statuses, the first actionable exclusion reason when applicable, quality status, candidate status, and all scores that were successfully computed. Missing or failed data MUST remain visible and MUST NOT be converted into a passing result or fabricated numeric score.

#### Scenario: Failed ticker does not abort the batch

- **WHEN** one ticker has a missing or failed dimension while another ticker has valid data
- **THEN** the valid ticker SHALL continue through the applicable stages and the failed ticker SHALL retain its failure status and reason

#### Scenario: Candidate keeps score explanations

- **WHEN** a ticker passes the staged filters and heat filter
- **THEN** its result SHALL include factor scores, anti-trap output, heat-filter output, adjusted composite, and candidate=true

#### Scenario: Non-candidate has an actionable reason

- **WHEN** a ticker fails a hard gate, lacks a required dimension, or fails the heat filter
- **THEN** its result SHALL set candidate=false and expose the first applicable stage, dimension/status, and reason without inventing scores

### Requirement: Deterministic user-readable artifacts

The runner SHALL produce deterministic JSON and Markdown artifacts sorted by canonical ticker and bound to the input run identity. The output SHALL include a summary of input count, stage counts, candidate count, quality-status distribution, profile version, as-of, and the explicit fixture/not-evidence status.

#### Scenario: Input order does not change artifacts

- **WHEN** the same normalized fixture is provided in different row or ticker orders
- **THEN** the JSON semantic content and Markdown ticker ordering SHALL be identical

#### Scenario: Output identity is preserved

- **WHEN** the runner completes successfully
- **THEN** both artifacts SHALL contain or clearly display the same run id, profile version, input hash, as-of, fixture provenance, and `capability_status=not_evidence`

#### Scenario: Different runs do not overwrite each other

- **WHEN** two executions use different run ids and the same output directory
- **THEN** the runner SHALL write distinct run-scoped filenames and preserve both artifacts

