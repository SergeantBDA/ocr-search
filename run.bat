@echo off
title OCR-Search Service
chcp 65001 >nul

REM === НАСТРОЙКИ ===
set "PYTHON_DIR=%~dp0"
set "VENV_DIR=%PYTHON_DIR%venv"
set "WORKERS=1"

REM === Проверка виртуального окружения ===
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [INFO] Создаю виртуальное окружение...
    python -m venv "%VENV_DIR%"
)

echo [INFO] Активирую виртуальное окружение...
call "%VENV_DIR%\Scripts\activate.bat"

REM === Проверяем Redis ===
echo [INFO] Проверяю наличие Redis (Memurai)...
where memurai >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [WARN] Memurai не найден в PATH.
) else (
    echo [OK] Memurai найден. Не забудь запустить службу.
)
 
REM === Запуск брокера Dramatiq ===
echo [INFO] Запускаю брокер Dramatiq...
start "Dramatiq Worker" cmd /k ^
    "%VENV_DIR%\Scripts\python.exe" -m dramatiq app.broker.workers -Q upload --processes 2 --threads 4

REM === Задержка, чтобы Dramatiq успел подняться ===
timeout /t 3 >nul

REM === Запуск веб-приложения FastAPI ===
echo [INFO] Запускаю веб-приложение OCR-Search...
start "OCR Web Server" cmd /k ^
    "%VENV_DIR%\Scripts\python.exe" -m app.main

echo.
echo [INFO] Приложение OCR-Search запущено.
echo [INFO] Dramatiq воркеры работают в отдельном окне.
pause
