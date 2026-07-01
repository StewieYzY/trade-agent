## ADDED Requirements

### Requirement: 全市场候选集区分度验证
Scout SHALL 在真实全市场候选集（非手工挑的 20 只样本）上验证区分度，实证 AD-03 成本闸门假设（200→20，¥0.01/只）。

> 背景：deviation-analysis §1.5 实证发现，L2 从未在真实候选集上跑过——`data/cache/` 26 个目录全是手工挑的白马（茅台/平安/五粮液等），`review-notes.md` 门 2 跑的 `batch data/tickers.txt` 只有 20 只手工清单，`stats.input_scale == "subset"` 退化标记一直在说"这不是真·全市场"。AD-03 假设零佐证。

#### Scenario: 全市场 L1→L2 链路验证
- **WHEN** L1 对全 A 股 ~5000 只跑完 `screen`，产出 candidates 列表
- **THEN** SHALL 将 L1 candidates 全量喂给 `scout_batch`，记录 deep_dive 数量 / watch 数量 / skip 数量的分布，验证漏斗比例（设计目标 200→20）

#### Scenario: L2 区分度实证
- **WHEN** Scout 对真实全市场 candidates 跑完 batch
- **THEN** SHALL 记录 confidence 分布（直方图）、deep_dive 比例、与手工 20 只样本的对比，验证 L2 不是"对所有白马都输出 deep_dive"的同质化筛选

#### Scenario: 成本实测
- **WHEN** 全市场 L2 batch 执行
- **THEN** SHALL 记录 LLM 调用次数、token 消耗、总费用，验证 AD-03 成本假设（≈¥0.01/只，200→20 总成本 ≈¥2）

#### Scenario: input_scale 退化标记在全市场的表现
- **WHEN** L1 对全 A 股 ~5000 只跑 `screen`
- **THEN** `stats.input_scale` SHALL 为 "full"（≥300 只），`industry_pe_degraded` 在全市场样本下的触发面 SHALL 被记录（验证退化标记不是只在 subset 下才触发）
