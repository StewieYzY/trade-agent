## Why

当前 L1/L2 已具备量化筛选与 LLM 初筛骨架，但真实能力仍停留在小样本可运行：排序存在量纲风险、分层采集未落实、L2 未保留全量 verdict，且尚无一次可审计的全市场能力验证。本 change 需要先定义“符合用户个人价值风格的快速筛股”究竟何时算成立，作为后续小里程碑的总验收门。

## What Changes

- 将“快”正式定义为个人价值风格筛选能力，而不是通用涨跌预测能力。
- 定义最终产品 Goal、近期能力 Gate、量化验收标准和明确 Non-Goals。
- 定义正确性、分层采集、全市场吞吐、失败隔离、成本、全量漏斗输出和用户人工复核要求。
- 明确简化 DCF 不应在量纲与假设未可靠前污染 L1 排序；是否修复或移出 L1 由后续 child change 决定。
- 规定本 umbrella change 不直接承载代码实现；后续按“排序正确性 → 分层采集 → L2 全量输出 → 规模实跑 → 产品质量复核”拆成可执行 child changes。

## Capabilities

### New Capabilities

- `personal-value-screening`: 定义按用户个人价值投资风格从全市场形成可解释候选池的能力边界、验证门与里程碑拆分规则。

### Modified Capabilities

无。本 umbrella change 不直接修改现有 `quantitative-screener` 或 `scout-agent` requirement；具体行为变更由后续 child changes 提交 delta specs。

## Impact

- 未来受影响模块：`value-screener/screener/`、`value-screener/scout/`、`value-screener/data/lib/batch_fetcher.py`、L1/L2 CLI 与漏斗分析脚本。
- 未来受影响现有 specs：`quantitative-screener`、`scout-agent`。
- 不引入新依赖，不修改当前运行时代码。
- 依赖关系：本 Goal 通过后，才进入 G2 深研能力 Gate 的正式验收。
