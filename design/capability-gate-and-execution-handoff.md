# Capability Gate 与执行 Handoff

> 类型：永久执行导航（宏观能力治理 + 微观工程执行）
>
> 创建日期：2026-07-29
>
> 动态状态截至：2026-07-29
>
> 上位设计：`three-goal-capability-roadmap.md`、`architecture-decisions.md` AD-09 / AD-10
>
> G2 细化设计：`g2-deep-investment-thesis-master-handoff.md`（目前位于 `g2-deep-investment-thesis` 分支）

## 使用方式

本文件分成两部分：

1. **宏观部分**回答“系统现在为什么做这些、什么可以放行、什么必须停止”。
2. **微观部分**回答“下一次具体在哪个 worktree、哪个分支、以什么命令、什么顺序继续”。

不要把“代码提交”“OpenSpec child archive”“测试全绿”误写成 capability Gate 通过。每次会话开始先核验 Git/OpenSpec/真实运行证据；每次状态变化后更新本文件的动态事实，但不要复制完整 spec 内容。

---

# 第一部分：宏观方向、进度与执行逻辑

## 1. 总目标与串行能力链

```text
G1 快：个人价值风格筛选
    ↓ 真实数据与全市场 Gate
G2 深：可信 Investment Thesis
    ↓ 事实、审计、A/B 与盲评 Gate
G3 拿得住：持仓纪律副驾驶
```

执行逻辑：

- **G1 是输入可信度**。如果全市场数据、行业覆盖和排序可信度没有成立，深研不能把错误候选“分析正确”。
- **G2 是结论可信度**。必须先证明单次研究能形成可追溯、诚实标注质量状态的 Thesis，再证明 Council 相比强单 Agent 有稳定增量。
- **G3 是纪律辅助，不是自动交易**。它只能消费通过 G2 Gate 的 `InvestmentThesis`；G2 未通过前不实现 G3 runtime。

当前结论：

- G1 capability 未通过。
- G2 工程机制已建设，但 capability 未通过。
- G3 runtime 继续锁定。

## 2. 当前大盘点

| 主题 | 当前状态 | 不能误读为 |
|---|---|---|
| G1-4 数据源韧性 | D1-D6 runtime 修复已在 main；真实行业接口失败时 Gate 正确 `blocked` | G1 已通过 |
| f3c R1 串台根因 | breaker/harness 已实现；可信强弱模型实验未跑；active `9/17` | 串台根因已定位或 f3c 可 archive |
| G2-1～G2-7 | 在 `g2-deep-investment-thesis@daf2111` 完成工程提交/child archive | G2 capability passed |
| G2 A/B | manifest 仍是 pending real snapshots，没有真实双路径、成本证据或盲评 | Council 已优于强单 Agent |
| G3 | 仅可继续设计与规划 | 可启动 shadow mode 或 runtime |

## 3. 为什么 f3c 是 G2 的前置诊断，而不是新的 G2 child

f3c 要回答的是 L3 R1 串台的根因：

- 假设 A：prompt 案例锚定诱发复读/串台；
- 假设 B：弱模型或 provider stack 在退化 features 下导致编造、同质化或串台；
- 若两者都不支持，则应建立 f3e，继续排查 provider cache、hidden context、代理层复用或数据泄漏。

G2-1 已解决“发现污染后不得伪装成功”的 runtime trust 问题：显性环形引用 fail closed，warning/failed/incomplete 持久化，成功缓存不复用半成品。

但 runtime containment 不等于 root cause closure。f3c 仍须提供可信受控实验，才能决定后续是 f3d prompt/model 修复，还是 f3e 新假设。因此：

- 不新建重复的 G2 child 来实现 f3c；
- 不用 G2 代码完成度绕过 f3c；
- f3c 未收口时，不以真实 G2 A/B 或 G3 runtime 宣称 L3 已可信。

## 4. G2 的工程状态与能力 Gate

G2 已实现的工程层包括：

1. runtime trust、审计身份、质量状态；
2. dossier provenance 与 dossier quality；
3. decision framework 与主流程质量门；
4. 强单 Agent baseline；
5. Council A/B harness；
6. 稳定 `InvestmentThesis` 接口。

G2 尚缺能力层证据：

1. 冻结 8–10 个真实 dossier snapshots；
2. 同模型、同 dossier、可比预算下的 baseline/Council 双路径运行；
3. usage/cost、provenance、quality 状态的真实产物；
4. 人工匿名盲评；
5. Council 没有稳定增量时，回退为“强单 Agent + 独立 DA/事实检查器 + Synthesizer”；
6. 独立整体 review 后，才可能放行 G3。

G1-4 未通过仍会阻断 G2 的**正式 capability pass**。可以完善固定样本上的 G2 foundation/repair，但不能把 mock、fixture、单测或 OpenSpec archive 当真实 Gate 证据。

## 5. 宏观下一步规划

```text
清理可合并 f3c mainline
    ↓
可信 f3c 强弱模型配对实验
    ↓
独立 review：f3c archive / f3d / f3e
    ↓
重新切干净的 G2 mainline，并独立 review G2 工程提交
    ↓
冻结真实 G2 snapshots，执行 A/B + 成本 + 盲评 Gate
    ↓
G2 整体 capability review
    ↓
仅通过后启动 G3 runtime
```

停止规则：

- 没有用户授权的真实模型/成本支出，不调用 LLM；
- 没有可比较的 strong model，不把同一模型重跑冒充组 4；
- G1-4 provider 失败时保持 `blocked`，不 mock 成功；
- f3c 结果不稳定时保持 active，不为了流程 archive；
- G2 A/B 没有 Council 增量时选择回退形态，不为保留多 Agent 而调口径。

---

# 第二部分：微观执行、当前进度与操作逻辑

## 6. 当前 Git / worktree 拓扑

截至 2026-07-29：

```text
/Users/admin/Documents/trade-agent
  main @ 419ce51
  └─ 419ce51 chore: ignore local worktrees

/Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline
  f3c-harness-mainline @ 1984ffc
  └─ 干净的 f3c-only checkpoint，基于 main@3b1ad4e

/Users/admin/Documents/trade-agent-f3c-strong-model-control
  codex/f3c-strong-model-control @ f83bb85
  └─ 旧 stacked 实施 worktree；含 G2 祖先，不得作为 main merge source

g2-deep-investment-thesis @ daf2111
  └─ stacked G2 工程分支；其祖先还含旧 f3c checkpoint，不得整体 merge main
```

`.worktrees/` 已被根 `.gitignore` 忽略，因此项目内 worktree 不会污染 Git status。

## 7. f3c mainline checkpoint

可审查的 f3c-only 提交：

```text
1984ffc wip(f3c): harden controlled model experiment harness
```

它只包含：

- `openspec/changes/f3c-r1-crosstalk-root-cause/{design.md,tasks.md,specs/council-debate/spec.md}`
- `value-screener/council/llm.py`
- `value-screener/scripts/repro_out/crosstalk_exp.py`
- `value-screener/tests/test_crosstalk_experiment.py`
- `value-screener/tests/test_llm_usage.py`

它明确**不包含**：

- G2-1～G2-7 的代码/spec/archive；
- G1-4 handoff 或 failed sample artifacts；
- 已作废的旧 `crosstalk_exp_data.json`、report、raw outputs。

已验证证据：

```text
14 passed  # f3c harness + llm usage 定向测试
512 passed # 在 mainline 基线上完整 pytest
openspec validate f3c-r1-crosstalk-root-cause --strict
git diff --check
```

独立 review 已完成并回填：

- group1 ticker/data 错配修复；
- group2/group4 的 ticker/features/prompt/agents 一致，仅 model id 不同；
- weak/strong 相同、缺少 live 输入、空 full snapshot 均 fail closed；
- fixture 标记为 `fixture_reference`，不得冒充 prompt/model 对照；
- live/fixture 写入 `run_id/mode` 隔离路径；
- artifact 记录 model、非敏感 provider host、ticker、agent、features/prompt hash、usage、代码版本；
- URL userinfo 不进入 artifact；
- group2/group4 经过真实 harness 编排与 summary/raw 落盘回归测试。

## 8. f3c 下一步：先让分支可合并，再做真实实验

### 8.1 合并前整理

`f3c-harness-mainline` 的父提交是 `3b1ad4e`，而 main 已前进到 `419ce51`（仅增加 `.worktrees/` 忽略规则）。

合并或发起 PR 前：

```bash
cd /Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline
git fetch --all --prune
git rebase main
cd value-screener
/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python -m pytest -q
cd ..
openspec validate f3c-r1-crosstalk-root-cause --strict
git diff --check
```

rebase 无冲突、验证仍通过后，`1984ffc`（rebased 后 SHA 会变化）才是可独立 merge main 的 f3c WIP checkpoint。它进入 main 也不代表 f3c archive。

### 8.2 真实强弱模型实验的输入

只有用户明确授权模型调用与成本后，才能运行 `crosstalk_exp.py --live`。

必须提供：

1. `--weak-model` 和 `--strong-model`，且 model id 不同；
2. group1 的冻结完整 dossier/features JSON；
3. group2-4 共用的冻结退化 features JSON（允许 `{}` 以复刻 missing features）；
4. 明确 provider/base。不同 provider 时结论只能表述为“model + provider stack”差异；
5. 固定 agent 集合、prompt 版本、脚本 commit、实验判读规则。

最小命令形态：

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

输出必须读取新生成的：

```text
scripts/repro_out/crosstalk_exp_runs/<run-id>/live/summary.json
scripts/repro_out/crosstalk_exp_runs/<run-id>/live/raw/
```

不得恢复旧 canonical report/data/raw 作为证据。

### 8.3 推荐实验量与判读

推荐先运行：

1. 一轮 group1–4（16 次 R1 calls）；
2. 再运行两轮 group2/4 配对（16 次 R1 calls）；
3. 总计 32 次 R1 calls。

预注册指标：

- 显性串台率；
- 隐性串台候选率；
- 凭空数字率；
- citation divergence / 信息增量；
- usage；若无法得到成本，记录 `cost_unknown`，不得补默认值。

判读：

- group4 稳定改善、group3 不改善：B 是贡献因素，开 f3d model-policy 修复；
- group3 稳定改善、group4 不改善：A 是贡献因素，开 f3d prompt 修复；
- 两者改善：开 f3d 混合修复；
- 两者均不改善：开 f3e 新假设；
- 结果不稳定：f3c 保持 active。

真实产物完成后再回填 f3c 任务 `2.1 / 2.2 / 2.3 / 4.1 / 4.2 / 5.2`，然后独立 review。当前 f3c 是 `9/17`，不得 archive。

## 9. G2 分支的重新集成策略

不要 merge 当前 `g2-deep-investment-thesis` 整体分支。它的历史含：

```text
a9f1fc7  G1-4 diagnostic docs
2904525  旧 f3c checkpoint
b8f610d  G2-1～G2-4
daf2111  G2-5～G2-7
```

正确做法是在 f3c mainline 整理后：

1. 从最新 main 新建干净 G2 integration branch；
2. 只移植并审查 G2 最终代码/spec/archive，不携带 G1-4 diagnostic 或旧 f3c experiment artifacts；
3. 将 G2 拆为至少两次 review：
   - `b8f610d` 语义：runtime trust / audit / dossier / quality gates；
   - `daf2111` 语义：strong baseline / A-B harness / InvestmentThesis；
4. 在干净 G2 branch 上重新运行测试、strict specs、检查 mainline merge diff；
5. 工程 review 通过后再决定是否 merge main；merge 不等于 capability pass。

## 10. 新会话最小启动清单

```bash
cd /Users/admin/Documents/trade-agent
git status --short
git log -1 --oneline main
git worktree list

cd /Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline
git status --short
git branch --show-current
git log -1 --oneline
openspec list --json
```

然后根据目标选择：

- **准备 merge f3c harness**：执行 §8.1 rebase + verification。
- **做真实 f3c 实验**：先获得用户对模型/成本的授权，再执行 §8.2。
- **审查/重切 G2**：先完成 f3c 的当前阻断处理，再按 §9 建干净 integration branch。

## 11. 本文件维护规则

更新本文件仅当以下动态事实变化：

- main / f3c / G2 branch、commit 或 worktree 位置变化；
- f3c 真实实验完成、结论改变或创建 f3d/f3e；
- G1-4 Gate 状态变化；
- G2 工程重新集成、真实 A/B/盲评完成或 pipeline 选择改变；
- G3 放行条件改变。

不要把完整测试日志、长原始模型输出、API key、Authorization header 或用户持仓写入本文件。

## 12. 2026-08-04：clean G2 fallback integration checkpoint

已从最新 `main@dd52d11` 创建：

```text
/Users/admin/Documents/trade-agent/.worktrees/g2-integration-mainline
branch: codex/g2-integration-mainline
```

本次只移植 G2 fallback 的最小 mainline prerequisites：

- tracked `value-screener/data/cache/` source，缓存 JSON 仍 local-only；
- f3c Council input preflight 及其受影响 fixture tests；
- G2 strong single-agent fallback foundation。

验证结果：

- focused Council/preflight/fallback：`93 passed`；
- full `pytest value-screener/tests/`：`527 passed`；
- OpenSpec strict validation 与 `git diff --check` 通过。

该 checkpoint 只证明 clean mainline integration，不是 G2 capability pass；G2 A/B、
成本证据、人工盲评和 G3 runtime 继续锁定。测试生成的 `debate/`、`watchlist/`
只保留本地，不进入源码 commit。
