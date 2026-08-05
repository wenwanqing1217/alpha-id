"""
Alpha-ID Enrichment 模块
=========================
LLM 驱动的数据理解引擎。

核心组件：
  - LLMEnricher: 把原始对话变成结构化画像
  - ProfileStore: 本地 SQLite 存储 + Markdown 报告
  - run_pipeline: 一键运行管道
"""

from alpha_id.enrichment.llm_enricher import LLMEnricher
from alpha_id.enrichment.profile_store import ProfileStore

__all__ = ["LLMEnricher", "ProfileStore"]
