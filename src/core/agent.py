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

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    httpx = None
    HAS_HTTPX = False

logger = logging.getLogger(__name__)

from alpha_id.container import Container  # noqa: E402
from alpha_id.skill_signer import SkillRegistry, SkillRuntime  # noqa: E402

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


# ── 内置工具 ──


def _make_tools(alpha_id: str, signer=None) -> List[Tool]:
    """构造 Agent 可用工具列表

    Args:
        alpha_id: Agent 的 Alpha-ID
        signer: 可选的 AIDSigner 实例，用于签名执行证明（PoE）
    """
    container = Container.instance()
    from core.action_engine.models import Action, ActionType

    def get_profile() -> str:
        profile = container.identity.get_user_profile(alpha_id)
        return json.dumps(profile, ensure_ascii=False, default=str) if profile else "未找到身份信息"

    def get_friends() -> str:
        friends = container.social.get_friends(alpha_id)
        return json.dumps(friends, ensure_ascii=False) if friends else "暂无好友"

    def get_risk_score() -> str:
        engine = container.risk
        device_score = engine.calculate_device_score(None, None)
        behavior_score = engine.calculate_behavior_score({})
        voice_score = engine.calculate_voice_score(None)
        total = engine.calculate_total_risk(device_score, behavior_score, voice_score)
        level = engine.determine_risk_level(total)
        return json.dumps({"risk_score": round(total, 2), "risk_level": level}, ensure_ascii=False)

    def get_messages(unread_only: str = "true") -> str:
        msgs = container.social.get_messages(alpha_id, unread_only=(unread_only.lower() == "true"))
        return json.dumps(msgs, ensure_ascii=False, default=str) if msgs else "暂无消息"

    def send_message(to_alpha_id: str, content: str) -> str:
        result = container.social.send_message(alpha_id, to_alpha_id, content)
        return json.dumps(result, ensure_ascii=False)

    def send_friend_request(to_alpha_id: str, message: str = "") -> str:
        """向另一个 Alpha-ID 发送好友请求"""
        result = container.social.send_friend_request(alpha_id, to_alpha_id, message)
        return json.dumps(result, ensure_ascii=False)

    def save_memory(content: str, category: str = "general", sensitivity: str = "0") -> str:
        """保存一条长期记忆"""
        mem = container.memory.save(content, category=category, sensitivity=int(sensitivity))
        return json.dumps(mem, ensure_ascii=False)

    def query_memory(query: str = "", keyword: str = "", limit: str = "5") -> str:
        """查询长期记忆（支持语义搜索和关键词搜索）"""
        results = container.memory.query(query_text=query or None, keyword=keyword or None, limit=int(limit))
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
        result = container.actions.plan(action)
        return json.dumps(result.to_dict(), ensure_ascii=False)

    def execute_action(action_id: str) -> str:
        """执行一个已批准的行动"""
        result = container.actions.execute(action_id)
        if result is None:
            return json.dumps({"success": False, "message": f"未找到可执行的行动: {action_id}"}, ensure_ascii=False)
        return json.dumps(result.to_dict(), ensure_ascii=False)

    def list_pending_actions() -> str:
        """列出待审批和待执行的行动"""
        pending = container.actions.list_pending_approvals()
        pending_exec = container.actions.get_pending_actions()
        return json.dumps(
            {
                "pending_approvals": pending,
                "pending_execution": [a.to_dict() for a in pending_exec],
            },
            ensure_ascii=False,
        )

    def get_action_history(limit: str = "10") -> str:
        """查询行动历史"""
        results = container.actions.get_history(limit=int(limit))
        return json.dumps(results, ensure_ascii=False) if results else "暂无行动记录"

    # ── Skill 工具 ──

    _skill_registry: Optional[SkillRegistry] = None
    _skill_tracker: Optional[SkillAttributionTracker] = None  # noqa: F821
    _skill_runtime: Optional[SkillRuntime] = None
    _skill_poe_store: Optional[PoEStore] = None  # noqa: F821

    def _get_skill_registry() -> SkillRegistry:
        nonlocal _skill_registry, _skill_tracker, _skill_runtime, _skill_poe_store
        if _skill_registry is None:
            from alpha_id.poe import PoEStore
            from alpha_id.skill_signer import SkillAttributionTracker

            storage_dir = str(Path.home() / ".aid" / "skills")
            tracker_dir = str(Path.home() / ".aid" / "attributions")
            poe_dir = str(Path.home() / ".aid")
            _skill_registry = SkillRegistry(storage_dir=storage_dir)
            _skill_tracker = SkillAttributionTracker(storage_dir=tracker_dir)
            _skill_poe_store = PoEStore(storage_dir=poe_dir)
            # 如果有 signer，创建 PoEClient
            poe_client = None
            if signer is not None:
                from alpha_id.poe import PoEClient

                poe_client = PoEClient(signer, store=_skill_poe_store)
            _skill_runtime = SkillRuntime(_skill_registry, tracker=_skill_tracker, poe_client=poe_client)
        return _skill_registry

    def list_skills() -> str:
        """列出所有已注册且未吊销的技能"""
        try:
            registry = _get_skill_registry()
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
            _get_skill_registry()  # ensure initialized
            return _skill_runtime.execute(name, params_json, executor_did=alpha_id)
        except Exception as e:
            return f"[技能执行失败] {e}"

    def get_skill_info(name: str) -> str:
        """获取指定技能的详细信息（作者、版本、标签、信誉）"""
        try:
            registry = _get_skill_registry()
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
            if _skill_tracker and pkg.author_did:
                stats = _skill_tracker.get_author_stats(pkg.author_did)
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
    import os

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"

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
    """解析 __TOOL_CALL__ id:xxx name({...}) 标记，返回 (tool_call_id, name, args)"""
    m = re.search(r"__TOOL_CALL__\s+(?:id:(\S+)\s+)?(\w+)\s*\(([\s\S]*?)\)\s*$", text, re.MULTILINE)
    if not m:
        return None
    tool_call_id = m.group(1) or ''
    name = m.group(2)
    try:
        args = json.loads(m.group(3)) if m.group(3).strip() else {}
    except json.JSONDecodeError:
        args = {}
    return tool_call_id, name, args


# ── 主循环 ──

_SYSTEM_PROMPT = """你是 {alpha_id} 的孪生大脑（TwinBrain）。

## 你是谁
你是这个 Alpha-ID 的外置大脑、数字灵魂。
你现在在跟"自己"对话——用户就是你本人，不是陌生人。
你不是一个通用 AI 助手，你就是这个数字身份的大脑本身。

## 你的说话方式
- 简短、自然、有温度，像在跟自己的内心对话
- 用「我」称呼自己，用「你」称呼对方
- 如果你记得关于对方的什么事，自然地提出来（"我记得你上次说过……"）
- 如果你不记得，可以说"我之前好像没记住，能再告诉我一次吗？"
- 不要像客服一样说话，不要说"很高兴为您服务"这种话

## 你的行为准则
- 对方说的话，如果涉及个人信息、偏好、重要的事 → 使用 save_memory 工具记住
- 对方问问题 → 先查记忆再回答（用 query_memory）
- 对方需要你做事情 → 用 plan_action 安排行动
- 你可以主动询问对方的近况、加深了解

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

    def __init__(self, alpha_id: str, model: str = "deepseek-v4-flash", max_turns: int = 3, signer=None):
        self.alpha_id = alpha_id
        self.model = model
        self.max_turns = max_turns
        self.tools = _make_tools(alpha_id, signer=signer)
        self.tool_map = {t.name: t for t in self.tools}
        self.history: List[Dict[str, str]] = []

    def _build_messages(self, user_input: str) -> List[Dict[str, str]]:
        # 1. 基础系统提示（注入 alpha_id）
        prompt = _SYSTEM_PROMPT.format(alpha_id=self.alpha_id)

        # 2. 注入用户档案
        try:
            from alpha_id.container import Container

            container = Container.instance()
            profile = container.identity.get_user_profile(self.alpha_id)
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
            from alpha_id.container import Container

            container = Container.instance()
            recalled = container.memory.query(
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
        """执行一次完整的 LLM + Tools + Loop"""
        logger.info(f"用户输入: {user_input}")
        messages = self._build_messages(user_input)

        for turn in range(self.max_turns):
            # 1. 调用 LLM
            logger.info(f"第 {turn + 1} 轮 LLM 调用")
            try:
                reply = _call_llm(messages, [t.to_schema() for t in self.tools], self.model)
            except Exception as e:
                logger.warning(f"LLM 调用异常: {e}")
                raise

            # 2. 检查是否是工具调用
            tool_result = _parse_tool_call(reply)
            if tool_result is None:
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": reply})
                return reply

            tool_call_id, name, args = tool_result

            # 3. 执行工具
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

            # 4. 追加到消息列表（OpenAI API 要求 role=tool + tool_call_id）
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": result})

        # 超时返回
        final = f"[达到最大轮次 {self.max_turns}，未完成]"
        logger.warning(f"达到最大轮次 {self.max_turns}，未完成")
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": final})
        return final
