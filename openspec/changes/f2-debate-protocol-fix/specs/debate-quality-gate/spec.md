## ADDED Requirements

### Requirement: R2 新证据校验（soft warning，f3 落地后升 hard gate）
质量门 SHALL 新增「R2 新证据」校验维度，**以 soft warning 形式**检测 R2 是否复读 R1（不阻断产出）：

- 每个 agent 的 R2 `AgentOutput` 满足以下任一即记「有增量」通过：`new_evidence` 非空，或 `evidence_exhausted == true`
- `new_evidence` 中引用的数字 SHALL 通过反向特征校验（复用 `verify_r1_feature_grounding` 逻辑）——新引用数字必须在 features 任一字段值中出现，否则标记为「疑似编造」soft warning
- 既无 `new_evidence` 又未声明 `evidence_exhausted` 时，记「复读 R1」soft warning——**通过校验但不阻断**，仅记录供后续调优

> 背景：Kimi 辩论要点 3（每轮新数据证据防退化）。**scope 调整（2026-07-10）**：原设计为 hard gate，但实证显示 L3 输入仅 21 个纯量化字段，R2 无新维度可引（R1 已引用信息量最高的 PE/ROE/F-score/涨跌幅），硬约束会触发「编造-校验-拦截」死循环或 evidence_exhausted 全员命中。根因属信息基底不足（f3-l3-research-dossier 范畴），本 change 降为 soft。`new_evidence`/`evidence_exhausted` 字段保留作 f3 的 enabling carrier——f3 补定性维度后，R2 确有新东西可引，届时升回 hard gate 是一行改动。

#### Scenario: R2 含新证据通过
- **WHEN** agent 的 R2 `new_evidence` 含 `"PB 1.2"`，且 features 中存在值为 1.2 的字段
- **THEN** 质量门 SHALL 标记该 R2 为「有新证据」，通过校验（无 warning）

#### Scenario: R2 声明证据穷尽通过
- **WHEN** agent 的 R2 `evidence_exhausted == true`，`new_evidence` 为空
- **THEN** 质量门 SHALL 标记该 R2 为「证据穷尽」，通过校验（无 warning）

#### Scenario: R2 既无新证据又未声明穷尽 soft warning 不拦截
- **WHEN** agent 的 R2 `new_evidence` 为空且 `evidence_exhausted == false`
- **THEN** 质量门 SHALL 标记该 R2 为「复读 R1」soft warning，**仍通过校验**（返回 `pass=True` + warnings 含 `r2_no_new_evidence`），不阻断 quality gate 整体

#### Scenario: R2 新证据含凭空数字 soft warning 不拦截
- **WHEN** agent 的 R2 `new_evidence` 含 `"ROE 50%"`，但 features 中无任何字段值为 50
- **THEN** 质量门 SHALL 标记该数据点为「疑似凭空编造」soft warning，**仍通过校验**（返回 `pass=True` + warnings 含 `suspected_fabricated_evidence`），不阻断（f3 升 hard 后改为拦截）

#### Scenario: 校验模块可单元测试
- **WHEN** 实现新证据校验逻辑
- **THEN** SHALL 将校验抽成可导入函数 `verify_r2_new_evidence(output: AgentOutput, features: dict) -> tuple[bool, list[str]]`，复用 `verify_r1_feature_grounding` 的数字提取与匹配逻辑，**返回 `bool=True`（soft 不拦截）+ warnings 列表**

### Requirement: 分歧报告完整性校验
质量门 SHALL 新增「分歧报告完整性」校验维度，确保 R4 的 SynthesizerOutput 含结构化分歧信息：

- 全天团 R4 输出 SHALL 含 `divergence_level`（非 None）
- 当 `divergence_level` 为 `high` 或 `extreme` 时，`key_disagreements` SHALL 非空
- `calibration_status` SHALL 为 `"uncalibrated"`

#### Scenario: 分歧报告字段齐全通过
- **WHEN** R4 的 SynthesizerOutput 含 `divergence_level: "medium"`、`calibration_status: "uncalibrated"`
- **THEN** 质量门 SHALL 通过校验

#### Scenario: 高分歧缺 key_disagreements 拦截
- **WHEN** R4 的 `divergence_level: "high"` 但 `key_disagreements` 为空
- **THEN** 质量门 SHALL 不通过，提示 synthesizer prompt 未输出结构化分歧点

#### Scenario: 缺 divergence_level 拦截
- **WHEN** R4 的 SynthesizerOutput `divergence_level` 为 None
- **THEN** 质量门 SHALL 不通过，提示 synthesizer 未输出分歧等级

#### Scenario: 校验模块可单元测试
- **WHEN** 实现分歧报告校验逻辑
- **THEN** SHALL 将校验抽成可导入函数 `verify_divergence_report(syn_output: SynthesizerOutput) -> tuple[bool, list[str]]`

### Requirement: DA 仲裁事实回查校验
质量门 SHALL 新增「DA 仲裁事实回查」校验维度，确保 DA 的 `evidence_quality_assessment` 基于真实 features 比对而非纯主观：

- DA 输出 SHALL 含 `extra.evidence_quality_assessment`（非空 dict）
- DA 标注某 agent 为 `"inaccurate"` 时，SHALL 能在 DA 输出或比对中体现 features 实际值与 agent 引用值的差异
- DA 的 `recommendation` SHALL 引用真实存在的 agent_id（在 AGENT_REGISTRY 中）或为 `"no_clear_winner"`

> **spec review #2/#3 修订：DA skipped 条件分支**。DA 可能被跳过（low/extreme 分流、R2 evidence_exhausted≥3、运行时降级）。`da_skipped_reason` 取四值（`"low_divergence"` / `"extreme_divergence"` / `"evidence_exhausted"` / `"runtime_degraded"`），存 `CouncilResult`（编排器内部状态，非 L3 输出 schema，不违反 f1 N1）。质量门按 skip 原因区分处理：
> - **情况 A（low 或 extreme 分歧跳 R3）**：low = agent 高度一致无分歧可仲裁；extreme = agent 完全分散（1:1:1:1）DA 亦无共识倾向可判——两者对称，DA 无仲裁价值。`verify_da_fact_check` SHALL **跳过**（不跑，返回 `pass=True` 无 warning，因无 DA 输出可校验、亦无信息缺口）。extreme 路径的结构化分歧由 `verify_divergence_report` 兜底（`divergence_level=="extreme"` + 非空 `key_disagreements`，不在此重复校验）。
> - **情况 B（evidence_exhausted≥3 或运行时降级跳 R3）**：R1/R2 数据点未经事实回查是真实信息缺口，`verify_da_fact_check` SHALL 返回 **soft warning**（`pass=True` + warnings 含 `"da_skipped: r1_r2_evidence_not_fact_checked"` + `da_skipped_reason`），不阻断 quality gate。

#### Scenario: DA 含 evidence_quality_assessment 通过
- **WHEN** DA 输出 `extra.evidence_quality_assessment = {"buffett": "accurate", "munger": "moderate"}` 非空
- **THEN** 质量门 SHALL 通过此维度校验

#### Scenario: DA 缺 evidence_quality_assessment 拦截
- **WHEN** DA 输出 `extra.evidence_quality_assessment` 为空或缺失
- **THEN** 质量门 SHALL 不通过，提示 DA 未做事实回查（退化成纯文字评估风险）

#### Scenario: DA recommendation 引用不存在的 agent 拦截
- **WHEN** DA 输出 `extra.recommendation = "defer_to_zhangkun_consensus"`，但 "zhangkun" 不在 AGENT_REGISTRY
- **THEN** 质量门 SHALL 不通过，提示 recommendation 引用非法 agent_id

#### Scenario: DA 因 low 分歧被跳过——校验跳过（情况 A，spec review #2）
- **WHEN** R1 `level == "low"`，DA 被跳过（`da_output=None`，`da_skipped_reason == "low_divergence"`）
- **THEN** `verify_da_fact_check` SHALL 跳过（返回 `pass=True` + 空 warnings），不阻断 quality gate

#### Scenario: DA 因 extreme 分歧被跳过——校验跳过（情况 A，spec review #3 补）
- **WHEN** R1 `level == "extreme"`（signal 完全分散），DA 被跳过（`da_output=None`，`da_skipped_reason == "extreme_divergence"`）
- **THEN** `verify_da_fact_check` SHALL 跳过（返回 `pass=True` + 空 warnings），不阻断 quality gate；结构化分歧由 `verify_divergence_report` 兜底（`divergence_level=="extreme"` + 非空 `key_disagreements`）

#### Scenario: DA 因 evidence_exhausted 被跳过——soft warning（情况 B，spec review #2）
- **WHEN** R2 ≥3 agent 标 `evidence_exhausted: true`，DA 被跳过（`da_output=None`，`da_skipped_reason == "evidence_exhausted"`）
- **THEN** `verify_da_fact_check` SHALL 返回 `pass=True` + warnings 含 `"da_skipped: r1_r2_evidence_not_fact_checked"`（不阻断，但信息缺口可见：R1/R2 agent 引用数据点的真实性未经回查）

#### Scenario: DA 因运行时降级被跳过——soft warning（情况 B，spec review #3 补）
- **WHEN** R1 error rate ≥0.4 触发运行时降级，DA 被跳过（`da_output=None`，`da_skipped_reason == "runtime_degraded"`）
- **THEN** `verify_da_fact_check` SHALL 返回 `pass=True` + warnings 含 `"da_skipped: r1_r2_evidence_not_fact_checked"`；`confidence_cap=40` 的应用由 conviction 范围校验覆盖（不在此 scenario 重复，TDD 一 scenario 一维度）

#### Scenario: 校验模块可单元测试
- **WHEN** 实现 DA 事实回查校验逻辑
- **THEN** SHALL 将校验抽成可导入函数 `verify_da_fact_check(da_output: AgentOutput | None, agent_ids: tuple[str, ...] | None = None, da_skipped_reason: str | None = None) -> tuple[bool, list[str]]`（spec review #3 修订：`da_output` 可为 None，`da_skipped_reason` 显式传入——`da_output=None` 时由 reason 决定情况 A 跳过 / 情况 B soft warning）
