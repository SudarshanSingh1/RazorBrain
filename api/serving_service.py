"""
Authoritative serving assessment service for the Razorpay Serving Model.

Decision pipeline:
    features → ServingModelLoader → isotonic calibration → ServingPolicyLoader → ALLOW/REVIEW/BLOCK

SHAP is a separate, optional, read-only operation that never influences the decision.

Fail-closed semantics:
    - RISK_UNAVAILABLE → REVIEW
    - SERVING_MODEL_UNAVAILABLE → REVIEW
    - POLICY_UNAVAILABLE → REVIEW
    - Any NaN / Inf risk → REVIEW
"""
import json
import logging
import math
import uuid
import datetime
from typing import Any, Dict, Optional

import sqlite3

logger = logging.getLogger(__name__)

# ── Sentinel strings ───────────────────────────────────────────────────────────
MODEL_TRACK = "RAZORPAY_SERVING_MODEL"
ASSESSMENT_TYPE = "POST_EVENT_RISK_ASSESSMENT"


class ServingAssessmentError(Exception):
    pass


class DuplicateServingAssessmentError(Exception):
    pass


# ── Repository helpers (serving_assessments table) ────────────────────────────

def save_serving_assessment(
    conn: sqlite3.Connection,
    assessment_id: str,
    transaction_id: str,
    event_id: Optional[str],
    timestamp: str,
    risk: Optional[float],
    decision: str,
    decision_reason: str,
    feature_snapshot: Dict[str, Any],
    feature_availability: Dict[str, bool],
    shap_snapshot: Optional[Dict[str, Any]],
    model_version: str,
    calibration_version: str,
    policy_version: str,
    customer_id: Optional[str] = None,
) -> None:
    """Persist a serving assessment record. Idempotent via assessment_id PK."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    c = conn.cursor()

    # Ensure transaction row exists
    c.execute("SELECT 1 FROM transactions WHERE transaction_id = ?", (transaction_id,))
    if not c.fetchone():
        c.execute(
            "INSERT INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (transaction_id, timestamp, feature_snapshot.get("amount"), customer_id, None,
             json.dumps(feature_snapshot)),
        )

    try:
        c.execute(
            """
            INSERT INTO serving_assessments (
                assessment_id, transaction_id, event_id, assessment_type,
                model_track, model_version, calibration_version, policy_version,
                timestamp, risk, decision, decision_reason,
                feature_snapshot, feature_availability, shap_snapshot,
                processing_status, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                assessment_id, transaction_id, event_id, ASSESSMENT_TYPE,
                MODEL_TRACK, model_version, calibration_version, policy_version,
                timestamp, risk, decision, decision_reason,
                json.dumps(feature_snapshot), json.dumps(feature_availability),
                json.dumps(shap_snapshot) if shap_snapshot is not None else None,
                "COMPLETED", now,
            ),
        )
    except sqlite3.IntegrityError:
        raise DuplicateServingAssessmentError(
            f"Serving assessment {assessment_id} already exists."
        )


def get_serving_assessment(conn: sqlite3.Connection, assessment_id: str) -> Optional[Dict[str, Any]]:
    c = conn.cursor()
    c.execute("""
        SELECT s.*, t.timestamp as txn_timestamp, t.amount, t.customer_id, t.merchant_id, t.context_data
        FROM serving_assessments s
        JOIN transactions t ON s.transaction_id = t.transaction_id
        WHERE s.assessment_id = ?
    """, (assessment_id,))
    row = c.fetchone()
    if not row:
        return None
    rec = dict(row)
    for key in ("decision_reason", "feature_snapshot", "feature_availability", "shap_snapshot"):
        if rec.get(key):
            try:
                rec[key] = json.loads(rec[key])
            except Exception:
                pass
    return rec


def get_serving_assessments_paginated(
    conn: sqlite3.Connection, limit: int = 50, offset: int = 0
) -> list:
    c = conn.cursor()
    c.execute(
        "SELECT assessment_id, transaction_id, timestamp, risk, decision, model_track"
        " FROM serving_assessments ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return [dict(r) for r in c.fetchall()]


def check_event_already_processed(conn: sqlite3.Connection, event_id: str) -> bool:
    """Return True if a serving assessment already exists for this event_id."""
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM serving_assessments WHERE event_id = ?", (event_id,)
    )
    return c.fetchone() is not None


# ── Historical feature query for serving model ─────────────────────────────────

def get_serving_historical_features(
    conn: sqlite3.Connection,
    customer_id: str,
    current_timestamp: str,
    current_amount: float,
) -> Dict[str, Any]:
    """
    Compute exactly the history-derived serving features using data strictly before
    current_timestamp. Never includes the current transaction.
    Uses transactions table (shared store) — no duplication.
    """
    import datetime as dt

    c = conn.cursor()
    c.execute(
        "SELECT amount, timestamp FROM transactions"
        " WHERE customer_id = ? AND timestamp < ?"
        " ORDER BY timestamp ASC",
        (customer_id, current_timestamp),
    )
    rows = c.fetchall()
    prev_count = len(rows)
    is_new = 1 if prev_count == 0 else 0

    if prev_count == 0:
        return {
            "previous_transaction_count": 0,
            "is_new_customer": 1,
            "avg_customer_amount": 0.0,
            "amount_deviation": 0.0,
            "amount_ratio": 1.0,
            "txns_last_1h": 0,
            "txns_last_24h": 0,
        }

    amounts = [float(r[0]) for r in rows]
    avg_amt = sum(amounts) / prev_count
    deviation = abs(current_amount - avg_amt)
    ratio = current_amount / avg_amt if avg_amt > 0 else 1.0

    try:
        ts = dt.datetime.fromisoformat(current_timestamp.replace("Z", "+00:00"))
    except Exception:
        ts = dt.datetime.now(dt.timezone.utc)

    txns_1h = 0
    txns_24h = 0
    for r in rows:
        try:
            rt = dt.datetime.fromisoformat(str(r[1]).replace("Z", "+00:00"))
            delta = ts - rt
            if delta <= dt.timedelta(hours=1):
                txns_1h += 1
            if delta <= dt.timedelta(hours=24):
                txns_24h += 1
        except Exception:
            pass

    return {
        "previous_transaction_count": prev_count,
        "is_new_customer": is_new,
        "avg_customer_amount": avg_amt,
        "amount_deviation": deviation,
        "amount_ratio": ratio,
        "txns_last_1h": txns_1h,
        "txns_last_24h": txns_24h,
    }


# ── Main serving assessment function ─────────────────────────────────────────

def assess_serving_transaction(
    payment: Dict[str, Any],
    event_id: Optional[str],
    serving_state,          # AppState, must have serving_loader, serving_policy_loader
    db_path: str,
) -> Dict[str, Any]:
    """
    Full serving model pipeline:
      1. Duplicate event check
      2. Historical feature extraction from DB
      3. Serving feature construction
      4. Model scoring + isotonic calibration
      5. Policy decision
      6. Audit persistence
      7. SHAP explanation (async-safe, never touches decision)

    Returns the persisted assessment record.
    """
    from database.connection import get_session
    from model.serving_feature_extractor import extract_serving_features, ServingFeatureExtractorError

    transaction_id = payment.get("transaction_id", str(uuid.uuid4()))
    timestamp = payment.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
    customer_id = payment.get("customer_id", "")
    amount = float(payment.get("amount", 0.0))

    # ── 1. Duplicate event guard ──────────────────────────────────────────────
    if event_id:
        with get_session(db_path) as conn:
            if check_event_already_processed(conn, event_id):
                raise DuplicateServingAssessmentError(
                    f"Event {event_id} already has a serving assessment."
                )

    # ── 2. Historical features from DB ────────────────────────────────────────
    try:
        with get_session(db_path) as conn:
            history = get_serving_historical_features(
                conn, customer_id, timestamp, amount
            )
    except Exception as e:
        logger.error(f"Historical feature query failed: {e}. Using cold-start defaults.")
        history = {}

    # ── 3. Feature extraction ─────────────────────────────────────────────────
    try:
        X, availability = extract_serving_features(payment, history)
    except ServingFeatureExtractorError as e:
        logger.error(f"Feature extraction rejected: {e}")
        raise ServingAssessmentError(f"Feature extraction error: {e}") from e
    except Exception as e:
        logger.error(f"Feature extraction failed unexpectedly: {e}")
        raise ServingAssessmentError(f"Feature extraction failed: {e}") from e

    feature_snapshot = X.iloc[0].to_dict()

    # ── 4. Scoring ────────────────────────────────────────────────────────────
    loader = getattr(serving_state, "serving_loader", None)
    if loader is None:
        logger.error("Serving model loader not available.")
        risk = None
        scoring_status = "SERVING_MODEL_UNAVAILABLE"
    else:
        try:
            raw_scores = loader.predict_calibrated_proba(X)
            risk = float(raw_scores[0])
            if not math.isfinite(risk):
                risk = None
                scoring_status = "RISK_UNAVAILABLE"
            else:
                scoring_status = "OK"
        except Exception as e:
            logger.error(f"Serving model scoring failed: {e}")
            risk = None
            scoring_status = f"SCORING_ERROR: {e}"

    # ── 5. Policy decision ────────────────────────────────────────────────────
    policy_loader = getattr(serving_state, "serving_policy_loader", None)
    if policy_loader is None:
        decision = "REVIEW"
        decision_reason = {
            "reason": "POLICY_UNAVAILABLE",
            "model_track": MODEL_TRACK,
            "risk": None,
        }
    elif risk is None:
        decision = "REVIEW"
        decision_reason = {
            "reason": scoring_status,
            "model_track": MODEL_TRACK,
            "risk": None,
        }
    else:
        decision = policy_loader.make_decision(risk)
        decision_reason = {
            "reason": "POLICY_THRESHOLD",
            "model_track": MODEL_TRACK,
            "risk": risk,
            "threshold_review": policy_loader.t_review,
            "threshold_block": policy_loader.t_block,
            "decision": decision,
        }

    # Assessment ID: prefer payment's idempotency key, else generate
    assessment_id = payment.get("assessment_id") or str(uuid.uuid4())

    # ── 6. Persist ────────────────────────────────────────────────────────────
    loader_meta = getattr(loader, "metadata", {}) if loader else {}
    cal_artifact = {}
    try:
        import joblib
        cal_art = joblib.load("data/razorpay_serving_model_calibrated.joblib")
        cal_artifact = cal_art.get("metadata", {})
    except Exception:
        pass

    model_version = loader_meta.get("version", "unknown")
    calibration_version = cal_artifact.get("calibrator_type", "isotonic")
    policy_version = getattr(policy_loader, "metadata", {}).get("policy_version", "1.0") if policy_loader else "unknown"

    with get_session(db_path) as conn:
        save_serving_assessment(
            conn=conn,
            assessment_id=assessment_id,
            transaction_id=transaction_id,
            event_id=event_id,
            timestamp=timestamp,
            risk=risk,
            decision=decision,
            decision_reason=json.dumps(decision_reason),
            feature_snapshot=feature_snapshot,
            feature_availability=availability,
            shap_snapshot=None,  # populated below after persistence
            model_version=model_version,
            calibration_version=calibration_version,
            policy_version=policy_version,
            customer_id=customer_id,
        )


    # ── 7. SHAP (separate, read-only, never alters risk or decision) ──────────
    shap_result = None
    shap_explainer = getattr(serving_state, "serving_shap_explainer", None)
    if shap_explainer is not None:
        try:
            shap_result = shap_explainer.explain(X)
        except Exception as e:
            logger.error(f"SHAP explanation failed (decision unchanged): {e}")
            shap_result = {"status": "UNAVAILABLE", "reason": f"Internal error: {e}"}

    # Persist SHAP snapshot (separate update, does not touch decision)
    if shap_result is not None:
        with get_session(db_path) as conn:
            conn.execute(
                "UPDATE serving_assessments SET shap_snapshot = ? WHERE assessment_id = ?",
                (json.dumps(shap_result), assessment_id),
            )

    return {
        "assessment_id": assessment_id,
        "transaction_id": transaction_id,
        "model_track": MODEL_TRACK,
        "assessment_type": ASSESSMENT_TYPE,
        "model_version": model_version,
        "calibration_version": calibration_version,
        "policy_version": policy_version,
        "risk": risk,
        "decision": decision,
        "decision_reason": decision_reason,
        "feature_availability": availability,
        "feature_snapshot": feature_snapshot,
        "shap": shap_result,
    }
