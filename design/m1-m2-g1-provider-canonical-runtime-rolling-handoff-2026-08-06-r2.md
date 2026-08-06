# M1/M2：G1 Provider Qualification 与 Canonical Runtime Rolling Handoff（2026-08-06 r2）

> 类型：Repair attempt rolling handoff
>
> 所属大规划：`MASTER-2026-08-06`
>
> 稳定入口：`design/capability-gate-and-execution-handoff.md`
>
> 当前范围：Queue 1，仅 `R-G1-001`
>
> 不适用范围：`R-G1-002`、`R-G1-003`、`R-G1-004`、G1-4、canonical consumer、
> G2、G3 及任何未登记 repair

## 1. 基线与工作区

```text
source main baseline: 2f13be9
current planning baseline: 33540d8
branch: codex/r-g1-001-provenance-compatibility
worktree: /Users/admin/Documents/trade-agent/.worktrees/r-g1-001-provenance-compatibility
remote live/provider/LLM calls: none
```

本 worktree 从当前本地 `main@2f13be9` 新建，并快进到其直接子级
`MASTER-2026-08-06` governance commit `33540d8`；未复用已有 dirty 或 stacked
worktree。

## 2. Repair 状态

```text
Repair ID: R-G1-001
owner: g1-field-qualification-canonical-promotion
attempt: 1
state: verified
next state: independent_review
```

### Root cause

`provider_qualification._field_evidence()` 只在 evidence 顶层写入
`market/ticker/raw_field/response_hash`，而 `validate_field_evidence()` 要求这些
字段同时存在于 `provenance`。因此 runner 标记为 `available` 的字段在 evaluator
入口被降级为 `not_evaluated`，promotion 无法形成 qualified group。

### Implemented boundary

仅修改 `value-screener/scripts/provider_qualification.py`：

- 复用已经计算出的 `raw_field`；
- 将 `market`、`ticker`、`raw_field`、`response_hash` 镜像写入
  `provenance`；
- 不改变 status、eligibility、evaluator policy、promotion writer 或任何 consumer。

## 3. RED → GREEN 证据

### RED

```text
/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python -m pytest -q \
  value-screener/tests/test_r_g1_001_provenance_compatibility.py -vv
```

修复前结果：1 failed；真实 `QualificationRunner output → evaluator → promotion`
fixture 返回 `blocked` 而非预期的 `qualified`。

### GREEN

新增最小集成测试：

```text
value-screener/tests/test_r_g1_001_provenance_compatibility.py
```

覆盖：

- 使用真实 `QualificationRunner` 输出作为 source run；
- evaluator 读取该 run 并验证 provenance contract；
- promotion 生成 canonical `records.json`；
- source run 的 manifest/evidence/raw/plan 等文件在 promotion 后字节不变。

回归测试在 `test_provider_qualification.py` 中断言四个字段与顶层值一致。

## 4. OpenSpec 同步

```text
change: g1-field-qualification-canonical-promotion
spec: 新增 runner canonical provenance compatibility requirement/scenarios
tasks: 新增并完成 R-G1-001 repair tasks 5.1–5.4
archive: 未执行
```

## 5. 验证与边界

已完成：

- focused R-G1-001 integration；
- provider qualification regression；
- field qualification evaluator；
- provenance contract；
- canonical snapshot 相关测试；
- focused 及直接相关测试：`48 passed`；
- 相关全量测试：`125 passed`；
- 仓库完整 pytest：`652 passed`；
- `openspec validate g1-field-qualification-canonical-promotion --strict`：通过；
- `compileall`：通过；
- `git diff --check`：通过；
- runtime artifact / secret / live provider/LLM output 检查：未发现。

本 handoff 不构成 independent review，不构成 archive，不构成 G1/G2 Capability
passed。独立 reviewer 应从最终 commit 的 diff、RED/GREEN 输出和上述测试证据重新核验
`R-G1-001`，并确认没有跨入其他 repair。

## 6. 下一动作

```text
完成完整 repair attempt 验证
→ 提交边界清晰的 runtime/spec/test commit
→ 提供 independent review evidence
→ 仅在独立 review 通过后将 R-G1-001 从 verified 推进到 independent_review/closed
```
