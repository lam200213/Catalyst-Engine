# backend-services/scheduler-service/celery_app.py

import os
from celery import Celery
from celery.schedules import crontab

def _get_celery_urls():
    """
    Retrieves Celery broker and backend URLs from environment variables.
    Defaults to the shared Redis instance if specific Celery vars aren't set.
    """
    cache_redis_url = os.getenv("CACHE_REDIS_URL", "redis://redis:6379/0")
    broker_url = os.getenv("CELERY_BROKER_URL", cache_redis_url)
    backend_url = os.getenv("CELERY_RESULT_BACKEND", cache_redis_url)
    return broker_url, backend_url

broker_url, backend_url = _get_celery_urls()

celery = Celery(
    "scheduler_service",
    broker=broker_url,
    backend=backend_url,
    include=("tasks",), # Ensures tasks are registered when worker starts
)

# Configuration must match test_config_integrity.py expectations:
# 1. UTC Timezone
# 2. Registered Beat Schedule for Watchlist Refresh
celery.conf.update(
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "scheduler.refresh_watchlist_task": {
            "task": "scheduler.refresh_watchlist_task",
            "schedule": crontab(hour=5, minute=0),  # Run daily at 05:00 UTC
            "args": (),
        },
        # Future: The full screening pipeline can be added here when weekly rules are defined
        # "scheduler.run_weekly_screening": { ... }
    },
)

if __name__ == "__main__":
    celery.start()