@echo off
set OPENAI_API_KEY=sk-c15834a3a7fa4d8a8abd59bb78f5823f
set OPENAI_BASE_URL=https://api.deepseek.com/v1
set LLM_BASE_URL=https://api.deepseek.com/v1
set LLM_MODEL=deepseek-v4-flash
cd /d D:\Software\AID\projects
python -m uvicorn alpha_id.web:app --host 0.0.0.0 --port 8000
pause
