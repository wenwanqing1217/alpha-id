"""Alpha-ID 演示 Web 应用"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from alpha_id.container import Container
from alpha_id.poe import PoEStore
from alpha_id.signer import AIDSigner
from alpha_id.skill_signer import SkillRegistry
from core.message import Message
from core.twin_brain import BrainRegistry


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


# ── 应用 ──

_templates_dir = Path(__file__).parent / "templates"

# The HTML is a pure Vue.js 3 SPA that uses {{ }} for Vue bindings.
# Jinja2 and Vue.js both use {{ }} delimiters, which causes syntax conflicts.
# Since the template has no server-side rendering, HTMLResponse is the correct approach.
# The HTML template is a pure Vue.js 3 SPA that uses {{ }} for Vue bindings.
# Jinja2 and Vue.js both use {{ }} delimiters, causing syntax conflicts (e.g. ?. and ?? operators).
# Since the template has no server-side Jinja2 logic, HTMLResponse is the correct approach.
app = FastAPI(title="Alpha-ID Web Demo")
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


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = _templates_dir / "index.html"
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
        # 尝试按设备指纹查找已有用户
        users = container.storage.load("users") or {}
        found = None
        for aid, data in users.items():
            devices = data.get("devices", [])
            if req.device_fingerprint in devices:
                found = aid
                break
        if found:
            alpha_id = found
            action = "login"
        else:
            result = identity.register_user(device_fingerprint=req.device_fingerprint)
            if not result.get("success"):
                return JSONResponse(
                    status_code=400,
                    content={"error": result.get("message", "注册失败")},
                )
            alpha_id = result["alpha_id"]
            action = "register"

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
        nodes.append({
            "id": nid,
            "label": f"🤖 {label}\n信任:{p.trust_level}",
            "group": "peer",
            "did": p.did,
            "alias": p.alias or "",
            "trust_level": p.trust_level,
        })

    # ── 构建边 ──
    edges: List[dict] = []
    # 自己到每个对等节点的连接
    for p in peers:
        nid = p.did[-20:]
        edges.append({
            "from": "self",
            "to": nid,
            "label": "🔗",
            "title": f"信任: {p.trust_level}",
            "color": {"color": "#818cf8", "opacity": 0.6},
        })

    # 尝试加载最近的 PoE 调用链
    chains_found = 0
    try:
        poe_store = PoEStore(storage_dir=str(Path.home() / ".aid" / "poes"))
        for poe in poe_store.list_all():
            if chains_found >= 10:
                break
            nodes.append({
                "id": f"poe-{poe.poe_id[-12:]}",
                "label": f"📜 {poe.skill_name}",
                "group": "poe",
                "poe_id": poe.poe_id,
            })
            # 谁执行的这个 PoE
            executor_short = poe.executor_did[-20:] if len(poe.executor_did) > 20 else poe.executor_did
            edges.append({
                "from": executor_short if any(n["id"] == executor_short for n in nodes) else "self",
                "to": f"poe-{poe.poe_id[-12:]}",
                "label": poe.skill_name[:10],
                "color": {"color": "#34d399"},
                "title": f"技能: {poe.skill_name}\n成功: {poe.success}",
            })
            chains_found += 1
    except Exception:
        pass

    return {
        "my_did": my_did,
        "nodes": nodes,
        "edges": edges,
        "stats": {"peers": len(peers), "chains": chains_found},
    }
