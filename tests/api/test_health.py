import pytest
from fastapi.testclient import TestClient
from src.main import app

# Create a test client
client = TestClient(app)

# Test health check endpoint
def test_health_check():
    """Test that health check endpoint returns 200 and healthy status"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy" 