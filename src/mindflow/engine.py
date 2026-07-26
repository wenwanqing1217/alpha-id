"""
Mindflow 调度引擎

职责：
  1. 接收 AID 下发的"任务指令包"(结构化JSON)
  2. 拆解子任务
  3. 根据任务类型匹配对应的 Agent/工具
  4. 并行/串行执行
  5. 汇总结果
  6. 过权限检查（L1/L2/L3）
  7. 返回"执行结果包"

输入格式：
  {
    "task_id": "uuid",
    "intent": "route_plan | interview_prep | ...",
    "params": { ... },
    "tools_needed": ["baidu_map", "calendar", ...],
    "permission_level": "L1 | L2 | L3",
    "user_id": "sender_id"
  }

输出格式：
  {
    "task_id": "uuid",
    "status": "success | pending_approval | error",
    "results": { "tool_name": { ... } },
    "summary": "汇总文本",
    "card": { ... }  // 可选，飞书卡片 JSON
  }
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("mindflow.engine")


# ── 数据模型 ──

@dataclass
class TaskInstruction:
    """AID 下发的任务指令包"""
    task_id: str
    intent: str
    params: Dict[str, Any] = field(default_factory=dict)
    tools_needed: List[str] = field(default_factory=list)
    permission_level: str = "L1"  # L1=自动, L2=轻量确认, L3=必须确认
    user_id: str = ""
    raw_text: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "TaskInstruction":
        return cls(
            task_id=d.get("task_id", uuid.uuid4().hex[:12]),
            intent=d.get("intent", "chat"),
            params=d.get("params", {}),
            tools_needed=d.get("tools_needed", []),
            permission_level=d.get("permission_level", "L1"),
            user_id=d.get("user_id", ""),
            raw_text=d.get("raw_text", ""),
        )


@dataclass
class ToolResult:
    """单个工具的执行结果"""
    tool: str
    status: str  # success | error | pending
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class TaskResult:
    """任务执行结果包"""
    task_id: str
    status: str  # success | pending_approval | error
    results: Dict[str, ToolResult] = field(default_factory=dict)
    summary: str = ""
    card_data: Optional[dict] = None
    needs_confirmation: bool = False
    error: str = ""


# ── 工具注册表 ──

class ToolRegistry:
    """工具注册表：管理所有可用的 Agent 和 API 工具"""

    def __init__(self):
        self._tools: Dict[str, Callable] = {}

    def register(self, name: str, handler: Callable) -> None:
        """注册一个工具处理器"""
        self._tools[name] = handler
        logger.info(f"  📦 注册工具: {name}")

    def get(self, name: str) -> Optional[Callable]:
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def execute(self, name: str, params: dict) -> ToolResult:
        """执行指定工具"""
        start = time.time()
        handler = self._tools.get(name)
        if not handler:
            return ToolResult(
                tool=name,
                status="error",
                error=f"工具 '{name}' 未注册",
            )

        try:
            result = handler(params)
            duration = (time.time() - start) * 1000
            logger.info(f"  ✅ 工具执行完成: {name} ({duration:.0f}ms)")
            return ToolResult(
                tool=name,
                status="success",
                data=result if isinstance(result, dict) else {"result": result},
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(f"  ❌ 工具执行失败: {name} - {e}")
            return ToolResult(
                tool=name,
                status="error",
                error=str(e),
                duration_ms=duration,
            )


# ── 权限管控 ──

class PermissionGate:
    """
    权限管控：L1/L2/L3 分级
    - L1: 自动执行，不需要确认
    - L2: 轻量确认，飞书卡片推送让用户点一下
    - L3: 必须确认，涉及敏感操作
    """

    L1_AUTO = frozenset({
        "weather_query", "calendar_query", "route_plan",
        "search", "web_search", "code_runner", "codex_agent", "chat",
    })
    L2_CONFIRM = frozenset({
        "interview_prep", "resume_optimize", "schedule_add",
    })
    L3_MUST_CONFIRM = frozenset({
        "resume_submit", "payment", "data_delete",
        "message_send", "device_bind",
    })

    @classmethod
    def evaluate(cls, intent: str, params: dict = None) -> str:
        """判断意图的权限等级"""
        if intent in cls.L3_MUST_CONFIRM:
            return "L3"
        if intent in cls.L2_CONFIRM:
            return "L2"
        if intent in cls.L1_AUTO:
            return "L1"
        # 默认：未知意图走 L2 确认
        return "L2"


# ── 调度引擎 ──

class MindflowEngine:
    """
    Mindflow 调度引擎
    接收任务指令 → 拆解 → 匹配工具 → 执行 → 汇总
    """

    def __init__(self):
        self.tools = ToolRegistry()
        self.permission = PermissionGate()
        self._pending_approvals: Dict[str, TaskResult] = {}
        logger.info("🚀 Mindflow 调度引擎初始化")

    def register_tool(self, name: str, handler: Callable) -> None:
        """注册工具"""
        self.tools.register(name, handler)

    def execute(self, instruction: TaskInstruction) -> TaskResult:
        """执行任务指令"""
        task_id = instruction.task_id or uuid.uuid4().hex[:12]
        logger.info(f"📋 接收任务: task_id={task_id} intent={instruction.intent}")

        # 1. 权限检查
        level = instruction.permission_level or self.permission.evaluate(
            instruction.intent, instruction.params
        )

        if level == "L3":
            logger.info("  🔒 L3 权限: 需要用户确认")
            return TaskResult(
                task_id=task_id,
                status="pending_approval",
                needs_confirmation=True,
                summary=f"需要你确认后才能执行: {instruction.intent}",
            )

        # 2. 确定需要调用的工具列表
        tools_to_call = instruction.tools_needed or self._resolve_tools(instruction)

        if not tools_to_call:
            return TaskResult(
                task_id=task_id,
                status="success",
                summary=f"已理解你的需求: {instruction.raw_text[:50]}... (暂未接入具体工具)",
            )

        # 3. 执行工具（当前全部串行，后续可加并行）
        results: Dict[str, ToolResult] = {}
        all_success = True

        for tool_name in tools_to_call:
            tool_params = instruction.params.copy()
            tool_params["_intent"] = instruction.intent
            tool_params["_task_id"] = task_id

            result = self.tools.execute(tool_name, tool_params)
            results[tool_name] = result
            if result.status != "success":
                all_success = False

        # 4. 汇总结果
        summary = self._build_summary(instruction, results, all_success)

        return TaskResult(
            task_id=task_id,
            status="success" if all_success else "error",
            results=results,
            summary=summary,
            needs_confirmation=level == "L2",
            error="" if all_success else "部分工具执行失败",
        )

    def _resolve_tools(self, instruction: TaskInstruction) -> List[str]:
        """根据意图自动推断需要的工具"""
        intent_tool_map = {
            "route_plan": ["baidu_map"],
            "interview_prep": ["company_db", "calendar"],
            "calendar_query": ["calendar"],
            "weather_query": ["weather_api"],
            "resume": ["resume_engine"],
            "search": ["web_search"],
            "code_runner": ["code_runner"],
            "codex_agent": ["codex_agent"],
            "chat": ["chat"],
        }
        return intent_tool_map.get(instruction.intent, [])

    def _build_summary(
        self, instruction: TaskInstruction, results: Dict[str, ToolResult], ok: bool
    ) -> str:
        """构建汇总文本"""
        parts = []
        for tool_name, result in results.items():
            if result.status == "success":
                data = result.data
                if tool_name == "baidu_map":
                    parts.append(f"路线: {data.get('summary', '已规划')}")
                elif tool_name == "company_db":
                    parts.append(f"公司: {data.get('name', '已查询')}")
                elif tool_name == "calendar":
                    parts.append(f"日程: {data.get('summary', '已读取')}")
                elif tool_name == "code_runner":
                    parts.append(data.get('content', '代码已生成'))
                elif tool_name == "chat":
                    parts.append(data.get('content', ''))
                else:
                    parts.append(f"{tool_name}: 执行成功")
            else:
                parts.append(f"{tool_name}: {result.error}")
        return " | ".join(parts) if parts else "已处理"


# ── 全局单例 ──

_engine: Optional[MindflowEngine] = None


def get_engine() -> MindflowEngine:
    global _engine
    if _engine is None:
        _engine = MindflowEngine()
    return _engine
