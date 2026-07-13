# f3-l3-research-dossier Explore 探索文档

> 状态：explore 阶段（未 propose change）
> 创建：2026-07-10
> 承接：f2-debate-protocol-fix 已归档，f2 留的 `new_evidence`/`evidence_exhausted` 字段是 f3 的 enabling carrier（D2 soft→hard gate 的升级锚点）

## 一、问题根因（f2 未解决的部分）

f2 优化了辩论**过程**（分流/降级/分歧报告/DA 事实回查），但没动辩论**信息基础**。实证（600009.SH）：

- L3 输入仅 **21 个纯量化扁平字段**（`scout/input_assembly.py::assemble_snapshot`）
- R1 四 agent 引用数据点**完全同源**（PE 25.71 / ROE 2.22%→4.75% / 60日跌15.86% / 净利率15.86% / F-score），零信息不对称
- 真正提供增量的是 DA 从训练知识里「编」的资本开支/扣点率（不受校验）

**根因**：天团看到同一份数据，辩论没有信息不对称的来源。f3 要解决这个根因。

## 二、核心思路

**f3 不只是「加字段」，而是「按 agent 分发不同维度」制造信息不对称**。

关键判断：如果把 60+ 字段全塞给所有 agent，prompt 膨胀 + token 上升，且 agent 仍然「看到同样的东西只是更多了」——同质化不解决。真正的解法是信息不对称：巴菲特看护城河、芒格看治理、段永平看商业模式、冯柳看赔率。每人看的维度不同，R1 才有真实分歧基础。

但**完全割裂**（每 agent 只看自己维度）太激进——R2 互相质疑时缺少共同事实地基。所以用「**公共底座 + 角色侧重**」：21 量化字段全员共享 + 定性维度按角色分发。

## 三、可行性结论（Explore agent 已验证）

**中强可行**：6 类定性维度的 akshare 接口已存在且 uzi-skill 实战验证过，可直接移植 fetcher **无需换源**。

| 维度 | akshare 接口 | 数据源类型 | f3a 是否做 |
|---|---|---|---|
| 主营构成 | `stock_zygc_em` + `stock_zyjs_ths` | akshare | ✅ f3a 优先级1 |
| 竞品对比 | `stock_board_industry_cons_em`（依赖 industry） | akshare | ✅ f3a 优先级2 |
| 资本开支代理 | `financials.cash_flow.CONSTRUCT_LONG_ASSET`（**已采**） | 零成本接入 | ✅ f3a 优先级3 |
| 研报共识 | `stock_research_report_em` | akshare | ✅ f3a 优先级4 |
| 高管增减持 | `stock_ggcg_em`（全市场表） | akshare | ⏳ f3b |
| 限售解禁 | `stock_restricted_release_summary_em` | akshare | ⏳ f3b |
| 实控人 | akshare 无 | 需 web 换源 | ❌ 砍 |
| 在建工程明细 | akshare 无 | 需 PDF 解析 | ❌ 砍 |
| 行业ROE/增速 | akshare 无结构化 | 需 web/硬编码 | ❌ 砍 |

**最大风险**：小票研报覆盖（<50亿市值常返 0）+ cninfo 公告接口翻页灾难（若 f3b 做事件必须复刻 uzi 直连 HTTP，不能调 akshare 包装函数）。

## 四、架构基线（已定决策固化）

### 4.1 数据层（f3a 新建 3 fetcher + 1 已采字段接入，按优先级）

1. **fetch_main_business.py**（新建）— 主营构成，分产品/分行业/分地区营收占比
2. **fetch_peers.py**（新建）— 竞品对比，peer_avg_pe/行业排名（依赖 industry 字段）
3. **资本开支代理**（已采接入，零成本）— 由 `research_dossier` 读已采的 `CONSTRUCT_LONG_ASSET`，`input_assembly` 不动
4. **fetch_research.py**（新建）— 研报共识，consensus_eps/target_price/buy_rating_pct/coverage_count

cache 策略：全市场表走 `_LazyTable` intra-batch 复用（f1 已有模式，防封禁）。

### 4.2 组装层

**新建 `council/research_dossier.py`**（不污染 L2 快管线）：

```python
def build_research_dossier(symbol: str, core_snapshot: dict | None = None) -> dict:
    """组装 L3 专用分层研究档案.
    core_snapshot 缺省时调 assemble_snapshot 采集（复用，不重复采）。
    返回分层 dossier。
    """
```

**分层 fail-fast**（用户决策：门槛压窄）：
- `core_snapshot` + `main_business` 缺失 → **fail-fast**（核心，无这两样不深研）
- `peers` / `research` / `capex_proxy` 缺失 → **降级标注**（不阻断）

返回结构：
```python
{
  "core_snapshot": {...21 量化字段...},        # 全员共享
  "research_dossier": {                         # 角色分发
    "main_business": {...分产品/行业/地区...},
    "peers": {...peer_avg_pe, 行业排名...},
    "capex_proxy": {...CONSTRUCT_LONG_ASSET...},
    "research": {...consensus_eps, target_price...},
    "degraded_fields": [...缺失的降级维度名...],
  }
}
```

`assemble_snapshot`（scout 层扁平 21 字段）**保持不变**，L2 不受影响。

**衔接 `run_debate`**：`council/debate.py::run_debate` 当前 `features = assemble_council_features(ticker)`（debate.py:502-503）。f3a 改为调 `build_research_dossier(ticker)` 返回分层 dossier，`assemble_council_features` 退居为 dossier 内部 `core_snapshot` 的来源。`call_agent` / `_call_da` / `_call_synthesizer` 的 `features` 形参语义从「扁平 21 字段」变为「分层 dossier」。capex_proxy 由 dossier 读取，`input_assembly` 完全不动（不污染 L2 快管线）。

### 4.3 分发层（公共底座 + 角色侧重）

| agent | 角色侧重维度 | 核心看 |
|---|---|---|
| 巴菲特 | 主营构成 + 竞品 + 资本开支代理 | 生意质量、护城河、长期再投资 |
| 芒格 | 主营构成 + 竞品 + 治理/风险 | 商业模式脆弱点、管理层、反身性风险 |
| 段永平 | 主营构成 + 竞品 + 研报共识 | 用户价值、商业模式简单可靠、市场共识是否误判 |
| 冯柳 | 研报共识 + 资本开支代理 + 解禁/事件压力 | 预期差、赔率、反对意见、边际变化 |
| DA / Synthesizer | 全量 | 仲裁要全知 |

**代码级约定（P1，f3a 落地必做）**：当前 `_build_user_message(ticker, features, other_opinions)`（debate.py:69）对所有 agent 生成**完全相同**的 user message——同一份 features JSON，无 `agent_id` 入参。「角色分发」若只停在 prompt 层，f3a 的核心假设「分发制造信息不对称」无法落地也无法验证。f3a 改：
- `_build_user_message` 增加 `agent_id` 形参，按 agent_id 从 dossier 的 `research_dossier` 取角色侧重子集（`core_snapshot` 全员共享，定性维度按 §4.3 表分发）
- `call_agent`（debate.py:27）透传 `agent_id` 给 `_build_user_message`
- `_call_da` / `_call_synthesizer` 走**全量**路径（DA/Synthesizer 须全知，不分发），与 agent 分发路径区分

**注**：芒格的「治理/风险」、冯柳的「解禁/事件压力」在 f3a 的处理见 §五（待定）。

### 4.4 Prompt 层

**物理分区**（用户决策）：
- 「公司事实特征」段：财务/主营/竞品
- 「市场共识/外部预期」段：研报（单独成段，不混进公司事实）
- 研报引用须写明「市场预期认为……」，不当事实（像 Kimi 处理赔率：研究变量不是预测依据）

### 4.5 衔接 f2

- **D2 soft→hard gate**：f3a 落地后 **保持 soft**（不立刻升 hard）。理由：f3a 只是最小闭环，peers/research 覆盖率未知（小票研报常返 0、industry 缺失致 peers 降级），贸然升 hard 会重演 f2 的「编造-校验-拦截」死循环。升 hard 的门：A/B 验证定性维度覆盖率稳定（建议连续 N 只票 peers/research 命中率 ≥ 阈值）后，**独立 change** 升 hard（一行改动，见记忆 f2-d2-downgrade-and-f3-line）。
- **D3 DA 事实回查扩展为 f3a 同步项**：f2 时 D3 只能回查量化指标真假（features 仅 21 量化字段）。f3a 有了定性维度，但 DA 数字真假校验实际走 `verify_r1_feature_grounding`（verify_quality_gate.py:31），而 `verify_da_fact_check`（:170）只校验 `evidence_quality_assessment` 结构 + `recommendation` 引用合法性，**不回查具体数字**。f3a 要把 DA 回查能力真正扩展到定性维度，需同步改 DA 校验路径（见 §4.6 质量门嵌套兼容）。
- **D1 分流阈值实测校准**：agent 看不同维度可能更频繁触发 high/extreme 分流，需实测调阈值

### 4.6 验证

600009.SH **A/B 对比** f2 输出：
- A：f2 产出（4 agent 引用全同源 PE/ROE/跌幅/F-score）
- B：f3a 产出
- 判据：
  - **定性**：R1 引用数据分布是否分化（不再全同源），且有真实信息增量（非编造）
  - **定量（必补，防自欺）**：四 agent R1 引用数据点集合的 **Jaccard 距离**（1 - |交集|/|并集|），f2 基线应 ≈0（全同源），f3a 期望显著 >0；或统计「不同源数据点占比」。仅有定性判据易重蹈 f2 同质化 bug 覆辙（看起来分化实则同源）

**质量门嵌套兼容（P1，f3a 落地必做）**：当前 `verify_r1_feature_grounding`（verify_quality_gate.py:49-55）和 `verify_r2_new_evidence`（:110-117）收集 `feature_numbers` 时只遍历**顶层标量 + 顶层 list 里的标量**，`dict` 值直接跳过。f3 dossier 的 `research_dossier` 是嵌套 dict（§4.2 返回结构），其中 `peer_avg_pe`/`consensus_eps`/`target_price` 等数字**全不会进 feature_numbers** → R1/R2 引用这些数字会被反向校验误判为「凭空编造」。当前即时危害是污染人工检查输出（WARNING 不阻断），但 R1 接地未来升 hard 时会变致命。f3a 改：`feature_numbers` 收集改为**递归遍历 dict/list**（dict 值也展开）。

## 五、待定决策点（explore 浮现，需用户拍板）

### 5.1 f3a scope 边界——(a)/(b)/(c) 三选一

**起因**：芒格（治理/风险）和冯柳（解禁/事件压力）的角色侧重维度在 f3b 才做。f3a 阶段这两个 agent 会暂时缺核心侧重维度。

- **(a) f3a 只让巴菲特/段永平完整**
  - 芒格/冯柳半成品（缺治理/解禁），prompt 标注「待 f3b 补」
  - A/B 只验证巴菲特/段永平的分化
  - **风险**：巴菲特/段永平侧重高度重叠（都看主营+竞品），分化可能不显著，验证效果弱

- **(b) f3a 做 4 agent 全完整**
  - 含芒格治理（fetch_governance.py）+ 冯柳解禁（fetch_events.py）
  - 回到「一次做 6 类 fetcher」的坑，scope 膨胀

- **(c) 用已有数据做角色侧重代理（推荐）**
  - 芒格的治理视角，f3a 先用 `risk.py` **已采的 pledge_ratio**（质押率）做代理，不新建 fetch_governance.py
  - 冯柳的解禁/事件视角，f3a 先用**已有 capex_proxy + 研报**做代理，不新建 fetch_events.py
  - 4 agent 都有角色侧重、A/B 验证有 4 视角分化。**新建 3 fetcher**（main_business + peers + research），capex 读已采字段、pledge 读已采字段（§4.1 口径）

**推荐 (c)**：用已有数据做代理让 4 视角可验证，但不膨胀 fetcher 数。芒格用 pledge 代理治理、冯柳用 capex+研报代理事件——代理不完美但够 f3a 验证「分发是否制造分化」。**此为 propose 前唯一阻断点，待用户最终拍板**（(a)/(b) 保留作决策记录对比）。

### 5.2 dossier 缺失降级时，agent 分发是否「塌缩」——(i)/(ii)/(iii)

**起因**：分层降级里 peers/research/capex 缺失只降级不阻断。但 agent 角色侧重维度恰是这些「降级维度」——若某票 peers 缺失（industry 没采到），巴菲特/芒格/段永平的「竞品」侧重就没了，他们看什么？

- **(i)** 该 agent 退化成「只看 core_snapshot」（失去角色，等于 f2 状态）
- **(ii)** 该 agent 标 degraded 但仍跑，prompt 注明「你的竞品维度缺失，基于 core 判断」
- **(iii)** 该 agent 跳过（不跑），只剩看得到维度的 agent

**Claude 倾向 (ii)**：与 f2 的 L2 降级同哲学（标 degraded 继续，诚实标注），但 f3 降的是单 agent 角色维度而非整个 council。这比 (i)（静默退化失角色）诚实、比 (iii)（跳过破坏 4 agent 结构）稳妥。

## 六、避坑要点（用户明确）

1. **不要一次性做 6 类 fetcher**——数据层 change 一大，调试从「验证深度」变成「到处修接口」
2. **不要把所有定性字段全塞全员 prompt**——回到同质化，只是 token 更贵
3. **不要把研报当事实，只能当「市场共识变量」**——像 Kimi 处理赔率：研究变量不是预测依据
4. **f3a 最小闭环**：main_business + peers + research + capex_proxy 四件，验证「结构化研究档案 + agent 分发」是否让 R1 数据引用分布分化。通过再开 f3b 补治理/解禁/事件

## 七、数据流全景图

```
                        ┌─────────────────────────────────────────────┐
                        │          L0 数据采集层（f3a 新增 3 fetcher + 1 已采接入）   │
                        │                                             │
                        │  fetch_main_business  (stock_zygc_em)       │  优先级1
                        │  fetch_peers          (board_industry_cons) │  优先级2
                        │  CONSTRUCT_LONG_ASSET (已采,零成本接入)      │  优先级3
                        │  fetch_research       (research_report_em)  │  优先级4
                        │                                             │
                        │  cache: _LazyTable 全市场表复用 + TTL        │
                        └───────────────┬─────────────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
        ┌────────────────────┐              ┌──────────────────────────┐
        │ assemble_snapshot  │              │  council/research_       │  f3a 新建
        │ (scout 层,扁平,    │   core 复用  │  dossier.py             │
        │  21字段,L2快筛用)  │◀─────────────│  build_research_dossier( │
        │  不变)             │              │    symbol, core=None)   │
        └────────────────────┘              └──────────┬───────────────┘
                                                       │
                                            分层 dossier:
                                            {core_snapshot,        ← 全员
                                             research_dossier: {
                                               main_business,     ← 巴/芒/段
                                               peers,             ← 巴/芒/段
                                               capex_proxy,       ← 巴/冯
                                               research           ← 段/冯
                                             }}
                                                       │
                                ┌────────────────────────┴────────────────┐
                                ▼                                         ▼
                    ┌──────────────────────┐         ┌──────────────────────────┐
                    │ _build_user_message  │         │   DA / Synthesizer       │
                    │ (改:按 agent 分发)    │         │   看全量 dossier          │
                    │                       │         └──────────────────────────┘
                    │  core_snapshot → 全员  │
                    │  agent_context → 角色  │
                    │  prompt 物理分区:      │
                    │   - 公司事实特征段     │
                    │   - 市场共识段(研报)   │
                    └──────────┬─────────────┘
                               │
                    ┌──────────▼──────────────────────────┐
                    │   4 agent（公共底座 + 角色侧重）      │
                    │                                      │
                    │  巴菲特: core+主营+竞品+capex        │
                    │  芒格:   core+主营+竞品+质押(代理)    │
                    │  段永平: core+主营+竞品+研报         │
                    │  冯柳:   core+研报+capex             │
                    └──────────────────────────────────────┘
```

## 八、下一步

propose 前阻断点：**§5.1 (a)/(b)/(c) 拍板**（推荐 (c)，见 §5.1）。拍板后可进 `opsx:propose f3a-l3-research-dossier`（注意是 **f3a**，分阶段的第一阶段），产出 proposal/design/specs/tasks。f3b 补治理/解禁/事件为后续独立 change。

f3a 落地必做项（本文已标注，propose 时落入 tasks）：
1. §4.2 dossier 传入路径（`run_debate` 改调 `build_research_dossier`，`input_assembly` 不动）
2. §4.3 agent 分发落进 `_build_user_message` 签名（P1）
3. §4.5 D2 保持 soft，升 hard 留独立 change；D3 DA 回查扩展同步
4. §4.6 质量门 `feature_numbers` 递归遍历（P1）+ A/B 量化判据（Jaccard 距离）
