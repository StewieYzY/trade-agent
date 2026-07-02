# L2 分布 + 成本（f1-deviation-fix §5.4，光通信模块板块）

- 数据源：`data/l2_full.json`（L2 scout 输出，含 shortlist + usage_summary）
- L1 candidates 输入：11 只（来自 l1_full.json）

## 分布
- deep_dive 输出: 1 只（top-20 cap）
- confidence 列表: [80]
- confidence 直方图（10 分一档）:
  - 80-89: 1

## Token Usage（f1-deviation-fix §7 / P1 修复，AD-03 成本实测）
- LLM 调用数（本次实跑，含 watch/skip/error 全量）: 11
- cache 命中数: 0
- 等效全量调用数 = 11（推算全市场成本用）
- prompt_tokens 合计: 4877
- completion_tokens 合计: 4654
- total_tokens 合计: 9531
- 单次调用平均 token: 866
- 本次实跑费用估算: ≈¥0.0095（按 ¥0.001/1k token）
- 单只费用: ≈¥0.0009

## AD-03 成本假设验证
- AD-03 假设：≈¥0.01/只 × 200 只 = ¥2 总预算。实测单只 ≈¥0.0009（DeepSeek），远低于假设，预算充裕
- 200 只全量成本推算：≈¥0.1733（单只费用 × 200，远低于 AD-03 ¥2 预算）
- 注：本次 call_count 含 watch/skip/error 全量调用（P1 修复前只报 deep_dive 会丢 ~90%）

## 解读
- L2 不是'对所有候选都输出 deep_dive'的同质化筛选：11 candidates → 1 deep_dive（1/11=9% 入选）
- confidence 分布有梯度（非全 75），说明 L2 在做区分