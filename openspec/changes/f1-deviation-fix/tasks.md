# Tasks

> 依赖：proposal.md / design.md / specs/（4 个 delta）
> 实施顺序：P0 根因定位（D1 实验 → D2/D4 分叉）→ P1 全市场验证（D3+D5）→ 质量门校验（G4）
> 每个 task 标注验证方式（Verify），遵循 TDD：先写测试/实验，再改代码

## 1. P0 根因定位：最小复现实验（D1）

- [ ] 1.1 写最小复现脚本 `scripts/repro_r1.py`：对 600519 / 600900 / 600009 三只票，调用 `assemble_council_features(ticker)`，dump 返回的 features dict 到 `scripts/repro_out/{ticker}_features.json`。**Verify**：三个文件生成，人工对比 600519/600900 的 features 是否空/缺关键字段 vs 600009 是否齐全
- [ ] 1.2 扩展脚本：调用 `debate._build_user_message(ticker, features, other_opinions=None)`，dump 完整 user_message 到 `scripts/repro_out/{ticker}_user_msg.txt`。**Verify**：三份 user message 生成，确认 features JSON 段是否真的进了 user message
- [ ] 1.3 跑一次真实 R1：对三只票各调一次 `call_agent("buffett", ticker, features)`（force=True 跳过缓存），dump 输出 AgentOutput。**Verify**：对比 600519/600900 输出是否仍逐字相同、是否仍出现"munger 看好"环形引用；600009 是否仍引用真实特征
- [ ] 1.4 根因判定：根据 1.1-1.3 结果，按 design D1 判据填 `scripts/repro_out/ROOT_CAUSE.md`——若 features 空/缺 → 根因在代码层（走 §2）；若 features 正常但模型仍编造 → 根因在模型层（走 §3）。**Verify**：ROOT_CAUSE.md 写明判定依据和指向的 task 组

## 2. P0 代码层修复（若 §1.4 判定代码层，D2）

- [ ] 2.1 在 `council/features.py::assemble_council_features` 加关键字段充分性校验：返回的 dict 若 name/industry/pe_ttm/roe 等关键字段全空，返回 `{"error": "insufficient_data", "missing_fields": [...]}`。先写测试 `tests/test_features_sufficiency.py` 验证空 dict 和缺字段场景。**Verify**：测试 fail（未实现）→ 实现 → 测试 pass
- [ ] 2.2 验证 `debate.py::run_debate` 已有的 `if "error" in features: raise ValueError` 能消费新校验返回的 error，错误信息含缺失字段列表。**Verify**：对 600519（若 features 仍空）跑 `council --ticker 600519 --force`，应 fail-fast 报 insufficient_data + 缺失字段，不再产出幻觉 watchlist
- [ ] 2.3 联动验证 review-notes #1：确认 fail-fast 错误信息提示用户"先跑 `batch` 重采"。**Verify**：错误消息文案含可操作的下一步指引

## 3. P0 模型层记录（若 §1.4 判定模型层，D4）

- [ ] 3.1 在 `design/deviation-analysis-2026-07-01.md` §1.3 补充实验结论：features 正常注入但模型仍输出幻觉，记录为"DeepSeek temperature=0 下对空/简输入的案例锚定幻觉"已知限制。**Verify**：文档更新，标注根因落在模型层
- [ ] 3.2 起草衍生 change 提案（不在本 change 实施）：评估方向 a（prompt 强约束"必须引用下方特征数据，禁止引用其他分析师"）vs 方向 b（换更强 LLM_MODEL_HEAVY）。**Verify**：衍生 change 提案文档存在，列出两个方向的取舍

## 4. P1 cache ticker normalize（D3）

- [ ] 4.1 定位 CacheManager 实现（`data/cache/manager.py` 或 fetcher 层），找到 ticker key 读写入口。**Verify**：定位到具体文件和函数
- [ ] 4.2 先写测试 `tests/test_cache_ticker_normalize.py`：以 `600519.SH` / `600519` / `600519.SZ` 三种格式读写同一维度，SHALL 命中同一份缓存。**Verify**：测试 fail（未 normalize）
- [ ] 4.3 在 CacheManager `get`/`set` 入口加 `ticker.split(".")[0]` normalize，与 `features.py:23-24` 对齐。**Verify**：测试 pass
- [ ] 4.4 清理 `data/cache/` 下已存在的带后缀空壳目录（`600519.SH/` 等），以纯数字目录为唯一真值。**Verify**：`ls data/cache/` 不再有 `.SH`/`.SZ` 后缀目录

## 5. P1 全市场需求 A 验证（D5）

- [ ] 5.1 写脚本拉取全 A 股代码列表（akshare），存 `data/all_a_share.txt`。**Verify**：文件含 ~5000 个 6 位代码
- [ ] 5.2 跑 `batch data/all_a_share.txt`（分批 + 三级容错，复用已有 L0 采数），采全市场缓存。**Verify**：`data/cache/` 目录数接近全 A 股数量，采数成功率记录
- [ ] 5.3 跑 `screen --tickers data/all_a_share.txt --output data/l1_full.json`，记录 L1 漏斗比例（5000→hard_gates→factors→heat_filter 各阶段数量）和 `stats.input_scale`/`industry_pe_degraded` 触发情况。**Verify**：`data/l1_full.json` 生成，漏斗比例记录到 `scripts/repro_out/l1_full_funnel.md`
- [ ] 5.4 跑 `scout --input data/l1_full.json --output data/l2_full.json`，记录 L2 deep_dive/watch/skip 分布、confidence 直方图、LLM 调用次数和费用。**Verify**：`data/l2_full.json` 生成，区分度记录到 `scripts/repro_out/l2_full_distribution.md`，验证 AD-03 成本假设
- [ ] 5.5 对比全市场结果与 20 只手工样本的漏斗比例/区分度差异。**Verify**：对比记录写入 `scripts/repro_out/sample_vs_full.md`，确认 L2 不是"对所有白马都输出 deep_dive"的同质化筛选

## 6. 质量门校验（G4）

- [ ] 6.1 在 `council/verify_quality_gate.py` 新增"R1 引用真实特征"校验：检查 R1 AgentOutput 的 `key_metrics` 至少 1 个能在传入 features JSON 找到来源。先写测试。**Verify**：测试 fail → 实现 → pass
- [ ] 6.2 新增"R1 环形引用检测"：R1（other_opinions=None）的 `core_thesis` 出现其他 agent_id 名字时标记为幻觉引用。**Verify**：对 600519 旧 debate 文件回放，校验能识别"munger 看好"这类环形引用
- [ ] 6.3 对 P0 修复后的 600519/600900 重跑全天团辩论，验证质量门能区分真实产出（引用真实特征）vs 幻觉产出（被拦截）。**Verify**：600009 通过质量门，600519/600900 若 features 仍不足则 fail-fast 在 R1 入口、不进入质量门

## 7. 收尾

- [ ] 7.1 更新 `design/deviation-analysis-2026-07-01.md` §4 纠偏优先级，标注 P0/P1 完成状态和根因判定结果。**Verify**：文档状态与实际一致
- [ ] 7.2 跑 `pytest value-screener/tests/` 全套测试，确认无回归。**Verify**：测试全 pass
- [ ] 7.3 准备 archive：确认 proposal/design/specs/tasks 一致，根因判定和修复路径有实验数据支撑。**Verify**：可进入 `opsx:archive`
