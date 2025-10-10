# app/worker_logger.py
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
# === конфигурация отдельного логгера для actor ===
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "worker.log"
# Получаем изолированный логгер
worker_log = logging.getLogger("app.worker")
worker_log.setLevel(logging.INFO)
worker_log.propagate = False  # Не отправлять записи в основной логгер приложения
# Проверяем, чтобы не добавлять хендлер дважды
if not any(isinstance(h, TimedRotatingFileHandler) for h in worker_log.handlers):
    handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="D",          # ежедневная ротация
        interval=1,
        backupCount=14,    # хранить 14 дней
        encoding="utf-8",
    )
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s pid=%(process)d tid=%(threadName)s | %(message)s"
    )
    handler.setFormatter(fmt)
    worker_log.addHandler(handler)
# при необходимости можно добавить вывод в консоль (на dev)
if not any(isinstance(h, logging.StreamHandler) for h in worker_log.handlers):
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.WARNING)
    worker_log.addHandler(console)