# L3 Council 天团深研

巴菲特单 agent 对单股做深度研判，验证辩论编排架构可行性（AD-09 gate）。

## 用法

### 单股深研

```bash
cd value-screener
python cli.py council --ticker 600519
```

- TICKER：6 位数字，自动补后缀（6/9 开头 → .SH，0/3 开头 → .SZ）
- 输出：AgentOutput JSON（stdout）+ 辩论记录 `debate/{ticker}/{date}.md`
- 成本：~¥0.675/只（仅 R1 调用，R2-4 单 agent 跳过）

### 跳过缓存

```bash
python cli.py council --ticker 600519 --force
```

同股同日内重跑默认命中缓存（`debate/{ticker}/{date}.md`），`--force` 强制重跑 LLM。

### 校准测试

```bash
python cli.py council --calibrate
```

跑巴菲特校准用例（茅台看多 / 长江电力看空），验证立场一致性。

## 配置

环境变量（必填）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_API_KEY` | API 密钥 | `sk-...` |
| `LLM_API_BASE` | API base URL | `https://api.openai.com` |
| `LLM_MODEL_HEAVY` | 重度推理模型（R1-3） | `o1-preview` |
| `LLM_MODEL_MODERATE` | 中度推理模型（R4） | `gpt-4o` |

推理等级映射（design.md AD-04）：
- **heavy**（R1-3）：长输入、跨维度关联推理、对抗性分析
- **moderate**（R4）：收敛共识，推理强度较低

## Gate 结果（AD-09 三层 AND）

### 机制门 ✓
- debate.py 能跑完整流程，R1 独立跑通
- R2 mock 注入机制已实现（`mock_opinions` 参数），验证 A2A 消费链路
- R3/R4 框架代码可执行不报错（单 agent 下跳过）

### 校准门 ⏳（待实测）
- 校准测试（茅台看多 / 长江电力看空）立场一致性
- 运行 `council --calibrate` 验证

### 信息增量门 ⏳（待实测）
- L3 产出的 `risks` 和 `what_would_change_my_mind` 均为非空
- `core_thesis` 信息量明显多于 L2 的 `one_liner`

### moderate 推理等级声明
- `LLM_MODEL_MODERATE` 映射分支在 3a 已实现但 R4 跳过未被真实调用覆盖
- 留待 3b 全天团 R4 收敛共识验证

## 架构

```
council/
├── agents.py      # Agent 注册表（AGENT_REGISTRY）
├── prompt.py      # 巴菲特 system prompt（Level 2 四层结构）
├── schema.py      # AgentOutput / CouncilResult JSON schema
├── features.py    # L3 特征组装（复用 scout.input_assembly）
├── llm.py         # LLM 调用层（按推理等级映射模型）
├── debate.py      # 辩论编排器（4 轮串行，唯一状态持有者）
└── calibrate.py   # 校准测试
```

辩论编排（design.md §6.4）：
- Round 1：各自表态（并行，彼此隔离，重度推理）
- Round 2：交叉质疑（并行，可见他人 R1，重度推理；单 agent 跳过）
- Round 3：Devil's Advocate（单 agent 跳过；全天团可见 R1+R2）
- Round 4：收敛共识（单 agent 跳过；全天团可见 R1+R2+R3，中度推理）

信息可见性由编排器控制，agent 之间不直接通信。

## 扩展全天团（3b）

在 `council/agents.py` 注册全天团 agent：

```python
AGENT_REGISTRY = {
    "buffett": {...},
    "munger": {"name": "芒格", "prompt_builder": "council.prompt.build_munger_prompt"},
    "duan": {"name": "段永平", "prompt_builder": "council.prompt.build_duan_prompt"},
    # ...
}
```

debate.py 自动按 agent 列表跑 R2-4，无需改编排逻辑（"填 agent 即激活"）。
