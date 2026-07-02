# Cache 目录分裂审计（f1-deviation-fix §4.4a）

扫描目录：`/Users/admin/Documents/trade-agent/value-screener/data/cache`
带后缀目录数：4

| 带后缀目录 | 纯数字对应 | 含真实数据 | 数据文件 | 处置 |
|---|---|---|---|---|
| `000858.SZ` | `000858/` 存在 | 是 | valuation.json | 有真实数据 + 纯数字目录已存在（含 ['basic.json', 'financials.json', 'kline.json', 'risk.json', 'valuation.json']）→ 以纯数字为真值，后缀目录归档后删 |
| `002594.SZ` | `002594/` 不存在（孤儿） | 否（空壳） | 无 | 空壳 → 直接删 |
| `600519.SH` | `600519/` 存在 | 是 | valuation.json | 有真实数据 + 纯数字目录已存在（含 ['basic.json', 'financials.json', 'kline.json', 'risk.json', 'valuation.json']）→ 以纯数字为真值，后缀目录归档后删 |
| `600900.SH` | `600900/` 存在 | 否（空壳） | 无 | 空壳 → 直接删 |

## 汇总
- 空壳目录（直接删）：2 — ['002594.SZ', '600900.SH']
- 有真实数据 + 纯数字已存在（归档后删）：2 — ['000858.SZ', '600519.SH']
- 孤儿目录（含真实数据，需迁移）：0 — []