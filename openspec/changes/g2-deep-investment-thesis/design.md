## Context

G2 对应“深”：针对指定股票生成可信、可证伪、可持续跟踪的 Investment Thesis。当前 L3 已有 research dossier、角色 Agent、四轮辩论、DA、Synthesizer 和质量门等工程结构，但历史产物暴露过 ticker 数据错配、R1 串台、输出同质化、空壳结果和来源不足。工程结构存在不等于 Multi-Agent 已产生产品价值。

本 change 是 umbrella capability charter，不直接修改现有 L3 runtime specs。后续 child changes 将依次修复审计链与数据质量、蒸馏决策框架、接入主流程质量门，并建立相同输入下的强单 Agent 与 Council A/B harness。

G2 正式能力验收依赖 G1 通过。设计工作可并行，但在 G1 未通过时不得用 G2 扩展掩盖候选输入质量问题。G2 未通过信息增量 Gate 时，必须接受更简单的产品形态。

## Goals / Non-Goals

**Goals:**

- 将 L3 的成功标准从“完成结构化辩论”改为“生成可信 Investment Thesis”。
- 定义事实接地、来源追溯、运行审计、串台隔离、角色增量和质量状态 Gate。
- 用公平 A/B 证明 Council 是否优于强单 Agent。
- 定义稳定 `InvestmentThesis` 输出，供 G3 和 L4 消费。
- 将后续修复与验证拆成小型 child changes。

**Non-Goals:**

- 本 umbrella change 不直接修改 prompt、dossier、debate 或 watchlist 代码。
- 不预设 Multi-Agent 必须成为最终产品形态。
- 不以模仿投资大师语言风格作为主要质量指标。
- 不输出用户具体买卖仓位，不替代 G3 持仓纪律与用户最终决策。
- 不通过增加 Agent 数量或辩论轮数制造表面深度。

## Decisions

### D1. 稳定产物是 InvestmentThesis，不是 debate transcript

辩论记录是审计证据，最终对外能力是结构化 Thesis：核心判断、支持与反对证据、假设、风险、关键变量、改变条件、分歧、待验证项和质量状态。下游只依赖该稳定 contract，不依赖某一轮 prompt 文本。

备选方案是继续让 watchlist 直接消费 `SynthesizerOutput`。该方案把编排实现细节泄漏给下游，并难以支持 G3 生命周期，因此不采用。

### D2. 所有路径共享同一事实底座

强单 Agent 与 Council A/B 必须使用相同模型、相同 dossier snapshot、相同工具权限和可比 token budget。所有角色共享核心事实，不通过屏蔽关键事实人为制造分歧。

备选方案是为不同角色提供不同事实子集。该方案会把信息不对称误当作角色洞察，也增加串台与遗漏风险，因此不采用。

### D3. 角色蒸馏以决策框架为内核，人物是展示层

每个角色 prompt 的核心是：决策问题、证据选择、判断规则、拒绝判断条件、改变结论的证据、正反案例和常见错误。人物名称与表达风格只帮助用户理解视角，不作为实质差异来源。

备选方案是继续加强口头禅、语气和人物模仿。它会提高可见差异却不保证分析增量，因此不采用。

### D4. 质量 Gate 进入主流程并持久化

R1 grounding、R2 new evidence/revision、DA fact-check、R4 divergence 与最终 contract validation 必须成为正常运行路径。soft warning、跳轮、数据不足和 Agent 失败都要写入 `quality_status` 与审计记录，下游不得把 warning/failed 结果当作无标记成功。

只有完整运行且质量门通过的结果可以进入成功缓存。incomplete 或 warning 结果可以保留用于诊断，但不能伪装为 clean cache hit。

### D5. 以 canonical ticker + run_id 构建不可混淆审计链

prompt version、dossier version/snapshot、模型配置、每轮消息、quality report 和最终 Thesis 必须绑定同一个 canonical ticker 与 `run_id`。持久化路径不得只靠 ticker + date 导致同日覆盖。

备选方案是依赖目录上下文推断 identity。历史串台已证明隐式上下文不可靠，因此不采用。

### D6. Council 通过相对价值 Gate，而不是绝对“能运行”Gate

固定 8-10 只多类型股票，对强单 Agent 与 Council 进行同输入盲评。Council 必须在至少 70% 样本补充实质新风险、反证或关键变量；用户在至少 60% 样本盲评 Council 更好；Council 明显更差的比例不超过 20%。

若失败，默认收敛为“强单 Agent + 独立 DA/事实检查器 + Synthesizer”。这不是降级事故，而是能力验证得出的产品决策。

### D7. 允许诚实拒答与质量失败

数据不足、能力圈外或关键事实冲突时，系统可以输出 `quality_status=warning|failed`、pending verification 或拒绝方向性结论。强行 bullish/bearish 会制造虚假确定性，因此禁止把“每次都有结论”作为成功率。

### D8. Umbrella 只负责能力宪章

`f3c-r1-crosstalk-root-cause` 作为 G2 的前置诊断 child/precondition 保留，不被本 change 替代。其余里程碑同样独立建 change、独立验证和归档。G2 只有在证据 Gate 通过后才放行 G3 runtime。

## Risks / Trade-offs

- [Risk] 用户盲评样本过少导致比例波动大 → 固定 8-10 只类型分散样本，并保存逐只评分维度与理由，不只保存胜负。
- [Risk] Council 通过增加 token 获得不公平优势 → A/B 固定模型、dossier、工具权限，并记录 token/cost；预算差异必须显式披露。
- [Risk] 95% 来源追溯仍可能遗漏关键错误 → 对高严重度数字采用零容忍，并由独立事实检查/人工抽查补充。
- [Risk] Prompt 蒸馏变成大量人物资料堆积 → 每个新增 prompt 内容必须映射到决策问题、证据或拒答规则。
- [Risk] 质量门过严导致大量 warning/failed → 先暴露真实数据与机制缺口，再由 child change 修复，不以静默降级换取成功率。
- [Trade-off] 回退单 Agent 会减少“天团”产品辨识度 → 换取更低成本、更清晰责任和经验证的实际质量。

## Migration Plan

1. 完成 ticker/run 审计链与 incomplete cache 修复。
2. 提升 dossier 的主营、同行、研报、来源、报告期和新鲜度质量。
3. 将现有质量检查接入主流程并持久化 warning/failed。
4. 以决策框架重写并版本化角色 prompt。
5. 建立强单 Agent baseline 与 Council A/B harness。
6. 对固定 8-10 只样本执行盲评并形成 evidence bundle。
7. 根据 Gate 选择 Council 或强单 Agent + DA 作为默认形态。
8. 稳定并发布 `InvestmentThesis` contract，供 G3/L4 使用。

回退策略：在任一阶段发现串台、审计错配或高严重度编造时，停止发布该运行结果，保留诊断证据并回退到上一个通过质量门的版本；Council A/B 未通过时直接采用强单 Agent baseline。

## Open Questions

- 8-10 只样本的最终 ticker 与类型标签由 A/B child change 冻结。
- “实质信息增量”的评分 rubric 和用户盲评维度需在 harness child change 中预注册。
- `InvestmentThesis` 首版与现有 watchlist JSON 的兼容迁移方式由输出接口 child change 决定。
