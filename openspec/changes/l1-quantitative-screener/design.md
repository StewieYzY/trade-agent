## Context

L0 bootstrap-data-layer 已完成（73/73 tasks，已归档至 `archive/2026-06-29-l0-bootstrap-data-layer/`），交付了完整的数据采集基础设施：
- 5 个维度 fetcher（basic/financials/kline/valuation/risk）+ 容错链
- BatchFetcher 并发采集 + CacheManager 六档 TTL
- stock_features（F-Score）+ fin_models（简化 DCF）
- industry_mapper（行业映射，STATIC 缓存 7d）
- kline 含换手率字段（L1 低热度排除所需）

L1 quantitative-screener 是 L0 的直接消费者，将 ~5000 只 A 股压缩至 ~200 只候选池。纯量化，零 LLM 调用。

**架构决策约束**（architecture-decisions.md）：
- AD-01：L1 必须独立运行，不依赖 L3
- AD-02：低热度是排除维度，不是反转因子
- AD-06：不回测，直接用学术公式
- AD-07：格雷厄姆纪律嵌入 L1（PE×PB<22.5 + 7 项指标达标率）

---

## Goals / Non-Goals

**Goals:**
- 实现三道漏斗式筛选：Hard Gates（~5000→~800）→ Factor Scores + Anti-Trap（~800→~300）→ Heat Filter（~300→~200）
- 输出排序后的候选池 JSON，供 L2 消费
- 复用 L0 全部接口，不新增数据采集逻辑
- CLI 集成：`python cli.py screen` 一键跑完全市场

**Non-Goals:**
- 不做 LLM 调用（那是 L2 的职责）
- 不做 watchlist 管理（那是 L4 的职责）
- 不做系统性回测（AD-06 明确 MVP 不做）
- 不实现 L0 缺失的字段（应收账款、上市日期、高管变动）— MVP 跳过对应因子

---

## Decisions

### D1: 模块拆分 — 四文件 + 入口

**决策**: `screener/` 目录拆为 4 个核心文件 + 1 个入口，每个文件对应一道漏斗或一类因子。

```
screener/
├── __init__.py
├── hard_gates.py        # S1: 硬门槛过滤
├── factor_scores.py     # S2: 三因子打分
├── anti_trap.py         # S3: 反价值陷阱扣分
├── heat_filter.py       # S4: 低热度排除
└── main.py              # 入口：screen_a_shares()
```

**理由**: 
- 职责单一：每个文件只做一类判断，便于测试和调优
- 可解释性：每只股票的排除/打分原因可追溯到具体模块
- 调优友好：权重/阈值集中在各模块顶部常量，不分散

**替代方案**: 
- 单文件 `screener.py` 全部逻辑 → 代码量大（~800 行），难以维护
- 按数据维度拆分（`by_basic.py`, `by_financials.py`）→ 跨维度判断（如 F-Score + ROE）会分散在多文件

### D2: Hard Gates 容错策略 — 宁可漏过不误杀

**决策**: 某维度数据缺失时，跳过该条件，不阻塞（返回 `pass: true`）。

**理由**: 
- L1 是漏斗，漏过的股票会在 L2/L3 被更严格的判断捕获
- 误杀好公司的成本 > 漏过差公司的成本（L2/L3 会兜底）
- 数据缺失是常态（尤其财报季、新股、ST 股）

**实现**: 
```python
def check_h6_pledge_ratio(risk_data: dict) -> bool:
    pledge = risk_data.get("pledge_ratio")
    if pledge is None:
        return True  # 数据缺失，跳过
    return pledge <= 70
```

### D3: Factor Scores 归一化 — 0-100 分制

**决策**: 每个子项打分到 0-100，加权求和得到 composite。

**理由**: 
- 不同子项量纲不同（F-Score 0-9、ROE 百分比、PB 倍数），需要归一化
- 0-100 分制直观，便于 L2/L3 消费和前端展示
- 权重调整只需改顶部常量，不影响子项计算

**替代方案**: 
- Z-score 标准化 → 需要全市场统计，增加复杂度
- 排名百分位 → 需要全市场排序，不利于增量更新

### D4: Anti-Trap 是扣分不是排除

**决策**: 反陷阱因子在 Factor Scores 基础上追加扣分，不直接排除股票。

**理由**: 
- 反陷阱因子多数是"红旗"而非"死刑"（如 ROE 下降可能是周期性）
- 扣分保留可解释性：每只股票附带 `anti_trap_flags` 清单，L2/L3 可参考
- 直接排除会误杀（如茅台 2013-2014 年 ROE 下降，但后来反转）

**实现**: 
```python
# anti_trap.py
def compute_anti_trap(ticker_data: dict) -> dict:
    score = 100  # 初始满分
    flags = []
    
    # A1: ROE 3 年趋势下降
    roe_trend = compute_roe_trend(ticker_data["financials"])
    if roe_trend < 0:
        deduction = min(abs(roe_trend) * 2, 10)  # 每降 1 年扣 2 分，封顶 10 分
        score -= deduction
        flags.append(f"ROE declining ({roe_trend:.1f} years)")
    
    return {"score": max(0, score), "flags": flags}
```

**排序公式**: 
```
adjusted_composite = factor_scores.composite × (anti_trap.score / 100)
```
乘法而非减法——高质量股受同等扣分惩罚的绝对影响更大，符合投资逻辑。`adjusted_composite` 是实际排序键，输出到 S5 schema 保证透明度。

**H7 vs A6 分层设计**:
- **H7（hard gate）**: 白名单排除最严重的 3 类非标意见（保留意见/无法表示意见/否定意见）——死刑级，直接淘汰
- **A6（anti-trap）**: 黑名单扣任何非「标准无保留意见」——更宽泛，扣分但不排除
- 两者不是重复，而是不同严格度的分层：一份「带强调事项段的无保留意见」不应直接排除（H7），但值得扣分（A6）

### D5: Heat Filter 在 Factor Scores 之后执行

**决策**: 先用三因子 + 反陷阱排序取 top 300，再对 top 300 做低热度排除。

**理由**: 
- 低热度是防御性排除（AD-02），不是核心筛选逻辑
- 先排序再排除，保留可解释性：被排除的股票仍可查看其 factor_scores
- 减少计算量：只需对 top 300 计算换手率分位和涨幅，而非全市场 ~800 只

**替代方案**: 
- 在 Hard Gates 之后立即做 Heat Filter → 会排除掉"热度高但质量好"的股票（如茅台）
- 对所有 ~800 只都做 Heat Filter → 计算量大，且低质量股票排除后仍会被 Factor Scores 淘汰

### D6: 格雷厄姆 7 项指标达标率 — MVP 部分实现

**决策**: AD-07 要求嵌入格雷厄姆 7 项指标达标率，但 L0 数据不完整，MVP 先实现 4 项，其余跳过。

**格雷厄姆 7 项**:
1. ✅ 充足规模（市值 > 50 亿）— Hard Gate H3
2. ⚠️ 财务状况稳健（流动比率 > 2）— 需 L0 financials 补充 current_ratio 派生，MVP 跳过
3. ✅ 盈利稳定（近 10 年每年盈利）— F-Score F1（ROA > 0）近似
4. ✅ 股息记录（连续 20 年分红）— L0 未采集股息率，MVP 跳过
5. ✅ 盈利增长（近 10 年 EPS 增长 1/3）— F-Score F3（ROA 上升）近似
6. ✅ 适度 PE（PE×PB < 22.5）— 估值因子子项
7. ⚠️ 适度 PB（PB < 1.5）— 估值因子子项（PB < 2 得满分，1.5 是格雷厄姆原版）

**实现**: 在估值因子中嵌入 PE×PB < 22.5 和 PB < 2，其余项通过 F-Score 近似覆盖。

---

## Risks / Trade-offs

### R1: 财报数据延迟/缺失 → 质量因子失效

**风险**: financials 数据缺失（财报季、新股、ST 股）导致 F-Score/ROE/现金流无法计算，质量因子（50% 权重）失效。

**缓解**: 
- L0 已实现财报缓存 + 按季调度（CacheManager QUARTERLY TTL=24h）
- L1 对缺失字段做降级：跳过该子项，不阻塞整体打分
- 降级后 composite 分数会偏低，自然排在后面

**实现**:
```python
def compute_quality_score(ticker_data: dict) -> float:
    scores = []
    financials = ticker_data.get("financials", {})
    
    # F-Score（40%）— 先检查 financials 是否有有效数据
    if financials and (financials.get("income", {}).get("net_profit")
                       or financials.get("balance_sheet", {}).get("TOTAL_ASSETS")
                       or financials.get("cash_flow", {}).get("NETCASH_OPERATE")):
        f_score = compute_f_score(financials)
        scores.append(("f_score", f_score / 9 * 100, 0.40))
    
    # ROE 5 年平均（30%）
    roe_avg = compute_roe_5y_avg(financials)
    if roe_avg is not None:
        scores.append(("roe_avg", min(100, roe_avg / 15 * 100), 0.30))
    
    # 经营现金流连续 3 年正（30%）
    ccf_positive = compute_cash_flow_positive_years(financials)
    if ccf_positive is not None:
        scores.append(("cash_flow", ccf_positive / 3 * 100, 0.30))
    
    if not scores:
        return 0.0  # 全缺失，质量分 0
    
    # 加权求和（仅对有数据的子项）
    total_weight = sum(w for _, _, w in scores)
    return sum(s * w / total_weight for _, s, w in scores)
```

### R2: 权重设置不合理 → 排序偏差

**风险**: 初始权重 50/30/20 可能不符合实际投资逻辑，导致"便宜但烂"的公司排名靠前。

**缓解**: 
- 权重集中在 `factor_scores.py` 顶部常量，便于调整
- 跑几轮后根据 L2 否决率和 L3 共识调整（total-design §4.8）
- 输出包含子项分数，便于诊断（如 L2 经常否决 L1 top 候选 → 检查质量因子权重）

### R3: 反陷阱因子误杀 → 漏掉好公司

**风险**: 反陷阱因子（如 ROE 下降、应收账款增速）可能误杀周期性好公司（如茅台 2013-2014）。

**缓解**: 
- 反陷阱是扣分不是排除，保留可解释性
- 每只股票附带 `anti_trap_flags` 清单，L2/L3 可参考
- 扣分幅度保守（每项 2-15 分，总分 100），不会一次性扣到 0

### R4: 行业分类不准 → 行业中位 PE 计算偏差

**风险**: industry_mapper 可能分类错误（如把"消费电子"分到"半导体"），导致行业中位 PE 计算偏差。

**缓解**: 
- L0 industry_mapper 使用东财行业板块（~70 个），分类质量较高
- STATIC TTL=7d，定期更新
- 行业中位 PE 仅作为估值锚，不直接排除股票，偏差影响有限

### R5: L0 缺失字段 → 部分因子无法实现

**风险**: L0 未采集应收账款、上市日期、高管变动数据，导致反陷阱 A3/A7 和 Hard Gate H2 无法实现。

**缓解**: 
- MVP 跳过对应因子（A3/A7/H2），在 specs 中标注"待 L0 补充"
- 跳过的因子不影响核心逻辑（F-Score + ROE + 现金流 + 估值 + 安全边际）
- 后续 L0 补充字段后，L1 可直接启用对应因子

---

## Open Questions

### Q1: Hard Gate H2（上市 < 3 年）如何实现？

**问题**: L0 basic.py 未采集 `list_date`（上市日期），无法判断上市年限。

**选项**:
1. L0 basic.py 补充 `list_date` 字段（从 `stock_individual_info_em` 或 `stock_info_a_code_name` 派生）
2. 跳过 H2，MVP 不排除新股
3. 用 financials 的 `years` 字段近似：`len(years) < 3` 表示财务历史不足

**建议**: 选项 3（用 financials years 近似），无需改 L0，精度可接受。

### Q2: 股息率 > 2% 是否实现？

**问题**: total-design §4.2 提及股息率作为估值因子子项，但 L0 未采集股息率数据。

**选项**:
1. L0 basic.py 补充股息率字段（从 `stock_individual_spot_xq` 雪球接口）
2. 跳过股息率，MVP 仅用 PE/PB/格雷厄姆数
3. 用 financials 的净利润 + 市值近似股息率（需假设分红比例）

**建议**: 选项 2（跳过），MVP 聚焦核心因子，股息率作为后续增强。

### Q3: 周期股排除是否启用？

**问题**: total-design §4.2 提及"剔周期股（可选）"，但周期股定义模糊（钢铁/煤炭/航运/化工/水泥/养殖）。

**选项**:
1. 启用：Hard Gate H5 排除指定行业
2. 不启用：周期股仍进入候选池，由 L2/L3 判断
3. 可配置：CLI 参数 `--exclude-cyclicals` 控制

**建议**: 选项 3（可配置），默认不启用，用户可按需开启。

---

## Migration Plan

无数据迁移。L1 是新增模块，不影响 L0 或后续 change。

**部署步骤**:
1. 创建 `screener/` 目录 + 4 个核心文件
2. 实现 `screener/main.py` 入口 + CLI 集成
3. 测试：`python cli.py screen --debug` 输出中间步骤
4. 验证：候选池 ~200 只，按 composite 排序，JSON 格式正确

**回滚策略**: 删除 `screener/` 目录即可，不影响 L0。
