# Proposal: l1-quantitative-screener

## 问题

全 A 股 ~5000 只，人工逐只研判不可能。需要一个纯量化的筛选引擎，用学术验证过的因子（F-Score、PE/PB 分位、格雷厄姆数等）把 5000 只压缩到 ~200 只候选池，供下游 L2/L3 消费。

**核心挑战**：A 股价值投资最容易踩的坑是「价值陷阱」——便宜是因为真的烂。L1 不仅要选出便宜的，还要在量化层面尽可能标记陷阱信号。

## 目标

实现三道漏斗式筛选管线：

1. **硬门槛过滤**（Hard Gates）— 一票否决，~5000 → ~800
2. **价值质量双因子打分**（Factor Scores）+ **反价值陷阱**（Anti-Trap）— 软排序 + 扣分，~800 → ~300
3. **低热度排除**（Heat Filter）— 防御性排除，~300 → ~200

## 架构决策引用

- **AD-01**：L1 必须能独立运行并产出候选池，不依赖 L3。L1 输出是 L2 的输入。
- **AD-02**：低热度是排除维度（剔被炒的、剔刚炒完的），不是反转因子（跌多了 ≠ 机会）。逆向判断是 L3 冯柳 agent 的职责。
- **AD-06**：L1 不要求回测验证，F-Score/PE/PB 等因子直接采用学术公式（30 年+ 文献支撑）。
- **AD-07**：格雷厄姆纪律在 L1 强制执行——PE×PB<22.5 作为估值因子之一，格雷厄姆 7 项指标达标率嵌入质量因子。L3 天团不重复判断格雷厄姆纪律。

## 边界

### IN

- `screener/hard_gates.py` — 硬门槛过滤（一票否决）
- `screener/factor_scores.py` — 价值/质量/安全边际打分 + 综合分排序
- `screener/anti_trap.py` — 反价值陷阱因子（7 项扣分）
- `screener/heat_filter.py` — 低热度排除（防御性）
- `screener/main.py` — `screen_a_shares()` 入口，编排三道漏斗
- `cli.py` 集成 — `screen` 子命令

### OUT

- `data/`（fetchers/lib/cache）→ change 0 已实现
- `scout/`（L2 LLM 初筛）→ change 2
- `council/`（L3 天团深研）→ change 3a/3b
- `monitor/`（L4 监控）→ change 4
- `watchlist/`（watchlist 管理：增量 diff / 历史轨迹）→ change 4
- `frontend/`（Streamlit 前端）→ change 5
- `prompt_builder` + RULE.md 三层体系 → change 3a

### 关键边界

- L1 消费 L0 的 fetcher/cache/batch_fetcher/stock_features 接口，不新增数据采集逻辑
- L1 输出是排序后的候选列表（JSON），watchlist 增量 diff 和历史轨迹是 L4 的职责
- L1 不做任何 LLM 调用（纯量化）

## 依赖

- **上游**：`l0-bootstrap-data-layer`（fetchers + stock_features + cache + batch_fetcher）
- **下游**：`l2-llm-scout-agent`（消费 L1 候选池）

**L0 接口依赖**（Codex review 待修复项，不影响 L1 设计）：
- L0 的 `financials` fetcher 需要提供多期财报数据（当期 + 上期），以支持 F-Score 同比项（F3/F5/F6/F7/F8）和反陷阱因子的趋势计算
- L0 的 BaseFetcher 接口 sync/async 一致性待确认

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 财报数据延迟/缺失 | 质量因子（50% 权重）失效 | L0 已实现财报缓存 + 按季调度；L1 对缺失字段做降级（跳过该因子而非报错） |
| 权重设置不合理 | 排序偏差 | §4.8 初始值 50/30/20，跑几轮后根据 L2 否决率和 L3 共识调整 |
| 反陷阱因子误杀 | 漏掉好公司 | 反陷阱是扣分不是排除，保留可解释性（每只股票附带反陷阱标记） |
| 行业分类不准 | 行业中位 PE 计算偏差 | L0 market_router.py 维护行业映射，定期更新 |
