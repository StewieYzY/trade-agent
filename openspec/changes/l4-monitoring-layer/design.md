## Context

L1/L2/L3 已全部完成归档，代码状态：

- **L1**（`screener/main.py`）：`screen_a_shares()` 返回 `{run_date, candidates[], stats}`，每个 candidate 含 `ticker/name/industry/factor_scores/anti_trap/adjusted_composite/f_score/graham_number/pe_ttm/pb/pledge_ratio`
- **L2**（`scout/batch.py`）：`scout_batch()` 返回 top-20 deep_dive 列表，每项含 `ticker/verdict/confidence/one_liner/red_flags/green_flags/anti_trap_flags/low_confidence_anomaly`，结果缓存在 `ScoutCache`（24h TTL），无独立 watchlist 持久化文件
- **L3**（`council/`）：`watchlist/{date}_{ticker}.json` 接口文件，实测字段 `ticker/date/final_verdict/conviction/consensus_summary/key_variables/dissent_points/pending_verification/debate_path`，其中 `conviction/consensus_summary/dissent_points/pending_verification` 实测为 null
- **L0 数据层**（`data/fetchers/`）：5 个 dim（basic/financials/kline/valuation/risk），已归档冻结
  - `valuation.py`：`pe_percentile_5y`（0-100）、`pb_percentile_5y`、`pe_history`、`pb_history`、`graham_number`
  - `risk.py`：`pledge_ratio`（质押率%）、`goodwill`（商誉）、`audit_opinion`（审计意见，可能 None）
  - **缺失**：业绩预告/分红公告/高管变动/行业政策 fetcher
- **LLM 复用**：`council/llm.py` 的 `call_llm(system_prompt, user_message, reasoning_level="moderate")` 已实现 moderate 映射（`LLM_MODEL_MODERATE` 环境变量），httpx + temp=0 + JSON output
- **CLI**：Typer，已有 `fetch/batch/cache-clear/screen/scout/council` 六个子命令

约束引用（见 `design/architecture-decisions.md`）：
- AD-01：L4 同时消费 L1/L2 watchlist 和 L3 深研结果
- AD-02：估值提醒 = 估值低位 AND 催化，双条件
- AD-03：L4 轻量监控 ~¥0.1/只/周（不含触发 L2/L3），watchlist 5-20 只/周
- AD-04：L4 LLM 调用用 moderate
- AD-06：不做回测

## Goals / Non-Goals

**Goals:**
- 聚合 L1/L2/L3 三路产出为统一 `watchlist/{date}.json`（§7 结构），提供增量 diff 和历史轨迹
- 实现 weekly_monitor 主循环：轻量重跑 L1 → diff → 条件触发 L2/L3 → 估值提醒 → 风险扫描 → key_variable 提醒
- 催化事件检测 MVP 闭环（用 L0 已有数据源支撑的催化信号）
- 估值区间提醒严格落地 AD-02 双条件（估值低位 AND 催化）
- 风险事件扫描用硬规则（§7.1 表格"否"列）
- watchlist JSON null 字段完整防御（L3b 实测 conviction/consensus_summary/dissent_points/pending_verification 为 null）
- CLI 集成 `monitor` 子命令

**Non-Goals:**
- 不做 Streamlit 前端（change 5，横切）
- 不扩 L0 归档 fetcher 代码（决策 1 方案 B，用现有 risk/valuation dim）
- 不做回测（AD-06）
- 不做 L3 深研逻辑本身（L4 只消费 + 触发）
- 不做 watchlist 的 HTML 渲染（前端 change 5）
- 不做催化事件的 LLM 判断（财报/分红/高管变动/行业政策标 TODO）
- 不做 key_variables 自动变化检测（MVP 人工核对）

## Decisions

### 决策 1：催化事件数据源——MVP 用 L0 已有数据源（方案 B）

**选择方案 B：MVP 只做 L0 能支撑的风险信号，基本面催化维度为空。**

L0 已归档冻结，不能改。§7.1 催化事件需要的数据源全部缺失（业绩预告/分红/高管变动/行业政策），新建 event fetcher 涉及 akshare 接口调研、缓存策略、容错处理，工作量与整个 L4 MVP 相当。

**⚠️ MVP 阶段 AD-02 双条件的退化声明**：

AD-02 要求估值提醒 = 估值低位 AND 基本面催化，两者是不同维度（§7.1 明确区分"估值低位"是状态，"催化事件"是影响基本面的离散事件）。MVP 阶段基本面催化的数据源全部缺失，**🟢 估值提醒暂停输出**。`alert.py` 保留 AD-02 双条件框架代码，但该段落输出：`"⏸️ 估值提醒暂不可用——基本面催化事件数据源待补齐（event-fetcher TODO）"`。待 event-fetcher 补齐后启用。

**MVP 可覆盖的信号**（仅用于风险扫描，不用于估值提醒的催化判断）：

| 信号类型 | 数据源 | 判断逻辑 | 用途 |
|----------|--------|----------|------|
| 质押率急升 | `risk.py` `pledge_ratio` | 周环比上升 > 5ppt | 🔴 风险扫描（利空信号） |

**注意**：`valuation_low_marginal`（pe_percentile 从 ≥20% 变 <20%）是估值状态的边际变化，**不是基本面催化事件**，不归入催化检测（`catalyst.py`），仅用于 diff 检测（`diff.py` 的 `valuation_low` 类型）。`pledge_ratio_spike` 是利空信号，只归风险扫描，不用于估值提醒的催化判断（否则会出现"估值低位 + 质押率急升 = 🟢 建议关注"的语义矛盾）。

**标 TODO 的催化**（后续 change 补 event fetcher）：

| 催化类型 | 缺失数据源 | TODO 标记 |
|----------|-----------|-----------|
| 财报超预期 | 业绩预告/快报 fetcher | `# TODO: event-fetcher` |
| 分红提升 | 分红公告 fetcher | `# TODO: event-fetcher` |
| 行业政策 | 新闻/公告 + LLM 判断 | `# TODO: event-fetcher + LLM` |
| 管理层变动 | 高管变动 fetcher + LLM 判断 | `# TODO: event-fetcher + LLM` |
| 减持 | 减持公告 fetcher | `# TODO: event-fetcher` |
| 业绩预告差 | 业绩预告 fetcher | `# TODO: event-fetcher` |
| 审计意见变更 | `risk.py` `audit_opinion` 数据源不可靠（optional/degraded，大概率返回 None） | `# TODO: audit-opinion` |

**排除方案 A（L4 新增 event fetcher）的理由**：
- 工作量：每个 fetcher 需要 akshare 接口调研 + 对齐 L0 BaseFetcher 模式（缓存/TTL/容错），5 个 fetcher ≈ 3-5 天
- 接口稳定性：业绩预告/分红/减持的 akshare 接口质量未验证，可能需要多轮调试
- MVP 目标：L4 的核心价值是「diff + 提醒」闭环，不是催化事件的完整性；催化信号可以用已有数据源的边际变化近似

### 决策 2：watchlist 聚合 + diff + 历史轨迹

#### 聚合结构

`watchlist/{date}.json`（§7 子集 + L2/L3 扩展字段）：

> **与 §7 的差异**：§7 的 `roe_5y_avg` / `dividend_yield` / `safety_margin_pct` / `heat_rank` / `flags` / `red_flags` / `green_flags` / `rationale` 字段在 L4 聚合中**不填充**（L1/L2 未直接产出或需要额外 feature 组装）。L4 新增 `stage` / `l2_verdict` / `l2_confidence` / `l3_verdict` / `l3_conviction` / `key_variables` 字段。

```json
{
  "generated_at": "2026-06-30T10:00:00",
  "l1_candidates": 200,
  "l2_shortlist": 20,
  "candidates": [
    {
      "ticker": "002273.SZ",
      "name": "水晶光电",
      "stage": "l3",
      "l1_score": 87,
      "l2_verdict": "deep_dive",
      "l2_confidence": 82,
      "f_score": 8,
      "pe_ttm": 18.2,
      "pe_percentile_5y": 28.0,
      "pb": 1.8,
      "pledge_ratio": 5.2,
      "l3_verdict": "bullish",
      "l3_conviction": null,
      "key_variables": ["市场份额大幅下降"],
      "last_updated": "2026-06-30"
    }
  ]
}
```

**顶层字段计算口径**：
- `l1_candidates`：L1 产出文件中的 `candidates` 列表长度
- `l2_shortlist`：`candidates[]` 中 `stage >= l2` 的数量（即 `l2_verdict == "deep_dive"` 的 candidate 数）

**聚合逻辑**：
1. 读取 L1 最新产出文件（`screen --output` 生成的 JSON），获取 candidates 列表（~200 只）。如果文件不存在或过期（> 7 天）→ 提醒用户"请先跑 `screen` 更新 L1 数据"
2. 对每只 candidate 检查 `ScoutCache`（L2 缓存，24h TTL）是否有 deep_dive 结果 → 填充 `l2_verdict`/`l2_confidence`（即使缓存过期也接受）
3. 检查 `watchlist/{date}_{ticker}.json` 是否存在 L3 结果 → 填充 `l3_verdict`/`l3_conviction`/`key_variables`
4. `stage` 字段标记该 candidate 的最高阶段：`l1` / `l2` / `l3`
   ```python
   def compute_stage(has_l2_verdict, l2_is_deep_dive, has_l3_verdict):
       if has_l3_verdict:        # L3 跑过（包括 verdict="unknown" 的情况）
           return "l3"
       elif l2_is_deep_dive:     # L2 给了 deep_dive
           return "l2"
       elif has_l2_verdict:      # L2 给了 pass/reject
           return "l1"           # 评估过但不值得深研，仍算 l1
       else:                     # 只有 L1 产出，没跑过 L2
           return "l1"
   ```
   
   > **注意**：当 L3 的 `final_verdict` 为 null 时，`l3_verdict` 被标记为 `"unknown"`（决策 6）。此时 `has_l3_verdict=True`，因此 `stage="l3"`——这表示 L3 跑过但 verdict 为空，属于正常的 stage 计算逻辑。
5. **pe_percentile_5y 补充**：L1 产出文件不含 `pe_percentile_5y` 字段（L1 只输出 `pe_ttm`/`pb`/`graham_number`），但 L4 的 diff 检测和估值提醒依赖它。对 `stage >= l2` 的 candidate（~5-20 只）调用 `ValuationFetcher().fetch_with_fallback(ticker)` 补充 `pe_percentile_5y`，fetch 失败 → `pe_percentile_5y: null`，不阻断聚合。`stage=l1` 的 candidate（~180 只）`pe_percentile_5y` 留 null（L4 的估值关注聚焦已 deep_dive 或已深研的票，不为 change 5 前端的 200 只展示需求买单）。fetch_with_fallback 配合 L0 CacheManager，L1 刚跑过时命中缓存零网络。
6. null 防御（决策 6）：L3 字段为 null 时保留 null，不填默认值

**L2 触发策略**：
- 聚合时先从 ScoutCache 读 L2 verdict（可能过期，但接受）
- 做 diff，找出 significant 变化的票（l1_score 变化 > 15 或新增候选）
- 只对 significant 的票调用 `scout_batch`（绕过缓存，强制重跑）
- 其他票用旧的 L2 verdict（即使过期也接受，1 周前的数据够用）

**为什么 L4 不自己跑 L1**：
- L4 是**消费者**，不是**生产者**——职责清晰
- `screen_a_shares()` 全市场跑要 30-90 分钟（5000 只 × akshare live fetch），对 weekly 监控太重
- L1 产出文件已包含完整 candidates 列表，L4 直接读取做 diff，秒级完成
- 用户可以选择什么时候更新 L1（手动跑 or cron 定时）

#### diff 算法

对比 `watchlist/{date}.json` 与上一个快照（`watchlist/{prev_date}.json`），检测：

| diff 类型 | 检测逻辑 | 严重度 |
|-----------|----------|--------|
| candidate 新增 | ticker 在 current 不在 previous | info |
| candidate 跌出 | ticker 在 previous 不在 current | warning |
| l1_score 变化 | `abs(current.l1_score - previous.l1_score) > 10` | info |
| stage 升级 | `l1→l2` 或 `l2→l3`（verdict 翻转） | significant |
| stage 降级 | `l3→l2` 或 `l2→l1`（verdict 翻转） | significant |
| l3_verdict 变化 | `previous.l3_verdict != current.l3_verdict`（且均非 null） | significant |
| pe_percentile 边际变化 | 从 `>= 20%` 变为 `< 20%`（触及低位阈值） | significant |

#### 历史轨迹

按日归档 `watchlist/{date}.json`，提供 `diff.py --history {ticker}` 查询某只股票的 N 日轨迹：
- `l1_score` 走势
- `stage` 变化
- `l3_verdict` 变化
- `pe_percentile_5y` 走势

**输出格式**：Markdown 表格（终端友好，后续 Streamlit 可直接渲染）

```markdown
# 600519.SH 贵州茅台 — 历史轨迹

| 日期 | l1_score | stage | l3_verdict | pe_percentile |
|------|----------|-------|------------|---------------|
| 2026-06-09 | 78 | l2 | - | 22% |
| 2026-06-16 | 80 | l2 | - | 21% |
| 2026-06-23 | 85 | l3 | bullish | 18% |
| 2026-06-30 | 85 | l3 | bullish | 18% |
```

如果快照数 > 50，提示用户缩小日期范围（不自动截断）。

#### 触发 L2/L3 重评估的 diff 阈值（决策 3 联动）

见决策 3。

### 决策 3：weekly_monitor 触发条件与成本控制

#### 触发条件

| 触发 | 条件 | 动作 |
|------|------|------|
| L2 重评估 | candidate 新增（新进候选池）或 `l1_score` 变化 > 15 | 调用 `scout_batch` 对该 ticker 重新评估（绕过 24h 缓存） |
| L3 深研 | L2 verdict 翻转为 `deep_dive`（从 `pass`/`reject`/无） | 调用 `council` 对该 ticker 跑深研 |
| 估值提醒 | ~~`pe_percentile_5y < 20%` AND 催化出现~~ | **MVP 暂停**：基本面催化数据源缺失，输出 placeholder |
| 风险扫描 | 质押率急升 > 5ppt | 产出提醒，不自动触发 L3 |
| key_variable 提醒 | L3 产出 `key_variables` 非 null 非空 | 列出供人工核对（决策 5 方案 C） |

**关键原则**：
- 估值提醒和风险扫描**不自动触发 L3**，只产出提醒供人工决策（避免无谓成本）
- L3 深研只由 L2 verdict 翻转触发（不是每周全量重跑）
- 已有 L3 结果的 ticker，除非 L2 verdict 翻转，不重跑 L3

#### 成本估算

| 项目 | 单只成本 | 5 只/周 | 20 只/周 |
|------|----------|---------|----------|
| L1 轻量重跑 | ≈ 0 | ≈ 0 | ≈ 0 |
| L4 轻量监控（diff + 规则判断 + fetch_lite） | ≈ ¥0（纯本地计算 + 网络调用，无 LLM） | ≈ ¥0 | ≈ ¥0 |
| 触发 L2 重评估（按需） | ≈ ¥0.01 | ≈ ¥0.05 | ≈ ¥0.2 |
| 触发 L3 深研（按需，极少） | ≈ ¥20-60 | ≈ ¥0（通常不触发） | ≈ ¥0 |

**AD-03 约束验证**：L4 轻量监控本身 ¥0/只/周（纯本地计算 + stage≥l2 的 fetch_lite 网络调用，无 LLM 调用），满足 ~¥0.1/只/周的上限。触发 L2/L3 的成本不计入 L4 预算，单独列。

**fetch_lite 网络调用说明**：
- 对 `stage >= l2` 的 candidate（~5-20 只）调用 `ValuationFetcher().fetch_with_fallback(ticker)` 补充 `pe_percentile_5y`
- 每只票 ~3 次网络请求（估值数据 + PE 历史 + PB 历史），5-20 只 = 15-60 次调用
- 配合 L0 CacheManager 缓存，L1 刚跑过时命中率高，实际网络调用更少
- 无 LLM 费用，纯网络 I/O

**MVP vs 完整态的预算差异**：
- **AD-03（¥0.1/只/周）** 和 **AD-04（moderate LLM）** 描述的是**完整态预算**，假设催化 LLM 判断（决策 1 方案 B）和 key_variable LLM 判断（决策 5 方案 C）已启用
- **MVP 阶段**（决策 1 方案 B + 决策 5 方案 C）LLM 调用 = 0，实际成本 ¥0/只/周
- **后续启用 TODO 时**（event-fetcher + LLM 催化判断），成本将上升至 ~¥0.05-0.1/只/周，届时重新验证 AD-03 约束
- **AD-04 "触发重评估"语义澄清**：指 L4 自身的催化/重评估判断（需 moderate LLM），而非 L2/L3 触发阈值规则（diff 判断，不需 LLM）

### 决策 4：LLM 调用复用（AD-04）

**MVP 方案 B + 方案 C 下，L4 的 LLM 调用为 0。**

- 决策 1 方案 B：不做行业政策/管理层变动的 LLM 判断（标 TODO）
- 决策 5 方案 C：不做 key_variables 自动变化检测的 LLM 调用（标 TODO）
- 估值提醒和风险扫描用硬规则，不需要 LLM

**预留接口**：`monitor/catalyst.py` 中预留 `_llm_catalyst_check()` 函数（`# TODO: activate when event-fetcher available`），后续启用时复用 `council.llm.call_llm(reasoning_level="moderate")`。

**跨包 import 策略**：后续启用时直接 `from council.llm import call_llm`（类似 L3a import scout 的模式），不在 `monitor/` 内独立实现 LLM 调用。

### 决策 5：key_variables 变化检测——MVP 人工核对（方案 C）

**选择方案 C：MVP 不做自动检测，只把 key_variables 列在提醒里供人工核对。**

L3b 实测 `key_variables` 是自然语言文本（如"市场份额大幅下降"），不是结构化指标。三种方案对比：

| 方案 | 成本 | 准确性 | 实现复杂度 |
|------|------|--------|-----------|
| A: LLM 判断 | 高（每只每周期 1 次 moderate 调用） | 中（LLM 判断不稳定） | 中 |
| B: 规则映射 | 低 | 低（覆盖不全，映射表维护成本高） | 高（需人工建映射表） |
| C: 人工核对 | 0 | 高（人类判断最准） | 低 |

**理由**：
- MVP 目标是闭环 diff + 提醒，不是自动化程度
- key_variables 本身就是"什么会改变我的判断"的提示，人类核对是最自然的使用方式
- 方案 A/B 的 ROI 要在 watchlist 规模 > 50 只时才体现，当前 5-20 只/周人工核对成本极低

**实现**：`alert.py` 在周报中列出每只 L3 股票的 `key_variables`，标注"请人工核对以下变量是否发生变化"。

### 决策 6：watchlist JSON null 字段防御

L3b 实测 `watchlist/{date}_{ticker}.json` 中以下字段为 null：
- `conviction`：始终 null
- `consensus_summary`：始终 null
- `dissent_points`：始终 null
- `pending_verification`：始终 null
- `key_variables`：有值（`["市场份额大幅下降"]`）

**防御策略**：

| 字段 | null 处理 | 降级行为 |
|------|-----------|----------|
| `conviction` | 保留 null，聚合时 `l3_conviction: null` | diff 不比较 conviction 变化 |
| `consensus_summary` | 保留 null | 提醒中不展示 consensus |
| `dissent_points` | 保留 null | 提醒中不展示 dissent |
| `pending_verification` | 保留 null | 提醒中不展示 pending |
| `key_variables` | null 或空列表 → 跳过 key_variable 提醒 | 不触发 key_variable 监控 |
| `final_verdict` | null → 标记为 `unknown`，diff 视为无变化 | 不触发 verdict 变化提醒 |

**watchlist 健康检查**：`diff.py` 聚合时检测 L3 产出完整性——如果 `watchlist/{date}_{ticker}.json` 存在但 `conviction`/`consensus_summary`/`dissent_points`/`pending_verification` 全部为 null，标记为 `l3_incomplete: true` 并在周报中提醒"建议重跑 L3"。不做自动重跑（成本不可控）。

## Risks / Trade-offs

**[基本面催化维度 MVP 为空 → AD-02 估值提醒暂停]** → MVP 阶段基本面催化数据源全部缺失（财报/分红/高管变动/行业政策/减持/业绩预告差/审计意见），`catalyst.py` 无催化事件输出，🟢 估值提醒暂停（placeholder 提示）。`pe_percentile_5y` 边际变化是估值状态变化（归 `diff.py`），不是基本面催化事件。Mitigation：在 `catalyst.py` 中显式列出 7 条 TODO 项，后续 change 补 event fetcher 时逐一启用，届时 AD-02 双条件可正确落地。

**[L2 缓存 24h TTL 与 weekly 周期不匹配]** → ScoutCache TTL=24h，weekly_monitor 每周跑一次时 L2 缓存几乎必然过期。Mitigation：L4 接受过期的 L2 verdict（1 周前的数据够用），只对 diff significant 的票触发 L2 重跑（l1_score 变化 > 15 或新增候选），成本可控（~3 只/周 × ¥0.01 = ¥0.03）。

**[L3 null 字段可能长期存在]** → L3b 实测 conviction/consensus_summary 等为 null，可能是 synthesizer prompt 未产出这些字段。Mitigation：L4 做完整 null 防御（决策 6），同时通过 watchlist 健康检查提醒用户。L3 侧修复不在 L4 scope。

**[diff 无上一周快照时首次运行]** → 第一次跑 weekly_monitor 没有历史快照可对比。Mitigation：首次运行只产出当前快照，diff 报告标注"首次运行，无历史对比"，从第二次运行开始正常 diff。

**[key_variables 文本不结构化]** → L3b 产出自然语言 key_variables，无法自动检测变化。Mitigation：MVP 人工核对（决策 5），后续可考虑 LLM 判断（方案 A）或规则映射（方案 B）。

### 错误处理策略

| 失败点 | 处理方式 |
|--------|----------|
| L1 产出文件不存在/过期 | 报错退出，提示"请先跑 `screen`" |
| L2 重跑失败（LLM API 错误） | 跳过该 ticker，周报标注"L2 评估失败"，不触发 L3 |
| L3 重跑失败 | 保留旧 verdict（如有），标记 `l3_incomplete: true` |
| 催化检测数据缺失（如 `pledge_ratio` 为 None） | 跳过该催化信号，不报错 |
| ValuationFetcher 失败（pe_percentile_5y 获取失败） | `pe_percentile_5y: null`，不阻断聚合，该 candidate 不参与估值相关 diff 和提醒 |
| watchlist 写入失败 | 重试一次，仍失败则报错退出 |

**原则**：L4 是监控层，宁可漏报不可错报。一个 ticker 出错不应该影响其他 ticker。

### 周报输出格式

```markdown
# L4 监控周报 — 2026-06-30

## 摘要
- L1 候选：200 只（较上周 +5 / -3）
- L2 深研：20 只（较上周 +1 / -2）
- L3 跟踪：5 只（新增 0 只）

## 显著变化
- 📈 600519.SH 贵州茅台：l1_score 78→85（+7），stage l2→l3
- 📉 000858.SZ 五粮液：l1_score 82→71（-11），stage l2→l1

## 🟢 估值提醒（估值低位 + 催化）
- 600519.SH 贵州茅台：pe_percentile 22%→18%，建议关注

## 🔴 风险扫描
- 002594.SZ 比亚迪：质押率急升 3.2%→9.8%，建议重新审视

## 🔍 关键变量跟踪（人工核对）
- 600519.SH 贵州茅台：
  - 市场份额大幅下降
  - 高端白酒消费疲软
  
  💡 以上变量来自 L3 深研，请结合近期动态核对是否发生变化

## ⚠️ 健康检查
- 000858.SZ 五粮液：L3 产出不完整，建议重跑

## 成本
- L2 调用：3 只（¥0.03）
- L3 调用：0 只（¥0）
- 总计：¥0.03
```
