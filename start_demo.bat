@echo off
setlocal
chcp 65001 >nul

set "SCRIPT=%~dp0start_demo.ps1"
if not exist "%SCRIPT%" (
    echo [ERROR] Cannot find start_demo.ps1.
    echo Please keep start_demo.bat and start_demo.ps1 together in the CodeMind-FZU project root.
    pause
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
set "EXITCODE=%ERRORLEVEL%"
endlocal & exit /b %EXITCODE%
