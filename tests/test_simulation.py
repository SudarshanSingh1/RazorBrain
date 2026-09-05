import pytest
from fastapi.testclient import TestClient
from api.app import app

@pytest.fixture
def mock_db():
    with TestClient(app) as local_client:
        state = app.state.razor_state
        yield local_client, state.db_path

def test_simulation_zero_arrivals(mock_db):
    test_client, db_path = mock_db
    payload = {
        "horizon_hours": 24,
        "capacity_per_hour": 10.0,
        "arrival_rate_per_hour": 0.0,
        "initial_backlog": 15
    }
    resp = test_client.post("/dashboard/review-capacity/simulate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"]["ending_backlog"] == 0
    assert data["results"]["total_arrivals"] == 0.0
    assert data["results"]["total_completed"] == 15.0

def test_simulation_growth(mock_db):
    test_client, db_path = mock_db
    payload = {
        "horizon_hours": 10,
        "capacity_per_hour": 5.0,
        "arrival_rate_per_hour": 10.0,
        "initial_backlog": 0
    }
    resp = test_client.post("/dashboard/review-capacity/simulate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"]["ending_backlog"] == 50.0  # 10*10 = 100 arrivals, 5*10 = 50 completed -> 50 backlog
    assert "grows" in data["interpretation"]

def test_simulation_decay(mock_db):
    test_client, db_path = mock_db
    payload = {
        "horizon_hours": 5,
        "capacity_per_hour": 20.0,
        "arrival_rate_per_hour": 10.0,
        "initial_backlog": 50
    }
    resp = test_client.post("/dashboard/review-capacity/simulate", json=payload)
    data = resp.json()
    # hr 1: start 50, +10 = 60. max comp 20, end 40.
    # hr 2: start 40, +10 = 50. comp 20, end 30.
    # hr 3: start 30, +10 = 40. comp 20, end 20.
    # hr 4: start 20, +10 = 30. comp 20, end 10.
    # hr 5: start 10, +10 = 20. comp 20, end 0.
    assert data["results"]["ending_backlog"] == 0.0
    assert "exceeds" in data["interpretation"]

def test_simulation_stable(mock_db):
    test_client, db_path = mock_db
    payload = {
        "horizon_hours": 10,
        "capacity_per_hour": 15.0,
        "arrival_rate_per_hour": 15.0,
        "initial_backlog": 10
    }
    resp = test_client.post("/dashboard/review-capacity/simulate", json=payload)
    data = resp.json()
    assert data["results"]["ending_backlog"] == 10.0
    assert "balanced" in data["interpretation"]

def test_simulation_observed_mode(mock_db):
    test_client, db_path = mock_db
    payload = {
        "horizon_hours": 24,
        "capacity_per_hour": 10.0,
        "use_observed_arrival": True,
        "initial_backlog": 0
    }
    resp = test_client.post("/dashboard/review-capacity/simulate", json=payload)
    assert resp.status_code == 200
    assert resp.json()["assumptions"]["used_observed_arrival"] is True

def test_simulation_invalid_horizon(mock_db):
    test_client, db_path = mock_db
    payload = {
        "horizon_hours": 1000, # Max 720
        "capacity_per_hour": 10.0,
        "arrival_rate_per_hour": 10.0,
        "initial_backlog": 0
    }
    resp = test_client.post("/dashboard/review-capacity/simulate", json=payload)
    assert resp.status_code == 400

def test_simulation_missing_arrival(mock_db):
    test_client, db_path = mock_db
    payload = {
        "horizon_hours": 24,
        "capacity_per_hour": 10.0,
        "initial_backlog": 0
    }
    resp = test_client.post("/dashboard/review-capacity/simulate", json=payload)
    assert resp.status_code == 400

