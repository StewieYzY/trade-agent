"""Agent 注册表（design.md 决策 3, AD-09）.

当前注册 4 位投资大师：巴菲特（buffett）、芒格（munger）、段永平（duan）、冯柳（feng_liu）。
每位大师有独立的 prompt builder，体现其投资哲学和关注点差异。

DA（Devil's Advocate）和 Synthesizer 不注册（设计决策 3）。
它们通过 council.debate 中的独立函数（_call_da / _call_synthesizer）调用，
不进入 AGENT_REGISTRY，不参与 R1/R2 的并行辩论。

AGENT_REGISTRY 结构：
{
    "agent_id": {
        "name": "显示名",
        "prompt_builder": "模块路径.函数名",  # 返回 system prompt 字符串
    },
}
"""
from __future__ import annotations

AGENT_REGISTRY: dict[str, dict] = {
    "buffett": {
        "name": "巴菲特",
        "prompt_builder": "council.prompt.build_buffett_prompt",
    },
    "munger": {
        "name": "芒格",
        "prompt_builder": "council.prompt.build_munger_prompt",
    },
    "duan": {
        "name": "段永平",
        "prompt_builder": "council.prompt.build_duan_prompt",
    },
    "feng_liu": {
        "name": "冯柳",
        "prompt_builder": "council.prompt.build_feng_liu_prompt",
    },
    # DA/synthesizer 不注册（设计决策 3），debate.py 内独立调用
    # 张坤留给后续迭代（蒸馏素材和校准用例不足）
}


def get_prompt_builder(agent_id: str):
    """根据 agent_id 返回对应的 prompt builder 函数.

    Raises:
        KeyError: agent_id 不在 AGENT_REGISTRY 中
        ImportError: prompt_builder 模块路径无法导入
        AttributeError: 模块中找不到对应函数
    """
    if agent_id not in AGENT_REGISTRY:
        raise KeyError(f"unknown agent: {agent_id}")

    module_path = AGENT_REGISTRY[agent_id]["prompt_builder"]
    parts = module_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(f"invalid prompt_builder path: {module_path}")

    import importlib
    mod = importlib.import_module(parts[0])
    return getattr(mod, parts[1])


def get_agent_display_name(agent_id: str) -> str:
    """返回 agent 的显示名称.

    若 agent_id 不在注册表中，返回 agent_id 本身（支持 mock 注入等场景）.
    """
    return AGENT_REGISTRY.get(agent_id, {}).get("name", agent_id)
