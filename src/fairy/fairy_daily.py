"""
FAIRY 每日总结 — 事后总结 + 锐评

功能：
- 记录当日观察到的活动
- 晚间生成总结（今天做了什么）
- 锐评（sharp commentary）：幽默/讽刺的评论
"""

import logging
import os
import json
import time
from datetime import datetime, date
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

DAILY_PATH = os.getenv("FAIRY_DAILY_PATH", os.path.expanduser("~/.fairy/daily"))


class FairyDaily:
    """
    每日总结 + 锐评

    锐评风格：
    - 幽默但不刻薄
    - 基于事实（今天的真实活动）
    - 中文为主，偶尔夹英文
    """

    def __init__(self, daily_path: str = DAILY_PATH, brain=None):
        self.daily_path = daily_path
        self.brain = brain  # FairyBrain 实例，用于生成锐评
        self._today_activities: List[Dict[str, Any]] = []
        os.makedirs(self.daily_path, exist_ok=True)

    def record_activity(self, scene: str, detail: str = "", duration: int = 0):
        """记录一项活动"""
        self._today_activities.append({
            "time": datetime.now().isoformat(),
            "scene": scene,
            "detail": detail,
            "duration": duration,
        })

    def generate_summary(self) -> str:
        """
        生成今日总结

        Returns:
            总结文本
        """
        if not self._today_activities:
            return "今天没什么记录，FAIRY 在睡觉。"

        # 统计各场景时长
        scene_counts: Dict[str, int] = {}
        for act in self._today_activities:
            scene = act["scene"]
            scene_counts[scene] = scene_counts.get(scene, 0) + act.get("duration", 0)

        # 构建总结
        lines = [f"📊 FAIRY 日报 ({date.today().isoformat()})\n"]
        lines.append(f"今日记录 {len(self._today_activities)} 项活动：\n")

        for scene, total_secs in sorted(scene_counts.items(), key=lambda x: -x[1]):
            mins = total_secs // 60
            if mins > 0:
                lines.append(f"  • {scene}: {mins} 分钟")

        summary = "\n".join(lines)
        self._save_summary(summary)
        return summary

    def generate_commentary(self) -> str:
        """
        生成锐评（sharp commentary）

        Returns:
            锐评文本
        """
        if not self._today_activities:
            return ""

        # 构建上下文给大脑
        activity_text = "\n".join(
            f"- {a['scene']}: {a['detail']}" for a in self._today_activities[-20:]
        )

        prompt = f"""今天是我观察到的用户活动：

{activity_text}

请用一句话给出幽默但不过分的中文锐评，风格像一个毒舌但关心人的朋友。不要重复活动列表，只输出锐评本身。"""

        if self.brain:
            commentary = self.brain.generate(prompt, max_tokens=200)
            return commentary or self._fallback_commentary()

        return self._fallback_commentary()

    def _fallback_commentary(self) -> str:
        """无大脑时的默认锐评"""
        scenes = set(a["scene"] for a in self._today_activities)
        if "gaming" in scenes and "working" not in scenes:
            return "今天游戏通关了吗？还是说……你已经被游戏通关了？🎮"
        if len(self._today_activities) > 50:
            return "今天可真忙啊，FAIRY 的眼睛都快跟不上你的手速了。"
        if "working" in scenes:
            return "工作也是一种修行，FAIRY 为你点赞。💪"
        return "平淡的一天，但 FAIRY 一直陪着。✨"

    def _save_summary(self, summary: str):
        """保存总结到文件"""
        try:
            filename = f"daily_{date.today().isoformat()}.txt"
            filepath = os.path.join(self.daily_path, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(summary)
        except Exception as e:
            logger.error(f"总结保存失败: {e}")

    def get_today_file(self) -> Optional[str]:
        """获取今日文件路径"""
        filepath = os.path.join(self.daily_path, f"daily_{date.today().isoformat()}.txt")
        return filepath if os.path.exists(filepath) else None
