import os
import json
import redis
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results.backends import RedisBackend
from dramatiq.results import Results
from app.config import settings
from dramatiq.middleware import TimeLimit

# Memurai совместим с Redis URL
REDIS_URL = settings.redis_url
# Простая неймспейсовая схема ключей
NS = settings.dramatiq_ns

def KEY_JOB(job_id: str) -> str:
    return f"{NS}:job:{job_id}"  # JSON: {status, total, done, items, error, created_at}
def KEY_RESULT(job_id: str) -> str:
    return f"{NS}:result:{job_id}"

# --- Настройка брокера ---
redis_broker = RedisBroker(url=REDIS_URL, namespace=f"{NS}:broker")
dramatiq.set_broker(redis_broker)
 
# ❌ Полностью отключаем TimeLimit (удаляем стандартный middleware)
redis_broker.middleware = [
    m for m in redis_broker.middleware if not isinstance(m, TimeLimit)
]
 
# Результаты
result_backend = RedisBackend(url=REDIS_URL, namespace=f"{NS}:results")
redis_broker.add_middleware(Results(backend=result_backend))
 
# --- Клиент Redis для прогресса ---
r = redis.Redis.from_url(REDIS_URL)
 
def job_set(job_id: str, payload: dict, ttl_hours: int = 12) -> None:
    r.setex(KEY_JOB(job_id), ttl_hours * 3600, json.dumps(payload, ensure_ascii=False))

def job_get(job_id: str) -> dict | None:
    raw = r.get(KEY_JOB(job_id))
    if not raw:
        return None
    return json.loads(raw)

def job_update(job_id: str, **fields):
    # если стоит tombstone — не трогаем статус
    if r.get(f"{NS}:job-deleted:{job_id}"):
        return job_get(job_id) or {}
    data = job_get(job_id) or {}
    data.update(fields)
    job_set(job_id, data)
    return data
