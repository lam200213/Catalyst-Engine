# backend-services/monitoring-service/tests/contracts/test_api_contract_compliance.py 

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from typing import Any, Dict
from pydantic import ValidationError

# Import contract models; if missing, fail tests to surface discrepancies (Req #6)
try:
    from shared.contracts import (
        DeleteArchiveResponse,   # Expected: success schema with `message: str`
        ApiError,                # Expected: error schema with at least `error: str`
        TickerPathParam,         # Expected: path param model with ticker constraints
        MAX_TICKER_LEN,          # Expected: e.g., 10
        WatchlistFavouriteRequest,  # expected: { is_favourite: bool }
        WatchlistFavouriteResponse, # expected: { message: str }
        WatchlistBatchRemoveRequest,  # expected: { tickers: List[str] }
        WatchlistBatchRemoveResponse,  # expected: { message: str, removed: int, notfound: int }
        ArchiveReason,  # expected: Enum with MANUAL_DELETE, FAILED_HEALTH_CHECK
        InternalBatchAddRequest,  # expected: { tickers: List[str] }
        InternalBatchAddResponse,  # expected: { message: str, added: int, skipped: int }
        WatchlistRefreshStatusResponse,
        LastRefreshStatus, 
        ArchiveReason
    )
except Exception:
    DeleteArchiveResponse = None
    ApiError = None
    TickerPathParam = None
    MAX_TICKER_LEN = 10  # Sensible default used across tests; will surface if contract differs
    WatchlistFavouriteRequest = None
    WatchlistFavouriteResponse = None
    WatchlistBatchRemoveRequest = None
    WatchlistBatchRemoveResponse = None
    ArchiveReason = None
    InternalBatchAddRequest = None
    InternalBatchAddResponse = None
    WatchlistRefreshStatusResponse = None
    LastRefreshStatus = None
    ArchiveReason = None
# Ensure local imports resolve when running from repo root
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

from app import app as flask_app

def test_monitor_market_health_matches_api_reference():
    """
    Validates that the actual API response matches the example in API_REFERENCE.md
    """
    client = flask_app.test_client()
    response = client.get("/monitor/market-health")
    data = response.get_json()
    
    # Check top-level keys
    assert "market_overview" in data
    assert "leaders_by_industry" in data
    
    # Check market_overview structure
    mo = data["market_overview"]
    assert "market_stage" in mo
    assert "correction_depth_percent" in mo
    assert "high_low_ratio" in mo
    assert "new_highs" in mo
    assert "new_lows" in mo
    
    # Check leaders_by_industry structure
    lbi = data["leaders_by_industry"]
    assert "leading_industries" in lbi
    assert isinstance(lbi["leading_industries"], list)
    
    # Check nested stock structure
    if lbi["leading_industries"]:
        first_industry = lbi["leading_industries"][0]
        assert "industry" in first_industry
        assert "stocks" in first_industry
        if first_industry["stocks"]:
            first_stock = first_industry["stocks"][0]
            assert "ticker" in first_stock
            # Check for correct field name (should be percent_change_3m after fix)
            assert "percent_change_3m" in first_stock or "percent_change_1m" in first_stock

# Contract-oriented checks for PUT /monitor/watchlist/ticker
class TestPutTickerContract:
    """
    Response should follow project JSON patterns:
      - Content-Type: application/json
      - Proper status codes (201 for created, 200 for idempotent)
      - Error responses contain 'error'
      - No internal DB fields leaked
    """

    @patch('services.watchlist_service.add_or_upsert_ticker')
    @patch('database.mongo_client.connect')
    def test_response_shape_and_types_on_created(self, mock_connect, mock_add, client):
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_add.return_value = {
            "success": True,
            "ticker": "DDOG",
            "existed": False,
            "reintroduced": False,
        }

        resp = client.put('/monitor/watchlist/DDOG')
        assert resp.status_code == 201
        assert resp.content_type == 'application/json'

        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "item" in data
        item = data["item"]

        # Required keys and types
        assert isinstance(item["ticker"], str)
        assert isinstance(item["status"], str)
        assert isinstance(item["is_favourite"], bool)
        assert isinstance(item["last_refresh_status"], str)

        # No internal fields
        assert "_id" not in item
        assert "user_id" not in item

    def test_error_response_shape_on_validation_error(self, client):
        resp = client.put('/monitor/watchlist/%24AAPL')  # %24 = $
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data
        assert isinstance(data["error"], str)

class TestPutTickerContract:
    """
    Response should follow project JSON patterns:
    - Content-Type: application/json
    - Proper status codes (201 for created, 200 for idempotent)
    - Error responses contain 'error'
    - No internal DB fields leaked
    """

    # align PUT /monitor/watchlist/:ticker with status engine contracts
    @patch("services.watchlist_service.add_or_upsert_ticker")
    @patch("database.mongo_client.connect")
    def test_put_watchlist_ticker_status_values_match_status_engine_range(
        self,
        mock_connect,
        mock_add,
        client,
    ):
        """
        Returned item.status must be one of the allowed UI labels produced by the status engine.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_add.return_value = {
            "success": True,
            "ticker": "DDOG",
            "existed": False,
            "reintroduced": False,
        }

        resp = client.put("/monitor/watchlist/DDOG")
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        item = data["item"]

        allowed = {"Pending", "Failed", "Watch", "Buy Alert", "Buy Ready"}
        assert item["status"] in allowed
        assert isinstance(item["status"], str)
        assert item["ticker"] == "DDOG"

    @patch("services.watchlist_service.add_or_upsert_ticker")
    @patch("database.mongo_client.connect")
    def test_put_watchlist_ticker_defaults_to_watch_for_new_symbols(
        self,
        mock_connect,
        mock_add,
        client,
    ):
        """
        Brand new tickers should default to Watch with last_refresh_status=PENDING.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_add.return_value = {
            "success": True,
            "ticker": "NEWCAND",
            "existed": False,
            "reintroduced": False,
        }

        resp = client.put("/monitor/watchlist/NEWCAND")
        # New symbol: expect 201 Created per existing tests
        assert resp.status_code == 201
        data = json.loads(resp.data)
        item = data["item"]

        assert item["ticker"] == "NEWCAND"
        assert item["status"] == "Watch"
        assert item["last_refresh_status"] == "PENDING"

class TestDeleteTickerContract:
    """
    Contract-oriented checks for DELETE /monitor/watchlist/:ticker:
    - 200 with message only (no internal fields)
    - 404 not found error body
    - 400 for invalid ticker format/length
    - Uppercase normalization in the user-facing message
    - Disallowed methods on this path return 405
    """

    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_success_shape_and_types(self, mock_connect, mock_move, client):
        # success case returns message string and normalizes ticker
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_move.return_value = {
            "ticker": "AAPL",
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
            "archived_at": "2025-11-13T00:00:00Z",
        }

        resp = client.delete('/monitor/watchlist/aapl')
        assert resp.status_code == 200
        assert resp.content_type == 'application/json'
        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "message" in data and isinstance(data["message"], str)
        assert "AAPL" in data["message"]
        # No internal fields leaked in response body
        for k in ("reason", "failed_stage", "archived_at", "user_id", "_id"):
            assert k not in data

    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_not_found_404_error_body(self, mock_connect, mock_move, client):
        # not found should return 404 with error
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_move.return_value = None

        resp = client.delete('/monitor/watchlist/ZZZZZ')  # <= 10 chars so format is valid
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data and isinstance(data["error"], str)

    @patch('database.mongo_client.connect')
    def test_delete_validation_length_boundary(self, mock_connect, client):
        # at threshold accepted, above threshold rejected per API contract
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        ok = "A" * 10
        resp_ok = client.delete(f'/monitor/watchlist/{ok}')
        # If the route uses lazy service call, patching is needed, but contract test expects 200 surface behavior
        assert resp_ok.status_code in (200, 404)  # 200 if existed, 404 if not found; both valid surface outcomes

        too_long = "A" * 11
        resp_long = client.delete(f'/monitor/watchlist/{too_long}')
        assert resp_long.status_code == 400
        data = json.loads(resp_long.data)
        assert "error" in data

    def test_delete_method_constraints(self, client):
        path = '/monitor/watchlist/AAPL'
        methods = ("get", "post", "patch")
        for method in methods:
            r = getattr(client, method)(path)
            assert r.status_code == 405

class TestArchiveAPIContract:
    """Ensure archive route returns documented contract"""

    @patch('services.watchlist_service.get_archive')
    @patch('database.mongo_client.connect')
    def test_contract_empty_archived_items(self, mock_connect, mock_get_archive, client):
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_archive.return_value = {"archived_items": []}

        resp = client.get('/monitor/archive')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "archived_items" in data and isinstance(data["archived_items"], list)
        assert data["archived_items"] == []

    @patch('services.watchlist_service.get_archive')
    @patch('database.mongo_client.connect')
    def test_contract_populated_items_and_enums(self, mock_connect, mock_get_archive, client):
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_archive.return_value = {
            "archived_items": [
                {"ticker": "CRM", "archived_at": "2025-11-08T10:00:00Z", "reason": "FAILED_HEALTH_CHECK", "failed_stage": "vcp"},
                {"ticker": "NET", "archived_at": "2025-11-01T12:00:00Z", "reason": "MANUAL_DELETE", "failed_stage": None},
            ]
        }

        resp = client.get('/monitor/archive')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        items = data["archived_items"]
        assert len(items) == 2

        for it in items:
            assert isinstance(it["ticker"], str)
            assert isinstance(it["archived_at"], str)
            assert it["reason"] in {"MANUAL_DELETE", "FAILED_HEALTH_CHECK"}
            assert ("failed_stage" in it) and (it["failed_stage"] is None or isinstance(it["failed_stage"], str))

        assert {it["ticker"] for it in items} == {"CRM", "NET"}


class TestDeleteArchiveContractSuccess:
    def test_success_200_schema_message_only(self):
        """
        Requirements 1,4,5,6,7,9,10,11: Success response must validate against the
        DeleteArchiveResponse model and only expose `message: str` which includes the key identifier (ticker).
        """
        if DeleteArchiveResponse is None:
            pytest.fail("contracts.DeleteArchiveResponse model is missing (contract discrepancy)")

        # Simulate raw response.json() payload (Req #13)
        payload: Dict[str, Any] = {
            "message": "Archived ticker AAPL permanently deleted."
        }

        model = DeleteArchiveResponse.model_validate(payload)  # pydantic v2 API
        assert isinstance(model.message, str)
        assert "AAPL" in model.message  # assert key identifier present

        # Blind spot guard: ensure no internal fields are accidentally exposed
        extra_keys = set(payload.keys()) - {"message"}
        assert extra_keys == set()

    def test_success_rejects_extra_fields(self):
        """
        Requirements 3,4,5,6,7,9,10: Success schema must forbid leaking internals like archived_at/reason.
        """
        if DeleteArchiveResponse is None:
            pytest.fail("contracts.DeleteArchiveResponse model is missing (contract discrepancy)")

        bad_payload = {
            "message": "Archived ticker NET permanently deleted.",
            "archived_at": "2025-11-13T10:00:00Z",
            "reason": "MANUAL_DELETE",
        }
        with pytest.raises((ValidationError, AssertionError)):
            DeleteArchiveResponse.model_validate(bad_payload)


class TestDeleteArchiveContractErrors:
    def test_not_found_404_schema(self):
        """
        Requirements 1,2,3,4,6,7,8,9,10,11: 404 error must validate against ApiError and
        contain correct types; payload must not include internals; ticker identity appears in message upstream,
        but contracts for error only require `error: str`.
        """
        if ApiError is None:
            pytest.fail("contracts.ApiError model is missing (contract discrepancy)")

        payload = {"error": "Ticker not found"}
        model = ApiError.model_validate(payload)
        assert isinstance(model.error, str)

        # Ensure no extra fields
        extra_keys = set(payload.keys()) - {"error"}
        assert extra_keys == set()

    def test_invalid_input_400_schema(self):
        """
        Requirements 2,3,4,6,7,9,12: 400 error for invalid ticker should conform to ApiError.
        """
        if ApiError is None:
            pytest.fail("contracts.ApiError model is missing (contract discrepancy)")

        payload = {"error": "Invalid ticker format"}
        model = ApiError.model_validate(payload)
        assert isinstance(model.error, str)

    def test_db_failure_503_schema(self):
        """
        Requirements 2,3,4,5,6,7,9: 503 error for DB failure should conform to ApiError
        and avoid leaking internal exception messages beyond the standard error string.
        """
        if ApiError is None:
            pytest.fail("contracts.ApiError model is missing (contract discrepancy)")

        payload = {"error": "Service unavailable"}
        model = ApiError.model_validate(payload)
        assert isinstance(model.error, str)


class TestDeleteArchiveTickerParamContract:
    def test_ticker_below_threshold_rejected(self):
        """
        Requirements 2,3,4,6,7,9,12: Path param contract must reject values below min length.
        """
        if TickerPathParam is None:
            pytest.fail("contracts.TickerPathParam model is missing (contract discrepancy)")

        with pytest.raises(ValidationError):
            TickerPathParam(ticker="")  # below threshold

        with pytest.raises(ValidationError):
            TickerPathParam(ticker="   ")  # whitespace only

    def test_ticker_at_threshold_valid(self):
        """
        Requirements 1,2,4,6,7,9,12: Path param contract must accept tickers at the MAX_TICKER_LEN threshold.
        """
        if TickerPathParam is None:
            pytest.fail("contracts.TickerPathParam model is missing (contract discrepancy)")

        # Construct exactly at-threshold ticker
        ten = "A" * int(MAX_TICKER_LEN or 10)
        model = TickerPathParam(ticker=ten)
        assert model.ticker == ten

    def test_ticker_invalid_characters_rejected(self):
        """
        Requirements 2,3,4,6,7,9: Invalid characters must violate the path param contract.
        """
        if TickerPathParam is None:
            pytest.fail("contracts.TickerPathParam model is missing (contract discrepancy)")

        with pytest.raises(ValidationError):
            TickerPathParam(ticker="AAPL@")  # invalid symbol

    def test_ticker_normalization_is_service_concern_not_contract(self):
        """
        Requirements 4,5: Contract should validate shape/constraints only; case normalization
        is a service/route concern. This test asserts that the contract accepts case as-is.
        """
        if TickerPathParam is None:
            pytest.fail("contracts.TickerPathParam model is missing (contract discrepancy)")

        model = TickerPathParam(ticker="aapl")
        assert isinstance(model.ticker, str)

class TestFavouriteContract:
    """Contract-oriented checks for POST /monitor/watchlist/:ticker/favourite"""

    
    def test_favourite_request_requires_boolean(self):
        if WatchlistFavouriteRequest is None:
            pytest.fail("contracts.WatchlistFavouriteRequest model is missing (contract discrepancy)")
        # valid
        model = WatchlistFavouriteRequest(is_favourite=True)
        assert isinstance(model.is_favourite, bool)
        # invalids
        for bad in ("true", 1, 0, None, [], {}, "False"):
            with pytest.raises(ValidationError):
                WatchlistFavouriteRequest(is_favourite=bad)

    
    def test_favourite_response_success_message_only(self):
        if WatchlistFavouriteResponse is None:
            pytest.fail("contracts.WatchlistFavouriteResponse model is missing (contract discrepancy)")
        payload = {"message": "Ticker 'AAPL' marked as favourite."}
        model = WatchlistFavouriteResponse.model_validate(payload)
        assert isinstance(model.message, str)
        # No extra fields allowed
        extra = {"message": "ok", "archived_at": "2025-11-13T00:00:00Z"}
        with pytest.raises((ValidationError, AssertionError)):
            WatchlistFavouriteResponse.model_validate(extra)

    
    @patch('database.mongo_client.connect')
    @patch('database.mongo_client.toggle_favourite')
    def test_favourite_error_schemas_404_and_400(self, mock_toggle, mock_connect, client):
        if ApiError is None:
            pytest.fail("contracts.ApiError model is missing (contract discrepancy)")
        mock_client = MagicMock(); mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # 404 not found
        mock_toggle.return_value = MagicMock(modified_count=0)
        r1 = client.post('/monitor/watchlist/ZZZZZ/favourite', json={"is_favourite": True})
        assert r1.status_code == 404
        p1 = r1.get_json()
        ApiError.model_validate(p1)
        assert isinstance(p1["error"], str)

        # 400 invalid body
        r2 = client.post('/monitor/watchlist/AAPL/favourite', json={"is_favourite": "true"})
        assert r2.status_code == 400
        p2 = r2.get_json()
        ApiError.model_validate(p2)
        assert isinstance(p2["error"], str)

    
    def test_ticker_param_threshold_rules_for_favourite(self):
        if TickerPathParam is None:
            pytest.fail("contracts.TickerPathParam model is missing (contract discrepancy)")
        with pytest.raises(ValidationError):
            TickerPathParam(ticker="")  # below threshold
        at = "A" * int(MAX_TICKER_LEN or 10)
        ok = TickerPathParam(ticker=at)
        assert ok.ticker == at
        with pytest.raises(ValidationError):
            TickerPathParam(ticker="A" * (int(MAX_TICKER_LEN or 10) + 1))  # above threshold

# contract alignment for POST /monitor/watchlist/batch/remove

class TestWatchlistBatchRemoveContracts:
    """Validate request/response models and enums for batch remove."""

    def test_watchlist_batch_remove_request_shape_and_validation(self):
        """
        Req #3, #6, #7, #8, #10, #13:
        - Request must expose a tickers: List[str] field.
        - Non-list or non-string items must fail Pydantic validation.
        """
        assert WatchlistBatchRemoveRequest is not None, (
            "WatchlistBatchRemoveRequest must be defined in shared.contracts "
            "per Phase 2 technical design."
        )

        # Happy path
        payload = {"tickers": ["AAPL", "MSFT"]}
        model = WatchlistBatchRemoveRequest(**payload)
        assert isinstance(model.tickers, list)
        assert all(isinstance(t, str) for t in model.tickers)
        assert model.tickers == ["AAPL", "MSFT"]

        # Malformed: tickers is not a list
        with pytest.raises(ValidationError):
            WatchlistBatchRemoveRequest(**{"tickers": "AAPL"})

        # Malformed: non-string items in tickers
        with pytest.raises(ValidationError):
            WatchlistBatchRemoveRequest(**{"tickers": ["AAPL", 123]})

    def test_watchlist_batch_remove_response_shape_and_types(self):
        """
        Req #1, #3, #6, #7, #9:
        - Response must match { message: str, removed: int, notfound: int }.
        - Type mismatches must raise ValidationError.
        """
        assert WatchlistBatchRemoveResponse is not None, (
            "WatchlistBatchRemoveResponse must be defined in shared.contracts "
            "per Phase 2 technical design."
        )

        resp = WatchlistBatchRemoveResponse(
            message="Successfully removed 2 tickers from the watchlist.",
            removed=2,
            notfound=1,
        )

        assert isinstance(resp.message, str)
        assert isinstance(resp.removed, int)
        assert isinstance(resp.notfound, int)

        # Type mismatch: removed must be int
        with pytest.raises(ValidationError):
            WatchlistBatchRemoveResponse(
                message="bad types",
                removed="2",
                notfound=0,
            )

    def test_archive_reason_enum_includes_MANUAL_DELETE_and_FAILED_HEALTH_CHECK(self):
        """
        Req #1, #5, #6:
        - ArchiveReason enum must include MANUAL_DELETE and FAILED_HEALTH_CHECK,
          matching the archived_watchlist_items.reason semantics.
        """
        assert ArchiveReason is not None, (
            "ArchiveReason enum must be defined in shared.contracts."
        )

        values = {member.value for member in ArchiveReason}
        assert "MANUAL_DELETE" in values
        assert "FAILED_HEALTH_CHECK" in values

class TestInternalBatchAddContracts:
    """Validate request/response models for internal batch add"""

    def test_internal_batch_add_request_shape_and_validation(self):
        assert InternalBatchAddRequest is not None, "InternalBatchAddRequest must be defined in shared.contracts"

        # Happy path
        m = InternalBatchAddRequest(**{"tickers": ["CRWD", "DDOG"]})
        assert isinstance(m.tickers, list)
        assert all(isinstance(t, str) for t in m.tickers)

        # Non-list tickers
        with pytest.raises(ValidationError):
            InternalBatchAddRequest(**{"tickers": "CRWD"})

        # Non-string item
        with pytest.raises(ValidationError):
            InternalBatchAddRequest(**{"tickers": ["CRWD", 123]})

    def test_internal_batch_add_response_shape_and_types(self):
        assert InternalBatchAddResponse is not None, (
            "InternalBatchAddResponse must be defined in shared.contracts with fields: message, added, skipped"
        )

        ok = InternalBatchAddResponse(message="Added 2, skipped 1", added=2, skipped=1)
        assert isinstance(ok.message, str)
        assert isinstance(ok.added, int)
        assert isinstance(ok.skipped, int)

        with pytest.raises(ValidationError):
            InternalBatchAddResponse(message="bad types", added="2", skipped=0)

        with pytest.raises(ValidationError):
            InternalBatchAddResponse(message=123, added=2, skipped=0)

class TestRefreshOrchestratorContracts:
    def test_watchlist_refresh_status_response_schema_matches_data_contracts(self):
        """
        Contract: Response must include message (str), updated_items (int),
        archived_items (int), failed_items (int) and forbid extra fields.
        """
        if WatchlistRefreshStatusResponse is None:
            pytest.fail("shared.contracts.WatchlistRefreshStatusResponse missing")
        ok = WatchlistRefreshStatusResponse(
            message="Done",
            updated_items=2,
            archived_items=1,
            failed_items=0,
        )
        assert isinstance(ok.message, str)
        assert isinstance(ok.updated_items, int)
        assert isinstance(ok.archived_items, int)
        assert isinstance(ok.failed_items, int)
        with pytest.raises(ValidationError):
            WatchlistRefreshStatusResponse(
                message="Bad",
                updated_items=1,
                archived_items=0,
                failed_items=0,
                extra_key=True,
            )

    def test_lastrefreshstatus_enum_values_match_data_contracts(self):
        """
        Enum values must be exactly {PENDING, PASS, FAIL, UNKNOWN}.
        """
        if LastRefreshStatus is None:
            pytest.fail("shared.contracts.LastRefreshStatus missing")
        values = {m.value for m in LastRefreshStatus}
        assert values == {"PENDING", "PASS", "FAIL", "UNKNOWN"}

    def test_archive_reason_enum_values_match_data_contracts(self):
        """
        Enum values must be exactly {MANUAL_DELETE, FAILED_HEALTH_CHECK}.
        """
        if ArchiveReason is None:
            pytest.fail("shared.contracts.ArchiveReason missing")
        values = {m.value for m in ArchiveReason}
        assert values == {"MANUAL_DELETE", "FAILED_HEALTH_CHECK"}
