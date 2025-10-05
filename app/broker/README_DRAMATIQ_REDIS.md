
# Dramatiq + Redis/Memurai integration (extracted actor)

## Files added
- `app/broker/config.py` — RedisBroker + Results (RedisBackend) + helpers for job status.
- `app/broker/workers.py` — actor `process_upload` (moved from routes).
- `app/web/routes.py` — routes now enqueue jobs and poll status from Redis/Memurai.

## How to run (two terminals)

1) Start Memurai (or Redis) on Windows. Example URL: `redis://127.0.0.1:6379/0`
2) Environment:
   ```bash
   set REDIS_URL=redis://127.0.0.1:6379/0
   set DRAMATIQ_NAMESPACE=ocr-search
   ```
3) Worker:
   ```bash
   dramatiq app.broker.workers -Q upload --processes 1 --threads 4
   ```
4) App:
   ```bash
   uvicorn app.main:app --reload
   ```

## Notes
- Job status is stored in Redis JSON at key `ocr-search:job:<job_id>`.
- The actor writes progress and items back to that JSON.
- Result backend is enabled but not required for polling UI.
