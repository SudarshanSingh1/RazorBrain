"""
Razorpay Test Mode routes.

The /assess endpoint now uses the Razorpay Serving Model stack (not Model C).
The webhook endpoint enqueues events for asynchronous processing.
A new /investigate endpoint provides full SHAP + audit detail for a serving assessment.

POST_EVENT_RISK_ASSESSMENT semantics:
  Scoring occurs after Razorpay has authorized/captured the payment.
  This is explicitly represented as POST_EVENT_RISK_ASSESSMENT.
  The decision CANNOT retroactively block an already-processed payment.
"""
import hmac
import hashlib
import json
import os
import uuid
import logging
from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional

from api.security import get_api_key
from api.razorpay_adapter import (
    RazorpayAdapter, RazorpayConfigurationError, RazorpayAdapterError,
    normalize_razorpay_payment,
)
from api.events import TransactionEvent, EventMetadata
from api.serving_service import (
    assess_serving_transaction,
    get_serving_assessment,
    DuplicateServingAssessmentError,
    ServingAssessmentError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/razorpay/test", tags=["razorpay_test_mode"])


# ── Request / Response models ─────────────────────────────────────────────────

class CreateTestOrderRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount in subunits (e.g. paise)")
    currency: str = Field("INR", max_length=10)
    receipt: str = Field(..., max_length=100)
    notes: Dict[str, str] = Field(..., description="Must contain customer_id and merchant_id")


class CreateTestOrderResponse(BaseModel):
    id: str
    amount: int
    currency: str
    receipt: str
    status: str


class AssessTestPaymentRequest(BaseModel):
    payment_id: str = Field(..., max_length=100)


class ServingAssessmentResponse(BaseModel):
    assessment_id: str
    transaction_id: str
    model_track: str
    assessment_type: str
    risk: Optional[float]
    decision: str
    decision_reason: Dict[str, Any]
    feature_availability: Dict[str, bool]


class InvestigateResponse(BaseModel):
    assessment_id: str
    transaction_id: str
    amount: Optional[float] = None
    customer_id: Optional[str] = None
    merchant_id: Optional[str] = None
    txn_timestamp: Optional[str] = None
    context_data: Optional[Any] = None
    model_track: str
    assessment_type: str
    risk: Optional[float]
    decision: str
    decision_reason: Any
    feature_snapshot: Any
    feature_availability: Any
    shap: Any
    model_explanation_note: str = (
        "SHAP values explain which features pushed the XGBoost model score higher or lower. "
        "They are NOT proof of fraud. Positive SHAP = INCREASES_MODEL_SCORE."
    )
    decision_reason_note: str = (
        "Decision reason reflects calibrated risk vs. policy thresholds. "
        "Model explanation and decision reason are separate."
    )


# ── Razorpay adapter dependency ───────────────────────────────────────────────

def get_razorpay_adapter() -> RazorpayAdapter:
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    mode = os.environ.get("RAZORPAY_MODE", "test")
    if not key_id or not key_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Razorpay Test Mode credentials are not configured on this server.",
        )
    try:
        return RazorpayAdapter(key_id=key_id, key_secret=key_secret, mode=mode)
    except RazorpayConfigurationError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── Order creation ────────────────────────────────────────────────────────────

@router.post("/orders", response_model=CreateTestOrderResponse)
async def create_order(
    order_req: CreateTestOrderRequest,
    request: Request,
    api_key: str = Depends(get_api_key),
    adapter: RazorpayAdapter = Depends(get_razorpay_adapter),
):
    if "customer_id" not in order_req.notes or "merchant_id" not in order_req.notes:
        raise HTTPException(
            status_code=400, detail="Notes must contain customer_id and merchant_id"
        )

    # Inject server-observed IP (cannot be spoofed from body)
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "127.0.0.1"
    )
    order_req.notes["ip_address"] = client_ip

    # Inject header-validated session_id
    session_id = request.headers.get("x-session-id")
    if session_id and len(session_id) <= 36:
        order_req.notes["session_id"] = session_id
    elif "session_id" in order_req.notes:
        del order_req.notes["session_id"]

    try:
        rzp_order = await adapter.create_test_order(
            amount=order_req.amount,
            currency=order_req.currency,
            receipt=order_req.receipt,
            notes=order_req.notes,
        )
        return CreateTestOrderResponse(
            id=rzp_order["id"],
            amount=rzp_order["amount"],
            currency=rzp_order["currency"],
            receipt=rzp_order.get("receipt", order_req.receipt),
            status=rzp_order.get("status", "created"),
        )
    except RazorpayAdapterError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating Razorpay order: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Serving-model assessment ──────────────────────────────────────────────────

@router.post("/assess", response_model=ServingAssessmentResponse)
async def assess_payment(
    assess_req: AssessTestPaymentRequest,
    request: Request,
    api_key: str = Depends(get_api_key),
    adapter: RazorpayAdapter = Depends(get_razorpay_adapter),
):
    """
    Fetch a Razorpay payment by ID and assess it using the Razorpay Serving Model.

    POST_EVENT semantics: Razorpay has already authorized/captured the payment before
    this endpoint is called. The decision is a POST_EVENT_RISK_ASSESSMENT and cannot
    retroactively block the payment.

    Uses only RAZORPAY_SERVING_MODEL. Never falls back to Model C.
    """
    state = request.app.state.razor_state
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    try:
        # Fetch actual payment from Razorpay (server-side; no client-supplied data)
        rzp_payment = await adapter.fetch_payment(assess_req.payment_id)

        # Extract email and card fields that are NOT in the canonical TransactionRequest
        email = rzp_payment.get("email")
        card_info = rzp_payment.get("card", {}) or {}
        card_network = card_info.get("network")
        card_type = card_info.get("type")

        # Normalize to canonical transaction
        canonical_txn = normalize_razorpay_payment(rzp_payment)
        payment_dict = canonical_txn.model_dump()

        # Augment with fields the serving model needs that are not in TransactionRequest
        payment_dict["email"] = email
        payment_dict["card_network"] = card_network
        payment_dict["card_type"] = card_type

        # Run the serving pipeline in a threadpool (CPU-bound model inference)
        result = await run_in_threadpool(
            assess_serving_transaction,
            payment_dict,
            None,           # event_id: no Razorpay event ID in pull-mode assessment
            state,
            state.db_path,
        )

        return ServingAssessmentResponse(
            assessment_id=result["assessment_id"],
            transaction_id=result["transaction_id"],
            model_track=result["model_track"],
            assessment_type=result["assessment_type"],
            risk=result["risk"],
            decision=result["decision"],
            decision_reason=result["decision_reason"],
            feature_availability=result["feature_availability"],
        )

    except DuplicateServingAssessmentError as e:
        logger.warning(f"[{req_id}] Duplicate serving assessment: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate assessment.")
    except ServingAssessmentError as e:
        logger.error(f"[{req_id}] Serving assessment failed: {e}")
        raise HTTPException(status_code=500, detail="Serving assessment computation failed.")
    except RazorpayAdapterError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[{req_id}] Unhandled error in /assess: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Investigation endpoint ────────────────────────────────────────────────────

@router.get("/investigate/{assessment_id}", response_model=InvestigateResponse)
async def investigate_assessment(
    assessment_id: str,
    request: Request,
    api_key: str = Depends(get_api_key),
):
    """
    Return full audit detail for a serving model assessment, including:
    - transaction information
    - calibrated risk and decision
    - policy thresholds
    - feature values and availability
    - SHAP explanation (model explanation, NOT decision evidence)
    - decision reason

    Explicitly distinguishes MODEL EXPLANATION from DECISION REASON.
    SHAP output is model explanation. Decision reason is threshold comparison.
    Neither constitutes proof of fraud.
    """
    state = request.app.state.razor_state
    from database.connection import get_session

    with get_session(state.db_path) as conn:
        rec = get_serving_assessment(conn, assessment_id)

    if not rec:
        raise HTTPException(status_code=404, detail="Serving assessment not found.")

    import json
    context_data = None
    if rec.get("context_data"):
        try:
            context_data = json.loads(rec["context_data"])
        except Exception:
            pass

    return InvestigateResponse(
        assessment_id=rec["assessment_id"],
        transaction_id=rec["transaction_id"],
        amount=rec.get("amount"),
        customer_id=rec.get("customer_id"),
        merchant_id=rec.get("merchant_id"),
        txn_timestamp=rec.get("txn_timestamp"),
        context_data=context_data,
        model_track=rec["model_track"],
        assessment_type=rec["assessment_type"],
        risk=rec.get("risk"),
        decision=rec["decision"],
        decision_reason=rec.get("decision_reason"),
        feature_snapshot=rec.get("feature_snapshot"),
        feature_availability=rec.get("feature_availability"),
        shap=rec.get("shap_snapshot"),
    )


# ── Webhook ───────────────────────────────────────────────────────────────────

webhook_router = APIRouter(prefix="/webhooks/razorpay", tags=["razorpay_webhook"])


@webhook_router.post("")
async def razorpay_webhook(request: Request):
    """
    Receives Razorpay webhook events.

    Security:
    - HMAC-SHA256 signature validated over the raw body before any parsing.
    - Signature comparison is constant-time.
    - Raw body is NOT re-serialized before validation.
    - Secrets are never logged.

    Idempotency:
    - Uses x-razorpay-event-id header (or payload id) for deduplication.
    - Duplicate events are acknowledged without re-processing.

    POST_EVENT semantics:
    - payment.captured / payment.authorized arrive after Razorpay authorization.
    - The assessment is POST_EVENT_RISK_ASSESSMENT and cannot block the payment.
    """
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    mode = os.environ.get("RAZORPAY_MODE", "test")
    if not secret:
        raise HTTPException(status_code=501, detail="Webhook secret not configured.")
    if mode.lower() != "test":
        raise HTTPException(status_code=501, detail="Webhook only supports TEST mode.")

    signature = request.headers.get("x-razorpay-signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature.")

    # Read raw body BEFORE any parsing
    raw_body = await request.body()

    # Constant-time HMAC-SHA256 verification over the raw bytes
    expected_signature = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=401, detail="Invalid signature.")

    # Parse only after signature is verified
    try:
        payload_dict = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed JSON payload.")

    event_type = payload_dict.get("event")
    rzp_event_id = (
        request.headers.get("x-razorpay-event-id")
        or payload_dict.get("id")
        or str(uuid.uuid4())
    )
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    supported_events = {"payment.captured", "payment.authorized"}
    if event_type not in supported_events:
        logger.info(f"[{req_id}] Ignored unsupported webhook event: {event_type}")
        return {"status": "ignored", "reason": "unsupported_event"}

    try:
        payment_entity = payload_dict["payload"]["payment"]["entity"]
        if not payment_entity.get("id"):
            raise ValueError("Payment entity missing ID")
    except KeyError:
        raise HTTPException(status_code=400, detail="Malformed event payload structure.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        canonical_txn = normalize_razorpay_payment(payment_entity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    state = request.app.state.razor_state
    if not state.is_ready and not state.serving_model_ready:
        raise HTTPException(status_code=503, detail="RazorBrain ML infrastructure not ready.")

    if not state.broker:
        raise HTTPException(status_code=503, detail="RazorBrain event broker not ready.")

    event = TransactionEvent(
        metadata=EventMetadata(
            event_id=rzp_event_id,
            event_type="transaction.received",
            correlation_id=req_id,
        ),
        payload=canonical_txn,
    )

    success = await state.broker.publish("transaction.received", event.model_dump())
    if not success:
        raise HTTPException(status_code=503, detail="Processing queue is full. Retry later.")

    logger.info(f"[{req_id}] Webhook {event_type} accepted for event {rzp_event_id}.")
    return {"status": "accepted", "event_id": rzp_event_id}
