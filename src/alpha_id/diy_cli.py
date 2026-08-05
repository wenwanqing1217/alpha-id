# TERM: DIY CLI — 用户对自己的 alphaid 说话即可实现功能（自然语言 → 自动化操作）
"""Alpha-ID DIY 子命令：对话即实现

核心理念：用户对自己的 Alpha-ID "说话"，就像用自动化编程工具一样，
LLM 负责把自然语言意图翻译成底层能力调用：
  - `aid chat "给我搭个 Python 项目脚手架"`  →  scaffold init
  - `aid chat "接一个翻译 agent，价格 2 积分一次"`  →  A2A register
  - `aid chat "找个免费的资讯 agent 跑一下每日摘要"` →  dispatch skill
  - `aid chat "生成一个咸鱼文案"`  →  飞书指令 / 总助 brain
  - `aid chat "同步飞书通讯录，自动加平台好友"` →  social sync-contacts

这样用户根本不需要记命令，自然语言即可 DIY 自己的整个工作台。
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import typer

logger = logging.getLogger(__name__)

diy_app = typer.Typer(help="DIY：对自己的 Alpha-ID 说话，自然语言实现任何功能")


# ── 意图分类与参数抽取 ────────────────────────────────────────

INTENT_HINTS: Dict[str, List[str]] = {
    "scaffold.init": ["搭", "脚手架", "项目", "初始化项目", "创建新项目"],
    "a2a.register": ["接一个", "注册 agent", "上架", "新 agent", "diy agent"],
    "a2a.call": ["调用", "跑", "执行 skill", "用 agent"],
    "a2a.findskill": ["找", "搜 agent", "找工具", "找 free agent"],
    "feishu.sync_contacts": ["同步飞书", "飞书通讯录", "同步好友", "自动加好友"],
    "feishu.bind": ["绑定飞书", "飞书 oauth", "飞书账号"],
    "credits.reward": ["给积分", "充值", "奖励积分", "加积分"],
    "workflow.execute": ["执行工作流", "跑模板", "跑流程", "工作流"],
    # ── 业务场景意图（复用 DS / Gateway / Nebula 已有后端，不造轮子）──
    "channel_copy.generate": ["咸鱼", "闲鱼", "小红书", "文案", "种草"],
    "video.generate": ["视频", "短视频", "做视频"],
    "video.publish": ["发布视频", "发视频", "上传视频", "tiktok", "youtube"],
    "douyin.publish": ["抖音", "发抖音", "发到抖音"],
    "shortdramas.submit": ["短剧", "投短剧", "短剧预审"],
    "game.generate": ["游戏", "小游戏", "做个游戏"],
    # ── 编程类任务委派给本机 Codex / Claude / Aider（adapter 层）──
    "codex.delegate": ["写代码", "写个", "实现一个", "编程", "脚本", "爬虫", "帮我写", "做个脚本"],
    "brain.chat": ["总助", "和大脑聊", "回答问题", "总结"],
}

ACTION_DESCRIPTIONS: Dict[str, str] = {
    "scaffold.init": "生成 Python 项目脚手架（aid scaffold init）",
    "a2a.register": "注册一个新的 DIY Agent 到 A2A（POST /a2a/register）",
    "a2a.call": "调用某个 Agent 的 skill（POST /a2a/call）",
    "a2a.findskill": "在 AgentGraph 市场里搜索提供某 skill 的 agent",
    "feishu.sync_contacts": "同步飞书通讯录，自动把同平台同事互加为好友",
    "feishu.bind": "绑定飞书账号到 Alpha-ID",
    "credits.reward": "奖励/充值积分",
    "workflow.execute": "执行工作流模板（Nebula /flow）",
    "channel_copy.generate": "生成闲鱼+小红书两套渠道文案（复用 DS /api/ai/channel-copy）",
    "video.generate": "生成 AI 种草视频（复用 Gateway MoneyPrinterTurbo）",
    "video.publish": "把已生成视频发布到 TikTok/YouTube/Instagram",
    "douyin.publish": "发布图文到抖音创作者中心（复用 Nebula DouyinAutomation）",
    "shortdramas.submit": "提交短剧内容预审（复用 Nebula shortdramas）",
    "game.generate": "生成一个可玩的 HTML5 小游戏（复用 Gateway GameEngine）",
    "codex.delegate": "把编程/脚本类任务委派给本机 Codex/Claude/Aider（adapter 层）",
    "brain.chat": "通过 TwinBrain 做对话/总结/问答",
}


@dataclass
class ParsedIntent:
    intent: str
    params: Dict[str, Any]
    confidence: float


def _local_parse_intent(prompt: str) -> ParsedIntent:
    """轻量本地意图解析（没装 LLM 也能用）

    基于关键词打分匹配 → 有 LLM 时会被上层 LLM parser 替换。
    """
    p = prompt.lower()
    scores: Dict[str, float] = {}
    for intent, hints in INTENT_HINTS.items():
        score = 0.0
        for hint in hints:
            if hint.lower() in p:
                score += 1.0
        if intent == "brain.chat":
            score += 0.1  # 兜底意图，总是保留微概率
        scores[intent] = score

    # 简单抽取参数
    params: Dict[str, Any] = {}
    # 路径/项目名
    import re
    path_m = re.search(r"(?:在|到|目录|path[ =:])?([a-zA-Z0-9_./\\-]{3,})", prompt)
    if path_m and ("项目" in prompt or "脚手架" in prompt or "生成" in prompt):
        params["path"] = path_m.group(1)
    # 积分
    price_m = re.search(r"(\d+)\s*积?分", prompt)
    if price_m:
        params["price_credits"] = int(price_m.group(1))
    # skill / agent 关键词
    skill_m = re.search(r"skill[\s=:]+([A-Za-z_\-\.0-9]+)", prompt, re.I)
    if skill_m:
        params["skill"] = skill_m.group(1)

    # 中文 key=value 参数抽取：商品=XX 卖点=XX 价格=XX 成色=XX 主题=XX 标题=XX 内容=XX
    _KEY_MAP = {
        "商品": "product", "产品": "product",
        "卖点": "description", "描述": "description",
        "价格": "price",
        "成色": "condition",
        "主题": "subject", "题目": "subject",
        "标题": "title",
        "内容": "content",
        "平台": "platform",
    }
    for k, v in re.findall(r"([\u4e00-\u9fa5A-Za-z]+)\s*=\s*([^=\s][^=]*?)(?=\s+\S+\s*=|$)", prompt):
        mapped = _KEY_MAP.get(k)
        if mapped and mapped not in params:
            params[mapped] = v.strip().strip("'\"，,。")

    # 选择最高分
    best = max(scores.items(), key=lambda x: x[1])
    if best[1] <= 0:
        return ParsedIntent("brain.chat", params, 0.5)
    total = sum(scores.values()) or 1
    return ParsedIntent(best[0], params, best[1] / total)


def _llm_parse_intent(prompt: str, model: Optional[str] = None) -> ParsedIntent:
    """LLM 意图解析（优先），失败回退到 _local_parse_intent"""
    try:
        from core.settings import settings as _set
        api_key = getattr(_set, "llm_api_key", "") or ""
        base_url = getattr(_set, "llm_base_url", "") or ""
        if not api_key and not base_url:
            raise RuntimeError("no LLM config")

        import httpx
        system = (
            "你是一个自动化助手。分析用户输入，输出 JSON：\n"
            "{\"intent\": str, \"params\": {key:value}, \"confidence\": 0..1}\n"
            "intent 只能是这些之一：\n"
            + "\n".join(f"  - {k}: {v}" for k, v in ACTION_DESCRIPTIONS.items())
            + "\n严格按 schema 返回，不解释。"
        )
        url = base_url.rstrip("/") + "/chat/completions" if base_url else ""
        if not url:
            raise RuntimeError("no base_url")
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model or "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
            },
            timeout=30,
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        # 取大括号里的 JSON
        start = content.find("{")
        end = content.rfind("}") + 1
        parsed = json.loads(content[start:end])
        return ParsedIntent(
            intent=str(parsed.get("intent", "brain.chat")),
            params=dict(parsed.get("params") or {}),
            confidence=float(parsed.get("confidence", 0.5)),
        )
    except Exception as e:
        logger.debug("LLM 意图解析失败，回退本地: %s", e)
        return _local_parse_intent(prompt)


# ── 执行器 ─────────────────────────────────────────────────────

class IntentExecutor:
    """意图 → 实际命令执行"""

    def __init__(self, alpha_id: str = "Alpha-001"):
        self.alpha_id = alpha_id

    def execute(self, intent: ParsedIntent) -> Dict[str, Any]:
        """执行解析后的意图，返回 {action: str, result: ...}"""
        handler = _HANDLERS.get(intent.intent, _HANDLERS["brain.chat"])
        return handler(self, intent.params)


def _handler_scaffold_init(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    path = params.get("path") or "./my-project"
    name = params.get("name") or ""
    force = bool(params.get("force"))
    # 直接复用 scaffold_cli，走函数调用（避免再开子进程）
    from alpha_id.scaffold_cli import scaffold_init
    # typer 参数支持直接调用（scaffold_init 已经做了 unwrap）
    scaffold_init(path=path, name=name, desc="", force=force, skip_git=False)
    return {"action": "scaffold.init", "path": path, "name": name}


def _handler_a2a_register(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    agent_id = params.get("agent_id") or params.get("name") or f"diy-{ctx.alpha_id[:8]}"
    endpoint = params.get("endpoint") or "https://example.com/placeholder"
    api_key = params.get("api_key") or "user-set-later"
    skills = params.get("skills") or params.get("skill_list")
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.replace("，", ",").split(",") if s.strip()]
    if not skills:
        # 简单兜底：按名字猜一个 skill
        skills = [agent_id]
    price = int(params.get("price_credits", 0))
    owner = params.get("owner_alpha_id") or ctx.alpha_id
    category = params.get("category", "")

    # 调 HTTP API（默认本地 8000），避免 import FastAPI app lifecycle
    import httpx
    try:
        resp = httpx.post(
            "http://127.0.0.1:8000/api/v1/a2a/register",
            json={
                "agent_id": agent_id,
                "name": agent_id,
                "endpoint": endpoint,
                "api_key": api_key,
                "skill_list": skills,
                "owner_alpha_id": owner,
                "category": category,
                "price_credits": price,
                "auto_submit": True,
            },
            timeout=15,
        )
        return {"action": "a2a.register", "http_status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"action": "a2a.register", "error": str(e), "hint": "请先启动 alphaid 服务 (8000)"}


def _handler_a2a_call(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    target = params.get("target") or params.get("agent_id") or ""
    skill = params.get("skill") or ""
    call_params = dict(params.get("params") or {})
    import httpx
    try:
        resp = httpx.post(
            "http://127.0.0.1:8000/api/v1/a2a/call",
            json={
                "caller": ctx.alpha_id,
                "target": target,
                "skill": skill,
                "params": call_params,
                "caller_alpha_id": ctx.alpha_id,
            },
            timeout=60,
        )
        return {"action": "a2a.call", "http_status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"action": "a2a.call", "error": str(e), "hint": "请先启动 alphaid 服务 (8000)"}


def _handler_a2a_findskill(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    skill = params.get("skill") or ""
    category = params.get("category") or ""
    import httpx
    try:
        q = []
        if skill:
            q.append(f"q={skill}")
        if category:
            q.append(f"category={category}")
        qs = "?" + "&".join(q) if q else ""
        resp = httpx.get(f"http://127.0.0.1:8000/api/v1/a2a/market{qs}", timeout=15)
        return {"action": "a2a.findskill", "http_status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"action": "a2a.findskill", "error": str(e)}


def _handler_feishu_sync(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    aid = params.get("alpha_id") or ctx.alpha_id
    import httpx
    try:
        resp = httpx.post(
            f"http://127.0.0.1:8000/api/v1/social/{aid}/sync-feishu-contacts",
            json={},
            timeout=30,
        )
        return {"action": "feishu.sync_contacts", "http_status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"action": "feishu.sync_contacts", "error": str(e)}


def _handler_feishu_bind(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    aid = params.get("alpha_id") or ctx.alpha_id
    import httpx
    try:
        resp = httpx.post(
            f"http://127.0.0.1:8000/api/v1/social/{aid}/bind/feishu",
            json={
                "alpha_id": aid,
                "feishu_open_id": params.get("feishu_open_id", ""),
                "feishu_user_id": params.get("feishu_user_id", ""),
                "phone": params.get("phone", ""),
            },
            timeout=15,
        )
        return {"action": "feishu.bind", "http_status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"action": "feishu.bind", "error": str(e)}


def _handler_credits_reward(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    aid = params.get("alpha_id") or ctx.alpha_id
    amount = int(params.get("amount", 0) or params.get("price_credits", 0) or 100)
    reason = params.get("reason", "reward")
    import httpx
    try:
        resp = httpx.post(
            "http://127.0.0.1:8000/api/v1/credits/reward",
            json={
                "alpha_id": aid,
                "amount": amount,
                "reason": reason,
            },
            timeout=15,
        )
        return {"action": "credits.reward", "http_status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"action": "credits.reward", "error": str(e)}


def _handler_workflow(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    """工作流执行 — 默认走 Nebula workflow engine（:2002）或 Gateway /flow"""
    tmpl = params.get("template") or params.get("workflow") or params.get("task") or "general"
    import httpx
    try:
        # 优先 Gateway 代理
        resp = httpx.post(
            "http://127.0.0.1:18080/v1/flow/execute",
            json={"template": tmpl, "params": params},
            timeout=60,
        )
        return {"action": "workflow.execute", "http_status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"action": "workflow.execute", "error": str(e), "hint": "请先启动 Gateway (18080)"}


# ── 服务地址（复用现有服务，不硬编码单一端口）────────────────

def _get_gateway_url() -> str:
    """Gateway 地址：优先 settings.gateway_url，其次环境变量，最后本地默认"""
    try:
        from core.settings import settings as _set
        if getattr(_set, "gateway_url", ""):
            return _set.gateway_url
    except Exception:
        pass
    return os.environ.get("GATEWAY_URL", "http://localhost:18080")


def _get_ds_url() -> str:
    """DS 电商看板地址（渠道文案能力所在）"""
    return os.environ.get("DS_URL", "http://localhost:3000")


def _get_nebula_url() -> str:
    """Nebula 工作流引擎地址（抖音/短剧能力所在）"""
    return os.environ.get("NEBULA_URL", "http://localhost:2002")


def _handler_channel_copy(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    """生成闲鱼+小红书两套渠道文案 — 复用 DS /api/ai/channel-copy"""
    product = params.get("product") or params.get("subject") or params.get("prompt", "")
    if not product:
        return {
            "action": "channel_copy.generate",
            "error": "缺少商品名",
            "hint": "示例：生成咸鱼文案 商品=北欧风香薰 卖点=大豆蜡留香 价格=59 成色=全新",
        }
    import httpx
    ds_url = _get_ds_url().rstrip("/")
    sections = []
    names = {"xianyu": "🐟 闲鱼", "xiaohongshu": "📕 小红书"}
    with httpx.Client(timeout=30) as client:
        for platform in ("xianyu", "xiaohongshu"):
            name = names[platform]
            try:
                resp = client.post(
                    f"{ds_url}/api/ai/channel-copy",
                    json={
                        "platform": platform,
                        "product": product,
                        "description": params.get("description") or None,
                        "price": params.get("price") or None,
                        "condition": params.get("condition") or "全新未拆",
                        "tone": "casual",
                    },
                )
                data = resp.json()
                if not resp.is_success:
                    sections.append(f"{name}\n❌ {data.get('error', f'HTTP {resp.status_code}')}")
                    continue
                r = data.get("result", {})
                sections.append(
                    f"{name}\n【标题】{r.get('title', '')}\n【正文】\n{r.get('body', '')}\n"
                    f"【标签】{' '.join(r.get('tags', []))}"
                )
            except Exception as e:
                sections.append(f"{name}\n❌ 生成失败：{e}")
    return {"action": "channel_copy.generate", "product": product, "reply": "\n\n──────────\n\n".join(sections)}


def _handler_video_generate(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    """生成 AI 种草视频 — 复用 Gateway /v1/content/video/generate（MoneyPrinterTurbo）"""
    subject = params.get("subject") or params.get("product") or params.get("prompt", "")
    if not subject:
        return {"action": "video.generate", "error": "缺少视频主题", "hint": "示例：生成视频 主题=北欧风香薰蜡烛种草"}
    import httpx
    try:
        resp = httpx.post(
            f"{_get_gateway_url().rstrip('/')}/v1/content/video/generate",
            json={
                "video_subject": subject,
                "video_aspect": "9:16",
                "video_language": "zh",
                "paragraph_number": 2,
            },
            timeout=30,
        )
        data = resp.json()
        if not resp.is_success:
            return {"action": "video.generate", "error": data.get("error", f"HTTP {resp.status_code}")}
        d = data.get("data", {}) if isinstance(data.get("data"), dict) else data
        task_id = d.get("task_id", "")
        return {"action": "video.generate", "task_id": task_id, "subject": subject, "data": data}
    except Exception as e:
        return {"action": "video.generate", "error": str(e), "hint": "请先启动 Gateway (18080) + MoneyPrinterTurbo"}


def _handler_video_publish(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    """发布视频到 TikTok/YouTube/Instagram — 复用 Gateway /v1/content/video/publish"""
    task_id = params.get("task_id") or params.get("id") or ""
    if not task_id:
        return {"action": "video.publish", "error": "缺少任务 ID", "hint": "示例：发布视频 abc123 标题=我的视频 平台=tiktok"}
    import httpx
    title = params.get("title") or "AI 生成视频"
    platforms = params.get("platform") or params.get("platforms") or "tiktok"
    if isinstance(platforms, str):
        platforms = [p.strip() for p in platforms.split(",") if p.strip()]
    try:
        resp = httpx.post(
            f"{_get_gateway_url().rstrip('/')}/v1/content/video/publish",
            json={"task_id": task_id, "title": title, "platforms": platforms},
            timeout=300,
        )
        data = resp.json()
        if not resp.is_success:
            return {"action": "video.publish", "error": data.get("error", f"HTTP {resp.status_code}")}
        return {"action": "video.publish", "task_id": task_id, "platforms": platforms, "data": data}
    except Exception as e:
        return {"action": "video.publish", "error": str(e), "hint": "请先启动 Gateway (18080)"}


def _handler_douyin_publish(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    """发布图文到抖音创作者中心 — 复用 Nebula POST /api/v1/automation/douyin/publish"""
    title = params.get("title") or params.get("subject") or ""
    if not title:
        return {"action": "douyin.publish", "error": "缺少标题", "hint": "示例：发抖音 标题=我的短剧 内容=剧情简介"}
    import httpx
    try:
        resp = httpx.post(
            f"{_get_nebula_url().rstrip('/')}/api/v1/automation/douyin/publish",
            json={"title": title, "content": params.get("content", "")},
            timeout=60,
        )
        data = resp.json()
        if not resp.is_success:
            return {"action": "douyin.publish", "error": data.get("detail") or data.get("error") or f"HTTP {resp.status_code}"}
        return {"action": "douyin.publish", "title": title, "data": data}
    except Exception as e:
        return {"action": "douyin.publish", "error": str(e), "hint": "请先启动 Nebula (2002) 并完成抖音登录"}


def _handler_shortdramas_submit(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    """提交短剧内容预审 — 复用 Nebula POST /api/v1/shortdramas/submit"""
    title = params.get("title") or params.get("subject") or ""
    if not title:
        return {"action": "shortdramas.submit", "error": "缺少标题", "hint": "示例：投短剧 标题=我的短剧 内容=剧情简介"}
    import httpx
    try:
        resp = httpx.post(
            f"{_get_nebula_url().rstrip('/')}/api/v1/shortdramas/submit",
            json={"title": title, "content": params.get("content", ""), "content_type": "video"},
            timeout=30,
        )
        data = resp.json()
        if not resp.is_success:
            return {"action": "shortdramas.submit", "error": data.get("detail") or data.get("error") or f"HTTP {resp.status_code}"}
        return {"action": "shortdramas.submit", "title": title, "job_id": data.get("job_id", ""), "data": data}
    except Exception as e:
        return {"action": "shortdramas.submit", "error": str(e), "hint": "请先启动 Nebula (2002)"}


def _handler_game_generate(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    """生成可玩 HTML5 小游戏 — 复用 Gateway /v1/content/game/generate（GameEngine）"""
    theme = params.get("theme") or params.get("subject") or params.get("prompt", "")
    if not theme:
        return {"action": "game.generate", "error": "缺少游戏主题", "hint": "示例：做个游戏 主题=太空射击 风格=cyberpunk"}
    import httpx
    try:
        resp = httpx.post(
            f"{_get_gateway_url().rstrip('/')}/v1/content/game/generate",
            json={"game_type": params.get("game_type") or "space_shooter", "theme": theme, "style": params.get("style") or "pixel_art"},
            timeout=30,
        )
        data = resp.json()
        if not resp.is_success:
            return {"action": "game.generate", "error": data.get("error", f"HTTP {resp.status_code}")}
        return {"action": "game.generate", "theme": theme, "data": data}
    except Exception as e:
        return {"action": "game.generate", "error": str(e), "hint": "请先启动 Gateway (18080)"}


def _handler_codex_delegate(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    """编程类任务委派给本机 Codex/Claude/Aider（adapter 层，复用 alpha_id.codex_api）"""
    prompt = params.get("prompt", "")
    if not prompt:
        return {"action": "codex.delegate", "error": "no prompt"}
    try:
        from alpha_id.codex_api import CodexAPIServer
        result = CodexAPIServer.ask_once(prompt)
        return {"action": "codex.delegate", "result": result}
    except Exception as e:
        return {"action": "codex.delegate", "error": str(e), "hint": "需要本机安装 codex CLI（alpha_id.codex_api 已内置封装）"}


def _handler_brain(ctx: IntentExecutor, params: Dict[str, Any]) -> Dict[str, Any]:
    """兜底：把用户 prompt 扔给 TwinBrain（/v1/chat 接口）"""
    prompt = params.get("prompt", "")
    if not prompt:
        return {"action": "brain.chat", "error": "no prompt"}
    import httpx
    try:
        resp = httpx.post(
            "http://127.0.0.1:18080/v1/chat",
            json={"alpha_id": ctx.alpha_id, "message": prompt},
            timeout=120,
        )
        return {"action": "brain.chat", "http_status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"action": "brain.chat", "error": str(e), "hint": "请先启动 Gateway + alphaid 服务"}


_HANDLERS: Dict[str, Callable[[IntentExecutor, Dict[str, Any]], Dict[str, Any]]] = {
    "scaffold.init": _handler_scaffold_init,
    "a2a.register": _handler_a2a_register,
    "a2a.call": _handler_a2a_call,
    "a2a.findskill": _handler_a2a_findskill,
    "feishu.sync_contacts": _handler_feishu_sync,
    "feishu.bind": _handler_feishu_bind,
    "credits.reward": _handler_credits_reward,
    "workflow.execute": _handler_workflow,
    "channel_copy.generate": _handler_channel_copy,
    "video.generate": _handler_video_generate,
    "video.publish": _handler_video_publish,
    "douyin.publish": _handler_douyin_publish,
    "shortdramas.submit": _handler_shortdramas_submit,
    "game.generate": _handler_game_generate,
    "codex.delegate": _handler_codex_delegate,
    "brain.chat": _handler_brain,
}


# ── Typer CLI 入口 ─────────────────────────────────────────────

@diy_app.callback()
def _main():
    """DIY：对自己的 Alpha-ID 说话即可，不用记命令"""


@diy_app.command("chat")
def diy_chat(
    prompt: str = typer.Argument(..., help="你想实现的功能，用自然语言说"),
    alpha_id: str = typer.Option("Alpha-001", "--alpha-id", "-a"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="只解析意图不执行"),
    use_local_parser: bool = typer.Option(False, "--local", help="强制用本地关键词解析（不联网）"),
):
    """对话即实现：你用中文说，Alpha-ID DIY 自动找最合适的工具/流程/agent 执行"""
    typer.echo(f"🧠 Alpha-ID DIY — 收到：{prompt}")

    parser = _local_parse_intent if use_local_parser else _llm_parse_intent
    intent = parser(prompt)

    typer.echo(
        f"   意图：{intent.intent}  "
        f"(置信度 {intent.confidence:.0%})  "
        f"说明：{ACTION_DESCRIPTIONS.get(intent.intent, '?')}"
    )
    if intent.params:
        typer.echo(f"   参数：{json.dumps(intent.params, ensure_ascii=False)}")

    if dry_run:
        typer.echo("   ✋ --dry-run，停止执行")
        return

    # prompt 没有出现在 params 里，但 brain.chat 需要它 → 补上
    intent.params.setdefault("prompt", prompt)

    executor = IntentExecutor(alpha_id=alpha_id)
    result = executor.execute(intent)
    # 漂亮地打印结果
    typer.echo("--- 结果 ---")
    action = result.get("action", "")
    if result.get("error"):
        typer.echo(f"❌ [{action}] 错误：{result['error']}")
        hint = result.get("hint")
        if hint:
            typer.echo(f"   💡 {hint}")
        raise typer.Exit(code=1)
    else:
        typer.echo(f"✅ [{action}] 成功")
        for k, v in result.items():
            if k in ("action", "error", "hint"):
                continue
            if isinstance(v, dict):
                typer.echo(f"   {k}: {json.dumps(v, ensure_ascii=False, indent=6)}")
            else:
                typer.echo(f"   {k}: {v}")


@diy_app.command("intents")
def list_intents():
    """列出所有已注册的 DIY 意图（帮助理解能做什么）"""
    typer.echo("Alpha-ID DIY 可用意图（自然语言会被自动匹配到这些之一）：\n")
    for i, (intent, desc) in enumerate(ACTION_DESCRIPTIONS.items(), 1):
        typer.echo(f"  {i:2d}. {intent}")
        typer.echo(f"      {desc}")
        hints = INTENT_HINTS.get(intent, [])
        if hints:
            typer.echo(f"      关键词：{', '.join(hints)}")
        typer.echo("")


@diy_app.command("repl")
def diy_repl(
    alpha_id: str = typer.Option("Alpha-001", "--alpha-id", "-a"),
):
    """进入 REPL 模式：连续对话，每次一行自然语言即可"""
    typer.echo("进入 Alpha-ID DIY REPL。输入你想做的事情，Ctrl+C 退出。")
    typer.echo("提示：直接说 \"接一个翻译 agent，价格 2 积分\" 或 \"生成咸鱼文案\" 即可")
    executor = IntentExecutor(alpha_id=alpha_id)
    while True:
        try:
            prompt = input("🧠 diy> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("\n👋 再见")
            return
        if not prompt:
            continue
        if prompt in ("exit", "quit", "bye"):
            return
        intent = _llm_parse_intent(prompt)
        intent.params.setdefault("prompt", prompt)
        typer.echo(
            f"   → {intent.intent} ({intent.confidence:.0%})"
            + (f"  params={intent.params}" if intent.params else "")
        )
        try:
            result = executor.execute(intent)
        except Exception as e:
            typer.echo(f"   ❌ {e}")
            continue
        if result.get("error"):
            typer.echo(f"   ❌ {result['error']}")
        else:
            typer.echo(f"   ✅ done")
            data = result.get("data")
            if data and isinstance(data, dict):
                # 只打印关键字段
                keys_of_interest = ["success", "message", "price", "charged", "balance", "agents", "items", "count"]
                short = {k: data[k] for k in keys_of_interest if k in data}
                if short:
                    typer.echo(f"      {json.dumps(short, ensure_ascii=False)}")
                else:
                    s = json.dumps(data, ensure_ascii=False)
                    typer.echo(f"      {s[:300]}{'...' if len(s) > 300 else ''}")
