## 1. 输入与身份

- [x] 1.1 固定 provider-frozen dossier、canonical ticker、source hash、run_id 和安全 output root。**Verify**：`create_run_envelope`/`load_verified_dossier` 绑定 freeze hash 与 `AuditIdentity`，focused tests 10 passed ✓
- [x] 1.2 写 RED 测试覆盖 ticker/dossier/run_id mismatch fail-closed。**Verify**：mismatch 分支在 LLM 前 fail-closed（4 类错配全拦截），RED→GREEN ✓

## 2. 实验

- [x] 2.1 实现角色分发、全员共享、错配 fail-closed 与现有编排四分支。**Verify**：`f3e_input_assembly_exp.py` 四分支 harness 已实现（live 未执行，见 2.2）✓
- [x] 2.2 运行授权 live 配对实验并落盘 raw、parsed output、hash、usage 和报告。**Verify**：`f3e-live-20260819-01` 使用 frozen dossier `f588d5bf…a00c9`，落盘 `f3e_input_assembly_live_20260819/`（data + raw × 4 + report）；角色分发/all_shared 各 4/4 ok，六类错配（ticker/dossier hash/run_id/freeze/source hash/content tamper）全部 fail-closed，现有编排因 frozen dossier 缺 `roe_3y/net_margin` 预检失败并记 evidence gap；mismatch 分支已用最终 harness 确定性重生成（无 LLM）✓；`2026-08-20` 补全有效 `roe_3y/net_margin` 后重跑 `f3e-live-20260820-01`，编排分支越过预检但遇 DeepSeek `402 Payment Required`，仍记 evidence gap（见 design）
- [x] 2.3 记录 per-agent 串台、Jaccard、grounding 与输入一致性指标。**Verify**：per-agent records 含 raw/parsed/hash/usage；指标：explicit/implicit 0、grounding_unverified 1.0（反向校验未通过，见报告注）、Jaccard_dist 0.747/0.607、input_consistency 1.0 ✓

## 3. 验证与边界

- [x] 3.1 完成 focused/full tests、compileall、OpenSpec strict 和 diff check。**Verify**：focused 15 passed + 全量 1063 passed；compileall、`openspec validate --strict`、`git diff --check` 均通过 ✓
- [x] 3.2 独立 review 后决定是否创建 runtime/provider repair change；不宣称 G2 passed。**Verify**：`codex review --uncommitted` 独立 review 发现 P1（evidence_gap 文案少 `R1` 导致 focused test 失败），已修复并重跑 15/1063 passed；补全 frozen dossier 后重测编排分支，但遇 provider `402 Payment Required`，下一步先解决 provider 计费/可用性，暂不创建代码级 repair change ✓
- [x] 追加：provider 恢复后编排分支单独重跑通过（`f3e-live-20260820-02`，4/4 ok、无 input assembly mismatch、显性/隐性串台 0），仍不宣称 G2 passed；本 change 未发现明确串台根因 ✓
