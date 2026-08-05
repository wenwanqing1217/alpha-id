# TERM: FeishuBridge — 飞书渠道适配器（ChannelAdapter 实现，WebSocket + Webhook 双模式）
"""
Alpha-ID Feishu Bridge — 飞书集成
===================================

打通飞书与 Alpha-ID：
  - 飞书消息 → 提取工作内容 → 更新记忆
  - Agent 主动通过飞书联系用户
  - 飞书机器人作为 Alpha-ID 的"嘴"
  - 写代码模式：切换后端（atomcode/zcode/codex）执行编程任务

模式说明：
  CHAT 模式（默认）— 普通对话，消息交给上层处理
  CODE 模式         — 自动执行编程任务，结果直接返回

命令列表：
  /mode              — 切换对话/代码模式
  /mode chat         — 切换到对话模式
  /mode code         — 切换到代码模式
  /backend list      — 列出可用后端
  /backend <name>    — 切换后端（atomcode/zcode/codex）
  /status            — 查看当前模式和后端
  /code <prompt>     — 显式执行代码任务

核心洞察：
  飞书是工作场景的入口。工作内容应该自动沉淀到记忆系统。
  飞书也是编程入口——用户说"写个XXX"，系统应切换到代码模式。
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 代码模式：多后端支持（与 ghost-main/feishu-bot/code_runner 对齐）
# ══════════════════════════════════════════════════════════════

# 安全：prompt 输入校验
_FORBIDDEN_CHARS = re.compile(r'[;&|`$(){}[\]<>!\\]')
_MAX_PROMPT_LENGTH = 4096


def _sanitize_prompt(prompt: str) -> str:
    """清理用户输入的 prompt，防止命令注入"""
    if not prompt or not prompt.strip():
        raise ValueError("Prompt 不能为空")
    if len(prompt) > _MAX_PROMPT_LENGTH:
        raise ValueError(f"Prompt 超长（最大 {_MAX_PROMPT_LENGTH} 字符）")
    if _FORBIDDEN_CHARS.search(prompt):
        prompt = _FORBIDDEN_CHARS.sub("", prompt)
    return prompt.strip()


# 后端配置（单一起源，与 ghost-main/feishu-bot/code_runner.py 对齐）
BACKENDS: Dict[str, Dict[str, Any]] = {
    "atomcode": {
        "cmd": "atomcode",
        "args": ["-p", "{prompt}", "-y", "--provider", "AtomGit-deepseek-v4-flash"],
        "desc": "AtomCode CLI（AtomGit 免费额度）",
    },
    "zcode": {
        "cmd": "node",
        "args": [
            os.environ.get("ZCODE_PATH", str(Path.home() / "Software" / "ZCode" / "resources" / "glm" / "zcode.cjs")),
            "--prompt", "{prompt}", "--mode", "yolo", "--json"
        ],
        "desc": "ZCode CLI（GLM / LongCat）",
    },
    "codex": {
        "cmd": "codex",
        "args": ["-p", "{prompt}"],
        "desc": "Codex CLI（桌面版，仅限本机）",
    },
}

# 环境变量覆盖自定义后端
_custom = os.environ.get("CUSTOM_BACKEND", "").strip()
if _custom:
    parts = _custom.split(":", 2)
    if len(parts) == 3:
        BACKENDS[parts[0]] = {
            "cmd": parts[1],
            "args": parts[2].split("|"),
            "desc": f"自定义({parts[0]})",
        }

DEFAULT_BACKEND = os.environ.get("DEFAULT_BACKEND", "atomcode")


@dataclass
class CodeResult:
    """代码执行结果"""
    backend: str
    prompt: str
    output: str
    success: bool
    duration: float = 0.0
    error: str = ""


class CodeRunner:
    """
    编程技能执行器，支持多个后端引擎

    用法：
        runner = CodeRunner()
        result = runner.run("写个 Python 爬虫", backend="atomcode")
        print(result.output)

    支持命令：
        /backend list     — 列出可用后端
        /backend <name>   — 切换后端
        /status           — 查看当前后端
    """

    def __init__(self, max_concurrent: int = 3):
        self._max_concurrent = max_concurrent
        self._chat_backends: Dict[str, str] = {}  # chat_id → backend

    def get_backend(self, chat_id: str = "") -> str:
        """获取指定会话的当前后端"""
        return self._chat_backends.get(chat_id, DEFAULT_BACKEND)

    def set_backend(self, chat_id: str, name: str) -> bool:
        """切换指定会话的后端"""
        if name in BACKENDS:
            self._chat_backends[chat_id] = name
            return True
        return False

    def list_backends(self, chat_id: str = "") -> str:
        """列出所有可用后端"""
        lines = ["🛠️ 可用后端："]
        cur = self.get_backend(chat_id)
        for name, cfg in BACKENDS.items():
            mark = " ← 当前" if name == cur else ""
            lines.append(f"  {name} — {cfg['desc']}{mark}")
        return "\n".join(lines)

    def run(self, prompt: str, backend: str = "", timeout: int = 120,
            chat_id: str = "") -> CodeResult:
        """
        执行编程任务（同步封装）

        Args:
            prompt: 用户需求文本
            backend: 指定后端（空则用会话默认）
            timeout: 超时秒数
            chat_id: 会话标识

        Returns:
            CodeResult
        """
        import asyncio
        return asyncio.run(self._arun(prompt, backend, timeout, chat_id))

    async def _arun(self, prompt: str, backend: str, timeout: int,
                    chat_id: str) -> CodeResult:
        """异步执行核心"""
        start = time.time()

        # 安全校验
        try:
            prompt = _sanitize_prompt(prompt)
        except ValueError as e:
            return CodeResult(
                backend=backend or self.get_backend(chat_id),
                prompt=prompt, output="", success=False,
                error=str(e), duration=0,
            )

        # 确定后端
        be_name = backend or self.get_backend(chat_id)
        be = BACKENDS.get(be_name)
        if not be:
            return CodeResult(
                backend=be_name, prompt=prompt, output="", success=False,
                error=f"后端 '{be_name}' 不存在，可用: {', '.join(BACKENDS.keys())}",
                duration=0,
            )

        cmd = be["cmd"]
        args = [a.replace("{prompt}", prompt) for a in be["args"]]

        logger.info("执行: %s ...", cmd)

        try:
            import asyncio
            cwd = os.environ.get("CODE_RUNNER_DIR", "") or None
            proc = await asyncio.create_subprocess_exec(
                cmd, *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return CodeResult(
                    backend=be_name, prompt=prompt, output="", success=False,
                    error=f"⏰ 超时：{timeout} 秒未完成", duration=timeout,
                )

            duration = time.time() - start
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace")[:500]
                return CodeResult(
                    backend=be_name, prompt=prompt, output="", success=False,
                    error=f"❌ 执行出错:\n{err}", duration=duration,
                )

            output = stdout.decode("utf-8", errors="replace").strip()
            return CodeResult(
                backend=be_name, prompt=prompt,
                output=output or "执行完毕（无输出）",
                success=True, duration=duration,
            )
        except FileNotFoundError:
            return CodeResult(
                backend=be_name, prompt=prompt, output="", success=False,
                error=f"❌ 未找到命令 '{cmd}'，请确认已安装",
                duration=time.time() - start,
            )
        except Exception as e:
            return CodeResult(
                backend=be_name, prompt=prompt, output="", success=False,
                error=f"❌ 异常: {e}", duration=time.time() - start,
            )

    def handle_command(self, text: str, chat_id: str = "") -> Optional[str]:
        """
        处理飞书命令

        支持：
            /backend list     — 列出后端
            /backend <name>   — 切换后端
            /status           — 当前后端
            /code <prompt>    — 执行代码任务（显式）

        返回 None 表示不是命令
        """
        text = text.strip()
        if not text.startswith("/"):
            return None

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd == "/backend":
            if len(parts) == 1 or parts[1].strip() in ("list", "ls"):
                return self.list_backends(chat_id)
            name = parts[1].strip()
            if self.set_backend(chat_id, name):
                return f"✅ 已切换后端: {name} — {BACKENDS[name]['desc']}"
            return f"❌ 未知后端: {name}，可用: {', '.join(BACKENDS.keys())}"

        elif cmd == "/status":
            cur = self.get_backend(chat_id)
            return f"📊 当前后端: {cur} — {BACKENDS[cur]['desc']}"

        elif cmd == "/code":
            if len(parts) < 2:
                return "用法: /code <你的编程需求>"
            result = self.run(parts[1], chat_id=chat_id)
            if result.success:
                return f"✅ [{result.backend}] ({result.duration:.1f}s)\n{result.output}"
            return f"❌ [{result.backend}] {result.error}"

        return None


# ══════════════════════════════════════════════════════════════
# 飞书消息
# ══════════════════════════════════════════════════════════════

@dataclass
class FeishuMessage:
    """飞书消息"""
    msg_id: str = ""
    sender: str = ""
    chat_id: str = ""
    content: str = ""
    msg_type: str = "text"  # text / image / file
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processed: bool = False


# ══════════════════════════════════════════════════════════════
# 飞书桥接器
# ══════════════════════════════════════════════════════════════

class FeishuBridge:
    """
    飞书桥接器

    用法：
        bridge = FeishuBridge(app_id="xxx", app_secret="xxx")
        bridge.on_message(handle_feishu_msg)
        bridge.send_message(chat_id="xxx", text="你好")

    代码模式：
        # 用户切换到代码模式
        bridge.set_mode(chat_id, Mode.CODE)
        # 消息会自动走 CodeRunner 执行
        # 切换回对话模式
        bridge.set_mode(chat_id, Mode.CHAT)
    """

    # 模式
    CHAT = "chat"   # 普通对话模式
    CODE = "code"   # 写代码模式

    def __init__(self, app_id: str = "", app_secret: str = "",
                 verification_token: str = "", encrypt_key: str = ""):
        self._app_id = app_id
        self._app_secret = app_secret
        self._verification_token = verification_token
        self._encrypt_key = encrypt_key
        self._tenant_token = ""
        self._token_expire = 0.0
        self._callbacks: List[Callable[[FeishuMessage], None]] = []
        self._stats = {"received": 0, "sent": 0, "extracted": 0, "code_runs": 0}
        self._ws_client = None  # 飞书 SDK 长连接客户端

        # 代码模式
        self._runner = CodeRunner()
        self._chat_modes: Dict[str, str] = {}  # chat_id → mode

    # ── 模式切换 ──

    def set_mode(self, chat_id: str, mode: str) -> bool:
        """
        切换会话模式

        Args:
            chat_id: 会话 ID
            mode: CHAT 或 CODE

        Returns:
            是否切换成功
        """
        if mode not in (self.CHAT, self.CODE):
            return False
        old = self._chat_modes.get(mode)
        self._chat_modes[chat_id] = mode
        logger.info("会话 %s 模式切换: %s → %s", chat_id[:8], old, mode)
        return True

    def get_mode(self, chat_id: str) -> str:
        """获取会话当前模式"""
        return self._chat_modes.get(chat_id, self.CHAT)

    def toggle_mode(self, chat_id: str) -> str:
        """切换会话模式（对话 ↔ 代码）"""
        current = self.get_mode(chat_id)
        new_mode = self.CODE if current == self.CHAT else self.CHAT
        self.set_mode(chat_id, new_mode)
        return new_mode

    # ── 消息回调 ──

    def on_message(self, callback: Callable[[FeishuMessage], None]):
        """注册消息回调"""
        self._callbacks.append(callback)

    def set_credentials(self, app_id: str, app_secret: str,
                        verification_token: str = "", encrypt_key: str = ""):
        """设置飞书凭证"""
        self._app_id = app_id
        self._app_secret = app_secret
        self._verification_token = verification_token
        self._encrypt_key = encrypt_key

    # ── Token 管理 ──

    def _get_tenant_token(self) -> str:
        """获取 tenant_access_token（带缓存）"""
        if self._tenant_token and time.time() < self._token_expire:
            return self._tenant_token

        try:
            import httpx
            resp = httpx.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self._app_id,
                    "app_secret": self._app_secret,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("code") == 0:
                self._tenant_token = data["tenant_access_token"]
                self._token_expire = time.time() + data.get("expire", 7200) - 300
                return self._tenant_token
        except Exception as e:
            logger.error("飞书 token 获取失败: %s", e)

        return ""

    # ── 消息处理 ──

    def handle_webhook(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理飞书 Webhook 回调

        支持：
        - URL 验证（首次配置时飞书会发验证请求）
        - 事件回调 v2.0
        """
        # URL 验证
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge", "")}

        # 事件回调 v2.0
        header = body.get("header", {})
        event = body.get("event", {})

        if header.get("event_type") == "im.message.receive_v1":
            return self._handle_message_event(event)

        return {"code": 0, "msg": "ok"}

    def _handle_message_event(self, event: Dict) -> Dict:
        """处理消息事件"""
        message = event.get("message", {})
        sender = event.get("sender", {})

        msg = FeishuMessage(
            msg_id=message.get("message_id", ""),
            sender=sender.get("sender_id", {}).get("open_id", ""),
            chat_id=message.get("chat_id", ""),
            content=self._extract_text(message),
            msg_type=message.get("message_type", "text"),
        )

        self._stats["received"] += 1

        # 通知回调
        for cb in self._callbacks:
            try:
                cb(msg)
            except Exception:
                pass

        return {"code": 0, "msg": "ok"}

    def _extract_text(self, message: Dict) -> str:
        """从消息中提取文本内容"""
        msg_type = message.get("message_type", "text")
        content = message.get("content", "{}")

        try:
            data = json.loads(content)
        except Exception:
            return content

        if msg_type == "text":
            return data.get("text", "")
        elif msg_type == "post":
            # 富文本消息
            parts = []
            content_list = data.get("content", [])
            for block in content_list:
                if isinstance(block, list):
                    for seg in block:
                        if seg.get("tag") == "text":
                            parts.append(seg.get("text", ""))
                        elif seg.get("tag") == "at":
                            parts.append(f"@{seg.get('user_id', 'unknown')}")
            return " ".join(parts)

        return data.get("text", "")

    # ── 代码模式核心 ──

    def handle_message(self, msg: FeishuMessage) -> str:
        """
        根据会话模式自动路由消息

        - CHAT 模式：返回空（交给普通对话处理）
        - CODE 模式：作为编程任务执行

        也处理命令：
            /mode            — 切换对话/代码模式
            /mode chat       — 切换到对话模式
            /mode code       — 切换到代码模式
            /backend list    — 列出后端
            /backend <name>  — 切换后端
            /status          — 查看状态
            /code <prompt>   — 执行代码任务
        """
        text = msg.content.strip()
        chat_id = msg.chat_id

        # 命令处理
        if text.startswith("/"):
            # 模式切换命令
            if text.startswith("/mode"):
                parts = text.split(maxsplit=1)
                if len(parts) == 1:
                    new_mode = self.toggle_mode(chat_id)
                    icon = "💬" if new_mode == self.CHAT else "💻"
                    return f"{icon} 已切换到{'对话' if new_mode == self.CHAT else '代码'}模式"
                mode_str = parts[1].strip().lower()
                if mode_str in ("chat", "对话"):
                    self.set_mode(chat_id, self.CHAT)
                    return "💬 已切换到对话模式"
                elif mode_str in ("code", "代码"):
                    self.set_mode(chat_id, self.CODE)
                    return "💻 已切换到代码模式"
                return "❌ 用法: /mode [chat|code]"

            # CodeRunner 命令
            result = self._runner.handle_command(text, chat_id)
            if result is not None:
                return result

        # 代码模式：自动执行编程任务
        if self.get_mode(chat_id) == self.CODE:
            result = self._runner.run(text, chat_id=chat_id)
            self._stats["code_runs"] += 1
            if result.success:
                return f"💻 [{result.backend}] ({result.duration:.1f}s)\n{result.output}"
            return f"❌ [{result.backend}] {result.error}"

        # 对话模式：返回空（交给上层处理）
        return ""

    # ── 主动发送 ──

    def send_message(self, chat_id: str, text: str,
                     msg_type: str = "text") -> bool:
        """
        发送消息到飞书群/个人

        Args:
            chat_id: 群聊 ID 或 open_id
            text: 消息内容
            msg_type: 消息类型（text / interactive）
        """
        token = self._get_tenant_token()
        if not token:
            logger.warning("无法获取飞书 token，发送失败")
            return False

        try:
            import httpx

            # 判断是群聊还是私聊
            receive_id_type = "chat_id" if chat_id.startswith("oc_") else "open_id"

            resp = httpx.post(
                f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "receive_id": chat_id,
                    "msg_type": msg_type,
                    "content": json.dumps({"text": text}) if msg_type == "text" else text,
                },
                timeout=10,
            )

            result = resp.json()
            if result.get("code") == 0:
                self._stats["sent"] += 1
                return True
            else:
                logger.warning("飞书发送失败: %s", result.get("msg", ""))
                return False

        except Exception as e:
            logger.error("飞书发送异常: %s", e)
            return False

    # ── 内容提取 ──

    def extract_work_context(self, messages: List[FeishuMessage]) -> Dict[str, Any]:
        """
        从飞书消息中提取工作上下文

        提取：
        - 正在做什么
        - 进度如何
        - 卡在哪里
        - 做了什么决定
        """
        if not messages:
            return {}

        # 合并最近的消息
        recent_text = "\n".join(m.content for m in messages[-20:] if m.content)

        if not recent_text.strip():
            return {}

        # 简单的规则提取
        context = {
            "raw_summary": recent_text[:500],
            "projects_mentioned": [],
            "deadlines": [],
            "blockers": [],
            "decisions": [],
        }

        # 提取项目名（"项目"后面的词）
        proj_matches = re.findall(r'项目[：:]\s*(\S+)', recent_text)
        context["projects_mentioned"] = list(set(proj_matches))

        # 提取截止日期
        deadline_matches = re.findall(r'(截止|deadline|DDL)[：:]\s*(\S+)', recent_text)
        context["deadlines"] = [m[1] for m in deadline_matches]

        # 提取卡点
        blocker_keywords = ["卡住", "阻塞", "block", "问题", "报错", "失败"]
        for msg in messages:
            for kw in blocker_keywords:
                if kw in msg.content:
                    context["blockers"].append(msg.content[:100])
                    break

        self._stats["extracted"] += 1
        return context

    # ── WebSocket 长连接（飞书官方 SDK） ──

    def start_websocket(self, stop_event=None):
        """
        使用飞书官方 SDK (lark_oapi) 启动 WebSocket 长连接

        飞书长连接协议：
        1. SDK 内部通过 REST API 获取动态 WSS 地址
        2. 使用 protobuf 帧格式通信
        3. 自动处理鉴权、心跳、ACK、断线重连

        Args:
            stop_event: threading.Event 用于停止循环
        """
        try:
            import lark_oapi as lark
        except ImportError:
            logger.error("lark_oapi 未安装，无法启动飞书长连接。请运行: pip install lark-oapi")
            return

        if not self._app_id or not self._app_secret:
            logger.error("飞书凭证未配置，无法启动长连接")
            return

        def _on_message_receive(data):
            """处理飞书消息事件 (P2ImMessageReceiveV1)"""
            try:
                event = data.event
                message = event.message
                sender = event.sender

                msg = FeishuMessage(
                    msg_id=message.message_id if message else "",
                    sender=sender.sender_id.open_id if sender and sender.sender_id else "",
                    chat_id=message.chat_id if message else "",
                    content=self._extract_sdk_text(message),
                    msg_type=message.message_type if message else "text",
                )

                self._stats["received"] += 1
                logger.info("飞书消息收到: chat=%s sender=%s content=%s",
                            msg.chat_id[:12] if msg.chat_id else "?",
                            msg.sender[:12] if msg.sender else "?",
                            msg.content[:50])

                # 通知回调
                for cb in self._callbacks:
                    try:
                        cb(msg)
                    except Exception as e:
                        logger.error("飞书回调执行异常: %s", e)

            except Exception as e:
                logger.error("飞书消息处理异常: %s", e)

        # 构建事件处理器
        event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(_on_message_receive) \
            .build()

        # 创建长连接客户端
        cli = lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        self._ws_client = cli
        logger.info("飞书 WebSocket 长连接启动中（官方 SDK）...")

        # cli.start() 是阻塞调用，SDK 内部自动处理重连
        try:
            cli.start()
        except KeyboardInterrupt:
            logger.info("飞书长连接收到中断信号，正在停止...")
        except Exception as e:
            logger.error("飞书长连接异常: %s", e)

    def _extract_sdk_text(self, message) -> str:
        """从 SDK 消息对象中提取文本"""
        if not message:
            return ""

        msg_type = message.message_type or "text"
        content_str = message.content or "{}"

        try:
            data = json.loads(content_str)
        except Exception:
            return content_str

        if msg_type == "text":
            return data.get("text", "")
        elif msg_type == "post":
            parts = []
            content_list = data.get("content", [])
            for block in content_list:
                if isinstance(block, list):
                    for seg in block:
                        if isinstance(seg, dict):
                            if seg.get("tag") == "text":
                                parts.append(seg.get("text", ""))
                            elif seg.get("tag") == "at":
                                parts.append(f"@{seg.get('user_id', 'unknown')}")
            return " ".join(parts)

        return data.get("text", "")

    # ── 统计 ──

    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()

    def get_runner(self) -> CodeRunner:
        """获取 CodeRunner 实例"""
        return self._runner
