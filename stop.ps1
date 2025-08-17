# stop-fastapi.ps1
# Завершает процесс, который слушает порт 8000 (по умолчанию Uvicorn/FastAPI)

$port = 8000

Write-Host "Ищу процесс на порту $port..."

# получаем PID процесса, который слушает порт
$pid = (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue).OwningProcess

if ($pid) {
    Write-Host "Найден процесс PID=$pid. Останавливаю..."
    Stop-Process -Id $pid -Force
    Write-Host "FastAPI (Uvicorn) остановлен."
} else {
    Write-Host "Процесс на порту $port не найден."
}
