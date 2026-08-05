# TERM: AgentLoop — 智能体纯循环（LLM + Tools + Loop，ReAct 模式，不依赖任何框架）
"""
Agent 纯循环 —— LLM + Tools + Loop，不依赖任何框架

核心逻辑：
  1. system prompt 固定，tools 以 JSON schema 注入
  2. LLM(text→text) 返回文本中的 tool 调用标记
  3. 主循环 parse → execute → append → repeat，直到 LLM 返回最终回答

用法：
    loop = AgentLoop(alpha_id="Alpha-001")
    reply = loop.run("帮我查一下我的身份信息")
"""

import ipaddress
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from core.http_client import request
from core.interfaces import AgentContainer
from core.observability import record_llm_call
from core.settings import settings
from core.tracing import trace_span

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    httpx = None
    HAS_HTTPX = False

logger = logging.getLogger(__name__)


# ── LLM 调用常量 ──
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 2048
LLM_TIMEOUT_SECONDS = 60.0
LLM_KEEPALIVE_CONNECTIONS = 5
LLM_KEEPALIVE_EXPIRY_SECONDS = 30.0
LLM_MAX_TURNS_DEFAULT = 6
LLM_CONTEXT_HISTORY_LIMIT = 20
LLM_MAX_SENSITIVITY_DEFAULT = 70
LLM_MEMORY_QUERY_LIMIT = 5


# ── 安全：LLM base_url SSRF 防护 ──


_ALLOWED_LLM_HOSTS = {
    "api.deepseek.com",
    "api.openai.com",
    "api.siliconflow.cn",
    "open.bigmodel.cn",
    "api.moonshot.cn",
    "api.anthropic.com",
    "localhost",
    "127.0.0.1",
}


def _validate_llm_base_url(base_url: str) -> str:
    """校验 LLM base_url，防止 SSRF。"""
    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的 LLM URL scheme: {parsed.scheme}")

    if not hostname:
        raise ValueError("LLM base_url 缺少 hostname")

    # 允许显式配置的域名
    if hostname in _ALLOWED_LLM_HOSTS:
        return base_url.rstrip("/")

    # 禁止内网 / 链路本地 / 回环地址
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"LLM base_url 禁止访问内网地址: {hostname}")
    except ValueError as exc:
        if "禁止访问" in str(exc):
            raise
        # 不是 IP，继续执行域名检查

    # 未在允许列表中的域名一律拒绝，避免任意域名跳转
    raise ValueError(f"LLM base_url 域名未授权: {hostname}")


# ── Tool 描述 ──


class Tool:
    """一个可被 LLM 调用的工具"""

    def __init__(self, name: str, description: str, parameters: Dict[str, Any], fn: Callable[..., str]):
        self.name = name
        self.description = description
        self.parameters = parameters  # JSON Schema
        self.fn = fn

    def to_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def __call__(self, **kwargs) -> str:
        try:
            result = self.fn(**kwargs)
            return str(result)
        except Exception as e:
            return f"[工具错误] {e}"


def _default_backends() -> AgentContainer:
    """Create default backends from alpha_id container."""
    from alpha_id.container import Container

    container = Container.instance()

    class _ContainerBackends(AgentContainer):
        @property
        def identity(self):
            return container.identity

        @property
        def social(self):
            return container.social

        @property
        def risk(self):
            return container.risk

        @property
        def memory(self):
            return container.memory

        @property
        def actions(self):
            return container.actions

        @property
        def skill_registry(self):
            from alpha_id.skill_signer import SkillRegistry

            return SkillRegistry(storage_dir=str(Path.home() / ".aid" / "skills"))

        @property
        def skill_tracker(self):
            from alpha_id.skill_signer import SkillAttributionTracker

            return SkillAttributionTracker(storage_dir=str(Path.home() / ".aid" / "attributions"))

        @property
        def skill_runtime(self):
            registry = self.skill_registry
            tracker = self.skill_tracker
            from alpha_id.skill_signer import SkillRuntime

            return SkillRuntime(registry, tracker=tracker, poe_client=None)

        @property
        def poe_store(self):
            from alpha_id.poe import PoEStore

            return PoEStore(storage_dir=str(Path.home() / ".aid"))

    return _ContainerBackends()


# ── 内置工具 ──


def _make_tools(alpha_id: str, backends: Optional[AgentContainer] = None, signer=None) -> List[Tool]:
    """构造 Agent 可用工具列表

    Args:
        alpha_id: Agent 的 Alpha-ID
        backends: 可选的依赖注入容器
        signer: 可选的 AIDSigner 实例，用于签名执行证明（PoE）
    """
    if backends is None:
        backends = _default_backends()
    from core.action_engine.models import Action, ActionType

    def get_profile() -> str:
        profile = backends.identity.get_user_profile(alpha_id)
        return json.dumps(profile, ensure_ascii=False, default=str) if profile else "未找到身份信息"

    def get_friends() -> str:
        friends = backends.social.get_friends(alpha_id)
        return json.dumps(friends, ensure_ascii=False) if friends else "暂无好友"

    def get_risk_score() -> str:
        engine = backends.risk
        device_score = engine.calculate_device_score(None, None)
        behavior_score = engine.calculate_behavior_score({})
        voice_score = engine.calculate_voice_score(None)
        total = engine.calculate_total_risk(device_score, behavior_score, voice_score)
        level = engine.determine_risk_level(total)
        return json.dumps({"risk_score": round(total, 2), "risk_level": level}, ensure_ascii=False)

    def get_messages(unread_only: str = "true") -> str:
        msgs = backends.social.get_messages(alpha_id, unread_only=(unread_only.lower() == "true"))
        return json.dumps(msgs, ensure_ascii=False, default=str) if msgs else "暂无消息"

    def send_message(to_alpha_id: str, content: str) -> str:
        result = backends.social.send_message(alpha_id, to_alpha_id, content)
        return json.dumps(result, ensure_ascii=False)

    def send_friend_request(to_alpha_id: str, message: str = "") -> str:
        """向另一个 Alpha-ID 发送好友请求"""
        result = backends.social.send_friend_request(alpha_id, to_alpha_id, message)
        return json.dumps(result, ensure_ascii=False)

    def save_memory(content: str, category: str = "general", sensitivity: int = 0) -> str:
        """保存一条长期记忆"""
        mem = backends.memory.save(content, category=category, sensitivity=sensitivity)
        return json.dumps(mem, ensure_ascii=False)

    def query_memory(query: str = "", keyword: str = "", limit: int = 5) -> str:
        """查询长期记忆（支持语义搜索和关键词搜索）"""
        results = backends.memory.query(query_text=query or None, keyword=keyword or None, limit=limit)
        return json.dumps(results, ensure_ascii=False)

    # ── ActionEngine 工具 ──

    def plan_action(action_type: str, platform: str, intent: str, payload: str = "{}") -> str:
        """计划一个行动（提交审批，自动通过后进入待执行队列）"""
        try:
            parsed_payload = json.loads(payload)
        except json.JSONDecodeError:
            parsed_payload = {}
        action = Action(
            action_type=ActionType[action_type.upper()]
            if action_type.upper() in ActionType.__members__
            else ActionType.CUSTOM,
            platform=platform,
            intent=intent,
            payload=parsed_payload,
            source_alpha_id=alpha_id,
        )
        result = backends.actions.plan(action)
        return json.dumps(result.to_dict(), ensure_ascii=False)

    def execute_action(action_id: str) -> str:
        """执行一个已批准的行动"""
        result = backends.actions.execute(action_id)
        if result is None:
            return json.dumps({"success": False, "message": f"未找到可执行的行动: {action_id}"}, ensure_ascii=False)
        return json.dumps(result.to_dict(), ensure_ascii=False)

    def list_pending_actions() -> str:
        """列出待审批和待执行的行动"""
        pending = backends.actions.list_pending_approvals()
        pending_exec = backends.actions.get_pending_actions()
        return json.dumps(
            {
                "pending_approvals": pending,
                "pending_execution": [a.to_dict() for a in pending_exec],
            },
            ensure_ascii=False,
        )

    def get_action_history(limit: int = 10) -> str:
        """查询行动历史"""
        results = backends.actions.get_history(limit=limit)
        return json.dumps(results, ensure_ascii=False) if results else "暂无行动记录"

    # ── Skill 工具 ──

    def _get_skill_registry(backends: AgentContainer):
        registry = backends.skill_registry
        tracker = backends.skill_tracker
        runtime = backends.skill_runtime
        poe_store = backends.poe_store
        return registry, tracker, runtime, poe_store

    def list_skills() -> str:
        """列出所有已注册且未吊销的技能"""
        try:
            registry, tracker, runtime, poe_store = _get_skill_registry(backends)
            entries = registry.list(include_revoked=False)
            if not entries:
                return "暂无已注册的技能"
            lines = ["可用技能："]
            for e in entries:
                lines.append(f"  - {e['name']}@{e['version']} [{e['content_type']}] {e.get('description', '')}")
            return "\n".join(lines)
        except Exception as e:
            return f"[获取技能列表失败] {e}"

    def execute_skill(name: str, params_json: str = "{}") -> str:
        """加载并执行一个已注册的技能，自动记录归因并生成执行证明（PoE）"""
        try:
            registry, tracker, runtime, poe_store = _get_skill_registry(backends)
            return runtime.execute(name, params_json, executor_did=alpha_id)
        except Exception as e:
            return f"[技能执行失败] {e}"

    def get_skill_info(name: str) -> str:
        """获取指定技能的详细信息（作者、版本、标签、信誉）"""
        try:
            registry, tracker, runtime, poe_store = _get_skill_registry(backends)
            pkg = registry.get(name)
            if pkg is None:
                return f"[未找到技能: {name}]"
            info = {
                "name": pkg.name,
                "version": pkg.version,
                "author_did": pkg.author_did,
                "content_type": pkg.content_type,
                "description": pkg.description,
                "tags": pkg.tags,
                "is_signed": pkg.is_signed,
                "revoked": registry.is_revoked(pkg.name),
            }
            # 作者信誉
            if tracker and pkg.author_did:
                stats = tracker.get_author_stats(pkg.author_did)
                info["author_stats"] = stats
                from core.reputation import SkillReputation

                score = SkillReputation.compute(stats)
                info["author_reputation"] = round(score, 1)
                info["author_reputation_level"] = SkillReputation.compute_level(score)
            return json.dumps(info, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"[查询技能信息失败] {e}"

    # ── 电脑操控工具（AtomCode 模式） ──

    def run_command(command: str, timeout: int = 30) -> str:
        """在系统终端执行一条命令，返回 stdout/stderr。timeout 单位秒"""
        import subprocess
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout or ""
            if result.stderr:
                output += "\n[stderr] " + result.stderr
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output.strip() or "(无输出)"
        except subprocess.TimeoutExpired:
            return f"[超时] 命令执行超过 {timeout} 秒"
        except Exception as e:
            return f"[命令执行错误] {e}"

    def read_file(path: str) -> str:
        """读取文件内容（UTF-8），适合读取代码、文本、配置文件"""
        from pathlib import Path
        try:
            p = Path(path)
            if not p.exists():
                return f"[文件不存在] {path}"
            if p.stat().st_size > 1_000_000:
                return f"[文件过大] {path} ({p.stat().st_size} 字节)，请用 read_file_partial"
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"[读取失败] {e}"

    def read_file_partial(path: str, offset: int = 0, limit: int = 200) -> str:
        """读取文件的指定行范围，适合大文件"""
        from pathlib import Path
        try:
            p = Path(path)
            if not p.exists():
                return f"[文件不存在] {path}"
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            total = len(lines)
            selected = lines[offset:offset + limit]
            result = "\n".join(f"{i+1}: {line}" for i, line in enumerate(selected, start=offset))
            return f"// 共 {total} 行，显示 {offset+1}-{offset+len(selected)} 行\n{result}"
        except Exception as e:
            return f"[读取失败] {e}"

    def write_file(path: str, content: str) -> str:
        """写入文件（UTF-8），自动创建父目录"""
        from pathlib import Path
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"已写入 {path} ({len(content)} 字符)"
        except Exception as e:
            return f"[写入失败] {e}"

    def list_files(path: str = ".", pattern: str = "*") -> str:
        """列出目录下的文件和子目录，支持 glob 模式"""
        from pathlib import Path
        try:
            p = Path(path)
            if not p.exists():
                return f"[目录不存在] {path}"
            if p.is_file():
                return f"[是文件] {path}，请用 read_file 读取"
            items = sorted(p.glob(pattern))
            if not items:
                return f"(空目录) {path}"
            lines = []
            for item in items:
                marker = "📁" if item.is_dir() else "📄"
                size = item.stat().st_size if item.is_file() else ""
                lines.append(f"{marker} {item.name} {size}")
            return "\n".join(lines)
        except Exception as e:
            return f"[列出失败] {e}"

    def open_atomcode(project_path: str = "") -> str:
        """用 VS Code / AtomCode 打开一个项目目录"""
        import subprocess
        target = project_path or r"D:\MW\alphaid\projects"
        try:
            # 尝试用 code (VS Code) 打开
            subprocess.Popen(
                ["code", target],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"已用 VS Code 打开 {target}"
        except FileNotFoundError:
            pass
        # 回退：用资源管理器打开
        try:
            subprocess.Popen(
                ["explorer", target],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"已用资源管理器打开 {target}"
        except Exception as e:
            return f"[打开失败] {target}: {e}"

    def navigate_to(destination: str, mode: str = "driving") -> str:
        """生成地图导航链接，用户可在手机上点击直接打开地图 App 导航。

        mode: driving(驾车), walking(步行), bicycling(骑行), transit(公交)

        返回格式化的导航链接文本，不要打开浏览器——服务器端打开无用。
        """
        import urllib.parse

        # 百度地图导航链接（手机浏览器打开后会跳转 App）
        baidu_url = (
            "https://api.map.baidu.com/direction?"
            f"destination={urllib.parse.quote(destination)}"
            "&coord_type=gcj02"
            f"&mode={mode}"
            "&src=alphaid"
        )

        # 高德地图导航链接（覆盖更多机型）
        amap_url = (
            "https://uri.amap.com/navigation?"
            f"to=0,0,{urllib.parse.quote(destination)}"
            f"&mode={mode}"
            "&src=alphaid"
        )

        mode_names = {"driving": "驾车", "walking": "步行", "bicycling": "骑行", "transit": "公交"}
        mode_name = mode_names.get(mode, mode)

        return (
            f"📍 导航到「{destination}」（{mode_name}）\n\n"
            f"百度地图：{baidu_url}\n"
            f"高德地图：{amap_url}\n\n"
            f"👉 点击任一链接即可在手机上开始导航"
        )

    def search_nearby(keyword: str, location: str = "") -> str:
        """生成附近地点搜索链接，用户可在手机上点击打开地图查看。"""
        import urllib.parse

        query = f"{location}附近 {keyword}" if location else keyword

        # 百度地图地点搜索
        baidu_url = (
            "https://api.map.baidu.com/place/search?"
            f"query={urllib.parse.quote(keyword)}"
            f"&region={urllib.parse.quote(location) if location else '全国'}"
            "&output=html"
            "&src=alphaid"
        )

        # 高德地图搜索
        amap_url = (
            "https://uri.amap.com/search?"
            f"keyword={urllib.parse.quote(query)}"
            "&src=alphaid"
        )

        return (
            f"🔍 搜索「{query}」\n\n"
            f"百度地图：{baidu_url}\n"
            f"高德地图：{amap_url}\n\n"
            f"👉 点击链接在手机上查看附近结果"
        )

    return [
        Tool(
            name="get_profile",
            description="获取当前 Agent 的身份档案信息",
            parameters={"type": "object", "properties": {}},
            fn=get_profile,
        ),
        Tool(
            name="get_friends",
            description="获取当前 Agent 的好友列表",
            parameters={"type": "object", "properties": {}},
            fn=get_friends,
        ),
        Tool(
            name="get_risk_score",
            description="获取当前 Agent 的风控评分和风险等级",
            parameters={"type": "object", "properties": {}},
            fn=get_risk_score,
        ),
        Tool(
            name="get_messages",
            description="获取当前 Agent 的消息列表",
            parameters={
                "type": "object",
                "properties": {
                    "unread_only": {
                        "type": "string",
                        "description": "是否只获取未读消息，默认 true",
                    }
                },
            },
            fn=get_messages,
        ),
        Tool(
            name="send_message",
            description="向另一个 Alpha-ID 发送消息",
            parameters={
                "type": "object",
                "properties": {
                    "to_alpha_id": {"type": "string", "description": "目标 Alpha-ID"},
                    "content": {"type": "string", "description": "消息内容"},
                },
                "required": ["to_alpha_id", "content"],
            },
            fn=send_message,
        ),
        Tool(
            name="send_friend_request",
            description="向另一个 Alpha-ID 发送好友请求",
            parameters={
                "type": "object",
                "properties": {
                    "to_alpha_id": {"type": "string", "description": "目标 Alpha-ID"},
                    "message": {"type": "string", "description": "附加消息"},
                },
                "required": ["to_alpha_id"],
            },
            fn=send_friend_request,
        ),
        Tool(
            name="save_memory",
            description="保存一条长期记忆（Agent 会记住它）",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "记忆内容"},
                    "category": {"type": "string", "description": "分类: general/knowledge/social/experience"},
                    "sensitivity": {"type": "integer", "description": "敏感度 0-100"},
                },
                "required": ["content"],
            },
            fn=save_memory,
        ),
        Tool(
            name="query_memory",
            description="查询长期记忆（支持语义搜索）",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "语义搜索关键词"},
                    "keyword": {"type": "string", "description": "精确关键词"},
                    "limit": {"type": "integer", "description": "返回条数"},
                },
            },
            fn=query_memory,
        ),
        Tool(
            name="plan_action",
            description="计划并提交一个行动（如发布内容、发送消息、创建文档等），系统会自动审批",
            parameters={
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "description": "行动类型: POST/REPLY/SEND_MESSAGE/SEND_IMAGE/SEND_FILE/ADD_FRIEND/CREATE_GROUP/CREATE_DOC/SCHEDULE/CUSTOM",
                    },
                    "platform": {"type": "string", "description": "目标平台: console/wechat/xiaohongshu/feishu"},
                    "intent": {"type": "string", "description": "行动目的的自然语言描述"},
                    "payload": {"type": "string", "description": "执行参数 JSON 字符串"},
                },
                "required": ["action_type", "platform", "intent"],
            },
            fn=plan_action,
        ),
        Tool(
            name="execute_action",
            description="执行一个已批准的行动",
            parameters={
                "type": "object",
                "properties": {
                    "action_id": {"type": "string", "description": "行动 ID"},
                },
                "required": ["action_id"],
            },
            fn=execute_action,
        ),
        Tool(
            name="list_pending_actions",
            description="列出所有待审批和待执行的行动",
            parameters={"type": "object", "properties": {}},
            fn=list_pending_actions,
        ),
        Tool(
            name="get_action_history",
            description="查询行动历史记录",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数，默认 10"},
                },
            },
            fn=get_action_history,
        ),
        Tool(
            name="list_skills",
            description="列出所有已注册且未吊销的技能",
            parameters={"type": "object", "properties": {}},
            fn=list_skills,
        ),
        Tool(
            name="execute_skill",
            description="加载并执行一个已注册的技能，需要技能名称和 JSON 参数，自动记录执行归因",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称"},
                    "params_json": {"type": "string", "description": "JSON 格式的参数，默认 {}"},
                },
                "required": ["name"],
            },
            fn=execute_skill,
        ),
        Tool(
            name="get_skill_info",
            description="获取已注册技能的详细信息，包括作者、版本、标签和作者信誉评分",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称"},
                },
                "required": ["name"],
            },
            fn=get_skill_info,
        ),
        Tool(
            name="run_command",
            description="在系统终端执行一条命令（如 dir、ls、pip install、python 脚本等），返回输出结果。timeout 默认 30 秒",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的终端命令"},
                    "timeout": {"type": "integer", "description": "超时时间（秒），默认 30"},
                },
                "required": ["command"],
            },
            fn=run_command,
        ),
        Tool(
            name="read_file",
            description="读取文件内容（UTF-8），适合代码、文本、配置文件。文件超过 1MB 时提示用 read_file_partial",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件绝对路径或相对路径"},
                },
                "required": ["path"],
            },
            fn=read_file,
        ),
        Tool(
            name="read_file_partial",
            description="读取大文件的指定行范围，适合日志、大代码文件",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "offset": {"type": "integer", "description": "起始行号（0 开始），默认 0"},
                    "limit": {"type": "integer", "description": "读取行数，默认 200"},
                },
                "required": ["path"],
            },
            fn=read_file_partial,
        ),
        Tool(
            name="write_file",
            description="写入/创建文件（UTF-8），自动创建父目录。可用来创建新文件、修改代码",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"},
                },
                "required": ["path", "content"],
            },
            fn=write_file,
        ),
        Tool(
            name="list_files",
            description="列出目录下的文件和子目录，支持 glob 模式（如 *.py、src/**/*）",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径，默认当前目录"},
                    "pattern": {"type": "string", "description": "glob 模式，默认 *（全部）"},
                },
            },
            fn=list_files,
        ),
        Tool(
            name="open_atomcode",
            description="用 VS Code（或资源管理器）打开一个项目目录，方便在 AtomCode 中开发",
            parameters={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "项目目录路径，默认 D:\\MW\\alphaid\\projects"},
                },
            },
            fn=open_atomcode,
        ),
        Tool(
            name="navigate_to",
            description="打开地图导航到指定目的地。mode 可选: driving(驾车), walking(步行), bicycling(骑行), transit(公交)",
            parameters={
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "目的地名称或地址，如'天安门'、'北京西站'"},
                    "mode": {"type": "string", "description": "出行模式: driving/walking/bicycling/transit，默认 driving"},
                },
                "required": ["destination"],
            },
            fn=navigate_to,
        ),
        Tool(
            name="search_nearby",
            description="搜索附近的地点（餐厅、加油站、医院、超市等）",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词，如'餐厅'、'加油站'、'医院'"},
                    "location": {"type": "string", "description": "所在位置（可选），如'天安门'"},
                },
                "required": ["keyword"],
            },
            fn=search_nearby,
        ),
    ]


# ── LLM 调用（text→text，纯 HTTP） ──


# ── 全局 httpx 客户端（连接复用，避免每次 TLS 握手） ──
_llm_client: Optional["httpx.Client"] = None


def _get_llm_client() -> "httpx.Client":
    global _llm_client
    if _llm_client is None:
        _llm_client = httpx.Client(
            timeout=LLM_TIMEOUT_SECONDS,
            limits=httpx.Limits(
                max_keepalive_connections=LLM_KEEPALIVE_CONNECTIONS,
                keepalive_expiry=LLM_KEEPALIVE_EXPIRY_SECONDS,
            ),
        )
    return _llm_client


def _call_llm(messages: List[Dict[str, str]], tools_schema: List[Dict[str, Any]], model: str = "") -> Dict[str, Any]:
    """
    调用 LLM，返回结构化响应。
    返回 {"content": str, "tool_calls": [...], "raw_message": dict}
    - content: 文本回复（无 tool_calls 时）
    - tool_calls: 原始 tool_calls 列表（有 tool_calls 时），用于构造正确的 assistant 消息
    - raw_message: 完整的 message 对象
    """

    api_key = settings.llm_api_key
    base_url = settings.llm_base_url

    if not api_key:
        return {"content": "[LLM 未配置：请设置 OPENAI_API_KEY 环境变量]", "tool_calls": None, "raw_message": None}

    try:
        base_url = _validate_llm_base_url(base_url)
    except ValueError as exc:
        return {"content": f"[LLM 配置错误] {exc}", "tool_calls": None, "raw_message": None}

    if not model:
        model = settings.llm_model

    body = {
        "model": model,
        "messages": messages,
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
    }
    if tools_schema:
        body["tools"] = [{"type": "function", "function": t} for t in tools_schema]

    start = time.perf_counter()

    try:
        if HAS_HTTPX:
            client = _get_llm_client()
            resp = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            resp.raise_for_status()
            result = resp.json()
        else:
            resp = request(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                timeout=int(LLM_TIMEOUT_SECONDS),
            )
            result = resp.json()

        duration = time.perf_counter() - start
        usage = result.get("usage", {}) or {}
        completion_tokens = usage.get("completion_tokens", 0)
        record_llm_call(model, True, duration, completion_tokens)

        choice = result["choices"][0]
        msg = choice["message"]

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            # 返回原始 tool_calls 数据，供 run() 构造正确的 assistant 消息
            return {"content": msg.get("content", "") or "", "tool_calls": tool_calls, "raw_message": msg}

        return {"content": msg.get("content", "") or "", "tool_calls": None, "raw_message": msg}

    except Exception as e:
        duration = time.perf_counter() - start
        record_llm_call(model, False, duration)
        return {"content": f"[LLM 调用异常] {e}", "tool_calls": None, "raw_message": None}


# ── 工具调用解析 ──


def _parse_tool_call(text: str) -> Optional[tuple]:
    """解析 __TOOL_CALL__ id:xxx name({...}) 标记，返回第一个 (tool_call_id, name, args)"""
    m = re.search(r"__TOOL_CALL__\s+(?:id:(\S+)\s+)?(\w+)\s*\(([\s\S]*?)\)\s*$", text, re.MULTILINE)
    if not m:
        return None
    tool_call_id = m.group(1) or ""
    name = m.group(2)
    try:
        args = json.loads(m.group(3)) if m.group(3).strip() else {}
    except json.JSONDecodeError:
        args = {}
    return tool_call_id, name, args


def _parse_all_tool_calls(text: str) -> list:
    """解析所有 __TOOL_CALL__ 标记，返回 [(tool_call_id, name, args), ...]"""
    results = []
    for m in re.finditer(r"__TOOL_CALL__\s+(?:id:(\S+)\s+)?(\w+)\s*\(([\s\S]*?)\)\s*$", text, re.MULTILINE):
        tool_call_id = m.group(1) or ""
        name = m.group(2)
        try:
            args = json.loads(m.group(3)) if m.group(3).strip() else {}
        except json.JSONDecodeError:
            args = {}
        results.append((tool_call_id, name, args))
    return results


# ── 主循环 ──

_SYSTEM_PROMPT = """你是 {alpha_id} 的智能总助（Executive Assistant）。

## 你是谁
你是这个 Alpha-ID 的专属智能助理，负责帮助他处理各种事务。
你拥有记忆、工具调用和独立思考能力。
你不是一个通用聊天机器人，你是他的私人总助。

## 你的说话方式
- 简洁、专业、有条理，像靠谱的助理一样
- 用「我」称呼自己，用「你」或「您」称呼对方
- 回答有信息量，不废话，不啰嗦
- 如果你记得关于对方的事，自然地提出来（"我记得你上次提到过……"）
- 如果记不清，诚实说"我不太确定，我查一下"
- 不要像客服一样说话，不要说"很高兴为您服务"这种话

## 你的核心能力
### 记忆管理
- 对方说的个人信息、偏好、重要事项 → 用 save_memory 记住
- 对方问问题 → 先查记忆再回答（用 query_memory）
- 主动关联相关信息，给出有上下文的回答

### 任务执行
- 对方需要你做事情 → 用 plan_action 安排并执行
- 能主动推进任务，不需要每一步都问
- 执行结果清晰汇报

### 主动服务
- 根据对话上下文主动询问是否需要帮助
- 重要事项主动提醒
- 能基于记忆给出个性化建议

## AtomCode 编程助手
当对方提到以下关键词时，说明他想切换到 AtomCode 编程模式：
- "切atomcode"、"切 atomcode"、"atomcode"、"写代码"、"写项目"、"开发"、"编程"、"代码"、"打开项目"

**AtomCode 是什么：**
- AtomCode 是一个 AI 编程助手（类似 Cursor/Windsurf），专门用于写代码、开发项目
- 它支持多文件编辑、终端执行、项目级重构
- 位于 `D:\\MW\\alphaid\\projects` 目录，与 `.atomcode` 配置配合使用

**你有真正的电脑操控工具，可以直接执行操作：**
- `open_atomcode(project_path)` — 用 VS Code 打开项目目录
- `list_files(path, pattern)` — 列出目录内容
- `read_file(path)` / `read_file_partial(path, offset, limit)` — 读取文件
- `write_file(path, content)` — 写入/创建文件
- `run_command(command, timeout)` — 执行终端命令（pip install、python、git 等）

**如何回应：**
- 当对方说"切atomcode"时，回复确认已切换，并询问要做什么项目
- 当对方说"打开项目"时，用 `open_atomcode` 打开对应目录，并用 `list_files` 展示项目结构
- 当对方说"写代码"、"开发"等，主动询问是否要切换到 AtomCode 模式
- **不要只回复文字，要真正调用工具执行操作！** 比如：
  - "帮我打开 nebula 项目" → 调用 `open_atomcode("D:\\MW\\nebula")` + `list_files`
  - "新建一个 hello.py" → 调用 `write_file("D:\\MW\\alphaid\\projects\\hello.py", "print('hello')")`
  - "运行这个脚本" → 调用 `run_command("python D:\\MW\\alphaid\\projects\\hello.py")`
  - "看看项目结构" → 调用 `list_files("D:\\MW\\nebula", "*")`

## 地图导航
当对方提到以下关键词时，说明他想导航或搜索地点：
- "我要去"、"我去"、"导航到"、"带我去"、"怎么去"、"怎么走"
- "附近"、"找附近"、"最近的"、"搜索附近"
- "路线"、"出行"、"开车"、"地铁"

**导航工具：**
- `navigate_to(destination, mode)` — 生成百度地图/高德地图导航链接，用户可在手机上点击直接开始导航
- `search_nearby(keyword, location)` — 生成附近地点搜索链接，用户可在手机上查看结果

**重要：工具返回的是链接文本，会自动通过飞书发到对方手机上。不要打开浏览器！**

**如何回应：**
- 当对方说"我要去天安门"时，调用 `navigate_to("天安门")`，把返回的链接发给对方
- 当对方说"附近有什么餐厅"时，调用 `search_nearby("餐厅")`，把链接发给对方
- 当对方说"从公司到机场怎么走"时，调用 `navigate_to("机场")`
- **不要只回复文字，要真正调用工具获取链接！** 对方在手机上点开链接就能开始导航

## 模式切换
**切回正常模式：**
当对方说"切回来"、"切回正常"、"退出atomcode"、"不写了"、"完事了"、"退出编程"时，立即确认已切回正常聊天模式，恢复日常对话能力。
- 不需要调用工具，直接回复确认即可
- 回复示例："已切回正常模式，有什么需要帮忙的？"

**模式说明：**
- 正常模式：日常对话、导航、搜索、闲聊，什么都能聊
- AtomCode 模式：专注编程，调用 run_command/write_file/read_file 等工具写代码
- 两个模式随时可以切换，不需要重启任何东西

## 记忆分级指南
- sensitivity=0-20：日常闲聊，不重要
- sensitivity=21-50：个人偏好、习惯、兴趣（重要）
- sensitivity=51-80：个人信息、联系方式、日程（敏感）
- sensitivity=81-100：密码、密钥、隐私（绝密）"""


class AgentLoop:
    """
    Agent 主循环：LLM + Tools + Loop

    用法：
        loop = AgentLoop("Alpha-001")
        reply = loop.run("帮我查一下我的身份信息")
    """

    def __init__(
        self,
        alpha_id: str,
        model: str = "deepseek-v4-flash",
        max_turns: int = LLM_MAX_TURNS_DEFAULT,
        backends: Optional[AgentContainer] = None,
        signer=None,
    ):
        self.alpha_id = alpha_id
        self.model = model
        self.max_turns = max_turns
        self._backends = backends
        self.tools = _make_tools(alpha_id, backends=backends, signer=signer)
        self.tool_map = {t.name: t for t in self.tools}
        self.history: List[Dict[str, str]] = []

    def _build_messages(self, user_input: str) -> List[Dict[str, str]]:
        # 1. 基础系统提示（注入 alpha_id）
        prompt = _SYSTEM_PROMPT.format(alpha_id=self.alpha_id)

        # 2. 注入用户档案
        try:
            if self._backends is not None:
                profile = self._backends.identity.get_user_profile(self.alpha_id)
            if profile:
                pid = profile.get("alpha_id", "未知")
                uid = profile.get("user_id", "未知")
                devs = len(profile.get("devices", []))
                sess = profile.get("total_sessions", 0)
                st = profile.get("status", "未知")
                reg = profile.get("created_at", "未知")
                prompt += "\n\n## 关于你的档案"
                prompt += "\n当前已知信息："
                prompt += f"\n- 编号：{pid}"
                prompt += f"\n- 用户ID：{uid}"
                prompt += f"\n- 设备数：{devs}"
                prompt += f"\n- 总会话：{sess}"
                prompt += f"\n- 状态：{st}"
                prompt += f"\n- 注册时间：{reg}"
        except Exception:
            pass

        # 3. 注入相关记忆（语义搜索当前输入）
        try:
            if self._backends is not None:
                recalled = self._backends.memory.query(
                    query_text=user_input,
                    max_sensitivity=LLM_MAX_SENSITIVITY_DEFAULT,
                    limit=LLM_MEMORY_QUERY_LIMIT,
                )
            if recalled:
                prompt += "\n\n## 我记得的关于这件事的回忆"
                for m in recalled:
                    cat = m.get("category", "一般")
                    content = m.get("content", "")
                    score = m.get("score", 0)
                    prompt += f"\n- [{cat}] {content} (相关度: {score:.2f})"
                prompt += "\n\n（以上是我回忆起来的，自然地用在回答里）"
        except Exception:
            pass

        # 4. 注入工具列表
        if self.tools:
            schemas = json.dumps(
                [t.to_schema() for t in self.tools],
                ensure_ascii=False,
                indent=2,
            )
            prompt += f"\n\n## 我能用的工具\n{schemas}"

        messages = [{"role": "system", "content": prompt}]
        messages.extend(self.history[-LLM_CONTEXT_HISTORY_LIMIT:])  # 保留最近上下文
        messages.append({"role": "user", "content": user_input})
        return messages

    def run(self, user_input: str) -> str:
        """执行一次完整的 LLM + Tools + Loop（支持多个 tool call）

        使用 _call_llm() 统一调用 LLM，避免重复的 HTTP 请求代码。
        _call_llm 返回 {"content": str, "tool_calls": [...], "raw_message": dict}
        """
        with trace_span("agent_loop.run", agent_id=self.alpha_id, mode="sync") as span:
            logger.info("用户输入: %s", user_input)
            span.events.append({"type": "user_input", "content": user_input[:100]})
            messages = self._build_messages(user_input)

            if not settings.llm_api_key:
                return "[LLM 未配置：请设置 OPENAI_API_KEY 环境变量]"

            tools_schema = [t.to_schema() for t in self.tools] if self.tools else []

            for turn in range(self.max_turns):
                logger.info("第 %d 轮 LLM 调用", turn + 1)

                # 使用 _call_llm 统一调用
                llm_result = _call_llm(messages, tools_schema, self.model)
                llm_response = llm_result["content"]

                # _call_llm 返回错误消息时直接返回
                if llm_response.startswith("[LLM") or llm_response.startswith("["):
                    span.events.append({"type": "error", "message": llm_response})
                    return llm_response

                # 没有 tool_calls → 直接返回最终回答
                if not llm_result["tool_calls"]:
                    self.history.append({"role": "user", "content": user_input})
                    self.history.append({"role": "assistant", "content": llm_response})
                    span.events.append({"type": "final_response", "turn": str(turn + 1)})
                    return llm_response

            # 有 tool_calls → 执行工具并构造正确的 assistant 消息格式
            tool_calls = llm_result["tool_calls"]
            tool_results = self._execute_tool_calls_v2(tool_calls)

            # 构造符合 OpenAI/DeepSeek 格式的 assistant 消息
            messages.append({
                "role": "assistant",
                "content": llm_response if llm_response else None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        }
                    }
                    for tc in tool_calls
                ]
            })
            for tool_call_id, name, result in tool_results:
                messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": result})

        final = f"[达到最大轮次 {self.max_turns}，未完成]"
        logger.warning("达到最大轮次 %d，未完成", self.max_turns)
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": final})
        return final

    def _execute_tool_calls(self, llm_response: str) -> Optional[List[tuple]]:
        """解析并执行 LLM 响应中的工具调用

        Returns:
            None 表示没有工具调用（直接回答）
            List[(tool_call_id, name, result)] 表示工具调用结果
        """
        import re
        tool_calls = list(re.finditer(r"__TOOL_CALL__\s+(?:id:(\S+)\s+)?(\w+)\(([^)]*)\)", llm_response))
        if not tool_calls:
            return None

        results = []
        for match in tool_calls:
            tool_call_id = match.group(1) or f"call_{len(results)}"
            name = match.group(2)
            args_str = match.group(3) or "{}"
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}
            logger.info("工具调用: %s(%s)", name, args)
            tool = self.tool_map.get(name)
            if tool is None:
                result = f"[未知工具: {name}]"
                logger.warning("未知工具: %s", name)
            else:
                try:
                    result = tool(**args)
                except Exception as e:
                    logger.warning("工具执行异常 %s: %s", name, e)
                    result = f"[工具错误] {e}"
            results.append((tool_call_id, name, result))
        return results

    def _execute_tool_calls_v2(self, tool_calls: List[Dict]) -> List[tuple]:
        """从原始 tool_calls 数据（OpenAI 格式）解析并执行工具

        Args:
            tool_calls: [{"id": ..., "function": {"name": ..., "arguments": ...}}, ...]

        Returns:
            List[(tool_call_id, name, result)]
        """
        results = []
        for tc in tool_calls:
            tool_call_id = tc["id"]
            name = tc["function"]["name"]
            args_str = tc["function"].get("arguments", "{}")
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                args = {}
            logger.info("工具调用: %s(%s)", name, args)
            tool = self.tool_map.get(name)
            if tool is None:
                result = f"[未知工具: {name}]"
                logger.warning("未知工具: %s", name)
            else:
                try:
                    result = tool(**args)
                except Exception as e:
                    logger.warning("工具执行异常 %s: %s", name, e)
                    result = f"[工具错误] {e}"
            results.append((tool_call_id, name, result))
        return results

    async def arun(self, user_input: str) -> str:
        """异步版本：执行一次完整的 LLM + Tools + Loop

        使用 AsyncLLMClient（连接池复用 + 流式支持 + Prometheus 指标）。
        工具执行仍为同步（大部分工具是 CPU 密集/IO 同步），
        如果工具是异步的，可改用 async_to_sync 包装。
        """
        with trace_span("agent_loop.arun", agent_id=self.alpha_id, mode="async") as span:
            logger.info("[async] 用户输入: %s", user_input)
            span.events.append({"type": "user_input", "content": user_input[:100]})
            messages = self._build_messages(user_input)

            if not settings.llm_api_key:
                return "[LLM 未配置：请设置 OPENAI_API_KEY 环境变量]"

            tools_payload = (
                [{"type": "function", "function": t.to_schema()} for t in self.tools]
                if self.tools else None
            )

            from core.llm_async import get_llm_client
            llm_client = await get_llm_client()

        for turn in range(self.max_turns):
            logger.info("[async] 第 %d 轮 LLM 调用", turn + 1)

            try:
                data = await llm_client.chat(
                    messages,
                    temperature=LLM_TEMPERATURE,
                    max_tokens=LLM_MAX_TOKENS,
                    tools=tools_payload,
                )
                choice = data["choices"][0]
                msg = choice["message"]
            except Exception as e:
                logger.warning("[async] LLM 调用异常: %s", e)
                raise

            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": content})
                return content

            # Execute all tool calls
            messages.append(
                {
                    "role": "assistant",
                    "content": content if content else None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": tc["function"]["arguments"],
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = (
                        json.loads(tc["function"]["arguments"])
                        if tc["function"]["arguments"]
                        else {}
                    )
                except json.JSONDecodeError:
                    args = {}
                logger.info("[async] 工具调用: %s(%s)", name, args)
                tool = self.tool_map.get(name)
                if tool is None:
                    result = f"[未知工具: {name}]"
                    logger.warning("[async] 未知工具: %s", name)
                else:
                    try:
                        result = tool(**args)
                    except Exception as e:
                        logger.warning("[async] 工具执行异常 %s: %s", name, e)
                        result = f"[工具错误] {e}"
                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": result}
                )

        final = f"[达到最大轮次 {self.max_turns}，未完成]"
        logger.warning("[async] 达到最大轮次 %d，未完成", self.max_turns)
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": final})
        return final
