"""多租户面板测试：_owner_or_403 隔离校验、配置读写"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api import tenant_panel as tp


class TestOwnerOr403:
    def _req(self, headers: dict) -> MagicMock:
        req = MagicMock()
        req.headers = headers
        return req

    def test_owner_jwt_sub_matches(self):
        req = self._req({"authorization": "Bearer token"})
        with patch("api.tenant_panel.parse_jwt_or_none", return_value={"sub": "Alpha-001"}):
            tp._owner_or_403(req, "Alpha-001")  # 不抛异常即可

    def test_owner_jwt_alpha_id_matches(self):
        req = self._req({})
        with patch("api.tenant_panel.parse_jwt_or_none", return_value={"alpha_id": "Alpha-007"}):
            tp._owner_or_403(req, "Alpha-007")

    def test_master_role_allowed(self):
        req = self._req({})
        with patch("api.tenant_panel.parse_jwt_or_none", return_value={"role": "master"}):
            tp._owner_or_403(req, "Alpha-999")

    def test_header_fallback_allowed(self):
        req = self._req({"x-alpha-id": "Alpha-042"})
        with patch("api.tenant_panel.parse_jwt_or_none", return_value=None):
            tp._owner_or_403(req, "Alpha-042")

    def test_mismatch_raises_403(self):
        req = self._req({})
        with patch("api.tenant_panel.parse_jwt_or_none", return_value={"sub": "Alpha-001"}):
            with pytest.raises(HTTPException) as ei:
                tp._owner_or_403(req, "Alpha-999")
        assert ei.value.status_code == 403


class TestTenantConfigStorage:
    def test_load_returns_default_when_empty(self):
        c = MagicMock()
        c.storage.kv_get.return_value = None
        cfg = tp._load(c, "Alpha-1")
        assert cfg.alpha_id == "Alpha-1"
        assert cfg.display_name == "Alpha-1"
        assert "agents" in cfg.enabled_tabs

    def test_load_parses_saved_json(self):
        c = MagicMock()
        c.storage.kv_get.return_value = json.dumps({"alpha_id": "Alpha-1", "display_name": "小明"})
        cfg = tp._load(c, "Alpha-1")
        assert cfg.display_name == "小明"

    def test_save_writes_json(self):
        c = MagicMock()
        cfg = tp.TenantConfig(alpha_id="Alpha-1", display_name="小明")
        tp._save(c, cfg)
        saved = c.storage.kv_put.call_args[0]
        assert saved[0] == "tenant_configs"
        assert saved[1] == "Alpha-1"
        # model_dump(mode="json") 直接产出 dict，storage 层负责序列化
        assert saved[2]["display_name"] == "小明"
