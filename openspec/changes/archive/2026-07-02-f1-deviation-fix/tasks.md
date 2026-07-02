# Tasks

> 依赖：proposal.md / design.md / specs/（4 个 delta）
> 实施顺序：P0 根因现状确认（D1 → D2/D4 分叉）→ P1.5 call_llm token 采集（§7，纯代码重构不依赖全市场数据）→ P1 全市场验证（§4-5 cache + 全市场，§5.4 依赖 §7 的 usage 采集）→ 质量门校验（G4）
> 每个 task 标注验证方式（Verify），遵循 TDD：先写测试/实验，再改代码

## 1. P0 根因现状确认（D1，缩减版）

- [x] 1.1 写脚本 `scripts/repro_features.py`：对 600519 / 600900 / 600009 三只票，调用 `assemble_council_features(ticker)`，dump 返回的 features dict 到 `scripts/repro_out/{ticker}_features.json`，重点检查 financials_floor（pe_ttm/roe_3y/net_margin）是否为 None。**Verify**：三个文件生成，确认 600519/600900 的 financials 字段当前是否为 None（验证 cache 状态是否仍复现漏洞），600009 是否齐全 ✓ — 三票均返回 insufficient_data；600519/600009 financials 维度其实新鲜（21.5h<24h），是 basic 维度 2h TTL 过期触发 critical_fields；600900 整盘过期。详见 repro_out/repro_summary.json
- [x] 1.2 根因判定：根据 1.1 结果按 design D1 判据——若 financials_floor 确为 None → 确认根因在代码层 guard 放行，直接走 §2；若 features 竟然齐全 → 根因可能也在模型层，§2 的 guard 加固仍有价值（堵未来数据缺失），另起 §3 衍生 change。**Verify**：判定结论写入 `scripts/repro_out/ROOT_CAUSE.md`（1 段即可，不搞仪式）✓ — 判定代码层，走 §2；§3 不执行。现实触发路径是 basic 维度 2h TTL 过期导致 critical_fields 缺失，design 原假设的"缺失率<50% 放行"是潜在路径（需 basic 恰好新鲜），financials_floor 硬门槛价值在于不依赖 TTL 巧合独立兜底

## 2. P0 代码层修复（若 §1.2 判定代码层，D2）

- [x] 2.1 先写测试 `tests/test_features_sufficiency.py`：构造 features dict，name/market_cap 有值但 pe_ttm/roe_3y/net_margin 全 None 的场景，断言 `assemble_snapshot` 返回 `{"error": "insufficient_data", "missing_fields": ["pe_ttm","roe_3y","net_margin"]}`。**Verify**：测试 fail（现有 guard 因缺失率 <50% 放行，不返回 error）✓ — 4 测试中 test_financials_floor_one_none（仅 net_margin 缺、其余齐全）fail，正中 design 假设的漏洞路径
- [x] 2.2 在 `scout/input_assembly.py` guard 段（约 338-354 行）新增 `financials_floor = ["pe_ttm", "roe_3y", "net_margin"]` 校验：任一为 None 即返回 `insufficient_data`，与现有 `critical_fields`/`missing_ratio>0.5` 并列。**Verify**：测试 pass ✓ — 6 测试全 pass（含原有 8 个 input_assembly 测试无回归）
- [x] 2.3 验证 `council/features.py::assemble_council_features` 透传新 error（已有 `if "error" in features: return features` 链路），`debate.py::run_debate` 的 `if "error" in features: raise ValueError` 能消费。**Verify**：对 600519（若 features 仍空）跑 `council --ticker 600519 --force`，应 fail-fast 报 insufficient_data + 缺失字段，不再产出幻觉 watchlist ✓ — 透传链路 features.py:28-29 → debate.py:403-409 已验证；新增 e2e 测试 test_run_debate_fail_fast_on_insufficient_features 断言 LLM 未被触达
- [x] 2.4 联动验证 review-notes #1：确认 fail-fast 错误信息提示用户"先跑 `batch` 重采"。**Verify**：错误消息文案含可操作的下一步指引 ✓ — debate.py 错误消息改为含缺失字段 + "请先运行 batch 重采" + TTL 提示；test_run_debate_fail_fast_message_mentions_ttl 锁定文案

## 3. P0 模型层记录（若 §1.2 判定模型层，D4）

> **不执行**：§1.2 判定根因在代码层（cache TTL 过期致 features 缺失、guard 放行），非模型层。本次实验未出现"features 齐全但模型仍幻觉"的情况——所有 insufficient 都是 cache 过期导致的真缺失。§3 D4 衍生 change 不触发，但 §6 质量门的"反向特征校验 + 环形引用检测"作为防御层独立落地（G4 不依赖根因判定）。下方两 task 保留未勾选以记录"条件性未执行"，原因见 ROOT_CAUSE.md。

- [ ] 3.1 在 `design/deviation-analysis-2026-07-01.md` §1.3 补充实验结论：features 正常注入但模型仍输出幻觉，记录为"DeepSeek temperature=0 下对空/简输入的案例锚定幻觉"已知限制。**Verify**：文档更新，标注根因落在模型层 — **条件性未执行**（§1.2 判定代码层，根因不在模型层）
- [ ] 3.2 起草衍生 change 提案（不在本 change 实施）：评估方向 a（prompt 强约束"必须引用下方特征数据，禁止引用其他分析师"）vs 方向 b（换更强 LLM_MODEL_HEAVY）。**Verify**：衍生 change 提案文档存在，列出两个方向的取舍 — **条件性未执行**（同上，D4 不触发）

## 4. P1 cache ticker normalize（D3）

- [x] 4.1 定位 CacheManager 实现（`data/cache/manager.py` 或 fetcher 层），找到 ticker key 读写入口。**Verify**：定位到具体文件和函数 ✓ — `data/cache/manager.py`（CacheManager 类，`_path`/`get`/`set`/`is_expired`/`clear` 用裸 ticker）
- [x] 4.2 先写测试 `tests/test_cache_ticker_normalize.py`：以 `600519.SH` / `600519` / `600519.SZ` 三种格式读写同一维度，SHALL 命中同一份缓存。**Verify**：测试 fail（未 normalize）✓ — 4 测试 fail（set/get/is_expired/lowercase）
- [x] 4.3 在 CacheManager `get`/`set` 入口加 `ticker.split(".")[0]` normalize，与 `features.py:23-24` 对齐。**Verify**：测试 pass ✓ — 新增 `_normalize_ticker` 应用于 `_path`/`is_expired`/`get`/`set`/`clear`，5 normalize 测试 + 8 input_assembly 测试全 pass
- [x] 4.4a 扫描 `data/cache/` 下所有带后缀目录（`.SH`/`.SZ`），对每个检查是否含真实数据文件（basic.json/financials.json/kline.json/risk.json/valuation.json），标记为"空壳"或"有真实数据"。**Verify**：扫描结果列表记录到 `scripts/repro_out/cache_dir_audit.md`，标出孤儿目录（无纯数字对应的）✓ — `scripts/audit_cache_dirs.py` 输出：4 带后缀目录（000858.SZ/002594.SZ/600519.SH/600900.SH），2 空壳（002594.SZ/600900.SH），2 有 valuation.json 但纯数字已全（000858.SZ/600519.SH），0 孤儿含真实数据
- [x] 4.4b 按扫描结果迁移：空壳目录直接删；有真实数据的，若纯数字目录存在则人工确认后合并、若纯数字目录不存在（孤儿目录如 `002594.SZ`）则创建纯数字目录并移动数据文件后再删后缀目录。**Verify**：`ls data/cache/` 不再有 `.SH`/`.SZ` 后缀目录，且迁移前后真实数据文件总数不减少（`find data/cache -name "*.json" | wc -l` 对比）✓ — `scripts/migrate_cache_dirs.py`：115→113 json（删除 2 个被纯数字目录覆盖的孤儿 valuation.json），无带后缀目录残留；顺手修了 `tests/test_monitor.py::test_aggregate_watchlist_with_l3`（原测试漏 mock CacheManager 依赖真实缓存状态，normalize 后命中 600519/ 真实数据，已补 mock）

## 5. P1 全市场需求 A 验证（D5）

- [x] 5.1 写脚本拉取全 A 股代码列表（akshare），存 `data/all_a_share.txt`。**Verify**：文件含 ~5000 个 6 位代码 ✓ — 用户决策改用光通信模块板块（BK1136）前 50 只（"少一些，不然容易崩"），`scripts/fetch_optical_board.py` 生成 50 个 6 位代码
- [x] 5.2 跑 `batch data/all_a_share.txt`（分批 + 三级容错，复用已有 L0 采数），采全市场缓存。**Verify**：`data/cache/` 目录数接近全 A 股数量，采数成功率记录 ✓ — 50/50 完整采数（basic+financials+valuation+risk 全命中，kline 49/50），成功率近 100%
- [x] 5.3 跑 `screen --tickers data/all_a_share.txt --output data/l1_full.json`，记录 L1 漏斗比例（5000→hard_gates→factors→heat_filter 各阶段数量）和 `stats.input_scale`/`industry_pe_degraded` 触发情况。**Verify**：`data/l1_full.json` 生成，漏斗比例记录到 `scripts/repro_out/l1_full_funnel.md` ✓ — 漏斗 50→40→40→11（hard_gates 排除 H8×8+H3×3，heat_filter 砍 29）；input_scale=subset（50<300），industry_pe_degraded=True
- [x] 5.4 跑 `scout --input data/l1_full.json --output data/l2_full.json`，记录 L2 deep_dive/watch/skip 分布、confidence 直方图、LLM 调用次数、token 消耗（prompt_tokens/completion_tokens，依赖 §7 的 call_llm usage 采集）、总费用。**Verify**：`data/l2_full.json` 生成，区分度 + 成本记录到 `scripts/repro_out/l2_full_distribution.md`，验证 AD-03 成本假设（≈¥0.01/只）✓ — 11 candidates → 1 deep_dive（9% 入选，非同质化）；token usage 采集成功（prompt=443/completion=488/total=931，§7 链路验证）；实测单只 ≈¥0.0009（DeepSeek，符合 AD-03 ≈¥0.01/只量级甚至更低）。**附带修复 pre-existing fetcher bug**：`data/fetchers/basic.py:57` `r.get(col("名称"),"")` 用 name 值当 dict key 恒空 → 改为 `col("名称")`，否则所有 fresh basic.json name=None 阻住 L2 guard（用户确认修复）
- [x] 5.5 对比全市场结果与 20 只手工样本的漏斗比例/区分度差异。**Verify**：对比记录写入 `scripts/repro_out/sample_vs_full.md`，确认 L2 不是"对所有白马都输出 deep_dive"的同质化筛选 ✓ — 板块样本首次让 L1 hard_gates/heat_filter 在真实分布触发、L2 入选率非 100%，验证管线非同质化；样本仍偏小（50 vs 5000），L1 阈值校准需扩到 ≥300（§4.8 独立工作项）

## 6. 质量门校验（G4）

- [x] 6.0 重构 `council/verify_quality_gate.py` 为可导入模块：把核心校验逻辑抽成可测试函数（如 `verify_r1_feature_grounding(output, features) -> tuple[bool, list[str]]`），CLI 的 argparse+print 部分只做包装。**Verify**：`from council.verify_quality_gate import verify_r1_feature_grounding` 可导入，现有 CLI 调用方式不破坏 ✓ — 抽出 `verify_r1_feature_grounding` + `detect_circular_reference`，CLI `verify_quality_gate` 调用之
- [x] 6.1 先写测试 `tests/test_r1_feature_grounding.py`：构造 R1 AgentOutput 的 `key_metrics` 含数字 "32"，features 对应字段为 None 或值不匹配，断言反向校验返回 False（幻觉）。**Verify**：测试 fail（未实现）✓ — ImportError
- [x] 6.2 实现反向校验：提取 `key_metrics` 里的数字，检查是否在 features 任一字段值中出现；含凭空数字则标记幻觉。**Verify**：测试 pass ✓ — 9 测试全 pass；实现细节：绝对值匹配（跌幅 -17.84 vs R1 写 17.84）+ 0.5 容差（2.22 vs 2.2 四舍五入）+ 跳过单位标签数字（60日/5年/降至N倍）
- [x] 6.3 实现"R1 环形引用检测"：R1（other_opinions=None）的 `core_thesis` 出现其他 agent_id 名字（munger/duan/feng_liu/buffett 互引）时标记为幻觉引用。**Verify**：对 600519 旧 debate 文件回放，校验能识别"munger 看好"这类环形引用 ✓ — `scripts/replay_r1_grounding.py` 回放：600519 全 4 agent 环形引用 buffett→munger→duan→feng_liu→buffett 全识别
- [x] 6.4 对 P0 修复后的 600519/600900 重跑全天团辩论，验证质量门能区分真实产出（引用真实特征）vs 幻觉产出（被拦截）。**Verify**：600009 通过质量门，600519/600900 若 features 仍不足则 fail-fast 在 R1 入口、不进入质量门 ✓ — 回放验证：600519 全员被环形引用+凭空数字双拦截；600009 4 agent 中 3 通过反向校验、1 个因"有望降至15-20倍"预测值被保守标记（可接受误报，质量门偏保守）。600519/600900 因 features 不足在 R1 入口 fail-fast（§2），不进入质量门

## 7. call_llm token usage 采集（D6，方案 B）

- [x] 7.1 先写测试 `tests/test_llm_usage.py`：mock httpx 响应含 `usage: {prompt_tokens: 100, completion_tokens: 50, total_tokens: 150}`，断言 `call_llm` 返回 `(content, usage)` 且 usage 字段完整。**Verify**：测试 fail（当前 call_llm 只返回 str）✓ — ImportError: cannot import call_llm_light
- [x] 7.2 扩展 `council/llm.py::call_llm`：从 `resp.json()["usage"]` 提取 token usage，返回 `(content, usage)`，签名从 `-> str` 改为 `-> tuple[str, dict]`。**Verify**：测试 pass ✓ — 重构为共享 `_http_call`，新增 `call_llm_light`（原 scout/batch.py::call_llm_snapshot 迁入，第三档 light→LLM_MODEL），5 测试全 pass
- [x] 7.3 适配 L3 调用点：`council/debate.py` 的 `call_agent`/`_call_da`/`_call_synthesizer` 解构 `raw_json, usage = await call_llm(...)`，`AgentOutput.from_json` 只消费 raw_json 不受影响。**Verify**：`pytest tests/test_council_debate*.py` 通过 ✓ — 解构 + `usage_accumulator` 参数透传到 run_debate，写入辩论记录 md `## Token Usage` 段；mock 测试已适配 tuple 返回
- [x] 7.4 适配 L2 调用点：`scout/batch.py` 解构 `content, usage = await call_llm(...)`，累加 usage 到 batch 汇总。**Verify**：`pytest tests/test_scout*.py` 通过 ✓ — batch.py 调 `call_llm_light`（别名 call_llm_snapshot 兼容测试 patch），result 含 `usage` 字段，scout CLI 输出汇总
- [x] 7.5 移除 `verify_quality_gate.py::verify_cost` 里"token usage 未被采集"的注释，改为真实采集累加。**Verify**：verify_cost 输出含真实 token 数和费用估算 ✓ — 新增 `_parse_usage_from_debate` 解析辩论记录 md 的 Token Usage 段，输出 prompt/completion/total + 费用估算

## 8. 收尾

- [x] 8.1 更新 `design/deviation-analysis-2026-07-01.md` §4 纠偏优先级，标注 P0/P1 完成状态和根因判定结果。**Verify**：文档状态与实际一致 ✓ — §4 P0/P1 末尾各加「✅ 完成状态」段，含根因判定（代码层）+ 修复路径 + 实验数据指引
- [x] 8.2 跑 `pytest value-screener/tests/` 全套测试，确认无回归（尤其 call_llm 签名改动后 L2/L3 调用点全适配）。**Verify**：测试全 pass ✓ — 252 pass / 2 fail；2 fail 是 `test_cli_council.py` 的 `CouncilResult(rounds=...)` 与现 schema `round1` 不符（pre-existing，schema 重构后未同步的过时测试，与 f1-deviation-fix 无关，本 change 不改 L3 schema per N1）。新增测试：test_features_sufficiency(9) + test_llm_usage(5) + test_cache_ticker_normalize(5) + test_r1_feature_grounding(11) + §9 review 修复新增 7 = 32 个新测试全 pass
- [x] 8.3 准备 archive：确认 proposal/design/specs/tasks 一致，根因判定和修复路径有实验数据支撑。**Verify**：可进入 `opsx:archive` ✓ — proposal/design/specs/tasks 一致；根因判定（ROOT_CAUSE.md）+ 修复路径（§2 guard + §6 质量门）+ §5 全市场验证（l1/l2/sample 三份 md）均有实验数据支撑；§3 条件性未执行已标注原因。可进入 `opsx:archive`

## 9. 独立 Code Review 反馈修复（2026-07-02）

> 独立 review（不依赖实施汇报）发现 4 项问题，全在本 change 修复，按 P1→P2→P3→P4 顺序。

- [x] 9.1（P1，阻塞）L2 成本采集结构性缺陷：`scout_batch` 只返回 deep_dive shortlist，非 deep_dive 候选的 usage 随结果丢弃，AD-03 成本只覆盖 ~10% 调用。**修复**：`scout_batch` 返回 `(shortlist, usage_summary)`，内部累加**所有** LLM 调用（含 watch/skip/error）的 usage + cache_hits 单独计数；`cli.py` scout 命令解构 tuple 并输出全量成本；`cli --output` 写入 `{shortlist, usage_summary}` 格式；`weekly.py` 适配；`analyze_full_funnel.py` 改读 usage_summary。**Verify**：新增 2 测试（全量累加 + cache_hits）+ 适配 6 个旧测试 + test_cli_scout/weekly/screener_stats mock；252 pass。实测 11 candidates → call_count=11（修前只报 1）、total_tokens=9531、≈¥0.0095
- [x] 9.2（P2）死函数 `_normalize_number` 从未被调用（容差方案 `_found_in_features` 替代后忘删）。**修复**：删除 `verify_quality_gate.py` 的 `_normalize_number`。**Verify**：grep 无调用方，py_compile OK，测试全 pass
- [x] 9.3（P3）`_AGENT_IDS` 硬编码 `(buffett, munger, duan, feng_liu)`，张坤加入时漏检。**修复**：`detect_circular_reference` 加 `agent_ids: tuple | None = None` 参数，缺省时动态从 `council.agents.AGENT_REGISTRY.keys()` 读取（延迟 import 避免耦合，测试可 patch）。**Verify**：新增 2 测试（张坤注入检测 + 默认动态读 AGENT_REGISTRY），11 测试全 pass
- [x] 9.4（P4）`insufficient_data` 错误信息无法区分三种 guard 触发路径（critical_fields / financials_floor / missing_ratio）。**修复**：`input_assembly.py` guard return 加 `guard` + `guard_detail` 字段（短路口径，只报首个命中）；`debate.py` ValueError 消息带 `[guard]` 标识 + guard_detail。**Verify**：新增 3 测试（三种 guard 路径各自识别）+ 适配 2 个 e2e 消息测试；17 测试全 pass
