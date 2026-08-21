## 1. 契约与 RED 测试

- [x] 1.1 为 `dossier-fact-grounding` 写 RED 测试：关闭词汇、事实字段完整、高严重度缺失来源/时间基准/来源不匹配 fail closed。
- [x] 1.2 为追溯率统计写 RED 测试：只统计已出现事实、缺失 role 不计分母、stale/降级可见。
- [x] 1.3 为 `build_research_dossier` 写 RED 集成测试：完整 dossier 携带 fact_contract/quality_status/quality_reasons，高严重度不可追溯时 fail closed。

## 2. 事实契约实现

- [x] 2.1 实现字段级 `FactEvidence`、关闭词汇校验和 `build_fact_contract`，输出可复核统计。
- [x] 2.2 实现角色事实提取、来源映射、时间基准和新鲜度判定。
- [x] 2.3 实现高严重度 fail-closed 校验与 clean/degraded 质量状态导出。

## 3. dossier 集成

- [x] 3.1 在 `build_research_dossier` 末尾挂接事实契约并执行高严重度校验，保持 raw role payload 形状不变。
- [x] 3.2 在 dossier 顶层写入 `fact_contract`、`quality_status`、`quality_reasons`，并保持向后兼容。

## 4. 验证与收口

- [x] 4.1 让 RED 测试转绿并运行 focused tests。
- [x] 4.2 运行 full pytest、compileall、`openspec validate --all --strict` 和 `git diff --check`。
- [x] 4.3 完成 independent child-only review 前不 archive；不宣称 G2 capability passed，不启动 G3。
