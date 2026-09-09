# G1 小样本人工复核记录

- review_status: `completed`
- capability_status: `mvp_evidence`
- gate_status: `not_passed`
- 本记录保存显式人工反馈，不代表 G1 Capability Gate 通过。

## 运行身份

- run_id: `m1-2-real-five-20260908`
- profile_version: `g1-2026-07-21`
- input_ticker_set_hash: `47e8e1b3a15e`
- as_of: `2026-09-08`
- source_artifact_digest: `e685cf93e96febd9ee285ca10cfa87e6edcf6085351bcd0dd6e06910d1cf9c37`

## 逐票反馈

| ticker | dimension | status | feedback | question | issue | corrected_value | suggested_action |
|---|---|---|---|---|---|---|---|
| 002011.SZ | candidate | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 002011.SZ | inclusion_or_exclusion_reason | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 002011.SZ | scores_and_thresholds | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 002011.SZ | quality_and_data | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600104.SH | candidate | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600104.SH | inclusion_or_exclusion_reason | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600104.SH | scores_and_thresholds | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600104.SH | quality_and_data | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600600.SH | candidate | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600600.SH | inclusion_or_exclusion_reason | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600600.SH | scores_and_thresholds | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600600.SH | quality_and_data | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600676.SH | candidate | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600676.SH | inclusion_or_exclusion_reason | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600676.SH | scores_and_thresholds | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 600676.SH | quality_and_data | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 601899.SH | candidate | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 601899.SH | inclusion_or_exclusion_reason | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 601899.SH | scores_and_thresholds | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |
| 601899.SH | quality_and_data | accepted | 认可该系统结论，认为通过。 | （未填写） | （未填写） | {"status": "accepted"} | （未填写） |

## 反馈汇总

- status_counts: `{"accepted": 20, "not_evaluable": 0, "problem": 0, "question": 0}`
- dimension_status_counts: `{"candidate": {"accepted": 5, "not_evaluable": 0, "problem": 0, "question": 0}, "inclusion_or_exclusion_reason": {"accepted": 5, "not_evaluable": 0, "problem": 0, "question": 0}, "quality_and_data": {"accepted": 5, "not_evaluable": 0, "problem": 0, "question": 0}, "scores_and_thresholds": {"accepted": 5, "not_evaluable": 0, "problem": 0, "question": 0}}`

### 阈值问题

- （未填写）

### 误选

- （未填写）

### 漏选

- （未填写）

### 数据不足

- （未填写）

### 下一步建议

- （未填写）

## 限制

- 不调用 provider、LLM、Scout 或 Council。
- 不自动修改候选、筛选规则、阈值、watchlist 或 Gate verdict。
- `not_evaluable` 和空值不表示用户认可。
