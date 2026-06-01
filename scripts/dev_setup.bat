@echo off
REM AID 开发环境一键初始化
REM 以管理员身份在 cmd 中运行

title AID Dev Setup

echo ============================================
echo    AID Development Environment Setup
echo ============================================
echo.

REM 检查 Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 未找到！请先安装 Python 3.12+
    echo         下载: https://www.python.org/downloads/
    pause
    exit /b 1
)

python --version

REM 1. 升级 pip
echo.
echo [1/5] Upgrading pip...
python -m pip install --upgrade pip setuptools wheel
if %ERRORLEVEL% neq 0 (
    echo [WARN] pip 升级失败，继续...
)

REM 2. 安装项目（dev 模式）
echo.
echo [2/5] Installing project in dev mode...
pip install -e .[all]
if %ERRORLEVEL% neq 0 (
    echo [WARN] 部分可选依赖安装失败（这通常不影响核心功能）
)

REM 3. 安装 dev 工具
echo.
echo [3/5] Installing dev tools...
pip install pre-commit mypy pytest-cov pytest-xdist coverage pyright
if %ERRORLEVEL% neq 0 (
    echo [WARN] 部分 dev 工具安装失败
)

REM 4. 安装 pre-commit hooks
echo.
echo [4/5] Installing pre-commit hooks...
pre-commit install
pre-commit install --hook-type commit-msg
if %ERRORLEVEL% neq 0 (
    echo [WARN] pre-commit hooks 安装失败（可手动重试）
)

REM 5. 验证
echo.
echo [5/5] Verifying setup...
echo.

echo --- Ruff check ---
ruff check src/ --silent
if %ERRORLEVEL% equ 0 (
    echo   Ruff: OK
) else (
    echo   Ruff: 有 lint 警告（不阻塞）
)

echo --- Pytest ---
python -m pytest tests/ -q --tb=short --no-header 2>nul
if %ERRORLEVEL% equ 0 (
    echo   Tests: PASS
) else (
    echo   Tests: 需要检查（可能缺少依赖）
)

echo.
echo ============================================
echo    Setup complete!
echo ============================================
echo.
echo   Next steps:
echo     1. Open VS Code in this folder:  code .
echo     2. Install recommended extensions (Ctrl+Shift+X)
echo     3. Start developing:              task dev
echo     4. Run tests:                     task test
echo.
echo   See DEVENV.md for detailed guide.
echo.

pause
