# l4b-docker-run 端到端实跑验证笔记

> 2026-07-01 实跑，DeepSeek（deepseek-v4-flash）作 LLM，单模型覆盖 heavy/moderate/light。

## 两道验证门结果

### 门 1：最小闭环（L0→L3→L4）✅

`docker compose run --rm value-screener council --ticker 600519`

- 退出码 0
- `debate/600519/2026-07-01.md` 生成，含 Round 1 巴菲特输出（signal=bullish, conviction=75）
- `watchlist/2026-07-01_600519.SH.json` 生成，`final_verdict="bullish"`、`key_variables` 非 null
- 成本：单次 LLM 调用，~¥0.x（DeepSeek 定价）

### 门 2：完整链路（L1→L2→L3）✅

- `batch data/tickers.txt`（20 只）→ 全采到 5 维度缓存
- `screen --tickers data/tickers.txt --output data/l1.json` → 20→19(hard gates)→19(factors)→6(heat filter)，6 个 candidate
  - `stats.input_scale == "subset"` ✅（20 < 300）
  - `stats.industry_pe_degraded == True` ✅（同行业样本不足，PE map 为空）
  - **本 change 的 L1 退化标记在真实数据上生效**
- `scout --input data/l1.json --output data/l2.json` → 6 candidates → 2 deep_dive（600519 conf=85、600009 conf=70）
  - L1→L2 接缝顺畅：L2 只读 ticker，能消费 L1 candidates 列表 ✅
  - L2 输出质量好：引用真实特征（PE 17.92 处 5 年分位 16.53%、ROE 32%+、F-Score 8/9）
- 5.5 人工挑 **600009 上海机场**（避开已跑的茅台，且 confidence 70 有现金流亮点）
- `council --ticker 600009` → `final_verdict="neutral"`、`conviction=51`
  - `consensus_summary`/`dissent_points`/`pending_verification` **全非 null**（R4 真跑了）
  - 辩论有信息增量：多数中性（估值缺安全边际、ROE 3.8% 偏低）vs 冯柳逆向（PB 历史低位、赔率 2.5:1）
  - `debate/600009/2026-07-01.md`（10.7KB，4 轮完整）

## 接缝顺畅度总结

| 接缝 | 状态 | 备注 |
|---|---|---|
| Docker compose → CLI | ✅ | `command` 覆盖 ENTRYPOINT，子命令透传正常 |
| `.env` → compose env | ✅ | 5 个 LLM 变量注入，`${VAR:?err}` fail-fast 验证通过 |
| bind mount 三卷 | ✅ | data/watchlist/debate 产出落宿主，跨容器复用 |
| L0 采数（akshare 公网）| ✅ | 容器内能访问 akshare，茅台/上海机场等采数成功 |
| L1 → L2 | ✅ | L2 只读 ticker，无运行时断裂（与 design 核实结论一致）|
| L1 stats 退化标记 | ✅ | `industry_pe_degraded`/`input_scale` 在 20 只真实数据上正确触发 |
| L2 → L3 | ✅ | 人工从 deep_dive 挑一只，`council --ticker` 跑通 |
| L3 → L4 watchlist | ✅ | `_write_council_output` 写出 JSON，字段对齐 |

## 发现的既有问题（非本 change 引入，记录备查）

### 1. 缓存过期导致 council 首跑 insufficient_data ⚠️

**现象**：门1 首次跑 `council --ticker 600519` 直接崩 `ValueError: insufficient_data`，missing 几乎所有字段。

**根因**：`CacheManager` 的 TTL 实际是 24h（`QUARTERLY=24*3600`，注释写 90d 但代码是 24h，注释与代码不一致）。6/30 采的缓存到 7/1 已过期，`cache_manager.get` 返回 None。`assemble_snapshot` 只读缓存不触发采集，`council` 命令也没先 `batch` 采数——假设数据已在缓存且未过期。

**临时绕过**：门1 前手动 `fetch` 逐维度刷新缓存（本笔记做的）。

**建议后续 change**：
- `council` 命令在 `assemble_council_features` 返 insufficient 时，自动触发该 ticker 的 `batch` 重采（或提示用户先跑 `batch`）
- 或修正 TTL 注释/代码不一致（financials 注释 90d 实际 24h）
- 这属于 L3/L0 既有缺陷，不在 l4b-docker-run 范围

### 2. 门1 茅台 L3 输出质量异常 ⚠️

**现象**：门1 茅台的 L3 输出：
- `core_thesis` 串台——buffett 写 "munger 看好长期价值"、munger 写 "duan 看好长期价值"、duan 写 "feng_liu 考虑其他观点后调整"。R1 本该隔离（`other_opinions=None`），却出现别的 agent 名字。
- `consensus_summary`/`dissent_points`/`pending_verification` 全 null（R4 被跳过或失败）
- `key_variables` 8 个里 7 个重复 "市场份额大幅下降"
- 多 agent 输出高度同质化（都引 ROE 32%、可口可乐）

**对比**：门2 上海机场的 L3 输出质量明显更好——R4 真跑、consensus/dissent/pending 全非 null、辩论有信息增量（多数中性 vs 冯柳逆向）。

**可能原因**（未深查）：
- R1 prompt 模板把别的 agent 信息泄露（但 debate.py:424 R1 传 `other_opinions=None`，代码看着对）
- DeepSeek 模型把 system prompt 里的示例当真
- 茅台特征（PE 历史低位 + ROE 32%）太"完美"，agent 容易输出同质化 bullish
- temperature=0 但长输出仍有波动

**建议后续 change**：这是 L3 council 既有质量问题（CLAUDE.md「已知差距」已记"四 agent 输出高度同质化"），应由专门评估 L3 辩论增量的 change 处理，不属于 l4b-docker-run。

### 3. L0 缓存 ticker 规范不统一 ⚠️

**现象**：`data/cache/` 下同票两份目录：`600519` 和 `600519.SH`、`000858` 和 `000858.SZ`。fetcher 写缓存时有的用纯数字、有的带后缀。

**影响**：不影响门2（L1 screen 用纯数字 ticker 读 `600519` 目录，能读到）。但长期看浪费存储、且 council 用 `600519.SH` 时读 `600519.SH` 目录（只有 basic，导致门1前 insufficient——虽然根因是 TTL，但目录分裂加剧了问题）。

**建议后续 change**：L0 fetcher 统一用纯 6 位数字作缓存 key（normalize 在 CacheManager 层做）。不属于 l4b-docker-run。

## 结论

**本 change 的目标——Docker 端到端跑通一只真实票——完全达成。** 两道验证门通过，L1 stats 退化标记在真实数据上生效，L1→L2→L3→L4 全链路接缝顺畅。发现的 3 个既有问题（缓存 TTL、L3 输出质量、缓存 key 分裂）均非本 change 引入，已记录备查，留待后续 change。
