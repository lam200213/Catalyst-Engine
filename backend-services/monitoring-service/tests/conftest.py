# backend-services/monitoring-service/tests/conftest.py
"""
Pytest configuration and shared fixtures for monitoring-service tests
Centralizes common test client, DB patching, constants, and sample data
"""

import os
import sys
from typing import Tuple, Dict, Any, List
from unittest.mock import MagicMock
from urllib.parse import quote
from datetime import datetime, timedelta

import pytest

# Ensure local imports resolve when running from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# -------------------------------------------------------------------
# Constants shared across tests
# -------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_constants() -> Dict[str, Any]:
    return {
        "DEFAULT_USER_ID": "single_user_mode",
        "BUY_READY_THRESHOLD": 5.0,  # 5% proximity to pivot
        "MAX_SYMBOL_LEN": 10,
        "VALID_RE": r"^[A-Za-z0-9.\-]{1,10}$",
    }

# -------------------------------------------------------------------
# Environment helpers
# -------------------------------------------------------------------

@pytest.fixture(autouse=True)
def ensure_test_env(monkeypatch):
    """
    Standardize DB env for tests and fix Docker hostname vs localhost.
    """
    in_docker = os.path.exists("/.dockerenv")
    mongo_uri = "mongodb://mongodb:27017" if in_docker else "mongodb://localhost:27017"
    # Set both legacy and new env names for compatibility with old tests
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("MONGO_URI", mongo_uri)   
    # Optional test DB name to keep data isolated
    monkeypatch.setenv("TEST_DB_NAME", "test_stock_analysis")
    yield

# -------------------------------------------------------------------
# Flask app and client fixtures
# -------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

# -------------------------------------------------------------------
# Mongo DB helpers
# -------------------------------------------------------------------

def _make_mock_db_and_client() -> Tuple[MagicMock, MagicMock]:
    mock_db = MagicMock()
    mock_client = MagicMock()
    return mock_client, mock_db

@pytest.fixture
def patch_connect(monkeypatch):
    """
    Context-manager style:
      with patch_connect() as (client_mock, db_mock):
          ...
    """
    from database import mongo_client
    class _Ctx:
        def __enter__(self):
            client_mock, db_mock = _make_mock_db_and_client()
            monkeypatch.setattr(mongo_client, "connect", lambda: (client_mock, db_mock))
            return client_mock, db_mock
        def __exit__(self, exc_type, exc, tb):
            return False
    return _Ctx()

@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()

@pytest.fixture
def mock_mongo_client():
    """Mock MongoDB client for testing"""
    client = MagicMock()
    db = MagicMock()
    client.__getitem__.return_value = db
    return client, db

@pytest.fixture
def test_db_connection():
    """
    Real database connection for integration-like CRUD tests
    Uses a dedicated test DB to avoid polluting production data
    """
    from pymongo import MongoClient
    # Prefer TEST_MONGO_URI; fallback to localhost
    uri = os.getenv("TEST_MONGO_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
    db_name = os.getenv("TEST_DB_NAME", "test_stock_analysis")
    client = MongoClient(uri)
    db = client[db_name]
    try:
        yield client, db
    finally:
        # Cleanup after each test
        db.watchlistitems.delete_many({})
        db.archived_watchlist_items.delete_many({})
        db.portfolioitems.delete_many({})
        client.close()

@pytest.fixture
def clean_test_db():
    """Provides clean database for each integration test"""
    from database.mongo_client import (
        connect,
    )

    client, db = connect()
    
    # Clean before test
    db.watchlistitems.delete_many({})
    db.archived_watchlist_items.delete_many({})
    
    yield db
    
    # Clean after test
    db.watchlistitems.delete_many({})
    db.archived_watchlist_items.delete_many({})
    client.close()

# -------------------------------------------------------------------
# Layered sample data
# -------------------------------------------------------------------
@pytest.fixture
def base_status_item() -> Dict[str, Any]:
    """
    Base rich-mode watchlist item used by status engine tests.

    Represents a healthy, valid VCP candidate near a good pivot with
    neutral volume – tests override only the fields they care about.
    """
    now = datetime.utcnow()
    return {
        "ticker": "BASE",
        "is_favourite": False,
        "last_refresh_status": "PASS",
        "failed_stage": None,
        "current_price": 100.0,
        "pivot_price": 100.0,
        "pivot_proximity_percent": -2.0,
        "vcp_pass": True,
        "is_pivot_good": True,
        "pattern_age_days": 20,
        "has_pivot": True,
        "is_at_pivot": True,
        "has_pullback_setup": False,
        "vol_vs_50d_ratio": 1.0,
        "day_change_pct": 0.5,
        "is_leader": False,
    }

@pytest.fixture
def sample_watchlist_items(test_constants) -> List[Dict[str, Any]]:
    """
    Match the richest DB shape used in service tests, so tests won’t redefine per-file variants.
    Mongo-shaped sample items for service/CRUD tests (richest shape).
    Includes optional _id for tests that assert presence, but route-layer
    tests must never assert on these internal fields.
    """
    uid = test_constants["DEFAULT_USER_ID"]
    now = datetime.utcnow()
    return [
        {
            "_id": "507f1f77bcf86cd799439011",
            "user_id": uid,                 # keep as-is to match current code paths
            "ticker": "AAPL",
            "date_added": now,
            "is_favourite": False,
            "last_refresh_status": "PENDING",
            "last_refresh_at": None,
            "failed_stage": None,
            "current_price": None,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False,
        },
        {
            "_id": "507f1f77bcf86cd799439012",
            "user_id": uid,
            "ticker": "MSFT",
            "date_added": now - timedelta(days=5),
            "is_favourite": True,
            "last_refresh_status": "PASS",
            "last_refresh_at": now,
            "failed_stage": None,
            "current_price": 330.0,
            "pivot_price": 335.0,
            "pivot_proximity_percent": -1.49,
            "is_leader": True,
        },
        {
            "_id": "507f1f77bcf86cd799439013",
            "user_id": uid,
            "ticker": "GOOGL",
            "date_added": now - timedelta(days=2),
            "is_favourite": False,
            "last_refresh_status": "PENDING",
            "last_refresh_at": None,
            "failed_stage": None,
            "current_price": 280.0,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False,
        },
    ]

@pytest.fixture
def sample_watchlist_response() -> Dict[str, Any]:
    """
    API-layer shape: fields as presented to the frontend (used by route/integration tests).
    Mirrors API_REFERENCE.
    """
    return {
        "items": [
            {
                "ticker": "AAPL",
                "status": "Watch",
                "date_added": None,
                "is_favourite": False,
                "last_refresh_status": "PENDING",
                "last_refresh_at": None,
                "failed_stage": None,
                "current_price": None,
                "pivot_price": None,
                "pivot_proximity_percent": None,
                "is_leader": False,
            },
            {
                "ticker": "MSFT",
                "status": "Buy Ready",
                "date_added": "2025-09-20T10:00:00Z",
                "is_favourite": True,
                "last_refresh_status": "PASS",
                "last_refresh_at": "2025-11-01T12:00:00Z",
                "failed_stage": None,
                "current_price": 330.0,
                "pivot_price": 335.0,
                "pivot_proximity_percent": -1.49,
                "is_leader": True,
            },
        ],
        "metadata": {"count": 2},
    }

@pytest.fixture
def sample_archive_items(test_constants):
    """Sample archive items for CRUD tests"""
    uid = test_constants["DEFAULT_USER_ID"]
    now = datetime.utcnow()
    return [
        {
            "user_id": uid,
            "ticker": "CRM",
            "archived_at": now - timedelta(days=5),
            "reason": "FAILED_HEALTH_CHECK",
            "failed_stage": "vcp",
        },
        {
            "user_id": uid,
            "ticker": "ZEN",
            "archived_at": now - timedelta(days=15),
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
        },
    ]

@pytest.fixture
def sample_empty_watchlist_response():
    """Sample empty watchlist response"""
    return {
        "items": [],
        "metadata": {
            "count": 0
        }
    }

@pytest.fixture
def portfolio_tickers():
    """Sample portfolio tickers for mutual exclusivity testing"""
    return ["CRWD", "NET", "DDOG"]

@pytest.fixture
def sample_archive_response():
    """
    API-layer shape for /monitor/archive responses (used by route tests).
    """
    # Mirrors API_REFERENCE contract: archived_items with field names archived_at/failed_stage
    return {
        "archived_items": [
            {"ticker": "CRM", "archived_at": "2025-11-08T10:00:00Z", "reason": "FAILED_HEALTH_CHECK", "failed_stage": "vcp"},
            {"ticker": "NET", "archived_at": "2025-11-01T12:00:00Z", "reason": "MANUAL_DELETE", "failed_stage": None},
        ]
    }

@pytest.fixture
def archive_db_docs(default_user_id):
    """Raw Mongo-shaped docs for archived_watchlist_items (used by DB/service tests)"""
    now = datetime.utcnow()
    return [
        {
            "user_id": default_user_id,
            "ticker": "CRM",
            "archived_at": now,
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
        },
        {
            "user_id": default_user_id,
            "ticker": "NET",
            "archived_at": now - timedelta(days=3),
            "reason": "FAILED_HEALTH_CHECK",
            "failed_stage": "vcp",
        },
    ]

@pytest.fixture
def api_archive_response():
    """API-shaped archive response (used by route tests)"""
    return {
        "archived_items": [
            {"ticker": "CRM", "archived_at": "2025-11-08T10:00:00Z", "reason": "FAILED_HEALTH_CHECK", "failed_stage": "vcp"},
            {"ticker": "NET", "archived_at": "2025-11-01T12:00:00Z", "reason": "MANUAL_DELETE", "failed_stage": None},
        ]
    }

# -------------------------------------------------------------------
# Sample sets for route format tests
# -------------------------------------------------------------------

@pytest.fixture(scope="session")
def valid_tickers() -> List[str]:
    return ["AAPL", "aapl", "BRK.B", "BRK%2EB", "NET", "SHOP.TO", "CRWD-N"]

@pytest.fixture(scope="session")
def invalid_tickers() -> List[str]:
    return ["", " ", "AAPL$", "TOO-LONG-TICK", "AAPL@", "AAPL!", "AAPL/"]

# -------------------------------------------------------------------
# Watchlist service patch helper
# -------------------------------------------------------------------

@pytest.fixture
def patch_add_or_upsert_ticker(monkeypatch):
    import services.watchlist_service as svc
    mock = MagicMock()
    monkeypatch.setattr(svc, "add_or_upsert_ticker", mock)
    return mock

# Ticker length boundary helpers for shared use in route/service tests
@pytest.fixture(scope="session")
def ticker_thresholds(test_constants):
    """
    Provides tickers at, above, and below the length threshold (1–MAX_SYMBOL_LEN).
    below: empty, at: MAX_SYMBOL_LEN, above: MAX_SYMBOL_LEN + 1
    """
    max_len = test_constants.get("MAX_SYMBOL_LEN", 10)
    at = "A" * max_len
    above = "A" * (max_len + 1)
    below = ""  # just-below invalid
    return {"at": at, "above": above, "below": below}

# Seed default-user watchlist for integration-like CRUD tests
@pytest.fixture
def seeded_watchlist_default(test_db_connection, test_constants):
    client, db = test_db_connection
    uid = test_constants["DEFAULT_USER_ID"]

    docs = [
        {"user_id": uid, "ticker": "AAPL", "date_added": datetime.utcnow(), "is_favourite": False,
         "last_refresh_status": "PENDING", "last_refresh_at": None, "failed_stage": None},
        {"user_id": uid, "ticker": "NET", "date_added": datetime.utcnow(), "is_favourite": False,
         "last_refresh_status": "PENDING", "last_refresh_at": None, "failed_stage": None},
    ]
    db.watchlistitems.insert_many(docs)
    yield client, db, ["AAPL", "NET"]

# Seed default-user archive for integration-like CRUD tests
@pytest.fixture
def seeded_archive_default(test_db_connection, test_constants):
    client, db = test_db_connection
    uid = test_constants["DEFAULT_USER_ID"]

    docs = [
        {"user_id": uid, "ticker": "ZEN", "archived_at": datetime.utcnow(),
         "reason": "MANUAL_DELETE", "failed_stage": None},
        {"user_id": uid, "ticker": "CRM", "archived_at": datetime.utcnow(),
         "reason": "FAILED_HEALTH_CHECK", "failed_stage": "vcp"},
    ]
    db.archived_watchlist_items.insert_many(docs)
    yield client, db, ["ZEN", "CRM"]

# Archive TTL index assertion helper
def assert_archive_ttl_index(db, ttl_seconds: int = 2_592_000):
    """
    Assert that a TTL index exists on archived_watchlist_items.archived_at with the expected expireAfterSeconds.
    """
    indexes = list(db.archived_watchlist_items.list_indexes())
    ttl_candidates = [ix for ix in indexes if "expireAfterSeconds" in ix]
    assert any(ttl for ttl in ttl_candidates), "No TTL index found on archived_watchlist_items"

    found_correct_field = False
    found_correct_ttl = False
    for ix in ttl_candidates:
        # key may be presented as OrderedDict-like mapping
        key_items = list(ix.get("key", {}).items()) if hasattr(ix.get("key", {}), "items") else ix.get("key", [])
        if any(k == "archived_at" for k, _ in key_items):
            found_correct_field = True
        if ix.get("expireAfterSeconds") == ttl_seconds:
            found_correct_ttl = True

    assert found_correct_field, "TTL index is not on archived_at"
    assert found_correct_ttl, f"TTL index expireAfterSeconds is not {ttl_seconds}"

# Factory for building archive documents consistently across tests
@pytest.fixture
def make_archive_doc(test_constants):
    uid = test_constants["DEFAULT_USER_ID"]
    def _factory(ticker: str, reason: str = "MANUAL_DELETE", failed_stage=None):
        return {
            "user_id": uid,
            "ticker": ticker,
            "archived_at": datetime.utcnow(),
            "reason": reason,
            "failed_stage": failed_stage,
        }
    return _factory

# Utility fixture exposing DEFAULT_USER_ID directly
@pytest.fixture(scope="session")
def default_user_id(test_constants):
    return test_constants["DEFAULT_USER_ID"]

@pytest.fixture
def default_user_id():
    """Default single-user mode user id used across archive tests"""
    return "single_user_mode"

@pytest.fixture(scope="session")
def make_large_ticker_list():
    """Factory to generate a large performance-safe ticker list (no explicit threshold in docs)."""
    def _factory(n: int = 500) -> List[str]:
        return [f"T{i:04d}" for i in range(n)]
    return _factory