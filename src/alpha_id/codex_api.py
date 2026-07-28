"""
Alpha-ID Codex API — Codex CLI HTTP 接口
=========================================

将 ghost-main/feishu-bot/codex_api.py 集成到 alpha_id 包：
  - HTTP 接口调用 Codex CLI（atomcode/zcode/codex）
  - API Key 认证
  - CORS 安全
  - Prompt 清理（防命令注入）
  - 多后端支持

用法：
    from alpha_id.codex_api import CodexAPIServer

    server = CodexAPIServer(port=21345)
    server.start()  # 阻塞
    # 或
    result = CodexAPIServer.ask_once("写个爬虫")  # 单次调用

独立运行：
    python -m alpha_id.codex_api --port 21345
"""

import json
import os
import re
import subprocess
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 安全：prompt 输入校验
# ══════════════════════════════════════════════════════════════

_FORBIDDEN_CHARS = re.compile(r'[;&|`$(){}[\]<>!\\]')
_MAX_PROMPT_LENGTH = 4096


def _sanitize_prompt(prompt: str) -> str:
    """清理用户输入的 prompt，防止命令注入"""
    if not prompt or not prompt.strip():
        raise ValueError("Prompt 不能为空")
    if len(prompt) > _MAX_PROMPT_LENGTH:
        raise ValueError(f"Prompt 超长（最大 {_MAX_PROMPT_LENGTH} 字符）")
    return _FORBIDDEN_CHARS.sub("", prompt).strip()


# ══════════════════════════════════════════════════════════════
# 后端配置
# ══════════════════════════════════════════════════════════════

BACKEND_CONFIG = {
    "atomcode": {
        "cmd": "atomcode",
        "args": ["-p", "{prompt}", "-y", "--provider", "AtomGit-deepseek-v4-flash"],
    },
    "codex": {
        "cmd": "codex",
        "args": ["-p", "{prompt}"],
    },
}


# ══════════════════════════════════════════════════════════════
# Codex API 服务器
# ══════════════════════════════════════════════════════════════

class CodexAPIServer:
    """
    Codex CLI HTTP 接口服务器

    用法：
        server = CodexAPIServer(port=21345)
        server.start()

    单次调用：
        result = CodexAPIServer.ask_once("写个爬虫")
    """

    def __init__(self, port: int = 21345, host: str = "127.0.0.1",
                 api_key: str = "", cors_origin: str = "http://localhost:21345",
                 backend: str = "atomcode", work_dir: str = ""):
        self._port = port
        self._host = host
        self._api_key = api_key
        self._cors_origin = cors_origin
        self._backend = backend
        self._work_dir = work_dir or os.getcwd()
        self._server = None

    def start(self):
        """启动 HTTP 服务（阻塞）"""
        handler = self._make_handler()
        self._server = ThreadedHTTPServer((self._host, self._port), handler)
        print(f"Codex API → http://{self._host}:{self._port}")
        print(f"  POST /ask   {{\"prompt\":\"...\"}}")
        print(f"  GET  /health")
        self._server.serve_forever()

    def stop(self):
        """停止服务"""
        if self._server:
            self._server.shutdown()

    def _make_handler(self):
        """创建请求处理器（绑定实例变量）"""
        api_key = self._api_key
        cors_origin = self._cors_origin
        work_dir = self._work_dir
        backend = self._backend

        class Handler(BaseHTTPRequestHandler):
            def _check_auth(self) -> bool:
                if not api_key:
                    return True
                provided = self.headers.get("X-API-Key", "")
                return provided == api_key

            def do_OPTIONS(self):
                self.send_response(200)
                self._cors()
                self.end_headers()

            def do_GET(self):
                if self.path == "/health":
                    self._json(200, {"status": "ok", "pid": os.getpid()})
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self):
                if not self._check_auth():
                    self._json(401, {"error": "Unauthorized"})
                    return
                if self.path == "/ask":
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length))
                    raw_prompt = body.get("prompt", "")
                    if not raw_prompt:
                        self._json(400, {"error": "prompt required"})
                        return
                    try:
                        prompt = _sanitize_prompt(raw_prompt)
                    except ValueError as e:
                        self._json(400, {"error": str(e)})
                        return

                    result = self._run_codex(prompt)
                    self._json(200, {"result": result})
                else:
                    self._json(404, {"error": "not found"})

            def _run_codex(self, prompt: str) -> str:
                """执行 Codex CLI"""
                cfg = BACKEND_CONFIG.get(backend, BACKEND_CONFIG["atomcode"])
                cmd = cfg["cmd"]
                args = [a.replace("{prompt}", prompt) for a in cfg["args"]]

                try:
                    r = subprocess.run(
                        [cmd, *args],
                        capture_output=True, timeout=180, cwd=work_dir,
                    )
                    out = r.stdout.decode('utf-8', errors='replace').strip()
                    if r.returncode != 0:
                        out = f"错误: {r.stderr.decode('utf-8', errors='replace')[:200]}"
                    return out
                except subprocess.TimeoutExpired:
                    return "超时（180秒）"
                except FileNotFoundError:
                    return f"找不到 {cmd}，请确认已安装"
                except Exception as e:
                    return f"异常: {str(e)[:200]}"

            def _json(self, status, data):
                self.send_response(status)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")

            def log_message(self, fmt, *args):
                pass

        return Handler

    @staticmethod
    def ask_once(prompt: str, backend: str = "atomcode",
                 work_dir: str = "", timeout: int = 180) -> str:
        """
        单次调用 Codex CLI（不启动 HTTP 服务）

        Args:
            prompt: 编程需求
            backend: 后端名称（atomcode / codex）
            work_dir: 工作目录
            timeout: 超时秒数

        Returns:
            执行结果
        """
        try:
            prompt = _sanitize_prompt(prompt)
        except ValueError as e:
            return f"❌ {e}"

        cfg = BACKEND_CONFIG.get(backend, BACKEND_CONFIG["atomcode"])
        cmd = cfg["cmd"]
        args = [a.replace("{prompt}", prompt) for a in cfg["args"]]

        try:
            r = subprocess.run(
                [cmd, *args],
                capture_output=True, timeout=timeout, cwd=work_dir or os.getcwd(),
            )
            out = r.stdout.decode('utf-8', errors='replace').strip()
            if r.returncode != 0:
                out = f"错误: {r.stderr.decode('utf-8', errors='replace')[:200]}"
            return out
        except subprocess.TimeoutExpired:
            return f"超时（{timeout}秒）"
        except FileNotFoundError:
            return f"找不到 {cmd}，请确认已安装"
        except Exception as e:
            return f"异常: {str(e)[:200]}"


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """支持多线程的 HTTP 服务器"""
    allow_reuse_address = True


# ══════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════

def main():
    """独立运行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Alpha-ID Codex API")
    parser.add_argument("--port", type=int, default=21345, help="服务端口")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--backend", default="atomcode", choices=["atomcode", "codex"],
                        help="后端引擎")
    parser.add_argument("--work-dir", default="", help="工作目录")
    args = parser.parse_args()

    server = CodexAPIServer(
        port=args.port,
        host=args.host,
        backend=args.backend,
        work_dir=args.work_dir,
    )
    server.start()


if __name__ == "__main__":
    main()
