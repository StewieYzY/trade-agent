# Capability Gate 与执行 Handoff：稳定入口

> 类型：唯一大规划导航入口
>
> 状态：`CURRENT POINTER`
>
> 更新日期：2026-08-06
>
> 本文件不是第二份大规划，不记录动态 milestone、Repair 状态或执行细节。

## 当前唯一生效的大规划

```text
design/capability-gate-and-execution-handoff-2026-08-06.md
```

Master ID：

```text
MASTER-2026-08-06
```

任何新窗口、SubAgent、rolling handoff、OpenSpec repair 或 PR review 都必须先读取
该 CURRENT master。

## 权威层级

```text
产品 Goal / Capability Gate
  design/three-goal-capability-roadmap.md

唯一当前执行大规划
  design/capability-gate-and-execution-handoff-2026-08-06.md

微观执行恢复点
  当前 master 指定的 rolling handoff

可执行合同与任务
  当前 master Repair ID 指向的 OpenSpec
```

## 历史文件

所有带旧日期的完整 Handoff 都是 `HISTORICAL / READ-ONLY`：

```text
design/capability-gate-and-execution-handoff-2026-08-05.md
design/capability-gate-and-execution-handoff-2026-08-04.md
design/capability-gate-and-execution-handoff-2026-08-03.md
```

历史文件用于复盘里程碑，不得作为当前执行入口。

## 防止重复工作的入口规则

- 没有出现在 CURRENT master Repair Register 或 milestone queue 的工作不得开始；
- rolling handoff 不得自行创建 scope；
- 同一 finding 必须复用原 Repair ID；
- OpenSpec、review report、PR description 只引用 master ID/Repair ID；
- 新 dated master 必须迁移所有未关闭 Repair ID；
- 任一时刻只允许一个 dated master 标记为 `CURRENT`。
