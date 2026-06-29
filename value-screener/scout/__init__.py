"""Scout Agent — L2 LLM 初筛（design.md §2, tasks 1.x）.

Scout 是 L1→L3 的成本闸门：
- 输入：L1 候选池 ~200 只（S5 schema）
- 处理：轻量 LLM 推理（¥0.01/只，~¥2/轮）
- 输出：deep_dive 短名单 ~20 只（top-20 cap，AD-03）

模块分工：
- prompt.py: System prompt 模板 + 特征快照格式化
- input_assembly.py: L1→L2 数据交接（从 L0 cache 取全维度原始数据）
- batch.py: 并发 LLM 调用（httpx 直连，asyncio 并发）
- parse.py: 结构化输出解析 + verdict 覆盖逻辑（缓冲带）
- quality.py: 输出质量保证（24h 缓存含输入快照）
"""
"""L2-LLM-Scout-Agent: 基于 LLM 的二级股票初筛系统.

Overview:
    L2 Scout Agent 是 value-screener 系统的二级筛选模块,接收 L1 量化筛选输出的
    ~200 只候选股票,通过 LLM 进行快速定性分析,输出 ~20 只 deep_dive 股票进入
    L3 深度研究阶段.

Architecture:
    - prompt.py: LLM 系统提示词设计 (5 问定性分析框架)
    - input_assembly.py: L1→L2 数据交接 (特征快照组装)
    - batch.py: LLM 批量调用 (并发控制、成本闸门)
    - parse.py: LLM 输出解析 (缓冲带逻辑)
    - quality.py: 输出质量保证 (缓存策略)

Key Design Decisions:
    1. 数据源: 从 L0 CacheManager 取全维度原始数据,不依赖 L1 S5 schema
    2. LLM 调用: httpx 直连 OpenAI 兼容 API, temperature=0.0
    3. 成本闸门: top-20 cap (confidence 降序), ~¥2/run
    4. 缓存策略: 24h TTL, 包含 input_snapshot 用于诊断
    5. 缓冲带: confidence 40-60 → watch, <40 → error

Usage:
    python cli.py scout --input l1_output.json --output l2_shortlist.json

Environment Variables:
    LLM_API_KEY: LLM API 密钥 (required)
    LLM_API_BASE: LLM API base URL (required, e.g., https://api.openai.com/v1)
    LLM_MODEL: LLM 模型名称 (required, e.g., gpt-4o-mini)

References:
    - design.md §2: Scout Prompt 设计
    - design.md §3: LLM Client 选型
    - design.md §4: 并发策略与成本闸门
    - total-design §5.2: LLM 初筛设计
"""
from .prompt import SCOUT_SYSTEM_PROMPT, format_snapshot
from .input_assembly import assemble_snapshot
from .batch import scout_batch
from .parse import parse_scout_output, apply_buffer_zone
from .quality import ScoutCache

__all__ = [
    "SCOUT_SYSTEM_PROMPT",
    "format_snapshot",
    "assemble_snapshot",
    "scout_batch",
    "parse_scout_output",
    "apply_buffer_zone",
    "ScoutCache",
]
