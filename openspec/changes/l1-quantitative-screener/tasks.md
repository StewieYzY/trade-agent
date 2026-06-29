# Tasks: l1-quantitative-screener

> 按漏斗顺序拆分，每个 task 可独立验证。
> checkbox 供 openspec CLI 进度跟踪；每个 Task 下的「文件 / 做什么 / 验证」为实施依据。

---

## 1. screener/ 目录骨架 + __init__.py（Task 0）

- [x] 1.1 创建 `value-screener/screener/__init__.py`：导出 `screen_a_shares` 入口函数占位
- [x] 1.2 创建 `value-screener/screener/hard_gates.py`：`check_hard_gates(ticker_data) -> dict` 函数占位，`raise NotImplementedError`
- [x] 1.3 创建 `value-screener/screener/factor_scores.py`：`compute_factor_scores(ticker_data) -> dict` 函数占位
- [x] 1.4 创建 `value-screener/screener/anti_trap.py`：`compute_anti_trap(ticker_data) -> dict` 函数占位
- [x] 1.5 创建 `value-screener/screener/heat_filter.py`：`check_heat_filter(ticker_data) -> dict` 函数占位
- [x] 1.6 创建 `value-screener/screener/main.py`：`screen_a_shares(tickers) -> dict` 入口函数占位
- [x] 1.7 验证：`from screener import screen_a_shares` 无报错；`screen_a_shares(["000001"])` 抛 `NotImplementedError`

---

## 2. hard_gates.py — 硬门槛过滤（Task 1 · S1）

- [x] 2.1 H1 ST/*ST 排除：`basic.name` 含 "ST"（大小写不敏感）
- [x] 2.2 H3 市值 < 50 亿排除：`basic.market_cap < 5e9`（单位元）
- [x] 2.3 H4 金融/券商排除：`basic.industry` 在排除列表 `["银行","证券","保险","多元金融"]`
- [x] 2.4 H5 周期股排除（可选，默认关闭）：`basic.industry` 在 `["钢铁","煤炭","航运","化工","水泥","养殖"]`
- [x] 2.5 H6 实控人质押 > 70% 排除：`risk.pledge_ratio > 70`
- [x] 2.6 H7 非标审计意见排除：`risk.audit_opinion` 在 `["保留意见","无法表示意见","否定意见"]`
- [x] 2.7 H8 PE 为负排除：`basic.pe < 0`
- [x] 2.8 容错：数据缺失时跳过该条件（返回 pass=true），记录跳过的条件
- [x] 2.9 返回结构：`{"pass": bool, "failed_gates": [str]}`
- [x] 2.10 验证：构造测试数据，H3 市值 30 亿 → `{"pass": false, "failed_gates": ["H3"]}`
- [x] 2.11 验证：数据缺失（industry=None, pledge_ratio=None）→ `{"pass": true, "failed_gates": []}`

---

## 3. factor_scores.py — 三因子打分（Task 2 · S2）

### 质量因子（50% 权重）

- [x] 3.1 F-Score 子项（40% 权重）：调用 `stock_features.compute_f_score(financials)` → 0-9 → 归一化到 0-100
- [x] 3.2 ROE 5 年平均子项（30% 权重）：从 financials 派生 ROE（net_profit / (TOTAL_ASSETS - TOTAL_NONCURRENT_LIAB - TOTAL_CURRENT_LIAB + SHARE_CAPITAL)），5 年均值 > 15% 得满分
- [x] 3.3 经营现金流连续正子项（30% 权重）：cash_flow.NETCASH_OPERATE 近 3 年都为正得满分，按比例衰减
- [x] 3.4 质量因子加权求和：仅对有数据的子项加权，全缺失返回 0

### 估值因子（30% 权重）

- [x] 3.5 PE 分位子项（40% 权重）：`valuation.pe_percentile_5y < 30` 得满分，30-70 线性衰减，> 70 得 0
- [x] 3.6 PB < 2 子项（30% 权重）：PB < 2 得满分，2-3 线性衰减，> 3 得 0
- [x] 3.7 PE×PB < 22.5 子项（30% 权重）：PE×PB < 22.5 得满分，22.5-30 线性衰减，> 30 得 0
- [x] 3.8 估值因子加权求和：仅对有数据的子项加权

### 安全边际（20% 权重）

- [x] 3.9 DCF 安全边际子项（60% 权重）：调用 `fin_models.compute_simple_dcf()` → safety_margin_pct > 30% 得满分，0-30% 线性衰减，< 0% 得 0
- [x] 3.10 质押率反向子项（40% 权重）：pledge_ratio < 20% 得满分，20-60% 线性衰减，> 60% 得 0
- [x] 3.11 安全边际加权求和：仅对有数据的子项加权

### 综合分

- [x] 3.12 综合分 = quality × 0.50 + value × 0.30 + safety_margin × 0.20
- [x] 3.13 返回结构：`{"quality": float, "value": float, "safety_margin": float, "composite": float}`
- [x] 3.14 验证：构造测试数据（F-Score=8, ROE=20%, PE分位=25%）→ composite > 70
- [x] 3.15 验证：全缺失数据 → `{"quality": 0, "value": 0, "safety_margin": 0, "composite": 0}`

---

## 4. anti_trap.py — 反价值陷阱扣分（Task 3 · S3）

- [x] 4.1 A1 ROE 3 年趋势下降：近 3 年 ROE 线性回归斜率 < 0 → 每降 1 年扣 2 分
- [x] 4.2 A2 净利润正但经营现金流负：net_profit > 0 && NETCASH_OPERATE < 0 → 扣 10 分
- [x] 4.3 A4 商誉/净资产 > 30%：GOODWILL / total_equity > 0.3 → 扣 8 分
- [x] 4.4 A5 大股东质押 > 60%：pledge_ratio > 60 → 扣 5 分
- [x] 4.5 A6 非标审计意见：audit_opinion 非标 → 扣 15 分
- [x] 4.6 初始 100 分，各项扣分累加，最低 0 分
- [x] 4.7 返回结构：`{"score": float, "flags": [str]}`，flags 记录触发的扣分项及原因
- [x] 4.8 验证：构造测试数据（ROE 3 年下降 + 质押 65%）→ score = 100 - 6 - 5 = 89，flags 含两项
- [x] 4.9 验证：无陷阱信号 → score = 100，flags = []

---

## 5. heat_filter.py — 低热度排除（Task 4 · S4）

- [x] 5.1 HF1 换手率分位 < 30%：kline.turnover_rate 近 60 日分位数 < 30 → 排除
- [x] 5.2 HF2 近 60 日涨幅 > 20%：(close[-1] - close[-60]) / close[-60] > 0.20 → 排除
- [x] 5.3 容错：kline 数据缺失或不足 60 日 → 跳过该条件（返回 pass=true）
- [x] 5.4 返回结构：`{"pass": bool, "failed_filters": [str]}`
- [x] 5.5 验证：构造测试数据（换手率分位 15%）→ `{"pass": false, "failed_filters": ["HF1"]}`
- [x] 5.6 验证：kline 数据不足 → `{"pass": true, "failed_filters": []}`

---

## 6. main.py — 入口编排（Task 5 · S5）

- [x] 6.1 `screen_a_shares(tickers, exclude_cyclicals=False) -> dict` 入口函数
- [x] 6.2 Layer 1：调用 `BatchFetcher.fetch_all(tickers, ["basic", "financials", "kline", "valuation", "risk"])` 批量采集
- [x] 6.3 第一道漏斗：对每只股票调用 `check_hard_gates()` → 过滤出通过的 ~800 只
- [x] 6.4 第二道漏斗：对通过 Hard Gates 的股票调用 `compute_factor_scores()` + `compute_anti_trap()` → 按 composite 降序排序，取 top 300
- [x] 6.5 第三道漏斗：对 top 300 调用 `check_heat_filter()` → 过滤出通过的 ~200 只
- [x] 6.6 组装输出 JSON：candidates 列表（含 ticker/name/industry/factor_scores/anti_trap/f_score/graham_number/pe_ttm/pb/pledge_ratio）+ stats 统计
- [x] 6.7 stats 包含：total / after_hard_gates / after_factors / after_heat_filter / excluded_by_gates（各 gate 排除数）
- [x] 6.8 验证：`screen_a_shares(["000001", "600519"])` 返回符合 S5 schema 的 JSON
- [x] 6.9 验证：stats.excluded_by_gates 各 gate 计数之和 + 最终候选数 ≈ total

---

## 7. cli.py 集成 — screen 子命令（Task 6 · S6）

- [x] 7.1 `cli.py` 新增 `screen` 子命令：`@app.command()` 装饰
- [x] 7.2 参数：`--tickers`（可选，tickers 文件路径）、`--output`（可选，输出文件路径）、`--debug`（可选，输出中间步骤）、`--exclude-cyclicals`（可选，排除周期股）
- [x] 7.3 无 `--tickers` 时：从 `stock_zh_a_spot_em` 全市场快照取所有代码
- [x] 7.4 调用 `screen_a_shares(tickers, exclude_cyclicals)` → JSON 输出（stdout 或文件）
- [x] 7.5 `--debug` 模式：输出每道漏斗的中间结果（Hard Gates 通过列表、Factor Scores top 300、Heat Filter 排除列表）
- [x] 7.6 验证：`python cli.py screen --help` 显示四个参数
- [x] 7.7 验证：`python cli.py screen --tickers tickers.txt --output result.json` → 生成 JSON 文件
- [x] 7.8 验证：`python cli.py screen --debug` → stdout 输出含中间步骤信息

---

## 依赖关系

```
Task 0 (骨架)
  └─ Task 1 (Hard Gates)
  └─ Task 2 (Factor Scores)
  └─ Task 3 (Anti-Trap)
  └─ Task 4 (Heat Filter)
       └─ Task 5 (main.py 入口编排)
            └─ Task 6 (CLI 集成)
```

Task 1-4 之间互不依赖，可并行。Task 5 依赖 Task 1-4 全部完成。Task 6 依赖 Task 5。

---

## 数据依赖（L0 接口）

| L0 模块 | Task 使用 | 字段 |
|---|---|---|
| `fetchers/basic.py` | Task 1, 2 | code, name, price, pe, pb, market_cap, industry |
| `fetchers/financials.py` | Task 2, 3 | years, income, balance_sheet, cash_flow |
| `fetchers/kline.py` | Task 4 | dates, close, turnover_rate |
| `fetchers/valuation.py` | Task 2 | pe_ttm, pb, pe_percentile_5y, pb_percentile_5y, graham_number |
| `fetchers/risk.py` | Task 1, 2, 3 | pledge_ratio, goodwill, audit_opinion |
| `lib/stock_features.py` | Task 2 | compute_f_score() |
| `lib/fin_models.py` | Task 2 | compute_simple_dcf() |
| `lib/batch_fetcher.py` | Task 5 | BatchFetcher.fetch_all() |
