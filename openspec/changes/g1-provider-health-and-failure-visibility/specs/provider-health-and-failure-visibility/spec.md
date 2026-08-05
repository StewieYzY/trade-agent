## ADDED Requirements

### Requirement: Live qualification cases are bounded and isolated

The live qualification runner SHALL execute each probe case within an explicit timeout
and SHALL terminate a child process that exceeds its deadline. A timed-out case MUST NOT
block later cases in the probe plan.

#### Scenario: Probe case completes before deadline
- **WHEN** an isolated provider case returns within its configured timeout
- **THEN** the runner SHALL record its normal field evidence, terminal event, elapsed time,
  and completed status

#### Scenario: Probe case exceeds deadline
- **WHEN** a child process does not return before the case timeout
- **THEN** the runner SHALL terminate the child, record `source_failed` failure metadata
  with `failure_class=timeout` and `terminated=true`, and continue or stop according to
  the run policy without fabricating available evidence

### Requirement: Qualification progress survives partial runs

The runner SHALL persist run-scoped append-only terminal events and an atomically updated
manifest after each case. The manifest SHALL distinguish completed, timed-out,
interrupted, and not-started cases.

#### Scenario: Run completes normally
- **WHEN** all planned cases finish
- **THEN** the manifest SHALL mark `completion_status=completed`, include all terminal
  case events, and write the aggregate evidence/comparison artifacts

#### Scenario: Run is interrupted or terminated
- **WHEN** the parent process stops before all cases finish
- **THEN** the events file and partial manifest SHALL remain readable, include a
  non-null stop reason, and SHALL NOT claim `completion_status=completed`

### Requirement: Timeout and failure metadata are auditable and safe

Every terminal event SHALL include run_id, provider, method, ticker, execution mode,
status, elapsed seconds, and a bounded non-sensitive failure classification when relevant.
Raw exception text MUST be redacted before persistence.

#### Scenario: Provider exception is persisted
- **WHEN** a provider raises a permission, rate-limit, schema, or transport exception
- **THEN** the event SHALL preserve the classified status and redacted reason without
  secrets, authorization headers, or URL userinfo

#### Scenario: Timed-out evidence is consumed later
- **WHEN** a later decision reads a qualification run containing timeout events
- **THEN** it SHALL be able to distinguish timeout metadata from `record_not_found` and
  SHALL NOT treat timeout events as production-eligible field evidence

### Requirement: Partial qualification does not imply completion or capability

The runner SHALL fail closed for incomplete runs. Partial events or a non-empty artifact
directory MUST NOT be reported as a completed qualification run or capability pass.

#### Scenario: Some cases completed before timeout
- **WHEN** at least one case completed and another case timed out or was interrupted
- **THEN** the manifest SHALL mark the run incomplete and list not-started cases without
  filling them with default values

#### Scenario: All cases are unavailable
- **WHEN** no provider adapter is callable or the run stops before a case begins
- **THEN** the runner SHALL write an explicit stop reason and SHALL leave provider
  eligibility unchanged

### Requirement: Health boundary does not mutate production paths

The bounded qualification runner SHALL write only to its caller-provided run-scoped
output root and MUST NOT mutate legacy cache, ranking inputs, canonical production
snapshots, debate outputs, watchlist outputs, or growth diagnostic inputs.

#### Scenario: Bounded probe finishes
- **WHEN** a real or fixture provider run completes, times out, or is interrupted
- **THEN** only qualification artifacts and health metadata SHALL be created

#### Scenario: Candidate provider is probed
- **WHEN** a candidate LongPort or Longbridge adapter is used in shadow/qualification mode
- **THEN** its evidence SHALL remain outside production data paths and its eligibility
  SHALL remain non-qualified until a later explicit decision
