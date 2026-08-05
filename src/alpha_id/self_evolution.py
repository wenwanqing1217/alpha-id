"""
Alpha-ID Self-Evolution — 自进化循环
======================================

实现 Alpha-ID 的自进化能力：
  - 从观察中学习（用户反馈、行为模式）
  - 知识沉淀（碎片 → 结构化知识）
  - 偏好审视（定期重新评估偏好是否还合理）
  - 能力增长（学习新 Skill、改进旧 Skill）

核心洞察：
  自进化不是知识增长，是判断力增长。
  系统不是记住更多，是理解更深。
"""

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Lesson:
    """一条教训/学到的东西"""
    id: str = ""
    scenario: str = ""        # 什么场景下学到的
    mistake: str = ""         # 之前做错了什么
    correction: str = ""      # 正确的做法
    lesson: str = ""          # 提炼出的教训
    category: str = ""        # 分类：决策/设计/交互/存储/...
    applicable_to: List[str] = field(default_factory=list)  # 适用场景
    evidence: List[str] = field(default_factory=list)       # 证据
    confidence: float = 0.5   # 置信度 0-1
    times_applied: int = 0    # 应用次数
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PreferenceAudit:
    """偏好审视记录"""
    preference: str = ""
    reason: str = ""          # 为什么有这个偏好
    valid_when: str = ""      # 什么时候有效
    invalid_when: str = ""    # 什么时候无效
    last_evaluated: str = ""
    status: str = "active"    # active / needs_review / outdated


class SelfEvolution:
    """
    自进化引擎

    用法：
        evolution = SelfEvolution(memory_store, llm_enricher)
        evolution.learn_from_correction(scenario, mistake, correction, lesson)
        evolution.audit_preferences()
        evolution.sediment_knowledge()
    """

    def __init__(self, memory_store=None, llm_enricher=None):
        self._memory = memory_store
        self._enricher = llm_enricher
        self._lessons: List[Lesson] = []
        self._audits: List[PreferenceAudit] = []
        self._stats = {"lessons_learned": 0, "audits_done": 0, "sediments": 0}

    # ── 从纠正中学习 ──

    def learn_from_correction(self, scenario: str, mistake: str,
                              correction: str, lesson: str,
                              category: str = "general",
                              applicable_to: List[str] = None) -> Lesson:
        """
        从一次纠正中学习

        当用户说"不是这样的"、"应该是..."、"你错了"时调用
        """
        import hashlib
        lesson_id = hashlib.md5(f"{scenario}_{mistake}_{time.time()}".encode()).hexdigest()[:16]

        new_lesson = Lesson(
            id=lesson_id,
            scenario=scenario,
            mistake=mistake,
            correction=correction,
            lesson=lesson,
            category=category,
            applicable_to=applicable_to or [],
            confidence=0.7,
        )

        # 检查是否有类似的教训（去重）
        for existing in self._lessons:
            if existing.lesson == lesson and existing.scenario == scenario:
                # 增强置信度
                existing.confidence = min(existing.confidence + 0.1, 1.0)
                existing.times_applied += 1
                return existing

        self._lessons.append(new_lesson)
        self._stats["lessons_learned"] += 1

        # 存入记忆
        if self._memory:
            try:
                self._memory.save(
                    content=f"[教训] {lesson} (场景: {scenario})",
                    tags=["lesson", category],
                    sensitivity=10,
                    source="self_evolution",
                )
            except Exception:
                pass

        logger.info("学到新教训: %s", lesson[:50])
        return new_lesson

    def find_relevant_lessons(self, scenario: str, limit: int = 5) -> List[Lesson]:
        """找到与当前场景相关的教训"""
        # 简单的关键词匹配
        scenario_words = set(scenario.lower().split())
        scored = []

        for lesson in self._lessons:
            lesson_words = set(lesson.scenario.lower().split())
            overlap = len(scenario_words & lesson_words)
            if overlap > 0:
                scored.append((overlap * lesson.confidence, lesson))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [lesson for _, lesson in scored[:limit]]

    # ── 偏好审视 ──

    def register_preference(self, preference: str, reason: str = "",
                            valid_when: str = "", invalid_when: str = ""):
        """注册一个偏好"""
        audit = PreferenceAudit(
            preference=preference,
            reason=reason,
            valid_when=valid_when,
            invalid_when=invalid_when,
            last_evaluated=datetime.now(timezone.utc).isoformat(),
        )
        self._audits.append(audit)

    def audit_preferences(self) -> List[PreferenceAudit]:
        """
        审视所有偏好，标记需要重新评估的

        规则：
        - 超过 30 天未评估的 → needs_review
        - 跟最近教训矛盾的 → needs_review
        """
        needs_review = []
        now = datetime.now(timezone.utc)

        for audit in self._audits:
            # 检查是否很久没评估了
            if audit.last_evaluated:
                try:
                    last = datetime.fromisoformat(audit.last_evaluated)
                    days_since = (now - last).days
                    if days_since > 30:
                        audit.status = "needs_review"
                        needs_review.append(audit)
                except Exception:
                    pass

            # 检查是否跟教训矛盾
            for lesson in self._lessons:
                if lesson.category == "preference":
                    if audit.preference.lower() in lesson.mistake.lower():
                        audit.status = "needs_review"
                        needs_review.append(audit)

        self._stats["audits_done"] += len(needs_review)
        return needs_review

    # ── 知识沉淀 ──

    def sediment_knowledge(self, topic: str, note_paths: List[str],
                           obsidian_bridge=None) -> Optional[str]:
        """
        知识沉淀：把同一主题的多个笔记凝结成一篇总结

        Args:
            topic: 主题
            note_paths: 相关笔记路径
            obsidian_bridge: 用于写入 Obsidian

        Returns:
            生成的总结内容
        """
        if len(note_paths) < 3:
            return None

        # 读取所有笔记
        contents = []
        for path in note_paths[:10]:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    contents.append(f.read()[:1000])
            except Exception:
                continue

        if not contents:
            return None

        # 用 LLM 生成总结
        summary = self._generate_summary(topic, contents)

        if summary and obsidian_bridge:
            obsidian_bridge.write_note(
                title=f"[沉淀] {topic}",
                content=summary,
                tags=["sediment", topic],
                links=[Path(p).stem for p in note_paths[:5]],
            )

        self._stats["sediments"] += 1
        return summary

    def _generate_summary(self, topic: str, contents: List[str]) -> str:
        """用 LLM 生成总结"""
        combined = "\n\n---\n\n".join(contents)
        prompt = f"""
以下是关于"{topic}"的多个笔记片段，请生成一篇结构化总结：

【要求】
1. 提炼核心观点和模式
2. 标注知识演进路径
3. 识别尚未解决的问题
4. 输出 Markdown 格式

【笔记内容】
{combined[:4000]}

【输出格式】
# {topic} — 知识沉淀

## 核心观点
- ...

## 演进路径
1. ...

## 待解决问题
- ...
"""

        if self._enricher:
            try:
                result = self._enricher.analyze(prompt, source="sedimentation")
                if result:
                    return f"# {topic} — 知识沉淀\n\n自动生成于 {datetime.now(timezone.utc).isoformat()}\n\n{combined[:500]}..."
            except Exception:
                pass

        # 降级：简单拼接
        return f"# {topic} — 知识沉淀\n\n基于 {len(contents)} 篇笔记的自动总结\n\n{combined[:1000]}..."

    # ── 能力增长 ──

    def learn_skill_from_feed(self, feed_item: Any, skill_registry=None) -> Optional[str]:
        """
        从资讯中学习新能力

        如果发现有用的工具/方法，生成 Skill
        """
        if not feed_item:
            return None

        title = getattr(feed_item, 'title', '')
        summary = getattr(feed_item, 'summary', '')

        if not title:
            return None

        # 生成 Skill 描述
        skill_desc = f"从资讯学习: {title}\n{summary[:200]}"

        if skill_registry:
            try:
                skill_registry.register(
                    name=f"learned_{hash(title) % 10000}",
                    func=lambda x: skill_desc,
                    description=skill_desc,
                )
                return skill_desc
            except Exception:
                pass

        return None

    # ── 统计 ──

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "total_lessons": len(self._lessons),
            "total_audits": len(self._audits),
        }

    def get_lessons(self, category: str = None, limit: int = 20) -> List[Lesson]:
        lessons = self._lessons
        if category:
            lessons = [lesson for lesson in lessons if lesson.category == category]
        return lessons[-limit:]
