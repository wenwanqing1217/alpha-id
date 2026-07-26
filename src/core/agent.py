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
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from core.interfaces import AgentContainer

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    httpx = None
    HAS_HTTPX = False

logger = logging.getLogger(__name__)


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

    def save_memory(content: str, category: str = "general", sensitivity: str = "0") -> str:
        """保存一条长期记忆"""
        mem = backends.memory.save(content, category=category, sensitivity=int(sensitivity))
        return json.dumps(mem, ensure_ascii=False)

    def query_memory(query: str = "", keyword: str = "", limit: str = "5") -> str:
        """查询长期记忆（支持语义搜索和关键词搜索）"""
        results = backends.memory.query(query_text=query or None, keyword=keyword or None, limit=int(limit))
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

    def get_action_history(limit: str = "10") -> str:
        """查询行动历史"""
        results = backends.actions.get_history(limit=int(limit))
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
                    "sensitivity": {"type": "string", "description": "敏感度 0-100"},
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
                    "limit": {"type": "string", "description": "返回条数"},
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
                    "limit": {"type": "string", "description": "返回条数，默认 10"},
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
    ]


# ── LLM 调用（text→text，纯 HTTP） ──


# ── 全局 httpx 客户端（连接复用，避免每次 TLS 握手） ──
_llm_client: Optional["httpx.Client"] = None


def _get_llm_client() -> "httpx.Client":
    global _llm_client
    if _llm_client is None:
        _llm_client = httpx.Client(
            timeout=60.0, limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=30.0)
        )
    return _llm_client


def _call_llm(messages: List[Dict[str, str]], tools_schema: List[Dict[str, Any]], model: str = "") -> str:
    """
    调用 LLM，返回文本响应。
    优先使用 httpx（连接复用），未安装时回退到 urllib。
    """

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"

    try:
        base_url = _validate_llm_base_url(base_url)
    except ValueError as exc:
        return f"[LLM 配置错误] {exc}"

    if not api_key:
        return "[LLM 未配置：请设置 OPENAI_API_KEY 环境变量]"

    if not model:
        model = os.getenv("LLM_MODEL", "deepseek-v4-flash")

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
    }
    if tools_schema:
        body["tools"] = [{"type": "function", "function": t} for t in tools_schema]

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
            import urllib.error
            import urllib.request

            req = urllib.request.Request(
                f"{base_url.rstrip('/')}/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))

        choice = result["choices"][0]
        msg = choice["message"]

        if msg.get("tool_calls"):
            lines = []
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                lines.append(f"__TOOL_CALL__ id:{tc['id']} {fn['name']}({fn['arguments']})")
            return "\n".join(lines)

        return msg.get("content", "") or ""

    except Exception as e:
        return f"[LLM 调用异常] {e}"


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
        max_turns: int = 3,
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
                    max_sensitivity=70,
                    limit=5,
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
        messages.extend(self.history[-20:])  # 保留最近上下文
        messages.append({"role": "user", "content": user_input})
        return messages

    def run(self, user_input: str) -> str:
        """执行一次完整的 LLM + Tools + Loop（支持多个 tool call）"""
        logger.info(f"用户输入: {user_input}")
        messages = self._build_messages(user_input)
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"

        if not api_key:
            return "[LLM 未配置：请设置 OPENAI_API_KEY 环境变量]"

        tools_payload = [{"type": "function", "function": t.to_schema()} for t in self.tools] if self.tools else None

        for turn in range(self.max_turns):
            logger.info(f"第 {turn + 1} 轮 LLM 调用")
            body = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 2048,
            }
            if tools_payload:
                body["tools"] = tools_payload

            try:
                import httpx
                resp = httpx.post(
                    base_url.rstrip("/") + "/chat/completions",
                    json=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + api_key,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                choice = data["choices"][0]
                msg = choice["message"]
            except Exception as e:
                logger.warning(f"LLM 调用异常: {e}")
                raise

            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": content})
                return content

            # Execute all tool calls
            messages.append({"role": "assistant", "content": content if content else None, "tool_calls": [
                {"id": tc["id"], "type": "function", "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}}
                for tc in tool_calls
            ]})

            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                logger.info(f"工具调用: {name}({args})")
                tool = self.tool_map.get(name)
                if tool is None:
                    result = f"[未知工具: {name}]"
                    logger.warning(f"未知工具: {name}")
                else:
                    try:
                        result = tool(**args)
                    except Exception as e:
                        logger.warning(f"工具执行异常 {name}: {e}")
                        result = f"[工具错误] {e}"
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        final = f"[达到最大轮次 {self.max_turns}，未完成]"
        logger.warning(f"达到最大轮次 {self.max_turns}，未完成")
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": final})
        return final
