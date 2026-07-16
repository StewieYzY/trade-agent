## Context

f1-deviation-fix 修复了 R1 同质化的**成因**（features 缺失→`financials_floor` fail-fast），但对串台只做了**事后检测**（`detect_circular_reference` + `verify_r1_feature_grounding`）。这两个检测器存在两个未解决的问题（详见 `design/r1-crosstalk-root-cause-explore.md` §三-五）：

1. **没接到主流程断路器**：只在 `verify_quality_gate.py:473-495` 的 `verify_mechanism_gate` 人工检查路径里 `print [WARNING]`，不 `return False`、不影响 gate 布尔结论；`debate.py::run_debate`（产出 watchlist 的主流程）grep 零命中。净效果：质量门能**识别**污染，但**不阻止**污染进入 watchlist JSON（CLAUDE.md 悬案：7 份 watchlist 6 份 null 的闭环根因）。

2. **串台成因未定位**：f1 排除了偏差分析假设①（prompt 无占位文本）③（无 LLM 缓存层），确认假设②（features 缺失）。但假设②解释不了串台——600900 单 agent 模式下 buffett 仍写"munger 看好长期价值"，21 量化字段不含人名。偏差分析 §1.2 铁证（环形串台方向 = AGENT_REGISTRY 顺序）至今无正面回答。f1 排查假设①的口径是"占位文本"，但真正诱导串台的可能是 system prompt 第 2 层「案例锚定」（`prompt.py:40` `可口可乐→茅台`、`:120` 芒格提"巴菲特"、`:164` 段永平"实际买过茅台"）——这是推测，**从未受控验证**。

**约束继承**：
- **AD-09**（辩论增量 gate）：本 change 直击 AD-09 存亡。串台根因若设计层（A），AD-09 在当前 prompt 架构下不成立；若模型层（B），AD-09 成立换模型即可。
- **AD-05**（不用多 agent 框架）：实验 + 接线都是串行 LLM + Python 检测，无框架。
- **AD-04**（推理等级映射）：实验"模型弱 vs 强"走 `reasoning_level` + `LLM_MODEL` env，不新增映射。
- **AD-03**（成本闸门）：实验为单股 R1 调用（非全天团 10 轮），成本可控。

**当前代码现状**（已核实接入点）：
- `detect_circular_reference(output, agent_ids=None)`（`verify_quality_gate.py:317-356`）：字符串子串匹配，`aid in thesis`，自引不算。`agent_ids` 缺省动态读 `AGENT_REGISTRY.keys()`（f1 P3 修复）。
- `verify_r1_feature_grounding(output, features)`（`:143`）：提取 output 数字，比对 `feature_numbers`（f3a D7 已改递归遍历，dossier 嵌套数字不误判）。
- `verify_mechanism_gate(ticker, force)`（`:360`）：CLI `verify_quality_gate.py:726` 调用的人工入口。hard fail 只覆盖结构完整性（R4 字段非空）；R1 接地/环形检测在其内部但 print-only（`:473-495`）。
- `run_debate(ticker, force)`（`debate.py`）：产出 watchlist 的主流程，4 轮编排，**不调任何 R1 质量门函数**。

## Goals / Non-Goals

**Goals:**
- **G1 受控实验定位串台根因**：分清假设 A（设计层 prompt 案例锚定）vs B（模型层弱模型复读），用控制变量矩阵给出可证伪结论。
- **G2 质量门接主流程**：`detect_circular_reference` / `verify_r1_feature_grounding` 接进 `run_debate` R1 后断路器，命中阻断"成功"产出落盘，让 AD-09 gate 真正启用。
- **G3 检测器逃逸面评估**：采样真实产出看隐性串台（模型不直呼 agent_id 绕过字符串匹配）占比，记录是否需升级语义检测。

**Non-Goals:**
- **不修串台本身**：修复（改 prompt / 换模型）取决于 A/B 实验结果，写进本 design Decisions 段标注「待定稿」，**开独立 f3d 修复 change 实施**，不在本 tasks 硬编（避免伪造注定要改的 task）。
- **不动 f3a 角色分发**：实验用 f3a 现有产出做基线之一，不回改 dossier。
- **不升 D2 hard**：f3a 明确保持 soft，独立 change。
- **不做 L3.5**：本 change 是 L3.5 前置地基。
- **不重跑全市场**：P1 既有差距。

## Decisions

### D1：实验设计——控制变量矩阵（3×2×2 但不全跑，先跑区分主因的最小对照）

**问题**：要分清 A（prompt）vs B（模型），需控制变量。全矩阵（features 充足/缺失 × prompt 锚定保留/剥离 × 模型弱/强 = 8 组）成本高，且很多组信息冗余。

**决策**：跑**最小区分主因对照**，4 组：

| 组 | features | prompt 案例锚定 | 模型 | 观测 |
|---|---|---|---|---|
| 1（基线） | 充足（600009 真实 dossier） | 保留 | 弱（DeepSeek） | 串台率（应为低，因 features 充足）|
| 2 | **缺失**（构造空 features，复刻 600519 旧 bug 条件） | 保留 | 弱 | 串台率（f1 已知高，复现验证）|
| 3 | 缺失 | **剥离**（临时删 prompt:40/120/164 案例锚定段） | 弱 | 若串台率显著降 → 支持假设 A |
| 4 | 缺失 | 保留 | **强**（gpt-4 级，env 切换） | 若串台率显著降 → 支持假设 B |

**判读规则**：
- 组3↓ 且 组4 不降 → 主因 A（prompt 设计），改 prompt 架构。
- 组4↓ 且 组3 不降 → 主因 B（模型），换模型。
- 组3↓ 且 组4↓ → A+B 混合，主因看降幅比，design §Open Questions 记录混合程度，修复需双管。
- 组3、组4 都不降 → 两假设皆否，根因在别处（如 debate.py 编排），需新假设，开 f3e。

**为何不全跑 8 组**：组1（features 充足）已由 600009 真实产出轻度验证（f1 回放四 agent 全通过环形检测），无需再跑"充足×剥离×强"等冗余组。最小 4 组足以区分主因。

**观测指标**：
- 显性串台率：`detect_circular_reference` 命中率（4 agent 中命中数 / 4）
- 隐性串台率：人工/语义采样（组2 的 buffett 写"另一位价值投资者看好"这类不直呼 agent_id 的引用占比）——G3
- 同质化率：`key_metrics` 集合 Jaccard（参照 f3a D6 `compute_citation_divergence`），但**用信息增量口径**：不只看距离，看"分化是否来自角色看到独特真数据"（组1 的分化应来自 dossier 真数据，组2 的分化若>0 则是噪音非增量）
- 凭空数字率：`verify_r1_feature_grounding` 命中率

**备选**：只跑 2 组（features 缺失 × prompt 保留/剥离）——否决，分不清 A/B，缺模型维度。全 8 组——否决，冗余且贵。

### D2：质量门接主流程——R1 后断路器，区分 hard fail vs soft warning

**问题**：接线不是简单把 print 改 return False。`run_debate` 有降级场景（f2：R1 error rate≥0.4 运行时降级，R1<4 agent），降级时强行 hard fail 会误杀幸存 agent。且 f3a D5 有 peers/research 降级标注（soft 不阻断）——质量门要和这些 soft 路径区分。

**决策**：R1 后断路器分两档：
- **hard fail（阻断落盘）**：`detect_circular_reference` 命中**显性串台**（core_thesis 含其他 agent_id 字面）。这是 f1 已确认的幻觉铁证，无歧义，直接阻断——不产出"成功"JSON，`run_debate` 抛 `CrosstalkDetectedError`（或标记 `quality_gate_failed`，按现有 error 路径走，参照 f1 `insufficient_data` 的 fail-fast 模式）。
- **soft warning（不阻断，记入产出）**：`verify_r1_feature_grounding` 命中凭空数字、隐性串台采样命中。这些有误判风险（f3a dossier 嵌套数字 f1 D7 已修，但语义级隐性串台采样准确率未验证），soft 标注记入 watchlist JSON 的 quality 字段，不阻断——与 f2/f3a 降级哲学一致（标 degraded 继续，诚实标注）。

**接线位置**：`run_debate` R1 4 agent gather 完成后、R2 之前。hard fail 在此阻断，避免 R2/R3/R4 浪费 LLM 调用（成本，AD-03）。

**为何不接进 `verify_mechanism_gate`**：那个是人工检查入口（CLI 调），`run_debate` 是程序主流程。接线必须在 `run_debate` 内，否则 watchlist 产出照常落盘。f1 把检测器放 `verify_quality_gate.py` 是对的（职责分离），但忘了在 `run_debate` 调——本 change 补这一步。

**备选**：全 hard fail（接地+环形+隐性都阻断）——否决，隐性采样误判风险高会误杀真实产出（600009 回归风险）。全 soft——否决，环形串台是铁证不阻断等于没接。

### D3：检测器逃逸面——G3 采样评估，不本 change 升级语义检测

**问题**：`detect_circular_reference` 是字符串子串匹配，模型写"另一位价值投资者看好"即绕过（探索稿 §五）。是否本 change 升级语义级检测？

**决策**：**不升级**，只评估。G3 在 D1 实验组2（features 缺失）采样真实产出，统计隐性串台占比。若占比高（>阈值，待实验定），在 design §Open Questions 记录"需升级语义检测"，开独立 change；若低，字符串匹配够用，不动。

**为何不本 change 升级**：语义级检测（embedding 相似度 / LLM-judge）引入新依赖 + 准确率需校准，scope 膨胀。先量化逃逸面再决定。

**备选**：直接上 LLM-judge 判隐性串台——否决，scope 膨胀且 LLM-judge 自身有幻觉风险（用 LLM 查 LLM 幻觉，循环）。

### D4：修复分叉——待实验定稿，开独立 f3d change

**问题**：proposal 写了"实验+修复+接线"，但修复（改 prompt / 换模型）取决于 D1 实验结果，现在写不进 tasks。

**决策**：**修复不进本 tasks**。本 change 的 tasks 只覆盖：D1 实验（跑 4 组出报告）+ D2 接线（hard fail + soft warning）+ D3 采样（G3）。D1 实验出结论后：
- 若 A → 开 f3d-r1-crosstalk-prompt-fix：改 `prompt.py` 案例锚定设计哲学（架构变更，需 design 探讨 AD-09 是否动摇）。
- 若 B → 开 f3d-r1-crosstalk-model-fix：换 `LLM_MODEL_HEAVY` / 调 `reasoning_level`（轻量，可能无需独立 change，直接调 env）。
- 若 A+B → f3d 双管。
- 若皆否 → 开 f3e 新假设。

**为何不塞进本 tasks**：TDD 要求 task 有明确 verify（fail→impl→pass）。修复 task 的 verify 取决于实验结果，现在写就是"待回填"空壳，违反 `subagent-driven-development` / `verification-before-completion` 纪律。诚实做法：实验定位 + 接线是确定的，做进 tasks；修复是条件的，进 design 待定。

**备选**：本 change 一次性做实验+修复——否决，修复方向未知时无法 TDD。

## Risks / Trade-offs

- **[实验 LLM 成本]** → D1 最小 4 组，每组 4 agent × R1 = 4 次调用，共 16 次 R1 调用（非 10 轮全天团），AD-03 预算内。
- **[接线回归 600009]** → D2 hard fail 可能误杀 600009 真实产出（若它含隐性串台）。缓解：接线前用 600009 做 D2 的回归基线测试（f1 已验证它通过显性环形检测 + R1 接地），hard fail 只拦显性环形，600009 应继续通过。
- **[A/B 不互斥]** → D1 判读规则已覆盖混合情况（组3+组4 都降），记降幅比，修复双管。
- **[弱模型 D1 组4 不可得]** → 若 env 无强模型 key，组4 跑不了，A/B 分不清。缓解：组4 为关键判别组，需确认 `.env` 有强模型配置或临时配置；若无，本 change 降级为只验证 A（组1-3），B 留待有强模型时补，design 标注。
- **[prompt 剥离组3 临时改动污染主 prompt]** → D1 组3 需临时删 prompt 案例锚定段。缓解：实验用独立实验脚本 `scripts/repro_out/crosstalk_exp.py` 构造剥离版 prompt（函数级 patch / 复制改写），**不改 `prompt.py` 主文件**，实验完即弃。
- **[隐性串台采样主观]** → D3 人工采样有主观性。缓解：采样规则前置定义（core_thesis 含"其他/另一位/共识/也看好"等不点名引用即标隐性），多人交叉标注或记为"待语义检测验证"。

## Migration Plan

**部署顺序**（tasks 实施顺序）：
1. 实验脚手架（`scripts/repro_out/crosstalk_exp.py`，构造 D1 4 组对照，不改主代码）
2. 跑 D1 4 组实验，落盘 `repro_out/crosstalk_exp_report.md`（A/B 结论 + 降幅数据）
3. D2 接线：先写测试（600009 真实产出通过 hard fail；构造环形串台产出被 hard fail 阻断）→ 改 `run_debate` 接断路器 → 跑 council 测试套件无回归
4. D3 采样：在 D1 组2 产出上跑隐性串台采样，记入实验报告
5. 收尾：更新 design Open Questions（A/B 结论回填、隐性串台占比、是否需 f3d/f3e）

**回滚策略**：
- 实验脚手架是 `scripts/` 新增文件，回滚直接删。
- D2 接线是 `run_debate` 加 R1 后断路器，回滚删该段 + 测试。保留 `agent_id=None` 退化路径不现实（接线是新增调用非签名改），但断路器是独立 try/except 段，删之即回退 f1 状态。

## Open Questions

> 本 change 实施期回填。

- **D1 强模型可得性**：组4 需强模型（gpt-4 级）env。实施时确认 `.env` 是否有 `LLM_MODEL_HEAVY` 强模型配置；若无，降级为只验证 A（组1-3），B 留待补。
- **D1 组3 prompt 剥离边界**：删哪些段算"剥离案例锚定"？候选：`prompt.py:40-44`（巴菲特护城河映射）、`:120-123`（芒格核心案例）、`:164-167`（段永平实际买过）、`:235-238`（冯柳真实案例）。实施时定义剥离集，记入实验报告。
- **D2 hard fail 的 error 路径**：抛 `CrosstalkDetectedError` 还是标记 `quality_gate_failed` 字段？需看 `run_debate` 现有 error 处理（`insufficient_data` 是抛 ValueError 还是标记）保持一致。实施时核实。
- **D3 隐性串台阈值**：占比>多少算"高需升级语义检测"？待 D1 组2 采样数据出来定。
- **A/B 结论后是否动摇 AD-09**：若 A 成立（prompt 设计是串台根因），AD-09"辩论产生增量"在当前 prompt 架构下不成立——这是架构级问题，需 architect 介入（`~/.claude/agents/architect`），可能触发 total-design 修订。本 change 不下结论，实验报告呈递后由 architect 评判。
