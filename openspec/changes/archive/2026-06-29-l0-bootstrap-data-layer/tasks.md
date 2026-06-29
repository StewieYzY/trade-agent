# Tasks: bootstrap-data-layer

> 按目录结构拆分，每个 task 可独立验证。
> checkbox 供 openspec CLI 进度跟踪；每个 Task 下的「文件 / 做什么 / 验证」为实施依据。

---

## 1. 项目骨架 + Dockerfile + requirements.txt（Task 0）

- [x] 1.1 创建 `value-screener/Dockerfile`：`python:3.11-slim` base 镜像，`pip install` akshare/httpx/pydantic/typer
- [x] 1.2 创建 `value-screener/requirements.txt`：锁定版本（akshare>=1.18.0 / httpx>=0.27.0 / pydantic>=2.0 / typer>=0.12.0）
- [x] 1.3 创建 `value-screener/.gitignore`：`__pycache__/`、`.venv/`、`data/cache/`、`*.pyc`
- [x] 1.4 主验证：`pip install -r requirements.txt && python -c "import akshare, httpx, pydantic, typer"` 无报错（不依赖 Docker，CI/本地均可运行）
- [x] 1.5 条件验证：若环境有 Docker，`docker build -t value-screener .` 退出码为 0（验证 Dockerfile 语法，不要求 docker run）

---

## 2. cli.py 骨架（Task 1）

- [x] 2.1 创建 `value-screener/cli.py`：typer 入口，三个子命令占位：`fetch`、`batch`、`cache-clear`
- [x] 2.2 函数体 `raise NotImplementedError`（占位，后续 task 填充）
- [x] 2.3 无模块级 `os.chdir` / `sys.path.insert`
- [x] 2.4 验证：`python cli.py --help` 显示三个子命令；`python cli.py fetch 000001` 抛 `NotImplementedError`

---

## 3. data/fetchers/basic.py — 基础信息 + 容错链（Task 2）

- [x] 3.1 创建 `value-screener/data/fetchers/__init__.py`
- [x] 3.2 创建 `value-screener/data/fetchers/base.py`：`BaseFetcher` ABC，定义 `fetch(ticker) -> dict` 抽象接口 + `fetch_with_fallback()` 容错链编排
- [x] 3.3 创建 `value-screener/data/fetchers/basic.py`，主选 `ak.stock_zh_a_spot_em()`（全市场快照，§4.7.2）
- [x] 3.4 basic.py 兜底 1：`ak.stock_info_a_code_name()` + tencent qt 逐只
- [x] 3.5 basic.py 指数退避重试（backoff=2, max_retries=3）+ 随机延迟 0.5-2s
- [x] 3.6 basic.py 异常收窄：不 `except Exception`，只捕获 `httpx.TimeoutException` / `KeyError` / akshare 具体异常
- [x] 3.7 验证：`python cli.py fetch 000001 --dim basic` 返回 `{"code": "000001", "name": "平安银行", "pe": ..., "pb": ..., "market_cap": ...}`

---

## 4. data/fetchers/financials.py — 财报数据（Task 3）

- [x] 4.1 创建 `value-screener/data/fetchers/financials.py`
- [x] 4.2 主选（利润表）：同花顺 `stock_financial_benefit_ths`（indicator="按年度"）；采集列：`*营业总收入`、`*归属于母公司所有者的净利润`、`其中：营业成本`；商誉从东财 `stock_financial_abstract` 补
- [x] 4.3 主选（资产负债表）：同花顺 `stock_financial_debt_ths`（indicator="按年度"）；采集列映射：`*资产合计`→TOTAL_ASSETS、`流动资产合计`→TOTAL_CURRENT_ASSETS、`流动负债合计`→TOTAL_CURRENT_LIAB、`非流动负债合计`→TOTAL_NONCURRENT_LIAB、`实收资本（或股本）`→SHARE_CAPITAL、GOODWILL 从 abstract 补（实测东财 _by_report_em 因 hidctype 反爬全挂，已切换 THS）
- [x] 4.4 主选（现金流表）：同花顺 `stock_financial_cash_ths`（indicator="按年度"）；采集列映射：`*经营活动产生的现金流量净额`→NETCASH_OPERATE、`购建固定资产、无形资产和其他长期资产支付的现金`→CONSTRUCT_LONG_ASSET
- [x] 4.5 兜底 1：新浪财报接口（UZI 验证过稳定性好但字段可能不全）
- [x] 4.6 默认采集近 3 年年报（多期，F-Score 同比项 + DCF 增长率所需）
- [x] 4.7 继承 `BaseFetcher`，同样容错模式
- [x] 4.8 验证：`python cli.py fetch 600519 --dim financials` 返回财报 dict（茅台，数据应完整）

---

## 5. data/fetchers/kline.py — K 线数据（Task 4）

- [x] 5.1 创建 `value-screener/data/fetchers/kline.py`，采集日 K 线（收盘价、成交量），用于热度/动量计算
- [x] 5.2 主选：`ak.stock_zh_a_hist()`（东财，前复权）
- [x] 5.3 兜底 1：`ak.stock_zh_a_daily()`（新浪，列名需归一化为东财格式）
- [x] 5.4 兜底 2：baostock `query_history_k_data_plus()`（官方接口，免登录限流）
- [x] 5.5 兜底 3-5（MVP 不实现，留接口）：东财 push2his 直连 / 新浪 quotes 直连 / 腾讯 ifzq 直连
- [x] 5.6 默认采集近 250 交易日（1 年）
- [x] 5.7 继承 `BaseFetcher`
- [x] 5.8 验证：`python cli.py fetch 000001 --dim kline` 返回 `{"close": [...], "volume": [...], "dates": [...]}`

---

## 6. data/fetchers/valuation.py — 估值分位（Task 5）

- [x] 6.1 创建 `value-screener/data/fetchers/valuation.py`，PE/PB 历史分位（近 5 年 / 10 年）
- [x] 6.2 格雷厄姆数：`sqrt(22.5 * EPS * BVPS)`
- [x] 6.3 主选：`ak.stock_zh_valuation_baidu()`（PE/PB 近 5 年历史序列，算分位）
- [x] 6.4 兜底 1：`ak.stock_industry_pe_ratio_cninfo()`（行业 PE 均值，A 股，cninfo 绕开东财 push2）
- [x] 6.5 港股兜底：`ak.hk_valuation_comparison_em()`（同行 PE 均值，MVP 不实现）
- [x] 6.6 格雷厄姆数：EPS/BVPS 从 financials 派生，无需额外接口
- [x] 6.7 继承 `BaseFetcher`
- [x] 6.8 验证：`python cli.py fetch 600519 --dim valuation` 返回 `{"pe_percentile_5y": ..., "pb_percentile_5y": ..., "graham_number": ...}`

---

## 7. data/fetchers/risk.py — 风险/治理数据（Task 6）

- [x] 7.1 创建 `value-screener/data/fetchers/risk.py`，质押率：`ak.stock_gpzy_pledge_ratio()`
- [x] 7.2 商誉：从财报数据派生（Task 3 的 financials 已含）
- [x] 7.3 审计意见：`ak.stock_audit_report_em()`（可选降级字段：接口缺失或无数据时返回 `null`，不阻塞；下游不得假设该字段必为非空）
- [x] 7.4 继承 `BaseFetcher`
- [x] 7.5 验证：`python cli.py fetch 000001 --dim risk` 返回 `{"pledge_ratio": <float>, "goodwill": <float>, "audit_opinion": <str|null>}`（audit_opinion 允许为 null）

---

## 8. data/lib/ — 特征工程 + 工具模块（Task 7）

- [x] 8.1 创建 `value-screener/data/lib/__init__.py`
- [x] 8.2 创建 `value-screener/data/lib/stock_features.py`：从 UZI 591 行版本借鉴，新增 F-Score 九项组装（F1-F9，Piotroski 1980）
- [x] 8.3 创建 `value-screener/data/lib/market_router.py`：从 UZI 借鉴板块/行业映射
- [x] 8.4 创建 `value-screener/data/lib/fin_models.py`：change 0 只做简化 DCF（`compute_simple_dcf`），完整版 DCF/LBO/Comps 留 L3 change
  - `compute_simple_dcf(fcf_series, revenue_series, current_price, assumptions) -> {"intrinsic_value": float, "safety_margin_pct": float}`
  - 输入：FCF 序列（`NETCASH_OPERATE - CONSTRUCT_LONG_ASSET`）、营收序列（算增长率）、当前股价（调用方传）、假设参数
  - 纯计算，不继承 `BaseFetcher`，不触发采集，跨维度输入由调用方组装
  - 算法：2-Stage FCF + Gordon Terminal（total-design §4.7.1）
- [x] 8.5 创建 `value-screener/data/lib/data_sources.py`：从 UZI 1463 行版本借鉴三级容错 + provider chain，修 `except Exception` 收窄
- [x] 8.6 验证：`from data.lib.stock_features import compute_f_score; compute_f_score({...})` 返回 0-9 整数
- [x] 8.7 验证：`from data.lib.fin_models import compute_simple_dcf; compute_simple_dcf([3.2,3.5,3.8], [50,55,60], 1800.0, {"discount_rate":0.08, "terminal_growth":0.03})` 返回含 `intrinsic_value`、`safety_margin_pct` 两个 float 字段的 dict

---

## 9. data/cache/ — 缓存管理（Task 8）

- [x] 9.1 创建 `value-screener/data/cache/__init__.py`
- [x] 9.2 创建 `value-screener/data/cache/manager.py`，六档 TTL 常量（DAILY=2h, QUARTERLY=24h, STATIC=7d 等，见 design.md §3.2）
- [x] 9.3 `CacheManager`：`get(ticker, dim)` / `set(ticker, dim, data)` / `is_expired(ticker, dim)`
- [x] 9.4 原子写：`json.dump` 到 `.tmp` → `os.replace` 到目标路径
- [x] 9.5 缓存目录：`data/cache/{ticker}/{dim}.json`
- [x] 9.6 验证：写入缓存 → 读出一致 → sleep 超过 TTL → `is_expired` 返回 True

---

## 10. data/lib/batch_fetcher.py — 批量采集 wrapper（Task 9）

- [x] 10.1 创建 `value-screener/data/lib/batch_fetcher.py`，`BatchFetcher(max_workers=10)` 封装 `ThreadPoolExecutor`
- [x] 10.2 `fetch_all(tickers, dimensions, dim_max_workers)` → 对每只股票并行采集所有维度，financials 维度单独限流（`max_workers=4`，见 design.md §4.1）
- [x] 10.3 集成 `CacheManager`：先查缓存，未过期跳过；采集成功后写缓存
- [x] 10.4 Resume 机制：某维度失败不影响其他维度，下次只重试失败的
- [x] 10.5 反爬：同 provider 请求间随机延迟 0.5-2s
- [x] 10.6 验证 1：`batch_fetcher.fetch_all(["000001", "600519"])` 返回两只股票全维度数据
- [x] 10.7 验证 2：第二次调用（缓存未过期）不调用 akshare 接口（可 mock 验证）
- [x] 10.8 验证 3：模拟某维度失败 → 重试只调失败维度

---

## 11. cli.py 填充 + 集成验证（Task 10）

- [x] 11.1 `value-screener/cli.py`（更新 Task 1 的占位），`fetch` 命令：调用单个 fetcher，输出 JSON
- [x] 11.2 `batch` 命令：从文件读 ticker 列表，调用 `BatchFetcher`
- [x] 11.3 `cache-clear` 命令：按 ticker/dim 清理缓存文件
- [x] 11.4 验证 1：`python cli.py fetch 600519 --dim basic` → JSON 输出
- [x] 11.5 验证 2：`python cli.py batch --tickers tickers.txt` → 批量采集完成
- [x] 11.6 验证 3：`python cli.py cache-clear --ticker 600519` → 缓存文件删除
- [x] 11.7 条件验证：若环境有 Docker，`docker build && docker run value-screener python cli.py --help` 退出码为 0（确认 ENTRYPOINT 端到端可运行）

---

## 依赖关系

```
Task 0 (骨架+Docker)
  └─ Task 1 (cli 骨架)
  └─ Task 2 (BaseFetcher + basic.py)
       └─ Task 3 (financials.py)
       └─ Task 4 (kline.py)
       └─ Task 5 (valuation.py)
       └─ Task 6 (risk.py)
  └─ Task 7 (lib/ 模块)
  └─ Task 8 (cache 管理)
       └─ Task 9 (batch_fetcher)
            └─ Task 10 (cli 集成)
```

Task 2-6 之间互不依赖，可并行。Task 7-8 之间互不依赖，可并行。Task 9 依赖 Task 2-8 全部完成。Task 10 依赖 Task 9。
