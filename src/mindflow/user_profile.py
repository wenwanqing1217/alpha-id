"""
MindFlow 用户画像与记忆系统

职责：
  1. 存储用户的基本信息（家、公司、常去地点）
  2. 记住用户的偏好和习惯
  3. 持久化到本地 JSON 文件（后续可迁移到数据库）
  4. 提供自然语言摘要给 LLM 作为对话上下文

数据结构：
  {
    "user_id": "feishu:ou_xxx",
    "profile": {
      "name": "老板",
      "home": { "label": "家", "address": "XX市XX区XX路XX号", "lat": 0.0, "lng": 0.0 },
      "work": { "label": "公司", "address": "XX市XX区XX大厦", "lat": 0.0, "lng": 0.0 },
      "frequent_places": [...],
      "preferences": {
        "wake_time": "07:30",
        "work_start": "09:00",
        "lunch_time": "12:00",
        "transport": "drive",  // drive / subway / walk
        "avoid_traffic": true,
      }
    },
    "memories": [
      { "text": "不喜欢走三环，太堵", "timestamp": 1784400000, "category": "preference" },
      { "text": "每周三下午有周会", "timestamp": 1784400000, "category": "schedule" },
    ]
  }
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mindflow.user_profile")

# 存储目录
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


class UserProfile:
    """单个用户的画像与记忆"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._data = {
            "user_id": user_id,
            "profile": {
                "name": "",
                "home": {},
                "work": {},
                "frequent_places": [],
                "preferences": {},
            },
            "memories": [],
        }

    # ── 基本信息 ──

    def set_name(self, name: str):
        self._data["profile"]["name"] = name

    def set_home(self, address: str, label: str = "家", lat: float = 0.0, lng: float = 0.0):
        self._data["profile"]["home"] = {"label": label, "address": address, "lat": lat, "lng": lng}

    def set_work(self, address: str, label: str = "公司", lat: float = 0.0, lng: float = 0.0):
        self._data["profile"]["work"] = {"label": label, "address": address, "lat": lat, "lng": lng}

    def add_frequent_place(self, name: str, address: str, lat: float = 0.0, lng: float = 0.0):
        place = {"label": name, "address": address, "lat": lat, "lng": lng}
        existing = self._data["profile"]["frequent_places"]
        # 同名地点不重复添加
        if not any(p["label"] == name for p in existing):
            existing.append(place)

    def set_preference(self, key: str, value: Any):
        self._data["profile"]["preferences"][key] = value

    # ── 记忆系统 ──

    def add_memory(self, text: str, category: str = "general"):
        """添加一条记忆"""
        self._data["memories"].append({
            "text": text,
            "timestamp": int(time.time()),
            "category": category,
        })
        # 最多保留 200 条记忆
        if len(self._data["memories"]) > 200:
            self._data["memories"] = self._data["memories"][-150:]

    def search_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """简单关键词搜索记忆（后续可升级为向量搜索）"""
        query_lower = query.lower()
        matches = []
        for mem in self._data["memories"]:
            if any(kw in mem["text"].lower() for kw in query_lower.split()):
                matches.append(mem)
                if len(matches) >= limit:
                    break
        return matches

    def get_all_memories(self) -> List[Dict]:
        return self._data["memories"]

    # ── 上下文生成（给 LLM 用）──

    def build_context(self) -> str:
        """生成用户上下文摘要，注入到 LLM 的 system prompt"""
        p = self._data["profile"]
        lines = []

        if p.get("name"):
            lines.append(f"用户称呼：{p['name']}")

        if p.get("home"):
            lines.append(f"家：{p['home'].get('address', '未设置')}")

        if p.get("work"):
            lines.append(f"公司：{p['work'].get('address', '未设置')}")

        places = p.get("frequent_places", [])
        if places:
            place_strs = [f"{pl['label']}({pl['address']})" for pl in places[:5]]
            lines.append(f"常去地点：{', '.join(place_strs)}")

        prefs = p.get("preferences", {})
        if prefs:
            pref_items = []
            if prefs.get("transport"):
                pref_items.append(f"出行方式：{prefs['transport']}")
            if prefs.get("avoid_traffic"):
                pref_items.append("避开拥堵")
            if prefs.get("wake_time"):
                pref_items.append(f"起床时间：{prefs['wake_time']}")
            if pref_items:
                lines.append(f"偏好：{', '.join(pref_items)}")

        # 最近 5 条相关记忆
        recent = self._data["memories"][-5:]
        if recent:
            mem_strs = [f"  - {m['text']}" for m in recent]
            lines.append("近期记忆：\n" + "\n".join(mem_strs))

        return "\n".join(lines) if lines else "暂无用户信息，请多了解用户的偏好和习惯。"

    # ── 持久化 ──

    def save(self):
        """保存到本地 JSON"""
        path = DATA_DIR / f"user_{self.user_id.replace(':', '_')}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        logger.info(f"用户画像已保存: {path}")

    @classmethod
    def load(cls, user_id: str) -> "UserProfile":
        """从本地 JSON 加载"""
        instance = cls(user_id)
        path = DATA_DIR / f"user_{user_id.replace(':', '_')}.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    instance._data = json.load(f)
                logger.info(f"用户画像已加载: {path}")
            except Exception as e:
                logger.warning(f"加载用户画像失败: {e}，使用空白画像")
        return instance


# ── 全局用户管理 ──

_user_cache: Dict[str, UserProfile] = {}


def get_user_profile(user_id: str) -> UserProfile:
    """获取用户画像（带缓存）"""
    if user_id not in _user_cache:
        _user_cache[user_id] = UserProfile.load(user_id)
    return _user_cache[user_id]


def save_all():
    """保存所有缓存的用户画像"""
    for profile in _user_cache.values():
        profile.save()
