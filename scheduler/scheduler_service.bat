@echo off
REM VK Ads Manager Scheduler - Windows startup script

setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "SCHEDULER_SCRIPT=%SCRIPT_DIR%scheduler_main.py"
set "PID_FILE=%SCRIPT_DIR%scheduler.pid"
set "LOG_FILE=%SCRIPT_DIR%scheduler_startup.log"

REM Функция для логирования
:log
echo %date% %time% - %~1
goto :eof

REM Проверка статуса
:status
if exist "%PID_FILE%" (
    set /p PID=<"%PID_FILE%"
    tasklist /FI "PID eq %PID%" 2>nul | find /i "%PID%" >nul
    if not errorlevel 1 (
        call :log "Scheduler запущен (PID: %PID%)"
        exit /b 0
    ) else (
        call :log "PID файл существует, но процесс не найден"
        del /f "%PID_FILE%" 2>nul
    )
)
call :log "Scheduler не запущен"
exit /b 1

REM Запуск планировщика
:start
call :status >nul
if %errorlevel%==0 (
    call :log "Scheduler уже запущен"
    exit /b 1
)

call :log "Запуск VK Ads Manager Scheduler..."
cd /d "%PROJECT_DIR%"

REM Запуск в фоне и сохранение PID
start /b python "%SCHEDULER_SCRIPT%" > "%SCRIPT_DIR%scheduler_output.log" 2>&1

REM Получаем PID последнего запущенного процесса Python
for /f "tokens=2 delims=," %%i in ('tasklist /fo csv ^| findstr /i python') do set "PID=%%~i"
echo %PID% > "%PID_FILE%"

timeout /t 2 /nobreak >nul

call :status >nul
if %errorlevel%==0 (
    call :log "Scheduler успешно запущен"
    exit /b 0
) else (
    call :log "Ошибка запуска Scheduler"
    exit /b 1
)

REM Остановка планировщика
:stop
call :status >nul
if not %errorlevel%==0 (
    call :log "Scheduler не запущен"
    exit /b 1
)

set /p PID=<"%PID_FILE%"
call :log "Остановка Scheduler (PID: %PID%)..."

REM Завершение процесса
taskkill /PID %PID% /T /F >nul 2>&1

del /f "%PID_FILE%" 2>nul
call :log "Scheduler остановлен"
exit /b 0

REM Перезапуск
:restart
call :stop
timeout /t 2 /nobreak >nul
call :start
exit /b %errorlevel%

REM Показ логов
:logs
if exist "%SCRIPT_DIR%scheduler_output.log" (
    powershell -Command "Get-Content '%SCRIPT_DIR%scheduler_output.log' -Wait"
) else (
    echo Лог файл не найден
    exit /b 1
)
exit /b 0

REM Основная логика
if "%~1"=="start" goto start
if "%~1"=="stop" goto stop
if "%~1"=="restart" goto restart
if "%~1"=="status" goto status
if "%~1"=="logs" goto logs

echo Использование: %0 {start^|stop^|restart^|status^|logs}
echo.
echo   start   - Запуск планировщика
echo   stop    - Остановка планировщика
echo   restart - Перезапуск планировщика
echo   status  - Проверка статуса
echo   logs    - Показать логи (Ctrl+C для выхода)
exit /b 1