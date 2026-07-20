@echo off
chcp 65001 >nul
title 短剧审核后台服务 - 启动器

echo ==========================================
echo   短剧审核后台服务 - 启动器
echo ==========================================

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

:: 切换到项目目录
cd /d "%~dp0.."

:: 检查是否已在运行
if exist "%~dp0..\shortdrama_service.pid" (
    set /p pid=<"%~dp0..\shortdrama_service.pid"
    echo 检查现有进程 PID: %pid%
    tasklist /fi "pid eq %pid%" 2>nul | findstr /i "%pid%" >nul
    if not errorlevel 1 (
        echo [提示] 服务已在运行 (PID: %pid%)
        pause
        exit /b 0
    )
    echo [清理] 旧 PID 文件已失效，正在清理...
    del /f "%~dp0..\shortdrama_service.pid"
)

:: 确保必要的目录存在
if not exist "%~dp0..\assets" mkdir "%~dp0..\assets"
if not exist "%~dp0..\logs" mkdir "%~dp0..\logs"

:: 启动服务（后台运行）
echo [启动] 正在启动短剧审核后台服务...
start "ShortDrama Service" /min python -m src.entrypoints.shortdrama_service --interval 60

:: 等待服务启动
timeout /t 3 /nobreak >nul

:: 检查是否启动成功
if exist "%~dp0..\shortdrama_service.pid" (
    set /p newpid=<"%~dp0..\shortdrama_service.pid"
    echo [成功] 服务已启动 (PID: %newpid%)
    echo [日志] 查看日志: %~dp0..\shortdrama_service.log
    echo [状态] 查看状态: %~dp0..\shortdrama_service_state.json
) else (
    echo [警告] PID 文件未创建，服务可能启动失败
)

pause
