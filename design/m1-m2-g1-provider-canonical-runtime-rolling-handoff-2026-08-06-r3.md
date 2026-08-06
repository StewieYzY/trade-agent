# M1/M2：G1 Provider Qualification 与 Canonical Runtime Rolling Handoff（2026-08-06 r3）

> 类型：Independent-review follow-up rolling handoff
>
> 所属大规划：`MASTER-2026-08-06`
>
> 稳定入口：`design/capability-gate-and-execution-handoff.md`
>
> 当前范围：Queue 1，仅 `R-G1-001`
>
> 不适用范围：`R-G1-002`、`R-G1-003`、`R-G1-004`、G1-4、canonical consumer、
> G2、G3 及任何未登记 repair

## 1. 基线与状态

```text
branch: codex/r-g1-001-provenance-compatibility
worktree: /Users/admin/Documents/trade-agent/.worktrees/r-g1-001-provenance-compatibility
previous repair commit: b26937b
Repair ID: R-G1-001
attempt: 2
state: verified
next state: independent_review
live provider/LLM calls: none
```

第一次 independent review 对 attempt 1 返回 `REQUEST CHANGES`，指出 response
`_meta`/field metadata 可通过 `_field_evidence()` 末尾的 `**meta` 覆盖 canonical
provenance 保留字段。

## 2. 修复边界

仅修改：

```text
value-screener/scripts/provider_qualification.py
value-screener/tests/test_provider_qualification.py
value-screener/tests/test_r_g1_001_provenance_compatibility.py
```

以及对应 OpenSpec spec/tasks 和本次 handoff。

实现保持最小：

- 非保留 metadata 先进入 provenance；
- runner 最后写入 `provider_family`、`provider`、`method`、`market`、`ticker`、
  `raw_field`、`response_hash`、`retrieved_at`、`run_scoped`；
- 不修改 evaluator、promotion writer、canonical consumer 或其他 repair。

## 3. RED → GREEN 证据

新增 RED fixture：

```text
value-screener/tests/test_provider_qualification.py::
test_reserved_provenance_fields_cannot_be_overridden_by_response_metadata
```

修复前实测：`provenance.provider_family == "wrong-family"`，而顶层值为
`"baseline"`，测试失败。

修复后：

- reserved provenance regression：通过；
- `QualificationRunner → evaluator → promotion` integration：通过；
- 最终 `provenance.json` 中 canonical identity/hash 与 source evidence 顶层一致；
- source qualification run promotion 前后文件保持不变。

## 4. OpenSpec 与验证状态

```text
change: g1-field-qualification-canonical-promotion
spec: 新增 response metadata 不得覆盖 canonical provenance requirement
tasks: 新增并完成 6.1–6.3
archive: 未执行
```

验证结果：

- 相关测试：`126 passed`；
- 完整 pytest：`653 passed`；
- OpenSpec strict、compileall、`git diff --check`：通过；
- 未产生待提交的 runtime artifact、secret 或 live provider/LLM output。

本 handoff 不构成 independent review 通过，不构成 archive，也不构成 G1/G2
Capability passed。下一 reviewer 应重新检查本次 diff 和以下验证证据，并确认没有
跨入其他 repair。
