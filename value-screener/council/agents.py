"""Agent 注册表（design.md 决策 3, AD-09）.

debate.py 从此注册表读取 agent 列表，不硬编码 agent 名称。
3a 仅注册巴菲特；3b 追加芒格/段永平/冯柳/张坤/DA/synthesizer，
无需改编排逻辑（"填 agent 即激活"）。

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
    # 3b 追加：
    # "munger": {"name": "芒格", "prompt_builder": "council.prompt.build_munger_prompt"},
    # "duan": {"name": "段永平", "prompt_builder": "council.prompt.build_duan_prompt"},
    # "feng_liu": {"name": "冯柳", "prompt_builder": "council.prompt.build_feng_liu_prompt"},
    # "zhang_kun": {"name": "张坤", "prompt_builder": "council.prompt.build_zhang_kun_prompt"},
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
