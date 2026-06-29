## Why

L1 量化筛选将 ~5000 只 A 股压缩至 ~200 只候选池，但 L3 天团深研成本高（¥20-60/只），200 只全丢 L3 成本 ¥4000-12000 不可承受（AD-03）。L2 Scout Agent 是必要的成本闸门，用轻量 LLM 推理（¥0.01/只，~¥2/轮）将 200 只压缩至 ~20 只 deep_dive 候选，供 L3 消费。

## What Changes

- 新增 `scout/prompt.py` — Scout system prompt 模板（~200 tokens 特征快照输入 + verdict/confidence/flags JSON 输出）
- 新增 `scout/parse.py` — 结构化输出解析 + verdict 覆盖逻辑（缓冲带 confidence 40-60 强制 watch，<40 覆盖 watch + 标低置信度异常）
- 新增 `scout/batch.py` — 并发 LLM 调用（OpenAI 兼容 httpx 直连，temperature=0，20 并发/批）
- 新增 `scout/quality.py` — 输出质量保证（24h 缓存含输入特征快照，区分"数据变了"vs"模型飘了"）
- 新增 `scout/input_assembly.py` — L1→L2 数据交接（从 L0 cache 取全维度原始数据组装特征快照）
- 修改 `cli.py` — 新增 `scout` 子命令，读取 L1 输出 + 调用 L2 管线
- 复用 `httpx`（L0 已引入 `httpx~=0.27.0`）实现 OpenAI 兼容 LLM 直连，无需新增依赖

## Capabilities

### New Capabilities
- `scout-prompt`: Scout system prompt 模板，定义 LLM 输入（特征快照 ~200 tokens）和输出（verdict/confidence/flags JSON schema）
- `scout-batch`: 并发 LLM 调用管线，OpenAI 兼容 httpx 直连，temperature=0，20 并发/批，轻量推理模型（AD-04）
- `scout-parse`: 结构化输出解析 + verdict 覆盖逻辑（缓冲带 + 低置信度异常标记）
- `scout-quality`: 输出质量保证（24h 缓存含输入快照，区分数据变化 vs 模型飘了）
- `scout-input-assembly`: L1→L2 数据交接，从 L0 CacheManager 取全维度原始数据组装特征快照
- `scout-cli`: CLI 集成，`scout` 子命令读取 L1 输出并调用 L2 管线

### Modified Capabilities
<!-- 无：L2 不修改 L1 或 L0 的已有 spec -->

## Impact

- **代码**: 新增 `value-screener/scout/` 目录（prompt.py / parse.py / batch.py / quality.py / input_assembly.py / __init__.py），修改 `value-screener/cli.py` 追加 scout 子命令
- **API**: 消费 L0 `CacheManager.get(ticker, dim)` 取全维度数据（basic/financials/kline/valuation/risk），不新增数据采集
- **依赖**: 复用 L0 已有的 `httpx~=0.27.0`（async HTTP，OpenAI 兼容 API 直连），不新增依赖
- **环境变量**: 复用 total-design §9.1 docker-compose 约定的 `LLM_API_KEY` / `LLM_API_BASE`，新增 `LLM_MODEL`（AD-04 不固定模型种类，只标推理等级=轻量）
- **缓存**: L2 结果写入 `data/cache/{ticker}/{date}/l2_scout.json`（TTL=24h，含输入特征快照，按日隔离便于跨日对比诊断）
- **成本**: ~¥2/轮（200 只 × ¥0.01/只，AD-03）
- **依赖 change**: L1 已完成（candidate list 来源），L0 已完成（CacheManager 已实现）
