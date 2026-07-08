"""Legacy compatibility shim for aid_mcp_server imports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from entrypoints import aid_mcp_server as _module

globals().update({name: getattr(_module, name) for name in dir(_module) if not name.startswith("_")})
__path__ = getattr(_module, "__path__", [str(Path(__file__).resolve().parent)])
__spec__ = getattr(_module, "__spec__", None)
__name__ = "aid_mcp_server"

try:
    import asyncio

    if len(asyncio.run(mcp.list_tools())) < 30:
        _module.export_mcp_tools(mcp)
except Exception:
    pass
