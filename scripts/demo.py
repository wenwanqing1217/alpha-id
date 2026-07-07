"""Alpha-ID 一键演示脚本（面试/展示用）"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_PATH = ROOT / "sample_data"


def run(cmd: list[str]) -> None:
    print(">>", " ".join(cmd))
    subprocess.run(cmd, check=True)


def ensure_demo_profile() -> None:
    profile_dir = Path.home() / ".alpha-id" / "profile" / "v0.1"
    if (profile_dir / "identity.yaml").exists():
        return
    run([sys.executable, "-m", "alpha_id.cli", "init"])
    run([sys.executable, "-m", "alpha_id.cli", "profile", "mine", "--path", str(SCAN_PATH)])


def main() -> int:
    if not SCAN_PATH.exists():
        print(f"演示数据不存在: {SCAN_PATH}")
        return 1

    ensure_demo_profile()
    run([sys.executable, "-m", "alpha_id.cli", "profile", "show"])

    print("\n可选：启动 Web 个人空间")
    print("  python -m alpha_id.cli web --host 127.0.0.1 --port 8080")
    print("\n可选：启动 MCP Server")
    print("  python -m alpha_id.cli serve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
