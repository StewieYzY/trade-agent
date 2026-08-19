# council-output-interface Specification

## Purpose

定义 L3 天团辩论到 L4 监控的接口契约：council 子命令跑完单股即写
`watchlist/{canonical_ticker}/{run_id}/{date}.json`（不引入批跑聚合），字段来源于
CouncilResult 与 R1/R2 的 what_would_change_my_mind 收集，与 L1/L2 的 screener
watchlist 文件独立。

## Requirements

### Requirement: L3→L4 接口文件结构
系统 SHALL 产出 run-scoped Council 接口文件，每个 council 子命令跑完单股即写
（不引入批跑聚合）。除既有字段外，新写入的接口文件 SHALL 包含
`run_quality_status`、`run_quality_reasons`、`final_quality_gate`、
`success_cache_eligible` 与 `quality_record_path`。

`success_cache_eligible` 只有在 `run_quality_status="complete"` 且
`final_quality_gate="passed"` 时才 SHALL 为 true。接口文件中存在
`final_verdict`、`conviction` 或 `debate_path` MUST NOT 单独表示 clean success。

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
  "debate_path": "debate/600519.SH/{run_id}/2026-06-30.md"
}
```

字段来源：
- `ticker` / `date` / `final_verdict` / `conviction`：来自 `CouncilResult`（synthesizer 输出）
- `consensus_summary`：来自 `CouncilResult.consensus_summary`（synthesizer 输出）
- `key_variables`：从 R1/R2 所有 AgentOutput 的 `what_would_change_my_mind` 原始收集（`extract_key_variables` 函数），与 `total-design.md` §6.4/§7 一致，L4 监控盯这些变量做宽泛盯盘
- `dissent_points`：来自 `CouncilResult.dissent_points`（synthesizer 输出）
- `pending_verification`：来自 `CouncilResult.pending_verification`（synthesizer 结构化提炼的待验证事项），L4 做聚焦验证。与 `key_variables` 是**两个独立字段**：前者是原始收集，后者是结构化提炼
- `debate_path`：辩论记录 md 路径

#### Scenario: Complete 接口文件
- **WHEN** `council --ticker 600519` 跑完单股深研
- **THEN** 质量记录为 complete 且 final quality gate passed 时，接口文件 SHALL 写入 `success_cache_eligible=true` 和 quality record reference

#### Scenario: 降级或中断接口文件
- **WHEN** Council run 为 warning、failed、incomplete、runtime_degraded 或 da_skipped
- **THEN** 接口文件 SHALL 明确写入对应 status/reasons，且 `success_cache_eligible=false`

#### Scenario: 接口文件与 L1/L2 watchlist 独立
- **WHEN** L3 产出 `watchlist/{canonical_ticker}/{run_id}/{date}.json`
- **THEN** SHALL NOT 覆盖或修改 `watchlist/{date}_screener.json`（L1/L2 产出），两个文件独立存在

### Requirement: 接口文件产出时机
接口文件 SHALL 在 council 子命令跑完单股后立即写入
(`watchlist/{canonical_ticker}/{run_id}/{date}.json`)，不引入批跑聚合。

#### Scenario: 单股即写
- **WHEN** `run_debate` 返回 `CouncilResult`
- **THEN** SHALL 立即写入 run-scoped Council 文件，不等待其他股票

#### Scenario: 批跑不在 3b scope
- **WHEN** 需要消费 L2 ~20 只股票
- **THEN** 3b SHALL NOT 实现批跑逻辑，留给 L4 触发（4 change 的职责）
