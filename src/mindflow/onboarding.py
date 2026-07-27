"""
MindFlow 用户身份注册引导流程

通过对话引导用户设置个人信息：
  1. 称呼（name）
  2. 家庭地址（home）
  3. 工作地址（work）
  4. 出行偏好（transport）
  5. 作息时间（wake_time, work_start）

用法：
  from mindflow.onboarding import OnboardingFlow

  flow = OnboardingFlow(user_id)
  reply = flow.handle_message("我家在朝阳区xxx")
  # flow.is_complete() → True/False
"""

import logging
import re
from typing import Dict, Optional

from mindflow.user_profile import get_user_profile

logger = logging.getLogger("mindflow.onboarding")

# 引导问题序列
_ONBOARDING_STEPS = [
    {
        "key": "name",
        "question": "你好！我是 MindFlow，你的个人数字分身。在开始之前，先认识一下吧 👋\n\n你希望我怎么称呼你？",
        "hint": "比如：小王、老板、名字都行",
        "parser": "_parse_name",
    },
    {
        "key": "home",
        "question": "你的家庭住址是？（这样我可以帮你规划出行路线）",
        "hint": "比如：北京市朝阳区望京SOHO",
        "parser": "_parse_address",
    },
    {
        "key": "work",
        "question": "你的工作地址是？",
        "hint": "比如：北京市海淀区中关村软件园",
        "parser": "_parse_address",
    },
    {
        "key": "transport",
        "question": "你平时主要怎么出行？",
        "hint": "开车 / 地铁 / 公交 / 步行 / 骑车",
        "parser": "_parse_transport",
    },
    {
        "key": "wake_time",
        "question": "你一般几点起床？（方便我安排提醒）",
        "hint": "比如：7:30、8点",
        "parser": "_parse_time",
    },
    {
        "key": "work_start",
        "question": "你一般几点到公司？",
        "hint": "比如：9:00、9点半",
        "parser": "_parse_time",
    },
]

_COMPLETE_MESSAGE = """✅ 身份注册完成！我已经记住了你的信息：

{summary}

现在你可以：
• 告诉我你的日程，我帮你规划最优路线
• 问我天气、路线
• 说「注册身份」随时修改信息

开始使用吧！🚀"""


class OnboardingFlow:
    """用户注册引导流程管理器"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.profile = get_user_profile(user_id)
        self.current_step = 0
        self._load_progress()

    def _load_progress(self):
        """从用户画像恢复进度，含有效性校验"""
        import re
        p = self.profile._data.get("profile", {})

        def _is_valid_address(addr):
            """地址必须含地点特征词，否则视为无效"""
            if not addr or not isinstance(addr, str):
                return False
            return bool(re.search(r'[省市区县路街巷镇号楼层室乡镇村屯号大道高架桥]', addr))

        # 根据已填字段跳过步骤
        for i, step in enumerate(_ONBOARDING_STEPS):
            key = step["key"]
            if key == "name" and p.get("name"):
                self.current_step = min(i + 1, len(_ONBOARDING_STEPS))
            elif key == "home" and _is_valid_address(p.get("home", {}).get("address", "")):
                self.current_step = min(i + 1, len(_ONBOARDING_STEPS))
            elif key == "work" and _is_valid_address(p.get("work", {}).get("address", "")):
                self.current_step = min(i + 1, len(_ONBOARDING_STEPS))
            elif key == "transport" and p.get("preferences", {}).get("transport"):
                self.current_step = min(i + 1, len(_ONBOARDING_STEPS))
            elif key == "wake_time" and p.get("preferences", {}).get("wake_time"):
                self.current_step = min(i + 1, len(_ONBOARDING_STEPS))
            elif key == "work_start" and p.get("preferences", {}).get("work_start"):
                self.current_step = min(i + 1, len(_ONBOARDING_STEPS))

    def is_complete(self) -> bool:
        """注册流程是否完成"""
        return self.current_step >= len(_ONBOARDING_STEPS)

    def is_active(self) -> bool:
        """是否有信息缺失（需要注册/补全）"""
        return not self.is_complete()

    def get_next_question(self) -> Optional[str]:
        """获取下一个引导问题"""
        if self.is_complete():
            return None
        step = _ONBOARDING_STEPS[self.current_step]
        return f"{step['question']}\n\n💡 {step['hint']}"

    def handle_message(self, text: str) -> Optional[str]:
        """
        处理用户在注册流程中的回复。
        返回给用户的回复文本；如果消息与注册无关则返回 None，让调用方走正常对话。
        """
        if self.is_complete():
            return None

        text = text.strip()

        # 用户明确说跳过 → 直接完成 onboarding
        if text in ("跳过", "skip", "跳过注册", "不用了", "稍后", "以后再说"):
            self.current_step = len(_ONBOARDING_STEPS)
            self.profile.save()
            return "好的，随时可以告诉我你的信息，我帮你记着 🙂"

        step = _ONBOARDING_STEPS[self.current_step]
        parser_name = step["parser"]
        parser = getattr(self, parser_name)

        # 解析用户输入
        parsed = parser(text)
        if parsed is None:
            # 解析失败 — 不强迫用户，放行到正常对话
            return None

        # 保存到用户画像
        self._save_field(step["key"], parsed)
        self.current_step += 1

        # 添加记忆
        self.profile.add_memory(f"设置{step['key']}: {str(parsed)[:30]}", category="profile")
        self.profile.save()

        # 检查是否完成
        if self.is_complete():
            return self._build_complete_message()

        # 返回下一个问题
        next_step = _ONBOARDING_STEPS[self.current_step]
        return f"✅ 记住了！\n\n{next_step['question']}\n\n💡 {next_step['hint']}"

    def _save_field(self, key: str, value):
        """保存字段到用户画像"""
        if key == "name":
            self.profile.set_name(value)
        elif key == "home":
            self.profile.set_home(value)
        elif key == "work":
            self.profile.set_work(value)
        elif key == "transport":
            self.profile.set_preference("transport", value)
        elif key == "wake_time":
            self.profile.set_preference("wake_time", value)
        elif key == "work_start":
            self.profile.set_preference("work_start", value)

    def _build_complete_message(self) -> str:
        """构建完成消息"""
        ctx = self.profile.build_context()
        return _COMPLETE_MESSAGE.format(summary=ctx)

    # ── 输入解析器 ──

    @staticmethod
    def _parse_name(text: str) -> Optional[str]:
        """解析称呼 — 必须像个人名，不能是聊天句子"""
        text = text.strip()
        text = text.rstrip('。！，,')
        # 太短或太长直接拒绝
        if len(text) < 1 or len(text) > 10:
            return None
        # 不能包含常见动词/疑问词/标点（说明是句子不是名字）
        if re.search(r'[去要想看发带在和吗呢吧啊哦嗯？?！!，,。；;：:的把被从到对给向往跟与及对但而或因为所以如果就虽然然则而且并且将让给被让给向往跟与及对但而或因为所以如果就虽然然则而且并且]', text):
            return None
        # 去除前缀
        text = re.sub(r'^(我叫|我是|叫我|称呼我|可以?叫?我)', '', text).strip()
        if len(text) < 1 or len(text) > 10:
            return None
        return text

    @staticmethod
    def _parse_address(text: str) -> Optional[str]:
        """解析地址 — 必须有地点特征词，避免聊天文字被误判"""
        text = text.strip()
        text = text.rstrip('。！，,')
        # 太短直接拒绝
        if len(text) < 4:
            return None
        # 必须包含地点特征：省市区县路街道号楼层室镇乡屯村号
        if not re.search(r'[省市区县路街巷镇号楼层室乡镇村屯号大道高架桥]', text):
            return None
        # 去除常见前缀
        text = re.sub(r'^(我家是?|我家?|公司地址?是?|公司|在|地址是?|住址是?|位于)', '', text).strip()
        if len(text) < 4:
            return None
        return text

    @staticmethod
    def _parse_transport(text: str) -> Optional[str]:
        """解析出行方式"""
        mapping = {
            "开车": "drive", "驾车": "drive", "车": "drive", "自驾": "drive",
            "地铁": "subway", "轨道交通": "subway",
            "公交": "bus", "公交车": "bus",
            "步行": "walk", "走路": "walk",
            "骑车": "bike", "自行车": "bike", "共享单车": "bike",
            "摩托": "motor", "摩托车": "motor",
        }
        for key, val in mapping.items():
            if key in text:
                return val
        return None

    @staticmethod
    def _parse_time(text: str) -> Optional[str]:
        """解析时间（标准化为 HH:MM）"""
        text = text.strip()
        # 匹配 "7:30", "7点30", "7点半", "8:00", "8点"
        m = re.match(r'(\d{1,2})[点:](\d{1,2}|半)?', text)
        if m:
            hour = int(m.group(1))
            minute_str = m.group(2) if m.group(2) else "00"
            if minute_str == "半":
                minute = 30
            else:
                minute = int(minute_str)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"
        # 纯数字（如 "7" → "07:00"）
        m = re.match(r'^(\d{1,2})$', text)
        if m:
            hour = int(m.group(1))
            if 0 <= hour <= 23:
                return f"{hour:02d}:00"
        return None


# ── 全局注册流程管理 ──

_onboarding_sessions: Dict[str, OnboardingFlow] = {}


def get_onboarding(user_id: str) -> OnboardingFlow:
    """获取或创建用户的注册流程"""
    if user_id not in _onboarding_sessions:
        _onboarding_sessions[user_id] = OnboardingFlow(user_id)
    return _onboarding_sessions[user_id]


def is_onboarding(user_id: str) -> bool:
    """用户是否正在注册流程中"""
    flow = get_onboarding(user_id)
    # 刷新进度：如果用户通过其他渠道（如图片OCR）填写了信息，跳过已填步骤
    if flow.is_active():
        flow._load_progress()
    return flow.is_active()
