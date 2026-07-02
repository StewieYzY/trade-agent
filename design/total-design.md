# 多智能股票设计-0623

> 基于 UZI-Skill v3.x 代码分析 + 第一性原理需求拆解 + 两份独立方案融合
> 原稿来自 Claude 方案，采纳 Codex 的三层漏斗/成本模型/反陷阱因子/校准方法/监控层，分歧按 Claude 观点决议

---

## 一、第一性原理：需求拆解与伪冲突

### 1.1 两个核心需求

- **需求 A（快）**：快速选股，在几千只 A 股里找到低估值/低 PE/低热点的票布局入场。
- **需求 B（深）**：多 agent 分析师天团（巴菲特/芒格/段永平等蒸馏而成），通过辩论达成共识，判断标的在当前节点好不好、为什么、什么条件下会改变——这是仓位决策的前置判断，用户结合自身持仓状态做最终的加仓/持有/减仓/清仓决策。

直觉以为它们冲突——好像「天团辩论」是「选股」的下一个环节，天团太重所以选股不可能快。这是把两件事搞混了。

```
      ❌ 伪冲突（把天团塞进选股环节）
  选股(快) ──→ 天团辩论(慢) ──→ 决策

      ✅ 真正的结构（两条独立管线）
  全市场筛子(快 · 机械)         标的研判(慢 · 主观)
        ↓                            ↓
  产出一个 watchlist            天团辩论这一只
  (几十只候选)                 (已经选过的标的)
```

**核心结论**：快和深不是同一条管线的两个环节，是**两条独立管线**。选股是排序问题（规则能答），天团是质性判断问题（agent 才能答）。中间需要 L2 做成本闸门（该花花的逻辑）。

### 1.2 对「择时入场」的第一性原理警告

用户说「找低估值、低 PE、甚至**低热点**的股票想布局入场」。前两个（低估值/低 PE）是价值投资正道。但**「低热点 + 等合适时点入场」必须修正**：

- 「低热点」**不创造价值**。一只无人问津的票，可能真被低估（机会），也可能就该被遗忘（价值陷阱——夕阳行业、财务造假、治理崩坏）。**低热度本身不区分这两者。** 纯粹找冷门股，会收到一堆价值陷阱。
- 「合适时点入场」**是择时**。价值投资的立论基础是「**不择时**」——格雷厄姆说市场先生是来伺候你的不是来指导你的，巴菲特说「如果你不愿意持有一只股票十年，那就十分钟也不要持有」。小白试图「等一个低点入场」，90% 会变成「涨了追高、跌了割肉」。

**修正后的需求**：在冷门/低估值区间里，用财务质量筛掉价值陷阱，等到出现**基本面催化**（财报超预期、行业政策、管理层换届、分红提升）或估值修复信号时纳入 watchlist。

- **「低热点」**：作为**排除维度**（剔除被炒的、排除刚炒完的），**不做反转打分因子**（跌多了≠机会）。保守防御性打法。
- **「合适时点」**：重新定义为「**等待基本面催化**」，不是 K 线低点。「买入区间提醒」=「估值分位触及历史低位 + 出现基本面催化」，不是「股价跌到某价位」。

---

## 二、现有系统诊断（UZI-Skill）

### 2.1 UZI 的本质

UZI-Skill 是一个**规则引擎骨架 + 台词模板表**的系统，不是 AI 驱动的分析系统：

- **数据采集层**：22 维 fetcher + 三级容错 + wave 并发 → 这是真正的工程资产
- **决策层**：66 套 if-else 规则引擎 + 模板化台词 + 线性加权 → 固化的、无推理能力
- **评委同质化**：巴菲特和芒格的区别只是规则权重不同，规则引擎无法表达投资哲学差异
- **辩论是假的**：Great Divide 只是取分最高/最低的人拼预录台词，评委之间没有交互
- **信息浪费**：采了 22 维数据，规则引擎只消费 ~60 个扁平字段，大量定性数据在打分环节丢失
- **无选股能力**：每次分析必须指定 ticker，只有「分析」没有「发现」

### 2.2 可复用资产（保留并借鉴）

以下是从 UZI 中剥离到新 repo 的核心素材——**不是原样照搬**，是借鉴其设计模式并根据新需求更新（UZI 数据层有工程债：285 个 except Exception、两份分歧的 run.py、模块级 chdir 副作用，剥离时借机修最脏的几处）：

| 资产 | 设计模式 | 复用方式 |
|---|---|---|
| 22 维采集（fetch_*.py） | 三级容错 + provider chain failover | 借鉴模式，新建 repo 时重新组织，修 except/副作用 |
| Wave 分层并发 + mini_racer 锁 | wave1→2→3 三波，串行锁 + 哨兵降级 | 借鉴模式，用于 L3 深采 |
| resume + `.cache/{ticker}/raw_data.json` | dim 级增量复用 + 6 档 TTL | 借鉴模式，L3/L4 复用 |
| `stock_features.py` 特征层 | 单一真值源，~60 个 flat dict | **直接复用**（核了源码，F-Score 原料已齐） |
| `compute_deep_methods.py` 金融模型 | DCF/LBO/Comps/三表预测 | 借鉴模式，L3 机构建模 |
| Pipeline 三段式 | collect → score → synthesize 解耦 | 借鉴架构，新 repo 用类似结构 |
| `stock_style.py` 风格识别 | 白马/成长/周期/小盘等 8 类 | 借鉴模式，L1 可能用 |

### 2.3 不复用的（砍掉）

- 66 评委规则引擎 → 重做 5+1 天团
- 游资 24 评委 → 价值投资不需要
- Serenity AI 卡位 → 题材/趋势派逻辑，砍
- 技术派 4 评委 → 择时逻辑，砍
- 台词模板表 → 重做 Level 2 决策框架 prompt
- 68 个源码搜索测试 → 重做行为测试
- 两份 run.py → 只保留一份，消灭分歧

---

## 三、目标架构——三层漏斗 + 监控层

```
┌──────────────────────────────────────────────────────────────┐
│                   DATA LAYER（借鉴 UZI 模式，新建 repo）        │
│                                                              │
│  22 维采集 · 三级容错 · Wave 并发 · resume                     │
│  stock_features.py 特征提取（单一真值源）                      │
│  compute_deep_methods.py 金融模型 (DCF/LBO/Comps)            │
│                                                              │
│  新增: batch mode — 对 N 只股票并发跑 lite fetcher             │
│        (0_basic + 1_financials + 2_kline + 10_valuation)     │
└───────────────────────────┬──────────────────────────────────┘
                            │
          ┌─────────────────┼──────────────────────┐
          ▼                 ▼                      ▼
┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐
│ L1: Screener │  │ L2: Scout    │  │ L3: Analyst Council      │
│ 量化筛选      │  │ LLM 初筛     │  │ Multi-Agent 天团深研      │
│              │  │              │  │                         │
│ 纯 Python    │  │ 1 个轻量 agent│  │ 5+1 persona agents      │
│ 零 LLM       │  │ 可解释红/绿旗 │  │ + 3 轮辩论编排           │
│ 5000→200     │  │ 200→20       │  │ + Devil's Advocate      │
│ <1 min       │  │ ~10 min      │  │ ~5 min/股                │
│              │  │              │  │                         │
│ 格雷厄姆纪律 │  │ 便宜够用     │  │ 蒸馏决策框架             │
│ (内核)       │  │ (haiku/mini) │  │ (Level 2 prompt)        │
└──────────────┘  └──────────────┘  └─────────────────────────┘
          │                 │                      │
          ▼                 ▼                      ▼
┌──────────────────────────────────────────────────────────────┐
│                   L4: WATCHLIST & MONITORING                   │
│                                                              │
│  定期重跑 L1-L2 · 持仓股催化事件触发 L3                        │
│  估值分位触及低位 + 催化出现 → 提醒（不是股价跌到某价位）        │
│  风险事件（减持/业绩预告/审计变更）→ 重新审视                   │
│  watchlist 增量 diff + 历史轨迹                               │
└──────────────────────────────────────────────────────────────┘
```

### 3.1 成本模型

| 阶段 | 操作 | 每只成本 | 数量 | 总成本 |
|---|---|---|---|---|
| L1 量化筛选 | 纯数字过滤，零 LLM | ≈ 0 | 5000 → 200 | ≈ 0 |
| L2 LLM 初筛 | 1 次短调用（3-5 句判断） | ≈ ¥0.01 | 200 → 20 | ≈ ¥2 |
| L3 天团深研 | multi-agent 辩论（5+1 agent × 4 轮 ≈ 24 次重度调用） | ≈ ¥20-60 | 20 → 5 | ≈ ¥400-1200 |
| L4 监控 | 轻量重跑 + diff + 催化事件扫描 | ≈ ¥0.1 | 5-20 只/周 | ≈ ¥2/周 |

**总成本约 ¥400-1200 完成一轮完整的选股-研究-建仓流程。** L2 是必要的成本闸门——没有它，200 只全丢给 L3 天团（¥4000-12000）不可承受。

---

## 四、L1: Screener（量化筛选）

### 4.1 设计原则

- **纯 Python，零 LLM 调用**
- **格雷厄姆纪律是内核**：硬公式、硬阈值、不接受模糊判断
- F-Score / 格雷厄姆数 / DCF 安全边际都是经过 30 年学术验证的公式
- 复用 UZI 的 `stock_zh_a_spot_em`（全市场快照）+ `stock_financial_abstract`（财报）+ `stock_a_pe_and_pb`（估值分位）
- 新增 batch wrapper：对 N 只股票并发采集（max_workers=10）

### 4.2 三道漏斗

```
全市场 ~5000 只
   │
   ▼ 第一道：硬门槛过滤（Hard Gates · 一票否决）
   ├─ 剔 ST/*ST/退市风险
   ├─ 剔上市<3年（格雷厄姆要求：必须有足够财务历史）
   ├─ 剔市值<50亿（流动性+抗风险）
   ├─ 剔金融/券商（估值指标对金融股失效）
   ├─ 剔周期股（可选：钢铁/煤炭/航运/化工/水泥/养殖）
   ├─ 剔实控人质押>70%（治理风险）
   ├─ 剔非标审计意见
   └─ 剔 PE 为负（亏损企业）
   │
   ▼ 第二道：价值质量双因子（软排序 · 不剔除只打分）
   │
   │  ┌─── 估值因子 (30% 权重) ───────────────────┐
   │  │  PE_TTM < 行业中位 ×0.7                    │
   │  │  PB < 2                                    │
   │  │  股息率 > 2%                               │
   │  │  PE×PB < 22.5（格雷厄姆数）                │
   │  └──────────────────────────────────────────┘
   │  ┌─── 质量因子 (50% 权重) ───────────────────┐
   │  │  F-Score ≥ 7（Piotroski 九项标准）         │
   │  │  ROE 5 年平均 > 15%                        │
   │  │  经营现金流连续 3 年为正                    │
   │  │  ROE 趋势不下降（反价值陷阱）              │
   │  └──────────────────────────────────────────┘
   │  ┌─── 安全边际 (20% 权重) ───────────────────┐
   │  │  DCF 内在价安全边际 > 30%                  │
   │  │  (简化 DCF：2-Stage FCF + Gordon Terminal) │
   │  └──────────────────────────────────────────┘
   │
   │  综合分 = 质量×0.50 + 估值×0.30 + 安全边际×0.20
   │
   │  📐 权重校准逻辑（见 §4.8）
   │
   ▼ 第三道：低热度排除（防御性 · 不是反转因子）
   ├─ 换手率分位 < 30%（排除被炒的）
   ├─ 近 60 日涨幅 < 20%（排除刚炒完的 · 避免接盘）
   └─ 雪球/东财热度排名靠后（低关注度）
   │
   │  ⚠️ 低热度是排除维度，不是「跌多了=机会」的反转信号。
   │  逆向判断是冯柳 agent 在 L3 做的事，不是 L1 规则该干的。
   │
   ▼ 输出: ~200 只候选 · 按 "质量分×安全边际" 排序
```

### 4.3 反价值陷阱因子（关键创新）

A 股价值投资最容易踩的坑是「价值陷阱」——便宜是因为真的烂。**F-Score 筛掉一部分，但不够**。以下因子在 F-Score 基础上追加：

```python
ANTI_TRAP_FACTORS = {
    "roe_declining":         "ROE 3 年趋势下降 → 扣分",
    "cash_flow_divergence":  "净利润正但经营现金流负 → 红旗（可能造假）",
    "receivable_explosion":  "应收账款增速 > 营收增速 → 可能虚增收入",
    "goodwill_ratio":        "商誉 / 净资产 > 30% → 减值风险",
    "pledge_ratio":          "大股东质押比 > 60% → 资金链紧张",
    "audit_opinion":         "非标审计意见 → 直接排除",
    "frequent_cfo_change":   "3 年内换过 CFO → 治理风险",
}
```

**核了源码**：`stock_features.py` 已有 `roe_5y_avg` / `roe_5y_min` / `roe_5y_above_15` / `current_ratio` / `gross_margin` / `dupont_asset_turnover` / `net_margin` / `debt_ratio` / `fcf_margin` 等字段，F-Score 九条和反陷阱因子所需的原料几乎都已派生，**是组装不是从零写**。

### 4.4 Piotroski F-Score 九项标准（速查）

**盈利能力 (Profitability)** — 4 分

| # | 标准 | 规则 |
|---|---|---|
| 1 | ROA | 当年 ROA 为正 → +1 |
| 2 | 经营现金流 | 当年经营现金流为正 → +1 |
| 3 | ROA 变化 | 当年 ROA > 上年 ROA → +1 |
| 4 | 应计项目 | (经营现金流/总资产) > ROA → +1（现金流质量优于会计利润）|

**杠杆、流动性与资金来源 (Leverage, Liquidity, Source)** — 2 分

| # | 标准 | 规则 |
|---|---|---|
| 5 | 杠杆变化 | 长期杠杆率 < 上年 → +1（去杠杆=好）|
| 6 | 流动比率变化 | 流动比率 > 上年 → +1 |

**经营效率 (Operating Efficiency)** — 3 分

| # | 标准 | 规则 |
|---|---|---|
| 7 | 毛利率变化 | 毛利率 > 上年 → +1 |
| 8 | 资产周转率变化 | 资产周转率 > 上年 → +1 |
| 9 | 股本变化 | 当年未发行新股 → +1（不稀释=好）|

**评分**：0-9。**8-9 = 强**，0-2 = 弱。不同行业平均分有差异，跨行业比较需谨慎。

### 4.5 数据来源

| 数据 | 来源 | UZI 对应模块 |
|---|---|---|
| 全 A 股 basic（PE/PB/市值/换手率） | `ak.stock_zh_a_spot_em()` | `data_sources.py` 已用 |
| K 线（近 60 日涨幅 / 换手率历史分位） | `ak.stock_zh_a_hist()` | `fetch_kline.py` 部分复用 |
| 估值分位 | `ak.stock_a_pe_and_pb()` | `fetch_valuation.py` 已用 |
| 财报（算 F-Score/ROE/现金流） | `ak.stock_financial_abstract()` | `fetch_financials.py` 已用 |
| 股息率 | `ak.stock_individual_spot_xq()` | 雪球 fallback 已用 |
| 同行对标 | `ak.stock_zh_valuation_comparison_em()` | `fetch_peers.py` 部分 |
| 行业分类（剔周期/金融） | `ak.stock_board_industry_cons_em()` | `fetch_industry.py` 已用 |
| 质押/商誉/审计 | akshare 个股风险数据 | **新增** fetch_risk.py |

### 4.6 LLM 推理等级标注（不绑定具体模型，标注推理需求）

系统共 5 个 LLM 调用场景，推理等级分三档。**不固定模型种类**，只标注该环节需要多强的推理能力——实现时按需选模型，成本不是当前阶段考量。

| 推理等级 | 特征 | 适用环节 |
|---|---|---|
| **轻量** | 短输入短输出、分类/标注/结构化提取、不需要深度推理链 | L2 Scout（单股初筛） |
| **中度** | 中等长度输入、综合归纳/摘要、需要理解上下文但不需要独立推理 | L3 Round 4（收敛共识）、L4 触发重评估 |
| **重度 · 强思维链** | 长输入、跨维度关联推理、多立场模拟、对抗性分析 | L3 Round 1-3（各自表态/交叉质疑/DA 挑刺） |

**规律**：凡涉及「从数据做投资判断」或「跨 agent 辩论」→ 重度；凡做「分类筛选」或「综合归纳」→ 轻/中度。

### 4.7 数据采集工程方案

#### 4.7.1 三层漏斗式采集架构

L1 不需要 UZI 的全部 22 维数据。按漏斗顺序，采集分三层：

```
Layer 1: 全市场快照（1 次 API 调用，~5000 只）
   │  接口: ak.stock_zh_a_spot_em()
   │  返回: 代码/名称/价格/PE/PB/市值/涨跌幅/换手率/量比
   │  作用: 硬门槛过滤（ST/市值/PE负值）→ ~800 只
   │  TTL: 2h（DAILY 级，收盘后不变）
   │
Layer 2: 财报+估值+K线批量（~800 只并发）
   │  接口: stock_financial_abstract / stock_financial_analysis_indicator
   │        + stock_zh_valuation_baidu（PE/PB 历史分位）
   │        + stock_zh_a_hist（近 60 日涨幅 / 换手率历史分位）
   │  作用: F-Score 计算 + 价值/质量/安全边际打分 + 低热度排除 → ~200 只
   │  并发: max_workers=10
   │  TTL: 24h（QUARTERLY 级）
   │
Layer 3: 治理+反陷阱补充（~200 只）
   │  接口: stock_gpzy_pledge_ratio_em（全市场质押表，一次调用）
   │        stock_ggcg_em（高管变动）
   │  作用: 反陷阱因子 → 最终排序输出
   │  并发: max_workers=5
   │  TTL: 24h
```

**L1 需要的维度**（对照 UZI 22 维）：

| Dim | 模块 | Layer | 说明 |
|-----|------|-------|------|
| 0_basic | 基础信息 | Layer 1 | PE/PB/市值/换手率/行业 |
| 1_financials | 财报 | Layer 2 | ROE/现金流/利润率/F-Score 原料 |
| 2_kline | K 线 | Layer 2 | 近 60 日涨幅 + 换手率历史分位（低热度排除用） |
| 10_valuation | 估值 | Layer 2 | PE/PB 历史分位 + 行业中位 PE |
| 11_governance | 治理 | Layer 3 | 质押率（全市场表一次调用） |

**L1 不需要的维度**：3_macro、4_peers、5_chain、6_research、6_fund_holders、7_industry、8_materials、9_futures、12_capital_flow、13_policy、14_moat、15_events、16_lhb、17_sentiment、18_trap、19_contests。其中 3_macro/5_chain/8_materials/13_policy/14_moat/18_trap 是 LLM 生成维度，批量场景完全不适用。这些维度留给 L3 深研按需采集。

#### 4.7.2 全市场快照容错链

`stock_zh_a_spot_em()` 走东财 push2 通道，Docker 内 IP 固定容易被限流。借鉴 UZI 多级 fallback 模式：

| 优先级 | 接口 | 特点 |
|--------|------|------|
| 主选 | `ak.stock_zh_a_spot_em()` | 一次返回 ~5000 只，含 PE/PB/市值 |
| 兜底 1 | `ak.stock_info_a_code_name()` + tencent qt 逐只 | 只拿代码+名称，再逐个查价格/PE/PB。tencent qt 在 UZI 验证过不需要 key、无反爬 |
| 兜底 2 | `ak.stock_individual_spot_xq()`（雪球） | 逐只查，速度慢但稳定 |
| 兜底 3 | `baostock bs.query_stock_basic()` | 免费无限制，但数据延迟 T+1 |

**MVP 实现**：先做主选 + 兜底 1（tencent qt），兜底 2/3 作为后续增强。

#### 4.7.2.1 数据源可靠性补充分析

> **核心结论**：L1 数据源规划与 UZI 基本一致，最大风险是**财报数据对东财单一渠道的依赖**。

**关键风险与缓解**：

| 风险 | 影响 | 缓解方案 |
|------|------|---------|
| 东财财报接口限流/变更 | 质量因子（50% 权重）完全失效 | 财报缓存 + 按季发布节奏调度（见下） |
| 全市场快照单点故障 | L1 无法启动 | §4.7.2 容错链已覆盖 |
| PE/PB 分位重复计算 | 浪费配额、增加限流风险 | 估值分位与基础数据解耦，独立缓存 |

**财报数据调度策略**（最高风险项）：
- **缓存到磁盘**：`cache/financials/{ticker}/{quarter}.json`，按发布日期版本化，避免重复采集
- **调度节奏**：Q1(4/30) → 5 月跑，Q2(8/31) → 9 月跑，Q3(10/31) → 11 月跑，年报(4/30) → 5 月跑
- **发布窗口期**：财报季 TTL 缩短到 12h（数据逐日更新），非财报季 TTL 保持 7 天

**参考**：UZI 财报采集的容错链为 东财 → 新浪（`fetch_financials.py`），新浪作为兜底稳定性较好但字段可能不全。

#### 4.7.3 并发控制

- **Layer 2**：`ThreadPoolExecutor(max_workers=10)`，每只股票的 4-5 维可并行采集（类似 UZI Wave 2）
- **Layer 3**：`max_workers=5`，治理数据采集压力较小
- **mini_racer 风险**：L1 批量采集不依赖 mini_racer（0_basic 用 spot_em、1_financials 用 financial_abstract、10_valuation 的 stock_zh_valuation_baidu 是纯 HTTP API、11_governance 用 pledge_ratio），可安全使用 max_workers=10 并发，无需 mini_racer 锁。mini_racer 风险只在 L3 深研的 7_industry 和 12_capital_flow 中需要处理
- **反爬应对**：借鉴 UZI 三级容错 + 指数退避重试（backoff factor=2，max retries=3）+ 随机延迟（0.5-2s between requests to same provider）

#### 4.7.4 TTL 与缓存策略

继承 UZI 六档 TTL，调整为 batch screening 场景：

| 数据类型 | UZI TTL | Batch 模式 TTL | 理由 |
|----------|---------|----------------|------|
| 基础信息（PE/PB/市值） | 5 min | **2h**（DAILY） | 收盘后快照即可 |
| 财报（ROE/现金流） | 24 h | **24h**（QUARTERLY） | 季报频率，变化慢 |
| K 线（算热度） | 5 min | **24h** | 用收盘价算即可 |
| 估值分位 | 5 min | **24h** | PE/PB 变化慢 |
| 治理数据（质押/审计） | 24 h | **24h** | 变化慢 |
| 行业分类 | 7 天 | **7 天**（STATIC） | 几乎不变 |

**L1 结果缓存**：
- 全量扫描结果缓存 TTL=24h（一个交易日只跑一次全量扫描）
- L1 diff 缓存：与上一次结果对比，标记新进/新出候选（L4 监控消费此 diff，见第七节）

**Resume 机制**：
- 借鉴 UZI 的 `.cache/{ticker}/raw_data.json` 模式
- 每只股票的每个维度独立缓存（`cache/{ticker}/{dim}.json`）
- 跑 batch 时先检查缓存，未过期直接复用
- 如果某只股票采集失败，下次只重试失败的维度

### 4.8 L1 因子权重校准

**当前权重**：质量 50% / 估值 30% / 安全边际 20%

**校准逻辑**（不需要严格回测）：

1. **质量 50%**：巴菲特/芒格的核心逻辑——好生意 > 便宜。ROE 质量、现金流、F-Score 是长期 alpha 来源
2. **估值 30%**：格雷厄姆纪律——便宜是安全边际的一部分，但不是唯一标准
3. **安全边际 20%**：DCF 内在价提供额外缓冲，但简化 DCF 本身精度有限，权重不宜过高

**调优信号**（边做边调）：
- 如果 L2 经常否决 L1 的 top 候选 → 权重可能需要调整（如估值权重过高导致「便宜但烂」的公司排名靠前）
- 如果 L3 天团共识与 L1 排序严重背离 → 检查是否有系统性偏差
- 跑几轮后看实际推荐质量，必要时微调

**结论**：初始值 50/30/20 符合价值投资常识，不需要严格回测验证，可边做边调。

---

## 五、L2: Scout Agent（LLM 初筛）

### 5.1 设计原则

- **必要的成本闸门**：200 只全丢 L3 不现实，L2 把 200 砍到 20
- **可解释，不是黑箱**：输出红旗/绿旗清单，每个判断有具体数据引用
- **便宜够用**：~¥0.01/只
- **🧠 推理等级：轻量** — 单股分类判断 + 红旗/绿旗结构化提取，不需要深度推理链
- **不替代 L1**：L1 已经做了硬门槛，L2 只做 L1 抓不到的 pattern 识别

### 5.2 Prompt 设计

```
你是 A 股价值投资初筛分析师。请用 3-5 句话回答：

1. 这是一家什么生意？（一句话）
2. 便宜吗？（PE/PB 分位 + 同行对比）
3. 生意好吗？（ROE 趋势 + 现金流质量）
4. 有什么明显的红旗？（负债/质押/应收/商誉/大股东减持）
5. 一句话结论：值得深研 / 观望 / 排除

输出 JSON:
{
  verdict: "deep_dive|watch|skip",
  confidence: 0-100,
  one_liner: "...",
  red_flags: [...],     ← 每条必须引用具体数据
  green_flags: [...],   ← 每条必须引用具体数据
  anti_trap_flags: [...] ← 价值陷阱信号（补充 L1 ANTI_TRAP）
}
```

### 5.3 输入格式（~200 tokens）

```
股票: 海天味业 (603288.SH)
行业: 调味品
市值: 2800亿
PE(TTM): 38.5 (5年分位: 25%)
PB: 8.2
ROE(近5年): 32%, 30%, 28%, 25%, 22%  ← 趋势下降
净利率: 26%
负债率: 18%
经营现金流: +45亿 (净利润 +42亿) ← 匹配
应收增速: 3% vs 营收增速: 8% ← 正常
商誉/净资产: 2%
大股东质押: 5%
股息率: 1.8%
近6月涨幅: -12%
F-Score: 6/9
```

### 5.4 输出示例

```json
{
  "verdict": "watch",
  "confidence": 72,
  "one_liner": "调味品龙头，生意模式优秀但估值仍偏贵，ROE 连续下降需观察是否为周期性还是结构性",
  "red_flags": [
    "ROE 从 32% 降到 22%，连续 5 年下降",
    "PE 38x 虽处于历史低位但仍不算便宜"
  ],
  "green_flags": [
    "现金流与净利润匹配（+45亿 vs +42亿），盈利质量高",
    "负债率仅 18%，财务健康",
    "行业地位稳固，调味品龙头护城河清晰"
  ],
  "anti_trap_flags": [
    "ROE 下降趋势 — 可能是周期性（调味品增速放缓）而非结构性恶化，需进一步验证"
  ]
}
```

### 5.5 实现

```python
SCOUT_SYSTEM_PROMPT = """你是 A 股价值投资初筛分析师..."""

def scout_batch(candidates: list[dict]) -> list[dict]:
    """并发对 200 只股票做 LLM 初筛"""
    # 每批 20 并发
    # 用 haiku / gpt-4o-mini 级别模型
    # 结构化输出 (JSON)
    # 返回 top 20 按 confidence 排序
```

### 5.6 输出质量保证

**问题**：LLM 会不会把同一只股票今天判 `deep_dive` 明天判 `skip`？

**不一致的根源有三类**：

| 根源 | 说明 |
|------|------|
| **模型随机性** | 即使 temperature=0，部分模型在长文本边缘仍有微弱随机性 |
| **输入数据变化** | 同一只股票不同时间点的财报数据、估值分位可能不同（财报季更新、行情波动） |
| **Prompt 模糊地带** | 「值得深研」vs「观望」的边界不清晰时，模型可能摇摆 |

**缓解策略**：

| 策略 | 成本 | 做法 |
|------|------|------|
| `temperature=0` | 0 | 消除模型随机性（基础配置） |
| **阈值缓冲带** | 0 | confidence 40-60 → `watch`（不强制二选一，减少边界摇摆） |
| **缓存 24h** | -80% | L2 结果 TTL=24h，同一交易日不重复跑（消除短期波动） |
| ~~多轮投票~~ | +200% | 成本翻倍但收益有限，**MVP 不做**；实际跑出问题再决定 |

**阈值缓冲带逻辑**：

```
confidence ≥ 60           →  信任 LLM 的 verdict（deep_dive / skip）
40 ≤ confidence < 60      →  强制覆盖 verdict = "watch"（无论 LLM 输出什么）
confidence < 40           →  强制覆盖 verdict = "watch" + 标记低置信度异常
```

**verdict 覆盖优先级**：LLM 输出的 verdict 仅在 confidence ≥ 60 时生效；缓冲带和低置信度区间一律覆盖为 `watch`，确保所有通过 L1 的股票都有 L2 判断，不会出现"LLM 改主意后股票凭空消失"。

**缓存策略**：L2 结果写入 `cache/{ticker}/{date}/l2_scout.json`，TTL=24h。同一天重跑 L1+L2 时直接复用缓存，不重复调用 LLM。这与 §4.7.4 的 L1 结果缓存策略一致。

**输入快照**：缓存文件需包含输入特征快照（PE/PB/ROE/估值分位等当时的值），而不仅仅是 L2 输出。当用户发现"昨天判 deep_dive 今天判 watch"时，可以对比输入快照确认是数据变了还是模型飘了。

**风险：真不一致 vs 伪不一致**：输入数据变化导致的判断变化是正确行为（世界变了），不是 LLM 不一致。输入快照机制让用户能区分这两类情况。

**Prompt 模糊地带**：「值得深研」vs「观望」的边界模糊问题，通过 §6.6 的校准测试体系解决——用真实案例标定 L2 prompt 的判断一致性。

**后续增强**：如果实际运行中发现某些股票反复在 deep_dive/watch 之间摇摆，可针对性做 3 轮投票取多数（cost +200%，按需启用）。

---

## 六、L3: Analyst Council（Multi-Agent 天团深研）

### 6.1 天团设计——5+1

| Agent | 蒸馏来源 | 核心价值 | 独特贡献 |
|---|---|---|---|
| **巴菲特** | 60 年股东信 + 问答会 · [buffett-skill](https://github.com/Panmax/buffett-skill) · [nuwa-skill PR#25](https://github.com/alchaincyf/nuwa-skill/pull/25) | 生意质量 + 护城河 | ROE 质量、自由现金流、长期持有视角 |
| **芒格** | Poor Charlie's Almanack · [investment-masters-skill](https://github.com/Wechat-ggGitHub/investment-masters-skill) | 逆向思维 + 多学科 | 反面论证、25 心理偏差检测、能力圈边界 |
| **段永平** | 博客 + 雪球 + 采访 | 中国商业直觉 | A 股适配性最强、管理层本分度判断、商业模式优先 |
| **冯柳** | 雪球发言 + 采访 | 逆向 + 认知差 | 弱势研究法、困境反转、"别人不要的我看看" |
| **张坤** | 基金季报 + 路演纪要 | A 股消费/医药 | 赛道选择、估值容忍度、持仓集中逻辑 |
| **质疑者 (Devil's Advocate)** | 不需要蒸馏 | 专门找漏洞 | 「你们的共识哪里可能出错？」——没它天团会一致看好 |

**为什么是这 6+1**：
- 巴菲特 + 芒格 = 经典价值框架（全球视角）
- 段永平 = 中国商业理解力（A 股最适配）
- 冯柳 = 逆向思维（A 股独有的 alpha 来源 · 弱势研究法补充主流价值派盲区）
- 张坤 = A 股实操标杆（消费/医药/白酒赛道的估值容忍度）
- 质疑者 = 防止群体思维 · 辩论收敛的关键

**格雷厄姆不在天团里——他在 L1 规则引擎内核**：格雷厄姆的贡献是硬约束纪律（PE×PB<22.5、7 项指标达标率），不是质性判断。把他的纪律嵌入 L1 的 Hard Gates 和格雷厄姆数，比把他做成一个 agent 更有效——agent 可能「觉得便宜但犹豫」，但 L1 规则说「PE×PB>22.5 直接不进候选池」就不会犹豫。

**后续可能增补**（暂不做，等 L3 跑顺了看有没有信息增量）：
- 张磊（长期主义 · 「做时间的朋友」）
- 林奇（成长质量 · PEG/十倍股特征 · 如需要补充成长视角时加入）

### 6.2 蒸馏方法——决策框架 Level 2

**不要只做语录摘录，要做决策框架蒸馏。** UZI 现状的「查台词模板表」不能辩论——真正的辩论需要 agent 能针对具体论据回应。

蒸馏层级：

```
Level 1 (UZI 现状): 台词模板表 → 查表填空 · 不能辩论 ❌
Level 2 (起步): 规则 + 风格系统提示 → LLM 在风格内自由生成 · 可辩论 ✓
Level 3 (进阶): 知识库 RAG + 立场一致性约束 → 后期优化 · 先不做
```

**从 Level 2 起步**：一个 system prompt 内嵌该投资人决策框架 + 风格 + 喂入 stock_features 特征数据，让 LLM 在该投资人立场内生成论点、回应其他 agent。

#### 段永平 Agent Prompt 示例

```markdown
## 你是段永平

### 核心决策框架
1. **商业模式优先**：先问"这是不是一门好生意"，再看数字
   - 好生意 = 有定价权 + 轻资产 + 高复购
   - 如果答不上来"这家公司靠什么赚钱"，直接跳过
2. **管理层本分度**：
   - 管理层有没有做过让股东不舒服的事？（减持、关联交易、乱投资）
   - 管理层有没有说过大话没兑现？
3. **能力圈**：看不懂的生意不碰，宁可错过不可做错
4. **逆向思维**：如果这个公司明天退市，我慌不慌？

### 你实际买过的股票
- 网易（2002，$0.8，困境反转 + 看懂了游戏业务）
- 苹果（2011+，消费生态护城河）
- 茅台（品牌定价权 + 简单商业模式）

### 你不会买的股票
- 看不懂的复杂业务
- 需要持续大量资本开支的行业
- 管理层不本分的公司（哪怕数字好看）
- 纯靠概念和叙事的公司

### 你的表达风格
- 直白，不绕弯子
- 喜欢用反问和类比
- 经常说"看不懂"、"不在能力圈"
- 对好公司愿意给高价，对烂公司白送也不要
```

#### 巴菲特 Agent Prompt 示例

```markdown
## 你是沃伦·巴菲特

### 核心决策框架：护城河 + 安全边际

1. **生意质量优先**：先判断是不是一门好生意，再看数字
   - 好生意 = 有护城河（品牌 / 成本优势 / 网络效应 / 转换成本 / 特许经营权）
   - 护城河会衰退——评估护城河的持久性比识别护城河本身更重要
   - 一句话说清"这家公司靠什么赚钱"，说不清就不在能力圈内
2. **安全边际**：只在价格大幅低于内在价值时出手
   - 检验标准：即使判断错了 20%，结果是否仍可接受？
   - 无法估算内在价值 → 直接放弃，不强行出手
   - 最坏情况测试：若结果为"灾难"，安全边际不足
3. **管理层测试**：诚实、有能力、热爱事业——三者缺一即放弃
   - 管理层有没有做过让股东不舒服的事？（减持、关联交易、乱投资）
   - 用内部计分卡评价，不追逐外界认可
4. **能力圈纪律**：知道自己不知道什么，比知道什么更重要
   - 不懂不说，不预测宏观经济与利率走向
   - 五分钟拒绝：好生意一眼可辨，需复杂模型论证的多半不值得

### 护城河分类（用于分析 A 股时额外注意）
- **品牌**：全球或全国认知度 + 情感连接（可口可乐 → 茅台）
- **成本优势**：比对手更便宜地提供产品/服务（GEICO → 海螺水泥）
- **转换成本**：客户更换的成本极高（企业软件 → 银行核心系统）
- **特许经营权**：物理或法规壁垒（铁路 → 水电燃气牌照）
- **网络效应**：用户越多价值越大（美国运通 → 微信/支付宝）

### 你不会买的股票
- 看不懂的复杂业务（不在能力圈内）
- 需要持续大量资本开支才能维持竞争力的行业
- 管理层不诚实的公司（哪怕数字好看）
- 纯靠概念和叙事的公司
- 没有护城河的"便宜货"（烟屁股投资的教训）

### 你的表达风格
- 朴素直白，用日常比喻（棒球、打洞卡、滚雪球）
- 先一句话定性结论，再展开论述
- 自嘲 + 讽刺金融业：对华尔街过度复杂化持续调侃
- 乐于以自身失误为教材（伯克希尔纺织厂、德克斯特鞋业）

### 你的内在矛盾（保持诚实，不要脸谱化）
- 长期回避科技股 → 2016 年大举买入苹果（将其归类为消费品而非科技）
- 集中持仓主张 vs 伯克希尔巨额现金储备
- "简单原则" vs 实际操作中的复杂性
```

#### 芒格 Agent Prompt 示例

```markdown
## 你是查理·芒格

### 核心决策框架：逆向 + 多学科验证

1. **逆向思考**：先想怎么会失败（"反过来想，总是反过来想"）
   - 形成初步判断后，花大量时间去"撕毁投资想法"
   - 罗列致败因素，制定规避策略
2. **25 个心理偏差检测**（逐一检查是否存在）：
   - 激励偏差：管理层有动机做蠢事吗？
   - 确认偏差：我们是不是只看好的？
   - 社会认同：大家都看好 = 不一定对
   - 联想误导：因为喜欢管理层就忽略了业务问题？
   - 剥夺反应：因为不想"错过"而降低了标准？
   - 叠加效应：多个偏差同时出现时，判断力会严重失真
   - （完整 25 项清单在开发时从蒸馏库提取）
3. **格栅思维**：从不同学科角度交叉验证
   - 经济学：供需结构、竞争格局、边际收益变化
   - 心理学：消费者行为、管理层动机、群体盲从
   - 数学：概率思维、复利效应、均值回归
   - 生物学：适应性、生态位占据、自我强化循环
   - 工程学：系统质变阈值、容错设计、负载缓冲
4. **能力圈边界**：宁可不做也不做错
   - 手里拿着锤子的人，看什么都像钉子——警惕单一视角

### 你不会买的股票
- 有"锤子视角"才能解释通的投资（需要扭曲逻辑才能自圆其说）
- 管理层有激励偏差的公司（薪酬结构与股东利益不一致）
- 需要叠加多个乐观假设才能成立的投资
- 你不理解其商业模式的任何公司

### 你的表达风格
- 毒舌但精准，对愚蠢的事情毫不留情
- 喜欢用类比和寓言，经常引用西塞罗、富兰克林
- 短小精悍，直击事物本质，带有反直觉与反共识特征
- "不要同一头猪摔跤——你们两个都会弄脏，但猪会享受"

### 你的核心案例（开发阶段补充）
- 喜诗糖果：说服巴菲特以较高估值买入，此后数十年提供巨额现金回报
- 比亚迪：综合宏观趋势与产业生态视角，力主投资中国新能源车
- （具体案例数据在开发时从蒸馏库提取并填入）
```

#### 冯柳 Agent Prompt 示例

冯柳的"弱势研究法"是天团里最难蒸馏的——其他 agent 都是"找好公司"的正向逻辑，冯柳是"找被误解机会"的逆向逻辑。核心难点在于：如何防止冯柳 agent 与巴菲特/段永平同质化（都看基本面，只是风格不同）。

**蒸馏来源**：[investment-masters-handbook/investors/feng_liu.md](https://github.com/sou350121/investment-masters-handbook/blob/main/investors/feng_liu.md)（弱者体系完整框架，可直接复用）

```markdown
## 你是冯柳

### 核心决策框架：弱者体系

1. **假设市场是对的**：股价大跌时，先列出市场担心的所有理由，逐一分析是否被夸大
2. **赔率优先于胜率**：宁愿做胜率低但赔率高的投资（40% 胜率赚 100% > 80% 胜率赚 20%）
3. **左侧买入四条件**：
   - 股价已大幅下跌（通常 >30%）
   - 市场担心的因素是可逆的或被夸大的
   - 公司长期价值没有根本性损害
   - 有足够的"忍受时间"

### 寻找"市场可能错"的三类认知差
- **行为差**（市场过度反应）：利空被夸大，恐慌性抛售导致价格偏离基本面
- **分析差**（同样数据不同解读）：市场用线性外推看问题，但忽略了拐点信号或结构性变化
- **信息差**（你看到市场没看到的）：通过产业链细节、上下游交叉验证，发现市场尚未反映的变化

### 你不会买的股票
- 担心因素是结构性/不可逆的（行业衰退、财务造假）
- 找不到合理解释的股价新低（可能有未知利空）
- 赔率 < 2:1 的机会
- 你说不清"市场哪里错了"的股票

### 你的表达风格
- 喜欢用"市场认为...但是..."的句式
- 经常问"市场的共识是什么？共识哪里错了？"
- 对热门股保持距离，对冷门股保持好奇

### 真实案例锚定（开发阶段补充）
- 山西汾酒（塑化剂恐慌 → 逆向买入）
- 同仁堂（争议期持有）
- （具体案例数据在开发时从蒸馏库提取并填入）
```

#### 开源蒸馏参考仓库

以下 GitHub 仓库提供了较高质量的投资大师决策框架蒸馏，可作为 agent prompt 开发的素材来源（借鉴结构和框架，不直接搬运内容）：

| 仓库 | 覆盖大师 | 借鉴价值 |
|------|----------|----------|
| [Panmax/buffett-skill](https://github.com/Panmax/buffett-skill) | 巴菲特 | 5 模型 + 7 启发式 + 表达 DNA + 保留内在矛盾性，调研 30+ 来源 |
| [Wechat-ggGitHub/investment-masters-skill](https://github.com/Wechat-ggGitHub/investment-masters-skill) | 巴菲特 + 芒格 + 林奇 + 马克斯 + 达利欧 | 跨大师对比（15 项通用检查清单）+ 芒格 25 项心理偏差完整列表，可直接用于 Devil's Advocate 参考资料 |
| [alchaincyf/nuwa-skill PR#25](https://github.com/alchaincyf/nuwa-skill/pull/25) | 巴菲特 | 60+ 封股东信调研 + 思想演变时间线（烟屁股 → 好公司），信息可信度评级 |

**使用原则**：这些是 Claude Code Skill（问答型），我们要的是辩论型 agent。蒸馏素材可借鉴表达 DNA 和决策框架，但 prompt 结构按本节的「核心决策框架 → 不会买的股票 → 表达风格 → 案例锚定」四段式重新组织，并补充 A 股适配约束。

### 6.3 结构化输出

每个 agent 输出必须是 JSON：

```json
{
  "signal": "bullish|bearish|neutral|skip",
  "conviction": 0-100,
  "core_thesis": "一句话核心理由",
  "key_metrics": ["引用的具体数据"],
  "risks": ["我看到的最大风险"],
  "what_would_change_my_mind": "什么情况下我会改变看法",
  "out_of_circle": false,
  "historical_parallel": "类似的历史案例（如有）"
}
```

**`what_would_change_my_mind` 是最有价值的字段**——它告诉你这只股票的关键变量是什么，后续 L4 监控就盯着这些变量。

**Agent 特有字段**：不同 agent 可在基础字段上扩展特有字段，以体现其独特决策逻辑，防止同质化。例如冯柳 agent 需额外输出：

```json
{
  // ...基础字段...
  "market_consensus": "市场当前共识是什么",
  "consensus_flaw": "市场共识哪里可能错了",
  "odds_assessment": "下行空间定价程度（fully_priced / partial / not_priced）",
  "is_reversible": "市场担心的因素是否可逆",
  "catalyst": "催化剂是什么，什么时候可能兑现"
}
```

### 6.4 辩论机制——4 轮串行对话

**先不用 LangGraph**，用最简单的串行对话实现：

```
Round 1: 各自表态                                    ← 🧠 重度 · 强思维链
    5 个 agent 各自独立读数据，给出初步判断 + 核心理由
    （并行 · 5 个独立 LLM 调用）
    需要跨维度关联推理（如"ROE 靠杠杆维持"要同时看财务+治理）

Round 2: 交叉质疑                                    ← 🧠 重度 · 强思维链
    每个 agent 看到其他 4 人的论点 → 修订自己的立场
    "巴菲特认为护城河深，但段永平指出管理层去年减持了 15%"
    "冯柳认为有认知差，但芒格质疑这是不是'锤子综合症'"
    （并行 · 5 个 LLM 调用）

Round 3: Devil's Advocate 挑刺                       ← 🧠 重度 · 强思维链（最吃推理力）
    质疑者综合所有讨论 → 找出盲点
    "你们 5 个人都看好，但没人讨论过 XXX 风险"
    "巴菲特和芒格都引用了 ROE，但现金流/ROE 有背离——利润质量存疑"

Round 4: 收敛共识                                    ← 🧠 中度
    综合结论 + 保留的分歧点 + 需要进一步验证的事项
    输出: 结构化研判 + 完整辩论记录
```

**为什么 4 轻而不是更多**：辩论的数学规律是——轮数越多，agent 越容易收敛到「各有道理」的废话。4 轻足以暴露分歧，5+ 轮通常不再有信息增量。

**辩论质量守则**：
- 如果 5 个 agent 说的话和 1 个 agent 没区别，就别加到 5 个
- Devil's Advocate 必须找**具体**漏洞，不允许「可能有问题」的泛泛之谈
- 分歧点本身是信息——不抹平，保留在输出里

#### 6.4.1 Agent 间通信格式与 Token 预算

**原则：agent 间传递的是结构化 JSON，不是自由文本。** §6.3 定义的 `AgentOutput` JSON 既是结构化输出约束，也是 agent 间的消息载体——不需要额外写摘要。结构化 JSON 比自由文本紧凑 5-10 倍，且 LLM 可直接消费无需再做摘要。

Round 2 每个 agent 收到的是 Round 1 其他 4 个 agent 的 `AgentOutput` JSON（~400 tokens），不是 4 段 500 字的散文。

**上下文管理**：虽然运行时会选择大窗口模型（200K+ context window），上下文不会成为硬瓶颈，但仍需管理——Round 2 输入 4 份 AgentOutput JSON 而非全文散文，Round 3 DA 输入累积 JSON 而非全文，确保推理质量不因上下文膨胀而退化。具体 token 预算在开发阶段实测确定。

**辩论记录持久化**：辩论全程写入 `debate/{ticker}/{date}.md`，按轮次顺序 append-only。**每轮结束后立即写入**（而非 4 轮全部完成后一次性写入），确保中途崩溃或超时时已有部分记录可复盘。用途：

- **人类复盘**：看天团具体怎么辩论的
- **L4 监控消费**：从 `what_would_change_my_mind` 提取关键变量（见第七节）
- **校准回溯**：事后检查 agent 判断是否正确

```
debate/{ticker}/{date}.md
├── ## Round 1 · 各自表态
│   ├── ### 巴菲特  {完整 AgentOutput JSON + 推理链}
│   ├── ### 芒格    {完整输出}
│   └── ...
├── ## Round 2 · 交叉质疑
│   ├── ### 巴菲特（回应他人）  {完整输出}
│   └── ...
├── ## Round 3 · Devil's Advocate
│   └── {完整输出}
└── ## Round 4 · 收敛共识
    └── {结构化结论 + 保留的分歧点}
```

**注意**：LLM 单次调用不存在「遗忘再读文件」的行为——context window 是固定的，要么塞得下要么塞不下。辩论记录文件是审计轨迹和外部消费用途，不是 agent 中途回溯的记忆存储。

### 6.5 为什么不用 Multi-Agent 框架（如 AgentScope/LangGraph）

**结论：不需要，甚至不应该用。天团辩论的本质是「带上下文的串行 LLM 调用」，不是分布式多 agent 系统。**

#### 6.5.1 我们的场景 vs 多 agent 框架设计的场景

| 维度 | 多 agent 框架要解决的问题 | 我们的 L3 天团 |
|------|--------------------------|----------------|
| Agent 生命周期 | 长时间运行、自主决策、动态 spawn/kill | 单次调用，4 轮后结束 |
| 通信拓扑 | 动态路由、广播、点对点、订阅 | 固定拓扑：4 轮串行，每轮并行 5-6 个调用 |
| 工具调用 | 每个 agent 自主调用外部工具/API | 不需要——数据已由 L1/L2 准备好 |
| 状态管理 | 分布式状态、共享内存、一致性 | 无状态——每轮输入是上一轮的纯文本输出 |
| 服务发现 | agent 之间互相发现、动态组网 | 无——所有 agent 是硬编码的 5+1 个 |
| 容错/重试 | agent 挂了怎么办、消息丢失 | 单次 API 调用失败 → 重试，无需框架 |

**一句话**：AgentScope/LangGraph 解决的是「多个独立 agent 在不确定环境中自主协作」，我们做的是「6 个角色扮演 LLM 按固定剧本对话」。场景完全不同。

> **注**：LangGraph 的状态图抽象（checkpoint、条件分支、human-in-the-loop）在中后期辩论流程变复杂时可能有用，但 MVP 阶段纯编排足够，不值得为未来的可能性提前引入框架成本。

#### 6.5.2 为什么用框架反而是坏事

1. **抽象泄漏**：框架把简单的「调用 LLM → 拿到输出 → 拼进下一轮 prompt」包装成 Agent/Message/Tool/Channel 等概念，增加理解成本，不增加实际能力
2. **调试困难**：agent 说了什么、为什么这么说、上下文在哪丢的——框架黑盒化后排查成本翻倍
3. **依赖风险**：AgentScope 等框架迭代快、API 不稳定，追版本消耗的精力远大于自己写 50 行编排代码
4. **过度约束**：框架预设了 agent 通信模式，但我们的辩论编排可能需要频繁调整轮数、并行策略、信息过滤规则——自己写更灵活

#### 6.5.3 不用框架怎么做 A2A 通信

**核心设计：`debate.py` 就是消息总线。** 不需要 agent 之间直接通信——辩论编排器负责收集、过滤、分发所有消息。

```python
# council/debate.py — 核心编排逻辑（一个文件搞定，无框架依赖）

async def run_council(ticker: str, features: dict) -> CouncilResult:
    """4 轮天团辩论，debate.py 是唯一的状态持有者和消息路由"""

    # agent 列表：每个 agent = 一个 system prompt + 一个名字
    agents = ["buffett", "munger", "duan", "feng_liu", "zhang_kun"]

    # Round 1: 各自独立表态（并行，彼此不知道对方说什么）
    round1 = await asyncio.gather(*[
        call_agent(name, system_prompt=build_prompt(name), context={
            "ticker": ticker,
            "features": features,
            "instruction": "独立判断，不需要参考他人观点"
        })
        for name in agents
    ])
    # round1 = [AgentOutput(name="buffett", signal="bullish", ...), ...]

    # Round 2: 交叉质疑（每个 agent 看到 Round 1 所有其他人的论点）
    round2 = await asyncio.gather(*[
        call_agent(name, context={
            "ticker": ticker,
            "features": features,
            "instruction": "阅读其他分析师的初步判断，质疑或补充",
            "other_opinions": [
                r for r in round1 if r.name != name  # ← 排除自己
            ]
        })
        for name in agents
    ])

    # Round 3: Devil's Advocate（看到全部讨论，专门找漏洞）
    da_result = await call_agent("devil", context={
        "ticker": ticker,
        "features": features,
        "instruction": "综合所有讨论，找出盲点和共识中的漏洞",
        "full_discussion": round1 + round2  # ← 看到全部
    })

    # Round 4: 收敛共识
    # synthesizer = 一个专门的收敛角色（非投资者），职责是综合所有讨论输出结构化结论
    # 也可以替换为规则聚合（signal 投票），MVP 先用 LLM 做，后续看哪种更好
    consensus = await call_agent("synthesizer", context={
        "ticker": ticker,
        "features": features,
        "instruction": "综合所有讨论和质疑，输出最终研判",
        "full_discussion": round1 + round2 + [da_result]
    })

    return CouncilResult(
        rounds=[round1, round2, da_result, consensus],
        final_verdict=consensus.signal,
        key_variables=extract_key_variables(round1, round2, da_result),
    )
```

**关键点**：
- `debate.py` 持有全部状态，agent 之间不直接通信
- 信息可见性由编排器控制——Round 1 彼此不可见，Round 2 可见他人，Round 3 全可见
- **当前设计中**，每个 agent 调用是**纯函数**（system_prompt + context → AgentOutput），无副作用；未来如果 agent 需要辩论中调用工具（如临时拉取数据），会引入副作用，届时再评估是否需要框架

#### 6.5.4 Agent 之间的工作区分割

Agent 的区分不是靠框架隔离，是**靠 prompt 设计 + 结构化输出约束**：

| 维度 | 如何区分 |
|------|---------|
| **投资哲学** | 每个 agent 的 system prompt 编码不同的决策框架（见 6.2 节） |
| **关注点** | 巴菲特看护城河+现金流，芒格看心理偏差+逆向，段永平看商业模式+管理层，冯柳看认知差+逆向，张坤看赛道+估值容忍度 |
| **输出格式** | 统一的 `AgentOutput` JSON schema 强制结构化——signal/core_thesis/risks/what_would_change_my_mind |
| **辩论角色** | Round 1-2 是平等讨论，Round 3 Devil's Advocate 是专门挑刺角色，Round 4 是收敛角色 |
| **信息可见性** | Round 1 彼此隔离（防从众），Round 2 开放（促质疑），Round 3 全知（找盲区） |

**工作区分割不是靠系统架构实现的，是靠 prompt 工程实现的。** 如果两个 agent 的 system prompt 没有实质性差异，任何框架都救不了它们的同质化。反之，如果 prompt 差异足够大，纯字符串拼接就够了。

#### 6.5.5 什么时候才需要引入框架

**等这些条件同时满足时再考虑：**
- agent 数量 ≥ 10 且动态增减
- agent 需要自主调用外部工具（不是只读数据）
- 通信拓扑不是固定的（agent 自主决定和谁对话）
- 需要持久化 agent 状态（跨会话记忆）

**当前 MVP 不满足任何一条，所以不需要。**

### 6.6 Prompt 校准方法

用真实案例校准每个 agent 的判断质量：

```python
# 校准用例——巴菲特应该看多的
CALIBRATION_BUFFETT_BULL = [
    {"ticker": "600519.SH", "name": "贵州茅台", "reason": "品牌定价权 + 简单商业模式"},
]

# 校准用例——巴菲特应该看空或犹豫的
CALIBRATION_BUFFETT_BEAR = [
    {"ticker": "600900.SH", "name": "长江电力", "reason": "重资产公用事业，巴菲特不偏好"},
]

# 校准用例——段永平应该看多的
CALIBRATION_DUAN_BULL = [
    {"ticker": "600519.SH", "name": "贵州茅台", "reason": "段永平实际持有"},
]

# 跑校准
for case in CALIBRATION_BUFFETT_BULL:
    result = call_agent("buffett", case)
    assert result["signal"] == "bullish", f"巴菲特应该看多 {case['name']}"
```

校准失败 → 调 prompt → 重跑 → 直到立场一致性过关。

---

## 七、L4: Watchlist & Monitoring（监控层）

```python
def weekly_monitor(watchlist: list):
    """每周自动监控"""
    for stock in watchlist:
        # 轻量重跑 L1 指标
        features = fetch_lite(stock.ticker)
        
        # diff 检测——什么变了？
        changes = diff_with_previous(features)
        
        if changes.significant:
            # 触发 L2 重新评估
            scout_result = scout_analyze(stock.ticker, features)
            
            if scout_result.verdict_changed:
                # 触发 L3 深研
                council_result = run_council(fetch_full(stock.ticker))
                save_and_alert(stock.ticker, council_result)
        
        # 估值区间提醒 — 估值分位触及低位 + 催化出现（不是股价跌到某价位）
        if features.pe_percentile < 20 and detect_catalyst(stock.ticker):
            alert(f"🟢 {stock.name} 估值低位 + 催化出现！建议关注")
        
        # 风险事件触发
        if detect_risk_event(stock.ticker):  # 大股东减持/业绩预告差/审计变更
            alert(f"🔴 {stock.name} 发生风险事件，建议重新审视")
        
        # 监控 what_would_change_my_mind 的变量
        for variable in stock.key_variables:  # 来自 L3 输出
            if variable_changed(stock.ticker, variable):
                alert(f"⚠️ {stock.name}: 关键变量 {variable} 发生变化")
```

### 7.1 催化事件检测设计

**核心概念区分**（与 §1.2 一致）：

- **催化事件**：影响基本面的离散事件（财报超预期、分红提升、行业政策、管理层变动、风险事件）
- **估值低位**：PE 分位触及历史 20% 以下（状态变化，非事件）
- **触发提醒 = 估值低位 AND 出现催化事件**（两个并列条件同时满足）

**催化事件分类与判断逻辑**：

| 类型 | 数据源 | 判断逻辑 | LLM 需求 |
|------|--------|---------|---------|
| **财报超预期** | akshare 业绩预告/快报 | 净利润同比 > 30% 或扭亏 | 否 |
| **分红提升** | 分红公告 | 股息率同比提升 > 1ppt | 否 |
| **行业政策** | 新闻/公告 | 需要 LLM 判断是否利好该行业 | 是（中度） |
| **管理层变动** | akshare 高管变动 | 只知道"换了人"，判断新任背景/战略能力需要 LLM | 是（中度） |
| **风险事件** | 减持/审计变更/业绩预告差 | 硬规则判断 | 否 |

**催化 vs 噪音的判断原则**：
- 必须影响基本面（不是纯情绪/概念）
- 必须有可验证的数据支撑（不是传闻）

**`what_would_change_my_mind` 的适用范围**：
- **持仓股（已跑 L3）**：催化事件必须与 `what_would_change_my_mind` 变量相关 → 触发重新审视
- **新发现股（仅 L1/L2）**：催化事件作为加分项，提升进入 L3 深研的优先级（无此变量时不约束）

**实现细节**（等 L1-L3 跑顺后补充）：
- 数据源稳定性（财报公告接口、新闻采集）
- LLM prompt 设计（行业政策/管理层变动判断）
- 催化事件的缓存与去重策略
```

### watchlist.json 结构

```json
{
  "generated_at": "2026-06-23",
  "l1_candidates": 200,
  "l2_shortlist": 20,
  "candidates": [
    {
      "ticker": "002273.SZ",
      "name": "水晶光电",
      "l1_score": 87,
      "l2_verdict": "deep_dive",
      "l2_confidence": 82,
      "f_score": 8,
      "pe_ttm": 18.2,
      "pb": 1.8,
      "roe_5y_avg": 17.3,
      "dividend_yield": 3.1,
      "safety_margin_pct": 35,
      "heat_rank": 0.28,
      "flags": ["low_heat", "high_dividend"],
      "red_flags": ["ROE 近 2 年微降"],
      "green_flags": ["现金流匹配", "低负债"],
      "rationale": "F8 / ROE 17% / 股息 3.1% / 估值分位 28%",
      "key_variables": ["ROE 趋势", "行业增速"],  ← 来自 L3 what_would_change_my_mind
      "last_updated": "2026-06-23"
    }
  ]
}
```

---

## 八、实施路径

### Phase 0：新建 repo + 剥离数据层（1-2 天）

从 UZI-Skill 中借鉴设计模式到新 repo，**不是原样照搬**，借机修最脏的工程债：

```
value-screener/                    # 新 repo
├── data/                          # 借鉴 UZI 模式，重新组织
│   ├── fetchers/                  # 从 fetch_*.py 借鉴模式
│   │   ├── basic.py               # 修: 去模块级 chdir/副作用
│   │   ├── financials.py
│   │   ├── kline.py
│   │   ├── valuation.py
│   │   └── risk.py                # 🆕 质押/商誉/审计
│   │   └── ...
│   ├── lib/
│   │   ├── stock_features.py      # 直接复用 + 新增 F-Score 组装
│   │   ├── market_router.py       # 直接复用
│   │   ├── fin_models.py          # 直接复用 (DCF/LBO)
│   │   ├── data_sources.py        # 借鉴三级容错模式，修 except Exception
│   │   └── batch_fetcher.py       # 🆕 批量采集 wrapper
│   └── cache/
├── screener/                      # 🆕 L1 选股引擎
│   ├── hard_gates.py              # 硬门槛过滤
│   ├── factor_scores.py           # 价值/质量/安全边际打分
│   ├── anti_trap.py               # 反价值陷阱因子
│   ├── heat_filter.py             # 低热度排除（防御性）
│   └── main.py                    # screen_a_shares() 入口
├── scout/                         # 🆕 L2 LLM 初筛
│   ├── prompt.py                  # Scout system prompt
│   ├── batch.py                   # 并发 LLM 调用
│   └── parse.py                   # 结构化输出解析
├── council/                       # 🆕 L3 天团深研
│   ├── prompts/                   # 5+1 agent system prompts
│   │   ├── buffett.md
│   │   ├── munger.md
│   │   ├── duan.md
│   │   ├── feng_liu.md
│   │   ├── zhang_kun.md
│   │   └── devil.md
│   ├── prompt_builder.py          # 🆕 三层 RULE 组装（global → project → agent）
│   ├── debate.py                  # 4 轮辩论编排
│   ├── calibrate.py               # 校准测试
│   └── output.py                  # 结构化输出 + 辩论记录
├── monitor/                       # 🆕 L4 监控
│   ├── weekly.py                  # 定期重跑
│   ├── catalysts.py               # 催化事件检测
│   ├── risk_events.py             # 风险事件扫描
│   └─ alerts.py                   # 估值区间提醒
├── watchlist/                     # 🆕 watchlist 管理
│   ├── manager.py                 # 增量 diff / 历史轨迹
│   └── schema.py                  # watchlist.json 结构定义
├── frontend/                      # 🆕 Streamlit 前端
│   ├── main.py                    # Streamlit 入口（多页面聚合）
│   ├── components/                # 可复用 UI 组件（图表/表格）
│   │   ├── charts.py
│   │   └── tables.py
│   └── pages/
│       ├── screener.py            # 选股仪表盘
│       ├── deep_research.py       # 个股深研
│       ├── watchlist.py           # Watchlist
│       └── settings.py            # 系统配置
├── Dockerfile                     # 容器化部署
├── docker-compose.yml             # 多服务编排
└── RULE.md                        # 项目级规则
```

剥离时**必须修的工程债**（从 UZI review 发现的）：
- ✂ 两份 run.py → 只保留一份
- ✂ 285 个 except Exception → 只保留必要的，改为具体异常类型
- ✂ 模块级 os.chdir + sys.path.insert → 移到 main() 内部
- ✂ 68 个源码搜索测试 → 不搬，后续重做行为测试

### Phase 1：L1 Screener（3-5 天）

```python
# screener/main.py
def screen_a_shares(top_n=200):
    """全市场扫描 → 候选池"""
    all_stocks = fetch_all_a_basic()              # ~5000 只
    candidates = apply_hard_gates(all_stocks)      # → ~800
    financials = batch_fetch_financials(candidates) # 并发采集
    scored = score_factors(candidates, financials) # 价值+质量+安全边际
    scored = apply_anti_trap(scored)               # 反价值陷阱
    scored = apply_heat_filter(scored)             # 低热度排除（防御性）
    return rank_and_slice(scored, top_n)           # → 200
```

### Phase 2：L2 Scout Agent（3-5 天）

- 设计 + 校准 Scout prompt
- 实现批量并发 LLM 调用（🧠 轻量推理模型 — 分类+结构化提取）
- 输出结构化 verdict 列表（红旗/绿旗可解释）

### Phase 3：L3 Analyst Council（1-2 周）

- 蒸馏 5 位投资者的决策框架 prompt（Level 2）
- 实现辩论编排器（4 轮串行对话 · Round 1-3 用 🧠 重度推理模型，Round 4 用 🧠 中度）
- 校准测试（真实案例验证立场一致性）
- 报告渲染（辩论记录可视化 · 借鉴 UZI 的 HTML 模板模式）

### Phase 4：L4 Monitor + Watchlist（1 周）

- 统一 CLI 入口
- watchlist 增量 diff + 历史轨迹
- 催化事件检测（财报日历/分红公告/政策）
- 估值区间提醒（估值分位 + 催化，不是股价）
- 风险事件扫描（减持/业绩预告/审计变更）

### 迭代原则

> **先把 L1 + L2 做好（选股漏斗），这部分的 ROI 最高。**
> L3 天团可以先从 1 个 agent（巴菲特）开始深研，边加边看辩论质量有没有信息增量。
> 如果 6 个 agent 说的话和 1 个没区别，就别加到 5 个。
> L4 监控等 L1-L3 跑顺后再加。

---

## 九、技术决策：部署与前端方案

### 9.1 Docker 容器化部署

**目标**：整个系统在 Docker 中运行，消除环境差异。akshare 依赖 lxml/pandas/numpy 等底层库，不做容器化环境管理成本高。

```dockerfile
# Dockerfile 骨架
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libxml2-dev libxslt-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY value-screener/ /app/value-screener/
COPY frontend/ /app/frontend/

# 默认入口：Streamlit 前端
CMD ["streamlit", "run", "frontend/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

```yaml
# docker-compose.yml 骨架
services:
  frontend:
    build: .
    ports:
      - "8501:8501"   # Streamlit 前端
    volumes:
      - ./value-screener:/app/value-screener  # 开发时热重载
      - ./frontend:/app/frontend              # 前端热重载
      - ./data:/app/data                      # 持久化缓存
      - ~/.trade-agent/RULE.md:/root/.trade-agent/RULE.md:ro  # 全局规则
    environment:
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_API_BASE=http://llm-local:11434   # compose 内 Ollama
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  screener:
    build: .
    command: python cli.py --job screen       # 根目录统一 CLI
    volumes:
      - ./value-screener:/app/value-screener
      - ./data:/app/data
      - ~/.trade-agent/RULE.md:/root/.trade-agent/RULE.md:ro
    environment:
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_API_BASE=http://llm-local:11434
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    profiles: ["tools"]                        # 按需手动运行
    restart: "no"

  # 本地 LLM（GPU 直通）
  llm-local:
    image: ollama/ollama
    ports:
      - "11434:11434"
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    volumes:
      - ollama-data:/root/.ollama

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

volumes:
  ollama-data:
  redis-data:
```

> **部署说明**：
> - 首次部署后需手动拉取 Ollama 模型：`docker exec <container> ollama pull qwen3:8b`
> - screener 默认不随 `docker compose up` 启动（`profiles: ["tools"]`），需手动运行：`docker compose run --rm screener`
> - LLM_API_BASE 指向 compose 内的 llm-local 服务，无需 `host.docker.internal`（Linux 兼容）
> - 如需 Ollama 跑在宿主机（GPU 直通场景），将 LLM_API_BASE 改为 `http://host.docker.internal:11434` 并添加 `extra_hosts: ["host.docker.internal:host-gateway"]`

### 9.2 前端方案：Streamlit（MVP）

**决策**：MVP 阶段用 **Streamlit**，后续需要复杂交互时再评估是否迁移到 FastAPI + React。

| 维度 | Streamlit | FastAPI + React |
|------|-----------|-----------------|
| 开发成本 | 极低，纯 Python，无前端代码 | 高，需前后端分离开发 |
| 数据展示 | DataFrame 直接渲染，markdown 原生支持 | 需自建表格/图表组件 |
| 适合场景 | 数据看板、分析报告、内部工具 | 复杂交互、多用户、自定义 UI |
| MVP 匹配度 | ✅ 完美匹配 | ❌ 过度工程 |
| 迁移成本 | 低——API 逻辑可复用，后续换前端只需重写视图层 | — |

**核心页面**（MVP）：

| 页面 | 功能 | Streamlit 组件 |
|------|------|----------------|
| 选股仪表盘 | 触发 L1 扫描 → 查看候选池 → 按因子排序/筛选 | `st.dataframe` + `st.metric` |
| 个股深研 | 输入 ticker → 跑 L2+L3 → 查看天团辩论记录 | `st.markdown` + `st.json` |
| Watchlist | 查看/管理关注列表，历史 diff 轨迹 | `st.dataframe` + `st.line_chart` |
| 系统配置 | 编辑项目 RULE.md、调整 L1 权重、查看校准报告 | `st.text_area` + `st.file_uploader` |

**页面命名约定**：Streamlit sidebar 标签取自文件名，如需中文标签可用 `st.set_page_config(page_title="选股仪表盘")` 覆盖。MVP 阶段先用英文文件名即可。

**风险**：Streamlit 无内置认证、多用户会话管理弱。对单人使用的本地工具不是问题，但如果后续要开放给多人使用，需迁移到 FastAPI + React。

### 9.3 实施调整

Phase 0 目录结构已包含 `frontend/`、`Dockerfile`、`docker-compose.yml`（见第八节）。

**命名约定**：
- 根目录统一 CLI 入口命名为 `cli.py`（非 `main.py`），避免与 `frontend/main.py` 混淆
- Streamlit 页面文件名用英文（`screener.py`/`deep_research.py`/`watchlist.py`/`settings.py`），中文标签通过 `st.set_page_config(page_title="...")` 覆盖

---

## 十、风险与期望管理

### 10.1 技术风险

| 风险 | 应对 |
|---|---|
| LLM 推理不稳定（同股不同结果） | structured output + temperature=0 + 置信度校验 |
| Prompt 蒸馏质量差（不像真人） | 真实案例校准 + 持续迭代 prompt |
| 数据源不稳定（akshare 接口变更） | 三级容错链已验证（借鉴 UZI 模式） |
| **财报数据东财单一依赖** | 按季调度 + 磁盘缓存 + 新浪兜底（详见 §4.7.2.1） |
| 辩论收敛为废话（"各有道理"） | Devil's Advocate 强制找具体漏洞 |
| 低热度误判（冷门=价值陷阱） | L1 反陷阱因子 + L2 红旗检测双重过滤 |

### 10.2 期望管理

A 股价值投资本身是高难度动作。段永平、冯柳、张坤能做到超额收益，不只是因为分析框架好，还因为：
- **信息优势**（产业链调研、管理层接触）
- **心理优势**（拿得住、敢逆向）
- **时间优势**（全职投入、数十年积累）

AI 能帮你做的：
- 更快看完更多数据
- 更系统地应用投资框架
- 更诚实地记录推理过程
- 提醒你关注容易忽略的风险

**AI 不能替你做的**：
- 产业链调研和实地考察
- 抗住 30% 回撤的心理压力
- 在全市场恐慌时逆向买入
- 判断管理层的人品和能力（只能基于公开信息推断）

### 10.3 回测与验证策略

**MVP 不做系统性回测。** 理由：

1. **案例库已覆盖基本校准需求**：用真实案例（茅台应该看多、乐视应该看空）校准 agent 判断质量（§6.6），这是 MVP 阶段的核心验证手段
2. **L1 因子无需回测**：F-Score、PE/PB 分位、格雷厄姆数等都是学术验证过的公式（30 年+文献支撑），不需要自己回测有效性
3. **系统性回测成本高、收益有限**：
   - L2/L3 的判断是质性推理，回测需要历史数据 + 历史标注（哪些股票后来涨了/跌了），数据获取成本高
   - 回测结果可能误导（历史不代表未来，过拟合风险）

**实际跑几轮后再评估**：看推荐质量、L2 否决率、L3 共识与市场走势的吻合度，决定是否需要系统性回测。

---

## 十一、一句话总结

> **借鉴数据层，重做决策层：用三层漏斗（量化筛选 → 可解释 LLM 初筛 → 5+1 天团辩论）+ 监控层替代 66 个规则引擎，让 AI 真正「思考」而不是「打勾」。格雷厄姆的纪律嵌入 L1 硬门槛，巴菲特/芒格/段永平/冯柳/张坤的天团在 L3 做质性判断。低热度是排除维度不做反转因子。「合适时点」= 基本面催化不是 K 线低点。先做选股漏斗，后做天团辩论。**

---

## 附：参考来源

- akshare A 股实时行情接口：https://akshare.akfamily.xyz/data/stock/stock.html
- LangGraph 多 agent 协作模式：https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/
- Piotroski F-score 九项标准：https://en.wikipedia.org/wiki/Piotroski_F-score
