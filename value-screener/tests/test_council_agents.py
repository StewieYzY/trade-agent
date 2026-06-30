"""L3 agent registry 单元测试.

覆盖:
- 注册表含 4 个 key（buffett/munger/duan/feng_liu）
- get_prompt_builder 返回函数
- DA/synthesizer 不注册
"""
from __future__ import annotations

import pytest

from council.agents import AGENT_REGISTRY, get_prompt_builder


class TestAgentRegistry:
    def test_registry_has_four_keys(self):
        """注册表含 4 个 key."""
        assert set(AGENT_REGISTRY.keys()) == {"buffett", "munger", "duan", "feng_liu"}

    def test_registry_no_da_or_synthesizer(self):
        """DA/synthesizer 不注册."""
        assert "da" not in AGENT_REGISTRY
        assert "synthesizer" not in AGENT_REGISTRY

    def test_registry_has_name_and_prompt_builder(self):
        """每条注册项含 name 和 prompt_builder."""
        for agent_id, entry in AGENT_REGISTRY.items():
            assert "name" in entry, f"{agent_id} missing name"
            assert "prompt_builder" in entry, f"{agent_id} missing prompt_builder"


class TestGetPromptBuilder:
    def test_returns_function(self):
        """get_prompt_builder 返回可调用函数."""
        func = get_prompt_builder("buffett")
        assert callable(func)

    def test_munger_returns_function(self):
        """get_prompt_builder('munger') 返回函数."""
        func = get_prompt_builder("munger")
        assert callable(func)

    def test_duan_returns_function(self):
        """get_prompt_builder('duan') 返回函数."""
        func = get_prompt_builder("duan")
        assert callable(func)

    def test_feng_liu_returns_function(self):
        """get_prompt_builder('feng_liu') 返回函数."""
        func = get_prompt_builder("feng_liu")
        assert callable(func)

    def test_unknown_agent_raises_key_error(self):
        """未知 agent_id 抛 KeyError."""
        with pytest.raises(KeyError, match="unknown agent"):
            get_prompt_builder("unknown_agent")

    def test_function_returns_string(self):
        """prompt builder 返回字符串."""
        func = get_prompt_builder("buffett")
        result = func()
        assert isinstance(result, str)
        assert len(result) > 0
