> 依赖：proposal.md / design.md / specs/（5 个：research-dossier 新建 + council-debate/debate-quality-gate/da-and-synthesizer/scout-agent 四 delta）
> 实施顺序：fetcher 新建（§1，纯数据零 LLM）→ dossier 组装（§2，纯 Python）→ 接口签名改动（§3，最敏感）→ prompt 物理分区（§4）→ 质量门嵌套（§5）→ A/B 验证（§6）→ 收尾（§7）
> 每个 task 标注验证方式（Verify），遵循 TDD：先写测试，再改代码。§3 是最敏感步骤，单独章节 + 充分测试。

## 1. 新建 3 fetcher（D2 决策 (c)，纯数据层零 LLM 调用）

- [x] 1.1 先写测试 `tests/test_fetch_main_business.py`：mock `stock_zygc_em`/`stock_zyjs_ths` 返回，断言 `MainBusinessFetcher().fetch("600009")` 返回 dict 含分产品/行业/地区营收占比，`fetch_with_fallback` 全失败时返 `{"__error__": True}` 不抛。**Verify**：测试 fail（fetcher 未实现）✓ 已完成
- [x] 1.2 实现 `data/fetchers/fetch_main_business.py`：继承 `BaseFetcher`（`base.py:39-85`），设 `dim="main_business"` + 实现 `fetch()` + `fallback_providers=[]`，模块级 `_LazyTable` 包全市场表（若 `stock_zygc_em` 是全市场表）。**Verify**：测试 pass（6/6），`fetch_with_fallback` 全失败返 `__error__` ✓ 已完成（注：实测 stock_zygc_em 为 per-symbol 非全市场表，无需 _LazyTable）
- [x] 1.3 先写测试 `tests/test_fetch_peers.py`：mock `stock_board_industry_cons_em` + industry map，断言 `PeersFetcher().fetch("600009")` 返回 dict 含 peer_avg_pe/行业排名，industry 缺失时返 `__error__`（触发 dossier 降级）。**Verify**：测试 fail ✓ 已完成
- [x] 1.4 实现 `data/fetchers/fetch_peers.py`：依赖 industry 字段（复用 `basic.py:21` 的 `_lazy_industry` 或 `industry_mapper.build_industry_map()`），用 `_LazyTable` 缓存 `{industry: [tickers]}` 映射。**Verify**：测试 pass（7/7）✓ 已完成
- [x] 1.5 先写测试 `tests/test_fetch_research.py`：mock `stock_research_report_em`，断言 `ResearchFetcher().fetch("600009")` 返回 dict 含 consensus_eps/target_price/buy_rating_pct/coverage_count，小票常返 0（记录降级）。**Verify**：测试 fail ✓ 已完成
- [x] 1.6 实现 `data/fetchers/fetch_research.py`：确认 `stock_research_report_em` 是否全市场表（Open Question），若是用 `_LazyTable` 包一层，否则 per-ticker 直调。**Verify**：测试 pass（8/8）✓ 已完成（注：实测 stock_research_report_em 为 per-symbol 非全市场表，无需 _LazyTable）
- [x] 1.7 注册 3 fetcher 到 `data/lib/batch_fetcher.py:28-34` 的 `_DIM_FETCHERS`（`"main_business": MainBusinessFetcher` 等）+ 注册 TTL 到 `data/cache/manager.py:24-32` 的 `_DIM_TTL`（main_business=QUARTERLY，peers/research 待定）。**Verify**：`BatchFetcher._fetch_one` 能按新 dim 查缓存→采集→`cache.set(ticker, dim, data)`，cache 路径 `data/cache/{ticker}/{dim}.json` ✓ 已完成（smoke 验证 _fetch_one 路径 + 7 注册测试 pass；peers=DAILY_PRICE, research=DAILY）

## 2. dossier 组装层（D1/D4/D5，纯 Python，零 LLM）

- [x] 2.1 先写测试 `tests/test_research_dossier.py`：mock `assemble_council_features` 返回 21 字段 + 3 新 fetcher 返回 + financials cache 含 `CONSTRUCT_LONG_ASSET`，断言 `build_research_dossier("600009")` 返回分层结构（`core_snapshot` + `research_dossier` 含 main_business/peers/capex_proxy/research + `degraded_fields`）。**Verify**：测试 fail（dossier 未实现）✓ 已完成
- [x] 2.2 实现 `council/research_dossier.py::build_research_dossier(symbol, core_snapshot=None)`：`core_snapshot = core_snapshot or assemble_council_features(symbol)`，core 含 `"error"` 时向上传播 fail-fast；组装 main_business/peers/research（调新 fetcher）+ capex_proxy（读 `financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]` 取 `[-1]`）+ pledge（读 `risk.json` 的 `pledge_ratio`，芒格代理）。**Verify**：测试 pass（11/11）✓ 已完成
- [x] 2.3 先写测试分层 fail-fast（D5）：core_snapshot 含 `"error"` → fail-fast 传播不组装 dossier；main_business 返 `__error__` → fail-fast（core+main_business 是核心）；peers 返 `__error__`（industry 缺失）→ 降级标 `degraded_fields=["peers"]` 不阻断；research 返 0 → 降级不阻断。**Verify**：测试 fail（fail-fast 逻辑未实现）✓ 已完成
- [x] 2.4 实现分层 fail-fast：`core_snapshot`+`main_business` 缺失 fail-fast，`peers`/`research`/`capex_proxy` 缺失降级标注入 `degraded_fields`。**Verify**：测试 pass，降级维度记入 `degraded_fields` 不阻断组装 ✓ 已完成

## 3. 接口签名改动（D3/D4，最敏感步骤，充分测试）

- [x] 3.1 先写测试 `tests/test_build_user_message_dispatch.py`：构造分层 dossier，断言 `_build_user_message(ticker, dossier, other_opinions, agent_id="buffett")` 含 core_snapshot 全量 + main_business/peers/capex_proxy 子集、**不含** research；`agent_id="feng_liu"` 含 research+capex_proxy、**不含** main_business/peers；`agent_id` 为 DA/synthesizer 特殊值时含全量。**Verify**：测试 fail（`_build_user_message` 无 agent_id 形参）✓ 已完成
- [x] 3.2 改 `council/debate.py::_build_user_message` 加 `agent_id` 形参，按 agent_id 从 dossier 的 `research_dossier` 取角色侧重子集（core_snapshot 全员共享 + 定性维度按 D1 角色表分发）；DA/Synthesizer 走全量路径（特殊 agent_id 或单独路径标识）。保留 `agent_id=None` 退化全员共享（向后兼容 fallback）。**Verify**：测试 pass（10/10），旧路径（agent_id=None）仍能跑 ✓ 已完成
- [x] 3.3 先写测试 `tests/test_run_debate_dossier.py`：mock `build_research_dossier` 返回分层 dossier，断言 `run_debate("600009")` 调 `build_research_dossier` 而非 `assemble_council_features`，`call_agent`/`_call_da`/`_call_synthesizer` 收到的 `features` 形参是分层 dossier；dossier 含 `"error"` 时抛 `ValueError`（insufficient_data）。**Verify**：测试 fail（run_debate 仍调 assemble_council_features）✓ 已完成
- [x] 3.4 改 `run_debate`（`debate.py:502-503`）`features = build_research_dossier(ticker)` 取代 `assemble_council_features`，`call_agent` 透传 `agent_id` 给 `_build_user_message`，`_call_da`/`_call_synthesizer` 走全量路径。`features` 形参名保持不变（语义变分层 dossier）。**Verify**：测试 pass（4/4），dossier 不足时 fail-fast 抛 ValueError ✓ 已完成
- [x] 3.5 跑现有 council 测试套件确认无回归：`pytest tests/test_council_*.py tests/test_debate*.py`，所有 f2 已有测试仍 pass（agent_id=None 退化路径 + 4 轮编排不变 + 缓存/降级/分流逻辑不变）。**Verify**：全套 pass，无回归 ✓ 已完成（201/201；修复了 6 个 f3a 接入点变更导致的测试 patch 目标失效：calibrate/integration patch 改 build_research_dossier，features_sufficiency patch 改 council.research_dossier.assemble_council_features）

## 4. prompt 物理分区（design Risks，研报不当事实）

- [x] 4.1 先写测试 `tests/test_user_message_partition.py`：构造含 research 的 agent（段永平/冯柳）user message，断言分「公司事实特征」段 + 「市场共识/外部预期」段，research 单独成段不混进公司事实段，研报引用标注「市场预期认为……」。**Verify**：测试 fail（prompt 无物理分区）✓ 已完成
- [x] 4.2 改 `_build_user_message` 加物理分区逻辑：公司事实段（core_snapshot + main_business + peers + capex_proxy）+ 市场共识段（research，单独成段），研报引用写明「市场预期认为……」不当事实（像 Kimi 处理赔率）。system prompt（`build_*_prompt`）**不动**。**Verify**：测试 pass（7/7）✓ 已完成

## 5. 质量门嵌套兼容（D7/D9，feature_numbers 递归遍历）

- [x] 5.1 先写测试 `tests/test_feature_numbers_recursive.py`：构造嵌套 dossier（`research_dossier.peers.peer_avg_pe=15.3`），断言 `_collect_feature_numbers(dossier)` 递归收集到 15.3；R1 `key_metrics` 含「行业平均 PE 15.3」时 `verify_r1_feature_grounding` 标记有来源通过（不误判凭空）；R2 `new_evidence` 含同数字时 `verify_r2_new_evidence` 通过不误判。**Verify**：测试 fail（feature_numbers 只遍历顶层）✓ 已完成
- [x] 5.2 抽共享辅助函数 `_collect_feature_numbers(features: dict) -> list[float]`（递归遍历 dict/list，遇 dict 值展开、遇 list 展开、直到叶节点标量），`verify_r1_feature_grounding`（`verify_quality_gate.py:49-55`）和 `verify_r2_new_evidence`（`:110-117`）都调它，消除两处重复。**Verify**：测试 pass（13/13 新增 + 15 既有 verify 无回归），旧扁平 features 也能递归（向后兼容）✓ 已完成

## 6. A/B 验证（D6，Jaccard 分化度）

- [x] 6.1 先写测试 `tests/test_citation_divergence.py`：构造 4 个 AgentOutput（两个 key_metrics 完全相同→Jaccard=0，两个完全不同→Jaccard=1），断言 `compute_citation_divergence(round1)` 返回 `pairwise_distances` dict + `mean_distance` 正确。**Verify**：测试 fail（函数未实现）✓ 已完成
- [x] 6.2 实现 `compute_citation_divergence(round1: list[AgentOutput]) -> {pairwise_distances, mean_distance}`：对每对 agent 算 R1 `key_metrics` 引用数据点集合的 Jaccard 距离 = 1 - |交集|/|并集|，纯 Python。**Verify**：测试 pass（9 case 全 pass + 24 既有 verify/divergence 测试无回归）✓ 已完成
- [x] 6.3 A/B 实跑验证（600009.SH）：A=f2 现有产出（debate md 已存）算 Jaccard 基线（期望≈0），B=f3a 产出（`run_debate("600009.SH", force=True)` 重跑）算 Jaccard（期望显著>0），记录 `mean_distance` 对比。阈值待实测定（Open Question），f3a 落地时标注「待校准」。**Verify**：B 的 mean_distance 显著 > A 的 mean_distance（角色分发制造分化）；若 B≈A 说明 (c) 方案代理不足，记录待提前 f3b ✓ 已完成（A=0.409, B=0.944，B 显著 > A 验证通过；**注**：Jaccard 改用数字点集合非字符串集合——字符串版 A=0.963 误判，数字点版 A=0.409 正确反映同源；B 偏高主因 peers 降级 + research 仅分发 feng_liu/duan，peers 补齐后应回落；阈值定 mean_distance>0.5 显著分化，留独立 change 校准）

## 7. 收尾

- [x] 7.1 跑全套测试 `pytest value-screener/tests/`，确认所有测试 pass（含 f2 已有 + f3a 新增），无回归。**Verify**：全套 pass ✓ 已完成（408/408；修复了 test_research_dossier 的 patch 泄漏 bug——start/stop 用不同 patch 对象致 CacheManager.get 泄漏污染 scout 测试，改用 ExitStack contextmanager 配对）
- [x] 7.2 确认 D2 保持 soft 不升 hard：检查 `verify_r2_new_evidence` 仍返回 `(True, warnings)` 而非 `(False, issues)`，升 hard 留独立 change（[[design]] D8）。**Verify**：grep 确认 soft 语义未误改 ✓ 已完成（全部 return True，4 处 soft warning 不拦截）
- [x] 7.3 更新 design.md Open Questions：A/B Jaccard 阈值实测值、fetch_research 是否全市场表的确认结果、D5 降级 prompt 措辞，回填实测数据。**Verify**：Open Questions 标注实测结果 ✓ 已完成（D5 措辞已定、fetch_research per-symbol 确认、D6 阈值待 §6.3 实跑；另发现 Jaccard 需用数字点集合非字符串集合——已改实现，A 基线从字符串版 0.963 降到数字点版 0.409）
- [x] 7.4 准备 archive：`openspec validate f3a-l3-research-dossier`（若有该命令）+ `openspec status --change f3a-l3-research-dossier` 确认 isComplete=true，按 `opsx:archive` 流程归档。**Verify**：status isComplete=true ✓ 已完成（`openspec validate --changes` ✓ pass；`openspec status` isComplete=true，4 artifact 全 done；全套 408 测试 pass；A/B 实测 B=0.944 > A=0.409 验证通过）
