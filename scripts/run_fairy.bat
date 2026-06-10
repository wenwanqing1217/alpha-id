@echo off
chcp 65001 >nul
title AID 桌面精灵

:: 切换到项目根目录
cd /d "%~dp0.."

:: 参数透传
python src\aid_daemon.py %*

:: 如果出错就暂停
if %ERRORLEVEL% neq 0 (
    echo.
    echo 退出码: %ERRORLEVEL%
    echo 如果报缺少依赖，运行 scripts\install_fairy.bat
    pause
)
