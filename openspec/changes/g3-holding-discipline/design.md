## Context

G3 对应“拿得住”：把已经通过 G2 质量门的 Investment Thesis 转译为用户事前确认的持有纪律，在价格波动和新信息出现时区分情绪扰动、待复核信号、Thesis 破坏、加仓审查和组合再平衡。

当前项目没有真实持仓真值源、HoldingContract 生命周期、标准化 MonitorSignal、持仓状态机或交易前纪律检查。现有 watchlist/monitor 主要跟踪候选和触发重评估，不能代表用户真实持仓，也不能约束用户在恐惧或兴奋时的临场决策。

G3 是显式产品边界扩展：系统会保存用户主动输入的成本、仓位、承受力和复核规则，但仍不连接券商、不自动下单、不替用户承担最终交易责任。本 change 是 umbrella capability charter；按 AD-10，G2 Gate 通过前只允许继续设计，不允许实现 G3 runtime。

## Goals / Non-Goals

**Goals:**

- 定义从 InvestmentThesis 到用户确认 HoldingContract 的领域边界与生命周期。
- 将候选池与真实/模拟持仓池分离。
- 建立基于合同规则与证据的确定性 Green/Yellow/Red/Blue/Rebalance Review 状态机。
- 所有加仓、减仓和卖出意图进入 `pre_trade_check`，形成允许、禁止和待复核动作。
- 通过历史场景回放与 3-5 只持仓至少四周 shadow mode 验证能力。

**Non-Goals:**

- 本 umbrella change 不直接实现 `holding/` 运行时代码。
- 不连接券商、不自动下单、不自动修改真实仓位。
- 不计算精确 Kelly 仓位，不做完整组合优化。
- 不把价格下跌自动解释为卖出理由或加仓机会。
- 不用 LLM 直接决定 Red 状态或交易动作。

## Decisions

### D1. HoldingContract 是用户确认的事前承诺，不是模型即时建议

系统从 passed InvestmentThesis 生成合同草稿，用户补充成本价、当前/目标/最大仓位、可承受回撤、预期持有期、复核周期和卖出冷静期后显式确认，合同才可生效。模型不得代填高风险仓位边界并自动激活。

备选方案是每次监控时让 LLM即时生成建议。该方案容易受当下价格与情绪叙事影响，也无法审计用户事前纪律，因此不采用。

### D2. 独立 holding 领域与 HoldingsRepository

后续实现建立独立 `value-screener/holding/` 领域，包含 schema、contract service、repository、evaluator、pre-trade check 和 append-only history。`HoldingsRepository` 是持仓真值源，不依赖 CandidateWatchlist。

备选方案是把持仓字段塞入现有 watchlist JSON。候选退出筛选时会造成持仓监控丢失，且候选状态与真实仓位生命周期不同，因此不采用。

### D3. L4 只产生标准化 MonitorSignal

L4 将价格、估值、财务、治理、数据缺失和 Thesis 关键变量变化转换为带来源、时间、严重度和 evidence reference 的 `MonitorSignal`。L4 不直接决定买卖，也不直接把合同状态改成 Red。

备选方案是让每个 monitor alert 自己携带动作建议。该方案会产生分散、冲突且不可统一审计的决策逻辑，因此不采用。

### D4. 状态机以确定性规则和证据优先

状态计算顺序优先检查 hard thesis-break trigger，其次检查待复核、可加仓条件、仓位超限，最后为 Green。每次状态变化必须映射到合同版本中的具体规则与新证据。LLM 只可辅助把非结构化事件映射为候选变量，最终规则命中必须由确定性 evaluator 验证。

备选方案是让 LLM直接输出状态。该方案难以复现、测试和解释，也可能把新闻措辞或价格波动误判为 Thesis 破坏，因此不采用。

### D5. 价格只触发复核，不单独授权卖出

价格跌幅命中合同阈值时进入 Yellow；只有 Thesis break evidence 或组合风险规则才允许进入卖出/减仓审查。价格下降、估值更有吸引力、Thesis 完整且仓位未满时可以进入 Blue，但仍需加仓审查。

该设计同时阻止“跌了就卖”和“跌了就机械补仓”两种对称错误。

### D6. `pre_trade_check` 是所有仓位变化意图的必经门

add/sell/trim 请求必须提供 action、理由、目标变化和相关证据。检查结果只输出 `allowed`、`required_action`、解释、违反的合同规则和人工确认要求，不执行交易。卖出理由仅为价格或恐惧时必须拦截；加仓后超上限或 Thesis 未复核时必须拦截。

### D7. 合同、Thesis 与状态历史版本化且 append-only

合同激活后的规则变化生成新版本，旧版本保留。每次状态评估保存 Thesis version、contract version、signal ids、前后状态、规则命中、时间和人工确认。这样可以复盘“当时依据什么作出何种纪律判断”。

### D8. 先历史回放，再 shadow mode

实现后先用确定性场景覆盖 Green、Yellow、Red、Blue 和 Rebalance Review，再选择 3-5 只真实或模拟持仓运行至少四周 shadow mode。shadow mode 记录系统本会如何提示，但不执行交易；用户评估是否能在一分钟内理解状态和动作边界。

如果状态机 Gate 未通过，保留人工 checklist，不继续自动化状态判断。

### D9. Umbrella 与 child change 分离

领域模型、repository、MonitorSignal、状态机、`pre_trade_check`、历史回放、shadow mode 和前端分别建立 child changes。每个 child change 只能在依赖具备时推进，不跨 Goal 偷带 G2 修复或交易执行。

## Risks / Trade-offs

- [Risk] 用户输入仓位或承受力错误导致错误状态 → 对必填字段、数值范围和交叉约束做校验，激活前展示完整摘要并要求确认。
- [Risk] 合同规则过于僵硬，无法覆盖现实变化 → 允许版本化修订和人工 override，但必须记录理由，不静默改写历史。
- [Risk] 非结构化事件映射错误触发 Red → LLM 只能产生候选映射；Red 必须由规则、结构化证据和必要人工确认共同成立。
- [Risk] 四周 shadow mode 样本事件太少 → 同时要求历史场景回放覆盖五类状态，shadow mode 验证真实工作流与可理解性。
- [Risk] 用户把 `allowed=true` 误解为交易建议 → UI/CLI 必须显示“纪律检查通过，不等于建议交易，仍需人工最终确认”。
- [Trade-off] 不自动交易会减少闭环自动化程度 → 保留用户最终控制，符合本产品的风险边界。

## Migration Plan

1. G2 发布稳定且 passed 的 InvestmentThesis contract。
2. 建立 HoldingContract schema、草稿/激活/修订/关闭生命周期和输入校验。
3. 建立独立 HoldingsRepository 与 append-only history。
4. 将 L4 输出规范化为 MonitorSignal。
5. 实现并测试确定性状态机与 evidence mapping。
6. 实现 `pre_trade_check`，覆盖 add/sell/trim。
7. 完成历史场景回放。
8. 选择 3-5 只持仓运行至少四周 shadow mode。
9. Gate 通过后再建设前端状态灯与复核界面。

回退策略：任一 evaluator 版本产生不可解释或错误状态时，停止自动状态更新，回退为上一版本或人工 checklist；所有已产生历史记录保持不可变。

## Open Questions

- 首版持仓数据采用本地 JSON、SQLite 或其他现有依赖内方案，由 repository child change 决定。
- 用户人工 override 的最小理由与二次确认流程，由生命周期 child change 设计。
- shadow mode 的 3-5 只标的、真实/模拟比例和周度复核节奏，在验证 child change 中冻结。
