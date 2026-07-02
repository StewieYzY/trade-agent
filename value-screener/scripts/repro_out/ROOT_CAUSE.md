# P0 根因判定（f1-deviation-fix §1.2 / D1）

> 实验时间：2026-07-02，`scripts/repro_features.py` 输出。

## 结论

**根因在代码层 guard 逻辑，走 §2（D2）修复。** 但现实复现的触发路径比 design 原假设更精确——是 **basic 维度过期（2h TTL）触发 `critical_fields` 缺失**，而非 design 原假设的 "financials 过期、basic 命中、缺失率 <50% 放行"。

## 实验数据

| ticker | basic (2h TTL) | financials (24h TTL) | 触发路径 | financials_floor 现状 |
|---|---|---|---|---|
| 600519 | 过期（age 21.65h）→ `name`/`market_cap` None | **新鲜**（age 21.65h < 24h） | `missing_critical` 命中（name/market_cap 缺）→ guard fail | 三件套**实际有数据**，但被 critical 维度先拦下 |
| 600900 | 过期（age 48h） | 过期（age 48h） | 整盘过期，`missing_critical` + `missing_ratio>0.5` 双触发 | 三件套全 None |
| 600009 | 过期（age 21.54h） | 新鲜（age 21.54h < 24h） | `missing_critical` 命中 → guard fail | 三件套**实际有数据** |

> 关键事实：`basic` 维度 TTL = 2h（`DAILY`），比 `financials` 的 24h（`QUARTERLY`）短得多。因此实跑中 basic 先过期，`critical_fields=["name","market_cap"]` 命中后 guard 已经 fail-fast——**design 原假设的"basic 命中、financials 过期、缺失率 <50% 放行"漏洞在当前 TTL 配置下未必能稳定复现**（要复现需 basic 在 2h 内新鲜、financials 超 24h 过期，窗口窄）。

## 对 §2（D2）的影响

**D2 guard 加固仍有价值，但定位更准**：
1. design 假设的漏洞路径（financials 全 None 但整体缺失率 <50% 放行）是**潜在路径**，需 basic 维度恰好新鲜才触发——现实中 basic 2h TTL 让它更早被 critical 维度兜住，但**不能依赖这个巧合**（basic TTL 一旦调长、或某次 fetch 只补了 basic 没补 financials，漏洞立刻复现）。
2. `financials_floor` 硬门槛的价值是**堵住"basic 命中但 financials 维度缺失"的潜在路径**，让财务三件套缺失时**独立**于 critical_fields / missing_ratio 直接 fail-fast——这是更精确的兜底，不依赖 TTL 配置的巧合。
3. 600519/600009 的 financials_floor 当前其实有数据（financials 维度新鲜），所以 §2 修复后这两只票若先跑 `batch` 补齐 basic，features 会齐全、能正常进入 LLM——**与 600009 历史上真实完整产出（core_thesis 引用 PE_TTM 26.42）一致**。

## 模型层（D4）判定

**不触发 D4**：本次实验没有出现"features 齐全但模型仍输出幻觉"的情况——所有 insufficient 都是 cache 过期导致的数据真缺失，不是模型编造。§3（D4 衍生 change）**不执行**，但 §6 质量门的"反向特征校验 + 环形引用检测"作为防御层仍然落地（G4 独立于根因判定）。

## 与 design §1.3 三假设的最终对照

| 假设 | design 核查结论 | 实验验证 |
|---|---|---|
| ① prompt 模板含示例被复读 | 排除（无占位文本） | 排除（未触及） |
| ② features 注入空/错 | 升为主因嫌疑 | **确认**——features 确实因 cache TTL 过期而缺关键字段，guard 已 fail-fast；但 design 推断的"缺失率 <50% 放行"具体路径未稳定复现（被 critical_fields 2h TTL 提前兜住） |
| ③ LLM 响应缓存 | 排除（无 cache） | 排除（未触及） |

## 下一步

走 §2（D2）：在 `scout/input_assembly.py` guard 段新增 `financials_floor = ["pe_ttm","roe_3y","net_margin"]` 硬门槛，TDD 实现。§3 不执行。
