"""L1 Quantitative Screener — 量化筛选引擎.

将 ~5000 只 A 股压缩至 ~200 只候选池，供 L2/L3 消费。
纯规则 + 学术公式，零 LLM 调用。

三道漏斗：
1. Hard Gates（硬门槛过滤）→ ~800
2. Factor Scores + Anti-Trap（三因子打分 + 反价值陷阱扣分）→ ~300
3. Heat Filter（低热度排除）→ ~200
"""

from .main import screen_a_shares

__all__ = ["screen_a_shares"]
