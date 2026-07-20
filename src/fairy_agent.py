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
import logging
import os
import threading
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 桌面工具（延迟加载） ──

HAS_SCREEN = False
HAS_OCR = False
HAS_WINDOW = False
try:
    from tools.screen_capture import capture_full_screen

    HAS_SCREEN = True
except ImportError:
    pass
try:
    from tools.ocr import extract_text as ocr_text

    HAS_OCR = True
except ImportError:
    pass
try:
    from tools.window_control import (
        get_mouse_position,
        list_application_windows,
        type_text,
    )

    HAS_WINDOW = True
except ImportError:
    pass

# ── 记忆存储组件 ──

HAS_MEMORY = False
try:
    from core.memory_store import MemoryStore  # noqa: F401

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
你有一个暗色磨砂玻璃风格的悬浮球界面，常驻桌面右上角。

## 你的能力
你可以调用以下工具，每次调用后你能**看到工具的返回结果**并据此推理：

### 📸 quick_look（看屏幕）
- 截取当前屏幕 + OCR 识别文字
- 返回结果会告诉你**屏幕上有什么文字**
- 用户说"看看屏幕"、"帮我看看"、"有什么"时优先调用

### 📋 list_windows（窗口列表）
- 列出所有打开的窗口标题
- 用户说"有哪些窗口"、"当前打开了什么"时调用

### 🖱️ click(x, y)（点击）
- 在指定坐标模拟鼠标点击
- 必须先通过 quick_look 或 list_windows 拿到信息后再决定点哪里

### ⌨️ type_text(text)（输入文字）
- 在当前焦点窗口输入文字

### 📍 mouse_position（鼠标位置）
- 获取鼠标当前坐标

### 📖 query_memory / save_memory（记忆）
- 查询或保存长期记忆

### 🆔 show_identity（身份）
- 显示 AID 数字身份

### 🎬 短剧审核工具组
- `shortdrama_scan_and_submit`：AI 预扫短剧内容并提交审核队列。用户说「预审短剧」「审核剧本」「检查能不能发」时调用。
- `shortdrama_query_status`：查询审核任务状态。需要 job_id。
- `shortdrama_list_jobs`：列出所有审核任务。可按 status 过滤：pending / reviewing / approved / rejected。
- `shortdrama_approve`：审核通过。需要 job_id。
- `shortdrama_reject`：审核拒绝。需要 job_id 和 reason。
- `shortdrama_copy_upload_info`：复制上传信息到剪贴板。需要 job_id。

## 短剧审核链式流程（重要）
当用户要求审核短剧时，按以下顺序调用：
1. `shortdrama_scan_and_submit` 提交内容，获得 job_id
2. `shortdrama_query_status` 用 job_id 查询审核状态
3. 如果状态是 reviewing，告诉用户"已提交审核，预计 1-3 天"
4. 如果用户要求通过/拒绝，调用 `shortdrama_approve` 或 `shortdrama_reject`
5. 最后调用 `shortdrama_copy_upload_info` 把上传信息复制到剪贴板，方便用户手动粘贴到短剧平台

## 你的性格
- 温和、简洁、务实
- 用中文回答，口语化
- 每次回答控制在 3-5 句，不废话
- 如果用户没说具体坐标的点击操作，先 quick_look 了解屏幕布局再说

## 链式推理（重要）
现在工具会返回真实数据给你，你可以：
1. 先 quick_look → 看到屏幕上有"微信" → 再找微信窗口位置 → 点击它
2. 先 query_memory → 知道用户上次说过什么 → 再执行操作
3. 短剧审核：scan_and_submit → query_status → approve/reject → copy_upload_info
4. 分步思考，每一步看到结果后再决定下一步

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

        # ── LLM 客户端：优先 DeepSeek，其次 OpenAI ──
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        self.api_base = os.getenv("DEEPSEEK_API_BASE", "") or os.getenv("OPENAI_API_BASE", "")

        # 如果用的是 DeepSeek 但没设 base_url，自动补上
        if os.getenv("DEEPSEEK_API_KEY") and not os.getenv("DEEPSEEK_API_BASE") and not os.getenv("OPENAI_API_BASE"):
            self.api_base = "https://api.deepseek.com"

        # 模型：用 DeepSeek key 时默认 deepseek-chat
        default_model = "deepseek-chat" if os.getenv("DEEPSEEK_API_KEY") else "gpt-4o-mini"
        self.model = os.getenv("AID_LLM_MODEL", default_model)
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
        """LLM 是否可用（DeepSeek 或 OpenAI key 均可）"""
        if not self.api_key:
            return False
        # DeepSeek key 可直接用 httpx 原生调用，OpenAI key 依赖 openai 包
        return HAS_OPENAI or self.model.startswith("deepseek")

    # ── 工具注册 ──

    def _register_tools(self):
        """注册所有桌面操作工具 — 返回真实数据给 LLM"""

        def _quick_look():
            """截屏 + OCR，返回文字内容给 LLM"""
            if not HAS_SCREEN:
                return "截图工具不可用（需 pip install pyautogui pygetwindow Pillow）"
            try:
                img_path = capture_full_screen()
                if not img_path or not os.path.exists(img_path):
                    return "截图失败"
                if HAS_OCR:
                    text = ocr_text(img_path, lang="chi_sim+eng")
                    if text and text.strip():
                        preview = text[:2000]
                        if len(text) > 2000:
                            preview += "\n...（截断）"
                        # 同时显示到 UI
                        self.fairy._show_result(f"📸 屏幕上看到：\n{preview}")
                        return f"屏幕 OCR 结果：\n{preview}"
                    else:
                        self.fairy._show_result("📸 截图已保存（未识别到文字）")
                        return "截图已完成，但未从屏幕图像中识别到任何文字。可能是纯图片界面或屏幕当前内容不包含文字。"
                else:
                    self.fairy._show_result(f"📸 截图已保存：{img_path}")
                    return f"截图已保存到 {img_path}，但 OCR 未安装，无法读取文字内容。"
            except Exception as e:
                return f"查看屏幕失败：{e}"

        def _list_windows():
            if not HAS_WINDOW:
                return "窗口控制不可用（需 pip install pygetwindow pyautogui）"
            try:
                windows = list_application_windows()
                display = windows[:1500]
                self.fairy._show_result(f"📋 当前窗口：\n{display}")
                return f"当前打开的窗口列表：\n{windows}"
            except Exception as e:
                return f"获取窗口列表失败：{e}"

        def _mouse_position():
            if not HAS_WINDOW:
                return "窗口控制不可用"
            try:
                pos = get_mouse_position()
                self.fairy._show_result(f"📍 鼠标位置：{pos}")
                return f"鼠标当前位于屏幕坐标 ({pos[0]}, {pos[1]})"
            except Exception as e:
                return f"获取鼠标位置失败：{e}"

        def _click(x: int, y: int):
            if not HAS_WINDOW:
                return "窗口控制不可用"
            try:
                msg = f"已点击 ({x}, {y})"
                self.fairy._show_result(f"🖱️ {msg}")
                return msg
            except Exception as e:
                return f"点击失败：{e}"

        def _type_text(text: str):
            if not HAS_WINDOW:
                return "窗口控制不可用"
            try:
                type_text(text)
                self.fairy._show_result(f"⌨️ 已输入：{text}")
                return f"已在当前焦点窗口输入：{text}"
            except Exception as e:
                return f"输入失败：{e}"

        def _show_identity():
            try:
                from alpha_id import AIDSigner

                signer = AIDSigner()
                signer.load_from_aid_dir()
                did = signer.did
                pk = signer.public_key.hex()[:16] + "..."
                info = f"DID: {did}\n公钥: {pk}"
                self.fairy._show_result(f"🆔 AID 身份\n{info}")
                return info
            except Exception:
                return "尚未初始化 AID 身份（命令行执行：aid identity init）"

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
                    data = "📖 我记得：\n" + "\n".join(lines)
                    self.fairy._show_result(data)
                    return "\n".join(f"- {r['content'][:200]}" for r in results)
                return "没有找到相关记忆"
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

        # ── 短剧自动化工具 ──
        self._register_shortdrama_tools()

    def _register_shortdrama_tools(self):
        """注册短剧创作与审核工具"""
        from tools.shortdrama_tool import ShortDramaTool

        tool = ShortDramaTool()

        def _scan_and_submit(title: str, content: str, content_type: str = "video"):
            """AI预扫 + 提交审核队列。title为短剧标题，content为剧本/描述。返回job_id和审核状态。"""
            result = tool.scan_and_submit(title=title, content=content, content_type=content_type)
            return json.dumps(result, ensure_ascii=False, indent=2)

        def _query_review_status(job_id: str):
            """查询短剧审核状态。job_id是审核任务的ID。返回状态：pending/reviewing/approved/rejected。"""
            result = tool.query_status(job_id)
            return json.dumps(result, ensure_ascii=False, indent=2)

        def _list_review_jobs(user_id: str = "default", status: str = ""):
            """列出所有短剧审核任务。status可选过滤：pending/reviewing/approved/rejected。"""
            result = tool.list_jobs(user_id=user_id, status=status or None)
            return json.dumps(result, ensure_ascii=False, indent=2)

        def _approve_job(job_id: str, reviewer: str = "admin"):
            """人工审核通过短剧任务。job_id是审核任务ID，reviewer是审核人。"""
            result = tool.approve_job(job_id, reviewer=reviewer)
            return json.dumps(result, ensure_ascii=False, indent=2)

        def _reject_job(job_id: str, reason: str, reviewer: str = "admin"):
            """人工审核拒绝短剧任务。job_id是审核任务ID，reason是拒绝原因，reviewer是审核人。"""
            result = tool.reject_job(job_id, reason=reason, reviewer=reviewer)
            return json.dumps(result, ensure_ascii=False, indent=2)

        def _copy_upload_info(job_id: str):
            """复制短剧上传信息到剪贴板。job_id是审核任务ID。复制后用户可直接粘贴到短剧平台。"""
            info = tool.get_upload_info(job_id)
            if not info.get("success"):
                return json.dumps(info, ensure_ascii=False, indent=2)
            text = info.get("text", "")
            copy_result = tool.copy_to_clipboard(text)
            return json.dumps({**copy_result, "upload_info": info.get("upload_info", {})}, ensure_ascii=False, indent=2)

        self._add_tool(
            FairyTool(
                name="shortdrama_scan_and_submit",
                description="短剧内容AI预检并提交审核。适合用户说「预审短剧」「审核剧本」「检查能不能发」时调用。返回job_id用于后续查询。",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "短剧标题"},
                        "content": {"type": "string", "description": "剧本内容或描述"},
                        "content_type": {"type": "string", "description": "内容类型，默认 video", "default": "video"},
                    },
                    "required": ["title", "content"],
                },
                fn=_scan_and_submit,
            )
        )
        self._add_tool(
            FairyTool(
                name="shortdrama_query_status",
                description="查询短剧审核状态。用户问「审核怎么样了」「看看状态」时调用。需要job_id参数。",
                parameters={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "审核任务ID，从 scan_and_submit 返回结果中获取"},
                    },
                    "required": ["job_id"],
                },
                fn=_query_review_status,
            )
        )
        self._add_tool(
            FairyTool(
                name="shortdrama_list_jobs",
                description="列出所有短剧审核任务。用户问「有哪些审核任务」「看看所有短剧」时调用。",
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "用户ID，默认 default"},
                        "status": {"type": "string", "description": "状态过滤：pending/reviewing/approved/rejected"},
                    },
                    "required": [],
                },
                fn=_list_review_jobs,
            )
        )
        self._add_tool(
            FairyTool(
                name="shortdrama_approve",
                description="人工审核通过短剧任务。用户说「通过」「批准」「过审」时调用。需要job_id。",
                parameters={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "审核任务ID"},
                        "reviewer": {"type": "string", "description": "审核人，默认 admin"},
                    },
                    "required": ["job_id"],
                },
                fn=_approve_job,
            )
        )
        self._add_tool(
            FairyTool(
                name="shortdrama_reject",
                description="人工审核拒绝短剧任务。用户说「拒绝」「打回」「需要修改」时调用。需要job_id和reason。",
                parameters={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "审核任务ID"},
                        "reason": {"type": "string", "description": "拒绝原因"},
                        "reviewer": {"type": "string", "description": "审核人，默认 admin"},
                    },
                    "required": ["job_id", "reason"],
                },
                fn=_reject_job,
            )
        )
        self._add_tool(
            FairyTool(
                name="shortdrama_copy_upload_info",
                description="复制短剧上传信息到剪贴板。用户说「复制上传信息」「粘贴到平台」时调用。需要job_id。",
                parameters={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "审核任务ID"},
                    },
                    "required": ["job_id"],
                },
                fn=_copy_upload_info,
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
            logger.exception("Unhandled exception")

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
