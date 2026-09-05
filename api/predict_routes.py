"""
Dedicated manual transaction scoring route module.
Reuses the authoritative 15-feature contract preprocessing pipeline and
the calibrated XGBoost serving model without duplicating ML logic.
"""
import datetime
import logging
import math
import uuid
import json
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator

from api.security import get_api_key

from api.security import rate_limit
from api.idempotency_service import IdempotencyService, IdempotencyError
import hashlib

from model.serving_feature_extractor import (
    extract_serving_features,
    ServingFeatureExtractorError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Prediction"])

# ── Request / Response Models ─────────────────────────────────────────────────

class PredictRequest(BaseModel):
    transaction_id: Optional[str] = Field(None, max_length=100)
    amount: Optional[float] = Field(None, allow_inf_nan=False)
    transaction_amount: Optional[float] = Field(None, allow_inf_nan=False)

    customer_id: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=150)
    email_domain: Optional[str] = Field(None, max_length=100)

    card_network: Optional[str] = Field("MISSING", max_length=50)
    card_type: Optional[str] = Field("MISSING", max_length=50)

    timestamp: Optional[str] = Field(None, max_length=50)
    hour_of_day: Optional[int] = Field(None, ge=0, le=23)
    day_of_week: Optional[int] = Field(None, ge=0, le=6)

    previous_transaction_count: Optional[int] = Field(0, ge=0)
    is_new_customer: Optional[int] = Field(None, ge=0, le=1)
    avg_customer_amount: Optional[float] = Field(0.0, ge=0.0)
    amount_deviation: Optional[float] = Field(None, ge=0.0)
    amount_ratio: Optional[float] = Field(None, ge=0.0)
    txns_last_1h: Optional[int] = Field(0, ge=0)
    txns_last_24h: Optional[int] = Field(0, ge=0)
    include_explanation: Optional[bool] = Field(False)

    @model_validator(mode="before")
    @classmethod
    def validate_amount_alias(cls, values: Any) -> Any:
        if isinstance(values, dict):
            amt = values.get("amount")
            txn_amt = values.get("transaction_amount")
            if amt is None and txn_amt is not None:
                values["amount"] = txn_amt
            elif amt is not None and txn_amt is None:
                values["transaction_amount"] = amt
            if values.get("amount") is None:
                raise ValueError("Transaction amount is required.")
        return values

    @field_validator("amount")
    @classmethod
    def check_amount_positive(cls, v: Optional[float]) -> float:
        if v is None:
            raise ValueError("Transaction amount is required.")
        if not math.isfinite(v):
            raise ValueError("Amount must be a finite number.")
        if v <= 0.0:
            raise ValueError("Transaction amount must be strictly greater than zero.")
        return float(v)

    @field_validator("transaction_id", "customer_id", "email", "email_domain", "card_network", "card_type")
    @classmethod
    def check_not_whitespace_only(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                return None
            return stripped
        return v


class PredictionDetails(BaseModel):
    transaction_id: str
    fraud_probability: float
    risk_level: str
    thresholds: Dict[str, float]
    model_version: str
    model_track: str
    calibrator: str
    scored_at: str
    features_used: Dict[str, Any]

class PredictResponse(BaseModel):
    success: bool
    prediction: PredictionDetails

class DecisionDetails(BaseModel):
    transaction_id: str
    fraud_probability: float
    risk_level: str
    base_decision: str = "APPROVE"
    triggered_rules: List[Dict[str, Any]] = []
    hybrid_assessment: Optional[Dict[str, Any]] = None
    final_decision: str
    decision_reason: str
    decision_trace: List[Dict[str, Any]]
    thresholds: Dict[str, float]
    model_version: str
    model_track: str = "RAZORPAY_SERVING_MODEL"
    calibrator: str = "isotonic"
    rule_policy_version: str = "1.0"
    fusion_version: str = "1.0"
    case: Optional[Dict[str, Any]] = None
    explanation: Optional[Dict[str, Any]] = None
    scored_at: str
    features_used: Dict[str, Any]

class DecideResponse(BaseModel):
    success: bool
    decision: DecisionDetails


def _run_core_inference(payload: PredictRequest, request: Request):
    state = getattr(request.app.state, "razor_state", None)
    if not state or not getattr(state, "serving_model_ready", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction service is currently unavailable. ML serving model is not ready.",
        )

    loader = getattr(state, "serving_loader", None)
    if not loader:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction service is currently unavailable. Model loader is missing.",
        )

    txn_id = payload.transaction_id or f"txn_{uuid.uuid4().hex[:12]}"
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_utc.isoformat()

    ts_str = payload.timestamp if payload.timestamp else now_iso

    email_val = payload.email
    if not email_val and payload.email_domain:
        email_val = f"user@{payload.email_domain}"

    payment_dict = {
        "amount": payload.amount,
        "timestamp": ts_str,
        "email": email_val,
        "card_network": payload.card_network,
        "card_type": payload.card_type,
    }

    prev_count = payload.previous_transaction_count if payload.previous_transaction_count is not None else 0
    if payload.is_new_customer is not None:
        is_new = int(payload.is_new_customer)
    else:
        is_new = 1 if prev_count == 0 else 0

    if is_new == 1:
        avg_amt, deviation, ratio, txns_1h, txns_24h, prev_count = 0.0, 0.0, 1.0, 0, 0, 0
    else:
        avg_amt = float(payload.avg_customer_amount or 0.0)
        deviation = float(payload.amount_deviation) if payload.amount_deviation is not None else (abs(payload.amount - avg_amt) if avg_amt > 0 else 0.0)
        ratio = float(payload.amount_ratio) if payload.amount_ratio is not None else ((payload.amount / avg_amt) if avg_amt > 0 else 1.0)
        txns_1h = int(payload.txns_last_1h or 0)
        txns_24h = int(payload.txns_last_24h or 0)

    history_dict = {
        "previous_transaction_count": prev_count,
        "is_new_customer": is_new,
        "avg_customer_amount": avg_amt,
        "amount_deviation": deviation,
        "amount_ratio": ratio,
        "txns_last_1h": txns_1h,
        "txns_last_24h": txns_24h,
    }

    try:
        X, availability = extract_serving_features(payment_dict, history_dict)
    except ServingFeatureExtractorError as e:
        logger.warning(f"Serving feature extraction rejected: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid feature extraction: {e}")
    except Exception as e:
        logger.error(f"Serving feature extraction unexpected failure: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Feature processing failed internally.")

    if payload.hour_of_day is not None:
        X["hour_of_day"] = payload.hour_of_day
    if payload.day_of_week is not None:
        X["day_of_week"] = payload.day_of_week

    try:
        raw_prob_array = loader.predict_calibrated_proba(X)
        prob = float(raw_prob_array[0])
    except Exception as e:
        logger.error(f"Inference calculation failure: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Model prediction error during scoring.")

    if not math.isfinite(prob) or prob < 0.0 or prob > 1.0:
        logger.error(f"Model returned non-finite or out-of-range probability: {prob}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Model returned an invalid probability value.")

    fraud_probability = max(0.0, min(1.0, prob))
    
    features_used = X.iloc[0].to_dict()
    for k, v in features_used.items():
        if not isinstance(v, (int, float, str, bool)):
            features_used[k] = float(v) if hasattr(v, "item") else str(v)

    return fraud_probability, features_used, txn_id, now_iso, state, X


@router.post(
    "/predict",
    response_model=PredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Score a transaction manually using the trained calibrated ML model",
)
@router.post(
    "/transactions/predict",
    response_model=PredictResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def predict_transaction(
    payload: PredictRequest,
    request: Request,
    api_key: Optional[str] = Depends(get_api_key),
    _rate_limit: None = Depends(rate_limit('predict', 50, 5.0)),
):
    fraud_probability, features_used, txn_id, now_iso, state, X = _run_core_inference(payload, request)

    policy_loader = getattr(state, "serving_policy_loader", None)
    t_review = float(getattr(policy_loader, "t_review", 0.1213))
    t_block = float(getattr(policy_loader, "t_block", 0.2053))

    if fraud_probability < t_review:
        risk_level = "LOW"
    elif fraud_probability < t_block:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    loader = getattr(state, "serving_loader", None)
    loader_meta = getattr(loader, "metadata", {}) or {}
    model_version = loader_meta.get("version", "1.0")

    return PredictResponse(
        success=True,
        prediction=PredictionDetails(
            transaction_id=txn_id,
            fraud_probability=fraud_probability,
            risk_level=risk_level,
            thresholds={
                "low_risk_cutoff": t_review,
                "high_risk_cutoff": t_block,
            },
            model_version=model_version,
            model_track="RAZORPAY_SERVING_MODEL",
            calibrator="isotonic",
            scored_at=now_iso,
            features_used=features_used,
        ),
    )


@router.post(
    "/transactions/decide",
    response_model=DecideResponse,
    status_code=status.HTTP_200_OK,
    summary="Make a final business decision for a transaction",
)
async def decide_transaction(
    payload: PredictRequest,
    request: Request,
    api_key: Optional[str] = Depends(get_api_key),
    _rate_limit: None = Depends(rate_limit('predict', 50, 5.0)),
):
    idempotency_key = request.headers.get("Idempotency-Key")
    payload_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    
    db_path = getattr(request.app.state, "razor_state", None).db_path if getattr(request.app.state, "razor_state", None) else "razorbrain_api.db"
    idemp_svc = IdempotencyService(db_path)
    
    if idempotency_key:
        try:
            cached = idemp_svc.check_or_store(idempotency_key, payload_hash)
            if cached:
                return cached["response"]
        except IdempotencyError as e:
            raise HTTPException(status_code=400, detail=str(e))
    fraud_probability, features_used, txn_id, now_iso, state, X = _run_core_inference(payload, request)

    # 1. Base ML risk level
    policy_loader = getattr(state, "serving_policy_loader", None)
    t_review = float(getattr(policy_loader, "t_review", 0.1213))
    t_block = float(getattr(policy_loader, "t_block", 0.2053))

    if fraud_probability < t_review:
        risk_level = "LOW"
    elif fraud_probability < t_block:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    # 2. Decision Engine v2 with Hybrid Risk Fusion
    decision_engine = getattr(state, "decision_engine_v2", None)
    if not decision_engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Decision Engine is currently unavailable.",
        )
        
    final_decision, decision_reason, decision_trace, hybrid_assessment = decision_engine.evaluate_hybrid(
        probability=fraud_probability,
        features=features_used,
        model_risk_level=risk_level,
    )

    # 3. Generate Explanation if requested or needed for auto-case creation
    explanation_result = None
    if payload.include_explanation or (
        getattr(state, "case_policy", None) 
        and getattr(state, "case_policy").should_create_case(final_decision)
    ):
        expl_svc = getattr(state, "serving_explanation_service", None)
        if expl_svc:
            try:
                explanation_result = expl_svc.explain_transaction(X, fraud_probability)
                if explanation_result.get("status") != "AVAILABLE":
                    logger.warning(f"Explanation unavailable: {explanation_result.get('reason')}")
                    explanation_result = None
            except Exception as e:
                logger.error(f"Failed to generate explanation: {e}", exc_info=True)
                explanation_result = None
                # Option B from instructions: continue without explanation snapshot on failure

    # 4. Log to WAL database
    import uuid
    assessment_id = str(uuid.uuid4())
    db_path = getattr(state, "db_path", "razorbrain_api.db")
    import sqlite3
    try:
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO serving_assessments (
                    assessment_id, transaction_id, timestamp, risk, decision, decision_reason, decision_trace,
                    model_version, policy_version, feature_contract_version,
                    rule_policy_version, triggered_rules, fusion_version, fusion_result, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                assessment_id,
                txn_id,
                now_iso,
                fraud_probability,
                final_decision,
                decision_reason,
                json.dumps(decision_trace),
                getattr(state, "active_model_version", "unknown"),
                getattr(state, "active_policy_version", "unknown"),
                getattr(state, "active_feature_contract_version", "unknown"),
                getattr(decision_engine.rule_engine, "policy_version", "1.0"),
                json.dumps([r.to_dict() for r in hybrid_assessment.triggered_rules]),
                hybrid_assessment.fusion_version,
                json.dumps(hybrid_assessment.to_dict()),
                now_iso
            ))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to persist decision to DB: {e}")
        # Non-fatal for the API response

    loader = getattr(state, "serving_loader", None)
    loader_meta = getattr(loader, "metadata", {}) or {}
    model_version = loader_meta.get("version", "1.0")

    # 5. Evaluate case creation policy & create case if appropriate
    case_ref: Dict[str, Any] = {"case_created": False, "reason": f"FINAL_DECISION_{final_decision}"}
    try:
        from api.case_service import CaseService, CasePolicy
        case_policy = getattr(state, "case_policy", None) or CasePolicy()
        if case_policy.should_create_case(final_decision):
            case_svc = CaseService(db_path=db_path, policy=case_policy)
            created_case = case_svc.create_case(
                transaction_id=txn_id,
                assessment_id=assessment_id,
                final_decision=final_decision,
                decision_reason=decision_reason,
                decision_snapshot={
                    "amount": payload.amount,
                    "fraud_probability": fraud_probability,
                    "risk_level": risk_level,
                    "base_decision": hybrid_assessment.base_decision,
                    "final_decision": final_decision,
                    "decision_reason": decision_reason,
                },
                risk_snapshot={
                    "calibrated_probability": fraud_probability,
                    "model_risk_level": risk_level,
                    "model_track": "RAZORPAY_SERVING_MODEL",
                    "model_version": model_version,
                    "calibrator": "isotonic",
                    "thresholds": {
                        "approve_max": decision_engine.policy.t_approve,
                        "review_max": decision_engine.policy.t_review,
                        "step_up_max": decision_engine.policy.t_step_up,
                    },
                },
                rule_snapshot={
                    "rule_policy_version": getattr(decision_engine.rule_engine, "policy_version", "1.0"),
                    "triggered_rules": [r.to_dict() for r in hybrid_assessment.triggered_rules],
                    "fusion_version": hybrid_assessment.fusion_version,
                },
                explanation_snapshot=explanation_result,
                actor="DECISION_ENGINE",
            )
            case_ref = {
                "case_created": True,
                "case_id": created_case["case_id"],
                "status": created_case["status"],
                "priority": created_case["priority"],
            }
    except Exception as e:
        logger.error(f"Automatic investigation case creation failed: {e}", exc_info=True)
        case_ref = {
            "case_created": False,
            "warning": "Case creation encountered an internal error but transaction assessment was preserved.",
        }

    response_obj = DecideResponse(
        success=True,
        decision=DecisionDetails(
            transaction_id=txn_id,
            fraud_probability=fraud_probability,
            risk_level=risk_level,
            base_decision=hybrid_assessment.base_decision,
            triggered_rules=[r.to_dict() for r in hybrid_assessment.triggered_rules],
            hybrid_assessment=hybrid_assessment.to_dict(),
            final_decision=final_decision,
            decision_reason=decision_reason,
            decision_trace=decision_trace,
            thresholds={
                "approve_max": decision_engine.policy.t_approve,
                "review_max": decision_engine.policy.t_review,
                "step_up_max": decision_engine.policy.t_step_up,
            },
            model_version=model_version,
            model_track="RAZORPAY_SERVING_MODEL",
            calibrator="isotonic",
            rule_policy_version=getattr(decision_engine.rule_engine, "policy_version", "1.0"),
            fusion_version=hybrid_assessment.fusion_version,
            case=case_ref,
            explanation=explanation_result if payload.include_explanation else None,
            scored_at=now_iso,
            features_used=features_used,
        )
    )
    if idempotency_key:
        idemp_svc.save_response(idempotency_key, payload_hash, response_obj.dict(), 200)
    return response_obj


@router.post(
    "/transactions/explain",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get detailed SHAP explanations for a transaction",
)
async def explain_transaction(
    payload: PredictRequest,
    request: Request,
    api_key: Optional[str] = Depends(get_api_key),
    _rate_limit: None = Depends(rate_limit('predict', 50, 5.0)),
):
    fraud_probability, features_used, txn_id, now_iso, state, X = _run_core_inference(payload, request)

    expl_svc = getattr(state, "serving_explanation_service", None)
    if not expl_svc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Explanation service is currently unavailable.",
        )
        
    try:
        explanation_result = expl_svc.explain_transaction(X, fraud_probability)
        if explanation_result.get("status") != "AVAILABLE":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Explanation unavailable: {explanation_result.get('reason')}"
            )
        
        return {
            "success": True,
            "transaction_id": txn_id,
            "explanation": explanation_result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explanation extraction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal error generating explanation."
        )
