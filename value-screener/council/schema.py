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
        extra: agent 特有字段透传（冯柳 5 字段、DA blind_spots 等）
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
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        """序列化为 JSON 字符串（extra 字段平铺到顶层）."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（extra 字段平铺到顶层）."""
        d = asdict(self)
        extra = d.pop("extra", {})
        d.update(extra)
        return d

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

        # 收集未定义字段到 extra（不再丢弃）
        known_fields = {
            "name", "signal", "conviction", "core_thesis", "key_metrics",
            "risks", "what_would_change_my_mind", "out_of_circle", "historical_parallel"
        }
        extra = {k: v for k, v in data.items() if k not in known_fields}

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
            extra=extra,
        )


@dataclass
class SynthesizerOutput:
    """R4 共识收敛器的输出（design.md 决策 2）.

    Synthesizer 不是投资 agent，输出语义与 AgentOutput 不同：
    - final_signal 代替 signal
    - 新增 consensus_summary / dissent_points / pending_verification

    Attributes:
        final_signal: 收敛后的投资信号
        conviction: 加权平均确信度 0-100
        consensus_summary: 一句话结论
        dissent_points: 保留的分歧点列表 [{topic, who_disagrees, their_reason}]
        pending_verification: 待验证事项列表（从 DA 盲点 + what_would_change_my_mind 提取）
    """
    final_signal: str
    conviction: int
    consensus_summary: str
    dissent_points: list[dict] = field(default_factory=list)
    pending_verification: list[str] = field(default_factory=list)

    def __post_init__(self):
        """校验枚举和范围."""
        if self.final_signal not in VALID_SIGNALS:
            raise ValidationError(
                f"invalid final_signal: {self.final_signal!r}, "
                f"expected one of {VALID_SIGNALS}"
            )
        if not isinstance(self.conviction, int) or not (0 <= self.conviction <= 100):
            raise ValidationError(
                f"conviction must be int 0-100, got {self.conviction!r}"
            )
        if not isinstance(self.consensus_summary, str) or not self.consensus_summary.strip():
            raise ValidationError("consensus_summary must be non-empty string")

    def to_json(self) -> str:
        """序列化为 JSON 字符串."""
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return asdict(self)

    @classmethod
    def from_json(cls, json_str: str) -> SynthesizerOutput:
        """从 JSON 字符串反序列化并校验.

        Raises:
            ValidationError: JSON 解析失败或字段校验不通过
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValidationError(f"invalid JSON: {e}")

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SynthesizerOutput:
        """从字典构建并校验.

        Raises:
            ValidationError: 必填字段缺失或类型/值非法
        """
        required = ["final_signal", "conviction", "consensus_summary"]
        missing = [f for f in required if f not in data]
        if missing:
            raise ValidationError(f"missing required fields: {missing}")

        final_signal = data["final_signal"]
        conviction = data["conviction"]
        consensus_summary = data["consensus_summary"]

        dissent_points = data.get("dissent_points", [])
        if not isinstance(dissent_points, list):
            raise ValidationError(
                f"dissent_points must be list, got {type(dissent_points)}"
            )

        pending_verification = data.get("pending_verification", [])
        if not isinstance(pending_verification, list):
            raise ValidationError(
                f"pending_verification must be list, got {type(pending_verification)}"
            )

        return cls(
            final_signal=final_signal,
            conviction=conviction,
            consensus_summary=consensus_summary,
            dissent_points=dissent_points,
            pending_verification=pending_verification,
        )


@dataclass
class CouncilResult:
    """辩论编排器的最终输出（显式命名字段，design.md 决策 7）.

    Attributes:
        ticker: 股票代码
        round1: R1 各 agent 独立判断
        round2: R2 交叉质疑（单 agent=None）
        round3: R3 DA 输出（单对象，不是列表）
        round4: R4 收敛共识（SynthesizerOutput，单对象）
        final_verdict: 最终信号（全天团=round4.final_signal，单 agent=round1[0].signal）
        key_variables: 从 R1/R2 what_would_change_my_mind 提取
        consensus_summary: 来自 round4
        dissent_points: 来自 round4
        pending_verification: 来自 round4
        debate_path: 辩论记录 md 路径
    """
    ticker: str
    round1: list[AgentOutput]
    final_verdict: str
    round2: list[AgentOutput] | None = None
    round3: AgentOutput | None = None
    round4: SynthesizerOutput | None = None
    key_variables: list[str] = field(default_factory=list)
    consensus_summary: str | None = None
    dissent_points: list[dict] | None = None
    pending_verification: list[str] | None = None
    debate_path: str | None = None

    def __post_init__(self):
        """单 agent fallback: final_verdict 取 round1[0].signal."""
        if not self.final_verdict and self.round1:
            self.final_verdict = self.round1[0].signal

    def to_json(self) -> str:
        """显式序列化四个轮次."""
        data = {
            "ticker": self.ticker,
            "round1": [a.to_dict() for a in self.round1] if self.round1 else None,
            "round2": [a.to_dict() for a in self.round2] if self.round2 else None,
            "round3": self.round3.to_dict() if self.round3 else None,
            "round4": self.round4.to_dict() if self.round4 else None,
            "final_verdict": self.final_verdict,
            "key_variables": self.key_variables,
            "consensus_summary": self.consensus_summary,
            "dissent_points": self.dissent_points,
            "pending_verification": self.pending_verification,
            "debate_path": self.debate_path,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    @classmethod
    def extract_key_variables(
        cls,
        round1: list[AgentOutput],
        round2: list[AgentOutput] | None = None,
    ) -> list[str]:
        """从 R1/R2 所有 AgentOutput 的 what_would_change_my_mind 收集关键变量.

        全天团场景下由 synthesizer 做结构化提炼（pending_verification），
        此函数保留原始收集用于 key_variables 字段。
        """
        variables = []
        for r in (round1, round2):
            if not r:
                continue
            for agent_output in r:
                if agent_output.what_would_change_my_mind:
                    variables.append(agent_output.what_would_change_my_mind)
        return variables
