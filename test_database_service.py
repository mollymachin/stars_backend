import pytest
from fastapi.testclient import TestClient
from database_service import app
from unittest.mock import Mock, patch

client = TestClient(app)

import pytest
from fastapi.testclient import TestClient
from database_service import app
from unittest.mock import Mock, patch

client = TestClient(app)

@pytest.fixture
def mock_table_service():
    with patch('database_service.TableServiceClient') as mock:
        yield mock

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

'''

@pytest.fixture
def mock_table_service():
    with patch('database_service.TableServiceClient') as mock:
        yield mock

@pytest.fixture
def mock_redis():
    with patch('database_service.aioredis') as mock:
        yield mock

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_star(mock_table_service):
    test_star = {
        "x": 0.5,
        "y": 0.5,
        "message": "Test Star"
    }
    response = client.post("/stars", json=test_star)
    assert response.status_code == 200
    assert response.json()["X"] == test_star["x"]
    assert response.json()["Y"] == test_star["y"]
    assert response.json()["Message"] == test_star["message"]

def test_get_stars(mock_table_service):
    mock_table_service.return_value.query_entities.return_value = [
        {
            "RowKey": "1",
            "X": 0.5,
            "Y": 0.5,
            "Message": "Test Star",
            "Brightness": 100.0,
            "LastLiked": 1234567890
        }
    ]
    response = client.get("/stars")
    assert response.status_code == 200
    assert len(response.json()) == 1

'''