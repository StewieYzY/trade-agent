# Design: bootstrap-data-layer

> 从 UZI-Skill 借鉴数据层设计模式，修工程债，建立 `value-screener/data/` 骨架。

## 约束（引用 ADR）

- **AD-01**：fetcher/features 必须能被 L1 直接消费，不依赖 L3/L4
- **AD-03**：数据层零 LLM——fetcher 是纯数据采集，不调用任何模型

---

## 1. Fetcher 模块设计

**来源**：total-design §2.2（22 维采集 + 三级容错）、§4.7.2（全市场快照容错链）、§4.7.3（并发控制）

### 1.1 五个维度

| 维度 | 文件 | 采集内容 | 来源章节 |
|------|------|----------|----------|
| basic | `fetchers/basic.py` | PE/PB/市值/行业/代码+名称 | §4.7.2 `stock_zh_a_spot_em()` |
| financials | `fetchers/financials.py` | 三表原始项（利润表/资产负债表/现金流表），近 3 年多期 | §4.7.2.1 财报调度（akshare 实测确认） |
| kline | `fetchers/kline.py` | 日 K 线（算热度/动量） | §4.7.4 K 线 TTL |
| valuation | `fetchers/valuation.py` | PE/PB 历史分位、格雷厄姆数 | §4.7.4 估值分位 |
| risk | `fetchers/risk.py` | 质押率/商誉（必采）、审计意见（可选，接口缺失时返回 null 不阻塞） | §八 Phase 0 🆕 标记 |

### 1.2 容错链模式

**来源**：§4.7.2 全市场快照容错链、UZI `data_sources.py` 三级容错

每个 fetcher 实现 provider chain failover：

```
主选接口 → 兜底 1 → 兜底 2（可选）
```

- **basic.py 容错链**（§4.7.2）：
  - 主选：`ak.stock_zh_a_spot_em()`（一次 ~5000 只）
  - 兜底 1：`ak.stock_info_a_code_name()` + tencent qt 逐只（UZI 验证过不需要 key）
  - 兜底 2/3：雪球/baostock（MVP 不实现，留接口）

- **financials.py 容错链**（§4.7.2.1）：
  - 主选：同花顺三表 `stock_financial_{benefit|debt|cash}_ths`（indicator="按年度"，一次返回全部年报，多期）。**实测确认（S4 风险已解决）**：东财 `stock_balance_sheet_by_report_em` / `stock_cash_flow_sheet_by_report_em` / `_by_yearly_em` 因东财页面 `hidctype` 反爬改动整体不可用（抛 TypeError），已切换到同花顺源。商誉（GOODWILL）从东财 `stock_financial_abstract` 商誉行补（ths 三表无商誉列，失败置 None，不影响 F-Score）
  - 兜底 1：新浪财报接口（UZI 验证过稳定性好但字段可能不全）
  - 注：同花顺三表为按年汇总接口（非分页），反爬压力低于原分页接口；financials 维度并发仍按保守处理（max_workers=4，见 §4.1）

- **kline.py 容错链**（UZI `data_sources._kline_a_share_chain` 验证过 6 级 fallback）：
  - 主选：`ak.stock_zh_a_hist()`（东财，前复权）
  - 兜底 1：`ak.stock_zh_a_daily()`（新浪，列名需归一化为东财格式）
  - 兜底 2：baostock `query_history_k_data_plus()`（官方接口，免登录限流）
  - 兜底 3-5（MVP 不实现，留接口）：东财 push2his 直连 / 新浪 quotes 直连 / 腾讯 ifzq 直连

- **valuation.py 容错链**（UZI `fetch_valuation.py` 验证过）：
  - 主选：`ak.stock_zh_valuation_baidu()`（PE/PB 近 5 年历史序列，算分位）
  - 兜底 1：`ak.stock_industry_pe_ratio_cninfo()`（行业 PE 均值，A 股，cninfo 绕开东财 push2）
  - 港股兜底：`ak.hk_valuation_comparison_em()`（同行 PE 均值，MVP 不实现）
  - 格雷厄姆数：`sqrt(22.5 * EPS * BVPS)`，EPS/BVPS 从 financials 派生，无需额外接口

- **risk.py 容错链**：
  - 主选：`ak.stock_gpzy_pledge_ratio_em()`（质押率，全市场一次返回）
  - 兜底：无独立兜底（质押率为东财单一渠道）；商誉从 financials 的 balance_sheet `GOODWILL` 派生，审计意见见 §1.1 可选标注

- **通用模式**：指数退避重试（backoff=2, max_retries=3）+ 随机延迟（0.5-2s，§4.7.3）

### 1.3 Fetcher 接口约定

```python
class BaseFetcher(ABC):
    @abstractmethod
    def fetch(self, ticker: str) -> dict:
        """采集单只股票该维度数据，返回多期结构（见下）"""

    def fetch_with_fallback(self, ticker: str) -> dict:
        """单次调用内的容错链：逐 provider 尝试，成功即返回。不含跨 batch 重试（见 §3.3）"""
```

- 所有 fetcher 继承 `BaseFetcher`
- `fetch()` 返回多期结构（非 flat dict）。financials 维度返回 `{"years": [...], "income": {...}, "balance_sheet": {...}, "cash_flow": {...}}`，其余维度按各自契约定义
- akshare 为同步库，`fetch()` / `fetch_with_fallback()` 为同步接口；并发由 `BatchFetcher` 的 `ThreadPoolExecutor` 承担（§4.1），不使用 async/await
- 字段名与 `stock_features.py`（§2.2）/ `fin_models.py`（§2.3）的输入契约对齐
- 异常收窄：不允许 `except Exception`，只捕获 `akshare` 具体异常 + `httpx.TimeoutException` + `KeyError`

---

## 2. 特征工程层

**来源**：total-design §2.2 stock_features.py 直接复用、§八 Phase 0 F-Score 组装

### 2.1 模块清单

| 文件 | 复用方式 | 说明 |
|------|----------|------|
| `lib/stock_features.py` | 直接复用 | UZI ~108 标准化特征（591 行），新增 F-Score 九项组装 |
| `lib/market_router.py` | 直接复用 | 板块/行业映射 |
| `lib/fin_models.py` | 🆕 新建 | change 0 简化 DCF；完整版 DCF/LBO/Comps 留 L3 change |
| `lib/data_sources.py` | 借鉴模式 | 三级容错 + provider chain failover（1463 行），修 except Exception |
| `lib/batch_fetcher.py` | 🆕 新建 | 批量采集 wrapper，封装并发控制 |

### 2.2 stock_features.py 新增

在 UZI 现有 ~108 特征基础上，新增 **F-Score 九项组装**（Piotroski 1980 学术公式，§一 L1 核心因子）：

```
F1: ROA > 0          F4: CFO > ROA        F7: 毛利率↑
F2: CFO > 0          F5: 长期负债率↓       F8: 资产周转率↑
F3: ROA↑             F6: 流动比率↑         F9: 无稀释
```

输入来自 fetcher 已采集的财报数据，无需额外接口。

**F-Score 输入字段**（来自 financials fetcher 三表，akshare 实测确认）：

| F 项 | 判定逻辑 | 需要字段 | 数据源 |
|------|----------|----------|--------|
| F1 | ROA > 0 | 净利润、总资产 | abstract「归母净利润」+ balance_sheet `TOTAL_ASSETS` |
| F2 | CFO > 0 | 经营现金流 | cash_flow `NETCASH_OPERATE` |
| F3 | ROA↑ | ROA 同比（两期） | F1 两期相减 |
| F4 | CFO > ROA | 经营现金流、ROA | F1+F2 |
| F5 | 长期负债率↓ | 长期负债率同比 | balance_sheet `TOTAL_NONCURRENT_LIAB` / `TOTAL_ASSETS`，两期 |
| F6 | 流动比率↑ | 流动比率同比 | balance_sheet `TOTAL_CURRENT_ASSETS` / `TOTAL_CURRENT_LIAB`，两期 |
| F7 | 毛利率↑ | 毛利率同比 | abstract（营收−营业成本）/营收，两期 |
| F8 | 资产周转率↑ | 资产周转率同比 | abstract 营收 / balance_sheet `TOTAL_ASSETS`，两期 |
| F9 | 无稀释 | 股本同比 | balance_sheet `SHARE_CAPITAL`，两期 |

**输出契约**：`compute_f_score(financials: dict) -> int`，返回 0-9 整数（每项满足得 1 分）。`financials` 参数为 financials fetcher 的多期结构，函数内部取近两期算同比。

**约束**：纯计算函数，不触发采集，不继承 `BaseFetcher`。派生口径遵循 Piotroski 1980 原版（ROA = 净利润/期末总资产，非平均）。

### 2.3 fin_models.py 契约（change 0 范围）

**定位**：L1/L3 共享纯计算工具库，放 `data/lib/fin_models.py`，不继承 `BaseFetcher`，不触发采集。change 0 只做简化 DCF，完整版 DCF/LBO/Comps 留 L3 change 预留接口。

**函数签名**：

```python
def compute_simple_dcf(
    fcf_series: list[float],      # cash_flow: NETCASH_OPERATE - CONSTRUCT_LONG_ASSET
    revenue_series: list[float],  # abstract: 营业总收入多期，算增长率
    current_price: float,         # 调用方从 basic/kline 取，不在 financials 范围
    assumptions: dict,            # {"discount_rate": float, "terminal_growth": float}
) -> dict:                        # {"intrinsic_value": float, "safety_margin_pct": float}
    """2-Stage FCF + Gordon Terminal，纯计算，无副作用"""
```

**输入字段来源**（akshare 实测确认）：
- FCF 序列：`stock_cash_flow_sheet` 的 `NETCASH_OPERATE` − `CONSTRUCT_LONG_ASSET`，多期
- 营收序列：`stock_financial_abstract` 的「营业总收入」行，多期
- 当前股价：basic fetcher（`stock_zh_a_spot_em`）或 kline fetcher 收盘价，由调用方传入
- 折现率/永续增长率：调用方传，非 fetcher 采

**输出**：`{"intrinsic_value": float, "safety_margin_pct": float}`，`safety_margin_pct = (intrinsic_value - current_price) / current_price * 100`

**消费方**：L1 hard_gates（安全边际 > 30%，total-design §4.7.1）、L1 因子打分（安全边际 20% 权重，total-design §4.7.4）、L3 机构建模（完整版，后续 change）

**约束**：纯计算函数，不持有 fetcher 引用，不触发采集，不继承 `BaseFetcher`。跨维度输入（financials + 股价）由调用方（batch_fetcher / L1）组装。

---

## 3. 缓存管理

**来源**：total-design §4.7.4 TTL 与缓存策略、§2.2 resume 模式

### 3.1 目录结构

```
data/cache/
├── {ticker}/
│   ├── basic.json        ← TTL: 2h (DAILY)
│   ├── financials.json   ← TTL: 24h (QUARTERLY)
│   ├── kline.json        ← TTL: 24h
│   ├── valuation.json    ← TTL: 24h
│   ├── risk.json         ← TTL: 24h
│   └── features.json     ← TTL: 24h (特征快照)
└── market/
    └── industry.json     ← TTL: 7d (STATIC)
```

### 3.2 六档 TTL

**来源**：§4.7.4

| 档位 | 名称 | TTL | 适用维度 |
|------|------|-----|----------|
| 1 | INTRADAY | 5min | 未使用（MVP 不做日内） |
| 2 | DAILY | 2h | basic（收盘后快照） |
| 3 | QUARTERLY | 24h | financials |
| 4 | DAILY_PRICE | 24h | kline、valuation |
| 5 | DAILY_RISK | 24h | risk |
| 6 | STATIC | 7d | industry（几乎不变） |

**财报季特殊处理**（§4.7.2.1）：Q1(4/30)→5月、Q2(8/31)→9月、Q3(10/31)→11月、年报(4/30)→5月，发布窗口期 TTL 缩短到 12h。

### 3.3 Resume 机制

**来源**：§2.2 `.cache/{ticker}/raw_data.json` 模式

**层次区分**：`fetch_with_fallback`（§1.3）是**单次调用内**的 provider chain 容错（同一 `fetch_with_fallback()` 调用里逐 provider 尝试）；Resume 是**跨 batch 运行**的维度级重试（本次 batch 失败的维度，下次跑 batch 时只重试该维度）。两者不冲突：fallback 在一次调用内穷尽 provider 后仍失败 → 该维度标记失败 → Resume 在下次 batch 跳过已成功的维度、只重试失败的。

- 每只股票每个维度独立缓存（`cache/{ticker}/{dim}.json`）
- 跑 batch 时先检查缓存，未过期直接复用（跳过采集）
- 某维度 `fetch_with_fallback` 穷尽 provider 仍失败 → 标记该维度失败，下次 batch 只重试该维度（不影响其他已成功维度）
- 缓存文件写入时 `json.dump` + `os.replace`（原子写，防中途崩溃写坏文件）

---

## 4. 并发控制

**来源**：§4.7.3

### 4.1 batch_fetcher.py 设计

```python
class BatchFetcher:
    """批量采集 wrapper，封装并发控制"""

    def __init__(self, max_workers: int = 10):
        self._pool = ThreadPoolExecutor(max_workers=max_workers)

    def fetch_all(
        self,
        tickers: list[str],
        dimensions: list[str] = ["basic", "financials", "kline", "valuation", "risk"],
        dim_max_workers: dict[str, int] | None = None,
    ) -> dict[str, dict]:
        """对每只股票并行采集所有维度（同步接口，并发由 ThreadPoolExecutor 承担）"""
```

- **Layer 2 并发**：`max_workers=10`（basic/kline/valuation/risk 维度），每只股票的 4-5 维并行（§4.7.3）
- **financials 维度单独限流**：balance_sheet/cash_flow 为分页接口（单只 20+ 次请求，见 §1.2），financials 维度 `max_workers=4`，其余维度 `max_workers=10`。`dim_max_workers` 参数默认 `{"financials": 4}`，覆盖全局 `max_workers`
- **mini_racer 安全**：basic/valuation/risk 为纯 HTTP API（§4.7.3）；financials 已实测切换到同花顺三表 `stock_financial_{benefit|debt|cash}_ths`（纯 HTTP，无 mini_racer 依赖）。原东财 `_by_report_em` 系因 hidctype 反爬不可用（S4 风险已确认并解决）。financials 维度仍按保守并发 max_workers=4
- **反爬应对**：同 provider 请求间随机延迟 0.5-2s（§4.7.3）

---

## 5. 工程债修复清单

**来源**：total-design §八 Phase 0（1149-1153 行）、CLAUDE.md 硬约束

| 债 | UZI 现状 | 修复方式 |
|----|----------|----------|
| except Exception 泛滥 | 285 处 `except Exception` | 收窄为具体异常类型（`httpx.TimeoutException` / `KeyError` / `akshare` 具体异常） |
| 模块级副作用 | `os.chdir()` / `sys.path.insert()` 在模块顶层 | 移到 `main()` 或 `__init__()` 内部 |
| 两份 run.py | 存在两份分歧的入口 | 只保留一份 `cli.py` |
| 源码搜索测试 | 68 个 `test_*.py` 搜索源码路径 | 不搬，后续重做行为测试 |

---

## 6. Dockerfile + cli.py 骨架

**来源**：total-design §九 技术决策、CLAUDE.md 技术栈

### 6.1 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENTRYPOINT ["python", "cli.py"]
```

- Base 镜像：`python:3.11-slim`
- 依赖：akshare（锁定版本）+ httpx + pydantic
- **不含** Ollama/Redis（留给后续 docker-compose）

### 6.2 cli.py 骨架

```python
"""value-screener CLI entry point"""
import typer

app = typer.Typer()

@app.command()
def fetch(ticker: str, dim: str = "all"):
    """采集单只股票数据"""

@app.command()
def batch(tickers_file: str):
    """批量采集"""

@app.command()
def cache_clear(ticker: str = None, dim: str = None):
    """清理缓存"""

if __name__ == "__main__":
    app()
```

- 单一入口，替代 UZI 的两份 run.py
- 子命令：`fetch`（单只）、`batch`（批量）、`cache-clear`（缓存管理）

### 6.3 requirements.txt

```
akshare>=1.18.0
httpx>=0.27.0
pydantic>=2.0
typer>=0.12.0
```

### 6.4 验证策略（分层）

Docker 验证采用分层策略，不要求所有环境都有 Docker：

- **主验证**（必须）：`pip install -r requirements.txt && python -c "import akshare, httpx, pydantic, typer"` — 不依赖 Docker，CI/本地均可运行
- **条件验证**（可选）：若环境有 Docker，`docker build -t value-screener .` 退出码为 0 即可（验证 Dockerfile 语法，不要求 `docker run`）
- **端到端验证**（Task 10）：`docker build && docker run value-screener python cli.py --help` — 确认 ENTRYPOINT 可运行
