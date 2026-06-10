"""
Alpha-ID 基准测试适配器框架

支持三大标准基准测试：
- LoCoMo (Snap Research)：多跳推理，1,986 个 QA 对
- LongMemEval：信息定位，500 个问题，6 种类型
- BEAM：大规模记忆，1M/10M token 规模

依据：
- Mem0 ECAI 2025 论文 (arXiv:2504.19413)
- LongMemEval 论文 (arXiv:2410.10813)
- LoCoMo 数据集 (Snap Research)
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BenchmarkResult:
    """基准测试结果"""
    benchmark_name: str
    score: float  # 0-100
    metric: str  # "R@5", "QA_accuracy", "LLM_judge_score"
    tokens_per_query: int
    latency_ms: float
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark_name": self.benchmark_name,
            "score": self.score,
            "metric": self.metric,
            "tokens_per_query": self.tokens_per_query,
            "latency_ms": self.latency_ms,
            "details": self.details,
        }


class BenchmarkAdapter:
    """基准测试适配器基类"""

    def __init__(self, name: str, data_path: Optional[Path] = None):
        self.name = name
        self.data_path = data_path
        self.questions: List[Dict[str, Any]] = []
        self.sessions: List[Dict[str, Any]] = []

    def load_data(self) -> bool:
        """加载基准测试数据"""
        raise NotImplementedError

    def run_evaluation(self, memory_system: Any) -> BenchmarkResult:
        """运行评估"""
        raise NotImplementedError

    def get_question_types(self) -> List[str]:
        """获取问题类型列表"""
        raise NotImplementedError


class LoCoMoAdapter(BenchmarkAdapter):
    """
    LoCoMo 基准测试适配器

    特点：
    - 10 段超长对话（平均 300 轮 / 9K token / 最多 35 会话）
    - 1,986 个 QA 对（其中 ~1,540 题用于综合排名）
    - 评测维度：单跳 / 多跳 / 时序 / 开放域 / 对抗

    依据：Snap Research LoCoMo 数据集
    """

    def __init__(self, data_path: Optional[Path] = None):
        super().__init__("LoCoMo", data_path)
        self.categories = [
            "single_hop",      # 单跳推理
            "multi_hop",       # 多跳推理
            "temporal",        # 时序推理
            "open_domain",     # 开放域问答
            "adversarial",     # 对抗性问答
        ]

    def load_data(self) -> bool:
        """加载 LoCoMo 数据集"""
        if self.data_path and self.data_path.exists():
            # 从本地加载
            with open(self.data_path / "locomo_questions.json", "r") as f:
                self.questions = json.load(f)
            with open(self.data_path / "locomo_sessions.json", "r") as f:
                self.sessions = json.load(f)
            return True

        # 尝试从 HuggingFace 加载（需要网络）
        try:
            # TODO: 实现 HuggingFace 数据加载
            return False
        except Exception:
            return False

    def run_evaluation(self, memory_system: Any) -> BenchmarkResult:
        """
        运行 LoCoMo 评估

        评估流程：
        1. 加载所有会话到记忆系统
        2. 对每个问题进行检索
        3. 计算 R@5（Recall@5）分数
        4. 记录 token 消耗和延迟
        """
        if not self.questions:
            self.load_data()

        if not self.questions:
            return BenchmarkResult(
                benchmark_name=self.name,
                score=0.0,
                metric="R@5",
                tokens_per_query=0,
                latency_ms=0.0,
                details={"error": "数据加载失败"}
            )

        # 加载会话到记忆系统
        start_time = time.time()
        for session in self.sessions:
            memory_system.add_session(session)
        load_time = time.time() - start_time

        # 评估每个问题
        correct = 0
        total_tokens = 0
        total_latency = 0.0

        for question in self.questions:
            query_start = time.time()
            result = memory_system.search(question["query"], top_k=5)
            query_latency = time.time() - query_start

            # 检查是否检索到正确会话
            retrieved_ids = [r["session_id"] for r in result]
            if question["target_session_id"] in retrieved_ids:
                correct += 1

            total_tokens += result.get("tokens_used", 0)
            total_latency += query_latency

        # 计算分数
        score = (correct / len(self.questions)) * 100
        avg_tokens = total_tokens // len(self.questions)
        avg_latency = (total_latency / len(self.questions)) * 1000

        return BenchmarkResult(
            benchmark_name=self.name,
            score=score,
            metric="R@5",
            tokens_per_query=avg_tokens,
            latency_ms=avg_latency,
            details={
                "correct": correct,
                "total": len(self.questions),
                "load_time_s": load_time,
                "categories": self._get_category_scores(memory_system),
            }
        )

    def _get_category_scores(self, memory_system: Any) -> Dict[str, float]:
        """计算各类别分数"""
        category_scores = {}
        for category in self.categories:
            category_questions = [q for q in self.questions if q.get("category") == category]
            if category_questions:
                correct = 0
                for q in category_questions:
                    result = memory_system.search(q["query"], top_k=5)
                    if q["target_session_id"] in [r["session_id"] for r in result]:
                        correct += 1
                category_scores[category] = (correct / len(category_questions)) * 100
        return category_scores

    def get_question_types(self) -> List[str]:
        return self.categories


class LongMemEvalAdapter(BenchmarkAdapter):
    """
    LongMemEval 基准测试适配器

    特点：
    - 500 个问题，53 个会话
    - 6 种问题类型
    - 核心能力：信息定位（找到包含答案的会话）

    依据：LongMemEval 论文 (arXiv:2410.10813)
    """

    def __init__(self, data_path: Optional[Path] = None):
        super().__init__("LongMemEval", data_path)
        self.question_types = [
            "knowledge_update",         # 知识更新（78 题）
            "multi_session",            # 多会话（133 题）
            "temporal_reasoning",       # 时序推理（133 题）
            "single_session_user",      # 单会话用户（70 题）
            "single_session_preference", # 单会话偏好（30 题）
            "single_session_assistant",  # 单会话助手（56 题）
        ]

    def load_data(self) -> bool:
        """加载 LongMemEval 数据集"""
        if self.data_path and self.data_path.exists():
            with open(self.data_path / "longmemeval_questions.json", "r") as f:
                self.questions = json.load(f)
            with open(self.data_path / "longmemeval_sessions.json", "r") as f:
                self.sessions = json.load(f)
            return True
        return False

    def run_evaluation(self, memory_system: Any) -> BenchmarkResult:
        """运行 LongMemEval 评估"""
        if not self.questions:
            self.load_data()

        if not self.questions:
            return BenchmarkResult(
                benchmark_name=self.name,
                score=0.0,
                metric="R@5",
                tokens_per_query=0,
                latency_ms=0.0,
                details={"error": "数据加载失败"}
            )

        # 加载会话到记忆系统
        for session in self.sessions:
            memory_system.add_session(session)

        # 评估
        correct = 0
        total_tokens = 0
        total_latency = 0.0

        for question in self.questions:
            query_start = time.time()
            result = memory_system.search(question["query"], top_k=5)
            query_latency = time.time() - query_start

            if question["target_session_id"] in [r["session_id"] for r in result]:
                correct += 1

            total_tokens += result.get("tokens_used", 0)
            total_latency += query_latency

        score = (correct / len(self.questions)) * 100
        avg_tokens = total_tokens // len(self.questions)
        avg_latency = (total_latency / len(self.questions)) * 1000

        return BenchmarkResult(
            benchmark_name=self.name,
            score=score,
            metric="R@5",
            tokens_per_query=avg_tokens,
            latency_ms=avg_latency,
            details={
                "correct": correct,
                "total": len(self.questions),
                "type_scores": self._get_type_scores(memory_system),
            }
        )

    def _get_type_scores(self, memory_system: Any) -> Dict[str, float]:
        """计算各类型分数"""
        type_scores = {}
        for qtype in self.question_types:
            type_questions = [q for q in self.questions if q.get("type") == qtype]
            if type_questions:
                correct = 0
                for q in type_questions:
                    result = memory_system.search(q["query"], top_k=5)
                    if q["target_session_id"] in [r["session_id"] for r in result]:
                        correct += 1
                type_scores[qtype] = (correct / len(type_questions)) * 100
        return type_scores

    def get_question_types(self) -> List[str]:
        return self.question_types


class BEAMAdapter(BenchmarkAdapter):
    """
    BEAM 基准测试适配器

    特点：
    - 1M 和 10M token 规模
    - 10 个类别
    - 测试大规模记忆系统性能

    依据：BEAM benchmark
    """

    def __init__(self, scale: str = "1M", data_path: Optional[Path] = None):
        super().__init__(f"BEAM_{scale}", data_path)
        self.scale = scale
        self.categories = [
            "preference_following",
            "instruction_following",
            "information_extraction",
            "knowledge_update",
            "multi_session_reasoning",
            "summarization",
            "temporal_reasoning",
            "event_ordering",
            "abstention",
            "contradiction_resolution",
        ]

    def load_data(self) -> bool:
        """加载 BEAM 数据集"""
        # TODO: 实现 BEAM 数据加载
        return False

    def run_evaluation(self, memory_system: Any) -> BenchmarkResult:
        """运行 BEAM 评估"""
        # TODO: 实现 BEAM 评估逻辑
        return BenchmarkResult(
            benchmark_name=self.name,
            score=0.0,
            metric="QA_accuracy",
            tokens_per_query=0,
            latency_ms=0.0,
            details={"error": "BEAM 数据集尚未实现"}
        )

    def get_question_types(self) -> List[str]:
        return self.categories


class BenchmarkRunner:
    """基准测试运行器"""

    def __init__(self, memory_system: Any):
        self.memory_system = memory_system
        self.adapters: Dict[str, BenchmarkAdapter] = {}
        self.results: List[BenchmarkResult] = []

    def register_adapter(self, adapter: BenchmarkAdapter):
        """注册适配器"""
        self.adapters[adapter.name] = adapter

    def run_all(self) -> List[BenchmarkResult]:
        """运行所有基准测试"""
        self.results = []
        for name, adapter in self.adapters.items():
            result = adapter.run_evaluation(self.memory_system)
            self.results.append(result)
        return self.results

    def run_single(self, benchmark_name: str) -> Optional[BenchmarkResult]:
        """运行单个基准测试"""
        if benchmark_name in self.adapters:
            return self.adapters[benchmark_name].run_evaluation(self.memory_system)
        return None

    def get_summary(self) -> Dict[str, Any]:
        """获取评估摘要"""
        if not self.results:
            return {"error": "尚未运行评估"}

        summary = {
            "total_benchmarks": len(self.results),
            "results": [r.to_dict() for r in self.results],
            "average_score": sum(r.score for r in self.results) / len(self.results),
            "average_tokens": sum(r.tokens_per_query for r in self.results) / len(self.results),
            "average_latency": sum(r.latency_ms for r in self.results) / len(self.results),
        }

        # 对比 Mem0 基准（依据：Mem0 ECAI 2025 论文）
        mem0_baseline = {
            "LoCoMo": 92.5,
            "LongMemEval": 94.4,
            "BEAM_1M": 64.1,
            "BEAM_10M": 48.6,
        }

        comparison = {}
        for result in self.results:
            if result.benchmark_name in mem0_baseline:
                comparison[result.benchmark_name] = {
                    "alpha_id_score": result.score,
                    "mem0_baseline": mem0_baseline[result.benchmark_name],
                    "gap": result.score - mem0_baseline[result.benchmark_name],
                }

        summary["comparison_vs_mem0"] = comparison

        return summary


# 使用示例
if __name__ == "__main__":
    # 创建适配器
    locomo_adapter = LoCoMoAdapter()
    longmemeval_adapter = LongMemEvalAdapter()
    beam_adapter = BEAMAdapter(scale="1M")

    # 注册到运行器
    # runner = BenchmarkRunner(memory_system)
    # runner.register_adapter(locomo_adapter)
    # runner.register_adapter(longmemeval_adapter)
    # runner.register_adapter(beam_adapter)

    # 运行评估
    # results = runner.run_all()
    # summary = runner.get_summary()
    # print(json.dumps(summary, indent=2))
