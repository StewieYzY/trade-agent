## Context

f2-debate-protocol-fix 把 L3 辩论**过程**优化到头（分歧度分流/降级/分歧报告/DA 事实回查），但实证（600009.SH）显示 L3 输入仅 **21 个纯量化扁平字段**（`scout/input_assembly.py::assemble_snapshot`，21 字段清单见 `input_assembly.py:324-346`），R1 四 agent 引用数据点**完全同源**（PE/ROE/跌幅/净利率/F-score 全来自那 21 字段），零信息不对称。f2 的 D2「强制新证据」硬约束因此在 21 字段底座上触发「编造-校验-拦截」死循环，被迫降为 soft warning，`new_evidence`/`evidence_exhausted` 字段保留作 enabling carrier。f1-deviation-fix 修复**只是「不再缺」未变厚**（diff 只在 guard 段加 `financials_floor`，21 字段数前后一致）。

**根因**：天团看到同一份数据，辩论没有信息不对称的来源。再优化辩论协议也制造不出本不存在的信息不对称。f3a 直击这个根因——把 L3 输入升级为**结构化研究档案**，让每个 agent 看不同维度的定性数据。

**约束继承**：
- **AD-03**（成本闸门）：f3a 新增 3 fetcher 是 akshare 数据层调用（零 LLM 成本），dossier 组装无 LLM 调用；L2 成本闸门不受影响（`assemble_snapshot` 不变）。L3 单股 LLM 成本不变（10 次调用结构不变，只是 user message 内容更丰富）。
- **AD-05**（不用多 agent 框架）：f3a 仍是「带上下文的串行 LLM 调用」，dossier 分发靠 prompt 设计 + 接口签名，不引入框架。
- **AD-09**（辩论增量 gate）：f3a 是「信息增量门」的信息基底升级——让「辩论增量」有真实分歧来源而非同源复读。f3a 自身的验证门是 A/B Jaccard 分化度（D6）。
- **AD-07**（格雷厄姆在 L1 不在天团）：f3a 不动 L1，天团仍是 4 agent。

**当前代码现状**（已核实接入点）：
- fetcher 基类 `BaseFetcher`（`data/fetchers/base.py:39-85`）：子类设 `dim` + 实现 `fetch()` + `fallback_providers`；`fetch_with_fallback` 容错链全失败返 `{"__error__": True}` 不抛
- 全市场表复用 `_LazyTable`（`data/lib/snapshot.py:22-57`）：模块级实例化 + `.get()`，intra-batch 只取一次防封禁，300s 失败冷却
- fetcher 注册点 `batch_fetcher.py:28-34` `_DIM_FETCHERS` dict + `cache/manager.py:24-32` `_DIM_TTL`；cache 路径 `data/cache/{ticker}/{dim}.json`
- `CONSTRUCT_LONG_ASSET` 已采于 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]`（list，近3年），L1 `screener/factor_scores.py:216-228` 已读，L2 `input_assembly.py` 未读
- `assemble_council_features(ticker)`（`council/features.py:10`）= `assemble_snapshot` 包装，返 21 字段或 `{"error": "insufficient_data", ...}`
- `AGENT_REGISTRY`（`council/agents.py:20-39`）key = `buffett/munger/duan/feng_liu`，value = `{"name", "prompt_builder"}`；DA/Synthesizer 不注册，`debate.py` 内独立调
- prompt 是**按 agent_id 分无参函数**（`build_buffett_prompt()` 等，`council/prompt.py`），system prompt 是静态字符串，特征数据走 user message `_build_user_message(ticker, features, other_opinions)`（`debate.py:69-116`），`features` 整个 `json.dumps` 进 user message（全员共享同一份）
- 质量门 `verify_r1_feature_grounding`（`verify_quality_gate.py:31`）/ `verify_r2_new_evidence`（`:87`）收集 `feature_numbers` 只遍历顶层标量 + 顶层 list 标量，`dict` 值跳过

## Goals / Non-Goals

**Goals:**
- L3 输入从 21 扁平字段升级为结构化研究档案（公共底座 + 角色侧重），制造 R1 信息不对称
- 4 agent 各看不同定性维度，R1 有真实分歧的信息基础（验证：A/B Jaccard 分化度显著 >0）
- 不污染 L2 快管线（`assemble_snapshot` 不变，capex 由 dossier 读不进 input_assembly）
- f2 的 D2 enabling carrier（`new_evidence`/`evidence_exhausted`）有真实定性维度可引，为后续升 hard 铺路
- D3 DA 事实回查从仅量化扩展到定性维度

**Non-Goals:**
- **不升 D2 hard gate**：f3a 保持 soft，升 hard 留独立 change（D2 决策）
- **不做治理/解禁/事件 fetcher**：高管增减持、限售解禁、cninfo 事件公告属 f3b（scope 控制）
- **不改 AgentOutput/SynthesizerOutput schema**：f3a 是输入层升级，不动输出 schema（守 f1 N1）
- **不做张坤 agent**：留待后续
- **不重跑全市场**：f3a 验证用 600009.SH A/B 对比，全市场实跑是 P1 既有差距，不在 f3a scope

## Decisions

### D1：公共底座 + 角色侧重——不是给所有人塞更多字段

**问题**：f3a 要解决 R1 同质化。直觉解法是「把所有定性字段全塞给所有 agent」——但这会让 agent「看到同样的东西只是更多了」，同质化不解决，且 prompt 膨胀 + token 上升。完全割裂（每 agent 只看自己维度）又太激进，R2 互相质疑时缺少共同事实地基。

**决策**：用「公共底座 + 角色侧重」：
- **公共底座**：`core_snapshot`（21 量化字段）全员共享——保证 R2 互相质疑有共同事实地基
- **角色侧重**：定性维度按 agent_id 分发，每 agent 看不同维度子集：

| agent | 角色侧重维度 | 核心看 |
|---|---|---|
| 巴菲特 | main_business + peers + capex_proxy | 生意质量、护城河、长期再投资 |
| 芒格 | main_business + peers + pledge（代理治理） | 商业模式脆弱点、管理层、反身性风险 |
| 段永平 | main_business + peers + research | 用户价值、商业模式简单可靠、市场共识是否误判 |
| 冯柳 | research + capex_proxy | 预期差、赔率、反对意见、边际变化 |
| DA / Synthesizer | 全量 | 仲裁要全知 |

芒格的「治理」、冯柳的「解禁/事件」在 f3a 用已有数据做代理（见 D2），f3b 再补真实 fetcher。

**为何不全塞全员**：回到同质化，只是 token 更贵（探索稿 §六第 2 条避坑）。
**为何不完全割裂**：R2 互相质疑缺共同事实地基，且单 agent 维度太窄判断不可靠。
**备选**：纯按 agent 分发无公共底座——否决，因 R2 交叉质疑需要共同事实参照。

### D2：f3a scope 边界——用已有数据做角色侧重代理（决策 (c)）

**问题**：芒格（治理/风险）和冯柳（解禁/事件压力）的角色侧重维度本应是 `fetch_governance.py` + `fetch_events.py`，但那是 f3b 范畴。f3a 阶段这两个 agent 会暂时缺核心侧重维度。三种选择：(a) 只让巴菲特/段永平完整、芒格/冯柳半成品；(b) f3a 做 4 agent 全完整（含 governance+events fetcher）；(c) 用已有数据做代理。

**决策**：选 **(c)**——用已有数据做角色侧重代理：
- 芒格的治理视角，f3a 用 `risk.py` **已采的 `pledge_ratio`**（质押率，`data/cache/{ticker}/risk.json`）做代理，不新建 `fetch_governance.py`
- 冯柳的解禁/事件视角，f3a 用**已有 capex_proxy + 研报**做代理，不新建 `fetch_events.py`
- 4 agent 都有角色侧重、A/B 验证有 4 视角分化
- **新建 3 fetcher**（main_business + peers + research），capex 读已采字段、pledge 读已采字段

**为何不选 (a)**：巴菲特/段永平侧重高度重叠（都看 main_business+peers），分化可能不显著，验证效果弱。
**为何不选 (b)**：回到「一次做 6 类 fetcher」的坑，scope 膨胀，调试从「验证深度」变成「到处修接口」（探索稿 §六第 1 条避坑）。
**备选**：(a)——否决，因验证效果弱；(b)——否决，因 scope 膨胀。

### D3：角色分发改 user message 层，不改 prompt 层

**问题**：当前 `_build_user_message(ticker, features, other_opinions)`（`debate.py:69-116`）对所有 agent 生成**完全相同**的 user message（同一份 features JSON），无 `agent_id` 入参。「角色分发」若只停在 prompt 层，f3a 核心假设「分发制造信息不对称」无法落地也无法验证。但 system prompt 是**按 agent_id 分无参函数**（`build_buffett_prompt()` 等），调用处 `builder()`（`debate.py:55`）也无参——改 prompt 层改动面大。

**决策**：角色分发改 **user message 层**（选项 A）：
- `_build_user_message` 增加 `agent_id` 形参，按 agent_id 从 dossier 的 `research_dossier` 取角色侧重子集
- `core_snapshot`（21 量化）全员共享，定性维度按 D1 角色表分发
- `call_agent`（`debate.py:27`）透传 `agent_id` 给 `_build_user_message`
- `_call_da` / `_call_synthesizer` 走**全量**路径（DA/Synthesizer 须全知，不分发），与 agent 分发路径区分
- system prompt（`build_*_prompt`）**不动**——角色哲学已在静态 prompt 里，分发的是数据不是哲学

**为何不改 prompt 层**：现有 `build_*_prompt()` 无参、调用处 `builder()` 无参，改要动 4 个函数签名 + registry 的 `prompt_builder` 字符串约定 + 调用处，改动面大且 prompt 层本就承载角色哲学（不需重复）。
**备选**：给 `build_*_prompt` 加参数注入角色侧重指引——否决，因改动面大且与现有无参设计冲突。

### D4：dossier 传入路径——run_debate 改调 build_research_dossier

**问题**：`run_debate`（`debate.py:478`）当前 `features = assemble_council_features(ticker)`（`:502-503`），`call_agent`/`_call_da`/`_call_synthesizer` 的 `features` 形参语义是「扁平 21 字段」。f3a 要接入 dossier，需明确传入路径，否则又是「设计口号」。

**决策**：
- `run_debate` 改调 `build_research_dossier(ticker)` 取代 `assemble_council_features` 作为 L3 入口
- `assemble_council_features` 退居为 dossier 内部 `core_snapshot` 的来源（`build_research_dossier` 内部 `core_snapshot = core_snapshot or assemble_council_features(symbol)`）
- `call_agent`/`_call_da`/`_call_synthesizer` 的 `features` 形参语义从「扁平 21 字段」变为「分层 dossier」——但**形参名保持 `features` 不变**（避免 cascade 改名），只是传入对象结构变了
- capex_proxy 由 dossier 读取 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]`，`input_assembly` 完全不动

**为何不改 input_assembly**：`assemble_snapshot` 是 L1→L2 交接点（`council/features.py:7` 和 `debate.py:22` 都 import），改它污染 L2 快管线（探索稿 §4.2 已明确）。
**备选**：在 input_assembly 加 capex 读取——否决，因污染 L2。

### D5：分层 fail-fast——core+main_business 缺失 fail-fast，其余降级

**问题**：dossier 的定性维度（peers/research/capex）覆盖率未知（小票研报常返 0、industry 缺失致 peers 降级）。全缺失时是 fail-fast 还是降级？

**决策**：分层 fail-fast（用户决策，门槛压窄）：
- `core_snapshot` + `main_business` 缺失 → **fail-fast**（核心，无这两样不深研，与 f1 `insufficient_data` 同模式）
- `peers` / `research` / `capex_proxy` 缺失 → **降级标注**（不阻断），记入 `research_dossier.degraded_fields`
- 降级时该维度对应 agent 的角色分发（D2 决策 (ii)）：标 degraded 但仍跑，prompt 注明「你的 X 维度缺失，基于 core 判断」（与 f2 L2 降级同哲学：标 degraded 继续，诚实标注）

**为何不全 fail-fast**：peers/research 覆盖率不稳，全 fail-fast 会让很多票跑不了 L3。
**为何不静默退化**：静默退化失角色（等于 f2 状态），不诚实（探索稿 §5.2 决策 (ii)）。
**备选**：缺失维度对应 agent 跳过（决策 (iii)）——否决，因破坏 4 agent 结构。

### D6：A/B 验证量化判据——Jaccard 分化度

**问题**：f3a 验证门若只有定性判据「R1 引用数据分布是否分化」，易自欺（看起来分化实则同源，重蹈 f2 同质化 bug 覆辙）。需量化指标。

**决策**：A/B 验证补量化判据——四 agent R1 引用数据点集合的 **Jaccard 距离**：
- 对每对 agent (i,j)，算引用数据点集合的 Jaccard 距离 = 1 - |交集| / |并集|
- f2 基线（600009.SH 现有产出）：四 agent 引用同源为主，Jaccard 距离偏低
- f3a 期望：Jaccard 距离显著 > f2 基线（角色分发让 agent 看不同维度，引用数据点分化）
- 实现为纯 Python 函数 `compute_citation_divergence(round1) -> {pairwise_distances, mean_distance}`，复用 `AgentOutput.key_metrics` 提取数据点

> **f3a 实测修订（2026-07-13，§6.3）**：Jaccard 用**数字点集合**而非字符串集合。实测发现字符串版有缺陷——f2 四 agent 都引 PE 25.71 但措辞不同（"PE(TTM) 25.71" vs "PE TTM 25.71"），按字符串算 Jaccard≈0.963（误判完全分化），按数字点算 ≈0.409（正确反映同源为主但侧重略不同）。改用 `_extract_metric_numbers`（复用 verify_r1 的数字提取规则，跳过时间窗/单位标签）算数字点集合 Jaccard。
>
> **A/B 实测数据（600009.SH，deepseek-v4-pro）**：
> - **A（f2 基线，2026-07-10 真实 LLM 产出）**：mean_distance = **0.409**（四 agent 引用 PE/PB/ROE/净利率/现金流/F-score 同源为主，但各有独有数字如 buffett 的跌幅 15.86、munger 的营收增长 7.9%）
> - **B（f3a 角色分发，2026-07-13 重跑）**：mean_distance = **0.944**（显著 > A，验证通过）。分化来源：feng_liu 引用 research 维度的「一致预期 EPS 1.173 / 目标价 27.39」（其他 agent 看不到）、duan 用定性判断数字「15% 合格线」、buffett/munger 仍引核心财务数据。**注**：B 偏高（0.944 而非中等 0.5-0.7）主因 peers 降级（600009 industry 未采，peers 维度对 buffett/munger/duan 缺失）+ research 只分发 feng_liu/duan，导致 core 之外共享维度少。peers 补齐后分化应回落到中等区间。
> - **结论**：B 显著 > A，f3a 角色分发制造信息不对称的假设验证成立。阈值定 **mean_distance > 0.5** 为「显著分化」（A=0.409 < 0.5 同源为主，B=0.944 > 0.5 显著分化），留独立 change 用更多样本校准。

**为何用 Jaccard 而非其他**：引用数据点是集合语义（引没引某数据点），Jaccard 是集合分化度的标准度量。**注**：用数字点集合（非字符串集合）——数字点反映「数据点同源」语义，字符串集合会因措辞不同误判。
**备选**：不同源数据点占比——否决，因「不同源」定义模糊（需先定义同源），Jaccard 更严谨。

### D7：质量门嵌套兼容——feature_numbers 递归遍历

**问题**：`verify_r1_feature_grounding`（`verify_quality_gate.py:31`）/ `verify_r2_new_evidence`（`:87`）收集 `feature_numbers` 只遍历顶层标量 + 顶层 list 标量（`:49-55`、`:110-117`），`dict` 值直接跳过。f3 dossier 的 `research_dossier` 是嵌套 dict，其中 `peer_avg_pe`/`consensus_eps`/`target_price` 等数字全不进 `feature_numbers` → R1/R2 引用这些数字会被反向校验误判「凭空编造」。当前即时危害是污染人工检查输出（WARNING 不阻断），但 R1 接地未来升 hard 时变致命。

**决策**：`feature_numbers` 收集改为**递归遍历 dict/list**——遇到 dict 值也展开，遇到 list 也展开，直到叶节点标量。抽成共享辅助函数 `_collect_feature_numbers(features) -> list[float]`，`verify_r1_feature_grounding` 和 `verify_r2_new_evidence` 都调它，消除两处重复。

**为何递归**：dossier 是任意深度嵌套（main_business 里可能还有分产品/分地区子 dict），递归是唯一稳妥遍历方式。
**备选**：按已知 dossier 结构硬编码路径取数——否决，因结构变化时硬编码失效，递归更稳健。

### D8：D2 保持 soft，升 hard 留独立 change

**问题**：f3a 补了定性维度，R2 真有新证据可引，f2 留的 `new_evidence`/`evidence_exhausted` enabling carrier 是否立刻激活升 hard？

**决策**：f3a 落地后 **D2 保持 soft**（不立刻升 hard）。升 hard 的门：A/B 验证定性维度覆盖率稳定（连续 N 只票 peers/research 命中率 ≥ 阈值，N 和阈值待 MVP 实测定）后，**独立 change** 升 hard（一行改动：`verify_r2_new_evidence` 返回 `(False, issues)` 而非 `(True, warnings)`，见记忆 f2-d2-downgrade-and-f3-line）。

**为何不立刻升 hard**：f3a 只是最小闭环，覆盖率未知（小票研报常返 0、industry 缺失致 peers 降级），贸然升 hard 会重演 f2 的「编造-校验-拦截」死循环——R2 凑低信息字段或编造来满足 hard 约束。
**备选**：f3a 立刻升 hard——否决，因覆盖率未验证会重演 f2 死循环。

### D9：D3 DA 事实回查扩展到定性维度

**问题**：f2 时 D3 只能回查量化指标真假（features 仅 21 量化字段）。f3a dossier 有定性维度数字（peer_avg_pe/consensus_eps/target_price），但代码现状是 `verify_da_fact_check`（`:170`）只校验 `evidence_quality_assessment` 结构 + `recommendation` 引用合法性，**不回查具体数字**——DA 数字真假校验实际走 `verify_r1_feature_grounding`。f3a 要把 DA 回查真正扩展到定性维度。

**决策**：D3 DA 回查扩展为 f3a 同步项——`verify_r1_feature_grounding` 的 `feature_numbers` 递归遍历（D7）已覆盖 dossier 嵌套数字，DA 回查定性维度数字自动受益（DA 引用 peer_avg_pe 等会被递归收集的 feature_numbers 匹配）。无需单独改 `verify_da_fact_check`——它职责是结构校验，数字回查统一走 `verify_r1_feature_grounding`。

**为何不改 verify_da_fact_check**：职责分离——`verify_da_fact_check` 校验 DA 输出结构合法性，`verify_r1_feature_grounding` 校验数字接地，两者职责不同，D7 的递归遍历已让数字接地覆盖定性维度。
**备选**：在 `verify_da_fact_check` 内加数字回查——否决，因职责重复且与现有分工冲突。

## Risks / Trade-offs

- **[小票研报覆盖 + peers 依赖 industry]** → peers/research 缺失频繁时 4 agent 角色侧重塌缩（芒格/段永平缺竞品维度），A/B Jaccard 分化度可能不显著 → 缓解：D5 分层 fail-fast 已设计降级路径；A/B 实测若分化不显著，说明 (c) 方案代理不足，需提前 f3b
- **[D2 升 hard 时机]** → 若实现时顺手升 hard，覆盖率不稳前会重演 f2 死循环 → 缓解：D8 明确保持 soft，升 hard 留独立 change，tasks.md 标注「不升 hard」
- **[prompt 膨胀]** → dossier 定性维度按角色分发（非全塞），但若分发不当仍 token 上升 → 缓解：D1 角色表控制每 agent 维度数 + prompt 物理分区（公司事实段 + 市场共识段）
- **[agent 分发签名连锁改动]** → `_build_user_message` 加 `agent_id` 影响 R1/R2 两条路径，DA/Synthesizer 走全量需区分 → 缓解：D3 明确两条路径（agent 分发 vs DA/Synthesizer 全量），tasks.md 分步实现 + 测试覆盖
- **[研报当事实]** → 研报共识（consensus_eps/target_price）是市场预期不是公司事实，混进事实段会误导 → 缓解：prompt 物理分区，研报单独成段，引用须写明「市场预期认为……」（像 Kimi 处理赔率：研究变量不是预测依据）
- **[akshare 接口不稳]** → `stock_research_report_em`/`stock_board_industry_cons_em` 可能限流或返空 → 缓解：`_LazyTable` 300s 失败冷却 + `fetch_with_fallback` 容错链 + D5 降级标注

## Migration Plan

**部署顺序**（tasks.md 实施顺序）：
1. 新建 3 fetcher（纯数据层，零 LLM 调用，可独立测试）→ 注册到 `_DIM_FETCHERS` + `_DIM_TTL`
2. 新建 `research_dossier.py::build_research_dossier`（纯 Python 组装，复用 fetcher + 已采字段）
3. 接口签名改动（`_build_user_message` 加 `agent_id` + `run_debate` 改调 dossier）—— 最敏感步骤，单独章节 + 充分测试
4. prompt 物理分区（公司事实段 + 市场共识段）
5. 质量门嵌套兼容（`feature_numbers` 递归遍历，D7）
6. A/B 验证（600009.SH f2 产出 vs f3a 产出，Jaccard 分化度）

**回滚策略**：
- fetcher/dossier 是新增文件，回滚直接删除 + 移除 `_DIM_FETCHERS`/`_DIM_TTL` 注册
- `_build_user_message` 签名改动是关键回滚点——保留旧路径（`agent_id=None` 时退化为全员共享 features）作 fallback，验证通过后再清理
- 质量门递归遍历是向后兼容改进（旧扁平 features 也能递归），无需回滚

**缓存兼容**：新 dim（main_business/peers/research）的 cache 是新增目录，不影响现有 `data/cache/{ticker}/{basic,valuation,financials,kline,risk}.json`。

## Open Questions

> **f3a 实现期回填（2026-07-13）**：以下 4 项中 3 项已实测确认，1 项（D6 阈值）待 A/B 实跑。

- **D6 Jaccard 阈值**：✅ **已实测定（§6.3，2026-07-13）**。Jaccard 用**数字点集合**（非字符串集合——字符串版会因措辞不同误判）。A/B 实测（600009.SH，deepseek-v4-pro）：**A（f2 基线）=0.409，B（f3a）=0.944**。阈值定 **mean_distance > 0.5 为「显著分化」**（A<0.5 同源为主，B>0.5 显著分化）。留独立 change 用更多样本（peers 补齐后的中等分化区间）校准。
- **D8 升 hard 的 N 和覆盖率阈值**：连续 N 只票 peers/research 命中率 ≥ 阈值，N 和阈值待 MVP 实测定（独立 change 升 hard 时再定，f3a 已确认 `verify_r2_new_evidence` 保持 soft 全返 `True`，§7.2 grep 确认）。
- **D5 降级时的 prompt 措辞**：✅ **已定**。实现为 `_degraded_note(dim)` 函数（`debate.py`），措辞：「你的{维度中文名}维度缺失，请基于核心特征（core_snapshot）判断，勿臆测该维度数据。」维度中文名映射：main_business→主营构成、peers→竞品对比、capex_proxy→资本开支、research→研报共识。诚实标注不静默退化，与 f2 L2 降级同哲学。
- **fetch_research 是否全市场表**：✅ **已确认**。实测 `inspect.signature(ak.stock_research_report_em)` → `(symbol: str)`，**per-symbol**（非全市场表），**无需 `_LazyTable`**。`ResearchFetcher.fetch` 直接 `ak.stock_research_report_em(symbol=code)` per-ticker 调用。另注：`fetch_main_business` 的 `stock_zygc_em`/`stock_zyjs_ths` 也都是 per-symbol（前者需 `SH/SZ` 前缀格式 `SH600009`，由 `market_router.parse_ticker` 派生），均无需 `_LazyTable`。**仅 `fetch_peers` 的 `stock_board_industry_cons_em` 是 per-industry**，用模块级 `_lazy_industry_cons: dict[str, _LazyTable]` 按 industry 缓存成分股表 intra-batch 复用。
