# Capability Gate 与执行 Handoff：MVP-first 当前规划

> 类型：唯一当前生效的大规划
>
> 状态：`CURRENT`
>
> 更新日期：2026-08-27
>
> 规划版本：`MASTER-2026-08-27`
>
> 核心调整：先形成可运行的最小闭环，再用实验结果推动工程增强与正式 Capability Gate。

## 1. 当前结论

trade-agent 的长期目标不变：

```text
G1 快：个人价值风格筛选
    ↓
G2 深：可信 Investment Thesis
    ↓
G3 拿得住：持仓纪律副驾驶
```

但当前执行方式调整为：

```text
MVP 可运行
→ 小样本真实实验
→ 针对性修复
→ 工程闭环
→ 正式 Capability Gate
```

不再要求先完成全市场规模、完整 Council、完整 HoldingContract 和前端，用户才能看到产品价值。

正式 Gate 仍然保留，只是从“开发前置条件”调整为“经过 MVP 实验后的发布条件”。

## 2. 当前基线

### 2.1 Git 与 OpenSpec

行动前必须重新核验以下动态状态：

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git worktree list
openspec list --json
```

本次规划更新时已核验：

```text
main == origin/main == d53134f
G1 umbrella：16/16，complete
G2 umbrella：11/27，in-progress
G3 umbrella：0/29，in-progress，runtime locked
```

根目录已有未跟踪 WIP，后续任何 child 都不得覆盖、删除、stage 或重置这些内容。

### 2.2 已完成能力

当前可以直接复用：

- canonical ticker、run identity 和 audit chain；
- canonical snapshot、provenance、field qualification；
- quality status、incomplete cache 隔离和 fail-closed；
- G1 staged screening runtime；
- G1 价值、质量、反陷阱和热度筛选；
- G1 真实全市场与 Top-20 历史证据；
- G2 dossier 数据质量与事实接地；
- growth expectation contract；
- growth expectation V0 engine；
- growth expectation dossier / InvestmentThesis projection；
- strong single-agent 与 Council 共享 diagnostic 的确定性证明；
- G2 main-flow quality gate 4.1。

### 2.3 尚未形成产品闭环

- G2 4.2/4.3 尚未完成完整持久化和下游阻断证据；
- Prompt 决策框架仍未完成蒸馏；
- strong single-agent baseline 尚未完成正式固定；
- Council A/B 尚未完成；
- 稳定 `InvestmentThesis` 尚未成为对外主接口；
- G3 `holding/` runtime 尚未开发；
- 前端尚未开发。

## 3. MVP-first 执行原则

### 3.1 三种完成状态必须分开

```text
MVP 可运行
    能对少量股票跑通并产生用户可读产物

工程闭环
    身份、质量、缓存、错误、测试和审计完整

Capability Gate 通过
    规模、用户复核、A/B、历史回放或 shadow mode 等正式证据满足
```

任一 child 完成，只能说明该 child 的工程范围完成，不自动推出上层 Goal 通过。

### 3.2 MVP 的最小约束

MVP 可以缩小：

- 股票数量；
- 数据维度；
- Agent 数量；
- 自动化程度；
- 持久化复杂度；
- 运行频率；
- UI 复杂度。

MVP 不可以放松：

- ticker/run identity；
- 数据来源和报告期可见；
- `not_evaluable`、`failed` 和 warning 语义；
- 不把观点伪装成事实；
- 不把“公司好”直接等同于“当前值得买”；
- 不自动交易。

### 3.3 当前产品判定对象

从本规划开始，所有 G2 结果都必须区分：

```text
view_signal
    分析观点：bullish / bearish / neutral / skip

investment_eligibility
    投资资格：investable / watchlist_only / speculative / not_evaluable
```

```text
view_signal != investment_eligibility
```

一个正确的 MVP 结果可以是：

```text
公司质量：强
分析观点：bullish
当前估值：预期偏高
投资资格：watchlist_only
```

## 4. 现有能力处理矩阵

| 能力/模块 | 当前处理 | 后续口径 |
|---|---|---|
| canonical snapshot / provenance / audit chain | 保留 | 所有 MVP 和正式路径共用 |
| quality status / fail-closed / cache isolation | 保留 | 继续完成 G2 4.2/4.3，但不阻塞单股 MVP 实验 |
| `run_staged_screening` | 保留 | 作为 G1 主路径 |
| `screen_a_shares` | 兼容保留 | 后续标记 legacy，不立即删除 |
| F-Score / ROE / OCF / anti-trap | 保留 | 作为 G1 价值风格基础 |
| G1 `safety_margin` 命名 | 改造 | 改为治理/风险安全分，不能代表真实估值安全边际 |
| `compute_simple_dcf` | 保留但降级 | legacy diagnostic，不进入投资资格主链 |
| PE/PB/PE×PB | 保留 | G1 筛选因子，不作为统一内在价值 |
| heat filter | 保留 | 只用于防追高和情绪背景 |
| growth expectation diagnostic | 保留 | G2 MVP 的核心估值诊断，不是目标价 |
| dossier / fact grounding | 保留 | G2 MVP 直接消费 |
| Council 多轮辩论 | 暂不作为默认 MVP | 通过 A/B 后再决定是否保留为默认形态 |
| 人物角色 prompt | 保留展示层 | 内部改成决策框架，不以语录和案例为核心 |
| `bullish/bearish` | 保留 | 只表示观点，不代表投资资格 |
| `target_price` | 保留为市场共识证据 | 不进入内在价值、安全边际或 G3 规则 |
| monitor diff/history | 保留 | 作为实验记录和后续 G3 输入 |
| catalyst placeholder | 保留 | 暂不作为买入信号 |
| HoldingContract runtime | 延后 | G2 MVP 和正式 Thesis 稳定后再开发 |
| 前端、数据库、任务队列 | 延后 | 核心闭环验证后再建设 |

## 5. 大里程碑规划

### M0：可运行 MVP 基线

目标：

> 使用现有可靠输入，对至少一只股票跑通“输入 → 诊断 → 深研 → 可读产物 → 人工反馈”。

最小闭环：

```text
已有缓存或冻结输入
→ dossier
→ growth expectation diagnostic
→ strong single-agent
→ Investment Thesis 草稿
→ Markdown/JSON 产物
→ 用户人工复核
```

产品产物至少说明：

- 公司是什么生意；
- 公司质量；
- 当前价格隐含的增长预期；
- 预期是否超过可信范围；
- 主要风险与反证；
- 什么条件会改变判断；
- 当前是 `investable`、`watchlist_only`、`speculative` 还是 `not_evaluable`。

Non-Goals：

- 不运行全市场；
- 不要求 Council；
- 不实现前端；
- 不实现 G3 runtime；
- 不输出自动买卖指令。

建议 child：

```text
详见 §5.1 的 M0 child queue
```

### M1：G1 快筛 MVP

目标：

> 对 5-20 只股票或一个小型多行业样本，验证个人价值风格筛选是否符合预期。

产物：

- 每只股票的筛选分数；
- 通过/排除原因；
- 质量、估值、反陷阱、热度和数据质量；
- 不足数据的显式状态；
- 可供 M0/G2 选择的候选列表。

完成标准：

- 可重复运行；
- 不因缺失数据静默放行；
- 不将低热度当成低估；
- 用户可以指出至少一个“为什么进入”和一个“为什么排除”的理由。

正式 Gate 后置：

- 300+ 多行业样本；
- 全市场实跑；
- 15 分钟性能；
- 成本/稳定性；
- Top-20 正式复核。

建议 child：

```text
详见 §5.1 的 M1 child queue
```

### M2：G2 深研 MVP

目标：

> 针对一只指定股票，以强单 Agent 为默认路径，生成可人工评审的 Investment Thesis 草稿。

最小输入：

- 可信 dossier；
- growth expectation diagnostic；
- 明确的 assumption snapshot；
- 当前价格/市值和报告期；
- 来源与数据质量状态。

最小输出：

- `business_quality`；
- `view_signal`；
- `investment_eligibility`；
- `valuation_status`；
- `expectation_status`；
- `downside_status`；
- evidence；
- counter_evidence；
- risks；
- key variables；
- what would change my mind；
- pending verification；
- quality status。

完成标准：

- 同一输入可以复现；
- 数据不足时可以拒绝判断；
- 能明确表达“公司很好但价格太贵”；
- 能识别“价格主要由未来预期支撑”；
- 能识别低增长情景下的损失风险；
- 用户可以对一只股票给出人工反馈。

Council 暂不作为 MVP 前置条件。

建议 child：

```text
详见 §5.1 的 M2 child queue
```

### M3：G3 手工纪律 MVP

目标：

> 在不开发 HoldingContract runtime 的前提下，验证“拿得住”的规则是否真的能帮助用户行动。

最小产物：

```text
Holding Discipline Card
```

内容：

- 为什么持有；
- 当前估值和预期基线；
- 关键变量；
- Thesis 破坏条件；
- 价格下跌时应该做什么；
- 估值过高时应该做什么；
- 允许加仓的条件；
- 禁止冲动卖出的条件；
- 必须人工复核的事项。

特别增加：

```text
Thesis 仍成立，但估值已经过度扩张
→ 不等于公司变坏
→ 但可以触发估值复核、停止新增资金或再平衡审查
```

正式 G3 runtime 后置：

- HoldingContract schema；
- HoldingsRepository；
- MonitorSignal；
- 状态机；
- pre_trade_check；
- 历史回放；
- 四周 shadow mode。

建议 child：

```text
详见 §5.1 的 M3 child queue
```

### 5.1 MVP 阶段 Child Change 拆分与推进队列

M0–M3 是产品阶段，不等同于单个 OpenSpec change。每个阶段继续拆成
可独立实现、测试、评审和归档的 child change。队列可以提前列出多个
pending child，但任一时刻只能有一个 `active` child、一个 active
worktree。

状态字段分为两类：

```text
engineering_status
    proposed / active / review / archived / merged

capability_status
    not_evidence / mvp_evidence / gate_evidence
```

`engineering_status=merged` 只表示代码工程闭环完成；
`capability_status=mvp_evidence` 才表示产生了可供用户复核的 MVP 证据；
两者都不能单独表示正式 Capability Gate 通过。

#### M0：单股研究 MVP

M0 的目标是完成第一次可读的单股研究实验。M0.2 消费 M0.1 的明确产物，
M0.3 记录用户反馈；三者完成后才算 M0 产品闭环成立。

| 顺序 | Child Change | 唯一用户问题 | 用户可见产物 | 明确不做 | 当前状态 |
|---|---|---|---|---|---|
| M0.1 | `m0-frozen-input-growth-diagnostic` | 当前价格隐含了多少未来预期？ | 带来源、报告期、假设快照和状态的 diagnostic JSON/Markdown | 不调用 provider/LLM；不做 Thesis | `merged / mvp_evidence` |
| M0.2 | `m0-strong-agent-thesis-draft` | 如何把诊断和事实转成可读研究判断？ | 单股 Thesis 草稿 JSON/Markdown | 不做 Council；不实现稳定版 `InvestmentThesis`；不做 G3 | `merged / mvp_evidence` |
| M0.3 | `m0-single-stock-user-review` | 用户能否理解并指出结果的问题？ | 人工复核记录、反馈和下一步决策 | 不把单次反馈写成 G2 Gate 证据 | `merged / not_evidence; pending real user review` |

M0.1 已于 2026-08-27 完成工程闭环并生成 MVP evidence：

- merge commit：`8fb8f21`；`main` 与 `origin/main` 已对齐；
- OpenSpec 已归档至 `openspec/changes/archive/2026-08-27-m0-frozen-input-growth-diagnostic/`；
- focused/相关测试：`134 passed`；全量测试：`1334 passed, 1 skipped`；
- `openspec validate --all --strict`：`35 passed`；
- compileall、CLI help、`git diff --check` 已通过；
- 产物为 deterministic growth diagnostic JSON/Markdown，明确标记
  `capability_status=mvp_evidence`、`gate_status=not_passed`。

M0.1 只证明冻结输入到 growth diagnostic 的可复现工程入口，不生成
Investment Thesis，也不代表 M0 产品闭环或 G2 Capability Gate 通过。

M0.2 已于 2026-08-28 完成工程闭环并生成 MVP evidence：

- merge commit：`91a2f296`；`main` 与 `origin/main` 已对齐；
- OpenSpec 已归档至
  `openspec/changes/archive/2026-08-28-m0-strong-agent-thesis-draft/`；
- M0.2 focused 测试：`23 passed`；按既定相关回归范围：`291 passed`；
- merged-main 全量测试：`1357 passed, 1 skipped`；
- `openspec validate --all --strict`：`36 passed, 0 failed`；
- compileall、CLI help、`git diff --check` 已通过；
- 未运行真实 LLM/provider smoke；
- trade-agent 根目录和 `value-screener` 没有可运行的 npm lint script；
  `uzi-skill/package.json` 虽存在，但未定义 scripts。

M0.2 的输入身份、digest 和 failed dossier 质量阻断采用 fail-closed；
diagnostic 为 `not_evaluable`/`failed` 时保留失败元数据并安全降级为
`signal=skip`、`conviction=0`，而不是直接丢弃产物。M0.2 不生成稳定版
InvestmentThesis，不代表 M0 产品闭环或 G2 Capability Gate 通过。
M0.3 的完成条件是保存用户对事实、假设、预期透支和结论可用性的反馈。

M0.3 已于 2026-08-28 完成工程闭环，但尚未产生真实用户填写的复核反馈：

- merge commits：`721a865`（实现）、`39ac693`（OpenSpec archive）；`main` 与
  `origin/main` 已对齐；
- OpenSpec 已归档至
  `openspec/changes/archive/2026-08-28-m0-single-stock-user-review/`；
- M0.3 focused 测试：`26 passed`；最终相关回归：`66 passed`；
- merged-main 全量测试：`1383 passed, 1 skipped`；
- `openspec validate --all --strict`：`36 passed, 0 failed`；
- compileall、CLI help、`git diff --check` 和 fresh child-only review 已通过；
- 未运行真实 provider/LLM；M0.3 只提供离线 review record 入口；
- 由于真实用户反馈尚未填写，当前 `capability_status=not_evidence`，
  `M0 product loop=pending user review`，G2 Capability Gate 仍为
  `not_passed`。

M0.3 的工程入口已完成，但 M0 整体产品闭环仍 pending；下一步应先让用户
基于真实 M0.1/M0.2 artifact 填写 review record，再根据反馈决定是否进入
M1.1，不自动开始新的 M1 child。

#### M1：小样本 G1 MVP

M1 的目标是验证 G1 筛选结果是否符合个人价值风格。现有
`g1-300-sample-validation` 是根目录用户未跟踪 WIP，不能自动视为
已完成或当前 active child；若继续使用，必须先按当前 baseline 单独核验。

| 顺序 | Child Change | 唯一用户问题 | 用户可见产物 | 明确不做 | 初始状态 |
|---|---|---|---|---|---|
| M1.1 | `g1-300-sample-validation` | 如何构造可重复、状态诚实的小样本？ | fixture/sample contract 与选择汇总 | 不调用 provider/LLM；不代表真实 G1 Gate | `existing-wip` |
| M1.2 | `g1-mvp-small-sample-run` | 小样本筛选是否符合用户风格？ | 每只股票的分数、通过/排除原因、质量状态和候选列表 | 不运行全市场；不做 300+ 正式证据 | `pending` |
| M1.3 | `g1-small-sample-user-review` | 用户是否认可候选及排除理由？ | 逐只人工反馈和阈值问题清单 | 不直接修改 G1 Gate；不预防性重写筛选器 | `pending` |

#### M2：强单 Agent G2 MVP

M2 不重复实现 M0.2，而是基于 M0 的单股实验和 M1 的候选输入，
固化强单 Agent 的可重复 baseline，并补齐影响用户判断的最小语义。

| 顺序 | Child Change | 唯一用户问题 | 用户可见产物 | 明确不做 | 初始状态 |
|---|---|---|---|---|---|
| M2.1 | `g2-strong-agent-baseline` | 强单 Agent 在固定输入、模型和预算下是否可重复？ | baseline 配置、运行记录和比较模板 | 不做 Council A/B；不宣称 G2 通过 | `pending` |
| M2.2 | `g2-investment-eligibility-semantics` | 如何表达“公司好但当前价格不一定值得买”？ | `view_signal` 与 `investment_eligibility` 的最小语义输出 | 不做仓位建议；不实现 G3 | `pending` |
| M2.3 | `g2-thesis-review-feedback` | 用户是否认为 Thesis 足以支持下一步研究？ | 多样本人工评审记录和 residual risk | 不做正式盲评 Gate；不扩 Council 角色 | `pending` |

M2.1–M2.3 完成后，才根据真实反馈决定是否进入 M4 的
`G2 4.2/4.3`、prompt distillation、稳定 Thesis interface 或 Council A/B。

#### M3：手工持有纪律 MVP

M3 只验证规则和人工工作流，不建设 `holding/` runtime。

| 顺序 | Child Change | 唯一用户问题 | 用户可见产物 | 明确不做 | 初始状态 |
|---|---|---|---|---|---|
| M3.1 | `g3-manual-holding-discipline-card` | 持有理由、关键变量和 Thesis 破坏条件如何记录？ | Holding Discipline Card Markdown/JSON 模板 | 不实现 HoldingContract runtime | `pending` |
| M3.2 | `g3-manual-scenario-review` | 下跌、估值透支和 Thesis 破坏是否应触发不同动作？ | 场景复核记录和人工 checklist | 不实现状态机；不自动交易 | `pending` |

每个 child 的 proposal/design/tasks 必须进一步写明：输入、允许修改的文件、
依赖、focused tests、实验验证、provider/LLM 调用边界、退出条件和是否产生
正式 Gate 证据。未列入本队列的工作不得以“顺手完善”为由开始。

### M4：基于实验结果的结构化增强

只有 M0-M3 至少产生可读实验结果后，才决定是否推进：

- G2 4.2/4.3 完整质量持久化；
- Prompt 决策框架蒸馏；
- stable InvestmentThesis；
- Council A/B；
- G1 语义和排序修复；
- growth diagnostic 保守下行情景；
- G3 估值透支监控。

每个增强必须对应实验中的具体问题，不做没有失败证据支撑的预防性扩建。

### M5：正式 Capability Gate

#### G1

- 300+ 多行业样本；
- 全市场真实运行；
- 性能/成本/失败分布；
- Top-20 用户复核；
- 规则和排序可解释。

#### G2

- 事实追溯率与高严重度 grounding；
- identity/audit 完整；
- warning/failed/incomplete 下游阻断；
- 8-10 只固定样本；
- strong single-agent vs Council A/B；
- 用户盲评；
- 投资资格和安全边际判断不被观点字段替代。

#### G3

- HoldingContract runtime；
- 五类状态历史回放；
- pre_trade_check；
- 3-5 只持仓至少四周 shadow mode；
- 自动交易次数为 0；
- 用户一分钟内可理解状态和动作边界。

## 6. 当前 OpenSpec 使用规则

文档更新完成后，后续代码仍必须通过独立 child change 推进。

当前建议顺序：

```text
M0.1 冻结输入与 growth diagnostic
→ M0.2 strong-agent Thesis 草稿
→ M0.3 用户人工复核
→ M1 小样本 G1 MVP
→ M2 strong-agent baseline 与最小语义
→ 根据实验结果选择 M4 工程增强或 Council A/B
```

不得因为已有 G2 umbrella tasks 仍有大量 checkbox，就继续无条件补齐所有工程项。

每个 child 必须写清：

- 它解决的用户问题；
- 它产生的可运行产物；
- 它依赖的已有能力；
- 它不解决什么；
- focused test；
- 实验验证；
- 工程闭环；
- 是否影响正式 Capability Gate。

## 7. 当前明确不做

- 不立即重写整个 G1；
- 不立即删除旧函数或历史产物；
- 不把 Council 继续扩展到更多角色；
- 不引入 LangGraph/AgentScope；
- 不建设前端、数据库和任务队列来掩盖核心闭环未跑通；
- 不启动 G3 HoldingContract runtime；
- 不连接券商；
- 不自动下单；
- 不把模型输出写成确定性投资建议；
- 不以绿色测试或 OpenSpec checkbox 代替用户实验。

## 8. 当前唯一下一步

当前下一步是：

```text
完成真实 M0.3 用户人工复核，并依据反馈决定是否进入 M1.1
```

执行窗口必须先读取：

```text
design/capability-gate-and-execution-handoff.md
design/capability-gate-and-execution-handoff-2026-08-27.md
design/three-goal-capability-roadmap.md
design/total-design.md
design/growth-expectation-capitalization-prd-2026-08-04.md
openspec/changes/g2-deep-investment-thesis/tasks.md
```

M0.1 和 M0.2 均已完成工程闭环并生成 MVP evidence。M0.3 已完成工程闭环，
但只负责用户人工复核和反馈记录，不新增研究运行时能力；当前仍等待真实
用户填写。后续如需继续开发，仍须重新核验当前 baseline、根目录用户 WIP、
worktree 状态和 OpenSpec 状态，并继续遵守同一时间只允许一个 active child
和一个 active worktree。

并重新核验：

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git worktree list
openspec list --json
```

在当前 child 完成独立 review、archive、strict validation、合入 main、
push 和 worktree 清理前，不开始第二个 active child。
