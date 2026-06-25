# Tasks: bootstrap-data-layer

> 按目录结构拆分，每个 task 可独立验证。

---

## Task 0: 项目骨架 + Dockerfile + requirements.txt

**文件**：
- `value-screener/Dockerfile`
- `value-screener/requirements.txt`
- `value-screener/.gitignore`

**做什么**：
- `python:3.11-slim` base 镜像，`pip install` akshare/httpx/pydantic/typer
- `requirements.txt` 锁定版本
- `.gitignore`：`__pycache__/`、`.venv/`、`data/cache/`、`*.pyc`

**验证**（分层）：
- 主验证：`pip install -r requirements.txt && python -c "import akshare, httpx, pydantic, typer"` 无报错（不依赖 Docker，CI/本地均可运行）
- 条件验证：若环境有 Docker，`docker build -t value-screener .` 退出码为 0（验证 Dockerfile 语法，不要求 docker run）

---

## Task 1: cli.py 骨架

**文件**：
- `value-screener/cli.py`

**做什么**：
- typer 入口，三个子命令占位：`fetch`、`batch`、`cache-clear`
- 函数体 `raise NotImplementedError`（占位，后续 task 填充）
- 无模块级 `os.chdir` / `sys.path.insert`

**验证**：`python cli.py --help` 显示三个子命令；`python cli.py fetch 000001` 抛 `NotImplementedError`

---

## Task 2: data/fetchers/basic.py — 基础信息 + 容错链

**文件**：
- `value-screener/data/fetchers/__init__.py`
- `value-screener/data/fetchers/base.py`（`BaseFetcher` ABC）
- `value-screener/data/fetchers/basic.py`

**做什么**：
- `BaseFetcher`：定义 `fetch(ticker) -> dict` 抽象接口 + `fetch_with_fallback()` 容错链编排
- `basic.py`：
  - 主选：`ak.stock_zh_a_spot_em()`（全市场快照，§4.7.2）
  - 兜底 1：`ak.stock_info_a_code_name()` + tencent qt 逐只
  - 指数退避重试（backoff=2, max_retries=3）+ 随机延迟 0.5-2s
  - 异常收窄：不 `except Exception`，只捕获 `httpx.TimeoutException` / `KeyError` / akshare 具体异常

**验证**：`python cli.py fetch 000001 --dim basic` 返回 `{"code": "000001", "name": "平安银行", "pe": ..., "pb": ..., "market_cap": ...}`

---

## Task 3: data/fetchers/financials.py — 财报数据

**文件**：
- `value-screener/data/fetchers/financials.py`

**做什么**：
- 主选（利润表）：东财 `stock_financial_abstract`（一次返回全部年报列，多期）
  - 采集行：营业总收入、归母净利润、营业成本、经营现金流量净额、商誉（按「指标」列关键词匹配）
- 主选（资产负债表）：东财 `stock_balance_sheet_by_report_em`（分页接口）
  - 采集列：`TOTAL_ASSETS`、`TOTAL_CURRENT_ASSETS`、`TOTAL_CURRENT_LIAB`、`TOTAL_NONCURRENT_LIAB`、`SHARE_CAPITAL`、`GOODWILL`
- 主选（现金流表）：东财 `stock_cash_flow_sheet_by_report_em`（分页接口）
  - 采集列：`NETCASH_OPERATE`（经营现金流）、`CONSTRUCT_LONG_ASSET`（资本开支）
- 兜底 1：新浪财报接口（UZI 验证过稳定性好但字段可能不全）
- 默认采集近 3 年年报（多期，F-Score 同比项 + DCF 增长率所需）
- 同样继承 `BaseFetcher`，同样容错模式

**验证**：`python cli.py fetch 600519 --dim financials` 返回财报 dict（茅台，数据应完整）

---

## Task 4: data/fetchers/kline.py — K 线数据

**文件**：
- `value-screener/data/fetchers/kline.py`

**做什么**：
- 采集日 K 线（收盘价、成交量），用于热度/动量计算
- akshare 接口：`ak.stock_zh_a_hist()`
- 默认采集近 250 交易日（1 年）
- 继承 `BaseFetcher`

**验证**：`python cli.py fetch 000001 --dim kline` 返回 `{"close": [...], "volume": [...], "dates": [...]}`

---

## Task 5: data/fetchers/valuation.py — 估值分位

**文件**：
- `value-screener/data/fetchers/valuation.py`

**做什么**：
- PE/PB 历史分位（近 5 年 / 10 年）
- 格雷厄姆数：`sqrt(22.5 * EPS * BVPS)`
- akshare 接口：`ak.stock_zh_valuation_baidu()`（纯 HTTP API，§4.7.3 确认无 mini_racer）
- 继承 `BaseFetcher`

**验证**：`python cli.py fetch 600519 --dim valuation` 返回 `{"pe_percentile_5y": ..., "pb_percentile_5y": ..., "graham_number": ...}`

---

## Task 6: data/fetchers/risk.py — 风险/治理数据

**文件**：
- `value-screener/data/fetchers/risk.py`

**做什么**：
- 质押率：`ak.stock_gpzy_pledge_ratio()`
- 商誉：从财报数据派生（Task 3 的 financials 已含）
- 审计意见：`ak.stock_audit_report_em()`（可选降级字段：接口缺失或无数据时返回 `null`，不阻塞；下游不得假设该字段必为非空）
- 继承 `BaseFetcher`

**验证**：`python cli.py fetch 000001 --dim risk` 返回 `{"pledge_ratio": <float>, "goodwill": <float>, "audit_opinion": <str|null>}`（audit_opinion 允许为 null）

---

## Task 7: data/lib/ — 特征工程 + 工具模块

**文件**：
- `value-screener/data/lib/__init__.py`
- `value-screener/data/lib/stock_features.py`
- `value-screener/data/lib/market_router.py`
- `value-screener/data/lib/fin_models.py`
- `value-screener/data/lib/data_sources.py`

**做什么**：
- `stock_features.py`：从 UZI 591 行版本借鉴，新增 F-Score 九项组装（F1-F9，Piotroski 1980）
- `market_router.py`：从 UZI 借鉴板块/行业映射
- `fin_models.py`：change 0 只做简化 DCF（`compute_simple_dcf`），完整版 DCF/LBO/Comps 留 L3 change
  - `compute_simple_dcf(fcf_series, revenue_series, current_price, assumptions) -> {"intrinsic_value": float, "safety_margin_pct": float}`
  - 输入：FCF 序列（`NETCASH_OPERATE - CONSTRUCT_LONG_ASSET`）、营收序列（算增长率）、当前股价（调用方传）、假设参数
  - 纯计算，不继承 `BaseFetcher`，不触发采集，跨维度输入由调用方组装
  - 算法：2-Stage FCF + Gordon Terminal（total-design §4.7.1）
- `data_sources.py`：从 UZI 1463 行版本借鉴三级容错 + provider chain，修 `except Exception` 收窄

**验证**：`from data.lib.stock_features import compute_f_score; compute_f_score({...})` 返回 0-9 整数
**验证**：`from data.lib.fin_models import compute_simple_dcf; compute_simple_dcf([3.2,3.5,3.8], [50,55,60], 1800.0, {"discount_rate":0.08, "terminal_growth":0.03})` 返回含 `intrinsic_value`、`safety_margin_pct` 两个 float 字段的 dict

---

## Task 8: data/cache/ — 缓存管理

**文件**：
- `value-screener/data/cache/__init__.py`
- `value-screener/data/cache/manager.py`

**做什么**：
- 六档 TTL 常量（DAILY=2h, QUARTERLY=24h, STATIC=7d 等，见 design.md §3.2）
- `CacheManager`：`get(ticker, dim)` / `set(ticker, dim, data)` / `is_expired(ticker, dim)`
- 原子写：`json.dump` 到 `.tmp` → `os.replace` 到目标路径
- 缓存目录：`data/cache/{ticker}/{dim}.json`

**验证**：写入缓存 → 读出一致 → sleep 超过 TTL → `is_expired` 返回 True

---

## Task 9: data/lib/batch_fetcher.py — 批量采集 wrapper

**文件**：
- `value-screener/data/lib/batch_fetcher.py`

**做什么**：
- `BatchFetcher(max_workers=10)` 封装 `ThreadPoolExecutor`
- `fetch_all(tickers, dimensions, dim_max_workers)` → 对每只股票并行采集所有维度，financials 维度单独限流（`max_workers=4`，见 design.md §4.1）
- 集成 `CacheManager`：先查缓存，未过期跳过；采集成功后写缓存
- Resume 机制：某维度失败不影响其他维度，下次只重试失败的
- 反爬：同 provider 请求间随机延迟 0.5-2s

**验证**：
1. `batch_fetcher.fetch_all(["000001", "600519"])` 返回两只股票全维度数据
2. 第二次调用（缓存未过期）不调用 akshare 接口（可 mock 验证）
3. 模拟某维度失败 → 重试只调失败维度

---

## Task 10: cli.py 填充 + 集成验证

**文件**：
- `value-screener/cli.py`（更新 Task 1 的占位）

**做什么**：
- `fetch` 命令：调用单个 fetcher，输出 JSON
- `batch` 命令：从文件读 ticker 列表，调用 `BatchFetcher`
- `cache-clear` 命令：按 ticker/dim 清理缓存文件

**验证**：
1. `python cli.py fetch 600519 --dim basic` → JSON 输出
2. `python cli.py batch --tickers tickers.txt` → 批量采集完成
3. `python cli.py cache-clear --ticker 600519` → 缓存文件删除
4. 条件验证：若环境有 Docker，`docker build && docker run value-screener python cli.py --help` 退出码为 0（确认 ENTRYPOINT 端到端可运行）

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
