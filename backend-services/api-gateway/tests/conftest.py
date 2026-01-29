# backend-services/api-gateway/tests/conftest.py

import sys
import os

# This adds the service root (one level up from tests/) to the path globally for all tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))