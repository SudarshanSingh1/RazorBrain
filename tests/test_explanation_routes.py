from fastapi.testclient import TestClient
from api.app import app

def test_explain_transaction():
    payload = {
        "amount": 2500,
        "customer_id": "cust_123",
        "email": "test@example.com",
        "card_network": "visa",
        "card_type": "credit",
        "is_new_customer": True
    }
    
    with TestClient(app) as client:
        response = client.post("/transactions/explain", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "explanation" in data
    assert data["explanation"]["status"] == "AVAILABLE"
    assert "top_positive" in data["explanation"]
    assert "top_negative" in data["explanation"]
    assert "description" in data["explanation"]["top_positive"][0]

def test_decide_with_explanation():
    payload = {
        "amount": 50000,
        "customer_id": "cust_high",
        "email": "high@example.com",
        "card_network": "visa",
        "card_type": "credit",
        "is_new_customer": True,
        "include_explanation": True
    }
    
    with TestClient(app) as client:
        response = client.post("/transactions/decide", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        decision = data["decision"]
        assert decision["explanation"]["status"] == "AVAILABLE"
        assert "metadata" in decision["explanation"]
        
        # Assert case was created and captured explanation
        case = decision["case"]
        if case["case_created"]:
            case_id = case["case_id"]
            case_response = client.get(f"/cases/{case_id}")
            assert case_response.status_code == 200
            case_data = case_response.json()["case"]
            assert case_data["explanation_snapshot"] is not None
            assert case_data["explanation_snapshot"]["status"] == "AVAILABLE"

