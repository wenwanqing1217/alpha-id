@echo off
chcp 65001 >nul
title 短剧审核后台服务 - 停止器

echo ==========================================
echo   短剧审核后台服务 - 停止器
echo ==========================================

cd /d "%~dp0.."

if not exist "%~dp0..\shortdrama_service.pid" (
    echo [提示] PID 文件不存在，服务可能未运行
    pause
    exit /b 0
)

set /p pid=<"%~dp0..\shortdrama_service.pid"
echo [停止] 正在停止服务 (PID: %pid%)...

:: 尝试优雅关闭
tasklist /fi "pid eq %pid%" 2>nul | findstr /i "%pid%" >nul
if not errorlevel 1 (
    taskkill /pid %pid% /f >nul 2>&1
    timeout /t 2 /nobreak >nul
    
    tasklist /fi "pid eq %pid%" 2>nul | findstr /i "%pid%" >nul
    if not errorlevel 1 (
        echo [强制] 进程未响应，强制结束...
        taskkill /pid %pid% /f
    )
    
    echo [成功] 服务已停止
) else (
    echo [提示] 进程 %pid% 未运行
)

:: 清理 PID 文件
del /f "%~dp0..\shortdrama_service.pid" 2>nul

pause
