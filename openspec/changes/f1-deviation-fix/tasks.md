# Tasks

> 依赖：proposal.md / design.md / specs/（4 个 delta）
> 实施顺序：P0 根因现状确认（D1 → D2/D4 分叉）→ P1.5 call_llm token 采集（§7，纯代码重构不依赖全市场数据）→ P1 全市场验证（§4-5 cache + 全市场，§5.4 依赖 §7 的 usage 采集）→ 质量门校验（G4）
> 每个 task 标注验证方式（Verify），遵循 TDD：先写测试/实验，再改代码

## 1. P0 根因现状确认（D1，缩减版）

- [ ] 1.1 写脚本 `scripts/repro_features.py`：对 600519 / 600900 / 600009 三只票，调用 `assemble_council_features(ticker)`，dump 返回的 features dict 到 `scripts/repro_out/{ticker}_features.json`，重点检查 financials_floor（pe_ttm/roe_3y/net_margin）是否为 None。**Verify**：三个文件生成，确认 600519/600900 的 financials 字段当前是否为 None（验证 cache 状态是否仍复现漏洞），600009 是否齐全
- [ ] 1.2 根因判定：根据 1.1 结果按 design D1 判据——若 financials_floor 确为 None → 确认根因在代码层 guard 放行，直接走 §2；若 features 竟然齐全 → 根因可能也在模型层，§2 的 guard 加固仍有价值（堵未来数据缺失），另起 §3 衍生 change。**Verify**：判定结论写入 `scripts/repro_out/ROOT_CAUSE.md`（1 段即可，不搞仪式）

## 2. P0 代码层修复（若 §1.2 判定代码层，D2）

- [ ] 2.1 先写测试 `tests/test_features_sufficiency.py`：构造 features dict，name/market_cap 有值但 pe_ttm/roe_3y/net_margin 全 None 的场景，断言 `assemble_snapshot` 返回 `{"error": "insufficient_data", "missing_fields": ["pe_ttm","roe_3y","net_margin"]}`。**Verify**：测试 fail（现有 guard 因缺失率 <50% 放行，不返回 error）
- [ ] 2.2 在 `scout/input_assembly.py` guard 段（约 338-354 行）新增 `financials_floor = ["pe_ttm", "roe_3y", "net_margin"]` 校验：任一为 None 即返回 `insufficient_data`，与现有 `critical_fields`/`missing_ratio>0.5` 并列。**Verify**：测试 pass
- [ ] 2.3 验证 `council/features.py::assemble_council_features` 透传新 error（已有 `if "error" in features: return features` 链路），`debate.py::run_debate` 的 `if "error" in features: raise ValueError` 能消费。**Verify**：对 600519（若 features 仍空）跑 `council --ticker 600519 --force`，应 fail-fast 报 insufficient_data + 缺失字段，不再产出幻觉 watchlist
- [ ] 2.4 联动验证 review-notes #1：确认 fail-fast 错误信息提示用户"先跑 `batch` 重采"。**Verify**：错误消息文案含可操作的下一步指引

## 3. P0 模型层记录（若 §1.2 判定模型层，D4）

- [ ] 3.1 在 `design/deviation-analysis-2026-07-01.md` §1.3 补充实验结论：features 正常注入但模型仍输出幻觉，记录为"DeepSeek temperature=0 下对空/简输入的案例锚定幻觉"已知限制。**Verify**：文档更新，标注根因落在模型层
- [ ] 3.2 起草衍生 change 提案（不在本 change 实施）：评估方向 a（prompt 强约束"必须引用下方特征数据，禁止引用其他分析师"）vs 方向 b（换更强 LLM_MODEL_HEAVY）。**Verify**：衍生 change 提案文档存在，列出两个方向的取舍

## 4. P1 cache ticker normalize（D3）

- [ ] 4.1 定位 CacheManager 实现（`data/cache/manager.py` 或 fetcher 层），找到 ticker key 读写入口。**Verify**：定位到具体文件和函数
- [ ] 4.2 先写测试 `tests/test_cache_ticker_normalize.py`：以 `600519.SH` / `600519` / `600519.SZ` 三种格式读写同一维度，SHALL 命中同一份缓存。**Verify**：测试 fail（未 normalize）
- [ ] 4.3 在 CacheManager `get`/`set` 入口加 `ticker.split(".")[0]` normalize，与 `features.py:23-24` 对齐。**Verify**：测试 pass
- [ ] 4.4a 扫描 `data/cache/` 下所有带后缀目录（`.SH`/`.SZ`），对每个检查是否含真实数据文件（basic.json/financials.json/kline.json/risk.json/valuation.json），标记为"空壳"或"有真实数据"。**Verify**：扫描结果列表记录到 `scripts/repro_out/cache_dir_audit.md`，标出孤儿目录（无纯数字对应的）
- [ ] 4.4b 按扫描结果迁移：空壳目录直接删；有真实数据的，若纯数字目录存在则人工确认后合并、若纯数字目录不存在（孤儿目录如 `002594.SZ`）则创建纯数字目录并移动数据文件后再删后缀目录。**Verify**：`ls data/cache/` 不再有 `.SH`/`.SZ` 后缀目录，且迁移前后真实数据文件总数不减少（`find data/cache -name "*.json" | wc -l` 对比）

## 5. P1 全市场需求 A 验证（D5）

- [ ] 5.1 写脚本拉取全 A 股代码列表（akshare），存 `data/all_a_share.txt`。**Verify**：文件含 ~5000 个 6 位代码
- [ ] 5.2 跑 `batch data/all_a_share.txt`（分批 + 三级容错，复用已有 L0 采数），采全市场缓存。**Verify**：`data/cache/` 目录数接近全 A 股数量，采数成功率记录
- [ ] 5.3 跑 `screen --tickers data/all_a_share.txt --output data/l1_full.json`，记录 L1 漏斗比例（5000→hard_gates→factors→heat_filter 各阶段数量）和 `stats.input_scale`/`industry_pe_degraded` 触发情况。**Verify**：`data/l1_full.json` 生成，漏斗比例记录到 `scripts/repro_out/l1_full_funnel.md`
- [ ] 5.4 跑 `scout --input data/l1_full.json --output data/l2_full.json`，记录 L2 deep_dive/watch/skip 分布、confidence 直方图、LLM 调用次数、token 消耗（prompt_tokens/completion_tokens，依赖 §7 的 call_llm usage 采集）、总费用。**Verify**：`data/l2_full.json` 生成，区分度 + 成本记录到 `scripts/repro_out/l2_full_distribution.md`，验证 AD-03 成本假设（≈¥0.01/只）
- [ ] 5.5 对比全市场结果与 20 只手工样本的漏斗比例/区分度差异。**Verify**：对比记录写入 `scripts/repro_out/sample_vs_full.md`，确认 L2 不是"对所有白马都输出 deep_dive"的同质化筛选

## 6. 质量门校验（G4）

- [ ] 6.0 重构 `council/verify_quality_gate.py` 为可导入模块：把核心校验逻辑抽成可测试函数（如 `verify_r1_feature_grounding(output, features) -> tuple[bool, list[str]]`），CLI 的 argparse+print 部分只做包装。**Verify**：`from council.verify_quality_gate import verify_r1_feature_grounding` 可导入，现有 CLI 调用方式不破坏
- [ ] 6.1 先写测试 `tests/test_r1_feature_grounding.py`：构造 R1 AgentOutput 的 `key_metrics` 含数字 "32"，features 对应字段为 None 或值不匹配，断言反向校验返回 False（幻觉）。**Verify**：测试 fail（未实现）
- [ ] 6.2 实现反向校验：提取 `key_metrics` 里的数字，检查是否在 features 任一字段值中出现；含凭空数字则标记幻觉。**Verify**：测试 pass
- [ ] 6.3 实现"R1 环形引用检测"：R1（other_opinions=None）的 `core_thesis` 出现其他 agent_id 名字（munger/duan/feng_liu/buffett 互引）时标记为幻觉引用。**Verify**：对 600519 旧 debate 文件回放，校验能识别"munger 看好"这类环形引用
- [ ] 6.4 对 P0 修复后的 600519/600900 重跑全天团辩论，验证质量门能区分真实产出（引用真实特征）vs 幻觉产出（被拦截）。**Verify**：600009 通过质量门，600519/600900 若 features 仍不足则 fail-fast 在 R1 入口、不进入质量门

## 7. call_llm token usage 采集（D6，方案 B）

- [ ] 7.1 先写测试 `tests/test_llm_usage.py`：mock httpx 响应含 `usage: {prompt_tokens: 100, completion_tokens: 50, total_tokens: 150}`，断言 `call_llm` 返回 `(content, usage)` 且 usage 字段完整。**Verify**：测试 fail（当前 call_llm 只返回 str）
- [ ] 7.2 扩展 `council/llm.py::call_llm`：从 `resp.json()["usage"]` 提取 token usage，返回 `(content, usage)`，签名从 `-> str` 改为 `-> tuple[str, dict]`。**Verify**：测试 pass
- [ ] 7.3 适配 L3 调用点：`council/debate.py` 的 `call_agent`/`_call_da`/`_call_synthesizer` 解构 `raw_json, usage = await call_llm(...)`，`AgentOutput.from_json` 只消费 raw_json 不受影响。**Verify**：`pytest tests/test_council_debate*.py` 通过
- [ ] 7.4 适配 L2 调用点：`scout/batch.py` 解构 `content, usage = await call_llm(...)`，累加 usage 到 batch 汇总。**Verify**：`pytest tests/test_scout*.py` 通过
- [ ] 7.5 移除 `verify_quality_gate.py::verify_cost` 里"token usage 未被采集"的注释，改为真实采集累加。**Verify**：verify_cost 输出含真实 token 数和费用估算

## 8. 收尾

- [ ] 8.1 更新 `design/deviation-analysis-2026-07-01.md` §4 纠偏优先级，标注 P0/P1 完成状态和根因判定结果。**Verify**：文档状态与实际一致
- [ ] 8.2 跑 `pytest value-screener/tests/` 全套测试，确认无回归（尤其 call_llm 签名改动后 L2/L3 调用点全适配）。**Verify**：测试全 pass
- [ ] 8.3 准备 archive：确认 proposal/design/specs/tasks 一致，根因判定和修复路径有实验数据支撑。**Verify**：可进入 `opsx:archive`
