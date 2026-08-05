# G1 Field Qualification and Canonical Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已有 run-scoped provider qualification evidence 按显式字段政策审查为可审计的 field-level eligibility decision，并仅把通过政策的字段写入 immutable canonical snapshot。

**Architecture:** 新增独立 policy/evaluation 层，不改变 `provider_qualification.py` 的 probe runner、legacy cache、ranking 或下游消费者。该层读取已完成 qualification run 的 `manifest.json` 与 `evidence.json`，验证 run 完整性、冻结的 ticker/method/field coverage、字段 provenance/time basis/freshness、跨 ticker coverage 和 provider consistency；输出带 decision reason 的 qualification decision sidecar，并把 `production_eligible` 仅赋给显式通过字段，再调用现有 `canonical_snapshot` writer 生成 run-scoped snapshot。

**Tech Stack:** Python 3.10+, pytest, 现有 `data.lib.provenance` / `data.lib.canonical_snapshot`，不新增依赖。

## Global Constraints

- 不调用真实 provider，不新增 LongPort/Longbridge SDK，不修改 legacy cache、ranking、watchlist、debate 或 G2/G3 runtime。
- `available` 不等于 production eligible；没有完整 provenance、可信时间基准、允许的 status、合格 coverage 或一致性证据时 fail closed。
- `record_not_found`、`source_failed`、`invalid_value`、`not_evaluated` 等失败状态必须保留，不转换为默认值或静默 fallback。
- 所有输出必须 run-scoped、immutable、可审计；原 qualification evidence 不得被原位覆盖。
- 代码修改前先写失败测试；每个行为先完成 RED → GREEN → focused regression。
- 项目根目录和 `value-screener/` 均无 `package.json`，因此 npm lint 不可运行；Python 验证使用仓库现有 `.venv`。

## Files and Responsibilities

- Create: `value-screener/data/lib/field_qualification.py` — qualification run loading, policy validation, field-level decision and promotion input construction。
- Create: `value-screener/scripts/promote_provider_snapshot.py` — 面向 run-scoped artifacts 的 CLI/入口，负责读取 qualification run、写 decision 与 canonical snapshot。
- Create: `value-screener/tests/test_field_qualification.py` — policy、coverage、freshness、consistency、fail-closed 与 output isolation 行为测试。
- Create: `openspec/changes/g1-field-qualification-canonical-promotion/` — proposal/design/spec/tasks，记录本 child 的边界和可验证任务。
- Modify: `value-screener/data/lib/canonical_snapshot.py` — 仅在测试暴露到入口契约缺口时，补最小的 manifest/sidecar 连接能力；不改变既有 canonical eligibility 语义。
- Modify: `design/g1-field-qualification-canonical-promotion-decision-2026-08-05.md` — 记录本轮实现与能力边界，明确不代表 G1 capability pass。

### Task 1: OpenSpec child and contract

- [ ] 创建 change artifacts，冻结 input run schema、field policy schema、decision status、coverage thresholds、output layout 和 non-goals。
- [ ] 用 `openspec validate ... --strict` 验证 artifacts，确保实现按 active tasks 推进。

### Task 2: Field-level policy evaluator

- [ ] 先写 failing tests：缺 artifact/不完整 run、非 A-share ticker、unexpected method/field、missing provenance/time basis、failure status、coverage 不足、cross-ticker value/time/unit conflict、stale/unknown freshness 均不得 promotion；完全满足 policy 的 field 才返回 `production_eligible`。
- [ ] 实现纯函数 evaluator，返回 decision records、status summary、provider/field coverage 和不修改原 evidence 的 promoted evidence。
- [ ] 运行 focused tests，确认 RED→GREEN。

### Task 3: Run-scoped promotion entrypoint

- [ ] 先写 failing tests：从 qualification run 读取 evidence，输出 `decision.json` 和 canonical snapshot；重复 run_id/输出越界/缺失文件 fail closed；原始 qualification run 保持不变。
- [ ] 实现 CLI/入口，固定 promotion run 与 source qualification run 的 identity，manifest 记录 code version、policy version、source evidence hash、decision hash 和 canonical output。
- [ ] 运行 focused tests、compileall 和 strict OpenSpec validation。

### Task 4: Decision record and handoff

- [ ] 写 dated design decision，列出实际 fixture 证据与未做的 live provider verification。
- [ ] 运行相关 provider qualification/canonical/provenance/full pytest 与 `git diff --check`；检查测试产生的 runtime artifacts 并清理不应提交的文件。
- [ ] 更新 OpenSpec tasks checkbox，仅勾选已由命令验证的任务。
