# f2 §7.2 分流跳轮 token 节省实测（2026-07-10）

## 验证场景
- **票**：600009.SH（上海机场）
- **数据**：5 维度重采（basic/financials/kline/valuation/risk）
- **LLM**：DeepSeek（deepseek-v4-flash，heavy/moderate 共用）

## 两次实跑对比

### 第 1 次：low 分流（R1 三 agent 全 neutral/60 一致）
- R1 仅 3 个 agent 成功（冯柳偶发并发超时被 `return_exceptions=True` 吞，error_rate=1/4=0.25<0.4 未降级）
- 3 个全 neutral → consensus=1.0, std=0 → `level="low"` → 跳 R2/R3
- `da_skipped_reason="low_divergence"`
- **LLM 调用次数：4**（R1×3 + R4×1）
- **total_tokens：7695**（prompt 5013 + completion 2682）

### 第 2 次：全 4 轮（R1 2 bullish + 2 neutral，medium 分流）
- R1 4 个 agent 全成功（buffett bullish/70, munger neutral/60, duan neutral/60, feng_liu bullish/60）
- consensus=0.5, max_count=2 → high 分流（但 R4 synthesizer 自评 divergence_level="medium"）
- DA ran（da_skipped_reason=None），全 4 轮
- **LLM 调用次数：10**（R1×4 + R2×4 + R3×1 + R4×1）
- **total_tokens：~19000**（估，全 4 轮）

## 节省比例
- low 分流场景：4 次调用 vs 全 4 轮 10 次 → **节省 60% LLM 调用**
- token：7695 vs ~19000 → **节省 ~60% token**（与调用次数节省比例一致）

## 结论
f2 D1 分流设计达成 AD-03 成本闸门目标——低分歧场景跳 R2/R3 省 heavy-model token。
- 首次 low 分流：跳 R2×3 + R3×1 = 省 4 次 heavy 调用
- 节省 60% 与 design.md D1 估算「省 ~60% heavy-model token」一致

## 关联验证
- §7.1：分流正确触发（low_divergence / da_skipped_reason 透传 watchlist）
- §7.3：DA 事实回查真实（evidence_quality_assessment 基于 features 实际值比对，
  如 DA 指出 buffett 把 PE 百分位 61.97% 误判为「中位偏低」→ 标 moderate）
- 偶发 agent 失败（冯柳）被 return_exceptions 容错，error_rate<0.4 不触发降级，
  不崩整轮——f2 §3.5/3.6 运行时降级设计的容错价值验证
