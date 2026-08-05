"""
Alpha-ID Skills — 技能集
==========================

可扩展的技能模块：
  - baidu_ai_map: 百度地图 AI 能力（地点检索、路线规划、地理编码、天气）
"""

from alpha_id.skills.baidu_ai_map import BaiduMapClient, BaiduMapConfig

__all__ = ["BaiduMapClient", "BaiduMapConfig"]
