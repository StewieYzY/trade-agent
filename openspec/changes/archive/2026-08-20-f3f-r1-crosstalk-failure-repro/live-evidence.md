# f3f 授权 live 复现证据

> run_id: `f3f-live-20260820-01`
> 日期：2026-08-20
> provider: `api.deepseek.com`（只记录 hostname，不记录 key/URL userinfo）
> heavy_model: `deepseek-v4-pro`
> input: insufficient-features proxy（历史 flat-features 路径的保守代理，非历史原始字节）

## 结果

5 次 R1 调用均成功：600900.SH 单 agent buffett、600519.SH 四 agent。

- `circular_reference_detected`：0 / 5
- `grounding_passed`：0 / 5（空 features 下所有数字均无法反向接地，预期结果）
- 未复现 600519 的历史 buffett→munger→duan→feng_liu→buffett 显性环形串台。
- 未复现 600900 单 agent buffett 写 `munger 看好长期价值`、`ROE 32%`、`毛利率 90%+` 的历史失败形态。

## 归因结论

- 本次 live 尝试为阴性：当前 `deepseek-v4-pro` + 当前 prompt + 空 features 代理
  没有复现历史显性串台。
- 历史失败仍可由 f3f fixture 级证据定位为 `insufficient_data → prompt 案例锚定/训练
  语料复读` 的代码路径；但当前 live 未证明该路径会在当前模型/prompt 下再次产生显性串台。
- 残余风险保持：live 证据是单次、代理输入、仅显性检测；隐性串台逃逸面与 prompt
  案例锚定设计审查仍未闭合。

## 边界

本证据不构成 G2 capability 证据，不宣称 G2 已通过，不启动 G3，也不再派生新的串台
诊断 child。下一步推进 `g2-dossier-data-quality`。
