# backend-services/scheduler-service/tests/unit/test_config_integrity.py

import os
from unittest.mock import patch
import pytest

def test_celery_broker_config_exists():
    """
    Ensures that the Celery Broker URL is correctly loaded from environment variables.
    """
    # Mock environment before importing celery_app
    with patch.dict(os.environ, {"CELERY_BROKER_URL": "redis://mock-redis:6379/0"}):
        from celery_app import celery
        assert celery.conf.broker_url == "redis://mock-redis:6379/0"

def test_beat_schedule_registered():
    """
    Verifies that the required periodic tasks are registered in the Celery Beat schedule.
    Ref: US-4 Automated Watchlist Refresh
    """
    from celery_app import celery
    
    schedule = celery.conf.beat_schedule
    
    # 1. Watchlist Refresh Task (Daily)
    assert "scheduler.refresh_watchlist_task" in str(schedule) or "refresh_watchlist_task" in schedule
    
    # 2. Full Pipeline (Weekly/Configurable) - Optional check depending on implementation
    # assert "run_screening_pipeline" in str(schedule)

def test_beat_schedule_is_utc():
    """
    Asserts that the scheduler timezone is explicitly set to UTC.
    Critical for consistent 05:00 UTC execution regardless of server location.
    """
    from celery_app import celery
    assert celery.conf.timezone == "UTC"
    assert celery.conf.enable_utc is True