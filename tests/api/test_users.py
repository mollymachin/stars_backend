import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys

from src.main import app
from src.models.user import User

# Create a test client
client = TestClient(app)

# Apply patches for critical dependencies
patches = [
    patch('src.api.users.tables', {"Users": MagicMock()}),
    patch('src.db.redis_cache.FastAPILimiter', MagicMock()),
    patch('src.db.redis_cache.aioredis', MagicMock()),
    patch('src.db.redis_cache.FastAPICache', MagicMock())
]

# Start all the patches
for p in patches:
    p.start()

# Create a mock limiter
mock_limiter = MagicMock()
mock_limiter.limit = lambda x: lambda func: func
sys.modules['src.db.redis_cache'].limiter = mock_limiter

# Test creating a user
def test_create_user():
    """Test creating a new user"""
    # Test data
    test_user = {
        "name": "Test User",
        "email": "test@example.com"
    }
    
    # Make request
    response = client.post("/users", json=test_user)
    
    # Assertions
    assert response.status_code == 200
    assert "user_id" in response.json()
    assert response.json()["name"] == test_user["name"]
    assert response.json()["email"] == test_user["email"] 