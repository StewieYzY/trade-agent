## MODIFIED Requirements

### Requirement: DA prompt 职责导向
`build_da_prompt()` SHALL 返回 DA（Devil's Advocate）的 system prompt，职责导向（非 Level 2 四层结构）。DA 职责从「找盲点」升级为「仲裁」：

- 职责一：综合 R1+R2 找盲点和共识漏洞（原有）
- 职责二：**评估各 agent 引用数据点的真实性**——对每个 agent 的 key_metrics，回查 user message 中注入的 dossier 实际值，标注证据质量
- 工作守则：必须找**具体**漏洞（指向具体数据或事件），不允许泛泛之谈；证据质量评估必须基于 dossier 实际值比对，不允许纯主观
- 输出格式：`AgentOutput` + `extra.blind_spots`（列表，每项含 `title` / `detail` / `which_agents_missed_it`）+ `extra.evidence_quality_assessment`（新增，dict，key 为 agent_id，value 为 `"accurate"`/`"moderate"`/`"weak"`/`"inaccurate"`）+ `extra.recommendation`（新增，`"defer_to_<agent_id>_consensus"` 或 `"no_clear_winner"`）
- `signal` 固定 `"neutral"`，`conviction` 固定 0

> 背景：Kimi 辩论要点 4（第三方仲裁）。DA 已在 user message 注入 dossier（`_call_da` 现有实现，f3a 起注入分层 dossier 而非扁平 features）。
>
> **f3a 修订（2026-07-13）**：DA 事实回查范围从「仅 21 量化字段」扩展到「dossier 全量含定性维度数字」（[[design]] D9）。f2 时 DA 只能回查量化指标真假（features 仅 21 量化字段），f3a dossier 有定性维度数字（peer_avg_pe/consensus_eps/target_price 等），DA 回查定性维度数字自动受益于 `verify_r1_feature_grounding` 的递归 `feature_numbers` 收集（[[design]] D7）。DA 走全量路径（不分发），见 council-debate spec「角色分发按 agent_id 构造 user message」requirement。

#### Scenario: DA prompt 强调具体漏洞
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 包含"必须找具体漏洞"、"不允许泛泛之谈"相关内容

#### Scenario: DA prompt 定义 blind_spots 结构
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 列出 `extra.blind_spots` 的结构（`title` / `detail` / `which_agents_missed_it`）

#### Scenario: DA prompt 要求事实回查
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 包含要求「对每个 agent 的 key_metrics 回查 dossier 实际值，标注证据质量」的相关内容

#### Scenario: DA prompt 定义 evidence_quality_assessment 结构
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 列出 `extra.evidence_quality_assessment`（agent_id → accurate/moderate/weak/inaccurate）和 `extra.recommendation` 的结构

#### Scenario: DA 事实回查覆盖定性维度数字（f3a）
- **WHEN** DA 评估某 agent 引用 `"行业平均 PE 15.3"`（dossier 的 `research_dossier.peers.peer_avg_pe` 嵌套值）
- **THEN** DA SHALL 能回查 dossier 的嵌套定性维度数字（因 DA 走全量路径 + `verify_r1_feature_grounding` 递归收集 feature_numbers 覆盖嵌套数字），不只回查 21 量化字段
