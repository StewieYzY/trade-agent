## ADDED Requirements

### Requirement: L3→L4 接口文件结构
系统 SHALL 产出 `watchlist/{date}_council.json`，每个 council 子命令跑完单股即写（不引入批跑聚合）。

文件结构：
```json
{
  "ticker": "600519.SH",
  "date": "2026-06-30",
  "final_verdict": "bullish",
  "conviction": 75,
  "consensus_summary": "品牌定价权 + 简单商业模式，护城河深厚",
  "key_variables": ["ROE 是否持续 > 20%", "管理层是否出现减持行为"],
  "dissent_points": [{"topic": "估值是否过高", "who_disagrees": "munger", "their_reason": "PE 30x 高于历史均值"}],
  "pending_verification": ["现金流/ROE 是否有背离"],
  "debate_path": "debate/600519/2026-06-30.md"
}
```

字段来源：
- `ticker` / `date` / `final_verdict` / `conviction`：来自 `CouncilResult`（synthesizer 输出）
- `consensus_summary`：来自 `CouncilResult.consensus_summary`（synthesizer 输出）
- `key_variables`：从 R1/R2 所有 AgentOutput 的 `what_would_change_my_mind` 原始收集（`extract_key_variables` 函数），与 `total-design.md` §6.4/§7 一致，L4 监控盯这些变量做宽泛盯盘
- `dissent_points`：来自 `CouncilResult.dissent_points`（synthesizer 输出）
- `pending_verification`：来自 `CouncilResult.pending_verification`（synthesizer 结构化提炼的待验证事项），L4 做聚焦验证。与 `key_variables` 是**两个独立字段**：前者是原始收集，后者是结构化提炼
- `debate_path`：辩论记录 md 路径

#### Scenario: 单股 council 产出接口文件
- **WHEN** `council --ticker 600519` 跑完单股深研
- **THEN** SHALL 写入 `watchlist/{date}_council.json`，包含上述字段

#### Scenario: 接口文件字段完整
- **WHEN** 接口文件被写入
- **THEN** SHALL 包含 `ticker` / `date` / `final_verdict` / `conviction` / `consensus_summary` / `key_variables` / `dissent_points` / `pending_verification` / `debate_path` 全部字段

#### Scenario: 接口文件与 L1/L2 watchlist 独立
- **WHEN** L3 产出 `watchlist/{date}_council.json`
- **THEN** SHALL NOT 覆盖或修改 `watchlist/{date}_screener.json`（L1/L2 产出），两个文件独立存在

### Requirement: 接口文件产出时机
接口文件 SHALL 在 council 子命令跑完单股后立即写入（`run_debate` 返回 `CouncilResult` 后立即写），不引入批跑聚合。

#### Scenario: 单股即写
- **WHEN** `run_debate` 返回 `CouncilResult`
- **THEN** SHALL 立即写入 `watchlist/{date}_council.json`，不等待其他股票

#### Scenario: 批跑不在 3b scope
- **WHEN** 需要消费 L2 ~20 只股票
- **THEN** 3b SHALL NOT 实现批跑逻辑，留给 L4 触发（4 change 的职责）
