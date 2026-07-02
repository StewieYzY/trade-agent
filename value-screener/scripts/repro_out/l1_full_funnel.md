# L1 漏斗比例（f1-deviation-fix §5.3，光通信模块板块 50 只）

- 数据源：`data/l1_full.json`（L1 screen 输出）
- 输入：50 只光通信模块板块成分股（`data/all_a_share.txt`）

## 漏斗
- total: 50
- after_hard_gates: 40
- after_factors: 40
- after_heat_filter: 11
- candidates 输出: 11

## 退化标记（spec scout-agent Scenario: input_scale 退化标记）
- input_scale: `subset`（全市场 ≥300 才为 'full'；50 只为 'subset'）
- industry_pe_degraded: `True`（行业 PE 兜底是否触发）

## Hard Gates 排除分布
- H8: 8
- H3: 3

## 解读
- 50→40（hard_gates 排除 10，H8/H3 为主）→40（factors 全过）→11（heat_filter 砍 29）
- heat_filter 在小样本下筛得狠（11/40=27.5%），与设计目标 200→~20 的 ~10% 略高，
  但样本仅 50 只无法验证全市场阈值，需扩到 ≥300 才能校准（§4.8 独立工作项）
- input_scale=subset 符合预期（50<300）；industry_pe_degraded=True 说明行业 PE 兜底触发