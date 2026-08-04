# M0：G2 前置可信基础收口详细 Handoff

> 日期：2026-08-03
>
> 类型：首个大里程碑详细执行 handoff
>
> 上位总 handoff：`design/capability-gate-and-execution-handoff-2026-08-03.md`
>
> 目标：收口 f3c 前置诊断，并在干净 mainline 上完成 G2 工程整合 review
>
> 当前状态：未开始本轮执行

## 1. 为什么 M0 是第一个大里程碑

当前 G2 已有大量工程实现，但仍有三个不能绕过的问题：

1. f3c 真实强弱模型实验没有完成；
2. G2 工程分支是 stacked branch，不能整体合并；
3. 旧 handoff 与当前 main/branch 状态已经不一致。

因此，第一步不是继续增加 Agent、Prompt 或 G2 数据源，而是完成：

```text
可合并 f3c mainline
→ 真实受控实验
→ 独立根因判断
→ 干净 G2 integration branch
→ G2 工程整体 review
```

M0 完成后，才可以可靠地判断下一步是：

- `f3d` Prompt/model 修复；
- `f3e` 新假设诊断；
- 继续 G2 evidence/A-B；
- 或暂时回退为强单 Agent + DA/事实检查器。

## 2. M0 的成功定义

M0 不是“f3c tasks 全勾选”或“G2 branch 合并”。

M0 成功必须同时满足：

```text
f3c 真实实验可复现
+ 根因结论可判读
+ 显性串台为 0
+ 实验输入与 artifact 审计对齐
+ G2 在干净 branch 上通过工程 review
```

M0 不代表：

- G1 capability passed；
- G2 capability passed；
- Council 已优于强单 Agent；
- 可以启动 G3 runtime。

## 3. 当前基线与风险

### 3.1 当前主线

```text
main@dd52d11
```

main 当前未包含：

- `f3c-harness-mainline@1984ffc`；
- `g2-deep-investment-thesis@daf2111`；
- G2 branch 上的完整实现提交。

### 3.2 当前 f3c worktree

```text
/Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline
branch: f3c-harness-mainline
HEAD: 1984ffc
```

这是 f3c-only checkpoint，但其父提交不是当前最新 main。不能直接 merge。

### 3.3 主要风险

| 风险 | 影响 | 处理 |
|---|---|---|
| f3c worktree 未 rebase | 可能带入旧代码 | 先 rebase main |
| weak/strong model 不同但 provider 不同 | 无法区分模型与 provider stack | artifact 记录 provider host，结论限定为 model + provider stack |
| 只有 fixture | 无法证明真实根因 | fixture 只能作参考 |
| 输入 ticker/features 错配 | 实验结论作废 | fingerprint 与 run-scoped artifact fail closed |
| 实验结果不稳定 | 无法开 f3d | 保持 f3c active |
| G2 stacked branch 整体 merge | 混入旧 f3c/G1 artifacts | 从最新 main 重切 integration branch |
| 直接 archive | 把机制 containment 当 root-cause closure | 必须有真实实验报告和独立 review |

## 4. M0 子 change / 执行单元拆分

M0 由一个现有 f3c change 加三个工程执行单元组成。

```text
M0.1 f3c mainline rebase
    ↓
M0.2 f3c live controlled experiment
    ↓
M0.3 independent review + f3d/f3e decision
    ↓
M0.4 clean G2 integration review
    ↓
M0.5 update dated rolling handoff
```

其中 M0.1、M0.5 是工程治理步骤，不应伪装成新的 capability change。

## 5. M0.1：整理可合并 f3c mainline

### 目标

让 f3c harness 建立在当前 main 上，并证明 rebase 后代码、测试和 OpenSpec 仍然一致。

### 操作范围

只处理：

- f3c harness；
- f3c 相关 tests；
- f3c OpenSpec artifacts；
- 必要的 rebase conflict。

不处理：

- G2 branch 的其他实现；
- G1 provider；
- Prompt 业务修复；
- G3；
- 外部报告。

### Exact commands

```bash
cd /Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline

git status --short --branch
git branch --show-current
git log -5 --oneline

git fetch --all --prune
git rebase main
```

若发生冲突：

1. 只解决 f3c 与 main 的真实冲突；
2. 不顺手合并 G2 stacked branch；
3. 记录冲突文件和决策；
4. rebase 完成后重新跑完整验证。

### 验证命令

```bash
cd /Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline

test -x /Users/admin/Documents/trade-agent/value-screener/.venv/bin/python

cd value-screener
/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python -m pytest -q
cd ..

openspec validate f3c-r1-crosstalk-root-cause --type change --strict
git diff --check
git status --short
```

### M0.1 通过条件

- rebase 无未解决冲突；
- 定向 f3c tests 通过；
- 相关全量 pytest 通过，或所有失败都有明确环境归因；
- strict validation 通过；
- 没有旧实验 artifact 被恢复；
- worktree 状态干净或仅保留明确的实验准备文件。

## 6. M0.2：执行真实 f3c controlled experiment

### 目标

回答 f3c 的真实根因问题：

```text
A：Prompt 案例锚定是否是主要因素？
B：弱模型/provider stack 是否是主要因素？
两者都不是？
结果是否不稳定？
```

### 前置条件

没有以下条件时，停止，不执行 live：

1. 用户明确授权真实模型调用和成本；
2. `weak-model` 与 `strong-model` id 不同；
3. group1 有冻结完整 dossier/features；
4. group2-4 有冻结退化 features；
5. ticker、features、prompt、agent 集合、脚本 commit 已冻结；
6. provider/base 已明确；
7. run id 已预注册。

### 实验组

| 组 | features | prompt | model | 用途 |
|---|---|---|---|---|
| group1 | 完整 | 原 prompt | weak | 完整基线 |
| group2 | 退化 | 原 prompt | weak | 测试数据缺失影响 |
| group3 | 退化 | 剥离案例锚定 | weak | 测试 Prompt 影响 |
| group4 | 退化 | 原 prompt | strong | 测试模型/provider stack 影响 |

必须保持除目标变量外的输入一致。

### 最小命令模板

```bash
cd /Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline/value-screener

/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python \
  scripts/repro_out/crosstalk_exp.py \
  --live \
  --weak-model "<weak-model-id>" \
  --strong-model "<strong-model-id>" \
  --full-features-json "<frozen-full.json>" \
  --degraded-features-json "<frozen-degraded.json>" \
  --run-id "<pre-registered-run-id>"
```

实际运行前必须先查看脚本 help，确认参数未发生变化：

```bash
/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python \
  scripts/repro_out/crosstalk_exp.py --help
```

### 建议运行量

先执行：

1. 一轮 group1-4：16 次 R1 calls；
2. 两轮 group2/group4 配对：16 次 R1 calls；
3. 总计 32 次 R1 calls。

如果成本或 provider 权限只允许较小样本，必须在报告中记录实际调用量，不能按计划量填写。

### 必须落盘的证据

```text
scripts/repro_out/crosstalk_exp_runs/<run-id>/live/summary.json
scripts/repro_out/crosstalk_exp_runs/<run-id>/live/raw/
```

每个结果至少包含：

- run id；
- ticker；
- group；
- model id；
- agent id；
- features hash；
- prompt hash；
- code version；
- provider hostname；
- usage；
- cost 或 `cost_unknown`；
- execution status；
- quality warnings。

禁止写入：

- API key；
- Authorization；
- URL userinfo；
- 用户持仓；
- 未脱敏完整配置。

### 预注册指标

- 显性串台率；
- 隐性串台候选率；
- 凭空数字率；
- citation divergence；
- 同质化率；
- usage；
- cost/cost_unknown；
- partial/failed rate。

## 7. M0.3：独立 review 与分支决策

### 目标

不是解释一份报告，而是根据预注册规则决定下一 change。

### 判读矩阵

| 实验结果 | 下一步 |
|---|---|
| group4 改善，group3 不改善 | 建 `f3d-r1-crosstalk-model-fix` |
| group3 改善，group4 不改善 | 建 `f3d-r1-crosstalk-prompt-fix` |
| group3/group4 都改善 | 建 `f3d-r1-crosstalk-hybrid-fix` |
| 两者都不改善 | 建 `f3e-r1-crosstalk-new-hypothesis` |
| 结果不稳定 | 保持 `f3c` active，不 archive |

### Review 必查项

1. group1 ticker 与 features 是否一致；
2. group2/group4 是否只改变 model id；
3. prompt hash 是否符合预期；
4. raw 与 summary 是否同一 run；
5. fixture 是否被错误计入 live；
6. provider 差异是否被误写成模型差异；
7. 显性串台是否为 0；
8. 高严重度凭空数字是否可解释；
9. cost_unknown 是否被错误填成默认成本；
10. 是否存在部分结果伪装成功。

### M0.3 输出

至少生成：

```text
实验报告
根因判读
指标表
有效性/无效性说明
f3d 或 f3e 建议
是否允许 archive 的决定
```

M0.3 未完成前，不得 archive f3c。

## 8. M0.4：干净 G2 integration review

### 目标

在 f3c mainline 整理后，从最新 main 创建新的 G2 integration branch，只移植并 review G2 工程能力。

### 禁止操作

禁止整体 merge 当前 `g2-deep-investment-thesis` branch，因为其历史包含旧 f3c 和 G1-4 diagnostic 内容。

### 建议分两组移植

#### 组 A：runtime trust / audit / dossier / quality

对应历史语义：

```text
b8f610d
```

复核：

- runtime trust；
- ticker/run audit；
- incomplete cache；
- dossier provenance；
- quality state；
- 主流程质量门；
- warning/failed/degraded 持久化。

#### 组 B：baseline / A-B / InvestmentThesis

对应历史语义：

```text
daf2111
```

复核：

- strong single-agent baseline；
- Council A/B harness；
- InvestmentThesis contract；
- A/B manifest；
- CLI 入口；
- fixture 与 live 边界。

### Integration branch 操作

```bash
cd /Users/admin/Documents/trade-agent

git switch main
git pull --ff-only
git switch -c codex/g2-clean-integration-2026-08-03
```

实际移植时必须按文件和语义选择性 cherry-pick 或手工移植，不能直接把 stacked branch 合入。

### Integration 验证

```bash
cd /Users/admin/Documents/trade-agent

git status --short
openspec list --json

cd value-screener
/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python -m pytest -q
cd ..

openspec validate g2-deep-investment-thesis --type change --strict
git diff --check
```

还需要单独检查：

- `git diff main...HEAD --stat`；
- 是否带入旧 `crosstalk_exp_data/report/raw`；
- 是否带入 G1-4 diagnostic artifacts；
- 是否有未授权真实模型调用；
- 是否将 fixture 写成真实 A/B 证据；
- 是否在 G2 代码中启动 G3 runtime。

### M0.4 通过条件

- 新 branch 基于最新 main；
- G2 两组实现可以独立 review；
- 相关测试和 strict validation 通过；
- 无旧 stacked ancestor 污染；
- 无 G3 runtime；
- 工程 review 结论为 pass 或明确 request changes。

工程 review 通过仍不等于 G2 capability passed。

## 9. M0.5：更新 rolling handoff

M0 完成后必须生成新的 dated rolling handoff，至少更新：

```text
main HEAD
f3c HEAD 和 archive 状态
f3c 实验 run_id
实验报告路径
根因判读
f3d/f3e 是否创建
G2 clean integration branch
测试命令与结果
OpenSpec strict validation
剩余 blocker
下一大里程碑：M1 Provider Qualification 或 G2 Evidence Dossier
```

不得只把本 handoff 复制一遍。

## 10. M0 证据包建议结构

```text
design/
  f3c-crosstalk-root-cause-report-2026-08-03.md

value-screener/scripts/repro_out/crosstalk_exp_runs/<run-id>/
  live/
    summary.json
    raw/

OpenSpec:
  openspec/changes/f3c-r1-crosstalk-root-cause/
  openspec/changes/<f3d-or-f3e>/

Git:
  f3c rebased commit
  clean G2 integration commit(s)
  independent review result
```

实验原始输出不应全部复制进 handoff；handoff 只引用路径和结论。

## 11. 停止规则

立即停止当前 M0 并回报 blocker：

- 没有用户授权模型调用或成本；
- weak/strong model id 相同；
- full/degraded snapshot 不完整；
- ticker fingerprint 不一致；
- provider/base 未记录；
- live 与 fixture 混用；
- 结果只剩单 Agent，却被写成 Council success；
- 显性串台仍存在；
- 实验结果跨轮不稳定；
- rebase 后测试失败且无法判断是冲突还是既有问题；
- G2 integration branch 包含 stacked ancestor；
- 发现 G3 runtime 被提前引入。

## 12. M0 完成后的下一步

若 M0 通过：

1. 生成 rolling handoff；
2. 对 G2 clean integration 做整体独立 review；
3. 进入 M1 `a-share-provider-qualification`；
4. 或根据 G2 数据质量 blocker，优先进入 M4 `g2-evidence-dossier-quality`；
5. 继续保持 G1/G2 capability 未通过的诚实状态。

若 M0 的 f3c 判定需要 f3d/f3e：

1. 创建新的独立 OpenSpec change；
2. 只实现实验指向的最小修复；
3. 不在 f3c 中继续扩 scope；
4. 修复后重新运行受控实验；
5. 再决定是否进入 G2 A/B。

## 13. Suggested skills

- `handoff`：M0 完成后生成下一份 dated rolling handoff；
- `openspec-apply-change`：执行 f3d/f3e 或 G2 child；
- `openspec-archive-change`：仅在真实证据和独立 review 后归档；
- `superpowers:using-git-worktrees`：创建 clean G2 integration worktree；
- `superpowers:test-driven-development`：实现 f3d/f3e 最小修复；
- `superpowers:verification-before-completion`：完成前验证；
- `superpowers:requesting-code-review`：请求 f3c/G2 独立 review；
- `gitnexus-impact-analysis`：修改 `council/`、cache、provider 公共层前分析影响；
- `gitnexus-debugging`：继续定位串台、缓存和 provider stack 根因。

## 14. 参考文件

- [capability-gate-and-execution-handoff-2026-08-03.md](/Users/admin/Documents/trade-agent/design/capability-gate-and-execution-handoff-2026-08-03.md)
- [capability-gate-and-execution-handoff.md](/Users/admin/Documents/trade-agent/design/capability-gate-and-execution-handoff.md)
- [three-goal-capability-roadmap.md](/Users/admin/Documents/trade-agent/design/three-goal-capability-roadmap.md)
- [tradingagents-cn-comparative-assessment-2026-08-03.md](/Users/admin/Documents/trade-agent/design/tradingagents-cn-comparative-assessment-2026-08-03.md)
- [f3c-r1-crosstalk-root-cause tasks](/Users/admin/Documents/trade-agent/openspec/changes/f3c-r1-crosstalk-root-cause/tasks.md)
- [g2-deep-investment-thesis design](/Users/admin/Documents/trade-agent/openspec/changes/g2-deep-investment-thesis/design.md)
- G2 旧 Master Handoff 当前仅存在于 `g2-deep-investment-thesis@daf2111`：
  `design/g2-deep-investment-thesis-master-handoff.md`。clean integration 时应选择性迁移并重新核验。
