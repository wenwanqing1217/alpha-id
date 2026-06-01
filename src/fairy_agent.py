"""
FairyBrain — 桌面精灵的 LLM 大脑

用自然语言理解用户指令，自动选择工具执行，带记忆持久化。

架构：
  1. 用户输入自然语言指令
  2. OpenAI API 理解意图，选择工具
  3. 工具执行（截图/OCR/鼠标/窗口…）
  4. 结果返回 + 自动存为记忆
  5. 下次启动自动加载过往记忆
"""

import json
import os
import threading
from typing import Callable, Dict, List, Optional

# ── 记忆存储组件 ──

HAS_MEMORY = False
try:
    HAS_MEMORY = True
except ImportError:
    pass

# ── LLM ──

HAS_OPENAI = False
try:
    from openai import OpenAI

    HAS_OPENAI = True
except ImportError:
    pass


# ══════════════════════════════════════════════════════════
#  工具注册表
# ══════════════════════════════════════════════════════════


class FairyTool:
    """一个可被 LLM 调用的桌面工具"""

    def __init__(self, name: str, description: str, parameters: dict, fn: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters  # JSON Schema
        self.fn = fn

    def to_openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __call__(self, **kwargs) -> str:
        try:
            result = self.fn(**kwargs)
            return str(result) if result is not None else "（执行成功，无返回）"
        except Exception as e:
            return f"[工具执行失败] {e}"


# ══════════════════════════════════════════════════════════
#  FairyBrain
# ══════════════════════════════════════════════════════════


class FairyBrain:
    """
    桌面精灵的 LLM 大脑。

    用法：
        brain = FairyBrain(fairy_instance)
        result = brain.process("看下屏幕上有什么")
        # → LLM 自动调用 screenshot + OCR，返回自然语言描述

    降级：
        没有 API Key 时 process() 返回 None，调用方走关键词 fallback。
    """

    # ── 系统人格 ──

    SYSTEM_PROMPT = """你是一个名为 AID 的桌面智能助手，运行在用户的 Windows 桌面上。
你有一个淡紫色磨砂玻璃风格的悬浮球界面，常驻桌面右上角。

## 你的能力
你可以：
- 截取屏幕并识别文字（quick_look）
- 列出当前打开的窗口（list_windows）
- 获取鼠标位置（mouse_position）
- 在指定坐标点击（click）
- 输入文字（type_text）
- 查询/保存记忆（query_memory / save_memory）
- 显示 AID 数字身份（show_identity）

## 你的性格
- 温和、简洁、务实
- 用中文回答，口语化
- 每次回答控制在 3-5 句，不废话
- 如果用户没说具体坐标的点击操作，先 quick_look 了解屏幕布局再说

## 规则
- 如果用户随便聊天（打招呼、问好、闲聊），直接 chat 回复，不用调工具
- 如果用户请求涉及屏幕内容（"看屏幕"、"帮我看看"、"有什么"），先 quick_look
- 执行前先理解用户意图，不要盲目调工具
"""

    def __init__(self, fairy, memory_store=None):
        self.fairy = fairy
        self.memory = memory_store

        # 对话历史（当前会话）
        self.history: List[dict] = []
        self.max_history = 20  # 保留最近 N 轮

        # LLM 客户端
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.api_base = os.getenv("OPENAI_API_BASE", "")
        self.model = os.getenv("AID_LLM_MODEL", "gpt-4o-mini")
        self._client = None

        # 注册工具
        self.tools: Dict[str, FairyTool] = {}
        self._register_tools()

        # 启动时加载过往记忆
        self._load_past_context()

    # ── 属性 ──

    @property
    def client(self):
        if self._client is None and self.api_key:
            kwargs = {"api_key": self.api_key}
            if self.api_base:
                kwargs["base_url"] = self.api_base
            self._client = OpenAI(**kwargs)
        return self._client

    @property
    def available(self) -> bool:
        """LLM 是否可用"""
        return bool(self.api_key) and HAS_OPENAI

    # ── 工具注册 ──

    def _register_tools(self):
        """注册所有桌面操作工具"""

        def _quick_look():
            """截屏 + OCR"""
            if not hasattr(self.fairy, "_quick_look"):
                return "截屏工具未就绪"
            # 直接调用 fairy 的方法
            self.fairy._quick_look()
            return "✅ 正在查看屏幕，结果已显示"

        def _list_windows():
            if not hasattr(self.fairy, "_list_windows"):
                return "窗口控制未就绪"
            self.fairy._list_windows()
            return "✅ 窗口列表已显示"

        def _mouse_position():
            if not hasattr(self.fairy, "_show_mouse_position"):
                return "鼠标控制未就绪"
            self.fairy._show_mouse_position()
            return "✅ 鼠标位置已显示"

        def _click(x: int, y: int):
            if not hasattr(self.fairy, "_parse_and_click"):
                return "点击控制未就绪"
            self.fairy._parse_and_click(f"点击 {x} {y}")
            return f"✅ 已点击 ({x}, {y})"

        def _type_text(text: str):
            if not hasattr(self.fairy, "_parse_and_type"):
                return "输入控制未就绪"
            self.fairy._parse_and_type(f"输入 {text}")
            return f"✅ 已输入: {text}"

        def _show_identity():
            if not hasattr(self.fairy, "_show_identity"):
                return "身份系统未就绪"
            self.fairy._show_identity()
            return "✅ 身份信息已显示"

        def _save_memory(content: str, category: str = "对话记录"):
            if self.memory:
                self.memory.save(
                    content=content,
                    category=category,
                    source="user",
                    tags=["desktop_fairy"],
                )
                return "✅ 已记住"
            return "记忆系统未就绪"

        def _query_memory(keyword: str = ""):
            if self.memory:
                results = self.memory.query(keyword=keyword, limit=5)
                if results:
                    lines = [f"• {r['content'][:100]}" for r in results]
                    return "📖 我记得：\n" + "\n".join(lines)
                return "📭 没有相关记忆"
            return "记忆系统未就绪"

        # 注册
        self._add_tool(
            FairyTool(
                name="quick_look",
                description="截取当前屏幕的完整画面，并自动识别其中的文字。适合用户问「屏幕上有什么」「看看这个」「帮我看一下」时调用。",
                parameters={"type": "object", "properties": {}, "required": []},
                fn=_quick_look,
            )
        )
        self._add_tool(
            FairyTool(
                name="list_windows",
                description="列出当前 Windows 桌面上所有打开的窗口标题。",
                parameters={"type": "object", "properties": {}, "required": []},
                fn=_list_windows,
            )
        )
        self._add_tool(
            FairyTool(
                name="mouse_position",
                description="获取当前鼠标指针在屏幕上的坐标位置 (x, y)。",
                parameters={"type": "object", "properties": {}, "required": []},
                fn=_mouse_position,
            )
        )
        self._add_tool(
            FairyTool(
                name="click",
                description="在屏幕指定坐标 (x, y) 处模拟鼠标点击（左键）。",
                parameters={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "屏幕 x 坐标"},
                        "y": {"type": "integer", "description": "屏幕 y 坐标"},
                    },
                    "required": ["x", "y"],
                },
                fn=_click,
            )
        )
        self._add_tool(
            FairyTool(
                name="type_text",
                description="在当前焦点窗口输入指定文字。适合用户说「帮我输入」「打字」「写」时调用。",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "要输入的文字内容"},
                    },
                    "required": ["text"],
                },
                fn=_type_text,
            )
        )
        self._add_tool(
            FairyTool(
                name="show_identity",
                description="显示 AID 数字身份信息（DID 和公钥）。",
                parameters={"type": "object", "properties": {}, "required": []},
                fn=_show_identity,
            )
        )
        self._add_tool(
            FairyTool(
                name="save_memory",
                description="保存一段信息到长期记忆中，以后可以查询。适合用户告诉你个人信息、偏好、重要事情时调用。",
                parameters={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "要记住的内容"},
                        "category": {
                            "type": "string",
                            "enum": ["对话记录", "用户偏好", "个人信息", "任务待办"],
                            "description": "记忆分类",
                        },
                    },
                    "required": ["content"],
                },
                fn=_save_memory,
            )
        )
        self._add_tool(
            FairyTool(
                name="query_memory",
                description="查询长期记忆中保存的信息。适合用户问「你记得…」「我之前说过…」时调用。",
                parameters={
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "搜索关键词，不传则返回最近记录"},
                    },
                    "required": [],
                },
                fn=_query_memory,
            )
        )

    def _add_tool(self, tool: FairyTool):
        self.tools[tool.name] = tool

    # ── 记忆管理 ──

    def _load_past_context(self):
        """启动时加载最近对话记忆"""
        if not self.memory:
            return
        try:
            recent = self.memory.query(keyword="", category="对话记录", limit=3)
            if recent:
                self._ctx_summary = "上次聊过的话题：\n" + "\n".join(f"· {r['content'][:120]}" for r in recent)
            else:
                self._ctx_summary = ""
        except Exception:
            self._ctx_summary = ""

    def _remember(self, user_cmd: str, reply: str):
        """保存一轮对话到长期记忆"""
        if not self.memory:
            return
        try:
            self.memory.save(
                content=f"用户说: {user_cmd} → AID: {reply[:200]}",
                category="对话记录",
                source="user",
                tags=["desktop_fairy"],
            )
        except Exception:
            pass

    # ── 核心处理 ──

    def process(self, cmd: str) -> Optional[str]:
        """
        处理一条自然语言指令。

        Returns:
            str: LLM 生成的回复文本
            None: LLM 不可用，调用方应走关键词 fallback
        """
        cmd = cmd.strip()
        if not cmd:
            return "嗯？"

        if not self.available:
            return None  # fallback

        # 显示"正在思考"
        self.fairy._show_result("💭 正在思考...")

        # 在线程中执行，避免阻塞 UI
        result_container = []

        def _run():
            try:
                reply = self._call_llm(cmd)
                result_container.append(reply)
                self.fairy._show_result(reply)
                self._remember(cmd, reply)
            except Exception as e:
                err = f"🤖 出错了：{e}"
                result_container.append(err)
                self.fairy._show_result(err)

        threading.Thread(target=_run, daemon=True).start()
        return "（处理中）"  # 占位，实际结果在线程里

    def _call_llm(self, cmd: str) -> str:
        """调用 OpenAI API 处理指令"""
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        # 注入上下文记忆
        if hasattr(self, "_ctx_summary") and self._ctx_summary:
            messages.append({"role": "system", "content": self._ctx_summary})

        # 注入最近对话历史
        for h in self.history[-self.max_history :]:
            messages.append(h)

        # 当前用户指令
        messages.append({"role": "user", "content": cmd})

        # 准备 tools
        openai_tools = [t.to_openai_tool() for t in self.tools.values()]

        # 最大轮次
        max_turns = 5
        for turn in range(max_turns):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=openai_tools if openai_tools else None,
                    tool_choice="auto" if openai_tools else None,
                    temperature=0.7,
                    max_tokens=1024,
                )
            except Exception as e:
                return f"🤖 AI 服务暂时不可用：{e}"

            choice = response.choices[0]
            msg = choice.message

            # 检查是否有工具调用
            if msg.tool_calls:
                messages.append(msg)  # 追加 assistant 消息
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    tool = self.tools.get(tool_name)
                    if tool is None:
                        result = f"[未知工具: {tool_name}]"
                    else:
                        result = tool(**args)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                continue  # 再调一次 LLM 让它生成最终回复

            # 没有工具调用 → 这是最终回复
            reply = msg.content or ""
            # 记录到历史
            self.history.append({"role": "user", "content": cmd})
            self.history.append({"role": "assistant", "content": reply})
            return reply

        return "🤔 我思考太久了，请再说一遍？"
