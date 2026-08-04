@echo off
REM Alpha-ID 启动脚本（端口 8002，使用正确的 DeepSeek API 配置）
REM 系统环境变量 OPENAI_BASE_URL 缺少 /v1 后缀，需要覆盖

set OPENAI_API_KEY=sk-48acbb5b15e24f8187869b832dd050c9
set OPENAI_BASE_URL=https://api.deepseek.com/v1

REM 演示模式（无真实短信/支付宝配置时启用）
set SMS_DEMO_MODE=true
set ALIPAY_DEMO_MODE=true

cd /d %~dp0
echo [AID] Starting Alpha-ID on port 8002...
echo [AID] DeepSeek API: %OPENAI_BASE_URL%
echo [AID] Demo Mode: SMS=%SMS_DEMO_MODE%, Alipay=%ALIPAY_DEMO_MODE%
python -m uvicorn src.main:app --host 0.0.0.0 --port 8002
