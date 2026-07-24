"""
面试求职Agent — 简历管理、企业背调、岗位匹配、面试题库

核心流程：
  1. 上传简历 → 解析 → 存入AID记忆
  2. 企业背调（企查查/天眼查风格）
  3. JD匹配 → 简历优化建议
  4. 生成面试题库
  5. 面试排期 + 通勤路线整合
  6. 面试复盘 + 归档

需要环境变量（可选）：
  COMPANY_API_KEY = 企查查/天眼查 API Key（没有则模拟数据）
"""

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import List

logger = logging.getLogger("mindflow.agents.interview")


# ── 数据模型 ──

@dataclass
class Resume:
    """简历数据结构"""
    name: str = ""
    title: str = ""  # 求职意向
    skills: List[str] = field(default_factory=list)
    experience: List[dict] = field(default_factory=list)  # 工作经历
    projects: List[dict] = field(default_factory=list)    # 项目经历
    education: List[dict] = field(default_factory=list)   # 教育背景
    raw_text: str = ""  # 原始文本

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Company:
    """企业信息"""
    name: str = ""
    industry: str = ""
    scale: str = ""        # 规模
    stage: str = ""        # 融资阶段
    description: str = ""
    location: str = ""
    rating: float = 0.0    # 评分
    interview_reviews: List[str] = field(default_factory=list)  # 面经摘要


@dataclass
class InterviewQuestion:
    """面试题"""
    category: str = ""      # 技术/项目/业务/HR
    question: str = ""
    hint: str = ""          # 答题思路
    difficulty: str = "medium"


# ════════════════════════════════════════════════════════════════
# 简历管理
# ════════════════════════════════════════════════════════════════

def parse_resume(params: dict) -> dict:
    """
    解析简历文本
    参数：
      - text: 简历文本内容
      - file_path: 简历文件路径（可选，优先于text）
    """
    text = params.get("text") or params.get("params", {}).get("text", "")
    file_path = params.get("file_path") or params.get("params", {}).get("file_path", "")

    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            return {"error": f"读取文件失败: {e}"}

    if not text:
        return {"error": "请提供简历内容", "summary": "请上传或粘贴你的简历"}

    # 简单解析（后续可用LLM增强）
    resume = Resume(raw_text=text[:5000])

    # 提取姓名
    name_match = re.search(r"(?:姓名|名字|我叫|我是)\s*[:：]?\s*(\S{2,4})", text)
    if name_match:
        resume.name = name_match.group(1)

    # 提取技能
    skill_match = re.search(r"(?:技能|技术栈|熟悉|掌握)[：:]\s*(.+?)(?:\n|$)", text)
    if skill_match:
        skills_text = skill_match.group(1)
        resume.skills = [s.strip() for s in re.split(r"[、,，/]", skills_text) if s.strip()]

    logger.info(f"简历解析完成: {resume.name or '未知'} [{len(resume.skills)}项技能]")

    return {
        "resume": resume.to_dict(),
        "summary": f"已解析简历: {resume.name or '未识别姓名'}",
        "skill_count": len(resume.skills),
    }


def optimize_resume_for_jd(params: dict) -> dict:
    """
    根据JD优化简历
    参数：
      - jd_text: 岗位描述
      - resume_text: 简历内容（可选，默认使用已存储的简历）
    """
    jd_text = params.get("jd_text") or params.get("params", {}).get("jd_text", "")
    resume_text = params.get("resume_text") or params.get("params", {}).get("resume_text", "")

    if not jd_text:
        return {"error": "请提供JD描述", "summary": "请粘贴岗位JD"}

    if not resume_text:
        return {"summary": "未找到已存储的简历，请先上传简历", "suggestions": ["上传简历"]}

    # 提取JD关键词
    jd_keywords = _extract_keywords(jd_text)
    resume_keywords = _extract_keywords(resume_text)

    # 匹配分析
    matched = [k for k in jd_keywords if k in resume_keywords]
    missing = [k for k in jd_keywords if k not in resume_keywords]

    match_rate = len(matched) / len(jd_keywords) * 100 if jd_keywords else 0

    suggestions = []
    if missing:
        suggestions.append(f"建议补充: {', '.join(missing[:5])}")

    return {
        "match_rate": round(match_rate, 1),
        "matched_keywords": matched,
        "missing_keywords": missing[:10],
        "suggestions": suggestions,
        "summary": f"匹配度 {match_rate:.0f}%",
    }


def _extract_keywords(text: str) -> List[str]:
    """从文本中提取关键词"""
    text_lower = text.lower()
    # 常见技术关键词
    tech_keywords = [
        "python", "java", "javascript", "typescript", "go", "rust", "c++",
        "react", "vue", "angular", "node", "django", "flask", "spring",
        "docker", "kubernetes", "k8s", "aws", "gcp", "azure",
        "mysql", "postgresql", "redis", "mongodb", "elasticsearch",
        "git", "ci/cd", "linux", "微服务", "分布式", "高并发",
        "machine learning", "deep learning", "nlp", "llm", "ai",
        "tensorflow", "pytorch", "transformer", "rag", "agent",
    ]
    found = []
    for kw in tech_keywords:
        if kw in text_lower:
            found.append(kw)
    return found


# ════════════════════════════════════════════════════════════════
# 企业背调
# ════════════════════════════════════════════════════════════════

def company_research(params: dict) -> dict:
    """
    企业背景调查
    参数：
      - company: 公司名
    """
    company_name = params.get("company") or params.get("params", {}).get("company", "")

    if not company_name:
        return {"error": "请提供公司名", "summary": "请告诉我公司名称"}

    # 模拟数据（后续对接企查查/天眼查API）
    company = Company(name=company_name)
    company.industry = _guess_industry(company_name)
    company.scale = "1000-5000人"
    company.stage = "D轮及以上"
    company.description = f"{company_name}是一家{company.industry}领域的公司"
    company.location = "北京"

    # 模拟面经
    company.interview_reviews = [
        "技术面主要考察项目和基础",
        "HR面关注职业规划和团队协作",
    ]

    logger.info(f"企业背调完成: {company_name} [{company.industry}]")

    return {
        "company": company.__dict__,
        "summary": f"{company_name} | {company.industry} | {company.stage}",
        "review_count": len(company.interview_reviews),
    }


def _guess_industry(name: str) -> str:
    """根据公司名猜测行业"""
    name_lower = name.lower()
    if any(kw in name_lower for kw in ["科技", "技术", "软件", "数据", "智能", "ai", "tech", "code"]):
        return "互联网/科技"
    if any(kw in name_lower for kw in ["金融", "银行", "保险", "证券", "基金"]):
        return "金融"
    if any(kw in name_lower for kw in ["教育", "培训", "学院", "学校"]):
        return "教育"
    if any(kw in name_lower for kw in ["医疗", "医药", "健康", "生物"]):
        return "医疗健康"
    return "互联网/科技"


# ════════════════════════════════════════════════════════════════
# 面试题库
# ════════════════════════════════════════════════════════════════

def generate_questions(params: dict) -> dict:
    """
    生成面试题库
    参数：
      - position: 岗位
      - skills: 技能列表（逗号分隔）
      - company: 公司名（可选，用于生成业务面问题）
    """
    position = params.get("position") or params.get("params", {}).get("position", "")
    skills_str = params.get("skills") or params.get("params", {}).get("skills", "")
    company = params.get("company") or params.get("params", {}).get("company", "")

    if not position:
        return {"error": "请提供岗位信息", "summary": "请告诉我面试什么岗位"}

    skills = [s.strip() for s in skills_str.split(",") if s.strip()]

    questions = _generate_question_template(position, skills, company)

    return {
        "position": position,
        "questions": questions,
        "total": len(questions),
        "summary": f"已生成 {len(questions)} 道面试题",
    }


def _generate_question_template(position: str, skills: List[str], company: str) -> List[dict]:
    """生成面试题模板"""
    questions = []

    # 技术基础题
    tech_base = {
        "python": [
            {"category": "技术", "question": "Python 的 GIL 是什么？如何绕过？", "difficulty": "medium"},
            {"category": "技术", "question": "Python 装饰器的工作原理和使用场景", "difficulty": "medium"},
            {"category": "技术", "question": "列表推导式和生成器表达式的区别", "difficulty": "easy"},
        ],
        "java": [
            {"category": "技术", "question": "Java 内存模型和垃圾回收机制", "difficulty": "hard"},
            {"category": "技术", "question": "ConcurrentHashMap 的实现原理", "difficulty": "hard"},
        ],
        "react": [
            {"category": "技术", "question": "React Hooks 的使用规则和原理", "difficulty": "medium"},
            {"category": "技术", "question": "虚拟DOM和Diff算法", "difficulty": "medium"},
        ],
        "docker": [
            {"category": "技术", "question": "Docker 和虚拟机的区别", "difficulty": "easy"},
            {"category": "技术", "question": "Dockerfile 最佳实践", "difficulty": "medium"},
        ],
    }

    for skill in skills:
        skill_lower = skill.lower()
        for key, qs in tech_base.items():
            if key in skill_lower:
                questions.extend(qs)

    # 项目经历题
    questions.append({
        "category": "项目",
        "question": "请介绍一个你最有挑战性的项目，你在其中承担了什么角色？",
        "difficulty": "medium",
        "hint": "STAR原则：Situation-Task-Action-Result",
    })
    questions.append({
        "category": "项目",
        "question": "项目中最难解决的技术问题是什么？你怎么解决的？",
        "difficulty": "medium",
    })

    # 业务面
    if company:
        questions.append({
            "category": "业务",
            "question": f"你对我们公司({company})的业务有什么了解？",
            "difficulty": "easy",
            "hint": "提前了解公司产品和业务线",
        })

    # HR面
    questions.extend([
        {"category": "HR", "question": "你为什么想离开现在的公司？", "difficulty": "easy"},
        {"category": "HR", "question": "你期望的薪资范围是多少？", "difficulty": "easy"},
        {"category": "HR", "question": "你未来3-5年的职业规划是什么？", "difficulty": "easy"},
    ])

    return questions[:15]  # 最多15题


# ════════════════════════════════════════════════════════════════
# 面试排期 + 行程整合
# ════════════════════════════════════════════════════════════════

def schedule_interview(params: dict) -> dict:
    """
    面试排期
    参数：
      - company: 公司名
      - time: 面试时间
      - address: 公司地址
      - position: 岗位
    """
    company = params.get("company") or params.get("params", {}).get("company", "")
    time = params.get("time") or params.get("params", {}).get("time", "")
    address = params.get("address") or params.get("params", {}).get("address", "")
    position = params.get("position") or params.get("params", {}).get("position", "")

    if not company:
        return {"error": "请提供公司信息", "summary": "请告诉我面试公司"}

    return {
        "company": company,
        "position": position or "未知岗位",
        "time": time or "待确认",
        "address": address or "待确认",
        "summary": f"{company} {position} 面试已排期",
        "needs_confirmation": True,
    }


# ════════════════════════════════════════════════════════════════
# 注册到 Mindflow
# ════════════════════════════════════════════════════════════════

def register_tools(engine):
    """将面试Agent的所有工具注册到 Mindflow 引擎"""
    engine.register_tool("resume_engine", parse_resume)
    engine.register_tool("resume_optimize", optimize_resume_for_jd)
    engine.register_tool("company_db", company_research)
    engine.register_tool("interview_questions", generate_questions)
    engine.register_tool("schedule_add", schedule_interview)
    logger.info("  💼 面试Agent已注册")
    return engine
