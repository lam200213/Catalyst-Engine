# backend-services/monitoring-service/tests/services/test_watchlist_service_status_derivation.py
"""
Test suite for services/watchlist_service.py
Tests cover add_to_watchlist, add_or_upsert_ticker and get_watchlist functions
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call

# Import the module under test
from services.watchlist_service import (
    add_to_watchlist,
    get_watchlist,
)

# Import database client functions
from database import mongo_client

# ============================================================================
# TEST: get_watchlist() - Business Logic Requirements
# ============================================================================

class TestGetWatchlistBusinessLogic:
    """Test get_watchlist business logic and requirements"""

    @patch("services.watchlist_status_service.derive_refresh_lists")
    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_get_watchlist_delegates_status_derivation_to_status_service(
        self,
        mock_list_watchlist,
        mock_derive_refresh_lists,
        mock_db,
    ):
        """get_watchlist should delegate status logic to watchlist_status_service."""
        raw_item = {
            "user_id": "single_user_mode",
            "ticker": "DLGT",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "is_leader": True,
        }
        mock_list_watchlist.return_value = [raw_item]

        derived_item = dict(raw_item)
        derived_item["status"] = "Buy Ready"
        mock_derive_refresh_lists.return_value = ([derived_item], [])

        result = get_watchlist(mock_db, [])

        mock_derive_refresh_lists.assert_called_once()
        args, kwargs = mock_derive_refresh_lists.call_args
        passed_items = args[0]
        assert isinstance(passed_items, list)
        assert passed_items[0]["ticker"] == "DLGT"

        assert len(result["items"]) == 1
        returned = result["items"][0]
        assert returned["ticker"] == "DLGT"
        assert returned["status"] == "Buy Ready"

    @patch("services.watchlist_status_service.derive_refresh_lists")
    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_get_watchlist_preserves_contract_fields_after_status_derivation(
        self,
        mock_list_watchlist,
        mock_derive_refresh_lists,
        mock_db,
    ):
        """All contract fields must be preserved when status service is introduced."""
        raw_item = {
            "user_id": "single_user_mode",
            "ticker": "NET",
            "date_added": datetime.utcnow(),
            "is_favourite": True,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 85.10,
            "pivot_price": 86.00,
            "pivot_proximity_percent": -1.05,
            "is_leader": True,
        }
        mock_list_watchlist.return_value = [raw_item]

        derived_item = dict(raw_item)
        derived_item["status"] = "Buy Ready"
        mock_derive_refresh_lists.return_value = ([derived_item], [])

        result = get_watchlist(mock_db, [])

        item = result["items"][0]
        assert item["ticker"] == "NET"
        assert item["status"] == "Buy Ready"
        assert "date_added" in item
        assert "is_favourite" in item
        assert "last_refresh_status" in item
        assert "last_refresh_at" in item
        assert "failed_stage" in item
        assert "current_price" in item
        assert "pivot_price" in item
        assert "pivot_proximity_percent" in item
        assert "is_leader" in item

    @patch("services.watchlist_status_service.derive_refresh_lists")
    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_get_watchlist_handles_mixed_last_refresh_status_values(
        self,
        mock_list_watchlist,
        mock_derive_refresh_lists,
        mock_db,
    ):
        """Mixed PASS, FAIL, PENDING, UNKNOWN items should produce expected UI statuses."""
        base_time = datetime.utcnow()
        raw_items = [
            {
                "user_id": "single_user_mode",
                "ticker": "PEND",
                "date_added": base_time,
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
                "user_id": "single_user_mode",
                "ticker": "FAIL",
                "date_added": base_time,
                "is_favourite": False,
                "last_refresh_status": "FAIL",
                "last_refresh_at": base_time,
                "failed_stage": "screening",
                "current_price": 100.0,
                "pivot_price": None,
                "pivot_proximity_percent": None,
                "is_leader": False,
            },
            {
                "user_id": "single_user_mode",
                "ticker": "READY",
                "date_added": base_time,
                "is_favourite": False,
                "last_refresh_status": "PASS",
                "last_refresh_at": base_time,
                "failed_stage": None,
                "current_price": 98.0,
                "pivot_price": 100.0,
                "pivot_proximity_percent": -2.0,
                "is_leader": True,
            },
        ]
        mock_list_watchlist.return_value = raw_items

        derived_items = [
            dict(raw_items[0], status="Pending"),
            dict(raw_items[1], status="Failed"),
            dict(raw_items[2], status="Buy Ready"),
        ]
        mock_derive_refresh_lists.return_value = (derived_items, [])

        result = get_watchlist(mock_db, [])

        statuses = {i["ticker"]: i["status"] for i in result["items"]}
        assert statuses["PEND"] == "Pending"
        assert statuses["FAIL"] == "Failed"
        assert statuses["READY"] == "Buy Ready"

    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_status_derivation_buy_ready(
        self, mock_list_watchlist, mock_db
    ):
        """
        Verify status derivation: "Buy Ready" when:
        - last_refresh_status == "PASS"
        - pivot_price is not None
        - current_price is within buy range of pivot_price
        """
        buy_ready_item = {
            "user_id": "single_user_mode",
            "ticker": "NET",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 85.10,
            "pivot_price": 86.00,
            "pivot_proximity_percent": -1.05,
            "is_leader": True
        }
        
        mock_list_watchlist.return_value = [buy_ready_item]
        
        result = get_watchlist(mock_db, [])
        
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "Buy Ready", \
            "Should derive 'Buy Ready' status when near pivot"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_status_derivation_watch_when_no_pivot_and_no_signals(
        self,
        mock_list_watchlist,
        mock_db,
    ):
        """
        Verify status derivation: "Watch" when:
        - last_refresh_status == "PASS"
        - pivot_price is None (no clear pivot yet)
        - no actionable VCP/volume signals are present
        """
        buy_alert_item = {
            "user_id": "single_user_mode",
            "ticker": "CELH",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 60.25,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False,
        }

        mock_list_watchlist.return_value = [buy_alert_item]

        result = get_watchlist(mock_db, [])

        assert len(result["items"]) == 1
        derived = result["items"][0]
        assert derived["ticker"] == "CELH"
        assert derived["status"] == "Watch"


    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_status_derivation_watch(
        self, mock_list_watchlist, mock_db
    ):
        """
        Verify status derivation: "Watch" when:
        - last_refresh_status == "PASS"
        - current_price is far from pivot (not in buy range)
        """
        watch_item = {
            "user_id": "single_user_mode",
            "ticker": "ZEN",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 50.00,
            "pivot_price": 60.00,
            "pivot_proximity_percent": -16.67,  # Far from pivot
            "is_leader": False
        }
        
        mock_list_watchlist.return_value = [watch_item]
        
        result = get_watchlist(mock_db, [])
        
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "Watch", \
            "Should derive 'Watch' status when far from pivot"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_status_derivation_failed(
        self, mock_list_watchlist, mock_db
    ):
        """
        Verify status derivation: "Failed" when:
        - last_refresh_status == "FAIL"
        - failed_stage is not None
        """
        failed_item = {
            "user_id": "single_user_mode",
            "ticker": "GOOGL",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "FAIL",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": "screening",
            "current_price": 135.80,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False
        }
        
        mock_list_watchlist.return_value = [failed_item]
        
        result = get_watchlist(mock_db, [])
        
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "Failed", \
            "Should derive 'Failed' status when last_refresh_status is FAIL"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_status_derivation_pending(
        self, mock_list_watchlist, mock_db
    ):
        """
        Verify status derivation: "Pending" when:
        - last_refresh_status == "PENDING"
        """
        pending_item = {
            "user_id": "single_user_mode",
            "ticker": "NVDA",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PENDING",
            "last_refresh_at": None,
            "failed_stage": None,
            "current_price": None,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False
        }
        
        mock_list_watchlist.return_value = [pending_item]
        
        result = get_watchlist(mock_db, [])
        
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "Pending", \
            "Should derive 'Pending' status when not yet refreshed"
    
    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_status_pending_when_last_refresh_unknown(self, mock_list_watchlist, mock_db):
        """UNKNOWN health status should surface as Pending in the UI."""
        item = {
            "userid": "single_user_mode",
            "ticker": "UNKN",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "UNKNOWN",
            "lastrefreshat": None,
            "failed_stage": None,
            "currentprice": None,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "Pending"
# ============================================================================
# TEST: Status Derivation Business Logic
# ============================================================================

class TestStatusDerivationLogic:
    """Detailed tests for status derivation business logic"""
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_status_buy_ready_within_5_percent_of_pivot(
        self, mock_list_watchlist, mock_db
    ):
        """
        Verify "Buy Ready" status when current_price is within 5% below pivot
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "TEST1",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 95.50,  # 4.5% below pivot
            "pivot_price": 100.00,
            "pivot_proximity_percent": -4.5,
            "is_leader": False
        }
        
        mock_list_watchlist.return_value = [item]
        
        result = get_watchlist(mock_db, [])
        
        assert result["items"][0]["status"] == "Buy Ready", \
            "Should be 'Buy Ready' when within 5% of pivot"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_status_watch_beyond_5_percent_of_pivot(
        self, mock_list_watchlist, mock_db
    ):
        """
        Verify "Watch" status when current_price is > 5% below pivot
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "TEST2",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 90.00,  # 10% below pivot
            "pivot_price": 100.00,
            "pivot_proximity_percent": -10.0,
            "is_leader": False
        }
        
        mock_list_watchlist.return_value = [item]
        
        result = get_watchlist(mock_db, [])
        
        assert result["items"][0]["status"] == "Watch", \
            "Should be 'Watch' when > 5% from pivot"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_status_buy_ready_exact_pivot_price(
        self, mock_list_watchlist, mock_db
    ):
        """
        Verify "Buy Ready" status when current_price equals pivot_price
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "TEST3",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 100.00,  # Exactly at pivot
            "pivot_price": 100.00,
            "pivot_proximity_percent": 0.0,
            "is_leader": False
        }
        
        mock_list_watchlist.return_value = [item]
        
        result = get_watchlist(mock_db, [])
        
        assert result["items"][0]["status"] == "Buy Ready", \
            "Should be 'Buy Ready' when at exact pivot"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_status_watch_default_when_pass_no_actionable_signals(self, mock_list_watchlist, mock_db):
        """PASS with no pivot, no pullback, no volume signal => Watch."""
        item = {
            "userid": "single_user_mode",
            "ticker": "BASE",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "lastrefreshat": datetime.utcnow(),
            "failed_stage": None,
            "currentprice": 50.0,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False,
            "has_pivot": False,
            "is_at_pivot": False,
            "has_pullback_setup": False,
            "vollast": 1_000_000,
            "vol50davg": 1_000_000,
            "vol_vs_50d_ratio": 1.0,
            "day_change_pct": 0.0,
            "pattern_age_days": 10,
            "vcp_pass": False,
            "is_pivot_good": False,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert result["items"][0]["status"] == "Watch"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_status_watch_when_pattern_stale(self, mock_list_watchlist, mock_db):
        """Very old VCP pattern should downgrade to Watch even if PASS."""
        item = {
            "userid": "single_user_mode",
            "ticker": "STALE",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "lastrefreshat": datetime.utcnow(),
            "failed_stage": None,
            "currentprice": 100.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "is_leader": False,
            "has_pivot": True,
            "is_at_pivot": True,
            "has_pullback_setup": False,
            "vollast": 800_000,
            "vol50davg": 1_000_000,
            "vol_vs_50d_ratio": 0.8,
            "day_change_pct": 0.5,
            "pattern_age_days": 120,  # above freshness threshold
            "vcp_pass": True,
            "is_pivot_good": True,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert result["items"][0]["status"] == "Watch"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_status_buy_alert_maturing_pivot_with_volume_contraction(self, mock_list_watchlist, mock_db):
        """Maturing pivot + contracting volume => Buy Alert."""
        item = {
            "userid": "single_user_mode",
            "ticker": "MTRN",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "lastrefreshat": datetime.utcnow(),
            "failed_stage": None,
            "currentprice": 90.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -10.0,  # outside Buy Ready band
            "is_leader": False,
            "has_pivot": True,
            "is_at_pivot": False,
            "has_pullback_setup": False,
            "vollast": 700_000,
            "vol50davg": 1_000_000,
            "vol_vs_50d_ratio": 0.7,  # contracting vs 50D
            "day_change_pct": 0.5,
            "pattern_age_days": 20,
            "vcp_pass": True,
            "is_pivot_good": False,  # not yet actionable
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert result["items"][0]["status"] == "Buy Alert"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_status_buy_alert_pullback_zone_with_volume_contraction(self, mock_list_watchlist, mock_db):
        """Confirmed pullback zone + contracted volume => Buy Alert."""
        item = {
            "userid": "single_user_mode",
            "ticker": "PBACK",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "lastrefreshat": datetime.utcnow(),
            "failed_stage": None,
            "currentprice": 95.0,
            "pivot_price": 110.0,
            "pivot_proximity_percent": -13.6,
            "is_leader": False,
            "has_pivot": True,
            "is_at_pivot": False,
            "has_pullback_setup": True,  # in PB zone
            "vollast": 600_000,
            "vol50davg": 800_000,
            "vol_vs_50d_ratio": 0.75,  # 75% of 50D
            "day_change_pct": -0.5,    # mild pullback
            "pattern_age_days": 25,
            "vcp_pass": True,
            "is_pivot_good": False,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert result["items"][0]["status"] == "Buy Alert"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_status_buy_alert_pullback_zone_with_volume_contraction(self, mock_list_watchlist, mock_db):
        """Confirmed pullback zone + contracted volume => Buy Alert."""
        item = {
            "userid": "single_user_mode",
            "ticker": "PBACK",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "lastrefreshat": datetime.utcnow(),
            "failed_stage": None,
            "currentprice": 95.0,
            "pivot_price": 110.0,
            "pivot_proximity_percent": -13.6,
            "is_leader": False,
            "has_pivot": True,
            "is_at_pivot": False,
            "has_pullback_setup": True,  # in PB zone
            "vollast": 600_000,
            "vol50davg": 800_000,
            "vol_vs_50d_ratio": 0.75,  # 75% of 50D
            "day_change_pct": -0.5,    # mild pullback
            "pattern_age_days": 25,
            "vcp_pass": True,
            "is_pivot_good": False,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert result["items"][0]["status"] == "Buy Alert"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_status_watch_when_high_volume_distribution_guardrail_trips(self, mock_list_watchlist, mock_db):
        """High-volume down day overrides Buy Alert/Ready to Watch."""
        item = {
            "userid": "single_user_mode",
            "ticker": "DIST",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "lastrefreshat": datetime.utcnow(),
            "failed_stage": None,
            "currentprice": 96.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -4.0,  # would normally be Buy Ready
            "is_leader": False,
            "has_pivot": True,
            "is_at_pivot": True,
            "has_pullback_setup": False,
            "vollast": 3_000_000,
            "vol50davg": 1_000_000,
            "vol_vs_50d_ratio": 3.0,   # spike
            "day_change_pct": -4.0,   # big down day
            "pattern_age_days": 20,
            "vcp_pass": True,
            "is_pivot_good": True,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert result["items"][0]["status"] == "Watch"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_status_buy_ready_preferred_when_buy_alert_conditions_also_true(self, mock_list_watchlist, mock_db):
        """When both Buy Ready and Buy Alert conditions hold, Buy Ready wins."""
        item = {
            "userid": "single_user_mode",
            "ticker": "PIVPB",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "lastrefreshat": datetime.utcnow(),
            "failed_stage": None,
            "currentprice": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,  # Buy Ready band
            "is_leader": True,
            "has_pivot": True,
            "is_at_pivot": True,
            "has_pullback_setup": True,       # also looks like PB setup
            "vollast": 800_000,
            "vol50davg": 1_000_000,
            "vol_vs_50d_ratio": 0.8,          # contracting
            "day_change_pct": 1.0,
            "pattern_age_days": 15,
            "vcp_pass": True,
            "is_pivot_good": True,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert result["items"][0]["status"] == "Buy Ready"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_status_never_buy_alert_or_ready_when_last_refresh_not_pass(self, mock_list_watchlist, mock_db):
        """Statuses Buy Alert / Buy Ready must only occur when last_refresh_status is PASS."""
        base = {
            "userid": "single_user_mode",
            "ticker": "STAT",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "lastrefreshat": None,
            "failed_stage": None,
            "currentprice": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "is_leader": False,
            "has_pivot": True,
            "is_at_pivot": True,
            "has_pullback_setup": True,
            "vollast": 800_000,
            "vol50davg": 1_000_000,
            "vol_vs_50d_ratio": 0.8,
            "day_change_pct": 1.0,
            "pattern_age_days": 10,
            "vcp_pass": True,
            "is_pivot_good": True,
        }

        for status in ["PENDING", "UNKNOWN", "FAIL"]:
            item = dict(base)
            item["last_refresh_status"] = status
            mock_list_watchlist.return_value = [item]

            result = get_watchlist(mock_db)
            ui_status = result["items"][0]["status"]

            assert ui_status not in ("Buy Alert", "Buy Ready")

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_buy_ready_requires_vcp_pass_and_good_pivot(self, mock_list_watchlist, mock_db):
        """
        Rich mode: Buy Ready must not be emitted if VCP or pivot quality are false,
        even when pivot proximity is in the buy band.
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "BADVCP",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "is_leader": False,
            # Rich-mode signals present:
            "has_pivot": False,
            "has_pullback_setup": False,
            "vol_vs_50d_ratio": 1.0,
            "day_change_pct": 0.5,
            "pattern_age_days": 10,
            "vcp_pass": False,         # gate should fail here
            "is_pivot_good": False,    # and here
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert len(result["items"]) == 1
        derived = result["items"][0]
        assert derived["ticker"] == "BADVCP"
        # Must not be Buy Ready when VCP gating fails
        assert derived["status"] == "Watch"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_buy_ready_when_vcp_pass_and_good_pivot_and_in_band(self, mock_list_watchlist, mock_db):
        """
        Rich mode: Buy Ready when VCP passes, pivot is good, and price is within buy band.
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "GOODVCP",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "is_leader": True,
            "has_pivot": True,
            "has_pullback_setup": False,
            "vol_vs_50d_ratio": 0.9,
            "day_change_pct": 1.0,
            "pattern_age_days": 15,
            "vcp_pass": True,
            "is_pivot_good": True,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        assert len(result["items"]) == 1
        derived = result["items"][0]
        assert derived["ticker"] == "GOODVCP"
        assert derived["status"] == "Buy Ready"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_pattern_age_at_threshold_still_actionable(self, mock_list_watchlist, mock_db):
        """
        Pattern age at freshness threshold remains actionable (Buy Ready).
        Assumes threshold is 90 days per design docs.
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "FRESH90",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "is_leader": False,
            "has_pivot": True,
            "has_pullback_setup": False,
            "vol_vs_50d_ratio": 0.9,
            "day_change_pct": 0.5,
            "pattern_age_days": 90,  # at threshold
            "vcp_pass": True,
            "is_pivot_good": True,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        derived = result["items"][0]
        assert derived["ticker"] == "FRESH90"
        assert derived["status"] == "Buy Ready"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_pattern_age_above_threshold_downgrades_to_watch(self, mock_list_watchlist, mock_db):
        """
        Pattern age strictly above freshness threshold downgrades to Watch even if other
        Buy Ready conditions are met.
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "STALE91",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "is_leader": False,
            "has_pivot": True,
            "has_pullback_setup": False,
            "vol_vs_50d_ratio": 0.9,
            "day_change_pct": 0.5,
            "pattern_age_days": 91,  # above threshold
            "vcp_pass": True,
            "is_pivot_good": True,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        derived = result["items"][0]
        assert derived["ticker"] == "STALE91"
        assert derived["status"] == "Watch"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_volume_spike_guardrail_triggers_at_threshold(self, mock_list_watchlist, mock_db):
        """
        High-volume down day at guardrail threshold must downgrade to Watch.
        Assumes spike threshold is 3.0x 50D volume.
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "SPK3X",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "is_leader": False,
            "has_pivot": True,
            "has_pullback_setup": False,
            "vol_vs_50d_ratio": 3.0,   # at threshold
            "day_change_pct": -4.0,    # big down day
            "pattern_age_days": 20,
            "vcp_pass": True,
            "is_pivot_good": True,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        derived = result["items"][0]
        assert derived["ticker"] == "SPK3X"
        assert derived["status"] == "Watch"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_volume_spike_guardrail_not_triggered_below_threshold(self, mock_list_watchlist, mock_db):
        """
        Volume spike just below threshold should not trigger guardrail and allow
        normal Buy Ready logic.
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "SPK2_9X",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "is_leader": False,
            "has_pivot": True,
            "has_pullback_setup": False,
            "vol_vs_50d_ratio": 2.9,
            "day_change_pct": -1.0,
            "pattern_age_days": 20,
            "vcp_pass": True,
            "is_pivot_good": True,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        derived = result["items"][0]
        assert derived["ticker"] == "SPK2_9X"
        assert derived["status"] == "Buy Ready"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_pullback_zone_without_volume_contraction_is_watch(self, mock_list_watchlist, mock_db):
        """
        Pullback setup without volume contraction should remain Watch, not Buy Alert.
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "PB_NO_CONTRACT",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 95.0,
            "pivot_price": 110.0,
            "pivot_proximity_percent": -13.6,
            "is_leader": False,
            "has_pivot": True,
            "has_pullback_setup": True,
            "vol_vs_50d_ratio": 1.1,   # no contraction
            "day_change_pct": -0.5,
            "pattern_age_days": 25,
            "vcp_pass": True,
            "is_pivot_good": False,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        derived = result["items"][0]
        assert derived["ticker"] == "PB_NO_CONTRACT"
        assert derived["status"] == "Watch"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_rich_mode_does_not_use_no_pivot_buy_alert_fallback(self, mock_list_watchlist, mock_db):
        """
        In rich mode, PASS with no pivot and no pullback setup should be Watch,
        not Buy Alert.
        """
        item = {
            "user_id": "single_user_mode",
            "ticker": "NOPIVOT_RICH",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 50.0,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False,
            "has_pivot": False,
            "has_pullback_setup": False,
            "vol_vs_50d_ratio": 1.0,
            "day_change_pct": 0.0,
            "pattern_age_days": 10,
            "vcp_pass": False,
            "is_pivot_good": False,
        }
        mock_list_watchlist.return_value = [item]

        result = get_watchlist(mock_db)

        derived = result["items"][0]
        assert derived["ticker"] == "NOPIVOT_RICH"
        assert derived["status"] == "Watch"

    @patch("services.watchlist_service.mongo_client.list_watchlist_excluding")
    def test_is_leader_does_not_change_status(self, mock_list_watchlist, mock_db):
        """
        Leadership flag is a separate UI badge and must not change status.
        """
        base = {
            "user_id": "single_user_mode",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 98.0,
            "pivot_price": 100.0,
            "pivot_proximity_percent": -2.0,
            "has_pivot": True,
            "has_pullback_setup": False,
            "vol_vs_50d_ratio": 0.9,
            "day_change_pct": 1.0,
            "pattern_age_days": 20,
            "vcp_pass": True,
            "is_pivot_good": True,
        }
        leader = dict(base, ticker="LEADER", is_leader=True)
        non_leader = dict(base, ticker="NLEAD", is_leader=False)

        mock_list_watchlist.return_value = [leader, non_leader]

        result = get_watchlist(mock_db)

        assert len(result["items"]) == 2
        statuses = {item["ticker"]: item["status"] for item in result["items"]}
        assert statuses["LEADER"] == statuses["NLEAD"]
        assert statuses["LEADER"] == "Buy Ready"

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
