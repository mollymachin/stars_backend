import pytest
import json
import time
from datetime import datetime, UTC
from fastapi.testclient import TestClient
from database_service import app, Star, User
from unittest.mock import Mock, patch, MagicMock
import sys

client = TestClient(app)

# Mock out FastAPILimiter for testingL
with patch('database_service.RateLimiter', MagicMock()):
    # Tests can now run without rate limiting dependency
    pass

# Create a mock limiter
mock_limiter = MagicMock()
mock_limiter.limit = lambda x: lambda func: func
sys.modules['database_service'].limiter = mock_limiter

# Mock Azure Table Storage
@pytest.fixture
def mock_tables():
    """Mock the tables dictionary with table clients"""
    with patch('database_service.tables') as mock_tables:
        # Create mock table clients
        mock_tables["Stars"] = MagicMock()
        mock_tables["Users"] = MagicMock()
        mock_tables["UserStars"] = MagicMock()
        yield mock_tables

# Mock TableServiceClient
@pytest.fixture
def mock_table_service():
    """Mock the Azure TableServiceClient"""
    with patch('database_service.TableServiceClient') as mock:
        mock_client = Mock()
        mock.from_connection_string.return_value = mock_client
        yield mock

# Mock Redis for caching
@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    with patch('database_service.aioredis') as mock:
        mock_redis = MagicMock()
        mock.from_url.return_value = mock_redis
        yield mock_redis

# Mock FastAPICache
@pytest.fixture
def mock_fastapi_cache():
    """Mock FastAPICache"""
    with patch('database_service.FastAPICache') as mock:
        mock_backend = MagicMock()
        mock.get_backend.return_value = mock_backend
        yield mock

# Test health check endpoint
def test_health_check():
    """Test that health check endpoint returns 200 and healthy status"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

# Test creating a star
def test_create_star(mock_tables):
    """Test creating a new star"""
    # Setup mock
    mock_tables["Stars"].create_entity.return_value = None
    
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
    assert "RowKey" in response.json()  # Check UUID was generated
    assert response.json()["X"] == test_star["x"]
    assert response.json()["Y"] == test_star["y"]
    assert response.json()["Message"] == test_star["message"]
    
    # Verify mock was called
    mock_tables["Stars"].create_entity.assert_called_once()

# Test getting stars
def test_get_stars(mock_tables):
    """Test retrieving all stars"""
    # Setup mock return data
    current_time = time.time()
    mock_tables["Stars"].query_entities.return_value = [
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
    
    # Verify mock was called
    mock_tables["Stars"].query_entities.assert_called_once()

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

# Test creating a user
def test_create_user(mock_tables):
    """Test creating a new user"""
    # Setup mock
    mock_tables["Users"].create_entity.return_value = None
    
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
    
    # Verify mock was called
    mock_tables["Users"].create_entity.assert_called_once()