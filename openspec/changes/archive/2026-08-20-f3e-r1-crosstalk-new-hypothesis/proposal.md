## Why

f3c 的 D1 live 实验使用冻结的 600009.SH dossier 完成四组、16/16 次 R1 调用，显性与隐性串台均为 0；prompt 案例剥离和 weak/heavy 模型切换都未支持 A/B 主因。下一步需要独立验证输入装配、角色分发、ticker/dossier 绑定和编排路径的新假设。

## What Changes

- 建立新的 R1 根因假设矩阵，优先区分 provider dossier、角色分发、输入绑定和编排状态问题。
- 为每次实验固定 canonical ticker、冻结 dossier、run_id、source hash、prompt/model metadata 和安全 output root。
- 记录 per-agent 原始响应、parsed output、usage、prompt/user hash 与质量指标。
- 对输入错配、dossier 缺失和 run identity 不一致执行 fail-closed。
- 不在本 change 修改主 prompt、切换模型或启动 G3。

## Capabilities

### New Capabilities

- `r1-crosstalk-new-hypothesis`: 下一轮 R1 串台根因诊断与可复核实验契约。

### Modified Capabilities

- `council-debate`: 增加实验所需的输入绑定和角色分发可观测性要求。
- `debate-quality-gate`: 增加输入一致性与检测器逃逸面的实验记录要求。

## Impact

- 主要影响 `value-screener/council/debate.py`、`council/research_dossier.py`、`council/verify_quality_gate.py` 及后续实验脚本/测试。
- 不新增依赖，不修改根目录原始 cache，不把 f3c 实验结果宣称为 G2 capability evidence。
- 起始证据：f3c 的冻结 dossier source hash `f588d5bf911aefd90348d9a7d150280847b9af938bf5b06d8548a3afeb2a00c9`。
