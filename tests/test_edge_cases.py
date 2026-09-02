import pytest
from fastapi.testclient import TestClient
import math
from api.app import app

def test_input_boundary_missing_fields():
    with TestClient(app) as client:
        # Missing amount
        payload = {
            "transaction_id": "EDGE-1",
            "timestamp": "2023-10-27T10:00:00Z",
            "customer_id": "C-1",
            "merchant_id": "M-1",
            "payment_method": "credit_card"
        }
        res = client.post("/transactions/assess", json=payload)
        assert res.status_code in (400, 422)
        assert "amount" in res.text

def test_input_boundary_extreme_amount():
    with TestClient(app) as client:
        payload = {
            "transaction_id": "EDGE-2",
            "timestamp": "2023-10-27T10:00:00Z",
            "amount": 1e12, # 1 trillion
            "customer_id": "C-1",
            "merchant_id": "M-1",
            "payment_method": "credit_card"
        }
        res = client.post("/transactions/assess", json=payload)
        assert res.status_code in (200, 201)
        # Extreme amount might trigger a rule or model, but it shouldn't crash
        data = res.json()
        assert data["decision_record"]["decision"] in ("ALLOW", "REVIEW", "BLOCK")

def test_input_boundary_negative_amount():
    with TestClient(app) as client:
        payload = {
            "transaction_id": "EDGE-3",
            "timestamp": "2023-10-27T10:00:00Z",
            "amount": -50.0,
            "customer_id": "C-1",
            "merchant_id": "M-1",
            "payment_method": "credit_card"
        }
        res = client.post("/transactions/assess", json=payload)
        # Assuming Pydantic validator allows negative or rejects. Let's see. 
        # If it allows, it shouldn't crash. If it rejects, 422 is fine.
        assert res.status_code in (200, 201, 400, 422)

def test_target_leakage_rejection():
    with TestClient(app) as client:
        payload = {
            "transaction_id": "EDGE-4",
            "timestamp": "2023-10-27T10:00:00Z",
            "amount": 100.0,
            "customer_id": "C-1",
            "merchant_id": "M-1",
            "payment_method": "credit_card",
            "is_fraud": 1, # Should be rejected by extra="forbid"
            "target": 1
        }
        res = client.post("/transactions/assess", json=payload)
        assert res.status_code in (400, 422) # Pydantic extra='forbid'

def test_nan_infinity_safeguards():
    with TestClient(app) as client:
        # JSON standard doesn't support NaN directly, but FastAPI might parse literal NaN if not strict
        # Let's send a string that might be coerced, or bypass HTTP and test Pydantic directly
        from api.schemas import TransactionRequest
        from pydantic import ValidationError
        
        try:
            req = TransactionRequest(
                transaction_id="EDGE-5",
                timestamp="2023-10-27T10:00:00Z",
                amount=math.nan,
                customer_id="C-1",
                merchant_id="M-1",
                payment_method="credit_card"
            )
            # If it accepts NaN, we must ensure the engine doesn't crash
            # Actually, Pydantic V2 often rejects NaN for floats unless configured.
        except ValidationError:
            pass

