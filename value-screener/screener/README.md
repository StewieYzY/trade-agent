# L1 量化筛选模块

## 概述

L1 量化筛选采用多层过滤架构,将 L0 采集的 ~5000 只 A 股压缩至 ~200 只候选池。

## 筛选流程

```
输入: ~5000 只股票
  ↓
[H1-H8] 硬门槛 → ~1200 只
  ↓
[多因子打分] Quality + Value + Momentum → 排序
  ↓
[反价值陷阱] A1-A7 扣分 → 调整分数
  ↓
[Top-300] 按 final_score 取前 300
  ↓
[热度过滤] 排除短期过热股票 → ~200 只
  ↓
输出: S5 schema JSON
```

## 硬门槛 (Hard Gates)

H1-H8 基础财务健康度过滤:

- **H1 营收规模**: 最近一年营收 > 10 亿
- **H2 盈利能力**: 最近一年净利润 > 0
- **H3 现金流**: 最近一年经营现金流 > 0
- **H4 负债率**: 资产负债率 < 70%
- **H5 流动性**: 流动比率 > 1
- **H6 上市年限**: 上市 > 3 年
- **H7 ST/退市风险**: 排除 ST/*ST 股票
- **H8 数据完整性**: 必须有完整的 financials 数据

实现: `screener/hard_gates.py`

## 多因子打分 (Factor Scores)

三因子模型,总分 = Quality×0.4 + Value×0.4 + Momentum×0.2

### Quality (质量因子, 40%)

- **ROE (30%)**: 最近 3 年平均 ROE
  - ROE > 20%: 100 分
  - ROE 15-20%: 80 分
  - ROE 10-15%: 60 分
  - ROE 5-10%: 40 分
  - ROE < 5%: 0 分

- **FCF (40%)**: 自由现金流连续 3 年为正
  - 3 年全正: 100 分
  - 2 年正: 50 分
  - 1 年或 0 年: 0 分

- **毛利率稳定性 (30%)**: 最近 3 年毛利率标准差
  - σ < 3%: 100 分
  - σ 3-5%: 80 分
  - σ 5-8%: 60 分
  - σ > 8%: 40 分

实现: `screener/factor_scores.py::_compute_quality()`

### Value (估值因子, 40%)

- **PE 分位 (40%)**: PE-TTM 在历史 5 年分位
  - 分位 < 20%: 100 分
  - 分位 20-40%: 80 分
  - 分位 40-60%: 60 分
  - 分位 60-80%: 40 分
  - 分位 > 80%: 0 分

- **PB 分位 (30%)**: PB 在历史 5 年分位
  - 评分规则同 PE 分位

- **安全边际 (30%)**: 格雷厄姆数 / 当前股价
  - 安全边际 > 50%: 100 分
  - 安全边际 30-50%: 80 分
  - 安全边际 10-30%: 60 分
  - 安全边际 < 10%: 40 分

实现: `screener/factor_scores.py::_compute_value()`

### Momentum (动量因子, 20%)

- **60 日涨幅**: 排除短期过热
  - 涨幅 < 20%: 100 分
  - 涨幅 20-40%: 60 分
  - 涨幅 > 40%: 0 分

实现: `screener/factor_scores.py::_compute_momentum()`

## 反价值陷阱 (Anti-Trap)

在 composite 分数基础上扣分,识别价值陷阱:

- **A1 ROE 趋势下降**: ROE 3 年趋势斜率为负,扣 5-10 分
- **A2 现金流不匹配**: 净利润正但经营现金流负,扣 10 分
- **A3 应收账款异常**: 应收账款增速 > 营收增速 2 倍,扣 5 分
- **A4 商誉占比过高**: 商誉/净资产 > 30%,扣 8 分
- **A5 质押率过高**: 大股东质押 > 50%,扣 5 分
- **A6 审计意见非标**: 非标准无保留意见,扣 15 分
- **A7 频繁更换审计机构**: 3 年内更换 2 次以上,扣 5 分

实现: `screener/anti_trap.py`

## 热度过滤 (Heat Filter)

排除短期过热股票:

- **HF1 60 日涨幅 > 80 分位**: 排除
- **HF2 换手率 > 90 分位**: 排除

实现: `screener/heat_filter.py`

## 输出格式 (S5 Schema)

```json
{
  "candidates": [
    {
      "ticker": "600519",
      "name": "贵州茅台",
      "composite": 78.5,
      "anti_trap_score": 95,
      "final_score": 74.6,
      "f_score": 8,
      "pe_ttm": 38.5,
      "pb": 8.2,
      "pledge_ratio": 12.5,
      "graham_number": 1850.0
    }
  ],
  "statistics": {
    "input": 4500,
    "after_hard_gates": 1200,
    "after_anti_trap": 800,
    "after_composite_top300": 300,
    "output": 200
  }
}
```

字段说明:
- `composite`: 多因子综合分 (Quality×0.4 + Value×0.4 + Momentum×0.2)
- `anti_trap_score`: 反价值陷阱分数 (初始 100,扣分后)
- `final_score`: 最终分数 (composite × anti_trap_score / 100)
- `f_score`: Piotroski F-Score (0-9)
- `pe_ttm`: PE-TTM (估值维度)
- `pb`: PB (估值维度)
- `pledge_ratio`: 大股东质押率 (%)
- `graham_number`: 格雷厄姆数

## 使用示例

```python
from screener.hard_gates import apply_hard_gates
from screener.factor_scores import compute_composite_score
from screener.anti_trap import apply_anti_trap
from screener.heat_filter import apply_heat_filter

# 1. 硬门槛筛选
candidates = apply_hard_gates(all_stocks)

# 2. 多因子打分
scored = compute_composite_score(candidates)

# 3. 反价值陷阱扣分
adjusted = apply_anti_trap(scored)

# 4. 取 Top-300
top300 = sorted(adjusted, key=lambda x: x['final_score'], reverse=True)[:300]

# 5. 热度过滤
final = apply_heat_filter(top300)
```

## 测试

```bash
pytest value-screener/tests/test_screener.py -v
```

## 调优建议

1. **硬门槛**: 可根据市场环境调整阈值(如牛市可放宽 H1)
2. **因子权重**: Quality/Value/Momentum 权重可根据投资风格调整
3. **反价值陷阱**: A1-A7 扣分值可根据历史回测优化
4. **热度过滤**: HF1/HF2 分位阈值可根据市场活跃度调整

## 相关文档

- [L2 Scout 设计](../scout/README.md)
- [L0 数据层](../data/README.md)
