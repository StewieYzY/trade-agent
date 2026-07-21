# trade-agent 三大产品能力 Goal 与验证路线

> 状态：已确认
> 确认日期：2026-07-21
> 角色：项目级产品能力与验证顺序的第一参考源
> 相关背景：`total-design.md`、`architecture-decisions.md`
> 下游：G1/G2/G3 umbrella OpenSpec changes 与后续 child changes

## 一、为什么需要这份文档

trade-agent 已经形成 L0-L4 的工程骨架，但此前的实施顺序出现过明显偏移：模块和协议先完成，核心能力的真实验证后补。结果是“系统看起来完整”，但快筛是否真的快且排序正确、深研是否真的产生信息增量、监控是否真的帮助用户拿得住，都没有在进入下一阶段前形成清晰的能力门。

本文件将产品目标重新收敛为三个独立但串行依赖的能力：

```text
G1 快：个人价值风格筛选
    ↓ 能力 Gate 通过
G2 深：可信 Investment Thesis
    ↓ 能力 Gate 通过
G3 拿得住：持仓纪律副驾驶
```

它们不是三个并行开发模块，而是三个逐层成立的产品能力。任何一层未通过，都不靠继续增加上层模块解决。

## 二、共同原则

### 2.1 能力 Gate 优先于工程完备性

每个 Goal 必须先定义：

1. 最终产品价值。
2. 近期可证伪的能力 Gate。
3. 产品层验收证据。
4. 技术层验收证据。
5. 明确的 Non-Goals。

“代码完成”“测试全绿”“OpenSpec tasks 全勾选”不等于能力 Gate 通过。

### 2.2 umbrella spec 与 child change 分离

三个 Goal 各自建立一个 umbrella OpenSpec change：

| Goal | Umbrella change | Capability spec |
|---|---|---|
| G1 快 | `g1-fast-personal-value-screening` | `personal-value-screening` |
| G2 深 | `g2-deep-investment-thesis` | `investment-thesis` |
| G3 拿得住 | `g3-holding-discipline` | `holding-discipline` |

Umbrella change 只承担：

- 能力定义。
- 总体验收 Gate。
- 架构边界。
- 与其他 Goal 的依赖。
- child changes 的拆分原则。

Umbrella change **不直接执行代码实现**。后续每个可在较短周期内独立评审、独立验证、独立归档的小里程碑，建立独立 child change，并在 proposal 中引用对应 umbrella spec。

### 2.3 产品价值优先于技术形态

- G1 的目标不是拥有复杂因子系统，而是快速形成符合用户风格的可信候选池。
- G2 的目标不是拥有 Multi-Agent，而是生成比基线更好的可信 Investment Thesis。
- G3 的目标不是拥有状态机，而是帮助用户区分情绪波动与 Thesis 破坏。

若技术形态不能增加产品价值，应降级到更简单的方案。

## 三、G1 快：个人价值风格筛选

### 3.1 最终产品 Goal

> 每个交易日按用户个人价值投资规则扫描全市场，在可接受时间和成本内，输出一份可解释、可复核、值得进一步研究的候选池。

G1 回答：

- 哪些股票符合我的价值投资风格？
- 为什么进入候选池？
- 为什么其他股票被排除？
- 哪些候选值得投入 G2 深研成本？

“潜力股”在 G1 中不表示承诺未来上涨，而表示：

> 符合用户价值风格、没有明显价值陷阱、值得进一步研究的股票。

### 3.2 近期可验证 Goal

> 修复 L1 排序正确性和分层采集架构，并完成一次真实全市场 L1+L2 运行，证明系统能够稳定、低成本地从约 5000 只股票中形成可用短名单。

### 3.3 产品验收 Gate

| 维度 | 验收标准 |
|---|---|
| 风格一致性 | 候选由版本化的个人价值投资规则产生，不以短期涨跌预测为目标 |
| 候选价值 | 用户人工复核 Top 20，至少 70% 被判断为“值得进一步研究” |
| 可解释性 | 每只候选可说明通过了什么、被哪些风险扣分、为何进入 L2/shortlist |
| 全漏斗可见 | 输出 deep_dive/watch/skip/error 全量结果，不只保留 shortlist |
| 不凑数 | 没有足够候选时允许少于 20 只，不降低门槛凑数 |

### 3.4 技术验收 Gate

| 维度 | 验收标准 |
|---|---|
| 数值正确性 | DCF、ROE、F-Score、PE/PB 等不存在单位或量纲错误 |
| 分层采集 | L1 不采集 `main_business`、`peers`、`research` 等 G2 数据 |
| 规模验证 | 先通过不少于 300 只多行业样本，再完成一次真实全市场运行 |
| 失败隔离 | 单股失败不阻断整批，未处理异常为 0 |
| 数据可用率 | 关键字段可用率不低于 95%，降级与失败单独统计 |
| 日常性能 | warm cache 全市场 L1+L2 在 15 分钟内完成 |
| 成本 | 全市场 L2 实测或等效推算成本不超过 AD-03 的 ¥2 预算 |
| 稳定性 | 相同输入与相同规则版本重复运行，非数据变化导致的 verdict 大幅漂移可诊断 |

### 3.5 产品实现思路

建立版本化 `ScreeningProfile`：

```text
ScreeningProfile
├── hard_exclusions
├── quality_weights
├── valuation_weights
├── anti_trap_rules
├── heat_exclusion_rules
└── l2_deep_dive_threshold
```

每轮产出完整漏斗与排除原因：

```text
全市场
→ basic hard gates
→ financial quality
→ valuation and anti-trap
→ heat exclusion
→ L2 deep_dive/watch/skip
→ shortlist
```

### 3.6 技术实现原则

1. 恢复真正的漏斗式采集，采集量随筛选逐层下降。
2. G1 与 G2 fetcher 注册边界分离，禁止通过默认参数把深研维度带入全市场路径。
3. 简化 DCF 默认移出 G1 排序；如未来保留，必须以独立 child change 验证每股口径、净债务、总股本和假设敏感性。
4. L2 返回全量结果、shortlist、usage 和 failure summary。
5. ticker 使用唯一 canonical form，运行产物携带 `run_id`、规则版本和输入快照。

### 3.7 Non-Goals

- 不预测短期涨跌。
- 不在 G1 做完整 DCF。
- 不对全市场调用重度 LLM。
- 不以固定候选数量作为成功标准。

### 3.8 后续 child changes 拆分建议

1. L1 数值口径与 DCF 纠偏。
2. 分层采集与 G1/G2 fetcher 边界。
3. L2 全量结果契约与失败分布。
4. ticker/run identity 统一。
5. 300+ 多行业规模验证。
6. 全市场实跑与性能/成本 Gate。
7. 用户 Top 20 风格复核与阈值校准。

## 四、G2 深：可信 Investment Thesis

### 4.1 最终产品 Goal

> 针对指定股票，生成一份可验证、可证伪、可持续跟踪的 Investment Thesis，回答“好不好、为什么、什么情况下改变”，并明确事实、假设、分歧和未知项。

Multi-Agent 是候选技术方案，不是产品目标。只有当 Council 相比强单 Agent 产生稳定信息增量时，才保留全天团形态。

### 4.2 近期可验证 Goal

> 在相同模型、相同 dossier 和相同股票样本下，对比“强单 Agent”与“Multi-Agent Council”，证明 Council 是否产生实质信息增量；若不能，则降级为“强单 Agent + 独立 DA/事实检查器”。

### 4.3 样本要求

验证样本应覆盖 8-10 只不同类型股票：

- 稳定白马。
- 高估值成长。
- 周期股。
- 困境反转。
- 治理风险。
- 强预期差。
- 财务数据不足。
- 明显能力圈外。

### 4.4 产品验收 Gate

| 维度 | 验收标准 |
|---|---|
| 信息增量 | 至少 70% 样本中，Council 补充一个强单 Agent 未发现的实质风险、反证或关键变量 |
| 用户盲评 | Council 在至少 60% 样本中优于单 Agent |
| 负增量 | Council 明显劣于单 Agent 的比例不高于 20% |
| 结论可用 | 输出包含核心 Thesis、反证、关键变量、改变条件和待验证事项 |
| 能力圈诚实 | 数据不足或超出能力圈时允许拒绝判断，不强行给 bullish/bearish |

若未通过 Gate，默认产品形态调整为：

```text
强单 Agent + 独立 DA + 事实检查器 + Synthesizer
```

### 4.5 技术验收 Gate

| 维度 | 验收标准 |
|---|---|
| 数据接地 | 高严重度凭空数字为 0 |
| 来源追溯 | 至少 95% 的关键事实和数字可定位到输入来源及报告期 |
| 审计链 | ticker、run_id、prompt version、dossier、debate、最终结论 100% 对应 |
| 串台 | 显性与隐性串台均为 0 |
| R2 价值 | R2 必须新增证据、修订观点或明确说明坚持原因，不接受改写重复 |
| DA 价值 | DA 必须发现遗漏、事实错误或证据不足，不能只写泛化风险 |
| 降级诚实 | 数据不足、agent 失败、DA 跳过和质量 warning 均进入最终状态 |

### 4.6 产品实现思路

人物角色保留为展示层，内部能力按决策框架定义：

| 展示角色 | 核心职责 |
|---|---|
| 巴菲特 | 商业质量、护城河、长期资本回报 |
| 芒格 | 逆向检查、治理风险、激励机制、反证 |
| 段永平 | 生意模式、管理层、消费者价值、能力圈 |
| 冯柳 | 市场预期、赔率、认知差、潜在催化 |

Prompt 蒸馏以以下内容为核心：

```text
决策问题
→ 使用什么证据
→ 如何形成判断
→ 何时拒绝判断
→ 什么证据能改变结论
→ 正面案例
→ 反面案例
→ 常见错误
```

所有 Agent 共享核心事实。角色差异来自分析视角，不通过人为隔离关键事实制造分歧。

### 4.7 稳定输出契约

未来 G2 对外输出统一为 `InvestmentThesis`：

```python
InvestmentThesis = {
    "thesis_id": "...",
    "ticker": "600009.SH",
    "run_id": "...",
    "core_thesis": "...",
    "evidence": [],
    "counter_evidence": [],
    "assumptions": [],
    "risks": [],
    "key_variables": [
        {
            "name": "...",
            "current_value": "...",
            "expected_direction": "...",
            "warning_threshold": "...",
            "thesis_break_threshold": "...",
            "source": "...",
            "as_of": "..."
        }
    ],
    "what_would_change_my_mind": [],
    "dissent": [],
    "pending_verification": [],
    "quality_status": "passed | warning | failed"
}
```

### 4.8 技术实现原则

1. ticker 与 `run_id` 同时进入持久化身份，禁止运行间覆盖审计证据。
2. 只有完整运行且质量门通过的结果才能作为成功缓存。
3. R1 grounding、R2 new evidence、DA fact-check、R4 divergence gate 进入主流程。
4. soft warning 必须持久化，消费者不得看到无标记的污染结果。
5. `evidence_exhausted` 不能只由 LLM 自报，需结合 dossier 覆盖验证。
6. dossier 数据携带来源、报告期、发布时间、新鲜度和降级状态。
7. Prompt、dossier schema、模型配置全部版本化。
8. 建立固定 A/B harness，在相同输入下比较单 Agent 与 Council。

### 4.9 Non-Goals

- 不以“像不像某位投资大师”作为核心验收指标。
- 不预设 Multi-Agent 一定优于单 Agent。
- 不直接决定用户应买卖多少仓位。
- 不通过增加轮数制造表面深度。

### 4.10 后续 child changes 拆分建议

1. ticker/run identity 与审计链修复。
2. incomplete cache 与质量状态契约。
3. dossier 主营/同行/研报数据质量。
4. R1 warning 持久化与全质量门主流程接线。
5. Prompt 决策框架蒸馏。
6. 单 Agent baseline。
7. Council A/B harness。
8. 8-10 只多类型股票实跑与盲评 Gate。
9. `InvestmentThesis` 稳定输出接口。

当前 `f3c-r1-crosstalk-root-cause` 归入本 Goal 的前置诊断里程碑。

## 五、G3 拿得住：持仓纪律副驾驶

### 5.1 最终产品 Goal

> 将通过 G2 Gate 的 Investment Thesis 转译为用户事前确认的持有合同，在价格波动和信息变化时区分“情绪扰动”与“Thesis 破坏”，帮助用户按纪律复核，而不是临场冲动交易。

G3 是从“标的研判工具”扩展到“持仓纪律系统”的明确产品边界变化。系统开始维护用户主动输入的持仓与纪律参数，但仍不承担交易执行。

### 5.2 近期可验证 Goal

> 基于通过 G2 质量门的 Investment Thesis，为 3-5 只真实或模拟持仓生成 HoldingContract，在不执行交易的 shadow mode 中验证状态机和交易前审查是否符合用户纪律。

### 5.3 必须通过的场景

| 场景 | 期望状态 |
|---|---|
| 下跌 20%，Thesis 未破坏 | Yellow：复核，但不能只因价格卖出 |
| 基本面关键条件被证伪 | Red：进入减仓/退出审查 |
| 下跌、估值更低、Thesis 更强、仓位未满 | Blue：进入加仓审查 |
| 单票仓位超过上限 | Rebalance Review |
| 无重大变化 | Green：继续持有 |

### 5.4 产品验收 Gate

1. 每个状态变化都能定位到一条合同规则和一项新证据。
2. 没有证据时不得自动从 Green 跳 Red。
3. 价格下跌不能单独触发卖出建议。
4. Thesis 破坏不能被“长期主义”掩盖。
5. 所有加仓/减仓请求均经过 `pre_trade_check`。
6. 用户能在一分钟内理解当前状态、触发原因、允许动作、禁止动作和待验证事项。
7. 完成历史场景回放后，至少进行四周 shadow mode。

### 5.5 产品实现思路

HoldingContract 采用“草稿 → 用户确认 → 生效”：

```text
InvestmentThesis
    ↓ 生成合同草稿
用户补充仓位纪律
    ↓ 人工确认
Active HoldingContract
```

用户必须补充：

- 成本价。
- 当前仓位。
- 目标仓位。
- 最大仓位。
- 可承受回撤。
- 预期持有期。
- 固定复核周期。
- 卖出冷静期。

候选池与持仓池必须分离：

```text
CandidateWatchlist：值得关注和继续研究的股票
HoldingsPortfolio：用户当前真实持有并需要持续监控的股票
```

持仓股不得因退出本期 G1 候选池而停止监控。

### 5.6 技术实现原则

建立独立 `holding/` 领域，不把 HoldingContract 塞入现有 monitor：

```text
holding/
├── schema.py
├── contract_service.py
├── evaluator.py
├── pre_trade_check.py
├── repository.py
└── history.py
```

数据流：

```text
InvestmentThesis
    ↓ draft_contract
用户仓位参数
    ↓ activate
HoldingContract
    ↓
L4 MonitorSignal
    ↓ evaluate_holding_state
HoldingState
    ↓
pre_trade_check
人工最终决策
```

关键约束：

1. `HoldingsRepository` 是持仓真值源，不依赖 G1 candidates。
2. L4 输出标准化 `MonitorSignal`，不直接决定买卖。
3. 状态机优先使用确定性规则。
4. LLM 只辅助将非结构化事件映射到关键变量，不能直接将状态改成 Red。
5. Thesis、合同和状态变化全部版本化、append-only。
6. 每次状态变化保留触发证据和人工确认记录。
7. 自动下单次数必须为 0。

### 5.7 Non-Goals

- 不连接券商。
- 不自动下单。
- 不计算精确 Kelly 仓位。
- 不做完整组合优化。
- 不把下跌自动解释为机会。
- 不替用户承担最终交易责任。

### 5.8 后续 child changes 拆分建议

1. `InvestmentThesis`→HoldingContract 输入契约。
2. HoldingContract schema 与生命周期。
3. HoldingsRepository 与候选池分离。
4. MonitorSignal 标准化。
5. 确定性状态机。
6. `pre_trade_check`。
7. 历史回放测试。
8. 3-5 只持仓四周 shadow mode。
9. 后续前端状态灯与复核界面。

## 六、三个 Goal 的 Gate 与停止规则

```text
G1 必须证明：
排序正确 + 全市场能跑 + 输出符合个人风格
        ↓
G2 必须证明：
事实可信 + 审计完整 + Council 相对单 Agent 有信息增量
        ↓
G3 必须证明：
可信 Thesis 能转化为可执行、可复核的持仓纪律
```

停止规则：

- G1 未通过：继续修筛选，不扩建更多上层功能。
- G2 未通过：回退强单 Agent + DA，不强留全天团。
- G3 未通过：保留人工 checklist，不建设自动状态判断。

允许并行的只有设计工作：

- G1 实现期间，可以完善 G2/G3 设计。
- G2 Gate 通过前，不实现 G3 运行时代码。
- 前端、自动化部署和外层体验不得优先于当前 Goal 的能力验证。

## 七、OpenSpec 治理规则

每个 child change 必须：

1. 在 proposal 中引用所属 umbrella change。
2. 只覆盖一个可独立验证的小里程碑。
3. 明确它推进了 umbrella Gate 的哪一项指标。
4. 不跨 Goal 偷带实现。
5. 归档时回填实测证据，而不是只证明测试通过。

Umbrella change 的完成条件不是 tasks 被执行，而是所有必要 child changes 归档且能力 Gate 有真实证据通过。
