# backend-services/monitoring-service/tests/routes/test_health.py
"""
Test suite for monitoring-service app.py watchlist routes
Health check endpoint: GET /health
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from flask import Flask
from urllib.parse import quote

# Import the Flask app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================================
# TEST: Health Check Endpoint
# ============================================================================

class TestHealthCheckEndpoint:
    """Test GET /health endpoint"""
    
    def test_health_check_returns_ok(self, client):
        """
        CRITICAL: Verify health check returns {"status": "healthy"}
        This is standard health check format for monitoring
        """
        response = client.get('/health')
        
        # Verify status code
        assert response.status_code == 200, "Health check should return 200 OK"
        
        # Verify response is JSON
        assert response.content_type == 'application/json', "Response should be JSON"
        
        # Parse response
        data = json.loads(response.data)
        
        # Verify response structure and content
        assert "status" in data, "Response must have 'status' field"
        assert data["status"] == "healthy", "Health check should return status: healthy"
        assert isinstance(data["status"], str), "status field must be string type"
    
    def test_health_check_method_not_allowed(self, client):
        """Edge case: Verify other HTTP methods are not allowed"""
        response_post = client.post('/health')
        response_put = client.put('/health')
        response_delete = client.delete('/health')
        
        # All should return 405 Method Not Allowed
        assert response_post.status_code == 405, "POST should not be allowed"
        assert response_put.status_code == 405, "PUT should not be allowed"
        assert response_delete.status_code == 405, "DELETE should not be allowed"
    
    def test_health_check_response_format_consistency(self, client):
        """
        Verify health check response format is consistent across multiple calls
        Important for monitoring systems that poll health
        """
        response1 = client.get('/health')
        response2 = client.get('/health')
        response3 = client.get('/health')
        
        data1 = json.loads(response1.data)
        data2 = json.loads(response2.data)
        data3 = json.loads(response3.data)
        
        # All should return identical structure
        assert data1 == data2 == data3, "Health check should return consistent format"
        assert data1["status"] == "healthy"
    
    def test_health_check_no_query_parameters_required(self, client):
        """Edge case: Verify health check works without query parameters"""
        response = client.get('/health')
        assert response.status_code == 200
        
        # Should also work with arbitrary query parameters (ignored)
        response_with_params = client.get('/health?foo=bar&test=123')
        assert response_with_params.status_code == 200

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
