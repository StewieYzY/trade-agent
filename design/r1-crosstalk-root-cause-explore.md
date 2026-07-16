# R1 串台根因探索：f1 兜了症状，成因未定位

> 状态：探索稿（未进入 OpenSpec change）
> 创建：2026-07-16
> 定位：承接 `deviation-analysis-2026-07-01.md` P0（串台/同质化）与 f1-deviation-fix 的修复边界，定位 R1 串台的**成因**（而非再加一道检测）。
> 关联：`design/l3-5-holding-discipline.md`（L3.5 在此之上盖楼）、`openspec/changes/f3a-l3-research-dossier/design.md`（D6 Jaccard 0.944 疑为信息割裂非增量）。

---

## 一、问题回顾：串台和同质化是两件事

`deviation-analysis-2026-07-01.md §1.2-1.3` 基于文件系统实证记录了两个现象：

- **同质化**：4 agent 的 `key_metrics`（ROE 32%、毛利率 90%+）、`risks`、`historical_parallel`（可口可乐）、`what_would_change_my_mind`（市场份额大幅下降）逐字相同。
- **串台（环形引用，非随机泄露）**：R1 本该隔离（`other_opinions=None`），但 4 agent 的 `core_thesis` 互写别人，且构成有方向的环：
  ```
  buffett  → "munger 看好长期价值"
  munger   → "duan 看好长期价值"
  duan     → "feng_liu 看好长期价值"
  feng_liu → "buffett 重新审视后仍看好"
  ```
  环的方向与 `AGENT_REGISTRY` 注册顺序一致——偏差分析当时判断"暗示根因在 prompt 模板，而非 `other_opinions` 运行时泄露"。

**铁证**（§1.3）：600900（长江电力，水电股）单 agent 模式下，buffett 的 R1 仍写"munger 看好长期价值"、ROE 32%、毛利率 90%+、可口可乐——而 600900 根本没跑 munger，ROE 也不是 32%。这不可能是两次独立 LLM 调用的结果，也不可能来自 `other_opinions` 运行时泄露（单 agent 模式无 munger 输出）。

---

## 二、f1-deviation-fix 修了什么、没修什么

偏差分析给了三个根因假设（按可能性排序）：

1. **【主线·最可能】prompt 模板含示例/占位文本被复读**
2. features 注入空/错（TTL 过期 + guard 放行）
3. LLM 响应缓存层

f1 的代码核查结论（`deviation-analysis §4 P0 完成状态` + `scripts/repro_out/ROOT_CAUSE.md`）：

- **排除假设①**："prompt 无占位文本"
- **排除假设③**："llm.py 无缓存层"
- **确认假设②**："features 因 cache TTL 过期缺失，guard 因 critical_fields/缺失率口径放行"
- 修复：`scout/input_assembly.py` guard 加 `financials_floor` 硬门槛（fail-fast）；`debate.py` 错误消息含缺失字段；§6 质量门补"R1 反向特征校验 + 环形引用检测"防御层。

### 2.1 f1 准确修好了「同质化」那一半

假设②（features 缺失）确实能解释同质化：features 没进去 → 模型没有真实财务数字 → 退回复读 system prompt 邻近值（ROE 32%/毛利率 90%+ 是 prompt 里"护城河好公司"的典型值，可口可乐是 `prompt.py:40` 明写的 `可口可乐 → 茅台` 映射）。`financials_floor` fail-fast 在 features 缺失时直接阻断，确实消除了这一条路径。

### 2.2 但假设②解释不了「串台」那一半

21 个量化扁平字段（PE/ROE/F-score/净利率/跌幅...）里**不含人名**。features 全空，顶多让 buffett 编不出财务数字，**不会让他凭空写"munger 看好长期价值"**。串台是 agent 间引用的元叙述，数据缺失这条成因够不着它。

**f1 没有正面回答串台的成因。** 它用 `detect_circular_reference`（`verify_quality_gate.py:317-356`）对串台做了**事后检测**，但那是"识别症状"，不是"消除成因"。

---

## 三、关键发现：检测器没接到主流程的断路器上

读代码实证（2026-07-16）：

### 3.1 串台/凭空数字检测是 print-only

`detect_circular_reference` 和 `verify_r1_feature_grounding` 只在 `verify_quality_gate.py:473-495` 被调用，那段代码全是 `print(...)` + `[WARNING]`，**不 `return False`、不影响 `verify_mechanism_gate` 的布尔结论**。

`verify_mechanism_gate`（`:360`，CLI `verify_quality_gate.py:726` 调用的人工验证入口）的 hard fail 只覆盖**结构完整性**：

```
R3 DA blind_spots 非空且结构合法（title/detail/which_agents_missed_it）
R4 Synthesizer dissent_points / pending_verification 非空
```

环形串台和凭空数字这两类**质量**问题，在同一函数内但只 print warning——**gate 即使含环形串台也能 PASSED**（只要 R4 字段非空）。

### 3.2 主流程根本不调质量门

`debate.py`（产出 watchlist JSON 的主流程）grep `detect_circular_reference` / `verify_r1_feature_grounding` / `verify_mechanism_gate` —— **零命中**。`cli.py` 同样零命中主流程路径。

净效果：

```
f1 的串台/同质化三道防线，实际力度：

① financials_floor fail-fast（debate.py 主流程）
   → 真·拦截，但只拦"features 缺失"这一种成因
   → features 充足但模型仍复读 prompt 案例锚定时，①不触发

② detect_circular_reference（verify_quality_gate.py）
   → 只在人工检查函数里 print [WARNING]
   → debate.py/cli.py 主流程零调用 ← 缝隙
   → 产出照样落盘，watchlist 照样可能 null

③ verify_r1_feature_grounding（同 ②）
   → 同 ②，只 print 不拦截

净效果：f1 兜的是"事后可识别"，不是"事前不产出"。
       AD-09 gate 在主流程里实际未启用。
```

### 3.3 这解释了 CLAUDE.md 里的悬案

CLAUDE.md："7 份 watchlist 中 6 份的 `consensus_summary/conviction/dissent_points` 为 `null`（R4 未跑到或 L3 R1 串台/同质化 bug）"。现在闭环了：**不是 R4 没跑到，是 R4 跑了但被串台/同质化污染，而质量门只在另一个人工调用的函数里 print warning，从不在主流程拦截**，污染产出照样落盘成"看起来成功"的 JSON。

f1 回放记录 `r1_grounding_replay.md` 末尾"AD-09 gate 不再被空壳污染"——**这话过度乐观**。质量门能**识别**污染（在人工检查模式），但**没有阻止**污染进入 watchlist 产出。识别 ≠ 拦截。

---

## 四、成因定位：两个未验证的可证伪假设

f1 排除假设①的口径是"prompt 无占位文本"。但偏差分析假设①说的是"R1 模板里可能有一段**示例串**"，"占位文本"和"few-shot 案例锚定段"不是一回事。真正诱导模型串台/复读的，不是占位文本，是 **system prompt 第 2 层「案例锚定」**（读 `council/prompt.py` 实证）：

| agent | 第 2 层案例锚定（system prompt 明文） |
|---|---|
| 巴菲特（`:40-44`） | 护城河分类带 `美国标的 → A 股标的` 映射：可口可乐→茅台、GEICO→海螺水泥、铁路→水电燃气牌照 |
| 芒格（`:120-123`） | 核心案例：喜诗糖果"说服**巴菲特**以较高估值买入"、比亚迪 |
| 段永平（`:164-167`） | 实际买过：网易、苹果、**茅台**（明写"品牌定价权"） |
| 冯柳（`:235-238`） | 真实案例：山西汾酒、同仁堂 |

芒格的 prompt **直接出现"巴菲特"这个名字**。即便 R1 隔离、user message 无"munger"字样，芒格的 R1 输出写"duan/buffett 看好"这类交叉引用时，模型有语料依据。四人 prompt 都带 A 股映射示例当事实素材——features 单薄时，模型退回复读这些邻近值。

但这是**推测**，没受控验证过。两个成因假设要分清：

### 假设 A（设计层根因）—— prompt 案例锚定诱导复读

> system prompt 第 2 层「案例锚定」（可口可乐→茅台、芒格提巴菲特、段永平"实际买过茅台"）在 features 单薄时被模型当事实素材复读，并复读训练语料里"巴菲特-芒格-段永平"形影不离的叙事。

- **验证**：features 充足 vs 缺失两组对照，串台/复读发生率应显著差异；或把案例锚定段临时剥离（降格为格式范例），对比串台率。
- **若成立**：不是 bug，是 AD-09 在当前 prompt 架构下的固有缺陷——案例锚定从"事实素材"降格为"格式范例，禁止当数据引用"，是架构变更，可能动摇 AD-09。

### 假设 B（模型层根因）—— 弱模型在 JSON 约束下复读语料

> deepseek 等弱模型在 JSON schema 约束下，倾向复读训练语料里"巴菲特-芒格-段永平"形影不离的叙事，与 prompt 设计无关。

- **验证**：同一 features/prompt，换强模型（gpt-4 级）对照，串台率应显著下降。
- **若成立**：根因在 `LLM_MODEL` 选择，不动 prompt，L3.5 可以放心盖楼。

两个假设现在**都没被验证过**，f1 的检测只兜住了症状。这是"正面定位串台根因"该做的事——**不是再加一道检测，是做受控实验分清 A 还是 B**。

---

## 五、逃逸面：现有检测器会被模型"不直呼其名"绕过

`detect_circular_reference`（`:317-356`）实现是**字符串子串匹配**：`aid in thesis`——只要 core_thesis 里出现 "munger"/"duan"/"feng_liu"/"buffett" 字面就拦。对显式点名（"munger 看好"）有效，但逃逸面清晰：

```
模型若写成「另一位价值投资者也看好」「价值投资派达成共识」
                  ↑ 不出现 agent_id 字面，detect_circular_reference 放行
```

一旦模型学到"别直呼 agent_id 就能过门"，串台就从显性变隐性。根因定位实验里要顺带验证这条逃逸面（采样真实产出看隐性串台占比），否则即使 A 成立、改了 prompt，靠字符串匹配的检测器也无法兜住改完后的产出。

---

## 六、对 f3a / L3.5 的影响

### 6.1 f3a 的 Jaccard 0.944 疑为信息割裂非增量

`f3a-l3-research-dossier/design.md` D6 自承：B=0.944 偏高主因 **peers 降级**（600009 industry 未采）+ research 只分发 feng_liu/duan，**导致 core 之外共享维度少**。Jaccard 衡量集合**不交叠程度**——人为把维度切窄，不交叠自然飙高。这不是信息增量，是**信息割裂**。peers 补齐后分化回落中等区间，恰恰说明 0.944 是假高分。

f3a 的角色分发还可能**放大**串台风险：当某 agent 侧重维度恰好降级缺失（D5: peers/research 降级标注）时，它比以前更容易退回 system prompt 案例锚定凑数。f1 的环形引用检测拦"凭空 ROE 32%"，但拦不了"芒格说巴菲特看好"这种元叙述——它不是凭空数字，是 prompt 里写了的叙事。

### 6.2 L3.5 在晃动地基上盖楼

`l3-5-holding-discipline.md` 承接 L3 深研输出生成持有协议。但 L3 的"好不好"判断若仍被串台/同质化污染（且质量门在主流程不拦截），L3.5 的"持有合同"就建立在不可靠的 L3 输出上。串台根因定位是 L3.5 之前的地基问题。

---

## 七、下一步：先 1 后 2

1. **本文（探索稿）**：沉淀"f1 兜症状未消成因 + 两个未验证假设 A/B + 检测器逃逸面"供立项引用。
2. **`opsx:propose`**：把"串台根因受控实验"立成 bug 定位类 change（参照 f1 模式）。实验设计要点：
   - A/B 受控：features 充足 vs 缺失 × prompt 案例锚定保留 vs 剥离 × 模型弱 vs 强
   - 观测指标：显性串台率（`detect_circular_reference` 命中）+ 隐性串台率（人工/语义采样）+ 同质化率 + Jaccard 分化度（参照 f3a D6，但用信息增量而非割裂口径）
   - 结论分叉：A 成立 → 改 prompt 设计哲学（架构变更，可能动摇 AD-09）；B 成立 → 换模型，不动 prompt，L3.5 可推进
   - **独立但可顺手记入**：把 `detect_circular_reference` / `verify_r1_feature_grounding` 从 print-only 接成主流程 hard fail（让 AD-09 gate 真正启用）——这是另一条独立工作项，根因定位 change 不应混入，但探索稿记录此缝隙

## 八、Open Questions

- 串台在 600009（真实完整产出）那份里**没有**发生（`r1_grounding_replay.md` 四 agent 全通过环形引用检测）。差异变量是"features 充足"——这轻度支持假设 A（features 充足时不复读案例锚定），但 600009 是单一样本，不足以排除假设 B（可能只是那次模型没幻觉）。需受控实验扩样本。
- `detect_circular_reference` 改 hard fail 的阈值/位置：是 R1 单 agent 检测即拦，还是 R4 Synthesizer 汇总时拦？前者更早，但降级场景下 R1 <4 agent 时的行为需设计。
