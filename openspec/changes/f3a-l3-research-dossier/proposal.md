## Why

f2 把辩论**过程**优化到头了（分流/降级/分歧报告/DA 事实回查），但实证（600009.SH）显示 L3 输入仅 **21 个纯量化扁平字段**，R1 四 agent 引用数据点**完全同源**（PE/ROE/跌幅/净利率/F-score 全来自那 21 字段），零信息不对称——f2 的 D2「强制新证据」硬约束因此在 21 字段底座上触发「编造-校验-拦截」死循环，被迫降为 soft warning（字段保留作 enabling carrier）。f1 修复**只是「不再缺」未变厚**：diff 只在 guard 段加 `financials_floor`，21 字段数前后一致。**根因是辩论信息基底不足、所有 agent 看同一份数据，不是协议问题**——再优化辩论协议也制造不出本不存在的信息不对称。

f3a 直击这个根因：把 L3 输入从 21 扁平字段升级为**结构化研究档案**（公共底座 + 角色侧重），让每个 agent 看不同维度的定性数据，R1 才有真实分歧的信息基础。这是 AD-09「辩论产生信息增量」假设从「跑得有价值」（f2）到「有真实分歧基底」的演进，也是 f2 D2 升回 hard gate 的前置条件。

## What Changes

**核心：信息不对称的来源，不是给所有人塞更多字段**。把 60+ 字段全塞全员 prompt 会回到同质化（只是 token 更贵）。真正解法是「公共底座 + 角色侧重」：21 量化字段全员共享 + 定性维度按角色分发。

1. **新建结构化研究档案层**：`council/research_dossier.py::build_research_dossier(symbol, core_snapshot=None)` 组装分层 dossier，返回 `{core_snapshot（21 量化，全员共享）, research_dossier: {main_business, peers, capex_proxy, research, degraded_fields}}`。分层 fail-fast：`core_snapshot` + `main_business` 缺失 → fail-fast（核心，无这两样不深研）；`peers`/`research`/`capex_proxy` 缺失 → 降级标注（不阻断）。`assemble_snapshot`（scout 层扁平 21 字段）**保持不变**，L2 快管线不受影响。

2. **新建 3 个数据接入 fetcher + 1 已采字段接入**（§5.1 决策 (c)，已拍板）：
   - `fetch_main_business.py`（新建，`stock_zygc_em` + `stock_zyjs_ths`）— 主营构成，分产品/行业/地区营收占比
   - `fetch_peers.py`（新建，`stock_board_industry_cons_em`，依赖 industry 字段）— 竞品对比，peer_avg_pe/行业排名
   - `fetch_research.py`（新建，`stock_research_report_em`）— 研报共识，consensus_eps/target_price/buy_rating_pct/coverage_count
   - 资本开支代理（**已采接入，零成本**）— 由 dossier 读已采的 `CONSTRUCT_LONG_ASSET`，`input_assembly` 不动

3. **角色分发落进接口签名（P1）**：当前 `_build_user_message(ticker, features, other_opinions)` 对所有 agent 生成**完全相同**的 user message——无 `agent_id` 入参，「角色分发」若只停在 prompt 层，f3a 核心假设「分发制造信息不对称」无法落地也无法验证。f3a 改：`_build_user_message` 加 `agent_id` 形参，按 agent_id 从 dossier 取角色侧重子集（`core_snapshot` 全员共享，定性维度按 §4.3 表分发：巴菲特=主营+竞品+capex、芒格=主营+竞品+pledge(代理治理)、段永平=主营+竞品+研报、冯柳=研报+capex）；`call_agent` 透传 `agent_id`；`_call_da`/`_call_synthesizer` 走**全量**路径（DA/Synthesizer 须全知，不分发）。

4. **dossier 传入路径**：`run_debate` 当前 `features = assemble_council_features(ticker)` 改为调 `build_research_dossier(ticker)`，`assemble_council_features` 退居为 dossier 内部 `core_snapshot` 的来源；`call_agent`/`_call_da`/`_call_synthesizer` 的 `features` 形参语义从「扁平 21 字段」变为「分层 dossier」。

5. **D2 保持 soft，不立刻升 hard**：f3a 只是最小闭环，peers/research 覆盖率未知（小票研报常返 0、industry 缺失致 peers 降级），贸然升 hard 会重演 f2 死循环。升 hard 门：A/B 验证定性维度覆盖率稳定（连续 N 只票 peers/research 命中率 ≥ 阈值）后，**独立 change** 升 hard（一行改动，见记忆 f2-d2-downgrade-and-f3-line）。

6. **D3 DA 事实回查扩展到定性维度（同步项）**：f2 时 D3 只能回查量化指标真假（features 仅 21 量化字段）。但代码现状是 `verify_da_fact_check` 只校验 `evidence_quality_assessment` 结构 + `recommendation` 引用合法性，**不回查具体数字**——DA 数字真假校验实际走 `verify_r1_feature_grounding`。f3a dossier 有定性维度数字（peer_avg_pe/consensus_eps/target_price），需同步把 DA 回查路径扩展到定性维度。

7. **质量门嵌套兼容（P1）**：当前 `verify_r1_feature_grounding` / `verify_r2_new_evidence` 收集 `feature_numbers` 只遍历顶层标量 + 顶层 list 标量，`dict` 值直接跳过。f3 dossier 的 `research_dossier` 是嵌套 dict，其中数字全不进 `feature_numbers` → R1/R2 引用会被误判「凭空编造」。f3a 改：`feature_numbers` 收集改为**递归遍历 dict/list**。

8. **A/B 量化判据（防自欺）**：f3a 验证门补量化指标——四 agent R1 引用数据点集合的 **Jaccard 距离**（1 - |交集|/|并集|），f2 基线应 ≈0（全同源），f3a 期望显著 >0。仅有定性判据易重蹈 f2 同质化 bug 覆辙。

**f3b（后续独立 change）补**：高管增减持（`stock_ggcg_em`）、限售解禁（`stock_restricted_release_summary_em`）、cninfo 事件公告（须复刻 uzi 直连 HTTP）。f3a 不做，避免 scope 膨胀。

## Capabilities

### New Capabilities
- `research-dossier`: L3 专用结构化研究档案层——`build_research_dossier` 组装分层 dossier（core_snapshot 全员共享 + research_dossier 角色分发），分层 fail-fast（core+main_business 缺失 fail-fast，peers/research/capex 缺失降级标注），3 新建 fetcher + 1 已采字段接入，不污染 L2 快管线（assemble_snapshot 不变）

### Modified Capabilities
- `council-debate`: agent 角色分发落进接口签名——`_build_user_message` 加 `agent_id` 形参按角色取 dossier 子集（`core_snapshot` 全员共享，定性维度按 §4.3 分发），`call_agent` 透传 `agent_id`，DA/Synthesizer 走全量路径；`run_debate` 改调 `build_research_dossier` 取代 `assemble_council_features` 作为 L3 入口
- `debate-quality-gate`: 质量门嵌套兼容——`verify_r1_feature_grounding` / `verify_r2_new_evidence` 的 `feature_numbers` 收集改递归遍历 dict/list（否则 dossier 嵌套数字被误判凭空）；新增 A/B 分化度量化判据（四 agent R1 引用数据点 Jaccard 距离，f2 基线≈0，f3a 期望显著>0）
- `da-and-synthesizer`: D3 DA 事实回查扩展到定性维度——DA 回查路径从仅量化指标扩展到 dossier 定性维度数字（peer_avg_pe/consensus_eps/target_price 等的真假比对）
- `scout-agent`: 防污染约束——`assemble_snapshot`（L2 扁平 21 字段）保持不变，capex_proxy 由 dossier 读取不进 input_assembly，L2 快管线不受 f3a 影响

## Impact

**受影响代码**：
- `value-screener/council/research_dossier.py`（**新建**）— `build_research_dossier` + 分层 fail-fast 逻辑
- `value-screener/data/fetchers/fetch_main_business.py`（**新建**）— 主营构成
- `value-screener/data/fetchers/fetch_peers.py`（**新建**）— 竞品对比
- `value-screener/data/fetchers/fetch_research.py`（**新建**）— 研报共识
- `value-screener/council/debate.py` — `_build_user_message` 加 `agent_id` 分发；`call_agent` 透传；`run_debate` 改调 `build_research_dossier`
- `value-screener/council/verify_quality_gate.py` — `verify_r1_feature_grounding` / `verify_r2_new_evidence` 的 `feature_numbers` 递归遍历；新增 Jaccard 分化度判据函数
- `value-screener/council/prompt.py` — prompt 物理分区（公司事实特征段 + 市场共识/研报段，研报引用须写明「市场预期认为……」不当事实）
- `value-screener/council/features.py` — `assemble_council_features` 退居 dossier 内 core_snapshot 来源
- `value-screener/data/lib/` — `_LazyTable` 全市场表复用（f1 已有模式，防封禁）

**依赖**：无新依赖（复用 akshare 现有接口 + 现有 `call_llm`/`asyncio.gather`/`_LazyTable`）。f3a 不引入新 LLM 框架（守 AD-05）。

**AD 引用**（不重复搬运，仅引用）：
- **AD-03**（成本闸门）：f3a 新增 3 fetcher 是数据层成本，需复算 L3 单股成本（dossier 组装无 LLM 调用，零增量 LLM 成本；fetcher 是 akshare 调用，成本可忽略）。L2 成本闸门不受影响（assemble_snapshot 不变）。
- **AD-09**（辩论增量 gate）：f3a 是「信息增量门」的信息基底升级——从 21 扁平字段到结构化档案，让「辩论增量」有真实分歧来源而非同源复读。f3a 自身的验证门是 A/B Jaccard 分化度。
- **AD-05**（不用多 agent 框架）：f3a 仍是「带上下文的串行 LLM 调用」，dossier 分发靠 prompt 设计 + 接口签名，不引入框架。

**风险**：
- **小票研报覆盖**（<50亿市值常返 0）+ **peers 依赖 industry 字段**（industry 没采到则 peers 降级）——f3a 分层 fail-fast 已设计降级路径（peers/research 缺失只降级不阻断），但若降级频繁，4 agent 角色侧重会塌缩（芒格/段永平缺竞品维度），A/B 分化度可能不显著。需 A/B 实测验证覆盖率，不显著则说明 (c) 方案的代理不足，需提前 f3b。
- **D2 升 hard 时机**：若 f3a 落地后立刻升 hard，覆盖率不稳会重演 f2 死循环。本 change 明确保持 soft，升 hard 留独立 change。
- **prompt 膨胀**：dossier 定性维度按角色分发（非全塞），但若分发不当仍可能 token 上升。靠 §4.3 角色表 + prompt 物理分区控制。
- **agent 分发签名的连锁改动**：`_build_user_message` 加 `agent_id` 影响 R1/R2 两条路径，DA/Synthesizer 走全量需区分路径，实现时边界要清晰（agent 分发 vs DA/Synthesizer 全量），不互相污染。
