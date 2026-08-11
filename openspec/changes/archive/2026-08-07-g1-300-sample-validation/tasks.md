## 1. Contract fixtures and RED tests

- [x] 1.1 在独立于 provider 的测试 fixture 中定义 spot 形状记录、行业映射、canonical identity 和 provenance envelope，覆盖 complete、degraded、source_failed、record_not_found、invalid_value/缺失值。
- [x] 1.2 先写 selector 确定性红测：固定 seed、输入顺序变化、稳定排序、重复 ticker 去重和 strata 标签合并。
- [x] 1.3 先写行业/风险分层红测：行业配额与上限、`_unmapped`、ST、小市值、负 PE、过热风险层及不可评估原因。
- [x] 1.4 先写规模语义红测：少于 300 只不得标记 `full_market_eligible`，不少于 300 只才可使用 full-market 语义，禁止重复/无效记录凑数。
- [x] 1.5 先写 identity/provenance 红测：canonical ticker、`run_id`、`profile_version`、`input_ticker_set_hash`、`as_of`、schema version 和 fixture/reference 标识必须存在且一致；测试中断言不发生 provider/LLM 调用。

## 2. Minimal offline implementation

- [x] 2.1 新增标准库 selector/contract 模块，显式接收 spot records、industry mapping、seed/config 和运行元数据，不读取 `BasicFetcher`、全局缓存或任何 provider。
- [x] 2.2 实现输入规范化与字段状态保留：缺失/invalid 不使用零值、市场均值或其他隐式默认值；区分 `source_failed` 与 `record_not_found`。
- [x] 2.3 实现确定性行业抽样、风险 strata 抽样、标签合并、canonical ticker 去重和稳定输出排序。
- [x] 2.4 实现设计汇总：实际样本数、行业覆盖、unmapped 数量、各 strata eligible/selected/unavailable 计数与原因、状态汇总。
- [x] 2.5 实现 full-market threshold 与 fixture envelope：`sample_size >= 300` 才能解锁 full-market 语义，所有输出标记 `fixture/reference` 或 `simulated/development`。

## 3. Integration boundary and regression

- [x] 3.1 确认用户未跟踪的 `value-screener/scripts/build_validation_sample.py` 未被修改、覆盖、stage 或作为已合入基线；仅在必要时补充兼容调用说明，不改其 provider 行为。
- [x] 3.2 增加最小 reader/adapter boundary 测试，证明未来替换真实 reader 时 selector 输入/输出 contract 不变，且本 child 不写 production cache、watchlist、debate 或 live evidence 路径。
- [x] 3.3 运行 selector focused pytest 与相关 G1 contract/identity/provenance 回归测试，修复本 child 引入的回归。

## 4. Verification and scope closure

- [x] 4.1 运行 `git diff --check`，确认无 whitespace 错误和生成的 runtime 产物。
- [x] 4.2 运行适用的 `openspec validate g1-300-sample-validation --strict`（或等价严格校验），确认 proposal/design/spec/tasks 合同完整。
- [x] 4.3 记录未运行 AkShare/东财/其他 provider/LLM、未执行真实 300+ 样本、未勾选 G1 umbrella 4.1/4.2、未生成 G1 evidence bundle，并保留真实 G1 Gate 的剩余阻塞。
