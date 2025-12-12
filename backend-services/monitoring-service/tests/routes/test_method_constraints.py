# backend-services/monitoring-service/tests/routes/test_method_constraints.py
"""
HTTP method constraint tests for monitoring-service routes, including disallowing
unsupported verbs and validating OPTIONS/HEAD behavior per service conventions.
Focuses on route-level method guards (no business logic duplication).
"""
import pytest

# Import the Flask app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================================
# TEST: HTTP Method Validation
# ============================================================================

class TestHTTPMethodValidation:
    """Test HTTP method constraints"""
    
    def test_watchlist_only_allows_get(self, client):
        """
        Verify only GET method is allowed on /monitor/watchlist
        """
        # GET should succeed (with mocked dependencies)
        # Other methods should return 405
        
        response_post = client.post('/monitor/watchlist')
        response_put = client.put('/monitor/watchlist')
        response_delete = client.delete('/monitor/watchlist')
        response_patch = client.patch('/monitor/watchlist')
        
        assert response_post.status_code == 405, "POST should not be allowed"
        assert response_put.status_code == 405, "PUT should not be allowed"
        assert response_delete.status_code == 405, "DELETE should not be allowed"
        assert response_patch.status_code == 405, "PATCH should not be allowed"

    # Only DELETE allowed on /monitor/watchlist/:ticker
    @pytest.mark.parametrize("method", ["get", "post", "patch"])
    def test_watchlist_ticker_only_allows_delete(self, client, method):
        """
        Verify only DELETE is allowed on /monitor/watchlist/:ticker.
        PUT is explicitly allowed and should not be asserted as 405.
        """
        path = '/monitor/watchlist/AAPL'
        resp = getattr(client, method)(path)
        assert resp.status_code == 405, f"{method.upper()} should not be allowed on {path}"

    def test_watchlist_ticker_favourite_only_allows_post(self, client):
        """
        Verify only POST is allowed on /monitor/watchlist/:ticker/favourite
        """
        path = '/monitor/watchlist/AAPL/favourite'
        assert client.get(path).status_code == 405
        assert client.put(path).status_code == 405
        assert client.delete(path).status_code == 405
        assert client.patch(path).status_code == 405

    # method constraints for batch remove endpoint
    def test_watchlist_batch_remove_only_allows_post(self, client):
        """
        Verify only POST is allowed on /monitor/watchlist/batch/remove.
        Other HTTP verbs must return 405 to enforce method constraints.
        """
        path = '/monitor/watchlist/batch/remove'

        # Disallowed methods
        resp_get = client.get(path)
        resp_put = client.put(path)
        resp_delete = client.delete(path)
        resp_patch = client.patch(path)

        assert resp_get.status_code == 405
        assert resp_put.status_code == 405
        assert resp_delete.status_code == 405
        assert resp_patch.status_code == 405
# ============================================================================
# HTTP method constraints for /monitor/archive and /monitor/archive/:ticker
# ============================================================================
class TestHTTPMethodValidationArchive:
    """Test HTTP method constraints for archive endpoints"""

    def test_archive_only_allows_get(self, client):
        # GET should succeed (when dependencies are mocked in other tests)
        resp_post = client.post('/monitor/archive')
        resp_put = client.put('/monitor/archive')
        resp_delete = client.delete('/monitor/archive')
        resp_patch = client.patch('/monitor/archive')

        assert resp_post.status_code == 405
        assert resp_put.status_code == 405
        assert resp_delete.status_code == 405
        assert resp_patch.status_code == 405

    @pytest.mark.parametrize("method", ["get", "post", "put", "patch"])
    def test_archive_ticker_only_allows_delete(self, client, method):
        path = '/monitor/archive/AAPL'
        resp = getattr(client, method)(path)
        assert resp.status_code == 405, f"{method.upper()} should not be allowed on {path}"

# ============================================================================
# TESTS: method constraints for internal batch add
# ============================================================================
class TestHTTPMethodValidationInternalBatchAdd:
    """Test HTTP method constraints for internal batch add"""

    def test_internal_batch_add_only_allows_post(self, client):
        path = '/monitor/internal/watchlist/batch/add'
        assert client.get(path).status_code == 405
        assert client.put(path).status_code == 405
        assert client.delete(path).status_code == 405
        assert client.patch(path).status_code == 405

    def test_internal_batch_add_requires_json_body(self, client):
        # Missing or wrong content-type should fail with 400
        resp_no_body = client.post('/monitor/internal/watchlist/batch/add')
        assert resp_no_body.status_code in (400, 415)

        resp_wrong_ct = client.post(
            '/monitor/internal/watchlist/batch/add',
            data="tickers=AAPL,MSFT",
            headers={"Content-Type": "text/plain"},
        )
        assert resp_wrong_ct.status_code in (400, 415)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
