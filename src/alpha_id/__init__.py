"""
Alpha-ID SDK — pip install alpha-id 入口包

公开 API：
    Agent           — 一站式 AI 身份智能体
    UserIdentity    — 用户身份管理器
    AlphaSocial     — 社交网络管理器
    RiskEngine      — 风控引擎
    TwinBrain       — AI 大脑状态机
"""

from .agent import Agent
from .container import Container

__all__ = ["Agent", "Container"]
__version__ = "0.2.0"
