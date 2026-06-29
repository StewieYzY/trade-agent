"""pytest 配置：把项目根加入 sys.path，使 screener/data 包可被测试导入.

无此文件时 pytest tests/test_screener.py 会 ModuleNotFoundError: No module named 'screener'。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
