# M1/M2：G1 Provider Qualification 与 Canonical Runtime Rolling Handoff（2026-08-06 r4）

> 类型：Independent-review coverage follow-up rolling handoff
>
> 所属大规划：`MASTER-2026-08-06`
>
> 稳定入口：`design/capability-gate-and-execution-handoff.md`
>
> 当前范围：Queue 1，仅 `R-G1-001`
>
> 不适用范围：`R-G1-002`、`R-G1-003`、`R-G1-004`、G1-4、canonical consumer、
> G2、G3 及任何未登记 repair

## 1. 状态

```text
branch: codex/r-g1-001-provenance-compatibility
worktree: /Users/admin/Documents/trade-agent/.worktrees/r-g1-001-provenance-compatibility
previous repair commit: 026907d
Repair ID: R-G1-001
attempt: 3
state: verified
next state: independent_review
full pytest: intentionally not rerun per user instruction
live provider/LLM calls: none
```

第二次 independent review 未发现 P0/P1，但提出 P2：现有测试未覆盖
`_fields.<field>` 级别的 metadata 冲突，也未证明非保留 metadata 会保留。

## 2. 修复与 RED 证据

生产实现未新增逻辑，仍保持：

```text
non-reserved metadata
→ canonical runner fields written last
```

为验证测试确实能捕获回归，临时恢复父版本的错误 `**meta` 顺序后运行新增测试，
得到预期失败：`field-wrong-family` 覆盖 `baseline`。

恢复正确实现后新增断言覆盖：

- `_fields.last_price.provider_family/ticker/response_hash` 不得覆盖 canonical 值；
- `_meta.source_locator` 等非保留 metadata 仍保留。

## 3. 定向验证

```text
value-screener/tests/test_provider_qualification.py
value-screener/tests/test_r_g1_001_provenance_compatibility.py
value-screener/tests/test_field_qualification.py
value-screener/tests/test_provenance_contract.py
value-screener/tests/test_canonical_snapshot.py
→ 49 passed
```

另外通过：

- `openspec validate g1-field-qualification-canonical-promotion --strict`
- `compileall`
- `git diff --check`

本次按用户指示不运行 repository-wide pytest；上一次完整验证结果仍为
`653 passed`，仅作为历史证据，不作为本次新鲜全量验证。

## 4. OpenSpec 与下一步

```text
change: g1-field-qualification-canonical-promotion
tasks: 新增并完成 7.1–7.3
archive: `openspec/changes/archive/2026-08-06-g1-field-qualification-canonical-promotion`
```

本 handoff 不构成 independent review 通过，也不构成 G1/G2 Capability passed。
OpenSpec archive 已按用户指示执行；下一步仍是重新 independent review，确认 P2
关闭后才能讨论将 R-G1-001 推进到 `closed`。
