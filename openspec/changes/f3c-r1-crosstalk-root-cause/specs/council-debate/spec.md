## MODIFIED Requirements

### Requirement: 辩论编排 4 轮串行
debate.py SHALL 实现 4 轮串行辩论编排：

- **Round 1（各自表态）**：所有 agent 并行调用 LLM，彼此隔离（不传他人论点），使用重度推理模型；user message SHALL 按 agent_id 从 dossier 取角色侧重子集（`core_snapshot` 全员共享 + 定性维度按角色分发，见下方「角色分发按 agent_id 构造 user message」requirement）
- **R1 质量门断路器（f3c）**：R1 所有 agent gather 完成后、R2 之前，`run_debate` SHALL 调用 `detect_circular_reference`（每 agent）+ `verify_r1_feature_grounding`（每 agent）。**显性环形引用命中 → hard fail 阻断**（不进 R2/R3/R4，不产出"成功"JSON 落盘，省 LLM 成本 AD-03）；凭空数字/隐性串台 → soft warning 记入产出不阻断。详见 `debate-quality-gate` 的「R1 输出引用真实特征校验（反向校验）」requirement。
- **分歧度分流**：R1 完成后（且未被 hard fail 阻断）计算分歧度，按 level 决定是否跳过 R2/R3
- **Round 2（交叉质疑）**：所有 agent 并行调用 LLM，每个 agent 可见其他 agent 的 R1 AgentOutput JSON，使用重度推理模型；单 agent 场景下跳过 LLM 调用；R2 prompt SHALL **encourage** 引用 R1 未充分覆盖的数据维度，如无则 **may** 声明 `evidence_exhausted`（**soft signal，非硬约束**，f3a 保持 soft 不升 hard，见 [[design]] D8）；user message SHALL 按 agent_id 角色分发（同 R1）
- **Round 3（DA 仲裁）**：Devil's Advocate 单独调用，可见 R1+R2 全部讨论 + 原始 dossier（做事实回查，含定性维度数字），使用重度推理模型；DA SHALL 走全量路径（不分发，见下方「角色分发按 agent_id 构造 user message」requirement）；**DA skipped 条件**：① 分流 `level == "low"` 或 `"extreme"` 跳 R2/R3；② R2 中 ≥3 agent 标 `evidence_exhausted` 跳 R3；③ 运行时降级（error rate ≥0.4）跳 R3。被跳时 `CouncilResult.round3 == None` + `CouncilResult.da_skipped_reason` 取四值之一。注：`da_skipped_reason` 存 `CouncilResult`（编排器内部状态，非 L3 输出 schema，不违反 f1 N1）
- **Round 4（收敛共识）**：Synthesizer 单独调用，可见 R1（+R2 if ran）+（DA 仲裁报告 if ran，否则 `da_skipped_reason`）+ 原始 dossier，使用中度推理模型，产出含分歧报告的 SynthesizerOutput；Synthesizer SHALL 走全量路径（不分发）

信息可见性 SHALL 由编排器控制（R1 彼此隔离但按角色分发 dossier 子集 / R2 可见他人 + 按角色分发 / R3 全知含 dossier / R4 全知含 dossier + DA 仲裁报告 if ran，否则含 `da_skipped_reason`），不由 agent 自行决定。

> **f3a 修订（2026-07-13）**：`run_debate` 的 L3 入口从 `assemble_council_features(ticker)` 改为 `build_research_dossier(ticker)`（见下方「run_debate 入口改调 build_research_dossier」requirement），`call_agent`/`_call_da`/`_call_synthesizer` 的 `features` 形参语义从「扁平 21 字段」变为「分层 dossier」（形参名保持 `features` 不变，避免 cascade 改名）。R1/R2 的 user message 按 agent_id 角色分发 dossier 子集，R3/R4 走全量。[[design]] D3/D4。
>
> **f3c 修订（2026-07-16）**：编排新增「R1 质量门断路器」步骤（R1 gather 后、R2 前）。f1 把检测器放 `verify_quality_gate.py` 但没在 `run_debate` 调，导致质量门只在人工检查时响、watchlist 产出照常落盘。f3c 补这一步：显性环形 hard fail 阻断（无歧义铁证），凭空数字/隐性 soft warning。[[design]] D2。降级场景（R1 error rate≥0.4 运行时降级，R1<4 agent）的断路器行为：仍对幸存 agent 跑检测，显性环形照样 hard fail（降级不豁免串台铁证）。

#### Scenario: R1 信息隔离但按角色分发
- **WHEN** 执行 Round 1 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 为空列表，且 user message SHALL 按 agent_id 从 dossier 取角色侧重子集（`core_snapshot` 全员共享 + 定性维度按角色分发）

#### Scenario: R2 可见他人 R1 论点且按角色分发
- **WHEN** 执行 Round 2 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 包含 R1 中其他 agent 的 AgentOutput JSON（排除自己），且 user message SHALL 按 agent_id 角色分发 dossier 子集（同 R1）

#### Scenario: R3 DA 走全量路径
- **WHEN** 执行 Round 3（DA 未被跳过）
- **THEN** DA 的 user message SHALL 含 dossier 全部维度（不分发，`research_dossier` 全量），区别于 agent 的角色分发路径

#### Scenario: R4 Synthesizer 走全量路径
- **WHEN** 执行 Round 4
- **THEN** Synthesizer 的 user message SHALL 含 dossier 全部维度（不分发）

#### Scenario: R1 后断路器显性环形命中阻断（f3c）
- **WHEN** R1 所有 agent gather 完成后，任一 agent 的 `core_thesis` 含其他 agent_id 名字（`detect_circular_reference` 返回 False）
- **THEN** `run_debate` SHALL 在 R2 前阻断：不进 R2/R3/R4，不产出"成功"watchlist JSON
- **AND** SHALL 走 error 路径（抛错或标记 `quality_gate_failed`），记录阻断原因

#### Scenario: R1 后断路器无环形通过进入分流（f3c）
- **WHEN** R1 所有 agent 无显性环形引用（`detect_circular_reference` 全 True）
- **THEN** `run_debate` SHALL 进入分歧度分流，按 level 决定 R2/R3（断路器不拦截正常流程）
- **AND** 凭空数字/隐性串台若命中 SHALL 仅 soft warning 记入产出，不阻断

#### Scenario: 运行时降级下断路器仍拦显性环形（f3c）
- **WHEN** R1 error rate≥0.4 触发运行时降级（R1<4 agent 幸存）
- **AND** 幸存 agent 中有显性环形引用
- **THEN** 断路器 SHALL 仍 hard fail 阻断（降级豁免 R3 DA 跳过，不豁免串台铁证）

#### Scenario: R1 低分歧跳过 R2/R3
- **WHEN** R1 计算得 `level == "low"`（且未被 hard fail 阻断）
- **THEN** `run_debate` SHALL 跳过 R2 和 R3，直接进入 R4，CouncilResult.round2/round3 为 None

#### Scenario: 单 agent 下 R2 跳过 LLM 调用
- **WHEN** 只有 1 个 agent 执行 Round 2
- **THEN** 系统 SHALL 跳过 LLM 调用，CouncilResult.round2 为 None，不调用 LLM 浪费 token

#### Scenario: 单 agent 下 R3/R4 跳过
- **WHEN** 只有 1 个 agent 且无 DA/synthesizer 注册
- **THEN** R3/R4 SHALL 返回 None，不报错，CouncilResult 中对应轮次为 None

#### Scenario: DA skipped 时 CouncilResult 记录 da_skipped_reason（spec review #3 连带）
- **WHEN** DA 被跳过（low/extreme 分流、R2 evidence_exhausted≥3、运行时降级任一）
- **THEN** `CouncilResult` SHALL 在新增选填字段 `da_skipped_reason: str | None`（默认 None）填入对应取值（`"low_divergence"` / `"extreme_divergence"` / `"evidence_exhausted"` / `"runtime_degraded"`）；DA ran 时该字段为 None。`_call_synthesizer` 从该字段读 reason 传入 synthesizer prompt。**f1 N1 豁免说明**：`CouncilResult` 是编排器内部状态结构（非 L3 对外 JSON 输出 schema——f1 N1 保护的是 `AgentOutput`/`SynthesizerOutput` 的输出语义），加选填字段不触碰 N1；老代码构造 CouncilResult 不传该字段走默认 None，向后兼容。

## ADDED Requirements

### Requirement: R1 串台根因受控实验脚手架（f3c 实验性）
debate.py SHALL 提供（或 scripts/ 下提供）可重复的 R1 串台根因受控实验脚手架，分清假设 A（设计层 prompt 案例锚定）vs B（模型层弱模型复读）。

> 背景：f1 修了同质化成因但没定位串台成因。偏差分析 §1.2 铁证（环形串台方向 = AGENT_REGISTRY 顺序）从未正面回答。f3c 跑控制变量矩阵（[[design]] D1）：组1 features 充足×prompt 保留×弱模型（基线）、组2 features 缺失×prompt 保留×弱模型（复刻 600519 bug 条件）、组3 features 缺失×prompt 剥离×弱模型（支持 A）、组4 features 缺失×prompt 保留×强模型（支持 B）。实验脚本 SHALL 不改主 prompt.py（组3 用函数级 patch / 复制改写构造剥离版），实验产物落盘 `scripts/repro_out/`。

#### Scenario: 实验脚本不改主 prompt.py
- **WHEN** 跑 D1 组3（prompt 案例锚定剥离）
- **THEN** 实验脚本 SHALL 用独立构造的剥离版 prompt（函数级 patch 或复制改写），**不改 `council/prompt.py` 主文件**
- **AND** 实验完即弃，主 prompt.py 不受污染

#### Scenario: 实验观测指标齐全
- **WHEN** 跑 D1 任一组
- **THEN** 实验脚本 SHALL 采集：显性串台率（`detect_circular_reference` 命中数/4）、隐性串台率（采样）、同质化率（Jaccard `compute_citation_divergence`，用信息增量口径非纯距离）、凭空数字率（`verify_r1_feature_grounding` 命中率）

#### Scenario: 实验结论分叉记录
- **WHEN** D1 4 组实验跑完
- **THEN** 实验报告 `scripts/repro_out/crosstalk_exp_report.md` SHALL 记录 A/B 结论：组3↓ 且组4不降→主因A；组4↓且组3不降→主因B；都降→混合（记降幅比）；都不降→两假设皆否（开 f3e 新假设）
- **AND** 报告 SHALL 标注「修复（改 prompt / 换模型）开独立 f3d change，不在本 change 实施」
