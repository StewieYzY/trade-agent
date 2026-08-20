# f3f live LLM 最终复现报告

## 边界
- 这是授权后的受控 live R1 调用，使用当前 prompt builder + insufficient-features 代理。
- 不修改主 prompt/debate，不调用 provider 数据源，不宣称 G2 capability passed。
- provider: api.deepseek.com
- heavy_model: deepseek-v4-pro
- run_id: f3f-live-20260820-01

## 输入边界
insufficient-features proxy for historical flat-features path

## 结果
### 600900.SH
- buffett: circular=False grounding=False parse=ok
### 600519.SH
- buffett: circular=False grounding=False parse=ok
- munger: circular=False grounding=False parse=ok
- duan: circular=False grounding=False parse=ok
- feng_liu: circular=False grounding=False parse=ok
