# backend-services/data-service/providers/yfin/tests/test_yahoo_client.py
import pytest
from unittest.mock import patch, Mock, call
import threading
import time
from curl_cffi import requests as cffi_requests
from curl_cffi.requests import errors as cffi_errors

# Since yahoo_client is in a sibling directory, we adjust the path
# This assumes tests are run from the root of the data-service
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers.yfin import yahoo_client

# --- Fixtures ---

@pytest.fixture(autouse=True)
def reset_yahoo_auth_globals():
    """Fixture to reset the global crumb and lock before each test."""
    
    # Correctly reset the crumb inside the imported module
    with yahoo_client._AUTH_LOCK:
        yahoo_client._YAHOO_CRUMB = None
    yield # Test runs here
    with yahoo_client._AUTH_LOCK:
        yahoo_client._YAHOO_CRUMB = None


# --- Test Cases ---

@patch('providers.yfin.yahoo_client.session.get')
def test_get_yahoo_auth_success(mock_session_get):
    """
    Tests that the crumb is successfully fetched and stored globally.
    """
    
    mock_response = Mock()
    mock_response.text = "test_crumb"
    mock_response.raise_for_status.return_value = None
    mock_session_get.return_value = mock_response

    crumb = yahoo_client._get_yahoo_auth()

    assert crumb == "test_crumb"
    # Correctly assert against the variable in the imported module
    assert yahoo_client._YAHOO_CRUMB == "test_crumb"
    mock_session_get.assert_called_once()


@patch('providers.yfin.yahoo_client.session.get')
def test_get_yahoo_auth_failure(mock_session_get):
    """
    Tests that the function returns None when the HTTP request fails.
    """
    
    mock_session_get.side_effect = cffi_requests.errors.RequestsError("HTTP Error")

    crumb = yahoo_client._get_yahoo_auth()

    assert crumb is None
    # Correctly assert against the variable in the imported module
    assert yahoo_client._YAHOO_CRUMB is None


@patch('providers.yfin.yahoo_client.session.get')
def test_get_yahoo_auth_is_thread_safe(mock_session_get):
    """
    Tests that only one thread fetches the crumb, while others wait and use the cached value.
    """
    
    mock_response = Mock()
    mock_response.text = "thread_safe_crumb"
    mock_response.raise_for_status.return_value = None
    # Simulate a network delay for the first fetcher
    mock_session_get.side_effect = lambda *args, **kwargs: (time.sleep(0.1), mock_response)[1]


    results = []
    def fetch_crumb_thread():
        crumb = yahoo_client._get_yahoo_auth()
        results.append(crumb)

    thread1 = threading.Thread(target=fetch_crumb_thread)
    thread2 = threading.Thread(target=fetch_crumb_thread)

    thread1.start()
    thread2.start()

    thread1.join()
    thread2.join()

    # Both threads should get the same crumb
    assert results == ["thread_safe_crumb", "thread_safe_crumb"]
    # But the actual HTTP call should have happened only once
    mock_session_get.assert_called_once()


def test_retry_decorator_recovers():
    """
    Tests that the decorator retries on a transient error and eventually succeeds.
    """
    
    mock_func = Mock(side_effect=[
        cffi_requests.errors.RequestsError("rate limited"),
        "Success"
    ])

    # Use the decorator from the imported module
    @yahoo_client.retry_on_failure(attempts=3, delay=0.01)
    def decorated_func():
        return mock_func()

    result = decorated_func()

    assert result == "Success"
    assert mock_func.call_count == 2


def test_retry_decorator_fails_after_exhaustion():
    """
    Tests that the decorator raises an exception after all retry attempts are exhausted.
    """
    
    mock_func = Mock(side_effect=cffi_requests.errors.RequestsError("could not resolve host"))

    # Use the decorator from the imported module
    @yahoo_client.retry_on_failure(attempts=3, delay=0.01)
    def decorated_func():
        return mock_func()

    with pytest.raises(cffi_requests.errors.RequestsError):
        decorated_func()

    assert mock_func.call_count == 3


def test_retry_decorator_ignores_non_retryable_errors():
    """
    Tests that the decorator does not retry on non-transient errors (e.g., TypeError).
    """
    
    mock_func = Mock(side_effect=TypeError("This is a programming error"))

    # Use the decorator from the imported module
    @yahoo_client.retry_on_failure(attempts=3, delay=0.01)
    def decorated_func():
        return mock_func()

    with pytest.raises(TypeError):
        decorated_func()

    # Should fail immediately without retrying
    assert mock_func.call_count == 1

def test_proxy_and_user_agent_rotation():
    """
    Verifies that the utility functions return valid values from their respective lists.
    This test is designed to be robust against the random nature of the function.
    """
    
    # Test User Agent
    agent = yahoo_client._get_random_user_agent()
    assert agent in yahoo_client.USER_AGENTS

    # Test Proxy with no proxies configured
    with patch('providers.yfin.yahoo_client.PROXIES', []):
        proxy = yahoo_client._get_random_proxy()
        assert proxy is None

    # Test Proxy with proxies configured
    test_proxies = ["http://proxy1.com:8080", "https://proxy2.com:9000"]
    with patch('providers.yfin.yahoo_client.PROXIES', test_proxies):
        # The function can correctly return None or a proxy dict. We test for either valid outcome.
        proxy = yahoo_client._get_random_proxy()

        if proxy is not None:
            # If a proxy was chosen, validate its structure and content.
            assert isinstance(proxy, dict)
            assert "http" in proxy
            assert "https" in proxy
            assert proxy["http"] in test_proxies
            assert proxy["https"] in test_proxies
        else:
            # If None was chosen, this is also a valid outcome. The test passes.
            assert proxy is None