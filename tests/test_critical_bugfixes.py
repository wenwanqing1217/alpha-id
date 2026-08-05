"""Tests for critical bugfixes applied during E2E debugging.

Run with:  pytest tests/test_critical_bugfixes.py -v
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from auth.csrf import CSRFMiddleware
from core.storage_postgres import PostgresStorage

# ─────────────────────────────────────────────────────────────────────────────
# 1. storage_postgres: JSONB deserialization
# ─────────────────────────────────────────────────────────────────────────────

class TestStoragePostgresJSONB:
    """psycopg3 returns JSONB as native Python types, not strings."""

    def test_deserialize_string(self):
        """Normal JSON string still works."""
        assert PostgresStorage._deserialize('{"key": "val"}') == {"key": "val"}

    def test_deserialize_dict_passthrough(self):
        """psycopg3 returns dict directly for JSONB."""
        raw = {"key": "val"}
        assert PostgresStorage._deserialize(raw) == raw

    def test_deserialize_int_passthrough(self):
        """Bug: old code called json.loads(int) -> TypeError."""
        raw = 42
        assert PostgresStorage._deserialize(raw) == raw

    def test_deserialize_list_passthrough(self):
        raw = [1, 2, 3]
        assert PostgresStorage._deserialize(raw) == raw

    def test_deserialize_none_returns_none(self):
        assert PostgresStorage._deserialize(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. CSRF: exempt internal paths
# ─────────────────────────────────────────────────────────────────────────────

class TestCSRFExemptPaths:
    """Gateway -> Alpha-ID internal calls must bypass CSRF."""

    @pytest.fixture
    def middleware(self):
        return CSRFMiddleware(
            app=MagicMock(),
            allowed_origins={"http://localhost:18080"},
            exempt_paths={"/api/v1/identity/quick-register", "/api/v1/dual-chain/save"},
        )

    def test_quick_register_exempt(self, middleware):
        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/v1/identity/quick-register"
        request.headers = {}

        async def _call_next(_req):
            return "passed-through"

        result = asyncio.run(middleware.dispatch(request, _call_next))
        assert result == "passed-through"

    def test_dual_chain_save_exempt(self, middleware):
        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/v1/dual-chain/save"
        request.headers = {}

        async def _call_next(_req):
            return "passed-through"

        result = asyncio.run(middleware.dispatch(request, _call_next))
        assert result == "passed-through"


# ─────────────────────────────────────────────────────────────────────────────
# 3. A2A graph endpoint logic
# ─────────────────────────────────────────────────────────────────────────────

class TestA2AGraphLogic:
    """a2a_agent_graph: 优先 AgentGraph 拓扑（主路径），回退 registry + audit 现算。"""

    def test_graph_nodes_from_agentgraph_topology(self):
        """Nodes come from AgentGraph topology (primary path)."""
        from api.a2a import a2a_agent_graph

        mock_graph = MagicMock()
        mock_graph.get_topology.return_value = {
            "nodes": [
                {"id": "did:ghost:1", "label": "Agent-A", "skills": ["ping"]},
                {"id": "did:ghost:2", "label": "Agent-B", "skills": ["echo"]},
            ],
            "edges": [],
        }

        with patch("core.agent_graph.get_agent_graph", return_value=mock_graph):
            result = asyncio.run(a2a_agent_graph(MagicMock()))

        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) == 2
        assert result["nodes"][0]["id"] == "did:ghost:1"
        assert result["nodes"][0]["label"] == "Agent-A"
        assert result["nodes"][1]["id"] == "did:ghost:2"

    def test_graph_edges_from_agentgraph_uses_source_target(self):
        """AgentGraph 主路径的 source/target 需映射为 from/to 兼容旧格式。"""
        from api.a2a import a2a_agent_graph

        mock_graph = MagicMock()
        mock_graph.get_topology.return_value = {
            "nodes": [],
            "edges": [{"source": "did:ghost:1", "target": "did:ghost:2", "skill": "ping"}],
        }

        with patch("core.agent_graph.get_agent_graph", return_value=mock_graph):
            result = asyncio.run(a2a_agent_graph(MagicMock()))

        assert result["edges"][0]["from"] == "did:ghost:1"
        assert result["edges"][0]["to"] == "did:ghost:2"
        assert result["edges"][0]["skill"] == "ping"

    def test_graph_falls_back_to_registry_and_audit(self):
        """AgentGraph 不可用时回退到 registry + audit log 现算（原逻辑保留）。"""
        from api.a2a import a2a_agent_graph

        mock_registry = MagicMock()
        mock_registry.to_payload.return_value = {
            "agents": [
                {"did": "did:ghost:1", "alpha_id": "Agent-A", "skill_list": ["ping"]},
                {"did": "did:ghost:2", "alpha_id": "Agent-B", "skill_list": ["echo"]},
            ]
        }
        mock_audit = MagicMock()
        mock_audit.list_records.return_value = [
            {
                "caller_agent_id": "did:ghost:1",
                "target_agent_id": "did:ghost:2",
                "skill": "ping",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        ]

        mock_state = {"registry": mock_registry, "audit": mock_audit}
        mock_request = MagicMock()
        mock_request.app.state.a2a_state = mock_state

        def _boom(*args, **kwargs):
            raise RuntimeError("graph unavailable")

        with patch("core.agent_graph.get_agent_graph", side_effect=_boom):
            with patch("api.a2a._get_a2a_state", return_value=mock_state):
                with patch("api.a2a._get_registry", return_value=mock_registry):
                    with patch("api.a2a._get_audit", return_value=mock_audit):
                        result = asyncio.run(a2a_agent_graph(mock_request))

        assert len(result["nodes"]) == 2
        assert result["nodes"][0]["id"] == "did:ghost:1"
        assert result["nodes"][0]["label"] == "Agent-A"
        assert len(result["edges"]) == 1
        assert result["edges"][0]["from"] == "did:ghost:1"
        assert result["edges"][0]["to"] == "did:ghost:2"
        assert result["edges"][0]["skill"] == "ping"
