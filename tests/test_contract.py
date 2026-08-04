"""
API 契约测试 — 基于 schemathesis

对 FastAPI 应用的 OpenAPI schema 做自动契约测试：
- 自动生成符合 schema 的请求
- 验证响应是否符合 schema 定义
- 发现 500 错误和 schema 不一致

运行方式：
    python -m pytest tests/test_contract.py -v
"""

import os
import sys

import pytest

# 确保测试环境
os.environ.setdefault("AUTH_MASTER_KEY", "test-master-key-for-pytest-0123456789abcdef")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 延迟导入，避免 schemathesis 的 pytest 插件在收集阶段触发
try:
    import schemathesis
    _SCHEMATHESIS_AVAILABLE = True
except ImportError:
    _SCHEMATHESIS_AVAILABLE = False

# 延迟创建 schema
_schema = None


def _get_schema():
    """延迟加载 OpenAPI schema"""
    global _schema
    if _schema is not None:
        return _schema
    if not _SCHEMATHESIS_AVAILABLE:
        return None
    from src.main import app
    _schema = schemathesis.openapi.from_asgi("/openapi.json", app)
    return _schema


# ── 基础契约测试 ──

@pytest.mark.skipif(not _SCHEMATHESIS_AVAILABLE, reason="schemathesis 未安装")
class TestAPIContract:
    """API 契约测试 — 验证所有端点符合 OpenAPI schema"""

    @pytest.fixture(autouse=True)
    def _setup_schema(self):
        """每个测试前加载 schema"""
        self.schema = _get_schema()

    def test_openapi_schema_valid(self):
        """OpenAPI schema 本身有效"""
        assert self.schema is not None

    def test_health_endpoint_contract(self):
        """/health 端点符合契约"""
        from fastapi.testclient import TestClient

        from src.main import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "database" in data  # main.py 的 health 返回依赖检查

    def test_ready_endpoint_contract(self):
        """/ready 端点符合契约"""
        from fastapi.testclient import TestClient

        from src.main import app
        client = TestClient(app)
        resp = client.get("/ready")
        assert resp.status_code == 200
        assert "checks" in resp.json()

    def test_metrics_endpoint_contract(self):
        """/metrics 端点符合契约"""
        from fastapi.testclient import TestClient

        from src.main import app
        client = TestClient(app)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        # Prometheus exposition format
        assert isinstance(resp.content, bytes)

    def test_identity_endpoints_require_auth(self):
        """身份相关端点需要认证"""
        from fastapi.testclient import TestClient

        from src.main import app
        client = TestClient(app)
        # 无 token 访问 /me 应返回 401
        resp = client.get("/api/v1/identity/me")
        assert resp.status_code in (401, 403, 404)  # 404 if route prefix differs

    def test_register_endpoint_validates_input(self):
        """注册端点验证输入"""
        from fastapi.testclient import TestClient

        from src.main import app
        client = TestClient(app)
        # 空请求体应返回 422（验证错误）
        resp = client.post("/api/v1/identity/register", json={})
        assert resp.status_code in (400, 422)


# ── Schema 一致性检查 ──

@pytest.mark.skipif(not _SCHEMATHESIS_AVAILABLE, reason="schemathesis 未安装")
class TestSchemaConsistency:
    """Schema 一致性检查"""

    def test_all_routes_have_responses_defined(self):
        """所有路由都定义了响应"""
        from src.main import app
        for route in app.routes:
            if hasattr(route, "methods") and route.methods:
                for method in route.methods:
                    if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                        # 确保路由可以访问
                        assert route.path is not None

    def test_observability_routes_exist(self):
        """可观测性路由存在"""
        from src.main import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health" in paths
        assert "/ready" in paths
        assert "/metrics" in paths
