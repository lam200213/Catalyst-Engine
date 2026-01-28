# backend-services/scheduler-service/db.py

import os
import logging
import time
from urllib.parse import urlparse

from pymongo import MongoClient, errors, ASCENDING, DESCENDING


logger = logging.getLogger(__name__)


def _db_name_from_mongo_uri(mongo_uri: str, default_db: str = "stock_analysis") -> str:
    try:
        parsed = urlparse(mongo_uri)
        path = (parsed.path or "").lstrip("/")
        return path if path else default_db
    except Exception:
        return default_db


class DatabaseManager:
    """
    Single responsibility: own Mongo connection lifecycle and provide collections.
    Reused by both Flask API process and Celery worker process.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self._mongo_uri = os.getenv("MONGO_URI", "mongodb://mongodb:27017/stock_analysis")
        self._db_name = _db_name_from_mongo_uri(self._mongo_uri, default_db="stock_analysis")

        self.client = None
        self.db = None

        self.collections = {
            "results": None,
            "jobs": None,
            "trend_survivors": None,
            "vcp_survivors": None,
            "leadership_survivors": None,
            "ticker_status": None,
        }

    def _ensure_indexes(self):
        """
        Creates indexes to support specific query patterns.
        This is idempotent (safe to run multiple times).
        """
        if self.collections["results"] is not None:
            # 1. "Show me the history of NVDA"
            # Background=True ensures building index doesn't lock the DB
            self.collections["results"].create_index(
                [("ticker", ASCENDING)], 
                background=True
            )
            
            # 2. "Show me all stocks that passed on Nov 12th"
            # Compound index might be useful here: job_id + processed_at
            self.collections["results"].create_index(
                [("processed_at", DESCENDING)], 
                background=True
            )
            
            # 3. "Show me results for this specific job run"
            self.collections["results"].create_index(
                [("job_id", ASCENDING)], 
                background=True
            )
            logger.info("Ensured indexes for screening_results.")

    def connect(self) -> bool:
        if self.client is not None and all(coll is not None for coll in self.collections.values()):
            return True

        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                self.client = MongoClient(self._mongo_uri, serverSelectionTimeoutMS=10000)
                self.client.admin.command("ping")

                self.db = self.client[self._db_name]
                self.collections["results"] = self.db["screening_results"]
                self.collections["jobs"] = self.db["screening_jobs"]
                self.collections["trend_survivors"] = self.db["trend_survivors"]
                self.collections["vcp_survivors"] = self.db["vcp_survivors"]
                self.collections["leadership_survivors"] = self.db["leadership_survivors"]
                self.collections["ticker_status"] = self.db["ticker_status"]

                logger.info("MongoDB connection successful.")
                self._ensure_indexes()
                return True
            except errors.ConnectionFailure as e:
                logger.error(f"MongoDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    self._reset()
                    return False

        return False

    def _reset(self) -> None:
        self.client = None
        self.db = None
        for key in self.collections:
            self.collections[key] = None

    def get_collections(self):
        if not self.connect():
            return (None, None, None, None, None, None)

        return (
            self.collections["results"],
            self.collections["jobs"],
            self.collections["trend_survivors"],
            self.collections["vcp_survivors"],
            self.collections["leadership_survivors"],
            self.collections["ticker_status"],
        )


def get_db_collections():
    db_manager = DatabaseManager()
    return db_manager.get_collections()
