## 1. RED: clean-checkout integration tests

- [x] 1.1 Add CacheManager import/normalize/atomic-write tests and verify they fail on
  clean `main` because `data.cache` is absent.
- [x] 1.2 Add fallback import and zero-side-effect preflight tests in the clean worktree.
- [x] 1.3 Add a regression assertion that fallback does not write Council cache, debate, or
  watchlist outputs.

## 2. GREEN: mainline integration

- [x] 2.1 Track `value-screener/data/cache/__init__.py` and `manager.py`; keep cache JSON
  ignored.
- [x] 2.2 Integrate the validated Council dossier preflight and its focused tests without
  importing the full f3c experiment branch.
- [x] 2.3 Keep the G2 fallback foundation on the integrated preflight path.

## 3. Verification and handoff

- [x] 3.1 Run cache/preflight/fallback focused tests and record RED→GREEN evidence:
  RED showed missing `data.cache` and missing `_prepare_council_input`; GREEN is `24 passed`.
- [x] 3.2 Run complete `pytest value-screener/tests/`, strict OpenSpec validation, and
  `git diff --check`: full suite `527 passed`; strict validation and diff check passed.
- [x] 3.3 Update the dated G2 handoff: clean integration checkpoint complete, G2
  capability A/B and G3 runtime still locked.
