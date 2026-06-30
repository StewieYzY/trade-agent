"""L3 天团辩论结构化输出 schema（design.md §6.3, spec council-debate）.

AgentOutput: 每个 agent 的输出 JSON schema
CouncilResult: 辩论编排器的最终输出

校验规则（spec Requirement: AgentOutput JSON Schema）：
- signal 枚举: bullish/bearish/neutral/skip
- conviction: 0-100 整数
- core_thesis: 非空字符串
- what_would_change_my_mind: 非空字符串
- out_of_circle: 布尔值
- key_metrics / risks: 列表（可为空）
- historical_parallel: 选填（可为 null）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


VALID_SIGNALS = {"bullish", "bearish", "neutral", "skip"}


class ValidationError(Exception):
    """AgentOutput JSON 校验失败."""
    pass


@dataclass
class AgentOutput:
    """单个 agent 的结构化输出（§6.3 JSON schema）.

    Attributes:
        name: agent 标识（如 "buffett"）
        signal: 投资信号（bullish/bearish/neutral/skip）
        conviction: 确信度 0-100
        core_thesis: 一句话核心理由
        key_metrics: 引用的具体数据点列表
        risks: 最大风险列表
        what_would_change_my_mind: 什么情况下会改变看法
        out_of_circle: 是否在能力圈外
        historical_parallel: 类似历史案例（选填）
    """
    name: str
    signal: str
    conviction: int
    core_thesis: str
    key_metrics: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    what_would_change_my_mind: str = ""
    out_of_circle: bool = False
    historical_parallel: str | None = None

    def to_json(self) -> str:
        """序列化为 JSON 字符串."""
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return asdict(self)

    @classmethod
    def from_json(cls, name: str, json_str: str) -> AgentOutput:
        """从 JSON 字符串反序列化并校验.

        Args:
            name: agent 标识（注入，不在 JSON 中）
            json_str: LLM 返回的 JSON 字符串

        Returns:
            AgentOutput 实例

        Raises:
            ValidationError: JSON 解析失败或字段校验不通过
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValidationError(f"invalid JSON: {e}")

        return cls.from_dict(name, data)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> AgentOutput:
        """从字典构建并校验.

        Raises:
            ValidationError: 必填字段缺失或类型/值非法
        """
        # 必填字段检查
        required = ["signal", "conviction", "core_thesis", "what_would_change_my_mind", "out_of_circle"]
        missing = [f for f in required if f not in data]
        if missing:
            raise ValidationError(f"missing required fields: {missing}")

        # signal 枚举校验
        signal = data["signal"]
        if signal not in VALID_SIGNALS:
            raise ValidationError(
                f"invalid signal: {signal!r}, expected one of {VALID_SIGNALS}"
            )

        # conviction 范围校验
        conviction = data["conviction"]
        if not isinstance(conviction, int) or not (0 <= conviction <= 100):
            raise ValidationError(
                f"conviction must be int 0-100, got {conviction!r}"
            )

        # core_thesis 非空
        core_thesis = data["core_thesis"]
        if not isinstance(core_thesis, str) or not core_thesis.strip():
            raise ValidationError("core_thesis must be non-empty string")

        # what_would_change_my_mind 非空
        wwcm = data["what_would_change_my_mind"]
        if not isinstance(wwcm, str) or not wwcm.strip():
            raise ValidationError("what_would_change_my_mind must be non-empty string")

        # out_of_circle 布尔
        out_of_circle = data["out_of_circle"]
        if not isinstance(out_of_circle, bool):
            raise ValidationError(f"out_of_circle must be bool, got {type(out_of_circle)}")

        # 列表字段（可为空但必须是列表）
        key_metrics = data.get("key_metrics", [])
        if not isinstance(key_metrics, list):
            raise ValidationError(f"key_metrics must be list, got {type(key_metrics)}")

        risks = data.get("risks", [])
        if not isinstance(risks, list):
            raise ValidationError(f"risks must be list, got {type(risks)}")

        # 选填字段
        historical_parallel = data.get("historical_parallel")

        return cls(
            name=name,
            signal=signal,
            conviction=conviction,
            core_thesis=core_thesis,
            key_metrics=key_metrics,
            risks=risks,
            what_would_change_my_mind=wwcm,
            out_of_circle=out_of_circle,
            historical_parallel=historical_parallel,
        )


@dataclass
class CouncilResult:
    """辩论编排器的最终输出.

    Attributes:
        ticker: 股票代码
        rounds: 按轮次顺序存放每轮结果（R1/R2/R3/R4），
                每项是 list[AgentOutput] 或 None（单 agent 下 R2-4 跳过）
        final_verdict: 最终信号（来自 R4 或 R1 的 fallback）
        key_variables: 从 what_would_change_my_mind 提取的关键变量列表
    """
    ticker: str
    rounds: list[list[AgentOutput] | None]
    final_verdict: str
    key_variables: list[str] = field(default_factory=list)

    def __post_init__(self):
        """单 agent fallback: final_verdict 取 rounds[0][0].signal."""
        if not self.final_verdict and self.rounds and self.rounds[0]:
            self.final_verdict = self.rounds[0][0].signal

    def to_json(self) -> str:
        """序列化为 JSON 字符串."""
        return json.dumps({
            "ticker": self.ticker,
            "rounds": [
                [a.to_dict() for a in r] if r else None
                for r in self.rounds
            ],
            "final_verdict": self.final_verdict,
            "key_variables": self.key_variables,
        }, ensure_ascii=False, indent=2)

    @classmethod
    def extract_key_variables(cls, rounds: list[list[AgentOutput] | None]) -> list[str]:
        """从所有 AgentOutput 的 what_would_change_my_mind 收集关键变量.

        当前实现为原文收集（3a 单 agent），结构化提取留待 3b/L4。
        全天团阶段可考虑用 synthesizer agent 或 NLP 从原文提取结构化变量。
        """
        variables = []
        for r in rounds:
            if not r:
                continue
            for agent_output in r:
                if agent_output.what_would_change_my_mind:
                    variables.append(agent_output.what_would_change_my_mind)
        return variables
