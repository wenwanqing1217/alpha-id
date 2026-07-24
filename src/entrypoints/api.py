"""aid-api CLI 入口 — 启动 Alpha-ID Web 演示服务

运行方式：
    python -m entrypoints.api
    或安装后：aid-api
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="AID Web API — 身份/社交/大脑控制 REST 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
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
        "--demo",
        action="store_true",
        help="启动 Ghost 官网演示（默认启动完整 API 服务）",
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

    import uvicorn

    if args.demo:
        # Ghost 官网演示（纯前端 SPA，无后端依赖）
        from alpha_id.web import app as demo_app

        print(f"Ghost 演示启动 -> http://{args.host}:{args.port}")
        print("   主页: GET /  (Ghost 官网)")
        print()
        run_app = demo_app
    else:
        # 完整 API 服务（含身份/社交/大脑等端点）
        from src.main import app as api_app

        print(f"AID Web API 启动 -> http://{args.host}:{args.port}")
        print("   主页: GET /")
        print("   聊天: POST /chat")
        print("   大脑: GET /brain/status")
        print("   健康: GET /health")
        print()
        run_app = api_app

    uvicorn.run(
        run_app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info" if args.reload else "warning",
    )


if __name__ == "__main__":
    main()
