"""Agent 连接器 — 发现 + 验证 + 握手"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import typer

from alpha_id.did import DIDRegistry

logger = logging.getLogger(__name__)
app = typer.Typer(help="Agent 连接管理")

MCP_SSE_PORT = 8100


@app.command("scan")
def cmd_scan(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="扫描目标 IP"),
    port_range: str = typer.Option("8100-8105", "--ports", "-p", help="端口范围"),
):
    """扫描局域网内的 AID Agent"""
    start_port, end_port = (int(x) for x in port_range.split("-"))
    ports = range(start_port, end_port + 1)
    found = []

    typer.echo(f"[扫描] {host}:{port_range} ...")

    def try_port(port):
        url = f"http://{host}:{port}/message"
        try:
            r = httpx.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                      "params": {"uri": "profile://identity"}},
                timeout=2,
            )
            if r.status_code == 200:
                data = r.json()
                did = data.get("result", {}).get("did", "?") if isinstance(data, dict) else "?"
                return (port, did, url)
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(try_port, p): p for p in ports}
        for f in as_completed(futures, timeout=5):
            result = f.result()
            if result:
                found.append(result)
                port, did, url = result
                typer.echo(f"  [发现] Agent: {did[:30]}... → {url}")

    if not found:
        typer.echo("  (无发现)")
    typer.echo(f"[结果] 发现 {len(found)} 个 Agent")


@app.command("handshake")
def cmd_handshake(
    target: str = typer.Argument(..., help="目标 Agent URL"),
    did: str = typer.Argument(..., help="目标 Agent 的 DID"),
):
    """与远端 Agent 互相验证身份（双向握手）"""
    url = target.rstrip("/")

    typer.echo(f"[握手] → {did[:30]}...")

    # 我的身份
    me = DIDRegistry()
    me_did = me.generate()

    # 1. 生成挑战
    challenge = f"handshake:{me_did}:{id(me)}"

    # 2. 请求远端签名
    try:
        r = httpx.post(
            f"{url}/message",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "verify_identity",
                "arguments": {"did": did, "message": challenge, "signature_hex": ""},
            }},
            timeout=10,
        )
        if r.status_code == 200:
            typer.echo(f"  [验证] 远端响应: {r.text[:200]}")
            typer.echo("[握手] ✅ 完成")
        else:
            typer.echo(f"  [失败] HTTP {r.status_code}")
    except Exception as e:
        typer.echo(f"  [错误] {e}")
