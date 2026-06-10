"""
Alpha-ID CoALA 四层记忆架构

基于 CoALA 框架（Sumers et al., 2023, arXiv:2309.02427）

四层记忆类型：
1. Working Memory（工作记忆）：当前 context window 中的内容
2. Episodic Memory（情景记忆）：过去交互的事件记录
3. Semantic Memory（语义记忆）：从交互中抽取的事实和实体关系
4. Procedural Memory（过程记忆）：成功的执行模式和推理策略

依据：
- CoALA Framework (arXiv:2309.02427)
- Agent Memory 工程化落地：从玩具到生产的三阶段跃迁
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryType(Enum):
    """CoALA 记忆类型"""
    WORKING = "working"       # 工作记忆（当前 context window）
    EPISODIC = "episodic"     # 情景记忆（事件记录）
    SEMANTIC = "semantic"     # 语义记忆（事实和实体关系）
    PROCEDURAL = "procedural" # 过程记忆（执行模式和推理策略）


@dataclass
class WorkingMemoryItem:
    """
    工作记忆项

    特点：
    - 当前 context window 中的内容
    - 实时更新，会话结束后清空或归档
    - 相当于 LLM 的 RAM
    """
    content: str
    role: str  # "system", "user", "assistant", "tool"
    timestamp: float
    session_id: str
    tokens: int = 0


@dataclass
class EpisodicMemoryItem:
    """
    情景记忆项

    特点：
    - 过去交互的事件记录
    - "用户上周三问过退款流程"
    - "上次部署失败是因为 npm 版本冲突"
    """
    event_type: str  # "query", "response", "action", "error"
    description: str
    timestamp: float
    session_id: str
    participants: List[str] = field(default_factory=list)
    outcome: str = ""  # "success", "failure", "partial"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticMemoryItem:
    """
    语义记忆项

    特点：
    - 从交互中抽取的事实和实体关系
    - "用户偏好深色主题"
    - "张三是 A 项目的负责人"
    """
    fact_type: str  # "preference", "entity", "relation", "knowledge"
    subject: str
    predicate: str
    object: str
    confidence: float  # 0-1
    source: str  # 来源 session_id
    timestamp: float
    validity_start: float = 0  # 事实生效时间
    validity_end: float = float("inf")  # 事实失效时间（默认永久有效）
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProceduralMemoryItem:
    """
    过程记忆项

    特点：
    - 成功的执行模式和推理策略
    - "上次处理这类工单的步骤是……"
    - "遇到 API 超时先检查 rate limit"
    """
    procedure_type: str  # "workflow", "strategy", "pattern", "heuristic"
    name: str
    description: str
    steps: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)  # 触发条件
    success_rate: float = 0  # 成功率
    usage_count: int = 0  # 使用次数
    last_used: float = 0
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkingMemory:
    """
    工作记忆管理器

    管理 context window 中的内容
    """

    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens
        self.items: List[WorkingMemoryItem] = []
        self.current_tokens = 0

    def add(self, content: str, role: str, session_id: str) -> bool:
        """添加工作记忆"""
        tokens = len(content.split()) * 1.3  # 简化 token 估算

        # 检查是否超出限制
        if self.current_tokens + tokens > self.max_tokens:
            # 需要压缩或清理
            self._compress()

        item = WorkingMemoryItem(
            content=content,
            role=role,
            timestamp=time.time(),
            session_id=session_id,
            tokens=int(tokens),
        )
        self.items.append(item)
        self.current_tokens += int(tokens)

        return True

    def get_context(self) -> str:
        """获取当前 context window 内容"""
        return "\n".join([f"{item.role}: {item.content}" for item in self.items])

    def clear(self) -> List[WorkingMemoryItem]:
        """清空工作记忆（返回归档内容）"""
        items = self.items.copy()
        self.items = []
        self.current_tokens = 0
        return items

    def _compress(self) -> int:
        """压缩工作记忆（移除旧内容）"""
        # 移除最早的内容，直到满足 token 限制
        removed_tokens = 0
        while self.current_tokens > self.max_tokens * 0.8 and self.items:
            removed = self.items.pop(0)
            removed_tokens += removed.tokens
            self.current_tokens -= removed.tokens
        return removed_tokens


class EpisodicMemory:
    """
    情景记忆管理器

    管理过去交互的事件记录
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.items: List[EpisodicMemoryItem] = []

    def add(
        self,
        event_type: str,
        description: str,
        session_id: str,
        participants: List[str] = [],
        outcome: str = "success",
        metadata: Dict[str, Any] = {}
    ) -> str:
        """添加情景记忆"""
        item = EpisodicMemoryItem(
            event_type=event_type,
            description=description,
            timestamp=time.time(),
            session_id=session_id,
            participants=participants,
            outcome=outcome,
            metadata=metadata,
        )
        self.items.append(item)
        return f"episodic_{len(self.items)}"

    def search(self, query: str, top_k: int = 5) -> List[EpisodicMemoryItem]:
        """搜索情景记忆"""
        # 简化实现：关键词匹配
        results = []
        query_words = set(query.lower().split())

        for item in self.items:
            item_words = set(item.description.lower().split())
            overlap = len(query_words & item_words)
            if overlap > 0:
                results.append((item, overlap))

        # 按重叠度排序
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:top_k]]

    def get_by_session(self, session_id: str) -> List[EpisodicMemoryItem]:
        """获取特定会话的事件"""
        return [item for item in self.items if item.session_id == session_id]

    def get_recent(self, hours: int = 24) -> List[EpisodicMemoryItem]:
        """获取最近的事件"""
        cutoff = time.time() - hours * 3600
        return [item for item in self.items if item.timestamp > cutoff]


class SemanticMemory:
    """
    语义记忆管理器

    管理事实和实体关系
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.facts: List[SemanticMemoryItem] = []
        self.entities: Dict[str, List[str]] = {}  # entity -> related facts

    def add_fact(
        self,
        fact_type: str,
        subject: str,
        predicate: str,
        object: str,
        source: str,
        confidence: float = 0.9,
        validity_start: float = 0,
        validity_end: float = float("inf"),
        metadata: Dict[str, Any] = {}
    ) -> str:
        """添加事实"""
        item = SemanticMemoryItem(
            fact_type=fact_type,
            subject=subject,
            predicate=predicate,
            object=object,
            confidence=confidence,
            source=source,
            timestamp=time.time(),
            validity_start=validity_start or time.time(),
            validity_end=validity_end,
            metadata=metadata,
        )
        self.facts.append(item)

        # 更新实体索引
        if subject not in self.entities:
            self.entities[subject] = []
        self.entities[subject].append(f"semantic_{len(self.facts)}")

        return f"semantic_{len(self.facts)}"

    def query_fact(self, subject: str, predicate: str = "") -> List[SemanticMemoryItem]:
        """查询事实"""
        results = []
        current_time = time.time()

        for fact in self.facts:
            # 检查时间有效性
            if current_time < fact.validity_start or current_time > fact.validity_end:
                continue

            # 检查主体匹配
            if fact.subject.lower() == subject.lower():
                if not predicate or fact.predicate.lower() == predicate.lower():
                    results.append(fact)

        # 按置信度排序
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results

    def get_entity_relations(self, entity: str) -> List[SemanticMemoryItem]:
        """获取实体的所有关系"""
        return [fact for fact in self.facts if fact.subject.lower() == entity.lower()]

    def update_fact_validity(self, fact_id: str, new_validity_end: float):
        """更新事实有效期（用于知识更新）"""
        idx = int(fact_id.split("_")[1]) - 1
        if 0 <= idx < len(self.facts):
            self.facts[idx].validity_end = new_validity_end


class ProceduralMemory:
    """
    过程记忆管理器

    管理执行模式和推理策略
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.procedures: List[ProceduralMemoryItem] = []

    def add(
        self,
        procedure_type: str,
        name: str,
        description: str,
        steps: List[str] = [],
        conditions: List[str] = [],
        metadata: Dict[str, Any] = {}
    ) -> str:
        """添加过程记忆"""
        item = ProceduralMemoryItem(
            procedure_type=procedure_type,
            name=name,
            description=description,
            steps=steps,
            conditions=conditions,
            timestamp=time.time(),
            metadata=metadata,
        )
        self.procedures.append(item)
        return f"procedural_{len(self.procedures)}"

    def find_matching(self, context: str) -> List[ProceduralMemoryItem]:
        """找到匹配当前上下文的过程"""
        results = []
        context_words = set(context.lower().split())

        for proc in self.procedures:
            # 检查条件匹配
            for condition in proc.conditions:
                condition_words = set(condition.lower().split())
                if context_words & condition_words:
                    results.append(proc)
                    break

        # 按成功率排序
        results.sort(key=lambda x: x.success_rate, reverse=True)
        return results

    def record_usage(self, procedure_id: str, success: bool):
        """记录使用结果"""
        idx = int(procedure_id.split("_")[1]) - 1
        if 0 <= idx < len(self.procedures):
            proc = self.procedures[idx]
            proc.usage_count += 1
            proc.last_used = time.time()

            # 更新成功率
            if success:
                proc.success_rate = (proc.success_rate * (proc.usage_count - 1) + 1) / proc.usage_count
            else:
                proc.success_rate = proc.success_rate * (proc.usage_count - 1) / proc.usage_count

    def get_best_practices(self, top_k: int = 5) -> List[ProceduralMemoryItem]:
        """获取最佳实践（成功率最高的过程）"""
        sorted_procs = sorted(self.procedures, key=lambda x: x.success_rate, reverse=True)
        return sorted_procs[:top_k]


class CoALAMemorySystem:
    """
    CoALA 四层记忆系统（整合层）

    整合四种记忆类型，提供统一接口
    """

    def __init__(self, storage_path: Optional[Path] = None, max_working_tokens: int = 4000):
        self.working = WorkingMemory(max_tokens=max_working_tokens)
        self.episodic = EpisodicMemory(storage_path)
        self.semantic = SemanticMemory(storage_path)
        self.procedural = ProceduralMemory(storage_path)
        self.storage_path = storage_path

    def add_session_content(self, role: str, content: str, session_id: str):
        """添加会话内容到工作记忆"""
        self.working.add(content, role, session_id)

    def archive_session(self, session_id: str):
        """归档会话（从工作记忆转移到情景记忆）"""
        items = self.working.clear()

        for item in items:
            if item.session_id == session_id:
                self.episodic.add(
                    event_type="conversation",
                    description=item.content,
                    session_id=session_id,
                    outcome="completed",
                    metadata={"role": item.role, "tokens": item.tokens}
                )

    def extract_facts(self, content: str, session_id: str) -> List[str]:
        """
        从内容中提取事实（语义记忆）

        返回提取的事实 ID 列表
        """
        # 简化实现：基于关键词提取
        fact_ids = []

        # 提取偏好
        preference_patterns = [
            (r"我喜欢(.+)", "preference", "likes"),
            (r"我偏好(.+)", "preference", "prefers"),
            (r"我更倾向于(.+)", "preference", "tends_to"),
        ]

        import re
        for pattern, fact_type, predicate in preference_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                fact_id = self.semantic.add_fact(
                    fact_type=fact_type,
                    subject="user",
                    predicate=predicate,
                    object=match,
                    source=session_id,
                    confidence=0.8
                )
                fact_ids.append(fact_id)

        return fact_ids

    def search_all(self, query: str, top_k: int = 5) -> Dict[str, List[Any]]:
        """跨所有记忆类型搜索"""
        return {
            "episodic": self.episodic.search(query, top_k),
            "semantic": self.semantic.query_fact(query),
            "procedural": self.procedural.find_matching(query),
        }

    def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        return {
            "working": {
                "items": len(self.working.items),
                "tokens": self.working.current_tokens,
                "max_tokens": self.working.max_tokens,
            },
            "episodic": {
                "total_events": len(self.episodic.items),
            },
            "semantic": {
                "total_facts": len(self.semantic.facts),
                "total_entities": len(self.semantic.entities),
            },
            "procedural": {
                "total_procedures": len(self.procedural.procedures),
                "avg_success_rate": sum(p.success_rate for p in self.procedural.procedures) / len(self.procedural.procedures) if self.procedural.procedures else 0,
            },
        }


# 使用示例
if __name__ == "__main__":
    # 创建四层记忆系统
    memory = CoALAMemorySystem(storage_path=Path("./data"), max_working_tokens=4000)

    # 添加工作记忆
    memory.add_session_content("user", "我喜欢深色主题，偏好使用 Vim 编辑器", "session_001")
    memory.add_session_content("assistant", "好的，我记住了你的偏好", "session_001")

    # 提取事实到语义记忆
    facts = memory.extract_facts("我喜欢深色主题，偏好使用 Vim 编辑器", "session_001")
    print(f"提取的事实: {facts}")

    # 归档会话到情景记忆
    memory.archive_session("session_001")

    # 添加过程记忆
    proc_id = memory.procedural.add(
        procedure_type="workflow",
        name="处理退款请求",
        description="用户退款处理流程",
        steps=["验证订单", "检查退款条件", "执行退款", "通知用户"],
        conditions=["退款", "refund", "退钱"],
    )

    # 搜索记忆
    results = memory.search_all("退款")
    print(f"搜索结果: {json.dumps({k: [str(v) for v in vals] for k, vals in results.items()}, indent=2)}")

    # 获取统计
    stats = memory.get_memory_stats()
    print(f"记忆统计: {json.dumps(stats, indent=2)}")
