# M0.3 Child-only Review

日期：2026-08-28

## 范围

本次 review 从当前 `m0-single-stock-user-review` worktree 的最终 diff、OpenSpec、M0.1/M0.2 contract 和 focused tests 重新检查。reviewer 未修改文件，未运行 provider 或真实 LLM。

## 结论

### P0

无。

### P1

无。

### P2

无阻塞 closure 的 P2。

已确认的修复包括：

- M0.2 `input_digest` 绑定当前 dossier、diagnostic artifact、身份、agent、model 和 prompt version；
- M0.2 `diagnostic_summary` 与 diagnostic 派生摘要一致，且 `agent_id` 固定为 `buffett`；
- 用户自由文本在 JSON 中原样保存，Markdown 对 LF、CRLF 和裸 CR 做结构隔离；
- M0.1/M0.2 artifact 使用 exact top-level schema，未知字段和缺字段均 fail closed；
- M0.3 构建路径不动态导入 `council.thesis_draft`、`council.debate` 或 `data.fetchers`；
- CLI 使用显式 input/output 路径，output 错误指向 `--output-dir`；
- template 使用 `capability_status=not_evidence`，completed review 使用
  `capability_status=mvp_evidence`，两者均固定 `gate_status=not_passed`；
- review record 不生成目标价、仓位、买卖或自动交易语义。

## 残余风险

- 当前只实现 review record 的工程入口和契约测试，未提供真实用户填写的 M0.1/M0.2 artifact review。
- focused、相关回归和全量测试使用 fixture/现有测试数据，不等于真实用户反馈，也不等于 G2 Capability Gate evidence。
- 未运行真实 provider/LLM；M0.3 本身不需要调用它们。
- artifact path 在生成时要求指向现存普通文件，但模块保存的是 input 中嵌入 artifact 的 digest，不会重新读取路径文件；后续归档流程仍需保留原始 artifact 文件。

本 review 只支持 M0.3 engineering closure，不表示 M0 产品闭环已因 fixture 完成，也不表示 G2 Capability Gate 通过。
