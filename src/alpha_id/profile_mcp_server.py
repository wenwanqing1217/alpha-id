"""
Alpha-ID Profile MCP Server

通过 MCP 协议暴露用户画像，供 Claude Desktop / Cursor 等工具注入。

资源:
  profile://identity          -- 用户身份（DID + Alpha-ID + 画像）
  profile://persona/technical -- 技术偏好

工具:
  get_profile_summary         -- 获取文本版画像摘要

用法:
    aid profile serve             启动 MCP 服务
    aid profile serve --install   自动写入 Claude Desktop 配置
"""

import json
import logging
import os
import sys
from pathlib import Path

from alpha_id.profile_schema import (
    load_profile,
    profile_exists,
    summary,
)

logger = logging.getLogger(__name__)
VERSION = "0.1.0"

try:
from mcp.server import FastMCP

    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def _claude_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", ""))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"
    return base / "Claude" / "claude_desktop_config.json"


def install_claude_config() -> bool:
    """自动写入 Claude Desktop 配置"""
    config_path = _claude_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"command": "aid", "args": ["profile", "serve"]}
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    config.setdefault("mcpServers", {})["alpha-id"] = entry
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


class ProfileMCPServer:
    """Profile MCP Server -- 身份注入接口"""

    def __init__(self):
        self.app = FastMCP("alpha-id-profile") if HAS_MCP else None

    def get_identity(self) -> str:
        """profile://identity -- 用户身份摘要"""
        if not profile_exists():
            return json.dumps({"status": "no_profile"}, ensure_ascii=False)
        profile = load_profile()
        if profile is None:
            return json.dumps({"status": "error"}, ensure_ascii=False)
        info = {"did": profile.did}
        aid = profile.extra.get("alpha_id")
        if aid:
            info["alpha_id"] = aid
        p = profile.persona
        info["persona"] = {
            "tone": p.communication.tone,
            "sentence_length": p.communication.sentence_length,
            "active_hours": p.communication.active_hours,
            "languages": p.technical.primary_languages,
            "coding_style": p.technical.coding_style,
            "work_rhythm": p.temporal.work_rhythm,
        }
        return json.dumps(info, ensure_ascii=False, indent=2)

    def get_technical_persona(self) -> str:
        """profile://persona/technical -- 技术偏好"""
        if not profile_exists():
            return json.dumps({"status": "no_profile"})
        profile = load_profile()
        if profile is None:
            return json.dumps({"status": "error"})
        tech = profile.persona.technical
        return json.dumps(
            {
                "primary_languages": tech.primary_languages,
                "coding_style": tech.coding_style,
            },
            ensure_ascii=False,
            indent=2,
        )

    def get_summary(self) -> str:
        """文本版画像摘要"""
        if not profile_exists():
            return "（暂无 profile 数据）"
        profile = load_profile()
        if profile is None:
            return "（profile 解析失败）"
        return summary(profile)


def main(install: bool = False):
    if install:
        install_claude_config()
        print("[OK] 已写入 Claude Desktop 配置")
        print("  配置路径: %s" % _claude_config_path())
        print("  重启 Claude Desktop 后生效")
        return

    if not HAS_MCP:
        print("[错误] 需要安装 mcp 库: pip install alpha-id-zix[mcp-server]")
        sys.exit(1)

    server = ProfileMCPServer()

    @server.app.resource("profile://identity")
    async def get_identity() -> str:
        return server.get_identity()

    @server.app.resource("profile://persona/technical")
    async def get_tech_persona() -> str:
        return server.get_technical_persona()

    @server.app.tool("get_profile_summary")
    async def get_summary_tool() -> str:
        return server.get_summary()

    @server.app.tool("verify_identity")
    async def verify_identity_tool(did: str, message: str, signature_hex: str) -> str:
        """验证一个 DID 签名的真伪——Agent 间信任的基础"""
        try:
            import sys

            sys.path.insert(0, str(Path(__file__).parent.parent))
            from alpha_id.crypto import verify

            sig = bytes.fromhex(signature_hex)
            # 尝试用常见公钥验证
            result = verify(sig, message.encode(), bytes.fromhex(did[-64:]) if len(did) > 64 else b"")
            return json.dumps({"valid": bool(result), "did": did}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"valid": False, "error": str(e)}, ensure_ascii=False)

    print("[Server] Alpha-ID Profile MCP Server v%s" % VERSION)
    print("    资源: profile://identity | profile://persona/technical")
    print("    工具: get_profile_summary")
    print()
    print("  挂载到 Claude Desktop:")
    print('    { "alpha-id-profile": { "command": "python", "args": ["-m", "alpha_id.profile_mcp_server"] } }')
    print()
    print("等待 MCP 客户端连接...")
    server.app.run()


if __name__ == "__main__":
    main()
