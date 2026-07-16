## Why

f1-deviation-fix 用 `detect_circular_reference` + `verify_r1_feature_grounding` 对 R1 串台/同质化做了**事后检测**，但这两个函数**只在 `verify_mechanism_gate` 的人工检查路径里 print [WARNING]，`debate.py` 产出 watchlist 的主流程零调用**——质量门从未真正拦截污染产出（CLAUDE.md 悬案：7 份 watchlist 6 份 `consensus_summary/conviction/dissent_points` 为 null，根因闭环）。更关键的是，**串台的成因从未被定位**：f1 修了「同质化」那一半（features 缺失→复读模板邻近值，`financials_floor` fail-fast 消除），但假设②（features 缺失）解释不了「串台」——600900 单 agent 模式下 buffett 仍写"munger 看好"，21 量化字段里不含人名，这话只能来自 prompt 或模型。偏差分析 §1.2 的铁证（环形串台方向与 AGENT_REGISTRY 顺序一致）至今无人正面回答。

这是 AD-09（辩论产生信息增量）假设的**存亡问题**：若 4 agent 在当前 prompt/模型组合下就是会串台/复读，「天团辩论」立项前提即错。L3.5 持有纪律层在 L3 之上盖楼前必须清这个地基。详见 `design/r1-crosstalk-root-cause-explore.md`。

## What Changes

本 change 是 **bug 定位 + 条件式修复**类（参照 f1 模式），不是单纯加检测器。三个层面：

1. **受控实验定位根因**（What 不定，取决于结果分叉）——分清两个互斥假设：
   - **假设 A（设计层根因）**：system prompt 第 2 层「案例锚定」（`prompt.py:40` `可口可乐→茅台`、`:120` 芒格提"巴菲特"、`:164` 段永平"实际买过茅台"）在 features 单薄时被模型当事实素材复读 + 复读训练语料"巴菲特-芒格-段永平"形影不离叙事。
   - **假设 B（模型层根因）**：弱模型（DeepSeek）在 JSON schema 约束下倾向复读语料，与 prompt 设计无关。
   - 实验设计：features 充足 vs 缺失 × prompt 案例锚定保留 vs 剥离 × 模型弱 vs 强，观测显性串台率（`detect_circular_reference` 命中）+ 隐性串台率（语义采样）+ 同质化率 + Jaccard 分化度（参照 f3a D6，但用**信息增量口径**而非纯 Jaccard 距离，避开"切窄维度即飙高"的假高分）。
   - **修复分叉**（写进 design Decisions，待实验结果定稿后开 f3d 修复 change，不在本 tasks 硬编）：
     - 若 A 成立 → 改 prompt 设计哲学（案例锚定从"事实素材"降格为"格式范例，禁止当数据引用"），架构变更，可能动摇 AD-09。
     - 若 B 成立 → 换模型 / 调 `reasoning_level`，不动 prompt，L3.5 可推进。

2. **质量门接主流程（接线，确定性）**——把 `detect_circular_reference` / `verify_r1_feature_grounding` 从 `verify_quality_gate.py` 的 print-only 调用，接进 `debate.py::run_debate` 主流程的 R1 后断路器：R1 输出含环形引用或凭空数字时，**不产出"成功"JSON 落盘**（或标记 quality_gate_failed，区别于降级场景的 soft warning）。让 AD-09 gate 在主流程真正启用，而非只在人工检查时响。

3. **检测器逃逸面补强（实验顺带验证）**——`detect_circular_reference` 现为字符串子串匹配（`aid in thesis`），模型不直呼 agent_id（写"另一位价值投资者"）即绕过。实验里采样真实产出看隐性串台占比，并在 design 记录是否需要升级为语义级检测（不在本 change 实施，除非实验证明隐性串台率高到现检测器失效）。

**不做的**（scope 控制）：
- 不重跑全市场（P1 既有差距）
- 不改 f3a 的角色分发（实验用 f3a 现有产出做基线之一，不动 dossier）
- 不升 f3a D2 hard（f3a 已明确保持 soft，独立 change）
- 不做 L3.5（本 change 是 L3.5 的前置地基）

## Capabilities

### New Capabilities
<!-- 无新建 capability。本 change 是定位 + 接线，复用现有 debate-quality-gate / council-debate spec。 -->

### Modified Capabilities
- `debate-quality-gate`: R1 质量门从「仅人工检查 print warning」升级为「主流程断路器」——`detect_circular_reference` / `verify_r1_feature_grounding` 在 `run_debate` R1 后强制调用，命中则阻断"成功"产出落盘（与降级场景 soft warning 区分）。新增"隐性串台"语义采样检测的实验性 scenario。
- `council-debate`: `run_debate` 主流程接入 R1 质量门断路器；R1 实验脚手架（features 充足/缺失、prompt 案例锚定保留/剥离、模型弱/强的受控对照）作为可重复实验记录入 spec scenario。

## Impact

**受影响代码**：
- `value-screener/council/debate.py` — `run_debate` R1 后接入 `detect_circular_reference` / `verify_r1_feature_grounding`，命中阻断产出（接线，**确定性**，写进 tasks）
- `value-screener/council/verify_quality_gate.py` — 检测器函数本身（已存在 f1 实现），本 change 不重写逻辑，只改调用位置；新增实验性隐性串台采样辅助（实验用，标注"实验性"）
- `value-screener/council/prompt.py` — **仅在实验阶段临时剥离案例锚定做对照**，不直接改（修复取决于 A/B 结果，写进 design 不写进 tasks）
- `value-screener/scripts/repro_out/` — 实验产物（A/B 对照数据）落盘于此，参照 f1 的 ROOT_CAUSE.md 模式写实验报告

**依赖**：无新依赖。实验复用现有 `call_llm` + `run_debate`，模型对照走现有 `LLM_MODEL` / `LLM_MODEL_HEAVY` env 切换。

**AD 引用**（不重复搬运）：
- **AD-09**（辩论增量 gate）：本 change 直击 AD-09 存亡——串台根因若是设计层（假设 A），AD-09 在当前 prompt 架构下不成立，需架构变更；若是模型层（假设 B），AD-09 成立，换模型即可。
- **AD-05**（不用多 agent 框架）：实验和接线都是串行 LLM 调用 + Python 检测，不引入框架。
- **AD-04**（推理等级映射）：实验的"模型弱 vs 强"对照走 `reasoning_level` + `LLM_MODEL` env，不新增映射。

**风险**：
- **实验成本**：受控实验需多次 LLM 调用（features×prompt×模型 矩阵），但均为单股 L3 R1（非全天团 10 轮），成本可控（参照 AD-03 单股预算）。
- **接线回归**：质量门接主流程后，现有真实产出（600009.SH）可能因隐性串台采样误判被拦——需用 600009 真实完整产出做回归基线（f1 已验证它通过 R1 接地 + 环形检测）。
- **A/B 不互斥**：真实根因可能是 A+B 混合（弱模型 + 诱导性 prompt 共同作用）。实验需设计能区分主因的对照（控制变量法），design 详述。
