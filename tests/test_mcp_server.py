"""测试 MCP Server 能正常响应 JSON-RPC 请求"""

import asyncio
import json
import sys

sys.path.insert(0, "src")

import pytest
from aid_mcp_server import mcp

pytestmark = pytest.mark.asyncio


async def test_list_tools():
    """测试 tools/list 请求"""
    result = await mcp.list_tools()
    tool_names = [t.name for t in result]
    print(f"[OK] tools/list: {len(tool_names)} tools")
    assert "capture_full_screen" in tool_names, "缺少 capture_full_screen"
    assert "ocr_image" in tool_names, "缺少 ocr_image"
    assert "click_screen" in tool_names, "缺少 click_screen"
    assert "get_identity" in tool_names, "缺少 get_identity"
    print("所有核心工具都存在 [OK]")
    return tool_names


async def test_get_server_info():
    """测试 get_server_info 工具描述"""
    result = await mcp.list_tools()
    for t in result:
        if t.name == "get_server_info":
            print(f"[OK] get_server_info 描述存在: {len(t.description)} 字符")
            assert t.description, "描述不能为空"
            return
    print("[WARN] get_server_info 未找到")


async def main():
    print("=" * 40)
    print("AID MCP Server 测试")
    print("=" * 40)

    tools = await test_list_tools()
    await test_get_server_info()

    print("")
    print("=" * 40)
    print(f"全部测试通过 [OK] ({len(tools)} tools)")
    print("=" * 40)


if __name__ == "__main__":
    asyncio.run(main())
