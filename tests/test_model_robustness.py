from api.app import app
from data.generator import generate_transactions
from model.feature_engineering import compute_historical_features

def test_temporal_leakage_safety():
    """Prove that historical features for row T depend only on rows before T."""
    df = generate_transactions(n=500, seed=42)
    # Pick a timestamp in the middle
    mid_idx = 250
    df.iloc[mid_idx]["timestamp"]
    
    # Engineer features on the full dataset
    df_full_features = compute_historical_features(df.copy())
    full_target_features = df_full_features.iloc[mid_idx]
    
    # Now chop off all rows AFTER mid_idx and compute again
    df_chopped = df.iloc[:mid_idx+1].copy()
    df_chopped_features = compute_historical_features(df_chopped)
    chopped_target_features = df_chopped_features.iloc[-1]
    
    # The historical features for the target row must be exactly identical
    assert full_target_features["avg_customer_amount"] == chopped_target_features["avg_customer_amount"]
    assert full_target_features["txns_last_24h"] == chopped_target_features["txns_last_24h"]

def test_model_robustness_cold_start():
    """Test model behavior for completely missing history (Cold Start)."""
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        # A transaction with completely unseen customer/merchant
        txn = {
            "transaction_id": "COLD-1",
            "timestamp": "2023-10-27T10:00:00Z",
            "amount": 100.0,
            "customer_id": "C-COLD-START-1",
            "merchant_id": "M-COLD-START-1",
            "payment_method": "credit_card"
        }
        
        res = client.post("/transactions/assess", json=txn)
        assert res.status_code == 201
        
        record = res.json()
        assert isinstance(record["primary_risk_probability"], float)
        assert record["decision"] in ["ALLOW", "REVIEW"]

def test_missing_data_null_probability_fallback():
    """Test decision behavior when probability falls back to None."""
    from model.decision_engine import DecisionPolicy, make_decision
    
    policy = DecisionPolicy(allow_threshold=0.3, block_threshold=0.7)
    
    fusion_result = {
        "primary_risk_probability": None,
        "confidence_in_probability": "NONE",
        "rule_evidence": []
    }
    result = make_decision(fusion_result, policy)
    assert result["decision"] == "REVIEW"
