@echo off
cd /d "%~dp0"
python -u -c "import sys; sys.path.insert(0, 'src'); import uvicorn; from main import app; uvicorn.run(app, host='127.0.0.1', port=8005, log_level='info')"
pause
