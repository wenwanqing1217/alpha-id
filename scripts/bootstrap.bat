@echo off
REM ============================================
REM  AID Bootstrap — 通用 Python 项目脚手架
REM  在任何目录运行，一键生成开发环境
REM ============================================
REM
REM  用法:
REM     bootstrap.bat <项目目录> [项目名称] [描述]
REM
REM  示例:
REM     bootstrap.bat C:\Projects\my-tool
REM     bootstrap.bat . my-project "我的新项目"
REM
REM  你的 python 必须已安装，且是 3.12+
REM ============================================

setlocal enabledelayedexpansion

title AID Bootstrap

if "%1"=="" (
    echo.
    echo [ERROR] 请指定项目目录！
    echo.
    echo 用法: %~nx0 ^<项目目录^> [项目名称] [描述]
    echo.
    echo 示例:
    echo   %~nx0 C:\Projects\my-tool
    echo   %~nx0 . my-project "My awesome project"
    echo.
    pause
    exit /b 1
)

set "PROJECT_DIR=%~f1"
set "PROJECT_NAME=%~2"
set "PROJECT_DESC=%~3"

if "%PROJECT_NAME%"=="" (
    for %%I in ("%PROJECT_DIR%") do set "PROJECT_NAME=%%~nxI"
)

if "%PROJECT_DESC%"=="" set "PROJECT_DESC=%PROJECT_NAME% — Python project"

set "SAFE_NAME=%PROJECT_NAME: =-%"
set "SAFE_NAME=%SAFE_NAME:_=-%"
set "SAFE_NAME=%SAFE_NAME: =-%"
for %%I in ("%SAFE_NAME%") do set "SAFE_NAME_LOWER=%%I"
for /f "usebackq delims=" %%I in (`echo %SAFE_NAME_LOWER%`) do set "SAFE_NAME_LOWER=%%I"

set "SRC_PKG=%SAFE_NAME:-=_%"

echo.
echo ============================================
echo   AID Bootstrap
echo ============================================
echo.
echo   Project: %PROJECT_NAME%
echo   Target:  %PROJECT_DIR%
echo.

REM Create directories
if not exist "%PROJECT_DIR%" mkdir "%PROJECT_DIR%"
if not exist "%PROJECT_DIR%\src\%SRC_PKG%" mkdir "%PROJECT_DIR%\src\%SRC_PKG%"
if not exist "%PROJECT_DIR%\tests" mkdir "%PROJECT_DIR%\tests"
if not exist "%PROJECT_DIR%\.github\workflows" mkdir "%PROJECT_DIR%\.github\workflows"
if not exist "%PROJECT_DIR%\.vscode" mkdir "%PROJECT_DIR%\.vscode"
if not exist "%PROJECT_DIR%\scripts" mkdir "%PROJECT_DIR%\scripts"

REM Create __init__.py files
echo. > "%PROJECT_DIR%\src\%SRC_PKG%\__init__.py"
echo. > "%PROJECT_DIR%\tests\__init__.py"

echo   Directories created.

REM ── .editorconfig ──
(
echo # editorconfig.org
echo root = true
echo.
echo [*]
echo indent_style = space
echo indent_size = 4
echo end_of_line = lf
echo charset = utf-8
echo trim_trailing_whitespace = true
echo insert_final_newline = true
echo.
echo [*.md]
echo trim_trailing_whitespace = false
echo.
echo [*.{yml,yaml}]
echo indent_size = 2
) > "%PROJECT_DIR%\.editorconfig"

REM ── .gitignore ──
(
echo # Python
echo __pycache__/
echo *.py[cod]
echo *.egg-info/
echo dist/
echo build/
echo *.so
echo .venv/
echo venv/
echo.
echo # IDE
echo .vscode/
echo .idea/
echo *.swp
echo *.swo
echo *~
echo.
echo # OS
echo Thumbs.db
echo .DS_Store
echo.
echo # Local data
echo data/
echo.
echo # Generated files
echo htmlcov/
echo *.log
echo *.db
echo.
echo # Dev artifacts
echo .mypy_cache/
echo .ruff_cache/
echo .pyright/
echo *.installed.cfg
) > "%PROJECT_DIR%\.gitignore"

REM ── pyproject.toml ──
(
echo [project]
echo name = "%SAFE_NAME_LOWER%"
echo version = "0.1.0"
echo description = "%PROJECT_DESC%"
echo requires-python = ">=3.12"
echo dependencies = []
echo.
echo [project.scripts]
echo %SAFE_NAME_LOWER% = "%SRC_PKG%.cli:app"
echo.
echo [project.optional-dependencies]
echo test = [
echo     "pytest>=8.0",
echo     "pytest-cov>=5.0",
echo     "ruff>=0.5",
echo ]
echo all = [
echo     "%SAFE_NAME_LOWER%[test]",
echo ]
echo dev = [
echo     "%SAFE_NAME_LOWER%[test]",
echo ]
echo.
echo [build-system]
echo requires = ["setuptools>=75.0", "wheel"]
echo build-backend = "setuptools.build_meta"
echo.
echo [tool.setuptools.packages.find]
echo where = ["src"]
echo include = ["%SRC_PKG%*"]
echo.
echo [tool.pytest.ini_options]
echo testpaths = ["tests"]
echo pythonpath = ["src"]
echo addopts = "-q --tb=short --no-header"
echo.
echo [tool.coverage.run]
echo source = ["src"]
echo omit = ["*/tests/*", "*/__pycache__/*", "*/site-packages/*"]
echo branch = true
echo.
echo [tool.coverage.report]
echo exclude_lines = [
echo     "pragma: no cover",
echo     "def __repr__",
echo     "if __name__ == .__main__.:",
echo     "if TYPE_CHECKING:",
echo     "raise NotImplementedError",
echo     "except ImportError",
echo ]
echo fail_under = 0
echo.
echo [tool.coverage.html]
echo directory = "htmlcov"
echo.
echo [tool.ruff]
echo target-version = "py312"
echo line-length = 120
echo.
echo [tool.ruff.lint]
echo select = [
echo     "E",
echo     "F",
echo     "I",
echo     "N",
echo     "W",
echo     "UP",
echo     "RUF",
echo ]
echo ignore = [
echo     "E501",
echo     "N999",
echo ]
echo fixable = ["ALL"]
echo exclude = ["__pycache__", ".git", "htmlcov", "dist"]
echo.
echo [tool.ruff.format]
echo quote-style = "double"
echo indent-width = 4
echo line-ending = "auto"
echo.
echo [tool.taskipy.tasks]
echo dev = "python src/%SRC_PKG%/main.py"
echo test = "python -m pytest tests/ -q --tb=short"
echo test-v = "python -m pytest tests/ -v --tb=long"
echo test-x = "python -m pytest tests/ -q --tb=short -x"
echo coverage = "python -m pytest tests/ -q --tb=short --cov=src --cov-report=term-missing"
echo coverage-html = "python -m pytest tests/ -q --tb=short --cov=src --cov-report=html"
echo lint = "ruff check src/"
echo format = "ruff format src/ tests/"
echo check-all = "ruff format --check src/ tests/ && ruff check src/ && python -m pytest tests/ -q --tb=short"
echo clean = "python -c \"import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__') if p.is_dir()]; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]\""
echo pre-commit-run = "pre-commit run --all-files"
echo.
echo [tool.codespell]
echo skip = "*.pyc,*.git,*.db,*.png,*.jpg,htmlcov,node_modules,.venv"
echo ignore-words-list = "ba,hte"
echo check-hidden = true
) > "%PROJECT_DIR%\pyproject.toml"

REM ── .pre-commit-config.yaml ──
(
echo repos:
echo   - repo: https://github.com/pre-commit/pre-commit-hooks
echo     rev: v5.0.0
echo     hooks:
echo       - id: trailing-whitespace
echo       - id: end-of-file-fixer
echo       - id: check-yaml
echo       - id: check-added-large-files
echo       - id: check-merge-conflict
echo       - id: mixed-line-ending
echo.
echo   - repo: https://github.com/astral-sh/ruff-pre-commit
echo     rev: v0.6.0
echo     hooks:
echo       - id: ruff-format
echo         args: [--line-length=120]
echo       - id: ruff
echo         args: [--fix, --line-length=120]
echo.
echo   - repo: https://github.com/codespell-project/codespell
echo     rev: v2.3.0
echo     hooks:
echo       - id: codespell
echo         args: [--skip=*.pyc,*.db,node_modules]
echo         language: python
echo         types: [text]
) > "%PROJECT_DIR%\.pre-commit-config.yaml"

REM ── .vscode/settings.json ──
(
echo {
echo   "python.defaultInterpreterPath": ".venv/Scripts/python.exe",
echo   "python.terminal.activateEnvironment": true,
echo   "python.testing.pytestEnabled": true,
echo   "python.testing.pytestArgs": ["tests"],
echo   "python.testing.autoTestDiscoverOnSaveEnabled": true,
echo   "[python]": {
echo     "editor.formatOnSave": true,
echo     "editor.codeActionsOnSave": {
echo       "source.fixAll": "explicit",
echo       "source.organizeImports": "explicit"
echo     },
echo     "editor.defaultFormatter": "charliermarsh.ruff"
echo   },
echo   "ruff.lineLength": 120,
echo   "ruff.organizeImports": true,
echo   "ruff.fixAll": true,
echo   "files.autoSave": "onFocusChange",
echo   "editor.rulers": [120],
echo   "workbench.colorTheme": "Default Dark Modern"
echo }
) > "%PROJECT_DIR%\.vscode\settings.json"

REM ── .vscode/extensions.json ──
(
echo {
echo   "recommendations": [
echo     "charliermarsh.ruff",
echo     "ms-python.python",
echo     "ms-python.vscode-pylance",
echo     "ms-python.mypy-type-checker",
echo     "tamasfe.even-better-toml",
echo     "github.vscode-github-actions",
echo     "redhat.vscode-yaml",
echo     "streetsidesoftware.code-spell-checker"
echo   ]
echo }
) > "%PROJECT_DIR%\.vscode\extensions.json"

REM ── .vscode/tasks.json ──
(
echo {
echo   "version": "2.0.0",
echo   "tasks": [
echo     {
echo       "label": "Run tests",
echo       "type": "shell",
echo       "command": "python -m pytest tests/ -q --tb=short",
echo       "group": "test",
echo       "problemMatcher": []
echo     },
echo     {
echo       "label": "Run coverage",
echo       "type": "shell",
echo       "command": "python -m pytest tests/ -q --tb=short --cov=src --cov-report=term-missing",
echo       "group": "test",
echo       "problemMatcher": []
echo     },
echo     {
echo       "label": "Lint (ruff check)",
echo       "type": "shell",
echo       "command": "ruff check src/",
echo       "group": "build",
echo       "problemMatcher": ["$ruff"]
echo     },
echo     {
echo       "label": "Format (ruff format)",
echo       "type": "shell",
echo       "command": "ruff format src/ tests/",
echo       "group": "build",
echo       "problemMatcher": []
echo     },
echo     {
echo       "label": "Check all",
echo       "type": "shell",
echo       "command": "ruff format --check src/ tests/ && ruff check src/ && python -m pytest tests/ -q --tb=short",
echo       "group": "test",
echo       "problemMatcher": []
echo     }
echo   ]
echo }
) > "%PROJECT_DIR%\.vscode\tasks.json"

REM ── .github/workflows/ci.yml ──
(
echo name: CI
echo.
echo on:
echo   push:
echo     branches: [master, main]
echo   pull_request:
echo     branches: [master, main]
echo.
echo jobs:
echo   lint:
echo     runs-on: windows-latest
echo     steps:
echo       - uses: actions/checkout@v4
echo       - uses: actions/setup-python@v5
echo         with:
echo           python-version: "3.12"
echo           cache: "pip"
echo.
echo       - name: Install dependencies
echo         run: pip install -e .[test]
echo.
echo       - name: Ruff check
echo         run: ruff check src/
echo.
echo       - name: Ruff format check
echo         run: ruff format --check src/ tests/
echo.
echo   test:
echo     runs-on: windows-latest
echo     steps:
echo       - uses: actions/checkout@v4
echo       - uses: actions/setup-python@v5
echo         with:
echo           python-version: "3.12"
echo           cache: "pip"
echo.
echo       - name: Install dependencies
echo         run: pip install -e .[test]
echo.
echo       - name: Run tests
echo         run: python -m pytest tests/ -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=70
) > "%PROJECT_DIR%\.github\workflows\ci.yml"

REM ── CONTRIBUTING.md ──
(
echo # 贡献指南
echo.
echo ## 开发环境
echo.
echo 运行 `scripts\dev_setup.bat` 一键初始化。
echo.
echo ## 分支策略
echo.
echo ```
echo main            → 稳定版本（只从 PR 合并）
echo feature/*       → 新功能
echo fix/*           → 修 Bug
echo refactor/*      → 重构
echo docs/*          → 文档
echo chore/*         → CI/依赖/杂项
echo ```
echo.
echo ## Commit 格式
echo.
echo ```
echo ^<type^>: ^<简短描述^>
echo.
echo 类型: feat / fix / docs / style / refactor / perf / test / chore
echo ```
echo.
echo ## 提交前检查
echo.
echo ```bash
echo task check-all
echo ```
echo.
echo ## 测试规范
echo.
echo - 所有新功能必须有对应测试
echo - 测试放在 `tests/` 目录下
echo - 覆盖率不低于 70%%
echo.
echo ## 代码风格
echo.
echo - 用 ruff 自动格式化（已在 pre-commit 中配置）
echo - 行宽: 120 字符
echo - 引号: 双引号
echo - 目标 Python: 3.12+
echo - 类型注解: 所有公开函数必须带类型注解
) > "%PROJECT_DIR%\CONTRIBUTING.md"

REM ── scripts/dev_setup.bat (copy of self with project-specific adjustments) ──
(
echo @echo off
echo title %PROJECT_NAME% Dev Setup
echo.
echo echo ============================================
echo echo    %PROJECT_NAME% Dev Setup
echo echo ============================================
echo echo.
echo where python ^>nul 2^>^&1
echo if %%ERRORLEVEL%% neq 0 (
echo     echo [ERROR] Python not found! Install Python 3.12+
echo     pause
echo     exit /b 1
echo )
echo python --version
echo.
echo echo [1/4] Installing project...
echo pip install -e .[all]
echo.
echo echo [2/4] Installing dev tools...
echo pip install pre-commit ruff pytest-cov
echo.
echo echo [3/4] Installing pre-commit hooks...
echo pre-commit install
echo.
echo echo [4/4] Done!
echo echo.
echo echo   task test       - Run tests
echo echo   task lint       - Check code
echo echo   task format     - Format code
echo echo   task check-all  - Full check
echo echo.
echo pause
) > "%PROJECT_DIR%\scripts\dev_setup.bat"

echo.
echo ============================================
echo   ✅ All files created!
echo ============================================
echo.
echo Files generated in %PROJECT_DIR%:
echo.
for %%F in (
    .editorconfig
    .gitignore
    .pre-commit-config.yaml
    pyproject.toml
    CONTRIBUTING.md
    .github/workflows/ci.yml
    .vscode/settings.json
    .vscode/extensions.json
    .vscode/tasks.json
    scripts/dev_setup.bat
    src/%SRC_PKG%/__init__.py
    tests/__init__.py
) do echo   📄 %%F

echo.
echo ============================================
echo   Next steps:
echo.
echo   cd %PROJECT_DIR%
echo   scripts\dev_setup.bat
echo   pip install -e .
echo   git init ^&^& git add . ^&^& git commit -m "Initial commit"
echo.
echo   Then use: task test / task lint / task check-all
echo ============================================
echo.

pause
