# TradingAgents-CN 与 trade-agent「快、深、拿得住」能力对照报告

> 文档类型：永久外部借鉴与能力边界基线  
> 分析日期：2026-08-03  
> 外部项目：`hsliuping/TradingAgents-CN`  
> 外部核验基线：`main@74783e8817d6cf6de29867880631cc555153f36b`（commit date: 2026-07-24，README 标记 v1.1.0）  
> 本项目核验基线：`trade-agent/main@dd52d11`  
> 上位设计：`three-goal-capability-roadmap.md`、`total-design.md`、`architecture-decisions.md`  
> 目的：判断 TradingAgents-CN 对本项目 G1「快」、G2「深」、G3「拿得住」有哪些值得借鉴、哪些可以复用、哪些不应照搬，以及哪些方面本项目已有更好的产品观点。

---

## 0. 使用方式

本文是一份长期判断基线，不是 TradingAgents-CN 的完整代码审计，也不是新的 implementation plan。

后续若考虑：

- 引入新的数据同步架构；
- 建设前端、任务队列、分析历史或报告导出；
- 扩展新闻与事件数据；
- 增加模拟持仓；
- 调整 G2 Multi-Agent 形态；
- 直接复用 TradingAgents-CN 代码；

应先回看本文，避免把“平台功能完整”“Multi-Agent 流程可运行”误写成 G1/G2/G3 Capability Gate 已成立。

本文的核心原则是：

```text
借鉴产品工程成熟度
≠
接受其投资结论生成哲学
```

---

## 1. 证据范围与限制

### 1.1 已核验内容

本次判断基于 TradingAgents-CN 对应 commit 的以下当前源码与产物：

- 根 README、版本与许可证文件；
- `tradingagents/graph/` 的 LangGraph 编排、条件路由、信号处理与反思机制；
- `tradingagents/agents/` 的分析师、多空研究员、交易员和风险辩论角色；
- `tradingagents/dataflows/` 的多市场、多 provider、缓存和新闻链路；
- `app/services/`、`app/routers/`、`app/models/` 的筛选、分析任务、数据同步和模拟交易；
- `frontend/src/` 的筛选、分析、历史、配置、任务和模拟交易页面；
- 仓库内样例分析报告；
- 当前许可证边界。

### 1.2 未做的验证

本次未执行：

- 真实 LLM 全流程调用；
- 真实 MongoDB/Redis/Docker 部署；
- TradingAgents-CN 全量测试；
- 真实 A 股多样本结果质量评估；
- TradingAgents-CN 与 trade-agent 的同模型、同股票、同数据、同预算 A/B；
- 对其尚未开源 v2/v3 的能力判断。

因此，本文可以判断：

- 当前开源代码有哪些能力和设计倾向；
- 当前输出契约是否符合本项目目标；
- 哪些工程模式值得借鉴；
- 哪些观点与本项目冲突。

本文不能证明：

- TradingAgents-CN 当前线上实例的实际稳定性；
- 其 Multi-Agent 一定没有信息增量；
- trade-agent 当前运行结果已经优于 TradingAgents-CN；
- README 中未出现在当前开源代码里的未来版本能力。

---

## 2. 核心结论

TradingAgents-CN 是一个比当前 trade-agent 产品化程度高得多的股票分析平台，但它不是一个已经证明 G1「快」、G2「深」、G3「拿得住」能力成立的投资决策系统。

其核心优势是：

1. 多数据源同步与本地数据库基础设施；
2. FastAPI + Vue 的完整产品壳；
3. 任务队列、实时进度、历史记录和报告导出；
4. 多模型、多 provider 和快慢模型配置；
5. 单股分析、多空辩论、风险辩论的可运行工作流；
6. 模拟账户、持仓和交易记录。

其核心局限是：

1. 筛选更接近通用条件查询，不是个人价值风格的全市场漏斗；
2. 深研最终目标仍是买入/持有/卖出和目标价，而非可信、可证伪的 `InvestmentThesis`；
3. Prompt 强制给结论和具体目标价，不充分允许数据不足、能力圈外或拒绝判断；
4. 运行失败可能退化成默认“持有”，混淆系统失败与投资意见；
5. Multi-Agent 主要通过立场角色制造分歧，缺少信息增量 A/B 和系统性质量 Gate；
6. 模拟交易解决执行记录，不等于持有纪律。

对本项目最准确的判断是：

> TradingAgents-CN 更像一个已经成形的“股票分析工作台”；trade-agent 的目标是一个“全市场价值发现 → 可信 Investment Thesis → 持有纪律”的串行能力系统。

两者表面都使用股票数据和 Multi-Agent，但产品目标并不相同。

---

## 3. 总体能力对照

| 维度 | TradingAgents-CN 当前特点 | trade-agent 当前特点 | 判断 |
|---|---|---|---|
| 产品完整度 | 前后端、认证、队列、配置、数据同步、报告、模拟交易齐全 | CLI 与研究骨架为主，前端未落地 | TradingAgents-CN 明显领先 |
| G1 快筛 | 有数据库筛选和筛选页面，偏通用条件查询 | 有价值/质量/安全边际/反陷阱/热度/L2 成本闸门设计 | 我方目标更准确，对方当前可用性更高 |
| G2 深研 | 分析师→多空辩论→交易员→风险辩论，流程完整 | dossier、grounding、分歧、DA、结构化 AgentOutput | 我方可信度方法更强，对方运行和产品化更成熟 |
| G3 拿得住 | 有模拟账户、持仓和交易历史 | 有 HoldingContract 和 thesis-break 设计 | 我方观点更深入，对方已有更多 runtime |
| 数据工程 | 多 provider、多市场、数据库同步与管理成熟 | canonical snapshot、缺失状态和 provenance 更严格 | 双方优势不同 |
| 失败语义 | 重可用性和 fallback，部分路径失败默认持有 | 强调 failed/degraded/not_evaluable 与 fail-closed | 我方更适合高风险决策 |
| Multi-Agent 判断 | 默认保留完整 Multi-Agent 流程 | 先证明 Council 相比强单 Agent 有增量 | 我方更可证伪 |
| 许可证 | 核心开源，`app/` 和 `frontend/` 为专有组件 | 自有项目 | 对方产品壳不可直接复制 |

---

## 4. G1「快」：个人价值风格筛选

### 4.1 TradingAgents-CN 已有能力

TradingAgents-CN 已有相对完整的筛选产品：

- 从 MongoDB 股票基础数据与行情视图筛选；
- 支持行业、地区、市场、市值、PE、PB、ROE、换手率、量比；
- 支持部分均线、RSI、KDJ、MACD 等技术条件；
- 基础字段可直接通过数据库完成查询与排序；
- 筛选结果可进入收藏、详情页和单股/批量分析；
- 有数据源优先级、同步任务、初始化任务和运维页面。

这种架构解决的是：

> 用户如何低延迟地查询一个已同步好的股票数据库。

这是一个真实且重要的产品能力，尤其值得 G1 后续工程化借鉴。

### 4.2 它不等于本项目 G1

本项目 G1 的目标不是“提供筛选条件页面”，而是：

> 每个交易日按版本化的个人价值投资规则扫描全市场，低成本输出一份可解释、可复核、值得进一步研究的候选池。

TradingAgents-CN 当前筛选与此存在以下差距。

#### 4.2.1 缺少个人价值风格的稳定决策对象

未看到与 `ScreeningProfile` 等价的稳定结构来统一管理：

- hard exclusions；
- quality weights；
- valuation weights；
- anti-trap rules；
- heat exclusion rules；
- L2 deep-dive threshold；
- profile version。

用户条件查询可以筛出“PE 小于 20、ROE 大于 10%”，但这还没有形成可版本化、可复核、可校准的个人投资风格。

#### 4.2.2 不是三层成本漏斗

当前主筛选更接近：

```text
数据库 universe
→ 条件查询
→ 排序与分页
```

而非：

```text
全市场快照
→ hard gates
→ 财务质量与估值
→ anti-trap
→ heat exclusion
→ L2 全量 verdict
→ shortlist
```

其传统技术指标路径还会先把股票池截断为前 120 只以控制时长，因此不能把该路径理解成完整全市场技术筛选能力。

#### 4.2.3 因子深度有限

当前数据库筛选的主要决策字段是：

- PE/PB/ROE；
- 总市值与流通市值；
- 换手率、量比；
- 行情与技术指标。

未形成与本项目对应的：

- Piotroski F-Score；
- 多年 ROE 与经营现金流稳定性；
- 行业估值锚；
- 质押、审计、商誉等反陷阱合同；
- 估值字段 degraded 状态；
- 缺失数据对 ranking 的影响语义；
- 全量 deep_dive/watch/skip/error 分布。

#### 4.2.4 筛选与深研之间缺少明确成本 Gate

TradingAgents-CN 支持批量分析，但当前请求模型最多接收 10 只股票，更像：

> 同时研究用户已选择的几个标的。

这不是本项目的：

```text
约 5000 → 约 200 → 约 20 → 少量深研
```

### 4.3 G1 结论

TradingAgents-CN 在“快筛产品体验”和“本地数据库查询”上领先；trade-agent 在“个人价值风格、漏斗、成本 Gate、反陷阱和缺失语义”上方向更准确。

但当前双方都不能夸大：

- TradingAgents-CN 的通用筛选不等于价值风格 Gate；
- trade-agent 当前仍在筛选前调用一次 `BatchFetcher.fetch_all()`，不是真正逐层下降的 fetch 调用；
- trade-agent G1-4 真实数据源 Gate 尚未通过；
- trade-agent 尚无可信的全市场性能、成本、行业覆盖和 Top 20 人工复核证据。

因此：

> 当前只能说 trade-agent 的 G1 方法论更符合项目目标，不能说其已实现能力优于 TradingAgents-CN。

---

## 5. G2「深」：可信 Investment Thesis

### 5.1 TradingAgents-CN 的分析链

其主流程是：

```text
市场/技术分析
→ 基本面分析
→ 新闻分析
→ 社交媒体情绪分析
→ Bull / Bear 多轮辩论
→ Research Manager 形成投资计划
→ Trader 给出交易建议和目标价
→ 激进 / 中性 / 保守风险辩论
→ Risk Manager 给最终交易建议
→ SignalProcessor 提取结构化信号
```

这条链路的优点是：

- 运行流程清晰；
- 研究上下文覆盖市场、基本面、新闻和情绪；
- 多空与风险讨论分成两个阶段；
- 支持选择分析师；
- 支持多档研究深度；
- 支持快速模型和深度模型；
- 有节点级进度、耗时、日志和历史产物；
- 能被 Web 任务系统直接消费。

### 5.2 与可信 Thesis 的差距

#### 5.2.1 最终对象仍是交易信号

TradingAgents-CN 的稳定产品输出主要围绕：

```text
recommendation
target_price
confidence
risk_score / risk_level
reasoning
```

而 G2 需要的稳定输出是：

```text
InvestmentThesis
├── core_thesis
├── evidence
├── counter_evidence
├── assumptions
├── unknowns
├── risks
├── key_variables
├── what_would_change_my_mind
├── source_refs
└── quality_status
```

前者回答“现在给什么建议”，后者回答：

- 为什么成立；
- 哪些是事实，哪些是假设；
- 最大反证是什么；
- 什么情况下应改变；
- 后续应该监控什么。

对于长期价值投资，后者更适合作为 G3 输入。

#### 5.2.2 强制给结论和目标价

TradingAgents-CN 多处 Prompt 强制要求：

- 必须给出买入/持有/卖出；
- 必须给具体目标价格；
- 不允许目标价为空；
- 不允许回答“无法确定”或“需要更多信息”。

这与 G2 的能力圈诚实原则冲突。

可信深研必须允许：

```text
out_of_circle
insufficient_data
not_evaluable
manual_review_required
```

强制精确结论会诱导模型在证据不足时补齐一个表面完整的答案。

#### 5.2.3 运行失败可能被写成“持有”

TradingAgents-CN 风险经理在多次 LLM 调用失败后，会生成默认“持有”建议；SignalProcessor 遇到空输入时也会返回默认持有结果。

这种设计提高了产品连续性，但在投资语义上不成立：

```text
系统失败
≠
持有 Thesis 成立
```

更可信的结果应是：

```text
quality_status = failed
decision_status = unavailable
manual_review_required = true
```

而不是把运行错误转换为仓位意见。

#### 5.2.4 Multi-Agent 的差异主要来自立场角色

其核心辩论角色包括：

- Bull：建立看涨论证；
- Bear：建立看跌论证；
- Risky：倡导高风险高回报；
- Safe：强调保护资产；
- Neutral：寻求平衡。

这种结构能产生可读的辩论，但角色差异本身不等于信息增量。

当前开源代码未形成与本项目等价的：

- R1 隔离与串台检测；
- key metric 数字 grounding；
- R2 新证据检查；
- DA 事实回查；
- dossier 角色信息分发；
- Council 与强单 Agent 的受控 A/B；
- Council 无增量时回退；
- `quality_status` 对下游的 fail-closed 约束。

因此，其代码证明的是：

> Multi-Agent 流程可以被编排并生成报告。

但不能仅据此证明：

> Multi-Agent 比强单 Agent 形成了更可信的 Investment Thesis。

### 5.3 trade-agent 的优势与现实差距

trade-agent 已有或已确定的更强方向包括：

- 结构化 `AgentOutput`；
- `what_would_change_my_mind` 必填；
- research dossier；
- 公司事实与市场共识分区；
- agent-specific context；
- 数字 grounding；
- citation divergence；
- R2 新证据语义；
- DA 事实回查；
- 分歧报告；
- Council 与强单 Agent 的同模型 A/B；
- Council 无增量时回退到更简单形态。

但当前 main 的真实状态仍然是：

- G2 capability 未通过；
- 当前 watchlist 中仍存在 `single_agent`、`quality_status=failed` 产物；
- `conviction`、`consensus_summary`、`dissent_points` 等关键字段仍可能为空；
- `InvestmentThesis` 尚未成为当前 main 的稳定 runtime 输出；
- f3c 受控真实模型实验尚未收口；
- 当前部分 `quality_warnings` 产物存在字符串被拆成单字符的问题。

因此，G2 的准确判断是：

> trade-agent 对“什么才算深”定义得更好；TradingAgents-CN 对“如何把深研流程做成可操作产品”实现得更完整。两者都还缺少足够的真实 A/B 证据证明研究质量。

---

## 6. G3「拿得住」：持仓纪律副驾驶

### 6.1 TradingAgents-CN 已有的相关能力

TradingAgents-CN 已实现：

- 模拟账户；
- 多货币现金；
- 持仓数量、成本和盈亏；
- 市价单；
- A 股 T+1；
- 手续费和市场规则；
- 分析报告与模拟订单关联；
- 分析历史；
- ChromaDB 相似场景记忆；
- 基于收益结果的反思接口。

这些是有价值的产品基础设施。

### 6.2 为什么不等于“拿得住”

#### 6.2.1 相似记忆不是持有合同

其 memory 主要保存历史场景和推荐，通过向量相似度提供过去经验。

它回答：

> 过去类似场景中系统有什么经验？

而 `HoldingContract` 要回答：

- 为什么持有？
- 当前信息优势是什么？
- 最大可承受回撤是多少？
- 什么证据证明原 Thesis 已破坏？
- 什么条件下允许加仓？
- 什么条件下只能复核，不能交易？

两者不是同一个能力。

#### 6.2.2 反思主链未形成自动闭环

当前 `reflect_and_remember(returns_losses)` 主要以可选接口存在，主示例调用仍为注释状态，未看到模拟交易结算自动驱动研究反思和持有合同更新的完整产品闭环。

同时，单纯以最终收益判断原决策正确或错误存在结果偏差：

- 正确决策可能短期亏损；
- 错误决策也可能短期赚钱；
- 股价表现不能直接证明原 Thesis 是否成立。

#### 6.2.3 模拟账户记录行为，不约束行为

模拟交易解决的是：

- 买了多少；
- 多少钱成交；
- 当前盈亏；
- 能否卖出。

它没有建立：

- 事前 Thesis；
- 用户确认的关键变量；
- `what_would_change_my_mind`；
- price drawdown 与 thesis break 的区分；
- 冷静期；
- 加仓条件；
- 最大仓位与组合集中度；
- 交易前审查。

### 6.3 G3 结论

trade-agent 的 `HoldingContract`、green/yellow/red/blue/rebalance review、价格只触发复核、Thesis 破坏才触发退出审查等原则，更接近“拿得住”的第一性问题。

但必须保留事实边界：

- TradingAgents-CN 已有模拟交易 runtime；
- trade-agent 当前只有 G3 设计和 umbrella change；
- 没有通过 G2 Gate 的 `InvestmentThesis`，G3 runtime 仍应锁定。

因此：

> trade-agent 在 G3 的观点和产品定义上领先，但尚未形成实际运行能力。

---

## 7. 最值得借鉴的能力

### 7.1 多数据源同步与本地数据库

这是 TradingAgents-CN 最值得深入研究的部分。

可借鉴的模式：

- provider 配置中心；
- 数据源启停与优先级；
- 初始化与定期同步任务；
- 股票基础数据、行情、财务、新闻分层存储；
- MongoDB 视图与索引；
- 同步进度与失败可见；
- 本地查询优先，外部接口承担同步角色；
- 数据运维页面。

对 G1 的长期启示是：

> 全市场日常快筛的最佳形态可能不是每次逐股调用 AkShare，而是先建立可信的本地 canonical snapshot，再对本地快照执行筛选。

但不能照搬其所有 fallback 语义。本项目仍应坚持：

```text
provider adapter
→ normalized raw response
→ mapping/unit/date normalization
→ canonical snapshot
→ provenance/status
→ cache
→ G1/G2/G3
```

尤其不能因为数据库中已有非空值，就默认其来源、报告期、单位和完整性已满足 Gate。

### 7.2 任务队列与节点级进度

G2 运行时间长、成本高，用户必须知道：

- 当前运行到哪个阶段；
- 哪个 agent 成功或失败；
- 是否发生降级；
- 已消耗多少 token；
- 是否仍值得继续；
- 失败后是否可恢复。

TradingAgents-CN 的任务、进度、SSE/WebSocket、历史状态和 worker 组织方式值得作为后续产品化参考。

### 7.3 模型与 provider 配置体验

可借鉴：

- quick/deep model 分离；
- provider/model catalog；
- 超时、token、temperature、reasoning effort；
- 用户可见的模型配置；
- 运行时记录 provider/model；
- token 和成本统计。

本项目应保留更严格的实验要求：

- A/B 显式绑定 model id；
- 同一实验的输入、工具和预算冻结；
- artifact 记录 provider host、model、usage、prompt/features hash；
- fixture 不冒充真实模型证据。

### 7.4 报告历史、导出与结果查看

值得借鉴的产品能力：

- 分析历史；
- 单次运行详情；
- Markdown/Word/PDF 导出；
- 任务结果与标的关联；
- 模型和耗时可见；
- 从模拟交易回到对应分析报告。

对本项目更重要的扩展是：

- Thesis version history；
- evidence/counter-evidence diff；
- key variable 变化；
- quality status 变化；
- dossier snapshot 与 prompt/version 审计。

### 7.5 新闻与事件基础设施

TradingAgents-CN 已有较丰富的：

- 新闻多源聚合；
- 去重；
- 相关性过滤；
- 新鲜度处理；
- 新闻与公告同步；
- 数据库存储和查看。

这对本项目未来有两个明确用途：

1. G2 dossier 的外部事实和市场预期补充；
2. G3 对 `key_variables`、风险事件和 thesis-break 候选信号的监控。

新闻不应直接进入最终 verdict，而应先进入带 provenance/status 的事件候选层。

### 7.6 模拟交易作为纪律验证沙盒

模拟交易可以借鉴，但其定位应调整为：

```text
InvestmentThesis
→ 用户确认 HoldingContract
→ shadow decision
→ 模拟订单
→ 后续复核
→ 检查是否遵守事前纪律
```

模拟账户服务于 G3 的纪律实验，而不是为了增加一个“交易功能”。

---

## 8. 可复用边界

### 8.1 可评估的小块代码或设计模式

TradingAgents-CN 根许可证声明，除 `app/` 和 `frontend/` 外的核心区域默认采用 Apache License 2.0。

可进一步评估的小块包括：

- provider key normalization；
- LLM client factory 的接口形式；
- 多市场 ticker 识别；
- 新闻去重和过滤；
- token/耗时记录；
- 节点级进度名称映射；
- 报告运行日志结构；
- 部分数据 provider adapter 模式。

复用前必须逐项检查：

1. 文件实际许可证；
2. 是否携带 LangChain/LangGraph/ChromaDB 等额外依赖；
3. 是否与本项目 canonical snapshot 冲突；
4. 是否存在宽泛 fallback 或 silent default；
5. 是否值得复制代码，还是只借鉴接口设计。

### 8.2 不建议整体引入核心框架

不建议直接引入完整 `tradingagents` 包。

原因：

- 会引入 LangGraph/LangChain；
- 会引入 ChromaDB 和多套 LLM adapter；
- provider、memory、agent state 和交易信号强耦合；
- 最终输出目标与 `InvestmentThesis` 不一致；
- 增加依赖和运行复杂度；
- 降低当前显式串行调用链的可审计性。

本项目已明确：

> Multi-Agent 本质是带信息可见性控制的串行 LLM 调用，不需要为了“像 Agent 系统”而引入框架。

### 8.3 不建议复用的核心决策逻辑

明确不建议复用：

- Bull/Bear 强制立场 Prompt；
- Risky/Safe/Neutral 角色辩论 Prompt；
- Trader 强制目标价逻辑；
- SignalProcessor 的默认值与智能推算目标价；
- 失败默认持有；
- 将短期收益直接作为历史决策对错标签的反思逻辑；
- 完整 LangGraph state schema。

这些逻辑与本项目 G2/G3 的可信度目标冲突。

### 8.4 `app/` 与 `frontend/` 许可证限制

TradingAgents-CN 的：

- `app/` FastAPI 后端；
- `frontend/` Vue 前端；

使用专有许可证，明确限制未经授权的修改、分发和商业使用。

因此：

- 可以研究交互和架构；
- 不应直接复制进本项目；
- 不应把源码搬来修改后再分发；
- 若未来希望直接使用，必须先取得明确授权并重新核验届时许可证。

本文不是法律意见，任何真实商业使用仍需单独做许可证确认。

---

## 9. 本项目已有更好观点的部分

### 9.1 三个串行 Capability Gate

本项目明确：

```text
G1 快：输入与候选可信
    ↓
G2 深：Investment Thesis 可信
    ↓
G3 拿得住：持有纪律可信
```

这优于把筛选、分析、报告、模拟交易作为并列功能不断堆叠。

任何下层未通过，都不能靠上层 UI、状态机或功能数量补救。

### 9.2 Multi-Agent 不是产品目标

本项目要求：

- 先建立强单 Agent baseline；
- Council 与 baseline 使用同模型、同 dossier、同工具、可比预算；
- 通过匿名盲评判断信息增量；
- 没有稳定增量就回退。

这比默认保留 Multi-Agent 形态更实事求是。

### 9.3 允许拒绝判断

可信系统必须允许：

- 数据不足；
- 超出能力圈；
- 事实无法验证；
- provider 失败；
- 结论不可用；
- 需要人工复核。

这比强制输出目标价和交易建议更适合高风险金融决策。

### 9.4 Investment Thesis 优于交易信号

买入/持有/卖出很快会过期。

可持续跟踪的是：

- 核心 Thesis；
- 支持证据；
- 反证；
- 假设；
- 未知项；
- 关键变量；
- 改变条件；
- 质量状态。

因此 G2 的稳定对象应是 `InvestmentThesis`，而不是目标价或交易信号。

### 9.5 缺失与降级语义

本项目已明确区分：

- `record_not_found`；
- `source_failed`；
- `invalid_value`；
- `present_but_degraded`；
- `not_evaluable`；
- `manual_action_required`。

这比“尽量返回一个非空结果”更符合可信排名和下游决策需求。

### 9.6 HoldingContract 优于模拟交易记录

模拟交易记录过去发生了什么。

`HoldingContract` 约束未来应该如何行动：

- 为什么持有；
- 最大仓位；
- 可承受回撤；
- 复核节奏；
- thesis-break 条件；
- 加仓条件；
- 冷静期；
- 交易前检查。

因此，模拟账户应是 G3 的辅助设施，而不是 G3 本身。

---

## 10. 不应因本次借鉴改变的既定决策

本次分析不改变以下项目决策：

1. G1 → G2 → G3 串行放行；
2. G1 未通过真实全市场 Gate 前，不用前端或 L4 完整度宣称能力成立；
3. G2 目标是可信 `InvestmentThesis`，不是保留 Multi-Agent 形式；
4. f3c 未收口前，不用更多角色或更多轮次掩盖串台/同质化问题；
5. G2 未通过前，不启动 G3 runtime；
6. 不引入 LangGraph/AgentScope 等 Multi-Agent 框架；
7. 不使用未经验证的 fallback source；
8. 失败、降级、能力圈外必须显式进入最终状态；
9. 系统不替用户执行自动交易；
10. TradingAgents-CN 的产品壳不能未经授权直接复制。

---

## 11. 分阶段吸收建议

### 11.1 当前阶段：只吸收设计与工程模式

在 G1/G2 Gate 尚未通过时，优先研究但不扩建：

- 本地数据同步与数据库查询架构；
- provider 管理和数据健康度；
- 新闻/公告聚合；
- 任务状态和进度模型；
- token、耗时和成本记录；
- 报告历史与导出信息架构。

本阶段不应：

- 开始复制其前端；
- 引入完整 LangGraph；
- 增加模拟交易；
- 把目标价和交易信号写入 G2 稳定接口；
- 为了产品完整度绕过当前 G1/f3c/G2 Gate。

### 11.2 G1 接近通过后：建设轻量产品壳

优先级建议：

1. G1 完整漏斗可视化；
2. 数据源健康度和字段 coverage；
3. L2 全量结果与 failure distribution；
4. run identity、profile version 和输入快照查看；
5. 分析任务队列与进度；
6. 运行历史。

前端需围绕“为什么进入、为什么排除、哪里降级”设计，而不只是展示最终候选。

### 11.3 G2 接近通过后：建设 Thesis 产品页

优先级建议：

1. dossier snapshot；
2. evidence/counter-evidence；
3. assumptions/unknowns；
4. Council 与 baseline 对照；
5. quality status；
6. Thesis version diff；
7. Markdown/PDF 导出；
8. key variables 与待验证事项。

### 11.4 G2 通过后：建设 G3 shadow mode

优先级建议：

1. `InvestmentThesis → HoldingContract`；
2. 用户确认与版本冻结；
3. 模拟持仓；
4. price-review 与 thesis-break 分离；
5. pre-trade check；
6. 持有纪律事件日志；
7. 事前判断与事后收益分开复盘。

---

## 12. 最终判断

如果把两个项目放在同一个坐标系：

- TradingAgents-CN 已经建成了一个功能丰富、可操作的股票分析平台；
- trade-agent 正在建设一套更强调输入可信、认知可信和持有纪律的投资能力系统。

TradingAgents-CN 最值得借鉴的是：

> 如何把数据、任务、配置、进度、历史、报告和模拟账户变成真实可操作的产品。

最不应照搬的是：

> 让多个角色完成讨论后，强制给出目标价和买入/持有/卖出结论。

本项目应保持的方向是：

```text
借鉴其平台工程
保留我方能力定义
坚持真实 Gate
先证明投资价值
再扩大产品形态
```

因此，不建议 fork、整体集成或迁移到 TradingAgents-CN；建议将其作为长期产品工程参考库，按需、小块、可审计地吸收模式，同时维持本项目 G1「快」→ G2「深」→ G3「拿得住」的既定 Capability Gate。
