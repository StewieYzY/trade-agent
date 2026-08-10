# R-G1-002 implementation evidence

Date: 2026-08-10

Repair ID: `R-G1-002`

Carrier: `g1-r-g1-002-source-plan-matrix-completeness`

Archived Change reference:
`openspec/changes/archive/2026-08-06-g1-field-qualification-canonical-promotion/`

## RED

Added `value-screener/tests/test_r_g1_002_source_plan_matrix_completeness.py`
before changing production code. The pre-fix run was:

```text
11 failed, 3 passed
```

The failures were the expected missing behaviors: plan absence/truncation,
artifact hash and evidence tamper acceptance, plan identity gaps, missing matrix
decisions, and unbound CLI plan-version validation.

## Minimal implementation

- `provider_qualification.py` now writes `plan.json` with `run_id` and completed
  source runs record exact plan/evidence artifact hashes plus a deterministic
  manifest hash.
- `field_qualification.py` requires and parses the frozen plan, validates artifact
  hashes, manifest serialization/hash, plan hash, manifest/plan hash identity,
  complete one-to-one plan/evidence identity coverage, and creates rejected
  decisions for missing required matrix groups.
- `promote_provider_snapshot.py` binds CLI policy construction to
  `PROBE_PLAN_VERSION` using an explicit `--probe-plan-version` choice.
- Existing provider eligibility, canonical snapshot policy, and downstream
  consumers were not changed.

## Verification

Focused and related tests:

```text
107 passed in 4.08s
```

This included the R-G1-002 tests, field qualification, provider qualification,
R-G1-001 compatibility, provenance, canonical snapshot, and provider health tests.

Other checks:

```text
openspec validate --all --strict: 29 passed, 0 failed
python3 -m compileall -q value-screener: passed
git diff --check: passed
```

Repository-wide pytest was rerun with the project's shared virtual environment
at `/Users/admin/Documents/trade-agent/value-screener/.venv`:

```text
674 passed in 52.40s
```

The system-Python attempt that produced `495 items / 18 collection errors` was
an environment mistake, not a project dependency gap. The full suite generated
three test runtime files under `debate/` and `watchlist/`; they were removed
from this worktree and are not part of the commit.

No live provider or LLM was called. The artifact scan found no newly generated
cache, watchlist, debate, canonical snapshot, or other production runtime output.
`R-G1-002` passed independent review and is ready for archive; no G1/G2
Capability is claimed.

## Independent review follow-up

The first independent review returned `REQUEST CHANGES` for two concrete gaps:
missing evidence for plan-declared identities and missing manifest/plan hash
cross-validation. Both were verified and fixed with focused regression tests.
The fresh independent review returned `PASS`.
