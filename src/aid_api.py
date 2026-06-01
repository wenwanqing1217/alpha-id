"""aid-api CLI 入口 — 启动 Alpha-ID Web 演示服务"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="AID Web API — 身份/社交/大脑控制 REST 服务"
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0）"
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="监听端口（默认 8000）",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="热重载（开发用）",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version="AID Web API v0.1.0",
    )
    args = parser.parse_args()

    # 确保 stdout 支持 UTF-8（Windows 兼容）
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # 延迟导入 uvicorn + app，避免启动前加载全部依赖
    import uvicorn

    from alpha_id.web import app

    print(f"🚀 AID Web API 启动 → http://{args.host}:{args.port}")
    print(f"   📄 主页: http://localhost:{args.port}/")
    print(f"   🔑 登录: POST /login")
    print(f"   💬 聊天: POST /chat")
    print(f"   🧠 大脑: GET  /brain/status")
    print()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info" if args.reload else "warning",
    )


if __name__ == "__main__":
    main()
