## Context

f3c 的 D1 live 结果在冻结 600009.SH dossier 上未复现显性或隐性串台，prompt 案例剥离与 weak/heavy 模型切换也未形成 A/B 主因证据。下一轮必须验证输入装配、角色分发、ticker/dossier 绑定和编排状态，而不是继续修改 prompt/model。

## Goals / Non-Goals

**Goals:**

- 固定 provider-frozen dossier、canonical ticker、run_id、source hash 和安全 output root。
- 比较角色分发、全员共享、输入错配 fail-closed 与现有编排路径。
- 每 agent 保存 raw response、parsed output、usage、prompt/user hash 和输入 hash。

**Non-Goals:**

- 不修改主 prompt，不切换模型，不启动 G3。
- 不刷新全市场，不宣称 G2 capability passed。

## Decisions

- **冻结输入**：实验只接受带 `600009.SH` 身份和 source hash 的 dossier；缺失或 mismatch 立即 fail closed。
- **分支最小化**：先比较输入/分发差异，保持模型、prompt 和 ticker 不变。
- **证据隔离**：每个 run 使用唯一 run_id；raw、报告、quality metadata 放在独立 output root，不覆盖 f3c bundle。
- **失败优先**：任何 ticker、dossier hash 或 run_id 不一致均不计入 clean success。

## Risks / Trade-offs

- [provider cache 过期或字段缺失] → 记录 evidence gap，不用 mock 结果替代。
- [单次 live 结果不稳定] → 固定输入并重复配对，保持 change active 直到可复核。
- [检测器自身逃逸] → 字符串检测和语义采样分开记录，不直接将采样升级为 hard gate。

## Migration Plan

1. 先补 RED 测试和 input envelope 校验。
2. 在授权和冻结输入就绪后运行四分支实验。
3. 保存 raw evidence、指标和报告，完成独立 review。
4. 仅在证据充分时创建后续 runtime/provider repair change。

## Open Questions

- provider dossier 的完整字段集合是否稳定且与角色分发契约一致？
- 是否存在前一 agent output、ticker 或 dossier 被下一调用复用的路径？
- 新假设是否应拆成独立 provider-contract change？

> 2026-08-19 实现回填：envelope/identity 绑定、四分支 harness、per-agent 指标与
> 报告已实现并通过 focused tests（11 passed）+ 全量 suite（1059 passed）。
> live 配对实验已执行（见下），3.2 独立 review 待办。现有编排分支通过临时包装
> `council.debate.call_llm` 捕获 raw response，并与 audit prompt artifact 的
> R1 user message hash 做直接调用对照；raw 不可得时记 evidence gap，不伪装 complete。
> 身份绑定除 source hash 外，另以 `EXPECTED_DOSSIER_SHA256`（frozen 文件 payload hash
> `556120be…678f`）做内容级 fail-closed，保留 freeze 篡改内容也会被拦截。

> 2026-08-19 live 回填（run_id `f3e-live-20260819-01`，用户授权）：
> 角色分发与全员共享各 4/4 R1 调用成功，显性/隐性串台均为 0，
> grounding_unverified_rate 均为 1.0（反向校验未通过主要因单位/派生值未归一：
> 9.34亿 vs 934000000、54% vs 0.540988、77% vs 0.7698、年份 2023-2025 等；
> 即使补全 `roe_3y/net_margin` 仍为 1.0，不能解读为全部编造数字），
> Jaccard_dist mean 0.747 / 0.607，input_consistency 1.0；
> mismatch 分支六类错配（ticker/dossier hash/run_id/freeze/source hash/content tamper）
> 全部在 LLM 前 fail-closed；mismatch 分支已用最终 harness 确定性重生成（无 LLM）
> 纳入 live 证据包，直接分支保留 live run 证据。现有编排分支被
> `run_debate` 预检拦截：frozen dossier `core_snapshot` 缺
> `roe_3y/net_margin`，未进入 R1 LLM 调用，已记为 evidence gap；
> 因此「编排状态是否导致 R1 串台」在该冻结输入上仍不可验证，
> 需先由 provider/runtime repair change 补全 dossier 或显式降级后再测。
> 本 change 保持 active，不宣称 G2 capability passed。

> 2026-08-20 独立 review：`codex review --uncommitted` 独立 subagent 发现
> P1 evidence_gap 文案不一致并已修复（`raw response not exposed` → `raw R1 response
> not exposed`），focused 15 passed / 全量 1063 passed。决定暂不新建
> runtime/provider repair change：编排分支仍被有效 `roe_3y/net_margin` 缺失阻断，
> 需先由 provider/input repair 补全 frozen dossier 后重测；本 change 保持 active。

> 2026-08-20 输入修复 + 重跑（run_id `f3e-live-20260820-01`，用户授权）：
> 已从根目录只读 cache 的 `financials.json` 派生补全 frozen dossier 的有效
> `roe_3y`（2023/2024/2025）与 `net_margin`（2025），payload hash 更新为
> `556120be…678f`；source hash 保持 `f588d5bf…a00c9`，未刷新 provider。
> `run_debate` 预检通过。角色分发与全员共享仍各 4/4 ok，显性/隐性串台 0，
> grounding_unverified 1.0（仍为单位/派生值未归一导致，不解读为全部编造），
> Jaccard_dist 0.612 / 0.718，input_consistency 1.0；mismatch 六类仍全部
> fail-closed。现有编排分支已越过预检、进入真实 R1 调用，但首个编排调用返回
> DeepSeek `402 Payment Required`，因此仍无编排 R1 产出。该证据 gap 是 provider
> 计费/可用性问题，不是输入身份或串台根因；本 change 继续 active，
> 编排状态假设待 provider 余额恢复并重新授权后再测。

> 2026-08-20 provider 恢复后编排分支单独重跑（run_id `f3e-live-20260820-02`）：
> `existing_orchestration` 完整通过：4/4 R1 ok，`input_assembly_mismatches=[]`，
> `evidence_gaps=[]`，explicit/implicit crosstalk 0，Jaccard_dist mean 0.790，
> input_consistency 1.0。审计 prompt artifact 的 R1 user message 与直接
> `role_distribution` 分支一致，因此在该冻结输入上未复现输入装配、角色分发、
> ticker/dossier/run identity 或编排状态导致的 R1 串台。
> `grounding_unverified_rate=1.0` 仍为单位/派生值归一误报，单独记录，
> 不升级为 G2 capability。本 change 的串台根因诊断仍未发现明确根因。
