"""
MindFlow 自然语言日程解析器

把用户的自然语言规划 → 结构化日程表

输入示例：
  "明天9点去公司开会，中午12点跟老王吃饭，下午3点去医院拿药"
  "后天去上海，上午飞机，下午见客户，晚上外滩吃饭"

输出：
  [
    { "time": "09:00", "date": "2026-07-25", "place": "公司", "activity": "开会", "raw": "9点去公司开会" },
    { "time": "12:00", "date": "2026-07-25", "place": "未知", "activity": "跟老王吃饭", "raw": "中午12点跟老王吃饭" },
    { "time": "15:00", "date": "2026-07-25", "place": "医院", "activity": "拿药", "raw": "下午3点去医院拿药" },
  ]
"""

import json
import logging
import os
import re
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mindflow.schedule_parser")


def _llm_parse_schedule(text: str, user_context: str = "") -> Optional[List[Dict]]:
    """用 LLM 解析自然语言日程"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("LLM_MODEL", "LongCat-2.0")

    if not api_key or not base_url:
        return None

    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    date_map = {
        "今天": today.strftime("%Y-%m-%d"),
        "明天": tomorrow.strftime("%Y-%m-%d"),
        "后天": day_after.strftime("%Y-%m-%d"),
    }

    prompt = f"""你是一个日程解析助手。从用户的自然语言中提取日程安排，输出 JSON 数组。

当前日期：{today.strftime("%Y-%m-%d")} 星期{['一','二','三','四','五','六','日'][today.weekday()]}

日期对照：今天={date_map['今天']}，明天={date_map['明天']}，后天={date_map['后天']}

用户信息：
{user_context if user_context else "暂无"}

规则：
1. 每个日程项包含：time(24小时制HH:MM)、date(YYYY-MM-DD)、place(地点，未知则填"未知")、activity(活动内容)、raw(原文片段)
2. 时间模糊时推断合理时间："上午"→09:00，"中午"→12:00，"下午"→14:00，"晚上"→19:00
3. 如果用户说"家""公司"等，结合用户信息中的地址
4. 只输出 JSON 数组，不要其他文字

用户输入：{text}

输出："""

    try:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是日程解析助手，只输出 JSON 数组，不要markdown代码块。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            reply = data["choices"][0]["message"]["content"].strip()

        # 清理可能的 markdown 代码块
        if "```json" in reply:
            reply = reply.split("```json")[1].split("```")[0].strip()
        elif "```" in reply:
            reply = reply.split("```")[1].split("```")[0].strip()

        result = json.loads(reply)
        if isinstance(result, list):
            return result
        return None
    except Exception as e:
        logger.warning(f"LLM 日程解析失败: {e}")
        return None


def parse_schedule(text: str, user_context: str = "") -> List[Dict]:
    """
    解析自然语言日程。
    优先用 LLM 解析，失败则返回空列表。
    """
    # 快速判断：不包含时间词的直接返回空
    time_keywords = ["点", "上午", "中午", "下午", "晚上", "早上", "傍晚",
                     "今天", "明天", "后天", "周", "星期", "号", "日"]
    if not any(kw in text for kw in time_keywords):
        return []

    result = _llm_parse_schedule(text, user_context)
    if result:
        logger.info(f"日程解析成功: {len(result)} 项")
        return result

    return []


def format_schedule_table(items: List[Dict]) -> str:
    """把日程表格式化为可读的文本"""
    if not items:
        return "没有解析到日程安排。"

    lines = ["📅 你的日程安排：\n"]
    for i, item in enumerate(items, 1):
        time_str = item.get("time", "?")
        place = item.get("place", "未知")
        activity = item.get("activity", "")
        lines.append(f"{i}. {time_str} — {activity} @ {place}")

    return "\n".join(lines)
