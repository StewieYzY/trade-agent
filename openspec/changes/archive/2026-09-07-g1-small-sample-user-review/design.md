## Context

本 child 隶属 Goal G1、Milestone M1.3，承接已归档的 `g1-mvp-small-sample-run`（M1.2）。M1.2 输出是确定性的离线 fixture/reference 结果，包含运行身份、provenance、汇总和按 canonical ticker 排序的逐票筛选结果。M0.3 已证明人工复核需要保留用户原文、明确区分 template 与 completed，并使用确定性 Markdown renderer；但 M1.3 的输入是一批股票筛选结果，不是单股 dossier/Thesis，不能直接复用 M0.3 的输入契约。

本设计遵守 G1 umbrella、AD-10 的 child change 治理，以及项目的工程闭环/能力 Gate 分离规则。M1.3 只完成离线人工复核工程入口；没有真实用户填写时不得生成 `mvp_evidence`，更不得宣称 M1 完成或 G1 Capability Gate 通过。

## Goals / Non-Goals

**Goals:**

- 只接受 M1.2 `g1-small-sample-run/v1` 的 fixture/reference、simulated/development JSON 产物。
- 重新校验 M1.2 顶层 identity、provenance、canonical ticker 集合和逐票结果结构；可选 Markdown 必须与同一 run identity 对齐。
- 生成默认的 `template/not_evidence` 记录，以及在调用方显式提供完整人工反馈时生成 `completed/mvp_evidence` 记录。
- 每只股票固定输出四个复核维度，每个维度支持四种状态，保留 feedback、question/issue、可选 corrected_value/suggested_action 的原始值。
- 汇总反馈状态、问题分类、阈值问题、误选、漏选、数据不足和下一步建议，按 canonical ticker 稳定排序。
- 以安全 run-scoped 文件名写入显式输出目录，阻止生产目录和不同内容覆盖。

**Non-Goals:**

- 不重新运行 M1.2，不调用 provider、LLM、Scout、Council 或任何网络服务。
- 不修改 `hard_gates.py`、`factor_scores.py`、`anti_trap.py`、`heat_filter.py`、M1.2 runner 或 G1 阈值。
- 不自动根据反馈重写规则，不做全市场/300+ 样本，不生成 G1 Capability Gate evidence。
- 不实现前端、M2、G3 holding runtime、watchlist manager 或新的依赖。

## Decisions

### D1：复核核心只消费已生成的 M1.2 artifact

新增独立模块 `council/small_sample_user_review.py`，提供纯本地函数：

- `build_small_sample_user_review_record(m1_result, reviews=None, *, markdown_path=None)`：校验 M1.2 结果并构造记录；`reviews=None` 生成 template。
- `write_small_sample_user_review_record(m1_result, output_dir, reviews=None, *, markdown_path=None)`：安全写入两个 run-scoped artifact。
- `render_small_sample_user_review_json(record)` 与 `render_small_sample_user_review_markdown(record)`：只做确定性序列化/展示。
- `validate_small_sample_user_review_record(record)`：校验输出 digest 与结构，防止篡改。

核心模块不导入 `council.debate`、`council.llm` 或 provider fetcher。这样可以把“用户对已有筛选结果的判断”和“重新运行筛选/辩论”保持在不同边界。

### D2：M1.2 identity 与输入结构 fail-closed

M1.2 输入顶层允许字段固定为 `schema_version`、`artifact_type`、`mode`、`capability_status`、`gate_status`、`run_id`、`profile_version`、`input_ticker_set_hash`、`as_of`、`provenance`、`summary`、`tickers`、`staged_evidence`。除这些字段外拒绝未知结构；逐票结构和四个阶段状态也做白名单校验。

重新用 `canonical_ticker` 和 `compute_input_ticker_set_hash` 计算集合 hash，拒绝重复 canonical ticker 的冲突数据、ticker 列表与逐票结果不一致、digest/identity 不一致、live/provider/production provenance，以及可选 Markdown 中不一致的 `run_id`、profile、hash、as_of 或状态标记。对 M1.2 本身没有 digest 字段的情况，记录确定性 `source_artifact_digest`，供复核记录绑定和后续校验。

### D3：反馈 schema 以“逐票 × 复核维度”为最小单位

四个固定维度分别代表候选认可、通过/排除理由、分数/阈值解释、质量/数据不足。每项结构固定包含：

```text
status: accepted | question | problem | not_evaluable
feedback: 原文字符串
question: 原文字符串
issue: 原文字符串
corrected_value: 任意严格 JSON 值或 null
suggested_action: 原文字符串
```

template 为每个字段生成空值和 `not_evaluable`，不能把空值解释为 accepted。completed 只允许显式传入所有 ticker 和维度的反馈；反馈文本按输入原样保存，Markdown 用 HTML escaping 和 `<pre>`/显式换行表达，避免 `|`、换行、反引号或空值破坏表格。

### D4：问题汇总只聚合，不推断或改规则

记录包含 `feedback_summary`，按 `question`、`problem`、`not_evaluable` 及显式 `category` 聚合计数/引用 ticker。调用方可显式提供 `threshold_issues`、`false_positive_tickers`、`false_negative_tickers`、`data_insufficiency`、`next_steps`；模块只做结构校验、canonicalize 和稳定排序，不从反馈自动改变筛选阈值或候选状态。缺少这些字段时保持空数组/空文本。

### D5：输出目录和覆盖规则复用生产路径边界

`write_small_sample_user_review_record` 先校验所有输入，再调用 `validate_g1_output_root`；因此失败不会创建输出目录。输出固定为 `<run_id>-review.json` 和 `<run_id>-review.md`。目标文件不存在时原子写入；已存在且内容相同则幂等成功，内容不同则抛错并保留原文件。不同 run_id 使用不同安全文件名，不写入 M1.2 的生产/证据目录。

## Risks / Trade-offs

- **[Risk] M1.2 结构未来演进导致复核器拒绝输入** → 固定 schema version 和白名单；新结构另开兼容性 change，不静默猜测。
- **[Risk] template 被误认为真实用户反馈** → 输出固定 `review_status=template`、`capability_status=not_evidence`，Markdown 明示 pending user review。
- **[Risk] 用户输入中的 Markdown 控制字符破坏可读性** → 原文存 JSON，Markdown 使用 HTML escaping、`<pre>` 和表格 cell escaping。
- **[Risk] 复核反馈改变候选判断** → 复核记录只保存判断和建议，不回写筛选器、阈值或 M1.2 artifact。
- **[Risk] 输出目录与生产目录重叠** → 在任何 mkdir/write 前复用 `validate_g1_output_root` 做 fail-closed 检查。

## Migration Plan

1. 在独立 worktree 中创建本 child OpenSpec artifacts。
2. 先写 M1.3 focused RED tests，验证合法 template、四维反馈、fail-closed、确定性 renderer、目录隔离与零外部调用。
3. 实现核心校验/构造/renderer/原子写入，再接入 CLI。
4. 运行 focused、M1.2/M0.3 相关回归、全量 pytest、compileall、CLI help、OpenSpec strict 和 diff check。
5. 完成独立 child-only review 后归档、合入 main、push `origin/main`，重新执行 merged-main 验证并清理 child branch/worktree；状态保持 `engineering_status=merged`、`capability_status=not_evidence`、`gate_status=not_passed`，M0.3 real user review 仍 pending。

## Open Questions

- 真实用户如何选择并填写逐票反馈，留给 M1.3 产物消费阶段；本 child 只提供可填写 contract 和 template。
- M1.2 未来是否增加原生 artifact digest，留给 M1.2 独立兼容性 change；本 child 以当前字段重算 source digest。
