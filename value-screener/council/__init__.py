"""L3 天团深研模块.

核心功能：
- 辩论编排器（debate.py）：4 轮串行辩论，支持多 agent 观点交锋
- Agent 注册表（agents.py）：管理投资大师 agent 的定义
- 输出 schema（schema.py）：AgentOutput / CouncilResult 结构化输出
- LLM 调用层（llm.py）：按推理等级映射模型，支持重试和异常处理

环境变量：
- LLM_API_KEY: API 密钥（required）
- LLM_API_BASE: API base URL（required）
- LLM_MODEL_HEAVY: 重度推理模型（R1-3，如 deepseek-chat）
- LLM_MODEL_MODERATE: 中度推理模型（R4，如 deepseek-chat）

用法：
- 单股深研：`council --ticker 600519`
- 校准测试：`council --calibrate`
- 强制重跑：`council --ticker 600519 --force`
"""

__version__ = "0.1.0"
