# L1 Quantitative Screener — Detailed Specifications

## Overview

纯量化筛选引擎，将 ~5000 只 A 股压缩至 ~200 只候选池，供 L2/L3 消费。零 LLM 调用，纯规则 + 学术公式。

---

## S1: Hard Gates（硬门槛过滤）

**位置**: `screener/hard_gates.py`  
**输入**: `BatchFetcher.fetch_all(tickers)` 返回的全维度数据  
**输出**: `{ticker: bool}` — True 表示通过，False 表示排除  
**目标**: ~5000 → ~800

### 硬门槛条件（一票否决）

| # | 条件 | 数据来源 | 阈值 | 理由 |
|---|---|---|---|---|
| H1 | ST/*ST/退市风险 | basic.name 含 "ST" | 排除 | 基本面崩坏 |
| H2 | 上市 < 3 年 | basic.list_date | 排除 | 格雷厄姆要求足够财务历史 |
| H3 | 市值 < 50 亿 | basic.market_cap | < 50e8 排除 | 流动性 + 抗风险 |
| H4 | 金融/券商 | basic.industry ∈ ["银行","证券","保险","多元金融"] | 排除 | 估值指标对金融股失效 |
| H5 | 周期股（可选） | basic.industry ∈ ["钢铁","煤炭","航运","化工","水泥","养殖"] | 排除 | 周期股估值逻辑不同 |
| H6 | 实控人质押 > 70% | risk.pledge_ratio | > 70 排除 | 资金链风险 |
| H7 | 非标审计意见 | risk.audit_opinion ∈ ["保留意见","无法表示意见","否定意见"] | 排除 | 财务可信度 |
| H8 | PE 为负（亏损） | basic.pe < 0 | 排除 | 无法估值 |

### 容错

- 某维度数据缺失（如 industry 为空、pledge_ratio 为 None）→ **跳过该条件，不阻塞**（宁可漏过不误杀）
- 返回结构包含排除原因：`{ticker: {"pass": false, "failed_gates": ["H3", "H6"]}}`

---

## S2: Factor Scores（三因子打分）

**位置**: `screener/factor_scores.py`  
**输入**: 通过 Hard Gates 的 ~800 只股票的全维度数据  
**输出**: `{ticker: {"quality": float, "value": float, "safety_margin": float, "composite": float}}`  
**目标**: 软排序，不剔除

### 综合分公式

```
composite = quality × 0.50 + value × 0.30 + safety_margin × 0.20
```

权重校准逻辑见 total-design §4.8：质量 > 估值 > 安全边际，符合巴菲特/芒格"好生意 > 便宜"的优先级。

### 质量因子（50% 权重）

| 子项 | 权重 | 计算 | 数据源 |
|---|---|---|---|
| F-Score | 40% | `stock_features.compute_f_score(financials)` → 0-9 → 归一化到 0-100 | financials |
| ROE 5 年平均 | 30% | 近 5 年 ROE 均值 > 15% 得满分，线性插值到 0% | financials（ROE = net_profit / (TOTAL_ASSETS - TOTAL_CURRENT_LIAB - TOTAL_NONCURRENT_LIAB)） |
| 经营现金流连续 3 年正 | 30% | 3 年都为正得满分，2 年得 66%，1 年得 33%，0 年得 0% | financials.cash_flow.NETCASH_OPERATE |

### 估值因子（30% 权重）

| 子项 | 权重 | 计算 | 数据源 |
|---|---|---|---|
| PE 行业折价（主）+ 历史分位（兜底） | 40% | 主：ratio = pe_ttm / industry_median_pe，< 0.7 得满分、0.7-1.0 线性衰减、>= 1.0 得 0；兜底（无行业 / 行业样本不足 / 无 pe_ttm）：pe_percentile_5y < 30 得满分、30-70 衰减、> 70 得 0 | valuation.pe_ttm + basic.industry + industry_pe_map；兜底 valuation.pe_percentile_5y |
| PB < 2 | 30% | PB < 2 得满分，2-3 线性衰减，> 3 得 0 | valuation.pb |
| PE×PB < 22.5（格雷厄姆数） | 30% | PE×PB < 22.5 得满分，22.5-30 线性衰减 | valuation.pe_ttm × valuation.pb |

**注意**: 股息率 > 2% 在 total-design §4.2 提及，但 L0 未采集股息率数据，MVP 暂不实现，留作后续增强。

### 安全边际（20% 权重）

| 子项 | 权重 | 计算 | 数据源 |
|---|---|---|---|
| DCF 安全边际 | 60% | `fin_models.compute_simple_dcf()` → safety_margin_pct > 30% 得满分 | financials.cash_flow + basic.price |
| 质押率反向 | 40% | pledge_ratio < 20% 得满分，20-60% 线性衰减，> 60% 得 0 | risk.pledge_ratio |

---

## S3: Anti-Trap Factors（反价值陷阱）

**位置**: `screener/anti_trap.py`  
**输入**: ~800 只股票的全维度数据  
**输出**: `{ticker: {"score": float, "flags": [str]}}` — 扣分项，不是排除项  
**目标**: 在 Factor Scores 基础上追加扣分

### 反陷阱因子（7 项扣分）

| # | 因子 | 计算 | 扣分 | 数据源 |
|---|---|---|---|---|
| A1 | ROE 3 年趋势下降 | 近 3 年 ROE 线性回归斜率 < 0 | 每降 1 年扣 2 分 | financials（需派生 ROE） |
| A2 | 净利润正但经营现金流负 | net_profit > 0 && NETCASH_OPERATE < 0 | 扣 10 分 | financials |
| A3 | 应收账款增速 > 营收增速 | (receivables_t - receivables_t-1) / receivables_t-1 > (revenue_t - revenue_t-1) / revenue_t-1 | 扣 5 分 | financials（需新增 receivables 字段） |
| A4 | 商誉 / 净资产 > 30% | goodwill / total_equity > 0.3 | 扣 8 分 | financials.balance_sheet.GOODWILL |
| A5 | 大股东质押 > 60% | pledge_ratio > 60 | 扣 5 分 | risk.pledge_ratio |
| A6 | 非标审计意见 | audit_opinion ≠ "标准无保留意见" | 扣 15 分 | risk.audit_opinion |
| A7 | 3 年内换过 CFO | 暂无数据源，MVP 不实现 | 0 | - |

**注意**:
- A3 需要 L0 financials 新增应收账款字段（`receivables`），当前未实现，MVP 先跳过
- A7 需要高管变动数据，L0 未实现，MVP 先跳过
- 反陷阱是**扣分不是排除**，保留可解释性（每只股票附带 anti_trap_flags 清单）
- A6 比 H7 覆盖更广：H7 用黑名单排除最严重的 3 类（保留意见/无法表示意见/否定意见），A6 用白名单取补扣任何非"标准无保留意见"（含"带强调事项段的无保留意见"）。两者分层：H7 是死刑级淘汰，A6 是宽泛扣分

---

## S4: Heat Filter（低热度排除）

**位置**: `screener/heat_filter.py`  
**输入**: ~300 只股票（经过 Factor Scores + Anti-Trap 排序后的 top 300）  
**输出**: `{ticker: bool}` — True 表示通过，False 表示排除  
**目标**: ~300 → ~200

**注意**: heat_filter 在 top-300 上执行，被剔除的股票**不会**从 rank 301+ 回填。最终输出数量可能少于 ~200（spec 用 `~` 表示约数），取决于市场热度。

### 低热度条件（防御性排除）

| # | 条件 | 数据来源 | 阈值 | 理由 |
|---|---|---|---|---|
| HF1 | 换手率分位 > 70% | kline.turnover_rate 近 60 日分位 | > 70% 排除 | 剔除正在被炒的（异常活跃） |
| HF2 | 近 60 日涨幅 > 20% | kline.close 计算 60 日涨幅 | > 20% 排除 | 剔除刚炒完的（避免接盘） |

**注意**: 
- 低热度是**排除维度，不是反转因子**（AD-02 约束）
- HF1 和 HF2 互补：HF1 抓「正在炒」（当下流速），HF2 抓「刚炒完」（价格位移）
- 换手率分位 = 当前换手率在过去 60 日的分位数（0-100），> 70% 表示当前换手率处于历史高位
- 近 60 日涨幅 = (close[-1] - close[-60]) / close[-60] × 100

---

## S5: Output Schema（输出格式）

**位置**: `screener/main.py` 的 `screen_a_shares()` 返回结构  
**输出**: JSON，包含候选列表 + 统计信息

```json
{
  "run_date": "2026-06-29",
  "candidates": [
    {
      "ticker": "600519",
      "name": "贵州茅台",
      "industry": "白酒",
      "factor_scores": {
        "quality": 85.2,
        "value": 72.5,
        "safety_margin": 60.0,
        "composite": 74.5
      },
      "anti_trap": {
        "score": 95,
        "flags": []
      },
      "adjusted_composite": 70.8,
      "f_score": 7,
      "graham_number": 1950.0,
      "pe_ttm": 28.5,
      "pb": 8.2,
      "pledge_ratio": 5.0
    }
  ],
  "stats": {
    "total": 5000,
    "after_hard_gates": 800,
    "after_factors": 300,
    "after_heat_filter": 200,
    "excluded_by_gates": {
      "H1_ST": 120,
      "H3_small_cap": 2000,
      "H8_pe_negative": 500
    }
  }
}
```

**关键说明**:
- `adjusted_composite` = `factor_scores.composite × (anti_trap.score / 100)`，是**实际排序依据**（乘法，不是减法）
- `factor_scores.composite` 是未扣减反陷阱的基础分
- 输出中同时包含两者，保证排序透明度

---

## S6: CLI Integration

**位置**: `cli.py` 新增 `screen` 子命令  
**用法**:

```bash
# 全市场扫描（默认）
python cli.py screen

# 指定 ticker 列表文件
python cli.py screen --tickers tickers.txt

# 输出到文件
python cli.py screen --output candidates.json

# 调试模式（输出中间步骤）
python cli.py screen --debug
```

**实现**: 调用 `screener/main.py` 的 `screen_a_shares()` 入口函数

---

## S7: 数据依赖（L0 接口）

L1 消费 L0 的以下模块，不新增数据采集逻辑：

| L0 模块 | L1 用途 | 状态 |
|---|---|---|
| `fetchers/basic.py` | PE/PB/market_cap/industry/price | ✅ 已实现（含 industry_mapper） |
| `fetchers/financials.py` | F-Score + ROE + 现金流 + 反陷阱因子 | ✅ 已实现（多期结构） |
| `fetchers/kline.py` | 近 60 日涨幅 + 换手率分位 | ✅ 已实现（含 turnover_rate） |
| `fetchers/valuation.py` | PE/PB 历史分位 + 格雷厄姆数 | ✅ 已实现 |
| `fetchers/risk.py` | 质押率 + 商誉 + 审计意见 | ✅ 已实现 |
| `lib/stock_features.py` | F-Score 九项 | ✅ 已实现 |
| `lib/fin_models.py` | 简化 DCF | ✅ 已实现 |
| `lib/batch_fetcher.py` | 批量采集 wrapper | ✅ 已实现 |
| `cache/manager.py` | 六档 TTL 缓存 | ✅ 已实现 |

**L0 缺失字段（MVP 跳过）**:
- `financials.receivables`（应收账款）— 反陷阱 A3 需要，MVP 跳过
- `basic.list_date`（上市日期）— Hard Gate H2 已用 `financials.years` 近似实现（`len(years) < 3` 排除）
- 高管变动数据 — 反陷阱 A7 需要，MVP 跳过

---

## S8: 性能与成本

| 指标 | 目标 | 实现 |
|---|---|---|
| 全市场扫描耗时 | < 10 分钟 | Layer 1 全市场快照 1 次 + Layer 2/3 并发采集 |
| LLM 调用 | 0 | 纯量化，零 LLM |
| 成本 | ≈ 0 | 仅 akshare API 调用 |
| 缓存命中率 | > 80% | 六档 TTL + Resume 机制 |

---

## S9: 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 财报数据延迟/缺失 | 质量因子（50% 权重）失效 | L0 已实现财报缓存 + 按季调度；L1 对缺失字段做降级（跳过该因子而非报错） |
| 权重设置不合理 | 排序偏差 | §4.8 初始值 50/30/20，跑几轮后根据 L2 否决率和 L3 共识调整 |
| 反陷阱因子误杀 | 漏掉好公司 | 反陷阱是扣分不是排除，保留可解释性（每只股票附带反陷阱标记） |
| 行业分类不准 | 行业中位 PE 计算偏差 | L0 market_router.py 维护行业映射，定期更新（STATIC TTL=7d） |

---

## S10: 边界

### IN
- `screener/hard_gates.py` — 硬门槛过滤
- `screener/factor_scores.py` — 三因子打分
- `screener/anti_trap.py` — 反价值陷阱扣分
- `screener/heat_filter.py` — 低热度排除
- `screener/main.py` — `screen_a_shares()` 入口
- `cli.py` 集成 — `screen` 子命令

### OUT
- `data/`（fetchers/lib/cache）→ L0 已实现
- `scout/`（L2 LLM 初筛）→ change 2
- `council/`（L3 天团深研）→ change 3a/3b
- `monitor/`（L4 监控）→ change 4
- `watchlist/`（watchlist 管理）→ change 4
- `frontend/`（Streamlit 前端）→ change 5
