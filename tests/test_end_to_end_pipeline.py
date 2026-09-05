import pytest
from fastapi.testclient import TestClient
import os
import tempfile
from database.migrations import run_migrations
from api.app import app
from api.security_service import SecurityService

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    run_migrations(db_path=path)
    yield path
    os.remove(path)

def test_full_happy_path(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    with TestClient(app) as client:
        svc = SecurityService(temp_db)
        meta, raw_secret = svc.create_api_key("EndToEnd Testing", "ADMIN")
        
        payload = {
            "transaction_id": "txn_e2e_001",
            "amount": 12500.0,
            "transaction_amount": 12500.0,
            "customer_id": "cust_e2e_001",
            "email": "fraudster@evil.com",
            "email_domain": "evil.com",
            "card_network": "visa",
            "card_type": "credit",
            "include_explanation": True
        }
        
        res = client.post("/transactions/decide", json=payload, headers={"X-API-Key": raw_secret})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["success"] is True
        dec = data["decision"]
        assert dec["transaction_id"] == "txn_e2e_001"
        
        res_cases = client.get("/cases", headers={"X-API-Key": raw_secret})
        assert res_cases.status_code == 200
        
        cases = res_cases.json().get("cases", [])
        our_case = next((c for c in cases if c["transaction_id"] == "txn_e2e_001"), None)
        assert our_case is not None
        
        fb_payload = {
            "ground_truth": "FRAUD",
            "label_source": "E2E_TEST",
            "notes": "Testing feedback"
        }
        res_fb = client.post(f"/transactions/{our_case['assessment_id']}/feedback", json=fb_payload, headers={"X-API-Key": raw_secret})
        assert res_fb.status_code == 200
        
        res_mon = client.get("/monitoring/summary", headers={"X-API-Key": raw_secret})
        assert res_mon.status_code == 200

def test_idempotency_behavior(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    with TestClient(app) as client:
        svc = SecurityService(temp_db)
        meta, raw_secret = svc.create_api_key("E2E Testing", "ADMIN")
        
        payload = {
            "transaction_id": "txn_idemp_001",
            "amount": 500.0,
            "customer_id": "cust_e2e_001"
        }
        
        res1 = client.post("/transactions/decide", json=payload, headers={"Idempotency-Key": "idemp_k_001", "X-API-Key": raw_secret})
        assert res1.status_code == 200
        
        res2 = client.post("/transactions/decide", json=payload, headers={"Idempotency-Key": "idemp_k_001", "X-API-Key": raw_secret})
        assert res2.status_code == 200
        assert res1.json()["decision"]["transaction_id"] == res2.json()["decision"]["transaction_id"]

def test_api_validation(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    with TestClient(app) as client:
        svc = SecurityService(temp_db)
        meta, raw_secret = svc.create_api_key("E2E Testing", "ADMIN")
        
        payload = {"amount": "not_a_number"}
        res = client.post("/transactions/decide", json=payload, headers={"X-API-Key": raw_secret})
        assert res.status_code == 400
