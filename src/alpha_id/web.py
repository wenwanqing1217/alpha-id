"""Alpha-ID 演示 Web 应用"""

import ipaddress
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from alpha_id.container import Container
from alpha_id.poe import PoEStore
from alpha_id.signer import AIDSigner
from alpha_id.skill_signer import SkillRegistry
from core.message import Message
from core.twin_brain import BrainRegistry

app = FastAPI(title="Alpha-ID Ghost Layer")

# ── 全局缓存 ──

_network_cache: Dict[str, Any] = {}


def _get_network() -> Optional[Any]:
    """创建 AgentNetwork 实例（带缓存）"""
    if "network" in _network_cache:
        return _network_cache["network"]
    try:
        signer = AIDSigner()
        signer.load_from_aid_dir()
        registry = SkillRegistry(storage_dir=str(Path.home() / ".aid" / "skills"))
        poe_store = PoEStore(storage_dir=str(Path.home() / ".aid" / "poes"))
        from alpha_id.agent_network import AgentNetwork

        net = AgentNetwork(signer, registry=registry, poe_store=poe_store)
        _network_cache["network"] = net
        return net
    except Exception:
        return None


# ── 数据模型 ──


class LoginRequest(BaseModel):
    device_fingerprint: str
    alpha_id: Optional[str] = None


class ChatRequest(BaseModel):
    alpha_id: str = ""
    message: str = ""


class BrainActionRequest(BaseModel):
    alpha_id: str


# ── Profile 页面 ──


def _load_profile_dict() -> Dict[str, Any]:
    try:
        from alpha_id.profile_schema import load_profile

        profile = load_profile()
        if profile:
            return profile.to_dict()
    except Exception:
        pass
    return {}


@app.get("/profile", response_class=HTMLResponse)
async def profile_page():
    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Alpha-ID 个人空间</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:linear-gradient(135deg,#0f172a,#1e293b);min-height:100vh;color:#e2e8f0;}
header{padding:24px;border-bottom:1px solid rgba(148,163,184,0.1);}
main{max-width:960px;margin:0 auto;padding:24px;}
.card{background:rgba(30,41,59,0.8);backdrop-filter:blur(20px);border:1px solid rgba(148,163,184,0.1);border-radius:24px;padding:24px;margin-bottom:24px;}
.tag{display:inline-block;background:rgba(51,65,85,0.6);color:#e2e8f0;padding:6px 14px;border-radius:999px;font-size:13px;margin:3px;border:1px solid rgba(148,163,184,0.08);}
.section-title{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;}
</style></head><body>
<header><h1>Alpha-ID 个人空间</h1><p>你的数字灵魂主页</p></header>
<main>
  <div class="card">
    <div class="section-title">画像概览</div>
    <pre id="profile" style="white-space:pre-wrap;opacity:.9;">加载中...</pre>
  </div>
  <div class="card">
    <div class="section-title">模拟盘入口</div>
    <p>模拟盘是 Alpha-ID 的第二魔法时刻：你的精灵在数字创世纪里替你学习、社交、成长。</p>
    <a href="/simulation" style="color:#38bdf8;">进入模拟盘 →</a>
  </div>
</main>
<script>
async function load(){
  const res = await fetch('/api/profile');
  const data = res.ok ? await res.json() : {error:'Profile not found'};
  document.getElementById('profile').textContent = JSON.stringify(data, null, 2);
}
load();
</script>
</body></html>"""
    return HTMLResponse(content=html)


@app.get("/simulation", response_class=HTMLResponse)
async def simulation_page():
    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Alpha-ID 模拟盘</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:radial-gradient(circle at top,#1e293b,#0f172a);min-height:100vh;color:#e2e8f0;}
header{padding:24px;border-bottom:1px solid rgba(148,163,184,0.1);}
main{max-width:960px;margin:0 auto;padding:24px;}
.realm{background:rgba(30,41,59,0.8);backdrop-filter:blur(20px);border:1px solid rgba(148,163,184,0.1);border-radius:24px;padding:24px;margin-bottom:24px;}
.realm h3{margin-bottom:8px;}
.tag{display:inline-block;background:rgba(51,65,85,0.6);color:#e2e8f0;padding:6px 14px;border-radius:999px;font-size:13px;margin:3px;border:1px solid rgba(148,163,184,0.08);}
</style></head><body>
<header><h1>数字创世纪 · 模拟盘</h1><p>Nine mini-universes for your spirit to play, learn, and grow.</p></header>
<main>
  <div class="realm">
    <h3>第一宇宙：交易所</h3>
    <p>收集决策数据：风险承受、决策速度、资产配置偏好。</p>
    <span class="tag">风险偏好</span><span class="tag">决策速度</span>
  </div>
  <div class="realm">
    <h3>第二宇宙：竞技场</h3>
    <p>收集对抗数据：进攻性、策略偏好、逆商。</p>
    <span class="tag">进攻性</span><span class="tag">策略</span>
  </div>
  <div class="realm">
    <h3>第三宇宙：学院</h3>
    <p>收集学习数据：知识领域、耐心、复盘习惯。</p>
    <span class="tag">知识领域</span><span class="tag">耐心</span>
  </div>
</main>
</body></html>"""
    return HTMLResponse(content=html)


# ── 应用 ──

_templates_dir = Path(__file__).parent / "templates"

# The HTML is a pure Vue.js 3 SPA that uses {{ }} for Vue bindings.
# Jinja2 and Vue.js both use {{ }} delimiters, which causes syntax conflicts.
# Since the template has no server-side rendering, HTMLResponse is the correct approach.
# The HTML template is a pure Vue.js 3 SPA that uses {{ }} for Vue bindings.
# Jinja2 and Vue.js both use {{ }} delimiters, causing syntax conflicts (e.g. ?. and ?? operators).
# Since the template has no server-side Jinja2 logic, HTMLResponse is the correct approach.
app = FastAPI(title="Alpha-ID Web Demo")

# CORS：显式允许列表（禁止 wildcard + credentials 组合）
from fastapi.middleware.cors import CORSMiddleware
_allowed = os.environ.get("AID_ALLOWED_ORIGINS", "").strip()
if _allowed:
    _origins = [o.strip() for o in _allowed.split(",") if o.strip()]
else:
    _origins = ["http://localhost:3000", "http://localhost:8000", "http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# 静态文件服务（本地 CSS / JS，避免 CDN 被墙）
_static_dir = Path(__file__).parent / "templates"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

_brain_registry = BrainRegistry()


# ── 辅助函数 ──


def _get_container() -> Container:
    return Container.instance()


def _get_or_create_brain(alpha_id: str):
    container = _get_container()
    return _brain_registry.get_or_create(alpha_id, storage=container.storage)


def _user_exists(alpha_id: str) -> bool:
    return _get_container().identity.get_user_profile(alpha_id) is not None


# ── 路由 ──


@app.get("/api/profile")
async def api_profile() -> JSONResponse:
    data = _load_profile_dict()
    return JSONResponse(
        {
            "profile": data,
            "collected_sources": data.get("x_collected_sources", []),
            "provenance": data.get("x_provenance", {}),
        }
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = _templates_dir / "ghost.html"
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.post("/login")
async def login(req: LoginRequest):
    if not req.device_fingerprint.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "设备指纹不能为空"},
        )

    container = _get_container()
    identity = container.identity

    # 如果指定了 alpha_id，检查是否存在
    if req.alpha_id:
        profile = identity.get_user_profile(req.alpha_id)
        if profile is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"Alpha-ID {req.alpha_id} 不存在"},
            )
        devices = profile.get("devices", [])
        if req.device_fingerprint not in devices:
            identity.update_device_binding(req.alpha_id, req.device_fingerprint)
        alpha_id = req.alpha_id
        action = "login"
    else:
        return JSONResponse(
            status_code=403,
            content={"error": "设备未绑定，请先注册或绑定设备"},
        )

    # 确保大脑已创建并唤醒
    brain = _get_or_create_brain(alpha_id)
    brain.awake()

    friends = container.social.get_friends(alpha_id)
    stats = {"msg_count": getattr(brain, "_message_count", 0)}

    return {
        "success": True,
        "alpha_id": alpha_id,
        "action": action,
        "friends": friends,
        "stats": stats,
        "brain_state": brain.state.value,
        "greeting": f"欢迎回来，{alpha_id}" if action == "login" else f"新身份 {alpha_id} 已创建",
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    if not req.alpha_id.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "alpha_id 不能为空"},
        )
    if not req.message.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "消息不能为空"},
        )

    container = _get_container()

    # 验证用户存在
    if not _user_exists(req.alpha_id):
        return JSONResponse(
            status_code=401,
            content={"error": f"Alpha-ID {req.alpha_id} 未认证"},
        )

    # 获取大脑并唤醒
    brain = _get_or_create_brain(req.alpha_id)
    brain.awake()

    # 发送消息给大脑
    msg = Message.create_chat(
        sender=req.alpha_id,
        recipient=req.alpha_id,
        text=req.message,
    )
    response = brain.receive(msg)

    reply = response.message or response.data.get("reply", "ok")

    return {
        "reply": reply,
        "agent": {
            "alpha_id": req.alpha_id,
            "brain_state": brain.state.value,
            "msg_count": getattr(brain, "_message_count", 0),
            "friends": container.social.get_friends(req.alpha_id),
        },
    }


# ── 流式聊天（延迟导入，可选依赖） ──

import json  # noqa: E402
import os  # noqa: E402

import httpx  # noqa: E402
from starlette.responses import StreamingResponse  # noqa: E402


async def _stream_llm(messages: list, model: str = "deepseek-v4-flash"):
    """调用 DeepSeek API 并流式返回 token"""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com/v1"

    # SSRF validation for LLM base_url
    _ALLOWED_LLM_HOSTS = {  # noqa: N806
        "api.deepseek.com",
        "api.openai.com",
        "api.siliconflow.cn",
        "open.bigmodel.cn",
        "api.moonshot.cn",
        "api.anthropic.com",
        "localhost",
        "127.0.0.1",
    }
    parsed_url = urlparse(base_url)
    hostname = (parsed_url.hostname or "").lower()
    if parsed_url.scheme not in ("http", "https"):
        yield f"data: {json.dumps({'error': '不支持的 LLM URL scheme: ' + parsed_url.scheme})}\n\n"
        yield "data: [DONE]\n\n"
        return
    if not hostname:
        yield f"data: {json.dumps({'error': 'LLM base_url 缺少 hostname'})}\n\n"
        yield "data: [DONE]\n\n"
        return
    if hostname not in _ALLOWED_LLM_HOSTS:
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                yield f"data: {json.dumps({'error': 'LLM base_url 禁止访问内网地址: ' + hostname})}\n\n"
                yield "data: [DONE]\n\n"
                return
        except ValueError:
            yield f"data: {json.dumps({'error': 'LLM base_url 域名未授权: ' + hostname})}\n\n"
            yield "data: [DONE]\n\n"
            return

    if not api_key:
        yield f"data: {json.dumps({'error': 'LLM 未配置'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield f"data: {json.dumps({'token': content})}\n\n"
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if not req.alpha_id.strip() or not req.message.strip():
        return JSONResponse(status_code=400, content={"error": "参数不全"})

    container = _get_container()
    if not _user_exists(req.alpha_id):
        return JSONResponse(status_code=401, content={"error": "未认证"})

    brain = _get_or_create_brain(req.alpha_id)
    brain.awake()

    # 构建消息（简化版：不经过完整的 ReAct 循环，仅做纯 LLM 对话）
    system_prompt = (
        f"你是 {req.alpha_id} 的孪生大脑（TwinBrain），一个有温度、有记忆的数字灵魂。\n"
        f"你现在在跟「自己」对话——用户就是你本人。\n"
        f"回答简短、自然、有温度，像在跟自己的内心对话。\n"
        f"不要像客服一样说话，不要说「很高兴为您服务」这种话。\n"
    )

    # 尝试注入记忆
    try:
        recalled = container.memory.query(query_text=req.message, max_sensitivity=70, limit=3)
        if recalled:
            system_prompt += "\n\n## 我记得的关于这件事的回忆"
            for m in recalled:
                content = m.get("content", "")
                system_prompt += f"\n- {content}"
    except Exception:
        pass

    messages_for_llm = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.message},
    ]

    return StreamingResponse(
        _stream_llm(messages_for_llm),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/identity")
async def get_identity(request: Request):
    alpha_id = request.headers.get("X-Alpha-ID")
    if not alpha_id:
        return JSONResponse(
            status_code=400,
            content={"error": "X-Alpha-ID header 不能为空"},
        )

    container = _get_container()
    profile = container.identity.get_user_profile(alpha_id)
    if profile is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Alpha-ID {alpha_id} 不存在"},
        )

    friends = container.social.get_friends(alpha_id)

    return {
        "alpha_id": alpha_id,
        "profile": profile,
        "friends": friends,
    }


@app.get("/brain/status")
async def brain_status(alpha_id: Optional[str] = None):
    if not alpha_id:
        return JSONResponse(
            status_code=400,
            content={"error": "alpha_id 不能为空"},
        )
    if not _user_exists(alpha_id):
        return JSONResponse(
            status_code=404,
            content={"error": f"Alpha-ID {alpha_id} 不存在"},
        )

    brain = _get_or_create_brain(alpha_id)
    return {
        "success": True,
        "alpha_id": alpha_id,
        "state": brain.state.value,
    }


@app.post("/brain/sleep")
async def brain_sleep(req: BrainActionRequest):
    brain = _get_or_create_brain(req.alpha_id)
    brain.sleep()
    return {"state": brain.state.value, "success": True}


@app.post("/brain/awake")
async def brain_awake(req: BrainActionRequest):
    brain = _get_or_create_brain(req.alpha_id)
    brain.awake()
    return {"state": brain.state.value, "success": True}


@app.post("/brain/think")
async def brain_think(req: BrainActionRequest):
    brain = _get_or_create_brain(req.alpha_id)
    brain.awake()
    result = brain.think()
    return {
        "success": True,
        "state": brain.state.value,
        "agent_thought": result.get("agent_thought", ""),
    }


# ── 网络拓扑 ──


@app.get("/network/topology")
async def network_topology():
    """返回 Agent 网络拓扑数据（节点 + 边），用于前端可视化"""
    network = _get_network()
    if network is None:
        return {
            "my_did": "",
            "nodes": [],
            "edges": [],
            "stats": {"peers": 0, "chains": 0},
        }

    peers = network.list_peers()
    my_did = network.my_did

    # ── 构建节点 ──
    nodes: List[dict] = []
    # 自己永远是中心节点
    my_label = my_did[-12:] if len(my_did) > 12 else my_did
    nodes.append({"id": "self", "label": f"🧠 我\n{my_label}", "group": "self", "did": my_did})

    for p in peers:
        nid = p.did[-20:]  # 短的节点 ID
        label = p.alias or p.did[-12:]
        nodes.append(
            {
                "id": nid,
                "label": f"🤖 {label}\n信任:{p.trust_level}",
                "group": "peer",
                "did": p.did,
                "alias": p.alias or "",
                "trust_level": p.trust_level,
            }
        )

    # ── 构建边 ──
    edges: List[dict] = []
    # 自己到每个对等节点的连接
    for p in peers:
        nid = p.did[-20:]
        edges.append(
            {
                "from": "self",
                "to": nid,
                "label": "🔗",
                "title": f"信任: {p.trust_level}",
                "color": {"color": "#818cf8", "opacity": 0.6},
            }
        )

    # 尝试加载最近的 PoE 调用链
    chains_found = 0
    try:
        poe_store = PoEStore(storage_dir=str(Path.home() / ".aid" / "poes"))
        for poe in poe_store.list_all():
            if chains_found >= 10:
                break
            nodes.append(
                {
                    "id": f"poe-{poe.poe_id[-12:]}",
                    "label": f"📜 {poe.skill_name}",
                    "group": "poe",
                    "poe_id": poe.poe_id,
                }
            )
            # 谁执行的这个 PoE
            executor_short = poe.executor_did[-20:] if len(poe.executor_did) > 20 else poe.executor_did
            edges.append(
                {
                    "from": executor_short if any(n["id"] == executor_short for n in nodes) else "self",
                    "to": f"poe-{poe.poe_id[-12:]}",
                    "label": poe.skill_name[:10],
                    "color": {"color": "#34d399"},
                    "title": f"技能: {poe.skill_name}\n成功: {poe.success}",
                }
            )
            chains_found += 1
    except Exception:
        pass

    return {
        "my_did": my_did,
        "nodes": nodes,
        "edges": edges,
        "stats": {"peers": len(peers), "chains": chains_found},
    }
