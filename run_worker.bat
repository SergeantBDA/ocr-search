echo off
chcp 65001 >nul
setlocal

set "BASE=%~dp0"
set "VENV=%BASE%venv"
set "PY=%VENV%\Scripts\python.exe"

REM (опционально) проверить наличие venv
if not exist "%PY%" (
  echo [ERROR] venv не найден: "%PY%"
  exit /b 1
)

REM Dramatiq worker (без start/cmd /k)
"%PY%" -m dramatiq app.broker.workers -Q upload --processes 2 --threads 4
exit /b %ERRORLEVEL%