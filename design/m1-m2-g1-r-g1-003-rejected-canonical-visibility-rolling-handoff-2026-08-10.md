# M1/M2：R-G1-003 Rejected Canonical Visibility Rolling Handoff（2026-08-10）

> 所属大规划：`MASTER-2026-08-06`
>
> Repair ID：`R-G1-003`
>
> Owner child：`g1-r-g1-003-rejected-canonical-visibility`
>
> 上游归档 Change：`g1-field-qualification-canonical-promotion`

## 当前状态

- 状态：`verified / re-review_passed / closure_pending`
- 本窗口只处理 R-G1-003；不处理 R-G1-004、`g1-canonical-snapshot-consumer`、G1-300 sample、G2 或任何 live provider/LLM。
- 不 archive；不宣称 G1/G2 Capability passed。
- 主 worktree 的 3 个未跟踪内容保持不变，未复制、stage、移动或清理。

## Workspace

```text
branch:  codex/r-g1-003-rejected-canonical-visibility
worktree: /Users/admin/Documents/trade-agent/.worktrees/r-g1-003-rejected-canonical-visibility
base:    main@1ff6678
```

实现范围：

- qualification decision 新增全部 in-policy `evaluated_evidence`；
- qualified evidence 保持 `production_eligible` 与 canonical value；
- rejected evidence 以 `not_qualified`、显式 `null`、原始 status/reason、qualification reason codes 和 provenance 进入 snapshot；
- promotion 在全 rejected 时仍写明确的 not-qualified canonical snapshot；
- reader 只依赖 canonical `records.json` + `provenance.json`，不依赖 `decision.json`；
- source qualification artifacts 不修改，未改变 snapshot schema/status enums、ranking、consumer 或 policy。

## RED → GREEN 证据

- RED：基线新增 R-G1-003 tests 为 `8 failed, 1 passed`；失败集中在 rejected evidence 不进入 canonical records/provenance，以及 all-rejected 不生成 snapshot。
- focused GREEN：R-G1-003、field qualification、canonical snapshot、R-G1-001/002 共 `54 passed`。
- provider qualification/batch 相关：`53 passed`。
- repository full pytest：`684 passed in 56.93s`。
- strict OpenSpec：`openspec validate --all --strict`，`29 passed, 0 failed`。
- compile：`/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python -m compileall -q value-screener` 通过。
- `git diff --check` 通过。
- 未运行 provider/LLM；full pytest 产生的 `debate/`、`watchlist/` 已从本 worktree 清理，未进入提交。

## Independent review

上一次独立只读 review 结论：`REQUEST CHANGES`，发现 1 个 P1 identity mismatch 缺口，以及 P2/P3 验证与状态问题。

本轮处理：

- 在 `validate_field_evidence()` 比较 top-level 与 provenance 的 provider_family/provider/method/market/ticker/raw_field/response_hash/retrieved_at；
- available mismatch 降级为 `not_evaluated`，已有 rejected status 保留原 status 并追加 mismatch reason；
- 增加 8 个 identity mismatch regression tests，并扩展所有现有 rejected status enum 覆盖；
- 增加 promotion 端到端 regression，确认 identity mismatch 不会进入 canonical value；
- 更新 active child spec/tasks；
- 最终独立 re-review：未发现新的 P0/P1/P2/P3；
- fresh verification：focused `76 passed`，full pytest `699 passed in 54.17s`，OpenSpec strict `29 passed, 0 failed`，compileall 与 diff-check 通过。

当前保持 `closure_pending`，不执行 archive、不标记 closed；后续 closure 仍需要单独治理确认。

## Residual risk / next scope

- 当前证据全部是离线 fixture/test evidence，不是 completed live qualification，也不放行 G1 Capability。
- canonical snapshot consumer/staged screening runtime 尚未实现。
- 后续 Queue 1 scope 是 R-G1-004 production-path isolation；不在本 child 中实现。
