@echo off
chcp 65001 >nul
setlocal

set "BASE=%~dp0"
set "VENV=%BASE%venv"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERROR] venv не найден: "%PY%"
  exit /b 1
)

REM Запуск FastAPI (как у вас). Если у вас uvicorn, лучше запускать uvicorn.
"%PY%" -m app.main
exit /b %ERRORLEVEL%