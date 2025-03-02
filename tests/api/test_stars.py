import pytest
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys

from src.main import app
from src.models.star import Star

# Create a test client
client = TestClient(app)

# Apply patches for critical dependencies
patches = [
    patch('src.api.stars.tables', {"Stars": MagicMock(), "UserStars": MagicMock()}),
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

# Test creating a star
def test_create_star():
    """Test creating a new star"""
    # Test data
    test_star = {
        "x": 0.5,
        "y": 0.5,
        "message": "Test Star"
    }
    
    # Make request
    response = client.post("/stars", json=test_star)
    
    # Assertions
    assert response.status_code == 200
    assert "id" in response.json()  # Check UUID was generated
    assert response.json()["x"] == test_star["x"]
    assert response.json()["y"] == test_star["y"]
    assert response.json()["message"] == test_star["message"]

# Test getting stars
def test_get_stars():
    """Test retrieving all stars"""
    # Setup mock return data
    from src.api.stars import tables
    current_time = time.time()
    tables["Stars"].list_entities.return_value = [
        {
            "PartitionKey": "STAR_202310",
            "RowKey": "1",
            "X": 0.5,
            "Y": 0.5,
            "Message": "Test Star",
            "Brightness": 100.0,
            "LastLiked": current_time,
            "CreatedAt": current_time
        }
    ]
    
    # Make request
    response = client.get("/stars")
    
    # Assertions
    assert response.status_code == 200
    assert len(response.json()) == 1
    star = response.json()[0]
    assert star["id"] == "1"
    assert star["x"] == 0.5
    assert star["y"] == 0.5
    assert star["message"] == "Test Star"

# Test validation of coordinates
def test_validate_coordinates():
    """Test that coordinates are validated"""
    # Test invalid x coordinate
    test_star = {
        "x": 2.0,  # Invalid - outside range
        "y": 0.5,
        "message": "Invalid Star"
    }
    response = client.post("/stars", json=test_star)
    assert response.status_code == 422  # Validation error
    
    # Test invalid y coordinate
    test_star = {
        "x": 0.5,
        "y": -2.0,  # Invalid - outside range
        "message": "Invalid Star"
    }
    response = client.post("/stars", json=test_star)
    assert response.status_code == 422  # Validation error

# Test message length validation
def test_validate_message_length():
    """Test that message length is validated"""
    # Create a message that's too long (over 280 chars)
    long_message = "x" * 300
    test_star = {
        "x": 0.5,
        "y": 0.5,
        "message": long_message
    }
    response = client.post("/stars", json=test_star)
    assert response.status_code == 422  # Validation error 