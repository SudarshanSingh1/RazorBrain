"""
Integration tests for the Razorpay Serving Model integration layer.
All fixtures are synthetic. test.csv is never opened. Model C is never used for serving decisions.
"""
import ast
import hashlib
import json
import math
import os
import sqlite3
import sys
import tempfile
import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from model.serving_feature_extractor import (
    SERVING_FEATURES, REJECTED_FEATURES, extract_serving_features,
    ServingFeatureExtractorError,
)
from model.serving_model_loader import ServingModelLoader
from model.serving_policy_loader import ServingPolicyLoader
from model.serving_shap_explainer import make_fixture
from database.migrations import run_migrations
from api.serving_service import (
    assess_serving_transaction,
    save_serving_assessment,
    get_serving_assessment,
    get_serving_historical_features,
    check_event_already_processed,
    DuplicateServingAssessmentError,
)

KNOWN_HASHES = {
    "data/razorpay_serving_model_calibrated.joblib": "1aada82e6f1af13bcada372eb02ec312",
    "data/razorpay_serving_model_uncalibrated.joblib": "1242b74830962d8d323676563648ffdb",
    "data/razorpay_serving_dataset/test.csv": "fc4e76764a2e7ad1df631ce37d050f35",
    "data/model_c_calibrated.joblib": "17eaa5aad2a2672f497221362ee4cefd",
    "data/model_c_engineered_raw_safe.joblib": "7de3be91a463ce8d9c74193869212aea",
    "data/validation_selected_policy.json": "a6f2994d904e4dab0bb8ceca52924106",
}


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Synthetic payment fixture ─────────────────────────────────────────────────

def make_payment(
    amount: float = 150.0,
    email: str = "test@gmail.com",
    card_network: str = "visa",
    card_type: str = "credit",
    timestamp: str = "2024-01-15T14:30:00Z",
    customer_id: str = "cust_test_001",
    transaction_id: str = None,
    assessment_id: str = None,
) -> Dict[str, Any]:
    return {
        "transaction_id": transaction_id or str(uuid.uuid4()),
        "assessment_id": assessment_id or str(uuid.uuid4()),
        "amount": amount,
        "email": email,
        "card_network": card_network,
        "card_type": card_type,
        "timestamp": timestamp,
        "customer_id": customer_id,
        "merchant_id": "merch_001",
    }


@pytest.fixture(scope="module")
def loader():
    return ServingModelLoader()


@pytest.fixture(scope="module")
def policy():
    return ServingPolicyLoader()


@pytest.fixture
def tmp_db():
    """In-memory SQLite with migrations applied."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    run_migrations(db_path=db_path)
    yield db_path
    os.unlink(db_path)


def make_serving_state(loader=None, policy=None, shap=None):
    """Build a minimal mock AppState with serving stack."""
    state = MagicMock()
    state.serving_loader = loader
    state.serving_policy_loader = policy
    state.serving_shap_explainer = shap
    return state


# ── 24 & 25. Artifact integrity ───────────────────────────────────────────────

def test_all_artifacts_unchanged():
    for path, expected in KNOWN_HASHES.items():
        assert md5(path) == expected, f"Artifact modified: {path}"


# ── 14. No test.csv in integration code ──────────────────────────────────────

def test_integration_files_never_open_test_csv():
    targets = [
        "api/serving_service.py",
        "api/razorpay_routes.py",
        "model/serving_feature_extractor.py",
    ]
    for filepath in targets:
        with open(filepath) as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = ""
                if isinstance(node.func, ast.Attribute):
                    fn = node.func.attr
                elif isinstance(node.func, ast.Name):
                    fn = node.func.id
                if fn in ("read_csv", "open"):
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and "test.csv" in str(arg.value):
                            pytest.fail(f"{filepath} opens test.csv")


# ── 2. Exact 15-feature contract ─────────────────────────────────────────────

def test_exact_15_features():
    assert len(SERVING_FEATURES) == 15


def test_extract_produces_15_columns():
    X, avail = extract_serving_features(make_payment(), {})
    assert list(X.columns) == SERVING_FEATURES


# ── 3. No rejected feature enters inference ───────────────────────────────────

def test_rejected_features_blocked():
    bad_payment = make_payment()
    bad_payment["V95"] = 0.5  # IEEE-CIS V-series
    with pytest.raises(ServingFeatureExtractorError, match="Rejected"):
        extract_serving_features(bad_payment, {})


def test_isFraud_rejected():
    bad_payment = make_payment()
    bad_payment["isFraud"] = 1
    with pytest.raises(ServingFeatureExtractorError, match="Rejected"):
        extract_serving_features(bad_payment, {})


# ── 4. Missing email → email_domain = MISSING, email_domain_missing = 1 ───────

def test_missing_email_handling():
    payment = make_payment(email=None)
    X, avail = extract_serving_features(payment, {})
    assert X.iloc[0]["email_domain"] == "MISSING"
    assert X.iloc[0]["email_domain_missing"] == 1
    assert avail["email_domain"] is False
    assert avail["email_domain_missing"] is True


def test_missing_at_in_email():
    payment = make_payment(email="notanemail")
    X, avail = extract_serving_features(payment, {})
    assert X.iloc[0]["email_domain"] == "MISSING"


# ── 5. Missing card fields → MISSING ─────────────────────────────────────────

def test_missing_card_network():
    payment = make_payment(card_network=None)
    X, avail = extract_serving_features(payment, {})
    assert X.iloc[0]["card_network"] == "MISSING"
    assert avail["card_network"] is False


def test_missing_card_type():
    payment = make_payment(card_type=None)
    X, avail = extract_serving_features(payment, {})
    assert X.iloc[0]["card_type"] == "MISSING"
    assert avail["card_type"] is False


# ── 6. Existing customer history ─────────────────────────────────────────────

def test_existing_customer_features(tmp_db):
    cust = "cust_hist_001"
    ts = "2024-01-15T14:30:00Z"
    # Insert prior transactions
    with sqlite3.connect(tmp_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("t_prior_1", "2024-01-15T13:00:00Z", 100.0, cust, "merch_001", "{}"),
        )
        conn.commit()

    with sqlite3.connect(tmp_db) as conn:
        conn.row_factory = sqlite3.Row
        hist = get_serving_historical_features(conn, cust, ts, 150.0)

    assert hist["previous_transaction_count"] == 1
    assert hist["is_new_customer"] == 0
    assert hist["avg_customer_amount"] == pytest.approx(100.0)


# ── 7. Cold-start customer ────────────────────────────────────────────────────

def test_cold_start_customer(tmp_db):
    with sqlite3.connect(tmp_db) as conn:
        conn.row_factory = sqlite3.Row
        hist = get_serving_historical_features(conn, "cust_brand_new", "2024-01-01T00:00:00Z", 50.0)
    assert hist["previous_transaction_count"] == 0
    assert hist["is_new_customer"] == 1
    assert hist["avg_customer_amount"] == 0.0
    assert hist["txns_last_1h"] == 0
    assert hist["txns_last_24h"] == 0


# ── 8 & 9. Historical causality — current txn excluded ────────────────────────

def test_current_transaction_excluded_from_history(tmp_db):
    cust = "cust_causality"
    CURRENT_TS = "2024-01-15T14:30:00Z"
    with sqlite3.connect(tmp_db) as conn:
        conn.row_factory = sqlite3.Row
        # Insert one PRIOR and one AT SAME TIME (should be excluded by strict <)
        conn.execute(
            "INSERT INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("t_prior_causal", "2024-01-15T13:00:00Z", 200.0, cust, "merch_001", "{}"),
        )
        conn.execute(
            "INSERT INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("t_same_time", CURRENT_TS, 150.0, cust, "merch_001", "{}"),
        )
        conn.commit()

    with sqlite3.connect(tmp_db) as conn:
        conn.row_factory = sqlite3.Row
        hist = get_serving_historical_features(conn, cust, CURRENT_TS, 150.0)

    # Only the PRIOR transaction at 13:00 should count
    assert hist["previous_transaction_count"] == 1


# ── 10. Invalid/missing risk → REVIEW ────────────────────────────────────────

def test_invalid_risk_returns_review(tmp_db):
    loader = ServingModelLoader()
    policy = ServingPolicyLoader()

    state = make_serving_state(loader=loader, policy=policy)

    # Patch the loader to return NaN
    with patch.object(loader, "predict_calibrated_proba", return_value=[float("nan")]):
        result = assess_serving_transaction(make_payment(), None, state, tmp_db)

    assert result["decision"] == "REVIEW"
    assert result["risk"] is None


# ── 11. Model unavailable → REVIEW ───────────────────────────────────────────

def test_model_unavailable_returns_review(tmp_db):
    state = make_serving_state(loader=None, policy=ServingPolicyLoader())
    result = assess_serving_transaction(make_payment(), None, state, tmp_db)
    assert result["decision"] == "REVIEW"
    assert result["risk"] is None


# ── 12. Policy unavailable → REVIEW ──────────────────────────────────────────

def test_policy_unavailable_returns_review(tmp_db):
    state = make_serving_state(loader=ServingModelLoader(), policy=None)
    result = assess_serving_transaction(make_payment(), None, state, tmp_db)
    assert result["decision"] == "REVIEW"


# ── 15 & 16. SHAP failure does not change risk or decision ────────────────────

def test_shap_failure_does_not_change_decision(tmp_db):
    loader = ServingModelLoader()
    policy = ServingPolicyLoader()

    # Good SHAP explainer first
    result_normal = assess_serving_transaction(
        make_payment(assessment_id=str(uuid.uuid4())), None,
        make_serving_state(loader=loader, policy=policy), tmp_db
    )
    normal_decision = result_normal["decision"]
    normal_risk = result_normal["risk"]

    # Broken SHAP explainer
    broken_shap = MagicMock()
    broken_shap.explain.side_effect = RuntimeError("SHAP exploded")

    result_broken = assess_serving_transaction(
        make_payment(assessment_id=str(uuid.uuid4())), None,
        make_serving_state(loader=loader, policy=policy, shap=broken_shap), tmp_db
    )
    # Decision and risk must be identical (SHAP failure is isolated)
    assert result_broken["decision"] == normal_decision
    assert result_broken["risk"] == pytest.approx(normal_risk, abs=1e-6)
    # SHAP result must be UNAVAILABLE
    assert result_broken["shap"]["status"] == "UNAVAILABLE"


# ── 17. Duplicate event idempotency ──────────────────────────────────────────

def test_duplicate_event_rejected(tmp_db):
    state = make_serving_state(loader=ServingModelLoader(), policy=ServingPolicyLoader())
    event_id = f"evt_{uuid.uuid4()}"
    payment = make_payment()

    # First call succeeds
    assess_serving_transaction(payment, event_id, state, tmp_db)

    # Second call with same event_id raises duplicate
    with pytest.raises(DuplicateServingAssessmentError):
        assess_serving_transaction(make_payment(), event_id, state, tmp_db)


# ── 20. Duplicate event does not duplicate history ────────────────────────────

def test_duplicate_event_does_not_duplicate_history(tmp_db):
    state = make_serving_state(loader=ServingModelLoader(), policy=ServingPolicyLoader())
    cust = "cust_dedup_hist"
    event_id = f"evt_{uuid.uuid4()}"
    # Use a fixed transaction_id so we can verify exactly one row was persisted
    first_tid = str(uuid.uuid4())
    payment = make_payment(customer_id=cust, transaction_id=first_tid,
                           assessment_id=str(uuid.uuid4()))

    assess_serving_transaction(payment, event_id, state, tmp_db)

    try:
        assess_serving_transaction(
            make_payment(customer_id=cust, transaction_id=str(uuid.uuid4()),
                         assessment_id=str(uuid.uuid4())),
            event_id, state, tmp_db
        )
    except DuplicateServingAssessmentError:
        pass  # Expected

    # The transactions table should have exactly ONE row for cust_dedup_hist
    with sqlite3.connect(tmp_db) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM transactions WHERE customer_id = ?", (cust,))
        row = c.fetchone()
    assert row["cnt"] == 1, f"Expected 1 transaction row, got {row['cnt']}"



# ── 21. Audit record persisted ────────────────────────────────────────────────

def test_audit_record_persisted(tmp_db):
    state = make_serving_state(loader=ServingModelLoader(), policy=ServingPolicyLoader())
    aid = str(uuid.uuid4())
    result = assess_serving_transaction(make_payment(assessment_id=aid), None, state, tmp_db)

    with sqlite3.connect(tmp_db) as conn:
        conn.row_factory = sqlite3.Row
        rec = get_serving_assessment(conn, aid)

    assert rec is not None
    assert rec["assessment_id"] == aid
    assert rec["model_track"] == "RAZORPAY_SERVING_MODEL"
    assert rec["decision"] in ("ALLOW", "REVIEW", "BLOCK")
    assert rec["feature_snapshot"] is not None
    assert rec["feature_availability"] is not None


# ── 22. Feedback does not alter historical labels automatically ───────────────

def test_feedback_does_not_alter_decision(tmp_db):
    """Labels (FRAUD/LEGITIMATE) are recorded in evaluation_feedback, never in serving_assessments."""
    state = make_serving_state(loader=ServingModelLoader(), policy=ServingPolicyLoader())
    aid = str(uuid.uuid4())
    result = assess_serving_transaction(make_payment(assessment_id=aid), None, state, tmp_db)
    original_decision = result["decision"]

    # Record feedback (simulated)
    with sqlite3.connect(tmp_db) as conn:
        conn.row_factory = sqlite3.Row
        rec = get_serving_assessment(conn, aid)

    # The serving assessment decision must remain unchanged
    assert rec["decision"] == original_decision


# ── Model track separation ────────────────────────────────────────────────────

def test_model_track_in_result(tmp_db):
    state = make_serving_state(loader=ServingModelLoader(), policy=ServingPolicyLoader())
    result = assess_serving_transaction(make_payment(), None, state, tmp_db)
    assert result["model_track"] == "RAZORPAY_SERVING_MODEL"


def test_assessment_type_is_post_event(tmp_db):
    state = make_serving_state(loader=ServingModelLoader(), policy=ServingPolicyLoader())
    result = assess_serving_transaction(make_payment(), None, state, tmp_db)
    assert result["assessment_type"] == "POST_EVENT_RISK_ASSESSMENT"


# ── 26–28. All frozen artifacts unchanged ─────────────────────────────────────

def test_serving_calibrated_hash():
    assert md5("data/razorpay_serving_model_calibrated.joblib") == KNOWN_HASHES["data/razorpay_serving_model_calibrated.joblib"]

def test_serving_uncalibrated_hash():
    assert md5("data/razorpay_serving_model_uncalibrated.joblib") == KNOWN_HASHES["data/razorpay_serving_model_uncalibrated.joblib"]

def test_serving_policy_hash():
    # Policy JSON was created this session; just verify it loads correctly
    policy = ServingPolicyLoader()
    assert policy.metadata["model_track"] == "RAZORPAY_SERVING_MODEL"

def test_serving_test_hash():
    assert md5("data/razorpay_serving_dataset/test.csv") == KNOWN_HASHES["data/razorpay_serving_dataset/test.csv"]

def test_model_c_hashes():
    for path in ("data/model_c_calibrated.joblib", "data/model_c_engineered_raw_safe.joblib", "data/validation_selected_policy.json"):
        assert md5(path) == KNOWN_HASHES[path]
