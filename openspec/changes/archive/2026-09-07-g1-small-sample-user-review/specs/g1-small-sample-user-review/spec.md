## ADDED Requirements

### Requirement: Offline M1.2 artifact binding is fail-closed

The M1.3 reviewer SHALL accept only a valid `g1-small-sample-run/v1` M1.2 artifact with `artifact_type=fixture/reference`, `mode=simulated/development`, `capability_status=not_evidence`, `gate_status=not_passed`, valid provenance, and a canonical ticker-set hash matching its ticker list. It MUST reject live/provider/production inputs, unknown fields, malformed per-ticker structures, identity mismatches, and inconsistent optional Markdown identity before creating output.

#### Scenario: Valid M1.2 artifact is accepted

- **WHEN** a deterministic M1.2 fixture/reference JSON artifact contains valid identity, provenance, summary, staged evidence, and canonical ticker results
- **THEN** the reviewer SHALL construct a bound M1.3 template without calling a provider, LLM, Scout, or Council

#### Scenario: Live or production input is rejected

- **WHEN** the artifact or provenance identifies live, provider, or production execution
- **THEN** the reviewer SHALL raise a validation error before creating the output directory or files

#### Scenario: Identity and ticker-set mismatch is rejected

- **WHEN** `run_id`, `profile_version`, `input_ticker_set_hash`, `as_of`, or canonical ticker membership is inconsistent across the artifact, per-ticker rows, or optional Markdown
- **THEN** the reviewer SHALL fail closed before writing any output

#### Scenario: Unknown input structure is rejected

- **WHEN** the M1.2 artifact contains an unknown top-level or per-ticker field
- **THEN** the reviewer SHALL reject it instead of silently ignoring the field

### Requirement: Review feedback is explicit and preserves user text

The reviewer SHALL represent each canonical ticker across exactly four dimensions: `candidate`, `inclusion_or_exclusion_reason`, `scores_and_thresholds`, and `quality_and_data`. Each dimension SHALL support `accepted`, `question`, `problem`, and `not_evaluable`, and SHALL preserve `feedback`, `question` or `issue`, and optional `corrected_value` and `suggested_action` without whitespace normalization.

#### Scenario: Template never implies acceptance

- **WHEN** no user feedback is supplied
- **THEN** every ticker and dimension SHALL be emitted with `status=not_evaluable`, empty user text, `review_status=template`, and `capability_status=not_evidence`

#### Scenario: Completed feedback covers every ticker and dimension

- **WHEN** explicit feedback supplies valid status and required user text for every canonical ticker and all four dimensions
- **THEN** the reviewer SHALL preserve the original text and emit `review_status=completed`, `capability_status=mvp_evidence`, and `gate_status=not_passed`

#### Scenario: Missing or invalid feedback is rejected

- **WHEN** a feedback dimension is missing, has an unsupported status, has a non-string user text field, or lacks required explanation for `question`, `problem`, or `not_evaluable`
- **THEN** the reviewer SHALL reject the record instead of interpreting missing data as accepted

#### Scenario: Markdown escapes user-provided control characters

- **WHEN** feedback contains `|`, newlines, backticks, HTML-sensitive characters, or empty values
- **THEN** JSON SHALL retain the original string and Markdown SHALL remain parseable/readable with escaped cells and explicit empty markers

### Requirement: Deterministic review artifacts and issue summary

The reviewer SHALL emit deterministic JSON and Markdown artifacts sorted by canonical ticker, bound to the M1.2 source identity and a deterministic source digest. The record SHALL include per-ticker feedback, overall review status, counts by feedback status, explicit threshold/mis-selection/missed-candidate/data-insufficiency issues, and next-step suggestions.

#### Scenario: Input ordering does not change output

- **WHEN** equivalent M1.2 ticker rows or feedback rows are supplied in different orders
- **THEN** semantic JSON and rendered Markdown SHALL be identical and ticker order SHALL be canonical

#### Scenario: Problem categories remain explicit

- **WHEN** the caller supplies threshold issues, false-positive tickers, false-negative tickers, data-insufficiency notes, or next steps
- **THEN** the reviewer SHALL validate and preserve those categories in stable order without changing the M1.2 candidate result or screening rules

#### Scenario: Tampered output digest is rejected

- **WHEN** a generated review record is changed without recomputing its bound digest
- **THEN** record validation SHALL reject it

### Requirement: Output isolation and offline CLI

The reviewer SHALL provide an offline CLI named `small-sample-user-review` with required `--input` and `--output-dir` options. It SHALL write only `<run_id>-review.json` and `<run_id>-review.md` below the explicit safe output directory, reject protected production roots, avoid all provider/LLM/Council side effects, and prevent different content from overwriting an existing run.

#### Scenario: CLI writes isolated run-scoped artifacts

- **WHEN** the CLI receives a valid M1.2 JSON file and an explicit non-production output directory
- **THEN** it SHALL write both review artifacts without creating cache, watchlist, debate, or live-evidence files

#### Scenario: Same run is immutable

- **WHEN** the same run_id is written again with identical content
- **THEN** the CLI SHALL succeed idempotently; when content differs, it SHALL reject the write and preserve the original files

#### Scenario: Protected output is rejected before mkdir

- **WHEN** `--output-dir` resolves to a protected production/cache/watchlist/debate/live-evidence root
- **THEN** the CLI SHALL fail before creating files or directories
