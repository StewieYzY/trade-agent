## Context

`design/deviation-analysis-2026-07-01.md` 的实证核查发现 L0→L4 骨架全落地但核心链路未真正跑通：L3 同质化（7 次实跑 6 次空壳）、L2 成本闸门零验证、cache ticker 分裂、全市场从未跑过。本 change 聚焦该文档的 P0（L3 R1 根因定位）与 P1（需求 A 全市场验证）。

**代码核查后的根因校准**（重要，与 deviation-analysis §1.3 的三假设对照）：

deviation-analysis §1.3 列了三个并行排查假设。本 design 阶段对涉及代码做了核查，结果如下：

| 假设 | 出处 | 代码核查结论 |
|---|---|---|
| ① prompt 模板含示例被复读 | §1.3 主线 | **排除**。`council/prompt.py` 四份 system prompt 含案例锚定（茅台/可口可乐/山西汾酒），但**无 `"{other_agent} 看好"` 占位文本**；`debate.py::_build_user_message` 构造的 user message 也无此类占位 |
| ② features 注入空/错 | §1.3 次要 | **升为主因嫌疑**。`features.py:23-24` 已做 `ticker.split(".")[0]` 标准化（ticker 后缀非根因），但 600519/600900 的 cache 数据本身可能不足（TTL 过期 + 门 1 前 fetch 不全），导致 `assemble_snapshot` 返回空/缺字段 |
| ③ LLM 响应缓存 | §1.3 最低 | **排除**。`council/llm.py::call_llm` 每次 new `httpx.AsyncClient`，无 cache 字典、无 `lru_cache`，每次独立 HTTP 请求 |

**决定性证据**：同一天、同一模型（DeepSeek，review-notes 确认）、同一份代码，600009 的 buffett R1 输出 `core_thesis="上海机场拥有地理垄断...PE_TTM 26.42、ROE 趋势上升"`（**引用真实特征**），600519/600900 的 buffett R1 输出 `core_thesis="munger 看好长期价值"、key_metrics=["ROE 32%","毛利率 90%+"]`（**无真实特征，全编造**）。区别只在 features 是否注入成功。

**环形引用的次生性**：环形 `core_thesis`（buffett→munger→duan→feng_liu→buffett）既不在 system prompt 也不在 user message，R1 又传 `other_opinions=None`。最可能是模型在 features 空 + `temperature=0` + "请独立判断"指令下，仍推测其他 agent 存在并编造引用——这是**空输入下的模型幻觉行为**，不是代码 bug。修了 features 注入（让数据真的进去），环形引用大概率随之消失。

**结论**：P0 不是"修一个代码 bug"，而是"先用最小复现实验确认根因落在 features 注入（代码层）还是模型幻觉（模型层）"。本 design 的核心决策围绕这个分叉展开。

## Goals / Non-Goals

**Goals:**
- G1：用最小复现实验定位 600519/600900 R1 同质化/串台的根因，区分代码层（features 注入）vs 模型层（幻觉）
- G2：若根因在 features 注入，修复"数据不足→喂空数据→幻觉"链路（R1 入口 fail-fast），与 review-notes #1 的 TTL 问题联动
- G3：跑通需求 A 全市场链路（修 cache ticker 分裂 + 全 A 股 batch + screen + scout），首次实证 AD-03 成本闸门假设
- G4：在质量门层补"R1 引用真实特征"校验维度，防止空壳产出污染 AD-09 gate

**Non-Goals:**
- N1：不改 L3 输入输出 schema（仓位决策语义已在 deviation-analysis §2.5 关闭）
- N2：不重写 agent system prompt（prompt.py 四份 prompt 的案例锚定是设计内的，不是 bug 源头）
- N3：不做 L1 阈值校准（§4.8 是独立工作项，P1 可能暴露但不在本 change 修）
- N4：不做 RULE.md 三层、前端、watchlist manager、张坤（暂缓项）
- N5：不换 LLM 模型（若根因落在模型层，记录为已知限制并衍生新 change，不在本 change 贸然换）

## Decisions

### D1：先做最小复现实验，再决定修哪里
**选择**：P0 第一步是写一个最小复现脚本，对 600519/600900/600009 三只票各跑一次 R1，dump 实际传给 LLM 的 `system_prompt` 长度 + `user_message` 全文（含 features JSON），人工对比。

**理由**：deviation-analysis §1.3 的三假设在代码核查后只剩假设②（features 注入）成立，但"cache 数据不足" vs "assemble_snapshot 逻辑缺陷" vs "模型幻觉"仍需实验区分。贸然改代码可能修错地方。

**替代方案**：直接改 `assemble_council_features` 加 fail-fast。被否——若根因其实是模型幻觉（features 进去了但模型仍编造），fail-fast 会让所有数据充分的票也跑不了。

**实验判据**：
- 若 600519/600900 的 user_message 里 features JSON 为空/缺关键字段 → 根因在代码层（features 注入），走 D2
- 若 features JSON 正常但模型仍输出"ROE 32%/可口可乐" → 根因在模型层，走 D4

### D2：R1 入口加 features 充分性门（若 D1 判定代码层）
**选择**：在 `run_debate` 调用 `assemble_council_features` 后、进入 R1 前，校验 features 充分性。空 dict 或返回 `insufficient_data` 错误时 fail-fast，不进 R1。

**理由**：当前 `debate.py:401-404` 已有 `if "error" in features: raise ValueError`，但只检查显式 error 字段，不检查"返回了 dict 但关键字段全空"的情况。模型拿到空 dict 不报错，靠 system prompt 案例编造。

**实现位置**：`council/features.py::assemble_council_features` 末尾加关键字段校验（name/industry/pe_ttm/roe 至少非空），缺失则返回 `{"error": "insufficient_data", "missing_fields": [...]}`。

**与 review-notes #1 联动**：review-notes #1 提的 TTL 注释/代码不一致（financials 注释 90d 实际 24h）导致 council 首跑 insufficient，本 change 的 fail-fast 会让这个错误更早、更明确地暴露（提示用户先跑 `batch`），但 TTL 注释修正本身不在本 change 范围（留给后续）。

### D3：cache ticker key normalize 放 CacheManager 层
**选择**：在 CacheManager 的 `get`/`set` 入口做 ticker normalize（`ticker.split(".")[0]`），与 `features.py` 已有的 normalize 对齐。

**理由**：`features.py:23-24` 已 normalize，但 CacheManager 层未对齐，导致 fetcher 写时分裂。normalize 应在数据层最底层做一次，调用方不用各自处理。

**替代方案**：在每个 fetcher 里 normalize。被否——分散易漏，且 CacheManager 是唯一读写入口，单点修复更可靠。

### D4：根因若落在模型层的处理
**选择**：若 D1 实验发现 features 正常注入但模型仍输出幻觉，则 P0 不靠代码修复。记录为"DeepSeek 在 temperature=0 下对空/简输入仍有案例锚定幻觉"的已知限制，评估两个方向（**不在本 change 实施**，衍生新 change）：
- 方向 a：prompt 加强约束（"必须引用下方特征数据中的具体数字，禁止引用其他分析师"）
- 方向 b：换更强模型（AD-04 推理等级映射已在，换 LLM_MODEL_HEAVY 即可）

**理由**：模型层问题靠改代码解决不了，强行改 prompt 可能引入新问题，需独立评估。

### D5：全市场验证用真实 akshare 全 A 股列表
**选择**：P1 用 akshare 拉全 A 股代码列表（~5000 只），跑 `batch` + `screen` + `scout`，记录漏斗比例和成本。

**理由**：deviation-analysis §1.5 的核心问题是"从未见过全市场分布"，20 只手工白马样本无法验证 L1 阈值合理性和 L2 区分度。

**风险控制**：~5000 只网络采集耗时长 + 可能触发 akshare 限流，分批跑（如每批 200 只），复用 L0 已有的三级容错 + provider chain。

## Risks / Trade-offs

- **[R1 实验可能显示根因混合]** → features 部分缺失 + 模型部分幻觉。Mitigation：D2 的 fail-fast 先把数据层兜住，模型层残留幻觉走 D4 衍生 change，两步分离。
- **[全市场 batch 耗时 + 限流]** → ~5000 只采集可能数小时 + akshare 限流。Mitigation：分批 + 三级容错 + 已采缓存复用；先跑一个子集（如沪深 300）验证管线再扩到全市场。
- **[L1 阈值在全市场下暴露问题]** → 5000→? 可能不是设计目标的 200，heat_filter 可能筛太狠或太松。Mitigation：本 change 只记录暴露的问题，不修阈值（§4.8 独立工作项）；若 L1 完全不可用则升级为阻塞项再讨论。
- **[fail-fast 可能误伤数据暂缺的好票]** → 某只票当天 akshare 接口异常导致 features 缺失，fail-fast 会让它当天跑不了。Mitigation：错误信息明确提示"先跑 batch 重采"，用户重跑即可；这比"喂空数据产出幻觉 watchlist"更好（后者污染 AD-09 gate）。
- **[D4 模型层根因可能让 P0 无法在本 change 关闭]** → 若实验判定根因在模型层，P0 的代码修复部分（D2）只能解决一半。Mitigation：诚实记录，D2 仍然有价值（堵住数据层），模型层部分明确标注为衍生 change，不硬塞进本 change。
