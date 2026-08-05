"""
Mindflow — 任务调度引擎包

接收结构化任务指令 → 拆解 → 匹配工具 → 执行 → 汇总结果。

公共 API:
  - MindflowEngine: 调度引擎
  - TaskInstruction: 任务指令数据类
  - TaskResult: 任务结果数据类
  - IntentClassifier: 意图识别器

用法:
  from mindflow import MindflowEngine, TaskInstruction
  from mindflow.intent import IntentClassifier

  engine = MindflowEngine()
  classifier = IntentClassifier()
  intent = classifier.classify("明天9点去公司开会")
  result = engine.execute(TaskInstruction.from_dict({
      "intent": intent.intent,
      "params": intent.params,
      "tools_needed": intent.tools_needed,
      "raw_text": "明天9点去公司开会",
  }))
"""

from .engine import (
    MindflowEngine,
    PermissionGate,
    TaskInstruction,
    TaskResult,
    ToolRegistry,
    ToolResult,
)

__all__ = [
    "MindflowEngine",
    "TaskInstruction",
    "TaskResult",
    "ToolResult",
    "ToolRegistry",
    "PermissionGate",
]

__version__ = "0.1.0"
