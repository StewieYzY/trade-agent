# M1.2 Child-only Review

Date: 2026-08-31
Base: 433ce650b52ec580ada387327e0b57a892e5415d
Change: g1-mvp-small-sample-run

## Scope

本次 review 仅覆盖当前 child worktree 相对 baseline 的 M1.2 OpenSpec、实现、CLI 和测试，不覆盖根目录既有 WIP。

## Verification Before Review

- M1.2 focused: `14 passed`
- M1.2 + staged runtime related: `42 passed`
- Full pytest: `1404 passed, 1 skipped`
- OpenSpec strict: `36 passed, 0 failed`
- compileall: passed
- `git diff --check`: passed
- No provider, LLM, Scout, Council or production-cache run was executed by this child.

## Review Findings and Closure

首轮 review 发现 output root、provenance、heat-filter score、Markdown provenance、sample range 和 immutable artifact 问题。修复后再次 review 逐项复核：

- output root 在 staged execution 前经过 `validate_g1_output_root()`；
- provenance 使用 allowlist，未知字段和 live/provider/production 标记 fail-closed；
- heat-filter 排除票复用 staged runtime 的共享评分 helper，保留已计算分数；
- Markdown 稳定展示完整 allowed provenance；
- sample scope 固定为 5–20 个 unique canonical tickers；
- 相同 run id 只允许完全相同内容幂等写入；
- 输出使用 run-scoped staging files 和 `os.replace`。

## Final Verdict

- P0: none
- P1: none
- P2: none
- Ready to merge: Yes

## Capability Boundary

- `engineering_status=ready_for_merge`
- `capability_status=not_evidence`
- `gate_status=not_passed`
- 本 child 不产生真实 G1 Capability Gate evidence，不改变 G1 Gate verdict。
