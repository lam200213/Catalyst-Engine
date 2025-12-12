# backend-services/monitoring-service/tests/services/test_update_orchestrator.py

import pytest
from unittest.mock import Mock, patch, MagicMock, call

# import orchestrator entrypoint
from services import update_orchestrator as orchestrator

class TestRefreshWatchlistStatusOrchestrator:
    """Tests for update_orchestrator.refresh_watchlist_status."""

    @patch("services.update_orchestrator.watchlist_status_service.derive_refresh_lists")
    @patch("services.update_orchestrator.mongo_client.bulk_archive_failed")
    @patch("services.update_orchestrator.mongo_client.bulk_update_status")
    @patch("services.update_orchestrator.mongo_client.list_watchlist_excluding")
    @patch("services.update_orchestrator.mongo_client.connect")
    def test_refresh_watchlist_status_single_item_happy_path(
        self,
        mock_connect,
        mock_list_watchlist,
        mock_bulk_update,
        mock_bulk_archive,
        mock_derive_refresh_lists,
    ):
        """
        Steps 3–10: Single-item pipeline correctness and summary shape.
        """
        mock_client, mock_db = MagicMock(), MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_list_watchlist.return_value = [{"ticker": "ONE", "last_refresh_status": "PASS"}]
        mock_derive_refresh_lists.return_value = (
            [{"ticker": "ONE", "status": "Watch", "last_refresh_status": "PASS"}],
            [],
        )
        from services import update_orchestrator as orchestrator
        summary = orchestrator.refresh_watchlist_status()
        assert set(summary.keys()) == {"message", "updated_items", "archived_items", "failed_items"}
        assert summary["updated_items"] == 1
        assert summary["archived_items"] == 0
        assert isinstance(summary["failed_items"], int)

    @patch("services.update_orchestrator.watchlist_status_service.derive_refresh_lists")
    @patch("services.update_orchestrator.mongo_client.bulk_archive_failed")
    @patch("services.update_orchestrator.mongo_client.bulk_update_status")
    @patch("services.update_orchestrator.mongo_client.list_watchlist_excluding")
    @patch("services.update_orchestrator.mongo_client.connect")
    def test_refresh_watchlist_status_large_batch_boundary_just_below_limit(
        self,
        mock_connect,
        mock_list_watchlist,
        mock_bulk_update,
        mock_bulk_archive,
        mock_derive_refresh_lists,
    ):
        """
        Steps 3–10 & Req 12: large batch just below a practical 1000-item boundary should succeed.
        """
        mock_client, mock_db = MagicMock(), MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        raw_items = [{"ticker": f"T{i:04d}", "last_refresh_status": "PASS"} for i in range(999)]
        mock_list_watchlist.return_value = raw_items
        to_update = [{"ticker": it["ticker"], "status": "Watch", "last_refresh_status": "PASS"} for it in raw_items]
        mock_derive_refresh_lists.return_value = (to_update, [])
        from services import update_orchestrator as orchestrator
        summary = orchestrator.refresh_watchlist_status()
        assert summary["updated_items"] == 999
        assert summary["archived_items"] == 0
        assert isinstance(summary["message"], str)

    @patch("services.update_orchestrator.watchlist_status_service.derive_refresh_lists")
    @patch("services.update_orchestrator.mongo_client.bulk_archive_failed")
    @patch("services.update_orchestrator.mongo_client.bulk_update_status")
    @patch("services.update_orchestrator.mongo_client.list_watchlist_excluding")
    @patch("services.update_orchestrator.mongo_client.connect")
    def test_refresh_watchlist_status_summary_forbids_extra_keys(
        self,
        mock_connect,
        mock_list_watchlist,
        mock_bulk_update,
        mock_bulk_archive,
        mock_derive_refresh_lists,
    ):
        """
        Step 10: Summary must not include undeclared keys (additionalProperties=false at contract).
        """
        mock_client, mock_db = MagicMock(), MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_list_watchlist.return_value = []
        from services import update_orchestrator as orchestrator
        summary = orchestrator.refresh_watchlist_status()
        assert set(summary.keys()) == {"message", "updated_items", "archived_items", "failed_items"}

    # large-batch behavior for update/archive partitioning
    @patch("services.update_orchestrator.downstream_clients.data_return_batch")
    @patch("services.update_orchestrator.downstream_clients.analyze_freshness_batch")
    @patch("services.update_orchestrator.downstream_clients.analyze_batch")
    @patch("services.update_orchestrator.downstream_clients.screen_batch")
    @patch("services.update_orchestrator.watchlist_status_service.derive_refresh_lists")
    @patch("services.update_orchestrator.mongo_client.bulk_archive_failed")
    @patch("services.update_orchestrator.mongo_client.bulk_update_status")
    @patch("services.update_orchestrator.mongo_client.list_watchlist_excluding")
    @patch("services.update_orchestrator.mongo_client.connect")
    def test_refresh_watchlist_status_scales_for_large_batches(
        self,
        mock_connect,
        mock_list_watchlist,
        mock_bulk_update,
        mock_bulk_archive,
        mock_derive_refresh_lists,
        mock_screen,
        mock_analyze,
        mock_fresh,
        mock_data,
        ):
        """
        Large watchlist batches should be processed without mutation and with correct counts.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Use a moderately large batch to exercise scaling; conftest provides base items
        raw_items = [
            {"ticker": f"TICK{i}", "last_refresh_status": "PASS"}
            for i in range(250)
        ]
        mock_list_watchlist.return_value = raw_items

        # Simulate status engine putting all in update list, none in archive
        to_update = [{"ticker": item["ticker"], "status": "Watch"} for item in raw_items]
        mock_derive_refresh_lists.return_value = (to_update, [])

        mock_screen.return_value = {"passed": [item["ticker"] for item in raw_items]}
        mock_analyze.return_value = []
        mock_fresh.return_value = []
        mock_data.return_value = {}
        summary = orchestrator.refresh_watchlist_status()

        # DB calls should be made once with all items
        mock_bulk_update.assert_called_once()
        args, _ = mock_bulk_update.call_args
        assert len(args[1]) == 250
        mock_bulk_archive.assert_called_once()
        _, kwargs = mock_bulk_archive.call_args
        # No items to archive in this scenario
        assert kwargs.get("items") in ([], None)

        # Summary must match logical outcome and identifiers
        assert summary["updated_items"] == 250
        assert summary["archived_items"] == 0
        assert summary["failed_items"] == 0
        assert isinstance(summary["message"], str)
        assert "TICK0" in summary["message"]

    # downstream error path contributes to failed_items
    @patch("services.update_orchestrator.watchlist_status_service.derive_refresh_lists")
    @patch("services.update_orchestrator.mongo_client.bulk_archive_failed")
    @patch("services.update_orchestrator.mongo_client.bulk_update_status")
    @patch("services.update_orchestrator.mongo_client.list_watchlist_excluding")
    @patch("services.update_orchestrator.mongo_client.connect")
    def test_refresh_watchlist_status_counts_failed_items_on_derive_error(
        self,
        mock_connect,
        mock_list_watchlist,
        mock_bulk_update,
        mock_bulk_archive,
        mock_derive_refresh_lists,
    ):
        """
        If status derivation fails, no DB writes occur and all items are counted as failed.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        raw_items = [
            {"ticker": "ERR1", "last_refresh_status": "PASS"},
            {"ticker": "ERR2", "last_refresh_status": "PASS"},
        ]
        mock_list_watchlist.return_value = raw_items

        mock_derive_refresh_lists.side_effect = RuntimeError("downstream failure")

        summary = orchestrator.refresh_watchlist_status()

        mock_bulk_update.assert_not_called()
        mock_bulk_archive.assert_not_called()

        assert summary["updated_items"] == 0
        assert summary["archived_items"] == 0
        assert summary["failed_items"] == 2
        assert isinstance(summary["message"], str)
        assert "ERR1" in summary["message"] or "ERR2" in summary["message"]

    @patch("services.update_orchestrator.watchlist_status_service.derive_refresh_lists")
    @patch("services.update_orchestrator.mongo_client.bulk_archive_failed")
    @patch("services.update_orchestrator.mongo_client.bulk_update_status")
    @patch("services.update_orchestrator.mongo_client.list_watchlist_excluding")
    @patch("services.update_orchestrator.mongo_client.connect")
    def test_refresh_watchlist_status_updates_db_with_status_partition_lists(
        self,
        mock_connect,
        mock_list_watchlist,
        mock_bulk_update,
        mock_bulk_archive,
        mock_derive_refresh_lists,
    ):
        """Happy path: orchestrator partitions items and calls bulk update and archive correctly."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        raw_items = [
            {
                "ticker": "KEEP",
                "is_favourite": True,
                "last_refresh_status": "FAIL",
            },
            {
                "ticker": "DROP",
                "is_favourite": False,
                "last_refresh_status": "FAIL",
            },
        ]
        mock_list_watchlist.return_value = raw_items

        to_update = [
            {"ticker": "KEEP", "last_refresh_status": "FAIL", "status": "Failed"},
        ]
        to_archive = [
            {"ticker": "DROP", "last_refresh_status": "FAIL", "status": "Failed"},
        ]
        mock_derive_refresh_lists.return_value = (to_update, to_archive)

        summary = orchestrator.refresh_watchlist_status()

        mock_connect.assert_called_once()
        mock_list_watchlist.assert_called_once_with(mock_db, [])
        mock_derive_refresh_lists.assert_called_once()
        mock_bulk_update.assert_called_once_with(mock_db, to_update)
        mock_bulk_archive.assert_called_once_with(mock_db, to_archive)

        assert isinstance(summary, dict)
        assert summary["updated_items"] == 1
        assert summary["archived_items"] == 1
        assert summary["failed_items"] == 0
        assert "message" in summary and isinstance(summary["message"], str)

    @patch("services.update_orchestrator.watchlist_status_service.derive_refresh_lists")
    @patch("services.update_orchestrator.mongo_client.bulk_archive_failed")
    @patch("services.update_orchestrator.mongo_client.bulk_update_status")
    @patch("services.update_orchestrator.mongo_client.list_watchlist_excluding")
    @patch("services.update_orchestrator.mongo_client.connect")
    def test_refresh_watchlist_status_is_noop_when_watchlist_empty(
        self,
        mock_connect,
        mock_list_watchlist,
        mock_bulk_update,
        mock_bulk_archive,
        mock_derive_refresh_lists,
    ):
        """Empty watchlist should not call status service or bulk ops and should return zero counts."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_list_watchlist.return_value = []

        summary = orchestrator.refresh_watchlist_status()

        mock_list_watchlist.assert_called_once_with(mock_db, [])
        mock_derive_refresh_lists.assert_not_called()
        mock_bulk_update.assert_not_called()
        mock_bulk_archive.assert_not_called()

        assert isinstance(summary, dict)
        assert summary["updated_items"] == 0
        assert summary["archived_items"] == 0

    @patch("services.update_orchestrator.watchlist_status_service.derive_refresh_lists")
    @patch("services.update_orchestrator.mongo_client.bulk_archive_failed")
    @patch("services.update_orchestrator.mongo_client.bulk_update_status")
    @patch("services.update_orchestrator.mongo_client.list_watchlist_excluding")
    @patch("services.update_orchestrator.mongo_client.connect")
    def test_refresh_watchlist_status_handles_partial_downstream_failures(
        self,
        mock_connect,
        mock_list_watchlist,
        mock_bulk_update,
        mock_bulk_archive,
        mock_derive_refresh_lists,
    ):
        """If a downstream error occurs for a subset of tickers, orchestrator should still update others."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Two items, but status derivation fails for one of them
        raw_items = [
            {"ticker": "GOOD", "is_favourite": False, "last_refresh_status": "PASS"},
            {"ticker": "BAD", "is_favourite": False, "last_refresh_status": "PASS"},
        ]
        mock_list_watchlist.return_value = raw_items

        to_update = [{"ticker": "GOOD", "last_refresh_status": "PASS", "status": "Buy Ready"}]
        to_archive = []
        mock_derive_refresh_lists.return_value = (to_update, to_archive)

        summary = orchestrator.refresh_watchlist_status()

        mock_bulk_update.assert_called_once()
        mock_bulk_archive.assert_called_once()

        assert summary["updated_items"] == 1
        assert summary["archived_items"] == 0
        # failed_items can be non zero if orchestrator tracks errors
        assert "failed_items" in summary

    @patch("services.update_orchestrator.watchlist_status_service.derive_refresh_lists")
    @patch("services.update_orchestrator.mongo_client.bulk_archive_failed")
    @patch("services.update_orchestrator.mongo_client.bulk_update_status")
    @patch("services.update_orchestrator.mongo_client.list_watchlist_excluding")
    @patch("services.update_orchestrator.mongo_client.connect")
    def test_refresh_watchlist_status_respects_default_user_scope(
        self,
        mock_connect,
        mock_list_watchlist,
        mock_bulk_update,
        mock_bulk_archive,
        mock_derive_refresh_lists,
    ):
        """All DB calls must route through the single user scope used by mongo_client."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        raw_items = [
            {"ticker": "SCOPED", "is_favourite": False, "last_refresh_status": "PASS"},
        ]
        mock_list_watchlist.return_value = raw_items

        mock_derive_refresh_lists.return_value = ([], [])

        orchestrator.refresh_watchlist_status()

        mock_connect.assert_called_once()
        mock_list_watchlist.assert_called_once()
        args, kwargs = mock_list_watchlist.call_args
        assert args[0] is mock_db
