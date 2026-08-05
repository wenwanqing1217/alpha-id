"""Alpha-ID API 服务入口

运行方式：
    python -m src.main
    或安装后：aid-api
"""

import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

# 配置结构化日志（structlog + 敏感数据脱敏 + JSON/彩色输出）
from core.logging_config import configure_logging

configure_logging()

logger = logging.getLogger(__name__)

from dotenv import load_dotenv  # noqa: E402

# 加载 .env 文件（必须在读取环境变量之前）
load_dotenv()

from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from alpha_id.container import Container, get_container  # noqa: E402
from auth.csrf import CSRFMiddleware  # noqa: E402
from auth.jwt import validate_master_key  # noqa: E402
from core.middleware import CorrelationIDMiddleware  # noqa: E402
from core.rate_limit import RateLimitMiddleware  # noqa: E402
from core.settings import settings  # noqa: E402

from .api.a2a import router as a2a_router  # noqa: E402
from .api.agent import router as agent_router  # noqa: E402
from .api.agent_dispatch import router as agent_dispatch_router  # noqa: E402
from .api.credits import router as credits_router  # noqa: E402
from .api.dual_chain import router as dual_chain_router  # noqa: E402
from .api.gdpr import router as gdpr_router  # noqa: E402

# 路由导入（项目始终以 python -m src.main 方式运行）
from .api.identity import router as identity_router  # noqa: E402
from .api.mindflow import router as mindflow_router  # noqa: E402
from .api.observability import router as observability_router  # noqa: E402
from .api.registration import router as registration_router  # noqa: E402
from .api.risk import router as risk_router  # noqa: E402
from .api.social import router as social_router  # noqa: E402
from .api.tenant_panel import router as tenant_panel_router  # noqa: E402
from .api.voice import router as voice_router  # noqa: E402


class SecurityHeadersMiddleware:
    """全局安全响应头中间件

    在 FastAPI 中间件栈最外层执行，确保所有响应都携带安全头。
    执行顺序：SecurityHeaders → CorrelationId → RateLimit → CSRF → CORS → Route
    """

    # 默认安全头配置
    _DEFAULT_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": (
            "geolocation=(), microphone=(), camera=(), payment=()"
        ),
    }

    def __init__(self, app, hsts_max_age: int = 31536000) -> None:
        self.app = app
        self._headers = dict(self._DEFAULT_HEADERS)
        if hsts_max_age > 0:
            self._headers["Strict-Transport-Security"] = (
                f"max-age={hsts_max_age}; includeSubDomains"
            )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                # 合并安全头，不覆盖应用已设置的响应头
                existing = {h[0].lower(): h[1] for h in message.get("headers", [])}
                for key, value in self._headers.items():
                    if key.lower() not in existing:
                        message["headers"].append(
                            (key.encode("latin-1"), value.encode("latin-1"))
                        )
            await send(message)

        await self.app(scope, receive, send_with_headers)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """服务生命周期管理

    依赖注入迁移（Phase 2）：
    - Container 实例存储在 app.state.container
    - API 路由通过 Depends(get_container) 获取
    - 保留 Container.instance() 单例以兼容非 FastAPI 上下文
    """
    # 启动：校验 JWT 主密钥
    validate_master_key()
    # 启动：配置文件热更新监听（.env 变更自动 reload）
    from core.settings import start_file_watcher
    start_file_watcher(interval=2.0)
    # 启动：容器初始化 + 注入 app.state（FastAPI DI）
    container = Container.instance()
    app.state.container = container
    # 保存主 event loop 引用，供跨线程异步调度使用（如飞书回调）
    app.state._main_event_loop = asyncio.get_event_loop()

    # 启动：EventBus 跨服务事件消费（Redis Streams XREADGROUP）
    # TERM: EventBus — Redis Streams 跨服务事件总线（替代旧 blinker 实现）
    try:
        from core.event_bus import get_event_bus
        event_bus = get_event_bus()
        event_bus.start_consuming()
        app.state.event_bus = event_bus
        logger.info("EventBus 消费已启动（Redis Streams XREADGROUP）")
    except Exception as exc:
        logger.warning("EventBus 启动失败（非阻塞，本地 emit/on 仍可用）: %s", exc)

    # 启动：A2A 协议（路由集成，非独立线程）
    if settings.a2a_enabled:
        try:
            from core.a2a import A2AAuditLog, A2ARegistry, A2ASigner, A2ASkillRegistry
            from core.audit_store import SqliteAuditStore
            from core.persistent_registry import FileRegistryStore, PersistentA2ARegistry

            # 构建持久化 A2A 注册表（服务重启不丢 Agent）
            base_registry = A2ARegistry()
            store = FileRegistryStore()
            registry = PersistentA2ARegistry(base_registry, store=store, ttl=300)
            restored = registry.load_from_store()
            if restored:
                logger.info("A2A 注册表已恢复 %d 个 Agent", restored)

            # 构建技能注册表
            skills = A2ASkillRegistry()

            # 初始化 A2A 签名器（无密钥 = 签名功能关闭，但对象可用）
            did = settings.app_name or ""
            signer = A2ASigner()

            # 注册示例技能
            @skills.skill("ping", description="健康检查")
            def _ping(params):
                return {"status": "ok", "agent": settings.app_name}

            @skills.skill("echo", description="回显参数")
            def _echo(params):
                return params

            @skills.skill("ghost.sample.fetch", description="外部 HTTP 获取（公开 API，带 SSRF 防护）")
            async def _ghost_sample_fetch(params):
                """调用外部公开 HTTP API 获取数据（SSRF 防护）

                参数：
                  endpoint: 要请求的 URL（仅允许 http/https，禁止内网地址）
                  method: HTTP 方法，默认 GET
                  headers: 可选请求头
                  body: 可选请求体（POST 时使用）

                安全限制：
                  - 仅允许 http/https 协议
                  - 禁止访问私有 IP 段（127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12,
                    192.168.0.0/16, 169.254.0.0/16）
                  - 禁止访问 localhost 及相关主机名
                  - 禁止访问云元数据端点
                  - 响应体限制 4000 字符
                """
                import ipaddress
                import socket
                from urllib.parse import urlparse

                endpoint = params.get("endpoint", "")
                if not endpoint:
                    return {"error": "endpoint 参数必填"}

                method = params.get("method", "GET").upper()
                headers = params.get("headers", {})
                body = params.get("body")

                # ── SSRF 防护 ──

                # 1. URL scheme 校验
                parsed = urlparse(endpoint)
                if parsed.scheme not in ("http", "https"):
                    return {"error": f"不支持的协议: {parsed.scheme}，仅允许 http/https"}

                # 2. 禁止内网主机名
                blocked_hosts = {
                    "localhost", "127.0.0.1", "0.0.0.0", "::1",
                    "metadata.google.internal", "metadata.internal",
                    "169.254.169.254",  # AWS/GCP/Azure 元数据
                }
                hostname = parsed.hostname or ""
                if hostname.lower() in blocked_hosts:
                    return {"error": f"禁止访问该主机: {hostname}"}

                # 3. 解析 IP 并禁止私有地址
                try:
                    addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
                    for family, type_, proto, canonname, sockaddr in addr_info:
                        ip = ipaddress.ip_address(sockaddr[0])
                        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                            return {"error": f"禁止访问私有/保留 IP 地址: {ip}"}
                except socket.gaierror:
                    return {"error": f"无法解析主机名: {hostname}"}

                # 4. 禁止危险请求方法
                if method not in ("GET", "POST", "PUT", "PATCH"):
                    return {"error": f"不支持的 HTTP 方法: {method}"}

                # 5. 使用连接池（避免每次调用都新建 AsyncClient）
                try:
                    from core.http_client import get_async_client
                    client = get_async_client()
                    if method == "POST":
                        resp = await client.post(endpoint, json=body, headers=headers)
                    else:
                        resp = await client.get(endpoint, headers=headers)
                    return {
                        "status_code": resp.status_code,
                        "headers": dict(resp.headers),
                        "body": resp.text[:4000],
                    }
                except Exception as e:
                    return {"error": str(e)}

            # 将 A2A 运行时状态注入 app.state，供 a2a_router 使用
            app.state.a2a_state = {
                "skills": skills,
                "registry": registry,
                "audit": A2AAuditLog(store=SqliteAuditStore()),
                "signer": signer,
                "did": did or "",
                "alpha_id": settings.app_name,
                "seen_requests": [],
                "seen_requests_set": set(),
                "seen_requests_deque": deque(maxlen=10000),
                "dual_chain_cache": {},  # alpha_id → DualChainManager (避免每次调用都 PBKDF2)
            }
            logger.info("A2A 协议已初始化（路由集成模式）")
        except Exception as exc:
            logger.warning("A2A 初始化失败（非阻塞）: %s", exc)

    # 启动：飞书桥接器（WebSocket 长连接 + Webhook）
    feishu_bridge = None
    feishu_ws_thread = None
    if settings.feishu_app_id and settings.feishu_app_secret:
        try:
            from alpha_id.feishu_bridge import FeishuBridge
            feishu_bridge = FeishuBridge(
                app_id=settings.feishu_app_id,
                app_secret=settings.feishu_app_secret,
                verification_token=settings.feishu_verification_token,
                encrypt_key=settings.feishu_encrypt_key,
            )
            app.state.feishu_bridge = feishu_bridge
            logger.info("飞书桥接器已初始化")

            # 注册消息回调 — 收到飞书消息后自动回复
            def _on_feishu_message(msg):
                """飞书消息回调：处理命令/代码模式 + CHAT 模式接入 Agent

                注意：此回调在飞书 WebSocket 后台线程中同步执行。
                涉及 async 操作（AgentLoop）通过主 event loop 调度，
                避免 asyncio.run() 在已有 loop 的线程中崩溃。
                """
                try:
                    # 1. 先走 bridge.handle_message（命令/代码模式，同步）
                    reply = feishu_bridge.handle_message(msg)

                    # 2. 如果命令/代码模式没返回内容，走 CHAT 模式（AgentLoop，异步）
                    if not reply:
                        try:
                            from core.agent import AgentLoop
                            coro = AgentLoop(alpha_id=settings.default_alpha_id).arun(msg.content)
                            # 通过主 event loop 调度（跨线程安全）
                            main_loop = getattr(app.state, "_main_event_loop", None)
                            if main_loop is not None and not main_loop.is_closed():
                                future = asyncio.run_coroutine_threadsafe(coro, main_loop)
                                reply = future.result(timeout=60)
                            else:
                                # 降级：在当前线程创建临时 loop（仅初始化失败时）
                                reply = asyncio.run(coro)
                        except Exception as agent_err:
                            logger.error("飞书 Agent 回复失败: %s", agent_err)
                            reply = f"抱歉，处理消息时遇到问题: {agent_err}"

                    # 3. 发送回复到飞书
                    if reply and msg.chat_id:
                        feishu_bridge.send_message(msg.chat_id, reply)
                        logger.info("飞书回复已发送: chat=%s reply=%s...",
                                    msg.chat_id[:12], reply[:50])
                except Exception as e:
                    logger.error("飞书消息处理异常: %s", e)

            feishu_bridge.on_message(_on_feishu_message)
            logger.info("飞书消息回调已注册")

            # 启动 WebSocket 长连接（后台线程）
            import threading
            stop_event = threading.Event()
            app.state.feishu_stop_event = stop_event
            feishu_ws_thread = threading.Thread(
                target=feishu_bridge.start_websocket,
                kwargs={"stop_event": stop_event},
                name="feishu-ws",
                daemon=True,
            )
            feishu_ws_thread.start()
            logger.info("飞书 WebSocket 长连接已启动")
        except Exception as exc:
            logger.warning("飞书桥接器启动失败（非阻塞）: %s", exc)

    yield

    # 关闭：飞书 WebSocket 长连接
    if feishu_bridge is not None and hasattr(app.state, "feishu_stop_event"):
        try:
            app.state.feishu_stop_event.set()
            logger.info("飞书 WebSocket 长连接已停止")
        except Exception as exc:
            logger.warning("飞书桥接器停止失败: %s", exc)
    from core.http_client import close_clients
    from core.llm_async import close_llm_client
    await close_llm_client()
    close_clients()
    # 关闭持久化审计日志连接
    try:
        a2a_state = app.state.a2a_state if hasattr(app.state, "a2a_state") else {}
        audit = a2a_state.get("audit")
        if audit and hasattr(audit, "_store") and audit._store is not None:
            audit._store.close()
    except Exception:
        pass
    container.close()


app = FastAPI(
    title="Alpha-ID API",
    description="数字身份智能管理系统 — API 服务",
    version="0.2.0",
    lifespan=lifespan,
)

# 安全头中间件（最外层：所有请求/响应都经过）
# 执行顺序：SecurityHeaders → CorrelationId → RateLimit → CSRF → CORS → Route
app.add_middleware(SecurityHeadersMiddleware)

# CORS - 从统一配置读取
origins = settings.cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流（SecurityHeaders 内层）
# 执行顺序：SecurityHeaders → CorrelationId → RateLimit → CSRF → CORS → Route
app.add_middleware(RateLimitMiddleware)

# CSRF 防护（RateLimit 内层）
# 执行顺序：SecurityHeaders → CorrelationId → CSRF → RateLimit → CORS → Route
# 仅对状态变更方法（POST/PUT/DELETE/PATCH）生效，安全方法直接放行
# 豁免路径：公开 API（无 session 可伪造）、webhook 回调（外部平台无法设置自定义头）
app.add_middleware(
    CSRFMiddleware,
    allowed_origins=set(origins),
    exempt_paths={
        # 注册流程（公开接口，无 session 可伪造）
        "/api/v1/register/send-sms",
        "/api/v1/register/verify-sms",
        "/api/v1/register/face-verify",
        "/api/v1/register/face-query",
        "/api/v1/register/generate-did",
        "/api/v1/register/complete",
        # 身份认证接口（Bearer Token 已防伪造，CSRF 不适用）
        "/api/v1/identity/login",
        "/api/v1/identity/refresh",
        "/api/v1/identity/register",
        "/api/v1/identity/auth/verify",
        # Agent 接口（Gateway 代理调用，Bearer Token 已防伪造）
        "/api/v1/agent/chat",
        "/api/v1/agent/status",
        # A2A 协议接口（服务间调用，不使用 Cookie）
        "/api/v1/a2a/call",
        "/api/v1/a2a/register",
        # 飞书 Webhook（外部平台无法设置自定义头）
        "/webhook/feishu",
    },
    # 前缀匹配：所有以此开头的路径都豁免（更灵活，避免遗漏子路径）
    exempt_prefixes={
        "/api/v1/register/",  # 所有注册相关接口
        "/api/v1/identity/login",
        "/api/v1/identity/refresh",
        "/api/v1/identity/register",
        "/api/v1/identity/auth/",
        # Gateway 代理接口（Gateway 已做 Tenant Auth + Rate Limit，跳过 CSRF 避免重复验证）
        "/api/v1/social/",
        "/api/v1/gdpr/",
        "/api/v1/brain/",
        "/api/v1/voice/",
        "/api/v1/risk/",
        "/api/v1/mindflow/",
    },
    enforce_custom_header=True,
)

app.add_middleware(CorrelationIDMiddleware)

app.include_router(identity_router)
app.include_router(social_router)
app.include_router(risk_router)
app.include_router(dual_chain_router)
app.include_router(observability_router)
app.include_router(registration_router)
app.include_router(agent_router)
app.include_router(a2a_router)
app.include_router(credits_router)
app.include_router(gdpr_router)
app.include_router(voice_router)
app.include_router(mindflow_router)
app.include_router(agent_dispatch_router)
app.include_router(tenant_panel_router)


@app.post("/webhook/feishu")
async def feishu_webhook(request: Request):
    """飞书 Webhook 回调（作为 WebSocket 的备用通道）"""
    try:
        body = await request.json()
        bridge = getattr(request.app.state, "feishu_bridge", None)
        if bridge:
            result = bridge.handle_webhook(body)
            return result
        return {"code": 0, "msg": "ok"}
    except Exception as e:
        logger.error("飞书 Webhook 处理异常: %s", e)
        return {"code": -1, "msg": str(e)}


@app.get("/webhook/feishu/health")
async def feishu_webhook_health(request: Request):
    """飞书桥接器健康检查"""
    bridge = getattr(request.app.state, "feishu_bridge", None)
    if bridge:
        return {
            "status": "ok",
            "bridge": "connected",
            "stats": bridge.get_stats(),
        }
    return {"status": "disconnected", "bridge": "not_initialized"}

# ── 前端页面 ──
_templates_dir = Path(__file__).parent / "alpha_id" / "templates"
_static_dir = _templates_dir
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    """Ghost.html 官网首页"""
    html_path = _templates_dir / "ghost.html"
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/health")
def health(container: Container = Depends(get_container)):
    """真实健康检查：验证关键组件可达性（通过 Container 获取存储后端）"""
    checks = {"status": "ok", "version": settings.app_version, "service": "alpha-id"}

    # 1. 存储后端连通性（只读检查，避免健康检查产生副作用）
    try:
        store = container.storage
        # 仅尝试读取一个已知可能存在的键，验证存储后端可达
        test_key = "__healthcheck__"
        store.load(test_key)
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        checks["status"] = "degraded"

    # 2. 用户身份 API 路由
    try:
        stats = container.identity.get_statistics()
        checks["identity"] = f"ok ({stats.total_users} users)"
    except Exception as e:
        checks["identity"] = f"error: {e}"
        checks["status"] = "degraded"

    # 3. 双链记忆存储
    try:
        from core.dual_chain import DualChainManager
        mgr = DualChainManager("did:aid:healthcheck", storage=container.storage)
        stats = mgr.stats()
        checks["memory"] = f"ok (private={stats.private_count}, knowledge={stats.knowledge_count})"
    except Exception as e:
        checks["memory"] = f"error: {e}"
        checks["status"] = "degraded"

    # 4. A2A 协议状态
    try:
        a2a_state = getattr(app.state, "a2a_state", None)
        if a2a_state:
            checks["a2a"] = {
                "did": a2a_state.get("did", ""),
                "alpha_id": a2a_state.get("alpha_id", ""),
                "skills": len(a2a_state.get("skills", {}).list_skills()),
                "agents": len(a2a_state.get("registry", {}).list_agents()),
            }
        else:
            checks["a2a"] = "disabled"
    except Exception as e:
        checks["a2a"] = f"error: {e}"
        checks["status"] = "degraded"

    return checks
