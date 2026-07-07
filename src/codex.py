"""
AID Codex — 代码理解 / 编辑 / 生成工具
通过 MCP 暴露为可调用的工具，FairyBrain 可以直接理解自然语言代码需求。
"""

import os
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent


def safe_path(path: str) -> Path:
    """安全解析路径，防止目录遍历"""
    p = Path(path).resolve()
    if not str(p).startswith(str(WORKSPACE.resolve())):
        raise PermissionError(f"Access denied: {path}")
    return p


def read_code(path: str, line_start: int = 1, line_end: int = 0) -> str:
    """读取代码文件，支持行范围"""
    p = safe_path(path)
    if not p.is_file():
        return f"[Error] File not found: {path}"
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    if line_end <= 0 or line_end > total:
        line_end = total
    if line_start < 1:
        line_start = 1
    snippet = lines[line_start - 1 : line_end]
    result = "\n".join(f"{i + line_start:4d}| {line}" for i, line in enumerate(snippet))
    return f"{path} ({total} lines)\n{result}"


def search_code(pattern: str, path: str = "") -> str:
    """在代码库中搜索文本或正则"""
    search_root = safe_path(path) if path else WORKSPACE
    if not search_root.is_dir():
        return f"[Error] Not a directory: {path}"
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"[Error] Invalid regex: {e}"
    results = []
    for fpath in search_root.rglob("*.py"):
        if ".venv" in str(fpath) or "__pycache__" in str(fpath):
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if compiled.search(line):
                results.append(f"{fpath.relative_to(WORKSPACE)}:{i}")
                break
        if len(results) >= 20:
            break
    if results:
        return f"Found {len(results)} file(s):\n" + "\n".join(results)
    return "No matches found."


def edit_code(path: str, old_string: str, new_string: str) -> str:
    """替换文件中的文本（类似 sed）"""
    p = safe_path(path)
    if not p.is_file():
        return f"[Error] File not found: {path}"
    content = p.read_text(encoding="utf-8", errors="replace")
    if old_string not in content:
        return f"[Error] String not found in {path}"
    count = content.count(old_string)
    content = content.replace(old_string, new_string, 1)
    p.write_text(content, encoding="utf-8")
    return f"[OK] Replaced 1 occurrence in {path} ({count} total)"


def run_python(code: str) -> str:
    """在隔离环境中执行 Python 代码片段"""
    import tempfile

    # 方案 A: subprocess + capture_output (Linux/macOS 首选)
    for attempt in range(2):
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(WORKSPACE),
            )
            out = result.stdout.strip()
            err = result.stderr.strip()
            if err:
                return f"STDERR:\n{err}" + (f"\n\nSTDOUT:\n{out}" if out else "")
            return out or "(no output)"
        except subprocess.TimeoutExpired:
            return "[Error] Execution timed out"
        except OSError:
            break

    # 方案 B: 临时文件 + shell 重定向（Windows 管道不可用时）
    tmpdir = tempfile.mkdtemp(prefix="codex_")
    script_path = os.path.join(tmpdir, "script.py")
    stdout_path = os.path.join(tmpdir, "stdout.txt")
    stderr_path = os.path.join(tmpdir, "stderr.txt")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        ret = os.system(f'"{sys.executable}" "{script_path}" > "{stdout_path}" 2> "{stderr_path}"')
        if ret < 0:
            return f"[Error] Process killed by signal {-ret}"
        out = open(stdout_path, encoding="utf-8").read().strip()
        err = open(stderr_path, encoding="utf-8").read().strip()
        if err:
            return f"STDERR:\n{err}" + (f"\n\nSTDOUT:\n{out}" if out else "")
        return out or "(no output)"
    except Exception as e:
        return f"[Error] {e}"
    finally:
        try:
            os.unlink(script_path)
            os.unlink(stdout_path)
            os.unlink(stderr_path)
            os.rmdir(tmpdir)
        except OSError:
            pass


def list_files(path: str = ".", pattern: str = "*.py") -> str:
    """列出目录中的文件"""
    p = safe_path(path)
    if not p.is_dir():
        return f"[Error] Not a directory: {path}"
    files = sorted(p.rglob(pattern))
    files = [f for f in files if ".venv" not in str(f) and "__pycache__" not in str(f)]
    if not files:
        return f"No files matching '{pattern}' in {path}"
    lines = [str(f.relative_to(WORKSPACE)) for f in files[:50]]
    if len(files) > 50:
        lines.append(f"... and {len(files) - 50} more")
    return "\n".join(lines)


def count_loc(path: str = ".") -> str:
    """统计 Python 代码行数"""
    p = safe_path(path)
    total = 0
    file_counts = []
    for f in sorted(p.rglob("*.py")):
        if ".venv" in str(f) or "__pycache__" in str(f):
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))
            total += code_lines
            file_counts.append(f"{code_lines:5d}  {f.relative_to(WORKSPACE)}")
        except Exception:
            pass
    return f"Total: {total} lines of Python code\n" + "\n".join(file_counts[:30])


class Codex:
    """代码工具箱"""

    def __init__(self, workspace: str = ""):
        global WORKSPACE
        if workspace:
            WORKSPACE = Path(workspace).resolve()

    @property
    def tools(self):
        return {
            "read_code": {
                "description": "Read code file with line numbers. Args: path, line_start=1, line_end=0(end)",
                "fn": lambda path, line_start=1, line_end=0: read_code(path, line_start, line_end),
            },
            "search_code": {
                "description": "Search codebase with regex. Args: pattern, path",
                "fn": lambda pattern, path="": search_code(pattern, path),
            },
            "edit_code": {
                "description": "Find and replace text in file. Args: path, old_string, new_string",
                "fn": lambda path, old_string, new_string: edit_code(path, old_string, new_string),
            },
            "run_python": {
                "description": "Execute Python code snippet. Args: code",
                "fn": lambda code: run_python(code),
            },
            "list_files": {
                "description": "List files. Args: path=., pattern=*.py",
                "fn": lambda path=".", pattern="*.py": list_files(path, pattern),
            },
            "count_loc": {
                "description": "Count lines of Python code. Args: path=.",
                "fn": lambda path=".": count_loc(path),
            },
        }


if __name__ == "__main__":
    c = Codex()
    print(f"Codex loaded — {len(c.tools)} tools")
    for name, tool in c.tools.items():
        print(f"  - {name}: {tool['description'][:60]}")
