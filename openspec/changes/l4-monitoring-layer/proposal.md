## Why

L1/L2/L3 已全部完成归档。快筛管线（L1 量化 → L2 LLM 初筛）和深研管线（L3 天团辩论）各自独立运行，但缺少一个汇合点：没有统一的 watchlist 聚合视图，没有增量 diff 检测，没有催化事件和估值区间的自动提醒。L4 监控层是两条管线的汇合点（AD-01），也是用户日常使用的主入口——每周跑一次监控，得到"什么变了、什么值得关注、什么有风险"的结构化提醒。

## What Changes

- 新增 `monitor/` 包：`weekly.py`（主循环）/ `diff.py`（watchlist diff + 历史轨迹）/ `catalyst.py`（催化事件检测）/ `alert.py`（估值提醒 + 风险提醒 + key_variable 提醒）
- 新增 watchlist 聚合：`watchlist/{date}.json`（§7 子集 + L2/L3 扩展字段），读取 L1 产出文件（不自己跑 L1），聚合 L2 cache + L3 深研结果，对 stage≥l2 的 candidate 调用 ValuationFetcher 补充 `pe_percentile_5y` 字段，按日归档提供历史轨迹
- 风险信号检测：MVP 仅用 L0 已有数据源检测风险信号（质押率急升），基本面催化事件数据源全部缺失（财报/分红/高管变动/行业政策/审计意见），标 TODO 待后续补齐
- 估值区间提醒：**MVP 阶段暂停输出**（AD-02 要求估值低位 AND 基本面催化双条件，但 MVP 无基本面催化数据源，placeholder 提示待 event-fetcher 补齐）
- 风险事件扫描：硬规则判断（质押率急升），减持/审计变更/业绩预告差标 TODO
- key_variables 变化提醒：MVP 列出 L3 产出的 key_variables 供人工核对，不做自动检测
- watchlist JSON null 防御：L3b 实测 `conviction`/`consensus_summary`/`dissent_points`/`pending_verification` 为 null，L4 消费做完整防御
- CLI 集成：`monitor` 子命令（weekly 跑监控 / watchlist 聚合查询）
- 触发 L2/L3 重评估的 diff 阈值设计：避免每周全量重跑 L3，成本可控

## Capabilities

### New Capabilities
- `watchlist-aggregation`: 聚合 L1/L2/L3 三路产出为统一 `watchlist/{date}.json`（§7 子集 + L2/L3 扩展字段），按日归档，提供历史轨迹和 diff 对比
- `watchlist-diff`: 增量 diff 检测——对比当前与上一日/上周快照，检测 candidate 增减、l1_score 变化、verdict 变化、估值分位边际变化（`valuation_low`），触发 L2/L3 重评估的阈值控制
- `catalyst-detection`: **MVP 阶段基本面催化维度为空**——仅检测风险信号（质押率急升），财报/分红/高管变动/行业政策/审计意见标 TODO 待 event-fetcher 补齐
- `monitoring-alerts`: 估值区间提醒（**MVP 暂停**，AD-02 双条件中基本面催化维度为空）+ 风险事件扫描（硬规则）+ key_variables 变化提醒（MVP 人工核对）
- `monitor-cli`: 统一 CLI 入口——`monitor weekly` 跑主循环、`monitor watchlist` 聚合查询、`monitor diff` 对比、`monitor history` 历史轨迹

### Modified Capabilities
（无——L4 是独立层，不修改 L1/L2/L3 已有 spec）

## Impact

- **代码**：新增 `value-screener/monitor/` 包（5 个模块），修改 `value-screener/cli.py` 增加 `monitor` 子命令
- **API/依赖**：无新依赖（复用 akshare 通过 L0 数据层、复用 httpx、复用 ValuationFetcher 补充 `pe_percentile_5y`，MVP 无 LLM 调用）
- **成本**：L4 轻量监控含 fetch_lite 网络调用（stage≥l2 的 5-20 只 × 3 次网络请求，无 LLM 费用），触发 L2/L3 的成本单独列，由 diff 阈值控制
- **数据**：消费 L1 candidates（`screener/main.py` 输出）、L2 deep_dive 列表（`scout/batch.py` 内存对象）、L3 `watchlist/{date}_{ticker}.json`
- **Scope 边界**：不做 Streamlit 前端（change 5）、不扩 L0 归档 fetcher 代码、不做回测（AD-06）、不做 L3 深研逻辑本身
