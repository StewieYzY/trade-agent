# L3.5 持有纪律层：把“拿得住的勇气”结构化

> 状态：设计探索稿（已纳入 `g3-holding-discipline` umbrella change；运行时代码未开发）
> 创建：2026-07-15
> 定位：承接 L3 深研输出，生成可执行的持有协议；供 L4 监控触发复核，不做自动交易。

## 一、问题定义

“找到好股票”和“找到后拿得住”是两个不同问题。

- **找到好股票**：解决选择问题，核心是判断力。
- **拿得住好股票**：解决持有问题，核心不是单纯勇气，而是能否在波动、质疑、恐惧中仍按事前结构行动。

本系统已有两条主线：

- **快**：L1 + L2 从全市场发现候选。
- **深**：L3 天团判断某只股票在当前节点好不好、为什么、什么条件下会改变。

但 L3 的“好不好”仍是仓位决策的前置判断，不等于持有纪律。L3.5 要补的是：

> 把 L3 的判断转译成一份用户事前认可的“持有合同”，让未来情绪上头的自己有结构可依。

## 二、核心原则

### 2.1 勇气不是性格，是结构

拿得住不应依赖临场硬扛，而应依赖四个事前锚点：

1. **认知锚**：为什么持有？我看到市场没看到什么？
2. **仓位锚**：即使下跌到难受区间，仓位是否仍可承受？
3. **反证锚**：什么证据出现，说明我错了？
4. **节奏锚**：多久复核一次？哪些信号触发复核？

### 2.2 价格波动只触发复核，thesis 破坏才触发行动

L3.5 的核心纪律：

```text
价格波动 ≠ 自动卖出理由
价格波动 → 触发复核
thesis 破坏 → 进入卖出/减仓审查
```

这样可以避免两种常见错误：

- 因短期下跌把长期 thesis 卖掉。
- 因“长期主义”口号掩盖 thesis 已失效。

### 2.3 系统不做自动交易，只做决策前置结构

L3.5 不直接输出“买入/卖出指令”，而是输出：

- 当前持有状态。
- 触发原因。
- 允许动作。
- 禁止动作。
- 需要人工复核的问题清单。

最终交易动作仍由用户结合真实持仓、现金流、组合风险和个人承受能力决策。

## 三、系统定位

```text
L1/L2：找到候选 —— 快
L3：判断标的好不好 —— 深
L3.5：判断该如何被持有 —— 稳
L4：监控变量变化并触发复核 —— 动态
```

L3.5 是 L3 与 L4 之间的纪律层：

- 从 L3 读取 `final_verdict`、`conviction`、`core_thesis`、`risks`、`what_would_change_my_mind`、`key_variables`。
- 结合用户持仓参数生成 `HoldingContract`。
- 由 L4 周期性或事件触发更新状态。
- 在用户想交易前执行 `pre_trade_check`。

## 四、核心产物：HoldingContract

`HoldingContract` 是一份“买入/持有前承诺书”，不是一份预测报告。

建议结构：

```python
HoldingContract = {
    "ticker": "600519.SH",
    "name": "贵州茅台",
    "created_at": "2026-07-15",
    "status": "draft | active | review_required | exit_review | closed",

    "thesis": {
        "core_reason": "...",
        "information_edge": "...",
        "analysis_edge": "...",
        "expected_holding_period": "3-5 years",
        "key_variables": [
            "高端白酒需求是否持续",
            "渠道库存是否恶化",
            "价格体系是否破坏"
        ],
        "what_would_change_my_mind": "..."
    },

    "position_discipline": {
        "cost_basis": 0.0,
        "current_position_pct": 0.0,
        "target_position_pct": 0.0,
        "max_position_pct": 0.0,
        "sleep_at_night_drawdown_pct": 0.0,
        "add_allowed": true,
        "average_down_rules": [
            "thesis 未破坏",
            "估值更有吸引力",
            "仓位未超过 max_position_pct",
            "没有 red trigger"
        ]
    },

    "review_rules": {
        "scheduled_review": "quarterly | semiannual",
        "price_review_thresholds": [-15, -25, -40],
        "fundamental_review_triggers": [],
        "hard_exit_triggers": [],
        "cooldown_hours_before_sell": 24
    },

    "latest_state": {
        "holding_state": "green | yellow | red | blue | rebalance_review",
        "reason": "...",
        "required_action": "...",
        "last_reviewed_at": "2026-07-15"
    }
}
```

## 五、状态机设计

### 5.1 Green：继续持有

触发条件：

- L3 thesis 未破坏。
- L4 未发现关键变量恶化。
- 仓位未超过上限。
- 价格波动仍在合同可承受范围内。

系统动作：

- 输出“继续持有”。
- 不建议交易。
- 下一次按固定节奏复核。

### 5.2 Yellow：复核但不交易

触发条件：

- 股价触及复核阈值，如 -15%、-25%。
- 估值大幅变化。
- L4 发现轻微信号，但尚未构成 thesis 破坏。
- 数据过期或关键数据缺失。

系统动作：

- 要求重跑 L3 或人工复核。
- 默认禁止因价格单独卖出。
- 记录“复核中，不得冲动交易”。

### 5.3 Red：进入卖出/减仓审查

触发条件：

- L3 的 `what_would_change_my_mind` 被命中。
- 核心财务质量恶化。
- 现金流与利润显著背离。
- 治理/质押/审计风险恶化。
- 主营逻辑、护城河、管理层信任基础被破坏。

系统动作：

- 进入 `exit_review`。
- 要求回答“哪条 thesis 被证伪”。
- 允许讨论减仓/清仓，但仍不自动执行。

### 5.4 Blue：可加仓审查

触发条件：

- 股价下跌或估值更有吸引力。
- 原 thesis 未破坏，甚至更强。
- 仓位低于目标仓位或最大仓位。
- 没有 red trigger。

系统动作：

- 输出“可进入加仓审查”。
- 要求确认现金流、组合集中度、下跌承受力。
- 不直接输出“加仓”。

### 5.5 Rebalance Review：再平衡审查

触发条件：

- 因上涨导致仓位超过 `max_position_pct`。
- 单一行业或单一标的集中度超出用户纪律。

系统动作：

- 进入再平衡审查。
- 减仓理由可以是组合风险，不一定是看空公司。

## 六、核心算法

### 6.1 持有状态评估

```python
def evaluate_holding_state(contract, latest_features, l4_signals, current_price):
    if hard_exit_trigger_hit(contract, latest_features, l4_signals):
        return "red"

    if thesis_variable_changed(contract, latest_features, l4_signals):
        return "yellow"

    if price_drawdown_hit(contract, current_price) and fundamentals_unchanged(latest_features):
        return "yellow"

    if (
        price_down(current_price, contract)
        and thesis_intact(contract, latest_features, l4_signals)
        and valuation_more_attractive(latest_features)
        and position_below_cap(contract)
    ):
        return "blue"

    if position_above_max(contract):
        return "rebalance_review"

    return "green"
```

### 6.2 卖出前审查

```python
def pre_trade_check(contract, intended_action, reason):
    if intended_action in ["sell", "trim"]:
        if reason_is_only_price_or_fear(reason):
            return {
                "allowed": False,
                "required_action": "cooldown_and_review",
                "message": "价格下跌或恐惧不能单独作为卖出理由，请复核 thesis 是否破坏。"
            }

        if thesis_break_evidence_present(reason, contract):
            return {
                "allowed": True,
                "required_action": "exit_review",
                "message": "存在 thesis 破坏证据，可进入卖出/减仓审查。"
            }

    if intended_action == "add":
        if not thesis_intact_for_add(contract):
            return {
                "allowed": False,
                "required_action": "rerun_l3",
                "message": "加仓前必须确认 thesis 未破坏。"
            }

        if position_above_cap_after_add(contract):
            return {
                "allowed": False,
                "required_action": "position_review",
                "message": "加仓后会超过最大仓位上限。"
            }

    return {
        "allowed": True,
        "required_action": "manual_confirm",
        "message": "通过纪律审查，但仍需用户最终确认。"
    }
```

## 七、与现有系统的衔接

### 7.1 L3 → L3.5

L3 负责输出标的判断：

- `final_verdict`
- `conviction`
- `consensus_summary`
- `dissent_points`
- `key_variables`
- `what_would_change_my_mind`

L3.5 负责把这些字段转译为持有合同：

- `core_reason`
- `key_variables`
- `fundamental_review_triggers`
- `hard_exit_triggers`
- `scheduled_review`

### 7.2 f3 research dossier → L3.5

f3 引入的结构化研究档案会增强 L3.5 的质量：

- 主营构成：判断 thesis 是否仍成立。
- 竞品对比：判断护城河是否削弱。
- 研报共识：判断市场预期是否过热或过冷。
- 资本开支代理：判断长期再投资与现金流压力。

L3.5 不直接消费所有原始数据，而是消费 L3 结论 + L4 最新信号；必要时可读取 f3 dossier 做复核解释。

### 7.3 L4 → L3.5

L4 不应只触发“重跑 L3”，还应触发持有状态更新：

```text
L4 signals → evaluate_holding_state → 更新 HoldingContract.latest_state
```

示例：

- `pledge_ratio_spike` → yellow 或 red，取决于严重程度。
- `financials_floor_missing` → yellow，要求补数据后复核。
- `thesis_key_variable_changed` → red，进入 exit review。
- `valuation_lower_but_thesis_intact` → blue，进入加仓审查。

## 八、MVP 范围

### 8.1 做

1. 新增 `holding_contract` 文件结构。
2. L3 跑完后生成 `HoldingContract` 草稿。
3. 用户手动补充：
   - 成本价
   - 当前仓位
   - 目标仓位
   - 最大仓位
   - 可承受回撤
   - 预期持有期
4. L4 每周或事件触发时更新状态。
5. 新增卖出/加仓前 checklist。
6. 前端展示持有状态灯和复核问题。

### 8.2 不做

1. 不接券商交易接口。
2. 不自动下单。
3. 不做完整组合优化。
4. 不计算精确 Kelly 仓位。
5. 不把价格下跌自动解释为机会。

## 九、验收标准

### 9.1 跌价但 thesis 未破坏

输入：

- 当前价格较成本价下跌 20%。
- L4 未发现基本面恶化。
- L3 key variables 未触发。

期望：

```text
holding_state = yellow
required_action = rerun_l3_or_manual_review
message = 价格触发复核，但不得因价格单独卖出
```

### 9.2 thesis 破坏

输入：

- 现金流恶化。
- 治理风险恶化。
- 命中 `what_would_change_my_mind` 中的关键条件。

期望：

```text
holding_state = red
required_action = exit_review
message = thesis 破坏，允许进入卖出/减仓审查
```

### 9.3 下跌但更便宜且 thesis 更强

输入：

- 当前价格下跌。
- 估值分位下降。
- 主营/现金流/护城河未恶化。
- 当前仓位低于 `max_position_pct`。

期望：

```text
holding_state = blue
required_action = add_review
message = 可进入加仓审查，但需确认仓位纪律
```

### 9.4 仓位超限

输入：

- 因上涨导致单票仓位超过 `max_position_pct`。
- thesis 未破坏。

期望：

```text
holding_state = rebalance_review
required_action = position_review
message = 可因组合风险再平衡，不代表看空公司
```

## 十、OpenSpec 归属与后续拆分

本探索稿已纳入 `g3-holding-discipline` umbrella change。该 umbrella 只定义能力边界和总体验收 Gate，不直接执行运行时代码；后续按以下 child changes 逐步推进：

1. `InvestmentThesis` → HoldingContract 输入契约。
2. HoldingContract schema 与生命周期。
3. HoldingsRepository 与候选池分离。
4. MonitorSignal 标准化。
5. 确定性状态机。
6. `pre_trade_check`。
7. 历史回放测试。
8. 3-5 只持仓至少四周 shadow mode。
9. 后续前端状态灯与复核界面。

实施依赖遵循 AD-10：

1. G2 先证明 Investment Thesis 可信。
2. G2 Gate 通过后，才实现 G3 运行时代码。
3. L4 负责提供信号，不越权直接决定持仓状态或交易动作。

原因：

- 没有可信 Investment Thesis，HoldingContract 只会把空泛结论结构化。
- 没有独立持仓纪律层，L4 信号只能提示“重跑 L3”，不能帮助用户抵抗情绪化交易。

## 十一、设计边界

L3.5 的价值不是让系统更像“交易机器人”，而是让系统更像“纪律化投资副驾驶”。

它要做的是：

```text
把临场勇气，提前写成结构；
把冲动交易，拦截成复核任务；
把长期主义，约束在可证伪的 thesis 上。
```
