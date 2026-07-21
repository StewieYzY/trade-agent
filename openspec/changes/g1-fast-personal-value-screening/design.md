## Context

G1 对应“快”：按用户个人价值投资风格，从全市场快速形成值得继续研究的候选池。当前 L1/L2 已有筛选骨架，但能力只在小样本上运行过，且存在数值口径、采集分层、全量结果、ticker identity 和全市场性能证据缺口。

本 change 是 umbrella capability charter。它约束后续 `quantitative-screener`、`scout-agent` 和数据采集相关 child changes，但不直接修改运行时代码。项目级顺序遵循 AD-10：G1 Capability Gate 未通过前，不以扩建 G2/G3、前端或部署替代 G1 验证。

利益相关方包括最终使用候选池的用户、维护 L0-L2 的开发者，以及消费 G1 shortlist 的 G2 深研流程。

## Goals / Non-Goals

**Goals:**

- 定义“个人价值风格筛选”的产品语义，避免偏移为短期涨跌预测或固定数量推荐。
- 定义从数值正确性、分层采集到全市场运行和人工风格复核的完整 Capability Gate。
- 建立可版本化、可解释、可复现的筛选输入与漏斗输出。
- 把后续实现拆为可独立验证和归档的 child changes。

**Non-Goals:**

- 本 umbrella change 不直接修复 L1/L2 代码，也不直接执行全市场运行。
- 不在 G1 完成完整 DCF、深度主营研究或重度 LLM 分析。
- 不预测短期股价涨跌，不承诺候选股票未来上涨。
- 不为了凑足固定候选数量而降低筛选门槛。

## Decisions

### D1. “潜力股”定义为符合个人价值风格且值得深研

G1 的输出是研究资源分配结果，不是交易信号。候选必须能解释其质量、估值、反陷阱和热度排除结果；是否买入由 G2/G3 和用户最终决策决定。

备选方案是直接以未来收益或热点反转为目标。该方案需要可靠预测标签与回测体系，也会偏离用户已确认的价值投资风格，因此不采用。

### D2. 以版本化 ScreeningProfile 作为规则真值源

后续 child change 将把硬排除、质量权重、估值权重、反陷阱规则、热度排除和 L2 阈值组织为可标识版本的 `ScreeningProfile`。每次运行保存 profile version、输入快照、canonical ticker 和 `run_id`。

备选方案是继续把阈值分散在代码与 prompt 中。该方案无法解释结果漂移，也不利于用户校准个人风格，因此不采用。

### D3. 恢复真实漏斗式采集并隔离 G1/G2 数据边界

L1 只消费全市场筛选所需的轻量数字维度；`main_business`、`peers`、`research` 等 G2 dossier 维度不得被默认带入全市场路径。通过逐层缩小 ticker 集合，减少网络请求、失败面和缓存污染。

备选方案是先为所有股票采齐所有维度再筛选。该方案实现表面简单，但吞吐、稳定性和成本不可接受，也模糊了 G1/G2 边界，因此不采用。

### D4. 简化 DCF 在可靠前不得影响 G1 排序

DCF 如缺少每股口径、净债务、总股本和假设敏感性验证，必须从排序中移除或隔离为非决策展示字段。后续 child change 决定是修复还是移除，但必须先用确定性测试证明量纲正确。

备选方案是保留当前输出并仅降低权重。错误量纲即使低权重仍会污染排序与解释，因此不采用。

### D5. G1 输出完整漏斗而非只有 shortlist

每只输入股票必须归属于 `deep_dive`、`watch`、`skip` 或 `error`，并保留阶段、原因、降级状态和关键分数。shortlist 是完整结果的派生视图。

备选方案是只持久化通过者。该方案无法计算失败分布、字段可用率和门槛偏差，也无法解释漏选，因此不采用。

### D6. 能力验证采用“300+ 预检 → 真实全市场 → 用户 Top 20 复核”

先用不少于 300 只、覆盖多行业与不同财务质量的样本发现分布性问题；通过后再做一次真实全市场 warm-cache L1+L2 运行；最后由用户盲于实现细节复核 Top 20 是否符合个人风格。

不直接从单元测试跳到全市场，因为小样本绿测不能暴露行业分布、数据源退化、长尾失败和性能瓶颈。

### D7. Umbrella 通过依赖真实证据，不依赖直接 apply

每个 child change 必须引用本 umbrella，并推进至少一个明确 Gate。Umbrella 的 tasks 是里程碑登记表，不应直接使用 `/opsx:apply` 作为巨型实现计划。只有必要 child changes 已归档，且最终 evidence bundle 满足全部 Gate，本 Goal 才可标记通过。

## Risks / Trade-offs

- [Risk] Top 20 的 70% 人工复核带有主观性 → 预先固定 ScreeningProfile 版本、候选展示格式和评价标签，并保留用户逐只理由。
- [Risk] warm-cache 15 分钟不能代表冷启动表现 → 同时记录 cold/warm 指标，但日常 Gate 以可重复的 warm-cache 场景为准。
- [Risk] 数据源在全市场运行时出现大面积降级 → 将 availability、degraded、error 分开统计，未达到 95% 时不允许用 shortlist 掩盖。
- [Risk] 为追求通过率而持续调低规则 → 所有阈值变更必须形成新 profile version，并重跑同一验证样本比较候选漂移。
- [Trade-off] 将完整 DCF 移出 G1 会减少一个“精细估值”信号 → 换取数值可靠性和全市场吞吐；完整估值保留给 G2。

## Migration Plan

1. 通过 child change 修复数值口径并确定简化 DCF 的去留。
2. 分离 G1/G2 fetcher registry，恢复逐层采集。
3. 补齐 L2 全量结果、failure summary、usage 和 canonical identity。
4. 建立 300+ 多行业验证集并通过数据质量预检。
5. 执行真实全市场运行，形成性能、成本、漏斗和失败证据。
6. 完成用户 Top 20 风格复核并冻结首个通过 Gate 的 profile version。

回退策略：任何 child change 导致候选质量或运行稳定性退化时，回退到上一个已验证的 ScreeningProfile 与输出 contract；未通过 Gate 的版本不得作为默认日常筛选版本。

## Open Questions

- 首个 300+ 验证集的行业配额和特殊风险样本比例由对应 child change 固定。
- `ScreeningProfile` 首版采用文件配置还是 Python schema，由实现 child change 在不引入新依赖的前提下决定。
- 全市场 cold-cache 运行是否需要单独设 SLA，在 warm-cache Gate 通过后根据实测决定。
