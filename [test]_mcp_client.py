"""Proper MCP client test (ASCII safe for Windows cmd)"""
import asyncio
import sys
sys.path.insert(0, 'src')

async def test():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # Start MCP server via stdio
    server_params = StdioServerParameters(
        command=sys.executable,
        args=['src/aid_mcp_server.py'],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List tools
            tools = await session.list_tools()
            print(f"[OK] Connected! Tools ({len(tools.tools)}):")
            for t in tools.tools:
                desc = t.description.split('\n')[0][:80]
                print(f"  - {t.name}: {desc}")

            # Test server info
            try:
                result = await session.call_tool("get_server_info", {})
                print(f"\n[OK] get_server_info:")
                print(f"  {result.content[0].text}")
            except Exception as e:
                print(f"  get_server_info ERROR: {e}")

            # Test identity
            try:
                result = await session.call_tool("get_identity", {})
                print(f"\n[OK] get_identity:")
                print(f"  {result.content[0].text[:500]}")
            except Exception as e:
                print(f"  get_identity ERROR: {e}")

    print("\n=== MCP Server 测试完成 ===")

if __name__ == "__main__":
    asyncio.run(test())
