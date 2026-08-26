## 1. OpenSpec and RED tests

- [x] 1.1 完成 proposal/design/spec，明确本 child 只推进 G2 umbrella 3.3
- [x] 1.2 新增 focused RED tests，覆盖 diagnostic 注入、identity/digest 绑定、assumption/provenance 传递和 `clean`/`degraded`/`not_evaluable`/`failed` 状态
- [x] 1.3 新增 RED test，证明失败 diagnostic 的 thesis/dossier 视图禁止发布数值结论

## 2. Minimal integration

- [x] 2.1 新增单一 integration adapter，使用 `validate_diagnostic_binding` 重新校验 artifact，并输出 JSON-compatible immutable view
- [x] 2.2 以 optional keyword-only 参数接入 `build_research_dossier`，保留旧调用兼容并保存 `growth_expectation_diagnostic`/`valuation_expectation`
- [x] 2.3 新增最小 `InvestmentThesis` mapping adapter，原样透传诊断身份、假设、来源、状态和失败元数据，不实现完整 8.1 interface

## 3. Verification and closure

- [x] 3.1 运行 focused tests 并完成 RED→GREEN，确认 engine/既有 dossier 行为无回归
- [x] 3.2 运行 full pytest、compileall、`openspec validate --all --strict` 和 `git diff --check`
- [x] 3.3 完成独立 child-only review，按当前 diff/代码/测试复核并修复 finding
- [x] 3.4 归档 child change，更新 G2 umbrella 3.3 勾选，提交并合入 main、push origin/main
- [x] 3.5 仅清理本 change worktree 与分支，确认根目录 WIP untouched
