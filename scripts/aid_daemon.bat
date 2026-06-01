@echo off
chcp 65001 >nul
title AID Desktop Fairy

cd /d "%~dp0.."

:: Try direct path first (8.3 short name avoids Chinese char issues)
set "PYHOME=%LOCALAPPDATA%\Python"
if exist "%PYHOME%\python.exe" (
    "%PYHOME%\python.exe" "%~dp0..\src\aid_daemon.py"
    goto :end
)

:: Fallback: search PATH
python "%~dp0..\src\aid_daemon.py"
if %ERRORLEVEL% neq 9009 goto :end

py -3 "%~dp0..\src\aid_daemon.py"
if %ERRORLEVEL% neq 9009 goto :end

echo.
echo === AID Desktop Fairy v0.1 ===
echo.
echo Python not found.
echo Please install Python 3.10+ with "Add to PATH" checked.
echo.
pause
exit /b 1

:end
echo.
echo AID exited (code %ERRORLEVEL%)
pause
