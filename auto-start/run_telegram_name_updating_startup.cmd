@echo off
setlocal
set "PROJECT_DIR=F:\Project\Telegram-Name-Updating"
set "PYTHONW_EXE=%PROJECT_DIR%\.venv\Scripts\pythonw.exe"
set "SCRIPT_PATH=%PROJECT_DIR%\tg_username_update.py"
set "CONFIG_PATH=%PROJECT_DIR%\config.local.json"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "LAUNCHER_LOG=%LOG_DIR%\startup-launcher.log"
set "STARTUP_DELAY=%~1"

if not defined STARTUP_DELAY set "STARTUP_DELAY=60"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo [%date% %time%] startup launcher invoked with delay %STARTUP_DELAY%s>>"%LAUNCHER_LOG%"
timeout /t %STARTUP_DELAY% /nobreak >nul
cd /d "F:\Project\Telegram-Name-Updating"

if not exist "%PYTHONW_EXE%" (
    echo [%date% %time%] pythonw.exe not found: %PYTHONW_EXE%>>"%LAUNCHER_LOG%"
    exit /b 1
)

if not exist "%SCRIPT_PATH%" (
    echo [%date% %time%] script not found: %SCRIPT_PATH%>>"%LAUNCHER_LOG%"
    exit /b 1
)

if not exist "%CONFIG_PATH%" (
    echo [%date% %time%] config not found: %CONFIG_PATH%>>"%LAUNCHER_LOG%"
    exit /b 1
)

start "" /min "%PYTHONW_EXE%" "%SCRIPT_PATH%" --config "%CONFIG_PATH%"
echo [%date% %time%] startup command issued>>"%LAUNCHER_LOG%"
endlocal
