# M2.1 real-provider and repair evidence

## Status boundary

- engineering_status: `repair_in_progress`
- capability_status: `not_evidence`
- gate_status: `not_passed`
- user_review_status: `not_performed`
- M2.2_status: `not_started`

## Fixed-input real-provider experiment

- experiment date: `2026-09-09`
- canonical ticker: `002709.SZ`
- run_id: `m0-002709-20260904`
- model: `deepseek-v4-pro`
- reasoning level: `heavy`
- repetitions: `3`
- provider calls: `3` total, one per attempt, no retry
- total tokens: `57957`
- stable identity fields: all matched
- structural failures: `0`
- comparison status: `drifted`
- output digest changes: `2`
- quality transition: `failed -> warning`

Attempt outcomes:

1. `failed / grounding`, 19233 tokens; reported unmatched numbers `40.0` and
   `18.7`.
2. `failed / grounding`, 20523 tokens; reported unmatched number `60.0` and
   exceeded the fixed 20000-token audit budget.
3. `warning / skipped`, 18201 tokens; the agent declined a directional result
   as out of circle.

The runtime artifacts remain under the ignored local live-run directory and
are not committed. API credentials and base URL are not recorded here.

## Repair question

The pre-repair artifact stores only the raw-response digest plus normalized
safe output. One bounded diagnostic call is therefore permitted to capture the
raw AgentOutput outside Git and decide whether the unmatched values are:

- fabricated by the model;
- present in a different declared input unit such as ratio versus percent; or
- omitted by input assembly.

No grounding rule is relaxed until that call and the frozen input support one
bounded repair hypothesis.

## Bounded diagnosis

- diagnostic provider calls: `1`
- model/reasoning/input: unchanged
- retries: `0`
- result: `warning / skipped`
- total tokens: `18129`
- raw AgentOutput: stored only in the ignored local live-run directory
- key observation: the model used both decimal-form ratios such as `0.44` and
  percent-form values such as `13.92%` in the same response

Deterministic inspection of the frozen input established these possible
unit-equivalent sources:

- `40%` is unit-equivalent to the declared
  `maintenance_capex_ratio=0.4`;
- `60%` is unit-equivalent to the declared
  `maintenance_capex_ratio=0.6`;
- `18.7%` is within the existing tolerance of traceable historical
  `gross_margin=0.186901`;
- the old checker compared only literal magnitudes and discarded field paths.

Most-supported repair hypothesis: at least part of the grounding instability
can arise because the checker cannot normalize an explicitly labeled
percentage against a semantically proportional field stored as a decimal.
Attempts 1-3 did not retain the raw metric strings, so the evidence does not
prove that their `40/60/18.7` values actually carried percent suffixes.

## RED and GREEN evidence

RED command:

`pytest -q value-screener/tests/test_r1_feature_grounding.py -k percent_labeled_metric`

RED result: `1 failed, 1 passed`; the supported decimal-ratio case failed for
the expected reason.

Initial GREEN focused result: `65 passed` across M2.1, M0.2, R1 grounding, and recursive
feature-number tests.

The repair accepts signed `x%` only for decimal fields whose leaf-name tokens
explicitly denote ratio/rate/margin/ROE/share/percentage semantics. It rejects
opposite-sign values, percentile/price/value/count fields, unlabeled numbers,
and unrelated plain numeric fields. The existing `PE 999` fabricated-number
regression remains green.

## Post-repair real-provider rerun

- attempt index: `4`
- attempt id: `c5652188c1c7d4c0-attempt-004`
- fixed identity fields: all unchanged
- provider calls: `1`
- retries: `0`
- total tokens: `17917`
- execution status: `skipped`
- quality status: `warning`
- failure kind: `null`
- agent signal/out-of-circle: `skip / true`

The post-repair attempt had no grounding failure. It remains a warning/skip
because the agent declined a directional conclusion; the repair does not
rewrite that legitimate model outcome as success. Because this response did
not reproduce the historical unmatched values, it is regression evidence but
not direct proof that the historical incident is fully closed.

The deterministic four-attempt comparison remains `drifted`, has zero
structural failures, and reports all stable identity fields as matched. Prior
failed attempts remain preserved in their original ignored live-run directory.

## Repair verification

- focused M2.1 + M0.2 + grounding regressions after review repair:
  `71 passed`
- full pytest after review repair: `1520 passed, 1 skipped`
- compileall: passed
- OpenSpec strict validation: `38 passed, 0 failed`
- `git diff --check`: passed
- npm lint: not applicable; the project has no matching `package.json` lint
  script

The skipped full-suite test is pre-existing and was not changed by this repair.

## Independent review

One fresh read-only reviewer returned `REQUEST CHANGES` with three P1 findings:

1. substring marker matching could treat `corporate_value`, `share_price`,
   `shareholder_count`, or `percentile` fields as ratios;
2. absolute-value collection in the new percentage branch could hide a sign
   reversal between a negative source ratio and a positive output percentage;
3. the evidence overstated the historical root-cause certainty despite missing
   raw responses from attempts 1-3.

Resolution:

- added RED cases for marker collisions and percentile fields, then changed
  ratio recognition to exact leaf-name tokens;
- added RED sign cases and preserved signed values only in the percentage
  conversion branch while retaining legacy absolute matching elsewhere;
- revised design/evidence to state a supported repair hypothesis and explicit
  residual risk rather than complete causal proof.

No P0/P1/P2 finding remains unaddressed. No second reviewer was started.

## Archive status

- delta spec synced to
  `openspec/specs/g2-strong-agent-baseline/spec.md`
- same change re-archived at
  `openspec/changes/archive/2026-09-09-g2-strong-agent-baseline/`
- merge/push/merged-main verification and repair worktree cleanup remain task
  5.8 and are not claimed complete in this archive commit

## Residual risk

The exact raw AgentOutput strings from attempts 1-3 are unavailable. Therefore
the change proves the checker now handles a safely bounded decimal/percent
representation class, but it cannot prove that every historical grounding
failure had that cause. Future real baseline attempts must preserve sufficient
raw-response audit evidence to distinguish unit conversion from fabricated
numbers without another diagnostic call.
