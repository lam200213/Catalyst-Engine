# backend-services/screening-service/tests/conftest.py

import sys
import os
import pytest

# This adds the service root (one level up from tests/) to the path globally for all tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Dynamically find the service root (the folder containing 'tests/')
# This works whether the test is in tests/, tests/unit/, or tests/integration/
service_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if service_root not in sys.path:
    sys.path.insert(0, service_root)

# Also add the shared directory for contracts.py access
shared_path = os.path.abspath(os.path.join(service_root, '..', 'shared'))
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)

# --- Environment Configuration ---
def pytest_configure(config):
    """Register custom markers to avoid warnings."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated, no containers).")
    config.addinivalue_line(
        "markers",
        "integration: Integration tests (service integration; may use DB/network mocks).",
    )
    config.addinivalue_line("markers", "e2e: End-to-end integration tests requiring running containers.")

def pytest_collection_modifyitems(config, items):
    # auto-tag tests by folder so `-m unit|integration|e2e` works consistently
    for item in items:
        path = str(item.fspath)
        if f"{os.sep}e2e{os.sep}" in path:
            item.add_marker(pytest.mark.e2e)
        elif f"{os.sep}integration{os.sep}" in path:
            item.add_marker(pytest.mark.integration)
        elif (f"{os.sep}unit{os.sep}" in path) or (f"{os.sep}unittest{os.sep}" in path):
            item.add_marker(pytest.mark.unit)