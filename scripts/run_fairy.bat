@echo off
chcp 65001 >nul
title NURO Ghost — Ghost Platform 桌面精灵

cd /d "%~dp0.."

set "PYHOME=%LOCALAPPDATA%\Python"
if exist "%PYHOME%\python.exe" (
    "%PYHOME%\python.exe" "%~dp0..\src\aid_daemon.py" %*
    goto :end
)

python "%~dp0..\src\aid_daemon.py" %*
if %ERRORLEVEL% neq 9009 goto :end

py -3 "%~dp0..\src\aid_daemon.py" %*
if %ERRORLEVEL% neq 9009 goto :end

echo.
echo === NURO Ghost — Ghost Platform 桌面精灵 ===
echo.
echo Python not found.
echo Please install Python 3.10+ with "Add to PATH" checked.
echo.
pause
exit /b 1

:end
echo.
echo NURO Ghost exited (code %ERRORLEVEL%)
pause
