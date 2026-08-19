# f3c D1/D3 R1 串台根因实验报告

> 使用真实 LLM 调用；输入为由根目录 600009 cache 只读拼装并冻结的 dossier。
> 未执行 provider refresh；结论不外推为全 provider/runtime capability。

- 模式：`live`
- 输入模式：`frozen_dossier`
- source dossier sha256：`f588d5bf911aefd90348d9a7d150280847b9af938bf5b06d8548a3afeb2a00c9`
- D1 分叉：`neither`

| group | features | prompt | model | status | explicit | implicit | Jaccard | fabricated |
|---|---|---|---|---|---:|---:|---:|---:|
| group1 | sufficient | retained | weak | complete | 0.00 | 0.00 | 0.68 | 1.00 |
| group2 | missing | retained | weak | complete | 0.00 | 0.00 | 0.00 | 0.00 |
| group3 | missing | stripped | weak | complete | 0.00 | 0.00 | 0.50 | 0.25 |
| group4 | missing | retained | strong | complete | 0.00 | 0.00 | 0.83 | 0.50 |

## D3

- group2 隐性串台占比：`0.00`（4 条 R1 `core_thesis` 的规则采样）。
- 规则：core_thesis 命中「其他/另一位/共识/也看好/大家/都看好」即候选。
- >0.25 建议独立语义检测；本次判断：`字符串检测暂够用（低样本、规则级结论，不等于语义排除）`。

## 边界

prompt/model 修复不在本 change 实施。若四态为皆否，后续开独立 f3e；若为 A/B/混合，按 proposal 分叉开独立 f3d。
