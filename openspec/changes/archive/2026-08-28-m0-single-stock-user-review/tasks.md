## 1. Contract fixtures and RED tests

- [x] 1.1 在 `tests/test_m0_single_stock_user_review.py` 复用 M0.1/M0.2 fixture 形状，构造包含两份 artifact、dossier、artifact 路径和 `user_review` 的 `m0-single-stock-user-review-input-v1` envelope。
- [x] 1.2 先写 RED 测试：有效的 completed review 必须覆盖 facts、assumptions、growth_expectation、thesis_draft 四个维度，并原样保存用户状态、反馈、问题/修正和无法判断原因。
- [x] 1.3 先写 RED 测试：not_evaluable 缺少原因、completed 缺少 next_decision、未知字段、身份错配或任一 digest 篡改必须在 output directory 创建前失败。
- [x] 1.4 先写 RED 测试：template 输出必须为 `capability_status=not_evidence`；completed 输出必须为 `mvp_evidence`；两者均为 `gate_status=not_passed`，且不生成交易字段。
- [x] 1.5 先写 RED 测试：相同 input 在不同 output directory 生成完全一致的 JSON/Markdown，并保存两份 artifact 的路径、digest 和 identity。
- [x] 1.6 先写 RED 测试：CLI 只接受显式 `--input`/`--output-dir`，缺失或无效 input 返回参数错误且不创建 output directory；测试不发生 provider/LLM 调用。

## 2. Minimal offline review implementation

- [x] 2.1 新增 `council/user_review.py`，定义版本化 input、dimension、review record 和 artifact result 数据结构，所有字段使用标准库并保持严格 JSON 约束。
- [x] 2.2 实现 input validator：复用 M0.1 `validate_frozen_growth_diagnostic_artifact`，并用纯 Python contract 校验 M0.2 Thesis draft，校验顶层 identity、两份 artifact digest、diagnostic digest、artifact 相互一致性、dossier-bound input digest、dossier ticker 和 artifact path。
- [x] 2.3 实现用户反馈 validator：固定四维和四态，校验字符串/列表类型、`not_evaluable` 原因规则、completed 的关键问题/认可内容/residual risk/下一步决策，并禁止结构化交易决策字段。
- [x] 2.4 实现 deterministic JSON renderer、Markdown renderer 和 output-directory 校验；固定 `<ticker>-<run_id>.json/.md` 文件名，使用严格 JSON、稳定键序和原子写入。
- [x] 2.5 实现 `build_user_review_record` / `write_user_review_record` / `validate_user_review_record` 公共入口，确保 template 与 completed 的 capability status 分离且不改变输入 artifact。

## 3. CLI and focused regression

- [x] 3.1 在 `value-screener/cli.py` 增加 `single-stock-user-review` 命令，只读取显式 input 文件并调用离线 review 模块，不导入或初始化 provider/LLM/Council/DA/Synthesizer。
- [x] 3.2 运行 `tests/test_m0_single_stock_user_review.py` 的 RED→GREEN focused 测试，修复本 child 引入的失败，确认 JSON/Markdown 与 CLI 行为稳定。
- [x] 3.3 运行 M0.1/M0.2 直接相关回归：`tests/test_m0_single_stock_user_review.py`、`tests/test_m0_strong_agent_thesis_draft.py`、`tests/test_m0_frozen_input_growth_diagnostic.py`。

## 4. Verification and scope closure

- [x] 4.1 运行 `python -m compileall -q .`、`git diff --check` 和 `openspec validate m0-single-stock-user-review --strict`。
- [x] 4.2 运行全量 pytest，记录实际通过/跳过数量；确认没有 npm lint script，不声称存在 `npm run lint`。
- [x] 4.3 做一次 fresh child-only review，检查 identity/digest 绑定、四维用户输入、template/evidence 边界、无 provider/LLM side effect、无交易语义和输出目录隔离；记录 `P0/P1/P2/残余风险`。
- [x] 4.4 修复 review findings 后重新运行 focused、相关回归、全量 pytest、compileall、OpenSpec strict 和 diff check，确认根目录 WIP 未被纳入 child diff。
- [x] 4.5 归档 M0.3 OpenSpec，提交并合入 `main`、push `origin/main`，清理仅本 child 的 branch/worktree；若没有真实用户 feedback artifact，明确保留 `capability_status=not_evidence` 与 `M0 product loop=pending user review`。
