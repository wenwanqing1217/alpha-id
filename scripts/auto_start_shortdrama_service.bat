@echo off
chcp 65001 >nul
title 短剧审核后台服务 - 开机自启

:: 等待系统稳定（网络、磁盘等就绪）
timeout /t 10 /nobreak >nul

:: 启动服务
cd /d "%~dp0.."
call "%~dp0start_shortdrama_service.bat"
