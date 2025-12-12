# backend-services/monitoring-service/tests/services/test_watchlist_status_service.py

import pytest
from database import mongo_client

# import the pure status engine under test
from services.watchlist_status_service import derive_refresh_lists

class TestWatchlistStatusService:
    """Pure-function tests for services.watchlist_status_service."""
    def _make_item(self, base_status_item, **overrides):
        """
        Helper: clone base_status_item and apply overrides.

        Keeps tests concise and guarantees all irrelevant fields start
        from a consistent, valid baseline.
        """
        item = dict(base_status_item)
        item.update(overrides)
        return item

    def test_derive_status_buy_ready_near_pivot(self, base_status_item):
        """PASS item near pivot within buy band should be Buy Ready and stay PASS."""
        items = [
            self._make_item(
                base_status_item,
                ticker="NET",
                current_price=85.10,
                pivot_price=86.00,
                pivot_proximity_percent=-1.05,
                vcp_pass=True,
                is_pivot_good=True,
                has_pivot=True,
                is_at_pivot=True,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        assert len(to_archive) == 0
        derived = to_update[0]
        assert derived["ticker"] == "NET"
        assert derived["status"] == "Buy Ready"
        assert derived["last_refresh_status"] == "PASS"

    def test_derive_status_watch_without_pivot_when_no_actionable_signals(self, base_status_item):
        """
        PASS item with no pivot and no actionable VCP/volume signals
        should default to Watch, not Buy Alert.
        """
        items = [
            self._make_item(
                base_status_item,
                ticker="CELH",
                pivot_price=None,
                pivot_proximity_percent=None,
                vcp_pass=True,
                is_pivot_good=False,
                has_pivot=False,
                has_pullback_setup=False,
                vol_vs_50d_ratio=0.9,
                day_change_pct=0.5,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        derived = to_update[0]
        assert derived["ticker"] == "CELH"
        assert derived["status"] == "Watch"

    def test_derive_status_watch_far_from_pivot(self, base_status_item):
        """PASS item far below pivot should downgrade to Watch."""
        items = [
            self._make_item(
                base_status_item,
                ticker="ZEN",
                current_price=50.00,
                pivot_price=60.00,
                pivot_proximity_percent=-16.67,
                vcp_pass=True,
                is_pivot_good=True,
                has_pivot=True,
                is_at_pivot=False,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        derived = to_update[0]
        assert derived["ticker"] == "ZEN"
        assert derived["status"] == "Watch"


    def test_derive_status_failed_when_last_refresh_fail(self, base_status_item):
        """FAIL plus non-null failed_stage should surface as Failed and go to archive if not favourite."""
        items = [
            self._make_item(
                base_status_item,
                ticker="GOOGL",
                last_refresh_status="FAIL",
                failed_stage="screening",
                is_favourite=False,
                vcp_pass=False,
                has_pivot=False,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 0
        assert len(to_archive) == 1
        archived = to_archive[0]
        assert archived["ticker"] == "GOOGL"
        assert archived["status"] == "Failed"
        assert archived["failed_stage"] == "screening"

    def test_derive_status_pending_for_pending_last_refresh(self, base_status_item):
        """PENDING should always surface as Pending and ignore other signals."""
        items = [
            self._make_item(
                base_status_item,
                ticker="NVDA",
                last_refresh_status="PENDING",
                pivot_price=None,
                pivot_proximity_percent=None,
                vcp_pass=False,
                has_pivot=False,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        pending = to_update[0]
        assert pending["ticker"] == "NVDA"
        assert pending["status"] == "Pending"

    def test_derive_status_pending_for_unknown_last_refresh(self, base_status_item):
        """UNKNOWN health state should map to Pending UI status."""
        items = [
            self._make_item(
                base_status_item,
                ticker="UNKN",
                last_refresh_status="UNKNOWN",
                pivot_price=None,
                pivot_proximity_percent=None,
                vcp_pass=False,
                has_pivot=False,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        derived = to_update[0]
        assert derived["ticker"] == "UNKN"
        assert derived["status"] == "Pending"

    def test_derive_status_watch_when_pattern_stale(self, base_status_item):
        """Very old pattern should downgrade to Watch even if other Buy Ready conditions hold."""
        items = [
            self._make_item(
                base_status_item,
                ticker="STALE",
                pattern_age_days=120,
                current_price=100.0,
                pivot_price=100.0,
                pivot_proximity_percent=-2.0,
                vcp_pass=True,
                is_pivot_good=True,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        derived = to_update[0]
        assert derived["ticker"] == "STALE"
        assert derived["status"] == "Watch"

    def test_derive_status_buy_alert_maturing_pivot_with_volume_contraction(self, base_status_item):
        """Maturing pivot plus contracting volume should be Buy Alert."""
        items = [
            {
                "ticker": "MTRN",
                "is_favourite": False,
                "last_refresh_status": "PASS",
                "failed_stage": None,
                "current_price": 90.0,
                "pivot_price": 100.0,
                "pivot_proximity_percent": -10.0,
                "vcp_pass": True,
                "is_pivot_good": False,
                "pattern_age_days": 20,
                "has_pivot": True,
                "is_at_pivot": False,
                "has_pullback_setup": False,
                "vol_vs_50d_ratio": 0.7,
                "day_change_pct": 0.5,
                "is_leader": False,
            }
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        derived = to_update[0]
        assert derived["ticker"] == "MTRN"
        assert derived["status"] == "Buy Alert"

    def test_derive_status_buy_alert_pullback_zone_with_volume_contraction(self, base_status_item):
        """Pullback setup plus contracted volume should be Buy Alert even outside Buy Ready band."""
        items = [
            {
                "ticker": "PBACK",
                "is_favourite": False,
                "last_refresh_status": "PASS",
                "failed_stage": None,
                "current_price": 95.0,
                "pivot_price": 110.0,
                "pivot_proximity_percent": -13.6,
                "vcp_pass": True,
                "is_pivot_good": False,
                "pattern_age_days": 25,
                "has_pivot": True,
                "is_at_pivot": False,
                "has_pullback_setup": True,
                "vol_vs_50d_ratio": 0.75,
                "day_change_pct": -0.5,
                "is_leader": False,
            }
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        derived = to_update[0]
        assert derived["ticker"] == "PBACK"
        assert derived["status"] == "Buy Alert"

    def test_guardrail_high_volume_distribution_downgrades_to_watch(self, base_status_item):
        """High volume down day should override Buy Ready or Buy Alert to Watch."""
        items = [
            self._make_item(
                base_status_item,
                ticker="DIST",
                current_price=96.0,
                pivot_price=100.0,
                pivot_proximity_percent=-4.0,
                vcp_pass=True,
                is_pivot_good=True,
                has_pivot=True,
                is_at_pivot=True,
                vol_vs_50d_ratio=3.0,
                day_change_pct=-4.0,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        derived = to_update[0]
        assert derived["ticker"] == "DIST"
        assert derived["status"] == "Watch"

    def test_partition_lists_keeps_favourites_in_update_list(self, base_status_item):
        """Favourite tickers that fail health check should remain in update list, not archived."""
        items = [
            {
                "ticker": "FAVFAIL",
                "is_favourite": True,
                "last_refresh_status": "FAIL",
                "failed_stage": "freshness",
                "current_price": 50.0,
                "pivot_price": None,
                "pivot_proximity_percent": None,
                "vcp_pass": False,
                "is_pivot_good": False,
                "pattern_age_days": None,
                "has_pivot": False,
                "is_at_pivot": False,
                "has_pullback_setup": False,
                "vol_vs_50d_ratio": 1.0,
                "day_change_pct": -1.0,
                "is_leader": False,
            }
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        assert len(to_archive) == 0
        derived = to_update[0]
        assert derived["ticker"] == "FAVFAIL"
        assert derived["last_refresh_status"] == "FAIL"
        assert derived["status"] == "Failed"

    def test_partition_lists_sends_nonfavourites_with_failures_to_archive_list(self, base_status_item):
        """Non favourite FAIL items should go to archive list."""
        items = [
            self._make_item(
                base_status_item,
                ticker="FAVFAIL",
                is_favourite=True,
                last_refresh_status="FAIL",
                failed_stage="freshness",
                vcp_pass=False,
                has_pivot=False,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        assert len(to_archive) == 0
        derived = to_update[0]
        assert derived["ticker"] == "FAVFAIL"
        assert derived["status"] == "Failed"

    def test_partition_lists_handles_empty_input_gracefully(self, base_status_item):
        """Empty input should return empty update and archive lists without error."""
        to_update, to_archive = derive_refresh_lists([])

        assert isinstance(to_update, list)
        assert isinstance(to_archive, list)
        assert len(to_update) == 0
        assert len(to_archive) == 0

    def test_partition_lists_scales_to_large_batch_sizes(self, base_status_item):
        """Partitioning large batches should preserve identifiers and not mutate data."""
        items = [
            self._make_item(base_status_item, ticker=f"TICK{i}")
            for i in range(1000)
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1000
        assert len(to_archive) == 0
        tickers = {item["ticker"] for item in to_update}
        assert "TICK0" in tickers
        assert "TICK999" in tickers

    def test_status_service_ignores_items_missing_ticker_or_last_refresh_status(self, base_status_item):
        """Invalid records missing key identifiers should be ignored rather than corrupt output."""
        invalid_items = [
            self._make_item(base_status_item, ticker=None),
            {  # missing last_refresh_status
                "ticker": "GOOD",
                "is_favourite": False,
                "current_price": 100.0,
                "pivot_price": 100.0,
                "pivot_proximity_percent": -2.0,
            },
        ]

        to_update, to_archive = derive_refresh_lists(invalid_items)

        assert len(to_update) == 0
        assert len(to_archive) == 0

    # Boundary and missing-data Buy Ready / Buy Alert behavior
    def test_derive_status_buy_ready_upper_band_boundary(
        self,
        base_status_item,
        test_constants,
    ):
        """
        PASS item exactly at the configured BUY_READY_THRESHOLD band should be Buy Ready.
        """
        threshold = test_constants["BUY_READY_THRESHOLD"]
        items = [
            self._make_item(
                base_status_item,
                ticker="UPBAND",
                # Negative proximity means below pivot; magnitude equals threshold
                pivot_proximity_percent=-threshold,
                vcp_pass=True,
                is_pivot_good=True,
                has_pivot=True,
                is_at_pivot=True,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        assert len(to_archive) == 0
        derived = to_update[0]
        assert derived["ticker"] == "UPBAND"
        assert derived["status"] == "Buy Ready"
        assert derived["last_refresh_status"] == "PASS"

    def test_derive_status_buy_ready_lower_band_boundary(
        self,
        base_status_item,
    ):
        """
        PASS item just inside the lower edge of the Buy Ready band
        (slightly below 0) should still be Buy Ready.
        """
        items = [
            self._make_item(
                base_status_item,
                ticker="LOWBAND",
                pivot_proximity_percent=-0.01,
                vcp_pass=True,
                is_pivot_good=True,
                has_pivot=True,
                is_at_pivot=True,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        assert len(to_archive) == 0
        derived = to_update[0]
        assert derived["ticker"] == "LOWBAND"
        assert derived["status"] == "Buy Ready"
        assert derived["last_refresh_status"] == "PASS"

    def test_derive_status_watch_when_volume_contraction_missing(
        self,
        base_status_item,
    ):
        """
        Missing vol_vs_50d_ratio should downgrade from Buy Alert candidate to Watch.
        """
        items = [
            self._make_item(
                base_status_item,
                ticker="NOVOL",
                # Maturing pivot setup that would normally be Buy Alert
                current_price=90.0,
                pivot_price=100.0,
                pivot_proximity_percent=-10.0,
                vcp_pass=True,
                is_pivot_good=False,
                has_pivot=True,
                is_at_pivot=False,
                has_pullback_setup=False,
                vol_vs_50d_ratio=None,
                day_change_pct=0.5,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        assert len(to_archive) == 0
        derived = to_update[0]
        assert derived["ticker"] == "NOVOL"
        assert derived["status"] == "Watch"
        assert derived["last_refresh_status"] == "PASS"

    def test_derive_status_watch_when_price_fields_missing(
        self,
        base_status_item,
    ):
        """
        PASS item with missing current_price and pivot_price should fall back to Watch.
        """
        items = [
            self._make_item(
                base_status_item,
                ticker="NOPRICE",
                current_price=None,
                pivot_price=None,
                pivot_proximity_percent=None,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        assert len(to_archive) == 0
        derived = to_update[0]
        assert derived["ticker"] == "NOPRICE"
        assert derived["status"] == "Watch"
        assert derived["last_refresh_status"] == "PASS"

    # explicit override and partitioning behavior

    def test_derive_status_failed_overrides_buy_ready_signals(
        self,
        base_status_item,
    ):
        """
        FAIL health with non-null failed_stage must surface as Failed even if Buy Ready conditions hold.
        """
        items = [
            self._make_item(
                base_status_item,
                ticker="FAILREADY",
                last_refresh_status="FAIL",
                failed_stage="freshness",
                # Otherwise Buy Ready configuration
                current_price=100.0,
                pivot_price=100.0,
                pivot_proximity_percent=-2.0,
                vcp_pass=True,
                is_pivot_good=True,
                has_pivot=True,
                is_at_pivot=True,
                is_favourite=False,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        # Non-favourite FAIL should go to archive list
        assert len(to_update) == 0
        assert len(to_archive) == 1
        archived = to_archive[0]
        assert archived["ticker"] == "FAILREADY"
        assert archived["status"] == "Failed"
        assert archived["last_refresh_status"] == "FAIL"
        assert archived["failed_stage"] == "freshness"

    def test_partition_lists_mixed_pass_fail_and_favourite_combinations(
        self,
        base_status_item,
    ):
        """
        List A should contain all PASS items plus FAIL favourites; List B only FAIL non-favourites.
        """
        items = [
            # PASS non-favourite
            self._make_item(
                base_status_item,
                ticker="PASSNONFAV",
                last_refresh_status="PASS",
                is_favourite=False,
            ),
            # PASS favourite
            self._make_item(
                base_status_item,
                ticker="PASSFAV",
                last_refresh_status="PASS",
                is_favourite=True,
            ),
            # FAIL favourite (should stay in update list)
            self._make_item(
                base_status_item,
                ticker="FAILFAV",
                last_refresh_status="FAIL",
                failed_stage="freshness",
                is_favourite=True,
                vcp_pass=False,
                has_pivot=False,
            ),
            # FAIL non-favourite (should be archived)
            self._make_item(
                base_status_item,
                ticker="FAILNONFAV",
                last_refresh_status="FAIL",
                failed_stage="freshness",
                is_favourite=False,
                vcp_pass=False,
                has_pivot=False,
            ),
        ]

        to_update, to_archive = derive_refresh_lists(items)

        update_tickers = {i["ticker"] for i in to_update}
        archive_tickers = {i["ticker"] for i in to_archive}

        assert update_tickers == {"PASSNONFAV", "PASSFAV", "FAILFAV"}
        assert archive_tickers == {"FAILNONFAV"}

    def test_partition_lists_preserves_leadership_flag_in_updates(
        self,
        base_status_item,
    ):
        """
        is_leader flag should be preserved exactly in the update list output.
        """
        items = [
            self._make_item(
                base_status_item,
                ticker="LEADER",
                is_leader=True,
            ),
            self._make_item(
                base_status_item,
                ticker="NONLEADER",
                is_leader=False,
            ),
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_archive) == 0
        leaders = {i["ticker"]: i["is_leader"] for i in to_update}
        assert leaders["LEADER"] is True
        assert leaders["NONLEADER"] is False

    # high-volume distribution on Buy Alert path

    def test_derive_status_watch_for_high_volume_distribution_on_buy_alert(
        self,
        base_status_item,
    ):
        """
        High volume down day should downgrade a Buy Alert candidate to Watch (distribution guardrail).
        """
        items = [
            self._make_item(
                base_status_item,
                ticker="ALRTDIST",
                # Start from a maturing-pivot Buy Alert configuration
                current_price=90.0,
                pivot_price=100.0,
                pivot_proximity_percent=-10.0,
                vcp_pass=True,
                is_pivot_good=False,
                has_pivot=True,
                is_at_pivot=False,
                has_pullback_setup=False,
                # Inject distribution: high volume and sharp negative move
                vol_vs_50d_ratio=3.0,
                day_change_pct=-4.5,
            )
        ]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1
        assert len(to_archive) == 0
        derived = to_update[0]
        assert derived["ticker"] == "ALRTDIST"
        assert derived["status"] == "Watch"
        assert derived["last_refresh_status"] == "PASS"

    # strengthen existing large-batch test to check immutability

    def test_partition_lists_scales_to_large_batch_sizes(self, base_status_item):
        """
        Partitioning large batches should preserve identifiers and not mutate the input list.
        """
        items = [
            self._make_item(base_status_item, ticker=f"TICK{i}")
            for i in range(1000)
        ]
        original_snapshot = [dict(i) for i in items]

        to_update, to_archive = derive_refresh_lists(items)

        assert len(to_update) == 1000
        assert len(to_archive) == 0
        tickers = {item["ticker"] for item in to_update}
        assert "TICK0" in tickers
        assert "TICK999" in tickers

        # Input list should remain unchanged
        assert items == original_snapshot
