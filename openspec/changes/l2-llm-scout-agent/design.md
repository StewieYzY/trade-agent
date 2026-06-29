# L2 Scout Agent — Design

## Context

L1 已将 ~5000 只 A 股压缩至 ~200 只候选池（S5 schema），但 L3 天团深研成本高（¥20-60/只）。L2 是必要的成本闸门（AD-03），用轻量 LLM 推理（¥0.01/只）将 200 只压缩至 ~20 只 deep_dive 候选。

**架构约束**（AD-01）：L2 属于快筛管线，必须独立产出 shortlist，不依赖 L3。

---

## §1 关键设计决策

### 决策 1：L1→L2 数据交接方式

**问题**：L1 S5 schema 是摘要（composite 分数 + pe_ttm/pb/pledge_ratio/graham_number/f_score），不含 Scout prompt 要的全量字段（市值、ROE 趋势、净利率、负债率、经营现金流、商誉比、近 60 日涨幅、换手率分位、pe_percentile_5y 等）。

**决策**：L2 拿 L1 的 candidate ticker 列表 → 逐只回 L0 `CacheManager.get(ticker, dim)` 取全维度原始数据（cache 命中不重采）→ 组装成 ~200 tokens 特征快照 → 喂 LLM。

**字段归属**：
- `pe_ttm` 从 `valuation` dim 取（key: `pe_ttm`），不从 `basic` 取（key: `pe`）
- 派生指标（ROE、净利率、负债率、商誉比）从 `financials` 计算，复用 `data/lib/fin_models.py` 的口径（L1 已固化 Piotroski ROA 等计算逻辑）

**Input Assembly 流程**：

```
L1 output (S5 schema)
  └─ candidates[].ticker
       │
       ▼
input_assembly.assemble(ticker)
  ├─ CacheManager.get(ticker, "basic")     → name, industry, market_cap
  ├─ CacheManager.get(ticker, "valuation") → pe_ttm, pb, pe_percentile_5y
  ├─ CacheManager.get(ticker, "financials")→ ROE 3y, 净利率, 经营现金流, 净利润
  ├─ CacheManager.get(ticker, "kline")     → 近60日涨幅, 换手率分位
  └─ CacheManager.get(ticker, "risk")      → 质押率, 商誉, 审计意见
       │
       ▼
snapshot.format(features)  →  ~200 tokens 文本
       │
       ▼
Scout prompt (system + user message)
```

**理由**：
- L0 cache 已采集全维度数据（L1 spec S7 确认），cache 命中不重采（TTL=24h for kline/valuation/risk, QUARTERLY for financials）
- 不假设 L1 JSON 自带全部字段（S5 schema 是摘要，不是全量）
- 特征快照是纯文本（~200 tokens），不是 JSON，符合 §5.3 格式

### 决策 2：LLM Client 选型

**问题**：L2 是第一个调 LLM 的 change，需要选定调用方式。

**决策**：OpenAI 兼容的 httpx 直连，不用 SDK。

**实现**：
```python
import httpx
import os

async def call_llm(prompt: str, system: str) -> str:
    # fail-fast: 显式检查环境变量，缺失抛 ValueError
    for key in ("LLM_API_KEY", "LLM_API_BASE", "LLM_MODEL"):
        if key not in os.environ:
            raise ValueError(f"missing required env var: {key}")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{os.environ['LLM_API_BASE']}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.environ["LLM_MODEL"],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,  # §5.6 消除随机性
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
```

**理由**：
- httpx 是 Python 标准库（asyncio 友好），比 openai SDK 轻量（无 pydantic/numpy 等隐式依赖）
- OpenAI 兼容 API 是事实标准，支持 Ollama/vLLM/各云厂商
- AD-04 不固定模型种类，只标推理等级（轻量），通过 `LLM_MODEL` 环境变量配置
- 环境变量 `LLM_API_KEY` / `LLM_API_BASE` 与 total-design §9.1 docker-compose 约定一致；`LLM_MODEL` 是 L2 扩展

**依赖**：复用 L0 已有的 `httpx~=0.27.0`（async HTTP），不新增依赖。

---

## §2 Scout Prompt 设计（来源：total-design §5.2）

### System Prompt 模板

```
你是 A 股价值投资初筛分析师。请用 3-5 句话回答：

1. 这是一家什么生意？（一句话）
2. 便宜吗？（PE/PB 分位 + 同行对比）
3. 生意好吗？（ROE 趋势 + 现金流质量）
4. 有什么明显的红旗？（负债/质押/商誉/大股东减持）
5. 一句话结论：值得深研 / 观望 / 排除

输出 JSON:
{
  "verdict": "deep_dive|watch|skip",
  "confidence": 0-100,
  "one_liner": "...",
  "red_flags": [...],     // 每条必须引用具体数据
  "green_flags": [...],   // 每条必须引用具体数据
  "anti_trap_flags": [...] // 价值陷阱信号（补充 L1 ANTI_TRAP）
}
```

### User Message 格式（~200 tokens 特征快照，来源：§5.3）

```
股票: {name} ({ticker})
行业: {industry}
市值: {market_cap}亿
PE(TTM): {pe_ttm} (5年分位: {pe_percentile_5y}%)
PB: {pb}
ROE(近3年): {roe_3y}  ← {roe_trend}
净利率: {net_margin}%
负债率: {debt_ratio}%
经营现金流: {operating_cashflow}亿 (净利润 {net_profit}亿) ← {cashflow_match}
营收增速: {revenue_growth}%
商誉/净资产: {goodwill_ratio}%
大股东质押: {pledge_ratio}%
近60日涨幅: {price_change_60d}%
换手率分位: {turnover_percentile}%
F-Score: {f_score}/9
```

**注**：涨幅窗口采用近60日（而非源 §5.3 示例的近6月），与 L1 heat filter HF2 对齐。`receivables_growth`（应收账款增速）因 L0 financials 无该字段（L1 spec 明确跳过），MVP 暂不实现，待 L0 补充后启用。

**注意**：括号内的趋势标注（如 `← 趋势下降`、`← 匹配`）由 `input_assembly.py` 在组装快照时自动计算，不是 LLM 生成。

### 输出 Schema（verdict/confidence/flags 结构）

| 字段 | 类型 | 说明 |
|------|------|------|
| `verdict` | enum | `deep_dive` / `watch` / `skip` |
| `confidence` | int | 0-100，LLM 自评置信度 |
| `one_liner` | str | 一句话结论（≤50 字） |
| `red_flags` | list[str] | 红旗清单，每条必须引用具体数据 |
| `green_flags` | list[str] | 绿旗清单，每条必须引用具体数据 |
| `anti_trap_flags` | list[str] | 价值陷阱信号（补充 L1 ANTI_TRAP） |

---

## §3 输出质量保证（来源：total-design §5.6 + AD-06）

AD-06 约束：L2 不做案例校准，只做一致性保障。以下四条必须全部落地：

### 3.1 temperature=0 消除随机性

- LLM 调用固定 `temperature=0.0`（见 §1 决策 2 代码）
- 消除模型随机性，确保相同输入产生相同输出

### 3.2 阈值缓冲带（verdict 覆盖逻辑）

```
confidence ≥ 60           →  信任 LLM 的 verdict（deep_dive / skip）
40 ≤ confidence < 60      →  强制覆盖 verdict = "watch"（无论 LLM 输出什么）
confidence < 40           →  强制覆盖 verdict = "watch" + 标记低置信度异常
```

**实现位置**：`scout/parse.py` 的 `apply_buffer_zone(verdict, confidence)` 函数。

**verdict 覆盖优先级**：LLM 输出的 verdict 仅在 confidence ≥ 60 时生效；缓冲带和低置信度区间一律覆盖为 `watch`，确保所有通过 L1 的股票都有 L2 判断，不会出现"LLM 改主意后股票凭空消失"。

### 3.3 缓存 24h + 输入特征快照

- L2 结果写入 `data/cache/{ticker}/{date}/l2_scout.json`，TTL=24h（与 L0 DAILY_PRICE 档位一致）
- 同交易日不重跑（cache 命中直接复用，不重复调用 LLM）
- **缓存必须包含输入特征快照**（PE/PB/ROE/估值分位等当时的值），而不仅仅是 L2 输出
- 当用户发现"昨天判 deep_dive 今天判 watch"时，可以对比输入快照确认是数据变了还是模型飘了
- `{date}` 子目录隔离不同交易日结果，次日重跑不覆盖昨日文件，支持跨日对比诊断

**缓存结构**：
```json
{
  "verdict": "watch",
  "confidence": 72,
  "one_liner": "...",
  "red_flags": [...],
  "green_flags": [...],
  "anti_trap_flags": [...],
  "input_snapshot": {
    "pe_ttm": 38.5,
    "pb": 8.2,
    "roe_3y": [28, 25, 22],
    "market_cap": 2800,
    ...
  },
  "timestamp": "2026-06-29T10:30:00"
}
```

**实现位置**：`scout/quality.py` 的 `ScoutCache` 类（复用 L0 `CacheManager` 的原子写模式）。

**与 CacheManager 的关系**：ScoutCache 独立实现，不扩展 `CacheManager._DIM_TTL`。原因：
- L2 缓存路径结构不同（含 `{date}` 子目录）
- L2 缓存 TTL 语义不同（跨日保留 vs 24h 过期）
- L2 缓存需存储 `input_snapshot`（诊断用途），L0 CacheManager 无此需求

### 3.4 多轮投票 MVP 不做

- 成本 +200%（3 轮投票），收益有限（§5.6 表格）
- 实际跑出问题再决定（条件：某些股票反复在 deep_dive/watch 之间摇摆）

**源内矛盾说明**：§5.6 末段提到"通过 §6.6 校准测试体系解决 Prompt 模糊地带"，但 AD-06 明确"L2 不做案例校准，只做一致性保障"。本 spec 遵循 AD-06，边界模糊问题靠缓冲带（40-60→watch）运行时缓解。后续若需校准，由 L3 校准体系统一处理。

---

## §4 并发 LLM 调用（来源：total-design §5.5）

### 批量并发策略

```python
async def scout_batch(candidates: list[dict]) -> list[dict]:
    """并发对 200 只股票做 LLM 初筛"""
    # 每批 20 并发（避免 rate limit）
    # 用 asyncio.Semaphore(20) 控制并发数
    # 返回 deep_dive 候选（按 confidence 降序排序）
```

**实现要点**：
- `asyncio.Semaphore(20)` 控制并发（避免 API rate limit）
- 单只超时 60s（`httpx.AsyncClient(timeout=60.0)`）
- 失败重试 1 次（退避 2s）
- 异常收窄：只捕获 `httpx.HTTPStatusError` / `httpx.TimeoutException`，不用 `except Exception`（CLAUDE.md 工程债约束）

### 输出过滤

- 只返回 `verdict == "deep_dive"` 的候选（供 L3 消费），**top-20 cap**（按 confidence 降序取前 20，AD-03 成本闸门 200→20）
- `verdict == "watch"` 的候选保留在 L2 结果中（供 L4 监控），但不进入 L3
- `verdict == "skip"` 的候选标记为排除（附 red_flags 供可解释性）

**watch 候选持久化**：watch 候选散落在 per-ticker cache 文件（`data/cache/{ticker}/{date}/l2_scout.json`）中，L4 消费时按需扫描。deep_dive 短名单有独立输出文件（`--output`），不受 cache 清理影响。

---

## §5 边界

### IN
- `scout/prompt.py` — Scout system prompt 模板 + 特征快照格式化
- `scout/input_assembly.py` — L1→L2 数据交接（从 L0 cache 取全维度原始数据）
- `scout/batch.py` — 并发 LLM 调用（httpx 直连，asyncio 并发）
- `scout/parse.py` — 结构化输出解析 + verdict 覆盖逻辑（缓冲带）
- `scout/quality.py` — 输出质量保证（24h 缓存含输入快照）
- `cli.py` 集成 — `scout` 子命令

### OUT
- `screener/`（L1 已实现）
- `council/`（L3 天团辩论是 L3a 的事）
- `monitor/`（L4 监控是 L4 的事）
- `watchlist/`（watchlist 增量 diff/历史轨迹是 L4 的职责）
- `frontend/`（Streamlit 前端）
- 数据采集（L0 已实现）
- L2 不做 LLM 推理本身以外的判断（护城河/管理层/认知差是 L3 的事）

---

## §6 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM API 不可用/超时 | L2 管线中断 | 单只超时 60s + 重试 1 次（退避 2s）；失败不阻塞整批（跳过该 ticker，标记为 `error`） |
| LLM 输出非 JSON | 解析失败 | `response_format: {"type": "json_object"}` 强制 JSON 输出；解析失败时 verdict 覆盖为 `watch` + 标异常 |
| L0 cache 缺失/过期 | 特征快照不完整 | `input_assembly` 对缺失字段用 `None` 占位，prompt 中标注"数据缺失"；**关键字段（name/industry/market_cap）任一缺失或整体缺失 >50% 时跳过 LLM 调用**（标记 `verdict: "error", reason: "insufficient_data"`），不花钱跑垃圾输入 |
| LLM verdict 不一致（同一输入不同输出） | 用户困惑 | temperature=0 + 缓存 24h 消除短期波动；输入快照机制让用户区分"数据变了"vs"模型飘了" |
| 成本超预期 | ¥2/轮 → ¥? | 缓存 24h 减少 80% 调用（同交易日不重跑）；top-20 cap 保障 AD-03 成本闸门；`LLM_MODEL` fail-fast 避免部署漏配导致运行时错误 |
| L1→L2 数据交接延迟 | L0 cache 未命中 | L2 依赖 L1 已跑过（cache 已预热）；CacheManager.get() 只读不触发回填（L0 契约），缺失过多时跳过 LLM 调用 |

---

## §7 待确认

- 并发数 20 是否需要根据 API rate limit 调整（部署时确定）
- 输入快照的字段列表是否需要随 L0 新增字段扩展（MVP 先用现有维度）
