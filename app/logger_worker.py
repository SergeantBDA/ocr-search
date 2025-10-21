# app/worker_logger.py
import logging
#from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
# === конфигурация отдельного логгера для actor ===
 
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "worker.log"
 
fmt = logging.Formatter("%(asctime)s | PID %(process)d | %(levelname)s | %(name)s | %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
 
# Попытаться использовать безопасный ротатор (межпроцессная блокировка)
try:
    from concurrent_log_handler import ConcurrentRotatingFileHandler as RotatingFileHandler
    fh = RotatingFileHandler(str(LOG_FILE), maxBytes=5_000_000, backupCount=5, encoding="utf-8")
except Exception:
    # fallback: обычный Timed/Rotating (если -p 1 в dramatiq)
    from logging.handlers import RotatingFileHandler
    fh = RotatingFileHandler(str(LOG_FILE), maxBytes=5_000_000, backupCount=5, encoding="utf-8")
 
fh.setFormatter(fmt)
fh.setLevel(logging.INFO)
 
ch = logging.StreamHandler()
ch.setFormatter(fmt)
ch.setLevel(logging.INFO)
 
worker_log = logging.getLogger("ocr.worker")
if not worker_log.handlers:
    worker_log.addHandler(ch)
    worker_log.addHandler(fh)
worker_log.setLevel(logging.INFO)
worker_log.propagate = False
