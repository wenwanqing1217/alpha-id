"""
找工作助手 —— TwinBrain 的"求职者大脑"

与招聘软件（BOSS直聘、猎聘、拉勾等）交互，实现：
1. 定时截图监控消息
2. LLM 视觉分析新消息
3. 智能生成回复
4. 自动点击发送

使用方法：
    python -m src.agents.job_hunter --app "BOSS直聘"
"""

import os
import json
import time
import argparse
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

# 兼容本地运行：有 langchain 则用 @tool，没有则用空装饰器
try:
    from langchain.tools import tool
except ImportError:
    def tool(func=None, **kwargs):
        if func is not None:
            return func
        def decorator(f):
            return f
        return decorator

# ── 配置 ──

DEFAULT_APP_NAMES = ["BOSS直聘"]  # 默认监控的招聘软件列表

SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "screenshots"
)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

JOB_HUNTER_MEMORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "job_hunter_memory"
)
os.makedirs(JOB_HUNTER_MEMORY_DIR, exist_ok=True)


# ── 简历画像 ──

@dataclass
class ResumeProfile:
    """你的个人画像，供 HR 回复参考"""
    name: str = ""
    years_exp: int = 0
    skills: List[str] = field(default_factory=list)
    target_positions: List[str] = field(default_factory=list)
    target_cities: List[str] = field(default_factory=list)
    current_salary: str = ""
    expected_salary: str = ""
    education: str = ""
    highlights: List[str] = field(default_factory=list)  # 亮点经历
    tags: List[str] = field(default_factory=list)  # 标签，用于简历-岗位匹配（如 ["后端","云原生","Go"]）

    def to_context(self) -> str:
        """转成给 LLM 看的上下文"""
        parts = []
        if self.name:
            parts.append(f"姓名: {self.name}")
        if self.years_exp:
            parts.append(f"工作经验: {self.years_exp} 年")
        if self.skills:
            parts.append(f"技能: {'、'.join(self.skills)}")
        if self.target_positions:
            parts.append(f"目标职位: {'、'.join(self.target_positions)}")
        if self.target_cities:
            parts.append(f"目标城市: {'、'.join(self.target_cities)}")
        if self.expected_salary:
            parts.append(f"期望薪资: {self.expected_salary}")
        if self.education:
            parts.append(f"学历: {self.education}")
        if self.highlights:
            parts.append(f"亮点: {'; '.join(self.highlights)}")
        return "\n".join(parts)

    def tailor_for_jd(self, jd_text: str, jd_title: str = "") -> str:
        """
        根据岗位描述（JD）筛选简历中最相关的部分。

        策略：
        - 提取 JD 中的关键词（技能、行业术语）
        - 只保留与 JD 匹配的技能
        - 按匹配度排序亮点，取最相关的 2 个
        - 整体上下文限定在 JD 方向上

        返回：精炼后的简历上下文（< 300 字符）
        """
        import re

        # 提取 JD 关键词做小写集合：分别匹配中英文，避免粘连
        jd_lower = jd_text.lower() + " " + jd_title.lower()
        jd_words = set(re.findall(r'[a-zA-Z0-9+\-#]{2,}|[\u4e00-\u9fff]{2,}', jd_lower))

        # 1. 筛选技能：只保留 JD 里提到的
        matched_skills = []
        for skill in self.skills:
            skill_lower = skill.lower()
            # 检查 JD 中是否包含这个技能（单词或汉字完全匹配）
            if any(word in skill_lower or skill_lower in word for word in jd_words):
                matched_skills.append(skill)
            # 也检查常用技能缩写
            elif skill_lower in ("k8s", "k8s/kubernetes") and any("k8s" in w or "kubernetes" in w for w in jd_words):
                matched_skills.append(skill)
            elif skill_lower == "ml/dl" and any(w in ("机器学习", "深度学习", "ai", "ml") for w in jd_words):
                matched_skills.append(skill)

        # 如果没匹配到任何技能，退回到全部（JD 信息太少时）
        if not matched_skills:
            matched_skills = self.skills[:5]  # 最多 5 个

        # 2. 筛选亮点：按 JD 关键词匹配度排序
        scored_highlights = []
        for hl in self.highlights:
            hl_lower = hl.lower()
            score = sum(1 for word in jd_words if word in hl_lower)
            scored_highlights.append((score, hl))
        scored_highlights.sort(key=lambda x: -x[0])
        top_highlights = [hl for _, hl in scored_highlights[:2]]

        # 3. 构建精简上下文
        parts = []
        if self.years_exp:
            parts.append(f"经验: {self.years_exp}年")
        if matched_skills:
            prefix = "相关技能"
            if len(matched_skills) < len(self.skills):
                prefix = f"相关技能（针对 {jd_title or '该岗位'} 筛出）"
            parts.append(f"{prefix}: {'、'.join(matched_skills)}")
        if self.education:
            parts.append(f"学历: {self.education}")
        if top_highlights:
            parts.append(f"相关经历: {'; '.join(top_highlights)}")
        if self.expected_salary:
            parts.append(f"期望: {self.expected_salary}")

        result = "\n".join(parts)
        return result[:600]  # 截断避免刷爆 prompt


# ── HR 回复场景模板 ──

HR_REPLY_TEMPLATES = {
    "first_greeting": {
        "label": "HR 主动打招呼",
        "hint": "对方先发消息问候，需要礼貌回应并表达兴趣",
        "strategy": "感谢关注 + 确认兴趣 + 问一个开放问题",
    },
    "resume_sent": {
        "label": "已投简历未读/已读未回",
        "hint": "已投递简历但 HR 没有回复",
        "strategy": "简短提醒 + 补充一个相关亮点 + 表达加入意愿",
    },
    "interview_invite": {
        "label": "面试邀请",
        "hint": "HR 邀请面试",
        "strategy": "确认时间 + 了解面试形式/流程 + 感谢",
    },
    "tech_chat": {
        "label": "技术交流",
        "hint": "HR 或技术负责人聊技术细节",
        "strategy": "展示专业深度 + 反问团队技术栈/项目方向",
    },
    "salary_negotiate": {
        "label": "薪资谈判",
        "hint": "谈薪资待遇",
        "strategy": "先了解对方预算范围 + 给出合理预期范围 + 表达灵活度",
    },
    "rejection": {
        "label": "拒绝/不合适",
        "hint": "被拒了",
        "strategy": "礼貌感谢 + 询问具体原因 + 请求后续机会关注",
    },
}

# 默认回复风格偏好
REPLY_STYLES = {
    "professional": "专业得体，用词准确，结构清晰",
    "friendly": "友善随和，适当口语化，拉近距离",
    "detailed": "详细具体，充分展示项目经验和技术深度",
    "concise": "简短有力，直击重点，不拖泥带水",
}

DEFAULT_REPLY_STYLE = "professional"


# ── 数据模型 ──

@dataclass
class JobPosting:
    """
    职位信息——从截图分析或未来 API 搜索中提取的结构化数据。

    参考自行业标准（BOSS直聘、猎聘等通用字段），
    但专为我们的 vision-based 场景设计。
    """
    title: str = ""              # 职位名称
    company: str = ""            # 公司名称
    salary: str = ""             # 薪资范围，如 "25K-50K"
    city: str = ""               # 城市
    district: str = ""           # 区域
    experience: str = ""         # 经验要求，如 "3-5年"
    education: str = ""          # 学历要求，如 "本科"
    skills: List[str] = field(default_factory=list)    # 技能列表
    welfare: List[str] = field(default_factory=list)   # 福利标签
    industry: str = ""           # 行业
    scale: str = ""              # 公司规模，如 "100-499人"
    stage: str = ""              # 融资阶段，如 "C轮"
    boss_name: str = ""          # 招聘者姓名
    boss_title: str = ""         # 招聘者职位
    desc_snippet: str = ""       # 职位描述片段
    source: str = "vision"       # 数据来源: "vision" | "api" | "manual"

    def to_context(self) -> str:
        """压缩成给 LLM 看的单行上下文"""
        parts = []
        if self.title:
            parts.append(f"职位: {self.title}")
        if self.company:
            parts.append(f"公司: {self.company}")
        if self.salary:
            parts.append(f"薪资: {self.salary}")
        if self.city:
            parts.append(f"城市: {self.city}")
        if self.experience:
            parts.append(f"经验: {self.experience}")
        if self.education:
            parts.append(f"学历: {self.education}")
        if self.skills:
            parts.append(f"技能: {'、'.join(self.skills[:5])}")
        if self.industry:
            parts.append(f"行业: {self.industry}")
        if self.desc_snippet:
            parts.append(f"描述: {self.desc_snippet[:80]}...")
        return " | ".join(parts)

    @classmethod
    def from_analysis(cls, data: Dict[str, Any]) -> "JobPosting":
        """从 VisionAnalyzer 截图分析结果中提取职位信息"""
        return cls(
            title=data.get("position", data.get("title", "")),
            company=data.get("company", ""),
            salary=data.get("salary", ""),
            city=data.get("city", ""),
            skills=data.get("skills", []),
            experience=data.get("experience", ""),
            education=data.get("education", ""),
            welfare=data.get("welfare", []),
            industry=data.get("industry", ""),
            scale=data.get("scale", ""),
            stage=data.get("stage", ""),
            boss_name=data.get("recruiter_name", data.get("boss_name", "")),
            boss_title=data.get("recruiter_title", data.get("boss_title", "")),
            desc_snippet=data.get("jd_snippet", data.get("description", "")),
            source="vision",
        )

@dataclass
class JobConversation:
    """与一位 HR/招聘者的对话记录"""
    company: str = ""
    position: str = ""
    jd_text: str = ""  # 岗位描述（JD），用于按需筛选简历技能
    recruiter_name: str = ""
    messages: List[Dict[str, str]] = field(default_factory=list)
    status: str = "new"  # new / chatting / interview_invited / rejected / offer / archived
    last_scan_time: float = 0.0
    posting: Optional[JobPosting] = None  # 关联的结构化职位信息

    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.last_scan_time = time.time()

    def summary(self) -> str:
        jd_tag = f" | JD: {self.jd_text[:50]}..." if self.jd_text else ""
        return (
            f"🏢 {self.company} - {self.position}\n"
            f"   HR: {self.recruiter_name} | 状态: {self.status}{jd_tag}\n"
            f"   消息数: {len(self.messages)} | 最近: {self.messages[-1]['time'] if self.messages else '无'}"
        )


# ── LLM 分析客户端 ──

class _OpenAIFallbackClient:
    """包装 ChatOpenAI，适配 Coze LLMClient 的 invoke(model=..., temperature=...) 签名"""
    def __init__(self, model, api_key, base_url):
        from langchain_openai import ChatOpenAI
        self._model = model
        self._default_temp = 0.7
        self._llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=self._default_temp,
        )

    def invoke(self, messages, model=None, temperature=0.7):
        llm = self._llm
        if abs(temperature - self._default_temp) > 0.01:
            llm = self._llm.bind(temperature=temperature)
        return llm.invoke(messages)


class VisionAnalyzer:
    """用 LLM-vision 分析截图内容"""

    def __init__(self):
        self._llm_client = None

    def _get_client(self):
        if self._llm_client is None:
            # 策略1: Coze 原生 SDK（生产环境）
            try:
                from coze_coding_dev_sdk import LLMClient
                from coze_coding_utils.runtime_ctx.context import new_context
                self._llm_client = LLMClient(ctx=new_context(method="job_hunter_vision"))
                return self._llm_client
            except ImportError:
                pass

            # 策略2: OpenAI 兼容 API（本地开发/调试）
            api_key = (
                os.getenv("OPENAI_API_KEY")
                or os.getenv("DASHSCOPE_API_KEY")
                or os.getenv("QWEN_API_KEY")
            )
            base_url = (
                os.getenv("OPENAI_BASE_URL")
                or os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            )
            model = os.getenv("LLM_VISION_MODEL", "qwen-vl-max")

            if api_key:
                try:
                    from langchain_openai import ChatOpenAI
                    self._llm_client = _OpenAIFallbackClient(
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                    )
                    return self._llm_client
                except ImportError:
                    raise ImportError(
                        "缺少 langchain-openai 依赖。\n"
                        "请安装: pip install langchain-openai\n"
                        "或用 Coze 环境运行。"
                    )

            raise ImportError(
                "未找到任何 LLM 配置。\n"
                "请选择一种方式：\n"
                "1. 在 Coze 环境下运行（自动加载 coze_coding_dev_sdk）\n"
                "2. 设置环境变量: OPENAI_API_KEY + OPENAI_BASE_URL（本地开发）\n"
                "   示例: set OPENAI_API_KEY=sk-xxx && set OPENAI_BASE_URL=https://api.openai.com/v1"
            )
        return self._llm_client

    def analyze_screenshot(self, image_path: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        分析截图，提取招聘软件界面信息。

        返回：
        {
            "has_new_messages": bool,
            "conversations": [
                {
                    "company": str,
                    "position": str,
                    "unread_count": int,
                    "last_message_snippet": str,
                    "location_on_screen": {"x": int, "y": int, "w": int, "h": int}  # 可选
                }
            ],
            "current_view": str,   # 当前在哪个页面
            "notifications": [...]
        }
        """
        client = self._get_client()

        prompt = """你是一个招聘软件界面分析专家。请分析这张截图，提取以下信息：

1. **当前页面**（首页/消息列表/聊天窗口/个人中心/搜索页）
2. **新消息提醒**：有没有未读消息？有几条？来自哪些公司？
3. **对话列表**：列出所有可见的对话条目（公司名、职位、最后一条消息片段）
4. **未读标记**：哪些对话有红点/数字标记？

请以纯 JSON 格式返回，不要额外文字：
{
    "current_view": "消息列表",
    "total_unread": 3,
    "new_messages": false,
    "conversations": [
        {
            "company": "字节跳动",
            "position": "后端开发",
            "unread_count": 1,
            "last_message_snippet": "您好，看到您的简历..."
        }
    ],
    "notifications": [],
    "window_info": "当前是聊天窗口还是列表页"
}

注意：
- new_messages 表示是否有 *新出现* 的消息（与上次扫描相比）
- 如果无法识别，对应字段设为 null
"""
        if context:
            prompt += f"\n\n上次扫描的上下文：{context}"

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content="你是一个专业的招聘软件界面分析助手。"),
                HumanMessage(content=[
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"file://{image_path}"}}
                ])
            ]

            response = client.invoke(
                messages=messages,
                model="doubao-seed-1-6-vision-250815",
                temperature=0.1
            )

            content = response.content
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = " ".join(text_parts)

            if isinstance(content, str):
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                if "{" in content and "}" in content:
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    content = content[start:end]

                result = json.loads(content)
                result["_raw_file"] = image_path
                return result

            return {"error": f"无法解析LLM响应: {str(content)[:200]}"}

        except Exception as e:
            return {"error": f"分析失败: {str(e)}"}

    def generate_reply(self, company: str, position: str,
                       recruiter_message: str, my_profile: str = "",
                       scene: str = "first_greeting",
                       style: str = "professional",
                       num_options: int = 2) -> str:
        """
        根据 HR 的消息，生成回复话术（支持场景模板 + 多方案）。

        参数：
            company: 公司名称
            position: 职位名称
            recruiter_message: HR 发来的消息原文
            my_profile: 个人简介/简历摘要（可选）
            scene: 场景键名（见 HR_REPLY_TEMPLATES）
            style: 回复风格键名（见 REPLY_STYLES）
            num_options: 生成几个备选方案（1-3）

        返回：建议的回复文本（多个方案用 --- 分隔）
        """
        client = self._get_client()

        # 获取场景模板
        template = HR_REPLY_TEMPLATES.get(scene, HR_REPLY_TEMPLATES["first_greeting"])
        style_desc = REPLY_STYLES.get(style, REPLY_STYLES["professional"])

        prompt = f"""你是一个求职者，收到一位 HR 关于以下职位的信息。

公司：{company}
职位：{position}
HR 消息：{recruiter_message}

【场景判断】
当前场景：{template['label']}
场景说明：{template['hint']}
推荐策略：{template['strategy']}

【回复要求】
1. 语气礼貌但不卑微，有底气
2. 体现对职位和公司的兴趣
3. 可适当询问岗位细节（技术栈、团队规模、项目方向等）
4. {'每个方案不超过 100 字' if num_options == 1 else f'每个方案不超过 80 字，共 {num_options} 个不同角度的方案'}
5. 不要使用表情符号
6. 风格：{style_desc}

"""
        if my_profile:
            prompt += f"\n【你的背景】（回复中自然融入这些信息，不要生硬罗列）：\n{my_profile}\n"

        if num_options > 1:
            prompt += f"\n请提供 {num_options} 个不同侧重点的回复方案，用 --- 分隔。每个方案开头标注「方案1」「方案2」等。"

        try:
            from langchain_core.messages import HumanMessage

            messages = [
                HumanMessage(content=[
                    {"type": "text", "text": prompt}
                ])
            ]

            response = client.invoke(
                messages=messages,
                model="doubao-seed-1-6-vision-250815",
                temperature=0.7
            )

            content = response.content
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = " ".join(text_parts)

            return content.strip() if isinstance(content, str) else str(content)

        except Exception as e:
            return f"抱歉，我暂时无法回复。请问能再发一遍吗？（生成回复出错: {str(e)}）"

    def detect_scene(self, recruiter_message: str) -> str:
        """
        根据 HR 消息内容自动判断场景。
        简单关键词匹配，不用 LLM（快）。
        """
        msg = recruiter_message.lower()

        # 拒绝/不合适
        if any(kw in msg for kw in ["不合适", "不匹配", "很遗憾", "暂不考虑", "没有通过", "fail"]):
            return "rejection"

        # 面试邀请
        if any(kw in msg for kw in ["面试", "面谈", "来聊聊", "来公司", "安排一下", "约个时间", "什么时候方便"]):
            return "interview_invite"

        # 薪资谈判
        if any(kw in msg for kw in ["薪资", "待遇", "薪酬", "期望多少", "工资", "package", "总包"]):
            return "salary_negotiate"

        # 技术交流
        if any(kw in msg for kw in ["技术栈", "项目经验", "做过", "熟悉", "框架", "语言", "后端", "前端"]):
            return "tech_chat"

        # 已投简历未回（对方已读但没回复，或者消息历史中有简历投递记录）
        if any(kw in msg for kw in ["收到简历", "已读", "看看"]):
            return "resume_sent"

        # 默认——主动打招呼
        return "first_greeting"

    def generate_profile_from_jd(self, jd_text: str, position: str = "") -> Optional[str]:
        """
        根据岗位描述（JD）自动生成一份匹配的简历 JSON。
        用户保存后即可加入简历库。

        返回：ResumeProfile 的 JSON 字符串，或 None（出错时）
        """
        client = self._get_client()
        prompt = f"""你是一个猎头顾问。请根据以下岗位 JD，生成一份"理想候选人"的简历画像。

【岗位名称】{position or '（未指定）'}
【岗位描述】
{jd_text[:1500]}

请严格按照以下 JSON 格式输出，不要加任何额外文字：
{{
  "name": "",
  "years_exp": <整型，JD 要求的经验年数>,
  "skills": ["技能1", "技能2", ...],
  "target_positions": ["{position}", ...],
  "target_cities": [],
  "current_salary": "",
  "expected_salary": "<JD 提供的薪资范围>",
  "education": "<JD 要求的学历>",
  "tags": ["标签1", "标签2", ...],
  "highlights": ["与 JD 最相关的亮点经历（3 条，用 LLM 模拟）"]
}}

要求：
- skills 只保留 & 扩展 JD 里明确提到的技术栈（包括团队协作/项目管理等软技能）
- tags 用 3-5 个关键词概括这个方向（如 ["后端","Go","云原生"]）
- highlights 写 3 条让 HR 眼前一亮的项目经历，语气真实具体
- 字段值留空用空字符串，不要 null
"""
        try:
            from langchain_core.messages import HumanMessage

            messages = [
                HumanMessage(content=[{"type": "text", "text": prompt}])
            ]

            response = client.invoke(
                messages=messages,
                model="doubao-seed-1-6-vision-250815",
                temperature=0.3
            )
            content = response.content
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = " ".join(text_parts)

            if isinstance(content, str):
                content = content.strip()
                # 提取 JSON
                if "{" in content and "}" in content:
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    json_str = content[start:end]
                    # 验证可解析
                    json.loads(json_str)
                    return json_str

            return None

        except Exception as e:
            print(f"⚠️  JD 简历生成失败: {e}")
            return None


# ── 分析聊天窗口（进阶功能） ──

class ChatWindowAnalyzer:
    """分析聊天窗口内的具体对话内容"""

    def __init__(self, vision_analyzer: VisionAnalyzer):
        self.vision = vision_analyzer

    def analyze_chat(self, image_path: str) -> Dict[str, Any]:
        """
        分析聊天窗口截图，提取对话历史。

        返回：
        {
            "conversation": [
                {"role": "hr/me", "content": "...", "time": "..."}
            ],
            "last_message": "最后一条消息内容",
            "last_sender": "hr/me",
            "has_input": bool,   # 输入框里有没有已经打好的字
            "input_text": ""     # 输入框内的文本
        }
        """
        client = self.vision._get_client()
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            prompt = """请分析这张招聘软件聊天截图，提取完整的对话记录。

以 JSON 格式返回：
{
    "contact_name": "对方名称",
    "company": "公司名",
    "position": "职位名",
    "conversation": [
        {"role": "hr", "content": "您好，看到您的简历...", "time": "10:30"},
        {"role": "me", "content": "你好，我对这个职位感兴趣", "time": "10:31"}
    ],
    "input_box_text": "输入框里已有的文字（如果有的话）",
    "last_message_from": "hr/me"
}

注意：
- role: hr 表示对方/HR, me 表示自己
- 对话按从旧到新排列
- 如果截图中看不到某些信息，对应字段设为 null
"""

            messages = [
                SystemMessage(content="你是一个聊天记录分析助手。"),
                HumanMessage(content=[
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"file://{image_path}"}}
                ])
            ]

            response = client.invoke(
                messages=messages,
                model="doubao-seed-1-6-vision-250815",
                temperature=0.1
            )

            content = response.content
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = " ".join(text_parts)

            if isinstance(content, str):
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                if "{" in content and "}" in content:
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    content = content[start:end]
                return json.loads(content)

            return {"error": f"无法解析: {str(content)[:200]}"}

        except Exception as e:
            return {"error": f"分析聊天窗口失败: {str(e)}"}


# ── 记忆管理 ──

class JobHunterMemory:
    """持久化保存对话记忆"""

    def __init__(self, memory_dir: str = JOB_HUNTER_MEMORY_DIR):
        self.memory_dir = memory_dir
        self._conversations: Dict[str, JobConversation] = {}
        self._load()

    def _filepath(self) -> str:
        return os.path.join(self.memory_dir, "conversations.json")

    def _log_path(self) -> str:
        """JSONL 操作日志路径——按日期分文件"""
        date_str = datetime.now().strftime("%Y%m%d")
        return os.path.join(self.memory_dir, f"actions_{date_str}.jsonl")

    def log_event(self, event_type: str, data: Dict[str, Any]):
        """写入一行 JSONL 日志（审计追踪）"""
        import json as _json
        record = {
            "time": datetime.now().isoformat(),
            "type": event_type,
            **data
        }
        try:
            with open(self._log_path(), "a", encoding="utf-8") as f:
                f.write(_json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 日志写入失败不影响主流程

    def _load(self):
        path = self._filepath()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key, val in data.items():
                    self._conversations[key] = JobConversation(**val)
            except Exception:
                self._conversations = {}

    def save(self):
        data = {k: asdict(v) for k, v in self._conversations.items()}
        with open(self._filepath(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 同时写 JSONL 日志
        self.log_event("state_save", {"conv_count": len(self._conversations)})

    def get_or_create(self, company: str, position: str = "") -> JobConversation:
        key = f"{company}|{position}"
        if key not in self._conversations:
            self._conversations[key] = JobConversation(company=company, position=position)
        return self._conversations[key]

    def get_all(self) -> List[JobConversation]:
        return list(self._conversations.values())

    def get_unreplied(self) -> List[JobConversation]:
        """获取需要回复的对话（最后一条是 HR 发的，且我没回）"""
        unreplied = []
        for conv in self._conversations.values():
            if conv.messages and conv.messages[-1]["role"] == "hr":
                unreplied.append(conv)
        return unreplied

    def summary(self) -> str:
        convs = self.get_all()
        if not convs:
            return "📭 暂无对话记录"
        lines = ["📋 找工作对话记录：", "─" * 50]
        for i, c in enumerate(convs, 1):
            lines.append(f"{i}. {c.summary()}")
        unreplied = self.get_unreplied()
        if unreplied:
            lines.append(f"\n⚠️  有 {len(unreplied)} 条未回复的对话：")
            for c in unreplied:
                lines.append(f"   - {c.company} {c.position}: {c.messages[-1]['content'][:50]}...")
        return "\n".join(lines)


# ── 主 Agent ──

class JobHunterAgent:
    """
    找工作助手主控器

    使用流程：
        1. scan()      — 截图+分析，发现新消息
        2. analyze()   — 查看具体对话内容
        3. reply()     — 生成回复+发送
        4. interactive() — 全自动交互循环
    """

    def __init__(self, app_name: Optional[str] = None, app_names: Optional[List[str]] = None, profile: Optional[ResumeProfile] = None, reply_style: str = DEFAULT_REPLY_STYLE, profiles_dir: Optional[str] = None):
        if app_names:
            self.app_names = app_names
        elif app_name:
            self.app_names = [app_name]
        else:
            self.app_names = DEFAULT_APP_NAMES[:]
        self.app_name = self.app_names[0]  # 默认用第一个
        self.profile = profile
        self.reply_style = reply_style
        self.profiles_dir = profiles_dir  # 多简历库目录
        self.profiles: Dict[str, ResumeProfile] = {}  # tag -> ResumeProfile
        if profiles_dir and os.path.isdir(profiles_dir):
            self._load_profiles_dir(profiles_dir)
        self.vision = VisionAnalyzer()
        self.chat_analyzer = ChatWindowAnalyzer(self.vision)
        self.memory = JobHunterMemory()
        self.last_scan_result = None
        self._tools_imported = False
        self._input_box_x = None
        self._input_box_y = None
        self._load_input_box_config()

    def _load_profiles_dir(self, profiles_dir: str):
        """加载多简历库目录下的所有简历"""
        import glob as _glob
        for fpath in _glob.glob(os.path.join(profiles_dir, "*.json")):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                p = ResumeProfile(**data)
                # 用文件名（不含后缀）作为 tag 键
                tag = os.path.splitext(os.path.basename(fpath))[0]
                self.profiles[tag] = p
                print(f"  📄 已加载简历 [{tag}]: {p.name or '匿名'} ({len(p.skills)} 技能)")
            except Exception as e:
                print(f"  ⚠️  跳过 {fpath}: {e}")
        if self.profiles:
            print(f"  ✅ 共加载 {len(self.profiles)} 份简历")

    def _match_profile(self, position: str, jd_text: str = "") -> Optional[ResumeProfile]:
        """
        根据职位名称和 JD 自动匹配合适的简历。

        策略：
        1. 用 position + jd_text 中的关键词
        2. 对每个简历计算匹配分数（技能匹配 + tag匹配 + target_position匹配）
        3. 返回最高分简历
        """
        if not self.profiles:
            return self.profile  # 没有多简历库，用单份

        if not position and not jd_text:
            return self.profile

        # 提取查询关键词
        import re
        query = (position + " " + jd_text).lower()
        keywords = set(re.findall(r'[a-zA-Z0-9+\-#]{2,}|[\u4e00-\u9fff]{2,}', query))

        best_score = -1
        best_profile: Optional[ResumeProfile] = None
        best_tag = ""

        for tag, p in self.profiles.items():
            score = 0
            # tag 匹配（文件名就是方向标签，如 "backend", "sre"）
            if any(kw in tag.lower() for kw in keywords):
                score += 5
            # 目标职位匹配
            for tp in p.target_positions:
                if any(kw in tp.lower() or tp.lower() in kw for kw in keywords):
                    score += 3
            # 技能匹配
            for skill in p.skills:
                if any(kw in skill.lower() or skill.lower() in kw for kw in keywords):
                    score += 2
            # tag 标签匹配
            for t in p.tags:
                if any(kw in t.lower() or t.lower() in kw for kw in keywords):
                    score += 4

            if score > best_score:
                best_score = score
                best_profile = p
                best_tag = tag

        if best_score > 0 and best_profile:
            print(f"  🎯 自动匹配简历: [{best_tag}] (得分 {best_score})")
            return best_profile
        return self.profile

    def _research_company(self, company_name: str) -> Optional[str]:
        """
        轻量公司背调。
        如果简历库中有该公司的记录则直接返回，否则返回基本信息提示。
        """
        if not company_name or company_name == "未知公司":
            return None

        # 检查简历库中是否有该公司的相关信息
        for tag, p in self.profiles.items():
            if company_name.lower() in tag.lower():
                return f"来自同类公司 [{tag}] 的匹配经验"

        # 简单提示，不阻塞流程
        return None

    def _suggest_interview_times(self) -> str:
        """
        根据当前时间，生成 2-3 个可用的面试时间段建议。
        """
        from datetime import timedelta

        today = datetime.now()
        suggestions = []
        for offset_days in [1, 2, 3]:
            day = today + timedelta(days=offset_days)
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            wd = weekday_names[day.weekday()]
            for hour in ["10:00", "14:00", "16:00"]:
                suggestions.append(f"{wd}（{day.month}/{day.day}）{hour}")

        # 返回前 3 个
        return "、".join(suggestions[:3])

    def _ensure_tools(self):
        """确保截图和窗口操作工具可用"""
        if not self._tools_imported:
            try:
                from tools import screen_capture, window_control
                self._screen_capture = screen_capture
                self._window_control = window_control
                self._tools_imported = True
            except ImportError as e:
                print(f"⚠️  工具导入失败（某些功能不可用）: {e}")
                print("   请安装依赖：pip install pyautogui pygetwindow pyperclip Pillow")
                print("   安装后重试即可。")

    def _load_input_box_config(self):
        """加载之前校准过的输入框坐标"""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "job_hunter_memory", "input_box.json"
        )
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._input_box_x = data.get("x")
                self._input_box_y = data.get("y")
                if self._input_box_x and self._input_box_y:
                    print(f"📌 已加载输入框坐标: ({self._input_box_x}, {self._input_box_y})")
            except Exception:
                pass

    def _take_screenshot(self, region: str = "window", app_name: Optional[str] = None) -> Optional[str]:
        """
        截图。支持：
        - "window": 截取招聘软件窗口
        - "full": 全屏
        - "manual": 用户手动截图（返回 None，让用户提供路径）
        """
        target = app_name or self.app_name
        self._ensure_tools()
        if not self._tools_imported:
            print("❌ 截图工具不可用，请安装依赖")
            return None

        try:
            if region == "full":
                result = self._screen_capture.capture_full_screen()
            else:
                result = self._screen_capture.capture_application_window(target)

            print(f"📸 {result}")

            # 从结果中提取文件路径
            if "截图已保存" in result:
                path_start = result.find(": ") + 2
                path = result[path_start:].strip()
                return path
            return None
        except Exception as e:
            print(f"❌ 截图失败: {e}")
            return None

    def scan(self, app_name: Optional[str] = None) -> Dict[str, Any]:
        """
        扫描招聘软件界面，发现有价值的消息。

        参数：
            app_name: 指定软件名（不指定则用 self.app_name）

        返回：
        {
            "success": bool,
            "has_new": bool,
            "conversations": [...],
            "current_view": "...",
            "screenshot_path": "..."
        }
        """
        target = app_name or self.app_name
        print(f"\n{'='*50}")
        print(f"🔍 扫描招聘软件: {target}")
        print(f"{'='*50}\n")

        # 1. 截图
        screenshot_path = self._take_screenshot("window", app_name=target)
        if not screenshot_path:
            return {"success": False, "error": "截图失败"}

        # 2. 用 LLM 视觉分析
        print("🧠 正在分析截图...")
        context = None
        if self.last_scan_result and "conversations" in self.last_scan_result:
            context = json.dumps(self.last_scan_result["conversations"], ensure_ascii=False)

        analysis = self.vision.analyze_screenshot(screenshot_path, context=context)
        analysis["screenshot_path"] = screenshot_path

        # 3. 检测是否有新消息
        has_new = analysis.get("new_messages", False) or analysis.get("total_unread", 0) > 0
        analysis["has_new"] = has_new

        # 4. 更新记忆
        for conv_data in analysis.get("conversations", []):
            company = conv_data.get("company", "未知公司")
            position = conv_data.get("position", "")
            conv = self.memory.get_or_create(company, position)
            if conv_data.get("last_message_snippet"):
                conv.add_message(
                    role="hr",
                    content=conv_data["last_message_snippet"]
                )
            # 关联结构化职位信息
            if not conv.posting:
                conv.posting = JobPosting.from_analysis(conv_data)

        self.memory.save()
        self.last_scan_result = analysis

        # 5. 打印摘要
        print(f"\n📊 扫描结果:")
        print(f"   页面: {analysis.get('current_view', '未知')}")
        print(f"   未读消息: {analysis.get('total_unread', 0)} 条")
        print(f"   对话数: {len(analysis.get('conversations', []))}")

        if analysis.get("new_messages"):
            print(f"\n🆕 检测到新消息!")
            for conv in analysis.get("conversations", []):
                if conv.get("unread_count", 0) > 0:
                    print(f"   - {conv.get('company', '?')} | {conv.get('position', '?')}")
        else:
            print("\n✅ 没有新消息")

        print(f"\n📸 截图: {screenshot_path}")

        return analysis

    def analyze_chat_window(self) -> Dict[str, Any]:
        """
        分析当前聊天窗口内容（假设已经打开了聊天窗口）。
        先截图裁出聊天区域，再分析对话内容。
        """
        screenshot_path = self._take_screenshot("window")
        if not screenshot_path:
            return {"success": False, "error": "截图失败"}

        print("🧠 正在分析聊天对话...")
        result = self.chat_analyzer.analyze_chat(screenshot_path)
        result["screenshot_path"] = screenshot_path

        # 打印对话摘要
        conversation = result.get("conversation", [])
        print(f"\n💬 对话记录 ({result.get('contact_name', '?')}):")
        print(f"   公司: {result.get('company', '?')} | 职位: {result.get('position', '?')}")
        for msg in conversation:
            prefix = "👤 HR" if msg.get("role") == "hr" else "🧑 我"
            print(f"   {prefix}: {msg.get('content', '')[:60]}")

        return result

    def generate_reply(self, company: str, position: str,
                       recruiter_message: str, my_profile: str = "",
                       scene: str = "",
                       style: str = "",
                       num_options: int = 2) -> str:
        """生成回复，自动判断场景，支持多方案"""
        if not scene:
            scene = self.vision.detect_scene(recruiter_message)
        if not style:
            style = self.reply_style

        print(f"\n✏️  正在为 {company} - {position} 生成回复...")
        print(f"   📌 场景: {HR_REPLY_TEMPLATES.get(scene, {}).get('label', '通用')}")
        print(f"   HR 说: {recruiter_message[:100]}")

        profile_text = self.profile.to_context() if self.profile else ""

        reply = self.vision.generate_reply(
            company=company,
            position=position,
            recruiter_message=recruiter_message,
            my_profile=profile_text,
            scene=scene,
            style=style,
            num_options=num_options
        )

        print(f"\n💡 建议回复 ({num_options} 个方案):\n{reply}\n")

        return reply

    def calibrate(self):
        """
        校准输入框位置。
        运行后把鼠标放在招聘软件输入框上，3 秒后会记录坐标。
        以后自动粘贴就能找到位置。
        """
        self._ensure_tools()
        if not self._tools_imported:
            print("❌ 需要 window_control 工具，先 pip install pyautogui pygetwindow")
            return

        print("🔧 输入框位置校准")
        print("   " + "─" * 40)
        print("   请把鼠标移动到 BOSS直聘 (或其他招聘软件) 的")
        print("   文字输入框上，保持不动。")
        print()
        print("   3 秒后自动记录坐标...")

        for i in range(3, 0, -1):
            print(f"   {i}...")
            time.sleep(1)

        x, y = self._window_control.get_mouse_position()
        print(f"\n✅ 当前鼠标坐标: ({x}, {y})")

        # 保存到配置
        self._input_box_x = x
        self._input_box_y = y

        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "job_hunter_memory", "input_box.json"
        )
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"x": x, "y": y}, f)
        print(f"📌 坐标已保存到: {config_path}")
        print("   以后自动发送时就会点这个位置。")

    def interactive_scan(self):
        """
        交互模式：一次扫描 + 人工选择 + 场景感知回复。
        扫描所有已配置的招聘软件。
        """
        results = self.scan_all()
        total_new = any(r.get("has_new") for r in results)

        if not total_new:
            print("\n💤 没有新消息")
            self._show_memory_and_options()
            return

        # 显示未回复对话（带场景标签）
        unreplied = self.memory.get_unreplied()
        if unreplied:
            print(f"\n📋 需要回复的对话:")
            for i, conv in enumerate(unreplied, 1):
                last_msg = conv.messages[-1]["content"]
                scene = self.vision.detect_scene(last_msg)
                scene_label = HR_REPLY_TEMPLATES.get(scene, {}).get("label", "通用")
                print(f"  {i}. {conv.company} - {conv.position}")
                print(f"     📌 {scene_label}")
                print(f"     HR: {last_msg[:60]}...")

            print(f"\n选择要回复的编号 (1-{len(unreplied)}), 或 0 跳过: ", end="")
            try:
                choice = int(input().strip())
                if 1 <= choice <= len(unreplied):
                    conv = unreplied[choice - 1]
                    self._handle_reply(conv)
            except (ValueError, IndexError):
                print("跳过")

        self.memory.save()

    def _show_memory_and_options(self):
        """没有新消息时显示记忆和可用操作"""
        print("\n📋 可用操作:")
        print("   m) 查看所有对话记录")
        print("   c) 校准输入框位置")
        print("   q) 退出")
        print("   enter) 继续扫描")

        cmd = input().strip().lower()
        if cmd == "m":
            print(self.memory.summary())
        elif cmd == "c":
            self.calibrate()
        elif cmd == "q":
            return
        else:
            # 再扫一次
            self.interactive_scan()

    def _handle_reply(self, conv: JobConversation):
        """处理回复流程：生成多个方案 → 用户选择 → 确认发送"""
        last_msg = conv.messages[-1]["content"]
        scene = self.vision.detect_scene(last_msg)
        scene_label = HR_REPLY_TEMPLATES.get(scene, {}).get("label", "通用")

        print(f"\n📌 识别场景: {scene_label}")

        # ── 公司背调查询（轻量版） ──
        company_info = self._research_company(conv.company)
        if company_info:
            print(f"  🏢 公司背景: {company_info}")

        # ── 面试时间自动协商 ──
        if scene == "interview_invite" and ("什么时候" in last_msg or "时间" in last_msg or "方便" in last_msg):
            suggested_times = self._suggest_interview_times()
            if suggested_times:
                print(f"  🗓 面试时间建议: {suggested_times}")

        # ── 简历匹配 + JD 筛选 ──
        profile = self._match_profile(conv.position, conv.jd_text) or self.profile
        profile_context = ""
        if profile:
            if conv.jd_text or conv.position:
                profile_context = profile.tailor_for_jd(conv.jd_text or "", conv.position)
                match_source = "JD 筛选" if conv.jd_text else "职位匹配"
                print(f"  📄 简历已按「{match_source}」定向调整（{len(profile_context)} 字符）")
            else:
                profile_context = profile.to_context()

        # 生成 2 个备选方案
        reply = self.generate_reply(
            conv.company, conv.position,
            last_msg,
            my_profile=profile_context,
            scene=scene,
            style=self.reply_style,
            num_options=2
        )

        # 解析方案
        options = []
        current = ""
        for line in reply.split("\n"):
            if line.startswith("方案") or line.startswith("—" * 3):
                if current.strip():
                    options.append(current.strip())
                current = line + "\n"
            else:
                current += line + "\n"
        if current.strip():
            options.append(current.strip())

        if not options:
            options = [reply.strip()]

        print(f"\n📝 备选方案 ({len(options)} 个):")
        for i, opt in enumerate(options, 1):
            print(f"\n  {'═' * 40}")
            print(f"  方案 {i}:\n")
            for line in opt.split("\n"):
                print(f"   {line}")

        print(f"\n{'─' * 40}")
        print(f"请选择:")
        print(f"   1-{len(options)}: 选择对应方案并发送")
        print(f"   e: 手动编辑后发送")
        print(f"   n: 重新生成")
        print(f"   s: 更换回复风格")
        print(f"   q: 跳过，下次再说")
        print(f"请选择 (1/{len(options)}/e/n/s/q): ", end="")

        cmd = input().strip().lower()

        if cmd in [str(i) for i in range(1, len(options) + 1)]:
            idx = int(cmd) - 1
            selected = options[idx]
            # 去掉方案标题行
            clean_lines = [l for l in selected.split("\n") if "方案" not in l]
            text = "\n".join(clean_lines).strip()
            self._send_or_edit(text, conv)
            self.memory.log_event("send_reply", {
                "company": conv.company,
                "position": conv.position,
                "scene": scene,
                "option_idx": idx,
                "length": len(text)
            })
        elif cmd == "e":
            print("\n请输入修改后的内容（直接回车取消）:")
            edited = input().strip()
            if edited:
                self._send_or_edit(edited, conv)
        elif cmd == "n":
            self._handle_reply(conv)
        elif cmd == "s":
            print(f"\n选择回复风格:")
            for k, v in REPLY_STYLES.items():
                print(f"   {k}: {v}")
            print(f"请输入风格 ({'/'.join(REPLY_STYLES.keys())}): ", end="")
            style = input().strip()
            if style in REPLY_STYLES:
                self.reply_style = style
                self._handle_reply(conv)
            else:
                print("无效风格，取消")
        else:
            print("⏭ 跳过")

    def _send_or_edit(self, text: str, conv: JobConversation):
        """确认并发送或修改"""
        print(f"\n📤 即将发送:")
        print(f"   {text}")
        print(f"\n确认发送？(y/n/e): ", end="")
        cmd = input().strip().lower()
        if cmd == "y":
            self._send_reply(text)
            conv.add_message(role="me", content=text)
            self.memory.save()
            self.memory.log_event("send_confirmed", {
                "company": conv.company, "position": conv.position, "length": len(text)
            })
            print("✅ 已发送")
        elif cmd == "e":
            print("请修改:")
            edited = input().strip()
            if edited:
                self._send_reply(edited)
                conv.add_message(role="me", content=edited)
                self.memory.save()
                print("✅ 已发送")
        else:
            print("⏭ 取消发送")

    def _send_reply(self, text: str):
        """发送回复：聚焦输入框 → 输入文本 → 回车发送"""
        self._ensure_tools()
        if not self._tools_imported:
            print(f"\n📝 请手动输入以下内容到招聘软件:\n{text}\n")
            return

        try:
            # 先激活窗口
            self._window_control.focus_application_window(self.app_name)

            print("⏳ 等待 1 秒...")
            time.sleep(1)

            # 点击输入框（假设在窗口底部区域）
            # 这是一个启发式位置，实际可能需要用户先用 get_mouse_position 定位
            # 或者在分析聊天窗口时从 LLM 获取准确坐标
            print("💡 如果没有自动输入，请手动点击输入框后按回车")

            # 先获取窗口位置
            info = self._window_control.focus_application_window(self.app_name)
            # 尝试点击窗口底部中央（输入框的常见位置）
            # 这个位置是猜测的，实际需要用户校准
            print(f"   尝试点击输入框区域...")

            # 打字发送（使用快捷键粘贴以支持中文）
            import pyperclip
            try:
                pyperclip.copy(text)
                time.sleep(0.2)
                self._window_control.press_key("ctrl+v")
                time.sleep(0.3)
                self._window_control.press_key("enter")
                print("✅ 已粘贴并发送")
            except ImportError:
                # 没有 pyperclip，用 type_text
                self._window_control.type_text(text)
                time.sleep(0.3)
                self._window_control.press_key("enter")

        except Exception as e:
            print(f"❌ 自动发送失败: {e}")
            print(f"\n📝 请手动输入以下内容:\n{text}\n")

    # ── 多平台扫描 ──

    def scan_all(self) -> List[Dict[str, Any]]:
        """
        扫描监控的所有招聘软件窗口。
        依次截取每个窗口 → 分析 → 聚合结果。
        """
        print(f"\n{'='*50}")
        print(f"🌐 多平台扫描: {' / '.join(self.app_names)}")
        print(f"{'='*50}\n")

        all_results = []
        for i, app in enumerate(self.app_names):
            print(f"\n{'─'*40}")
            print(f"  [{i+1}/{len(self.app_names)}] {app}")
            print(f"{'─'*40}")
            result = self.scan(app_name=app)
            all_results.append(result)

        total_new = any(r.get("has_new") for r in all_results)
        total_unread = sum(r.get("total_unread", 0) for r in all_results)

        print(f"\n{'='*50}")
        print(f"📊 多平台扫描完成")
        for i, app in enumerate(self.app_names):
            r = all_results[i]
            unread = r.get("total_unread", 0)
            nconv = len(r.get("conversations", []))
            mark = "🆕" if r.get("has_new") else "  "
            print(f"  {mark} {app}: {unread} 条未读, {nconv} 个对话")
        print(f"{'='*50}\n")

        return all_results

    # ── 自动回复执行器 ──

    def execute_reply(self, conv: JobConversation, silent: bool = False) -> Dict[str, Any]:
        """
        自动执行一次完整回复链路：分析场景→匹配简历→生成回复→发送→记录。

        参数：
            conv: 待回复的对话对象
            silent: 静默模式（不打印详细日志，用于守护模式）

        返回：
            {
                "success": bool,
                "reply": str,          # 实际发送的内容
                "scene": str,          # 识别到的场景
                "company": str,
                "position": str,
                "error": str | None,
            }
        """
        if not conv.messages:
            return {"success": False, "error": "无消息可回复", "reply": "", "scene": "",
                    "company": conv.company, "position": conv.position}

        last_msg = conv.messages[-1]["content"]
        scene = self.vision.detect_scene(last_msg)
        scene_label = HR_REPLY_TEMPLATES.get(scene, {}).get("label", "通用")

        if not silent:
            print(f"\n🔁 自动回复: {conv.company} - {conv.position}")
            print(f"   📌 场景: {scene_label}")
            print(f"   💬 HR 说: {last_msg[:80]}...")

        # 公司背景查询
        company_info = self._research_company(conv.company) if conv.company else None

        # 简历匹配 + 定向调整
        profile = self._match_profile(conv.position, conv.jd_text) or self.profile
        profile_context = ""
        if profile:
            if conv.jd_text or conv.position:
                profile_context = profile.tailor_for_jd(conv.jd_text or "", conv.position)
            else:
                profile_context = profile.to_context()

        # 面试时间协商
        suggested_times = ""
        if scene == "interview_invite" and ("什么时候" in last_msg or "时间" in last_msg or "方便" in last_msg):
            suggested_times = self._suggest_interview_times()

        # 生成回复（单方案，直接最佳）
        full_reply = self.generate_reply(
            conv.company, conv.position, last_msg,
            my_profile=profile_context,
            scene=scene,
            num_options=1
        )

        # 提取纯文本（去掉"方案1"等标题行）
        lines = [l for l in full_reply.split("\n") if "方案" not in l]
        clean_text = "\n".join(lines).strip()
        if not clean_text:
            clean_text = full_reply.strip()

        # 发送
        self._send_reply(clean_text)

        # 记录到对话历史
        conv.add_message(role="me", content=clean_text)
        self.memory.save()
        self.memory.log_event("execute_reply", {
            "company": conv.company,
            "position": conv.position,
            "scene": scene,
            "length": len(clean_text),
            "has_company_info": bool(company_info),
            "has_suggested_times": bool(suggested_times),
        })

        if not silent:
            print(f"   ✅ 已自动回复 ({len(clean_text)} 字符)")

        return {
            "success": True,
            "reply": clean_text,
            "scene": scene,
            "company": conv.company,
            "position": conv.position,
            "error": None,
        }

    # ── 守护模式 ──

    def daemon_loop(self, interval: int = 120, auto_send: bool = True):
        """
        守护模式：定时扫描招聘软件，有新消息时自动回复。

        参数：
            interval: 扫描间隔（秒），默认 120 秒（2 分钟）
            auto_send: 是否自动发送回复（False 则只扫描不自动发）
        """
        print(f"\n🔄 守护模式启动 | 扫描间隔: {interval//60} 分钟 | 自动发送: {'✅' if auto_send else '❌'}")
        print("   按 Ctrl+C 退出\n")

        while True:
            try:
                # 扫描所有平台
                self.scan_all()

                # 处理未回复对话
                unreplied = self.memory.get_unreplied()
                for conv in unreplied:
                    if auto_send:
                        # 使用 execute_reply 执行完整链路（含简历匹配+发送+记录）
                        result = self.execute_reply(conv, silent=True)
                        if result["success"]:
                            print(f"   ✅ 已自动回复 ({len(result['reply'])} 字符)")
                        else:
                            print(f"   ⚠️  {result.get('error', '回复失败')}")
                    else:
                        # 仅扫描不发送
                        last_msg = conv.messages[-1]["content"] if conv.messages else ""
                        scene = self.vision.detect_scene(last_msg)
                        print(f"   📌 [{conv.company}] {scene} | 未回复 (自动发送已关闭)")

                print(f"\n⏳ {interval//60} 分钟后再次扫描...")
                time.sleep(interval)

            except KeyboardInterrupt:
                print("\n👋 守护模式退出")
                break
            except Exception as e:
                print(f"\n⚠️  扫描异常: {e}")
                print(f"⏳ {interval//60} 分钟后重试...")
                time.sleep(interval)


# ── 命令行入口 ──

def main():
    parser = argparse.ArgumentParser(description="找工作助手 - TwinBrain Job Hunter")
    parser.add_argument("--app", action="append", dest="apps",
                        help=f"招聘软件窗口标题关键词（可多次指定，默认: {DEFAULT_APP_NAMES[0]}）如: --app BOSS直聘 --app 猎聘")
    parser.add_argument("--scan", action="store_true",
                        help="执行一次扫描后退出")
    parser.add_argument("--interactive", action="store_true", default=True,
                        help="进入交互模式（默认）")
    parser.add_argument("--list-windows", action="store_true",
                        help="列出当前桌面窗口")
    parser.add_argument("--calibrate", action="store_true",
                        help="校准输入框位置")
    parser.add_argument("--profile", type=str, default=None,
                        help="简历 JSON 文件路径")
    parser.add_argument("--resumes-dir", type=str, default=None,
                        help="多简历库目录（每个 JSON 文件按职位方向命名，如 backend.json / sre.json）")
    parser.add_argument("--style", type=str, default=DEFAULT_REPLY_STYLE,
                        choices=list(REPLY_STYLES.keys()),
                        help=f"回复风格 (默认: {DEFAULT_REPLY_STYLE})")
    parser.add_argument("--daemon", action="store_true",
                        help="守护模式：定时扫描并自动回复")
    parser.add_argument("--interval", type=int, default=120,
                        help="守护模式扫描间隔（秒），默认 120")
    parser.add_argument("--no-auto-send", action="store_true",
                        help="守护模式下只扫描不自动发送")

    args = parser.parse_args()

    print(r"""
   ╔═══════════════════════════════════════╗
   ║      🤖 找工作助手 v2.0              ║
   ║      TwinBrain × JobHunter            ║
   ╚═══════════════════════════════════════╝
    """)

    if args.list_windows:
        from tools.screen_capture import list_application_windows
        result = list_application_windows()
        print(result)
        return

    # 加载简历（可选）
    profile = None
    if args.profile:
        try:
            with open(args.profile, "r", encoding="utf-8") as f:
                data = json.load(f)
            profile = ResumeProfile(**data)
            print(f"✅ 已加载简历: {profile.name or '匿名'} (技能: {'、'.join(profile.skills[:3])}...)")
        except Exception as e:
            print(f"⚠️  简历加载失败: {e}")

    # 加载多简历库（优先于单份简历）
    profiles_dir = args.resumes_dir
    if not profiles_dir and args.profile:
        # 单份简历模式，不需要多简历库
        pass

    app_names = args.apps or DEFAULT_APP_NAMES
    agent = JobHunterAgent(app_names=app_names, profile=profile, reply_style=args.style, profiles_dir=profiles_dir)

    if args.calibrate:
        agent.calibrate()
        return

    if args.scan:
        agent.scan()
        return

    if args.daemon:
        agent.daemon_loop(interval=args.interval, auto_send=not args.no_auto_send)
        return

    # 交互模式
    print(f"🎯 监控软件: {' / '.join(app_names)}")
    print(f"   回复风格: {args.style}")
    if profile:
        print(f"   已绑定简历: {profile.name or '匿名'}")
    if profiles_dir:
        print(f"   多简历库: {profiles_dir} ({len(agent.profiles)} 份)")
    print(f"\n   输入命令: scan(s) / reply(r) / chat(c) / memory(m) / ")
    print(f"   windows(w) / calibrate / style / profile / resumes / daemon / help(h) / exit(q)\n")

    while True:
        try:
            cmd = input("🔧 > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 退出")
            break

        if cmd in ("exit", "quit", "q"):
            print("👋 退出")
            break

        elif cmd in ("scan", "s"):
            agent.scan_all()

        elif cmd in ("reply", "r"):
            unreplied = agent.memory.get_unreplied()
            if not unreplied:
                print("📭 没有需要回复的对话，先 scan 一下")
                continue
            print("\n📋 需要回复的对话:")
            for i, conv in enumerate(unreplied, 1):
                print(f"  {i}. {conv.company} - {conv.position}")
            print("选择编号: ", end="")
            try:
                choice = int(input().strip())
                if 1 <= choice <= len(unreplied):
                    agent._handle_reply(unreplied[choice - 1])
            except (ValueError, IndexError):
                print("无效选择")

        elif cmd in ("chat", "c"):
            agent.analyze_chat_window()

        elif cmd in ("memory", "m"):
            print(agent.memory.summary())

        elif cmd in ("windows", "w"):
            from tools.screen_capture import list_application_windows
            print(list_application_windows())

        elif cmd == "calibrate":
            agent.calibrate()

        elif cmd == "style":
            print(f"\n当前风格: {agent.reply_style}")
            print(f"可选风格: {', '.join(REPLY_STYLES.keys())}")
            print("输入新风格名称: ", end="")
            new_style = input().strip()
            if new_style in REPLY_STYLES:
                agent.reply_style = new_style
                print(f"✅ 已切换为: {new_style}")
            else:
                print("无效风格")

        elif cmd == "profile":
            """热更新简历"""
            print("输入简历 JSON 文件路径: ", end="")
            path = input().strip()
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                agent.profile = ResumeProfile(**data)
                print(f"✅ 简历已更新: {agent.profile.name or '匿名'}")
            except Exception as e:
                print(f"❌ 加载失败: {e}")

        elif cmd == "resumes":
            """查看已加载的简历库"""
            if not agent.profiles:
                print("📭 未加载多简历库（使用 --resumes-dir 启动，或先用 profile 命令加载）")
                continue
            print(f"\n📂 简历库 ({len(agent.profiles)} 份):")
            for tag, p in agent.profiles.items():
                print(f"\n  [{tag}]")
                print(f"   姓名: {p.name or '匿名'}")
                print(f"   经验: {p.years_exp}年" if p.years_exp else "")
                print(f"   技能: {', '.join(p.skills[:6])}{'...' if len(p.skills)>6 else ''}")
                print(f"   目标: {', '.join(p.target_positions[:3])}")
                if p.tags:
                    print(f"   标签: {', '.join(p.tags)}")
            print("\n输入简历名可查看详情，直接回车返回: ", end="")
            tag = input().strip()
            if tag in agent.profiles:
                p = agent.profiles[tag]
                print(f"\n📄 [{tag}] 完整简历:")
                print(p.to_context())

        elif cmd in ("help", "h"):
            print("""命令:
  scan(s)     — 截图分析新消息（所有已配置平台）
  reply(r)    — 回复未读消息（自动匹配简历 + JD 筛选）
  chat(c)     — 分析当前聊天窗口（可提取 JD）
  memory(m)   — 查看历史对话记录
  windows(w)  — 列出桌面窗口
  calibrate   — 校准输入框点击位置
  style       — 切换回复风格
  profile     — 热更新单份简历
  resumes     — 查看多简历库（需 --resumes-dir 启动）
  daemon      — 进入守护模式（定时扫描+自动回复）
  jdgen        — 根据 JD 自动生成简历
  help(h)     — 显示此帮助
  exit(q)     — 退出
""")

        else:
            print(f"未知命令: {cmd}  输入 help 查看帮助")


if __name__ == "__main__":
    main()
