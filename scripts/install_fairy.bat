@echo off
chcp 65001 >nul
title AID 桌面精灵 — 一键安装

setlocal enabledelayedexpansion

echo ============================================
echo    AID 桌面精灵 v2 — 一键安装
echo    磨砂玻璃悬浮球 + 持续对话 + 语音唤醒
echo ============================================
echo.

:: ── Step 0: 检查 Python ──
echo [0/4] 检查 Python...
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [失败] 未找到 Python！
    echo.
    echo 请先安装 Python 3.12+（安装时勾选 "Add to PATH"）
    echo   下载: https://www.python.org/downloads/
    echo.
    echo 或从 Microsoft Store 安装:
    echo   https://apps.microsoft.com/detail/9ncvdn91zqpj
    pause
    exit /b 1
)

python --version 2>&1 | findstr "3.1[2-9]" >nul
if %ERRORLEVEL% neq 0 (
    python --version
    echo [警告] 推荐 Python 3.12+，继续安装...
) else (
    echo   Python 版本正确 ✓
)
echo.

:: ── Step 1: 安装核心依赖 ──
echo [1/4] 安装核心依赖...
python -m pip install --upgrade pip setuptools wheel -q
pip install -e .. >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [失败] 核心安装失败！
    echo   尝试: cd /d "%~dp0.." ^&^& pip install -e .
    pause
    exit /b 1
)
echo   核心依赖 ✓
echo.

:: ── Step 2: 安装桌面精灵依赖 ──
echo [2/4] 安装桌面精灵依赖（openai, 截图, OCR, 窗口控制）...
pip install -e ..[fairy] >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   部分依赖安装失败，继续安装基础包...
)
pip install pyautogui pygetwindow Pillow -q
echo   截图/窗口控制 ✓

pip install pytesseract -q
echo   OCR ✓

pip install SpeechRecognition sounddevice -q
echo   语音识别 ✓

pip install pywin32 -q
echo   TTS ✓
echo.

:: ── Step 3: 检查 Ollama（可选本地 AI） ──
echo [3/4] 检查本地 AI 引擎...
where ollama >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   Ollama 已安装 ✓
    echo   运行后即可免 API Key 使用本地模型
) else (
    echo   Ollama 未安装（可选，推荐）
    echo   安装后无需 API Key，在本地跑 AI 模型
    echo   下载: https://ollama.com/download
    echo   安装后运行: ollama pull llama3.2
)
echo.

:: ── Step 4: 创建快捷方式 ──
echo [4/4] 创建启动脚本...
set "SCRIPT_DIR=%~dp0"
set "RUN_BAT=%SCRIPT_DIR%run_fairy.bat"

if not exist "%RUN_BAT%" (
    echo 创建 run_fairy.bat 失败，请手动运行:
    echo   python src\aid_daemon.py
) else (
    echo   启动脚本就绪 ✓
)
echo.

:: ── 完成 ──
echo ============================================
echo    安装完成！
echo ============================================
echo.
echo   🚀 启动方式:
echo     双击 scripts\run_fairy.bat
echo.
echo   🧠 使用本地 AI（无需 API Key）:
echo     1. 安装 Ollama: https://ollama.com/download
echo     2. 下载模型:    ollama pull llama3.2
echo     3. 启动 Ollama（后台自动运行）
echo     4. 运行精灵即可自动连接
echo.
echo   🔑 使用云端 AI（需 API Key）:
echo     推荐 DeepSeek（便宜又快）
echo     设置: set DEEPSEEK_API_KEY=sk-xxx
echo           set AID_LLM_MODEL=deepseek-chat
echo.
echo   ❓ 检查环境:  python src\aid_daemon.py --check
echo.
echo   💡 提示: 常用功能需额外装包
echo     截图:   pip install pyautogui pygetwindow Pillow
echo     OCR:    pip install pytesseract
echo     语音:   pip install SpeechRecognition sounddevice
echo.
pause
