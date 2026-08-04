"""
PostToolUse: 编辑后自动 ruff 格式化 + lint 检查
"""
import subprocess
import sys

PROJECT = r"D:\MW\alphaid\projects"

def main():
    # ruff format
    r1 = subprocess.run(
        ["python", "-m", "ruff", "format", "src/", "tests/", "--quiet"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )
    # ruff check + fix
    r2 = subprocess.run(
        ["python", "-m", "ruff", "check", "src/", "--fix", "--quiet"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )
    if r1.returncode != 0 or r2.returncode != 0:
        print(r1.stderr or r2.stderr)
    return r1.returncode or r2.returncode

if __name__ == "__main__":
    sys.exit(main())
