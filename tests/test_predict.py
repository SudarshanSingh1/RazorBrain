"""
Unit and integration tests for the /predict endpoint (Feature 1: Manual Transaction Scoring).
Ensures 100% adherence to the 15-feature contract, strict validation, safe defaults,
and boundary handling.
"""
import pytest
from fastapi.testclient import TestClient
from api.app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("RAZORBRAIN_API_KEY", raising=False)
    with TestClient(app) as c:
        yield c


def test_predict_valid_standard_transaction(client):
    payload = {
        "transaction_id": "txn_test_valid_01",
        "amount": 2500.0,
        "email": "customer@gmail.com",
        "card_network": "visa",
        "card_type": "credit",
        "hour_of_day": 14,
        "day_of_week": 2,
        "previous_transaction_count": 5,
        "avg_customer_amount": 1800.0,
        "txns_last_1h": 1,
        "txns_last_24h": 3,
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    pred = data["prediction"]
    assert pred["transaction_id"] == "txn_test_valid_01"
    assert isinstance(pred["fraud_probability"], float)
    assert 0.0 <= pred["fraud_probability"] <= 1.0
    assert pred["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert "thresholds" in pred
    assert pred["thresholds"]["low_risk_cutoff"] == 0.1213
    assert pred["thresholds"]["high_risk_cutoff"] == 0.2053
    assert pred["model_version"] == "1.0"
    assert pred["model_track"] == "RAZORPAY_SERVING_MODEL"
    assert pred["calibrator"] == "isotonic"
    assert "features_used" in pred
    assert len(pred["features_used"]) == 15


def test_predict_transaction_amount_alias(client):
    payload = {
        "transaction_amount": 1200.0,
        "card_network": "mastercard",
        "card_type": "debit"
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["prediction"]["features_used"]["amount"] == 1200.0


def test_predict_min_values(client):
    payload = {
        "amount": 0.01,
        "hour_of_day": 0,
        "day_of_week": 0,
        "previous_transaction_count": 0,
        "avg_customer_amount": 0.0,
        "txns_last_1h": 0,
        "txns_last_24h": 0,
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert 0.0 <= data["prediction"]["fraud_probability"] <= 1.0


def test_predict_max_reasonable_values(client):
    payload = {
        "amount": 50_000_000.0,
        "hour_of_day": 23,
        "day_of_week": 6,
        "previous_transaction_count": 100_000,
        "avg_customer_amount": 10_000_000.0,
        "txns_last_1h": 500,
        "txns_last_24h": 2000,
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert 0.0 <= data["prediction"]["fraud_probability"] <= 1.0


def test_predict_negative_amount_rejected(client):
    payload = {"amount": -100.0}
    res = client.post("/predict", json=payload)
    assert res.status_code == 400


def test_predict_zero_amount_rejected(client):
    payload = {"amount": 0.0}
    res = client.post("/predict", json=payload)
    assert res.status_code == 400


def test_predict_missing_amount_rejected(client):
    payload = {"card_network": "visa"}
    res = client.post("/predict", json=payload)
    assert res.status_code == 400


def test_predict_invalid_hour_rejected(client):
    payload = {"amount": 500.0, "hour_of_day": 25}
    res = client.post("/predict", json=payload)
    assert res.status_code == 400


def test_predict_invalid_day_of_week_rejected(client):
    payload = {"amount": 500.0, "day_of_week": 7}
    res = client.post("/predict", json=payload)
    assert res.status_code == 400


def test_predict_negative_velocity_rejected(client):
    payload = {"amount": 500.0, "txns_last_1h": -5}
    res = client.post("/predict", json=payload)
    assert res.status_code == 400


def test_predict_unknown_categorical_handled_safely(client):
    payload = {
        "amount": 999.0,
        "card_network": "hyper_unknown_network_xyz",
        "card_type": "crypto_token",
        "email_domain": "exotic-alien-domain.biz",
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert 0.0 <= data["prediction"]["fraud_probability"] <= 1.0


def test_predict_cold_start_defaults(client):
    payload = {
        "amount": 3000.0,
        "is_new_customer": 1,
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    features = data["prediction"]["features_used"]
    assert features["is_new_customer"] == 1
    assert features["previous_transaction_count"] == 0
    assert features["avg_customer_amount"] == 0.0
    assert features["amount_deviation"] == 0.0
    assert features["amount_ratio"] == 1.0
    assert features["txns_last_1h"] == 0
    assert features["txns_last_24h"] == 0


def test_predict_risk_level_mapping(client):
    # Verify risk level strictly matches threshold boundaries
    payload = {"amount": 2500.0}
    res = client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()["prediction"]
    prob = data["fraud_probability"]
    level = data["risk_level"]
    low_cutoff = data["thresholds"]["low_risk_cutoff"]
    high_cutoff = data["thresholds"]["high_risk_cutoff"]

    if prob < low_cutoff:
        assert level == "LOW"
    elif prob < high_cutoff:
        assert level == "MEDIUM"
    else:
        assert level == "HIGH"


def test_predict_transactions_alias_route(client):
    payload = {"amount": 750.0}
    res = client.post("/transactions/predict", json=payload)
    assert res.status_code == 200
    assert res.json()["success"] is True
