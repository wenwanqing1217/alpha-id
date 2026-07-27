"""Alpha-ID API 服务入口

运行方式：
    python -m src.main
    或安装后：aid-api
"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# 安装敏感数据日志过滤器（在所有日志输出前脱敏）
from core.logging_filter import install_sensitive_data_filter
install_sensitive_data_filter()

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

# 加载 .env 文件（必须在读取环境变量之前）
load_dotenv()

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from alpha_id.container import Container, get_container  # noqa: E402
from auth.jwt import validate_master_key  # noqa: E402
from auth.csrf import CSRFMiddleware  # noqa: E402
from core.middleware import CorrelationIDMiddleware  # noqa: E402
from core.rate_limit import RateLimitMiddleware  # noqa: E402
from core.settings import settings  # noqa: E402

# Support both package-style imports (`src.main`) and direct module imports (`main`).
if __package__:
    from .api.identity import router as identity_router
    from .api.risk import router as risk_router
    from .api.social import router as social_router
    from .api.dual_chain import router as dual_chain_router
    from .api.registration import router as registration_router
    from .api.observability import router as observability_router
    from .api.agent import router as agent_router
    from .api.gdpr import router as gdpr_router
else:
    from api.identity import router as identity_router
    from api.risk import router as risk_router
    from api.social import router as social_router
    from api.dual_chain import router as dual_chain_router
    from api.registration import router as registration_router
    from api.observability import router as observability_router
    from api.agent import router as agent_router
    from api.gdpr import router as gdpr_router


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
    # 启动：容器初始化 + 注入 app.state（FastAPI DI）
    container = Container.instance()
    app.state.container = container

    # 启动：A2A 服务器（后台线程，端口 9001）
    a2a_thread = None
    if settings.a2a_enabled:
        try:
            from core.a2a import A2AServer, SkillRegistry, A2ASigner
            from alpha_id.did import DIDRegistry

            # 构建技能注册表
            skills = SkillRegistry()

            # 注册示例技能
            @skills.skill("ping", description="健康检查")
            def _ping(params):
                return {"status": "ok", "agent": settings.app_name}

            @skills.skill("echo", description="回显参数")
            def _echo(params):
                return params

            # 签名器（从 DID 派生）
            did_reg = DIDRegistry()
            signer = None
            did = None
            if container.identity and hasattr(container.identity, "_did_registry"):
                did_reg = container.identity._did_registry
                if did_reg and did_reg.public_key:
                    did = did_reg.did
                    signer = A2ASigner(public_key_hex=did_reg.public_key.hex())

            a2a_server = A2AServer(
                skills=skills,
                signer=signer,
                did=did or "",
                alpha_id=settings.app_name,
                port=settings.a2a_port,
            )
            a2a_thread = a2a_server.start(blocking=False)
            logger.info("A2A 服务器已启动 (端口 %d)", settings.a2a_port)
        except Exception as exc:
            logger.warning("A2A 服务器启动失败（非阻塞）: %s", exc)

    yield

    # 关闭：释放资源（HTTP 客户端、LLM 客户端、容器）
    from core.http_client import close_clients
    from core.llm_async import close_llm_client
    await close_llm_client()
    close_clients()
    container.close()


app = FastAPI(
    title="Alpha-ID API",
    description="数字身份智能管理系统 — API 服务",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS - 从统一配置读取
origins = settings.cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流（CORS 内层，CorrelationID 外层）
# 执行顺序：CorrelationId → RateLimit → CORS → Route
app.add_middleware(RateLimitMiddleware)

# CSRF 防护（RateLimit 内层，CorrelationID 外层）
# 执行顺序：CorrelationId → CSRF → RateLimit → CORS → Route
# 仅对状态变更方法（POST/PUT/DELETE/PATCH）生效，安全方法直接放行
# 豁免路径：公开 API（无 session 可伪造）、webhook 回调（外部平台无法设置自定义头）
_registration_prefix = "/api/v1/register"
_auth_prefix = "/api/v1/identity/auth"
app.add_middleware(
    CSRFMiddleware,
    allowed_origins=set(origins),
    exempt_paths={
        # 注册流程（公开接口）
        f"{_registration_prefix}/send-sms",
        f"{_registration_prefix}/verify-sms",
        f"{_registration_prefix}/face-verify",
        f"{_registration_prefix}/face-query",
        f"{_registration_prefix}/generate-did",
        f"{_registration_prefix}/complete",
        # 身份认证接口（Bearer Token 已防伪造，CSRF 不适用）
        f"{_auth_prefix}/verify",
        f"{_auth_prefix}/login",
        f"{_auth_prefix}/refresh",
        f"{_auth_prefix}/bind-device",
        "/api/v1/identity/register",
    },
    enforce_custom_header=True,
)

app.add_middleware(CorrelationIDMiddleware)

app.include_router(identity_router)
app.include_router(social_router)
app.include_router(risk_router)
app.include_router(dual_chain_router)
app.include_router(registration_router)
app.include_router(observability_router)
app.include_router(agent_router)
app.include_router(gdpr_router)

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

    # 1. 存储后端连通性
    try:
        store = container.storage
        # 简单读写验证
        test_key = "__healthcheck__"
        store.save(test_key, {"ts": __import__("datetime").datetime.now().isoformat()})
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

    return checks
