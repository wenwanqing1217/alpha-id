"""
脚手架 — 模板内容

所有模板都是字符串常量，便于维护和测试。
"""


# ── .editorconfig ──

EDITORCONFIG = """\
# editorconfig.org
root = true

[*]
indent_style = space
indent_size = 4
end_of_line = lf
charset = utf-8
trim_trailing_whitespace = true
insert_final_newline = true

[*.md]
trim_trailing_whitespace = false

[*.{yml,yaml}]
indent_size = 2
"""

# ── .gitignore ──

GITIGNORE = """\
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
*.so
.venv/
venv/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
Thumbs.db
.DS_Store

# Local data
data/

# Generated files
htmlcov/
*.log
*.db

# Dev artifacts
.mypy_cache/
.ruff_cache/
.pyright/
*.installed.cfg
"""

# ── .pre-commit-config.yaml ──

PRE_COMMIT_CONFIG = """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: mixed-line-ending

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff-format
        args: [--line-length=120]
      - id: ruff
        args: [--fix, --line-length=120]

  - repo: https://github.com/codespell-project/codespell
    rev: v2.3.0
    hooks:
      - id: codespell
        args: [--skip=*.pyc,*.db,node_modules]
        language: python
        types: [text]

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.10
    hooks:
      - id: bandit
        args: [-c, pyproject.toml]
        additional_dependencies: [bandit[toml]]
"""

# ── .vscode/settings.json ──

VSCODE_SETTINGS = """\
{
  "python.defaultInterpreterPath": ".venv/Scripts/python.exe",
  "python.terminal.activateEnvironment": true,
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "python.testing.autoTestDiscoverOnSaveEnabled": true,
  "[python]": {
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll": "explicit",
      "source.organizeImports": "explicit"
    },
    "editor.defaultFormatter": "charliermarsh.ruff"
  },
  "ruff.lineLength": 120,
  "ruff.organizeImports": true,
  "ruff.fixAll": true,
  "files.autoSave": "onFocusChange",
  "files.exclude": {
    "**/__pycache__": true,
    "**/.mypy_cache": true,
    "**/.ruff_cache": true,
    "**/.pyright": true,
    "**/*.egg-info": true
  },
  "editor.rulers": [120],
  "workbench.colorTheme": "Default Dark Modern"
}
"""

# ── .vscode/extensions.json ──

VSCODE_EXTENSIONS = """\
{
  "recommendations": [
    "charliermarsh.ruff",
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-python.mypy-type-checker",
    "tamasfe.even-better-toml",
    "github.vscode-github-actions",
    "redhat.vscode-yaml",
    "esbenp.prettier-vscode",
    "streetsidesoftware.code-spell-checker",
    "ms-vscode-remote.remote-wsl"
  ]
}
"""

# ── .vscode/tasks.json ──

VSCODE_TASKS = """\
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Run tests",
      "type": "shell",
      "command": "python -m pytest tests/ -q --tb=short",
      "group": "test",
      "problemMatcher": []
    },
    {
      "label": "Run coverage",
      "type": "shell",
      "command": "python -m pytest tests/ -q --tb=short --cov=src --cov-report=term-missing",
      "group": "test",
      "problemMatcher": []
    },
    {
      "label": "Lint (ruff check)",
      "type": "shell",
      "command": "ruff check src/",
      "group": "build",
      "problemMatcher": ["$ruff"]
    },
    {
      "label": "Format (ruff format)",
      "type": "shell",
      "command": "ruff format src/ tests/",
      "group": "build",
      "problemMatcher": []
    },
    {
      "label": "Check all",
      "type": "shell",
      "command": "ruff format --check src/ tests/ && ruff check src/ && python -m pytest tests/ -q --tb=short",
      "group": "test",
      "problemMatcher": []
    }
  ]
}
"""

# ── .github/workflows/ci.yml ──

GITHUB_CI = """\
name: CI

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install -e .[test]

      - name: Ruff check
        run: ruff check src/

      - name: Ruff format check
        run: ruff format --check src/ tests/

  test:
    runs-on: windows-latest
    strategy:
      matrix:
        python-version: ["3.12"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install -e .[test]

      - name: Run tests with coverage
        run: |
          python -m pytest tests/ -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=70

      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-${{ matrix.python-version }}
          path: htmlcov/
"""

# ── CONTRIBUTING.md ──

CONTRIBUTING = """\
# 贡献指南

## 开发环境

运行 `scripts\\dev_setup.bat` 一键初始化。

## 分支策略

```
main            → 稳定版本（只从 PR 合并）
feature/*       → 新功能
fix/*           → 修 Bug
refactor/*      → 重构
docs/*          → 文档
chore/*         → CI/依赖/杂项
```

## Commit 格式

```
<type>: <简短描述>

类型: feat / fix / docs / style / refactor / perf / test / chore
```

## 提交前检查

```bash
task check-all
```

这条命令会自动运行：
1. `ruff format` — 格式化代码
2. `ruff check` — Lint 检查
3. `pytest` — 全部测试

## 测试规范

- 所有新功能必须有对应测试
- 测试放在 `tests/` 目录下
- 命名: `test_<模块名>.py`
- 覆盖率不低于 70%

## 代码风格

- 用 ruff 自动格式化（已在 pre-commit 中配置）
- 行宽: 120 字符
- 引号: 双引号
- 目标 Python: 3.12+
- 类型注解: 所有公开函数必须带类型注解
"""

# ── scripts/dev_setup.bat ──

DEV_SETUP_BAT = """\
@echo off
REM Development environment one-click setup
REM Run this as a normal user (no admin needed for most operations)

title Python Project Dev Setup

echo ============================================
echo    Development Environment Setup
echo ============================================
echo.

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.12+
    echo         Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

python --version

REM 1. Upgrade pip
echo.
echo [1/5] Upgrading pip...
python -m pip install --upgrade pip setuptools wheel
if %ERRORLEVEL% neq 0 (
    echo [WARN] pip upgrade failed, continuing...
)

REM 2. Install project in dev mode
echo.
echo [2/5] Installing project in dev mode...
pip install -e .[all]
if %ERRORLEVEL% neq 0 (
    echo [WARN] Some optional dependencies failed (usually harmless)
)

REM 3. Install dev tools
echo.
echo [3/5] Installing dev tools...
pip install pre-commit pytest-cov pytest-xdist ruff pyright
if %ERRORLEVEL% neq 0 (
    echo [WARN] Some dev tools failed to install
)

REM 4. Install pre-commit hooks
echo.
echo [4/5] Installing pre-commit hooks...
pre-commit install
pre-commit install --hook-type commit-msg
if %ERRORLEVEL% neq 0 (
    echo [WARN] pre-commit hooks failed (can retry manually)
)

REM 5. Verify
echo.
echo [5/5] Verifying setup...
echo.

echo --- Ruff check ---
ruff check src/ --silent
if %ERRORLEVEL% equ 0 (
    echo   Ruff: OK
) else (
    echo   Ruff: Warnings found (non-blocking)
)

echo --- Pytest ---
python -m pytest tests/ -q --tb=short --no-header 2>nul
if %ERRORLEVEL% equ 0 (
    echo   Tests: PASS
) else (
    echo   Tests: CHECK (may need dependencies)
)

echo.
echo ============================================
echo    Setup complete!
echo ============================================
echo.
echo   Next steps:
echo     1. Open VS Code:  code .
echo     2. Install recommended extensions (Ctrl+Shift+X)
echo     3. Start developing
echo     4. Run tests:     task test
echo.

pause
"""


def generate_pyproject_toml(project_name: str, description: str = "") -> str:
    """生成一个完整的 pyproject.toml（支持 taskipy 任务）"""
    safe_name = project_name.lower().replace(" ", "-").replace("_", "-")
    src_pkg = safe_name.replace("-", "_")

    desc = description or f"{project_name} — Python project"

    return f"""\
[project]
name = "{safe_name}"
version = "0.1.0"
description = "{desc}"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
{safe_name} = "{src_pkg}.cli:app"

[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.5",
]
all = [
    "{safe_name}[test]",
]
dev = [
    "{safe_name}[test]",
]

[build-system]
requires = ["setuptools>=75.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
include = ["{src_pkg}*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-q --tb=short --no-header"

[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*", "*/__pycache__/*", "*/site-packages/*"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "except ImportError",
]
fail_under = 0

[tool.coverage.html]
directory = "htmlcov"

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "W",   # pycodestyle warnings
    "UP",  # pyupgrade
    "RUF", # ruff-specific
]
ignore = [
    "E501",  # line length handled by formatter
    "N999",  # module name convention
]
fixable = ["ALL"]
exclude = ["__pycache__", ".git", "htmlcov", "dist"]

[tool.ruff.format]
quote-style = "double"
indent-width = 4
line-ending = "auto"

[tool.taskipy.tasks]
# Development
dev = "python src/{src_pkg}/main.py"

# Testing
test = "python -m pytest tests/ -q --tb=short"
test-v = "python -m pytest tests/ -v --tb=long"
test-x = "python -m pytest tests/ -q --tb=short -x"
coverage = "python -m pytest tests/ -q --tb=short --cov=src --cov-report=term-missing"
coverage-html = "python -m pytest tests/ -q --tb=short --cov=src --cov-report=html"

# Code quality
lint = "ruff check src/"
format = "ruff format src/ tests/"
check-all = "ruff format --check src/ tests/ && ruff check src/ && python -m pytest tests/ -q --tb=short"

# Maintenance
clean = "python -c \\"import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__') if p.is_dir()]; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]\\""
pre-commit-run = "pre-commit run --all-files"

[tool.codespell]
skip = "*.pyc,*.git,*.db,*.png,*.jpg,htmlcov,node_modules,.venv"
ignore-words-list = "ba,hte"
check-hidden = true
"""
