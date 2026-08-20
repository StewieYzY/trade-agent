## Why

f3e 在冻结的 600009.SH dossier 上未复现输入装配、角色分发、ticker/dossier/run
identity 或编排状态导致的 R1 串台，串台根因仍未闭合。G2 1.3 只允许再做一次
有界诊断：冻结并复现 600519 / 600900 历史 R1 串台失败快照，定位根因后另开
独立修复；无法复现或定位则记录残余风险并停止串台诊断循环，不再派生新的
串台诊断 child。

## What Changes

- 冻结 600519.SH（全天团环形串台）与 600900.SH（单 agent 复读茅台特征）两份
  历史失败快照，绑定 canonical ticker、run_id、历史输入 source hash 和快照
  payload hash。
- 建立最小 f3f fixture/dry-run 复现 harness：回放已记录的历史 R1 输出，用现有
  `detect_circular_reference` 确认显性串台可被识别；用现有 `_prepare_council_input`
  确认历史 `insufficient_data` 输入在当前路径下会 fail-closed，不会到达 LLM。
- 不修改主 `council/prompt.py`、`council/debate.py`，不切换模型，不启动 G3；
  无授权时不调用真实 LLM，只做 fixture 和 dry-run。
- 若定位根因，仅记录证据和建议的独立修复边界，不在本 change 实施修复。

## Capabilities

### New Capabilities

- `r1-crosstalk-failure-repro`: 冻结历史 R1 串台失败快照的可复核 fixture 复现契约。

## Impact

- 新增 `value-screener/scripts/repro_out/f3f_*` harness、fixture 快照与
  `value-screener/tests/test_f3f_failure_repro_exp.py`。
- 不新增依赖，不修改根目录原始 cache，不把 fixture 复现宣称为 G2 capability
  evidence，不把本 change 结果当作真实 LLM 复现。
