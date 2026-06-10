@echo off
REM Alpha-ID Daemon Auto-Start — 开机自启
REM 将此文件放到 开始菜单→启动 文件夹：
REM   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
REM 或直接在 Windows 任务计划程序中创建任务。

cd /d "%~dp0"

REM 检查 Python 是否可用
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [AID] 错误: 未找到 Python，请先安装 Python 3.12+
    pause
    exit /b 1
)

REM 确保日志目录存在
if not exist "%USERPROFILE%\.alpha-id" mkdir "%USERPROFILE%\.alpha-id"

echo [AID] 正在启动桌面精灵...
start /B /MIN "AID-Fairy" cmd /c "python src\aid_daemon.py --no-mcp >> \"%USERPROFILE%\.alpha-id\daemon.log\" 2>&1"

echo [AID] 启动完成（日志: %%USERPROFILE%%\.alpha-id\daemon.log）
