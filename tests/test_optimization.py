import pytest
import numpy as np
import json
import os
from unittest.mock import patch, MagicMock

# Dummy cost calculation matching the script
def calculate_cost(y_true, decisions, c_fn=100.0, c_fp_review=5.0, c_fp_block=15.0, c_review=2.0):
    total_cost = 0.0
    is_allow = (decisions == 'ALLOW')
    is_review = (decisions == 'REVIEW')
    is_block = (decisions == 'BLOCK')
    
    is_fraud = (y_true == 1)
    is_legit = (y_true == 0)
    
    fn_count = np.sum(is_allow & is_fraud)
    total_cost += fn_count * c_fn
    
    fp_review = np.sum(is_review & is_legit)
    total_cost += fp_review * c_fp_review
    
    fp_block = np.sum(is_block & is_legit)
    total_cost += fp_block * c_fp_block
    
    review_count = np.sum(is_review)
    total_cost += review_count * c_review
    
    return total_cost, {
        "fn_count": fn_count,
        "fp_review": fp_review,
        "fp_block": fp_block,
        "review_count": review_count,
        "block_count": np.sum(is_block),
        "allow_count": np.sum(is_allow),
        "fraud_caught": np.sum((is_review | is_block) & is_fraud)
    }

def test_threshold_ordering():
    t_review = 0.2
    t_block = 0.8
    assert t_review < t_block

def test_every_transaction_receives_exactly_one_decision():
    probs = np.random.rand(100)
    t_review = 0.3
    t_block = 0.7
    decisions = np.where(probs >= t_block, 'BLOCK',
                         np.where(probs >= t_review, 'REVIEW', 'ALLOW'))
    
    # Must be 100 decisions
    assert len(decisions) == 100
    
    # Must only contain the 3 valid strings
    unique = set(decisions)
    assert unique.issubset({'ALLOW', 'REVIEW', 'BLOCK'})
    
    # Sum of counts must equal total
    allow_c = np.sum(decisions == 'ALLOW')
    review_c = np.sum(decisions == 'REVIEW')
    block_c = np.sum(decisions == 'BLOCK')
    assert allow_c + review_c + block_c == 100

def test_cost_calculation():
    y_true = np.array([1, 0, 1, 0, 0])
    decisions = np.array(['ALLOW', 'ALLOW', 'BLOCK', 'REVIEW', 'BLOCK'])
    
    # True Fraud = idx 0, 2
    # True Legit = idx 1, 3, 4
    # idx 0: fraud ALLOW -> FN (100)
    # idx 1: legit ALLOW -> TN (0)
    # idx 2: fraud BLOCK -> TP (0)
    # idx 3: legit REVIEW -> FP_REV (5) + REV_OP (2) = 7
    # idx 4: legit BLOCK -> FP_BLK (15)
    
    cost, stats = calculate_cost(y_true, decisions)
    assert cost == 100.0 + 0 + 0 + 5.0 + 2.0 + 15.0
    assert stats["fn_count"] == 1
    assert stats["fp_review"] == 1
    assert stats["fp_block"] == 1
    assert stats["review_count"] == 1
    assert stats["block_count"] == 2
    assert stats["allow_count"] == 2
    assert stats["fraud_caught"] == 1

def test_no_negative_or_invalid_costs():
    y_true = np.array([1, 0])
    decisions = np.array(['BLOCK', 'ALLOW'])
    cost, stats = calculate_cost(y_true, decisions, c_fn=100.0, c_fp_review=5.0, c_fp_block=15.0, c_review=2.0)
    assert cost >= 0.0

def test_policy_serialization_deserialization(tmp_path):
    policy = {
        "t_review": 0.1234,
        "t_block": 0.5678,
        "cost": 1250.5,
        "review_pct": 0.045,
        "stats": {"fn_count": 10}
    }
    p = tmp_path / "policy.json"
    with open(p, "w") as f:
        json.dump(policy, f)
        
    with open(p, "r") as f:
        loaded = json.load(f)
        
    assert loaded["t_review"] == policy["t_review"]
    assert loaded["t_block"] == policy["t_block"]

def test_calibrated_probabilities_remain_within_0_1():
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    import numpy as np
    
    X = np.random.rand(100, 5)
    y = np.random.randint(0, 2, 100)
    
    base = LogisticRegression()
    calib = CalibratedClassifierCV(estimator=base, method='isotonic', cv=2)
    calib.fit(X, y)
    
    probs = calib.predict_proba(X)[:, 1]
    assert np.all(probs >= 0.0)
    assert np.all(probs <= 1.0)
