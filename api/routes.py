import uuid
import logging
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from api.security import get_api_key
from api.schemas import (
    TransactionRequest, RiskAssessmentResponse, ErrorResponse, ErrorDetail,
    RecordFeedbackRequest, EvaluationFeedbackResponse,
)
from api.service import assess_transaction, AssessmentServiceError, DatabasePersistenceError
from api.events import TransactionEvent, EventMetadata
from database.repository import (
    DuplicateAssessmentError, record_evaluation_feedback,
    get_evaluation_analytics, get_evaluation_timeseries,
)
from database.connection import get_session

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/transactions/assess",
    response_model=RiskAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse}
    }
)
async def assess(txn_request: TransactionRequest, request: Request, api_key: str = Depends(get_api_key)):
    state = request.app.state.razor_state
    if not state.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RazorBrain ML infrastructure is not ready."
        )

    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    txn_dict = txn_request.model_dump()

    try:
        assessment_record = await run_in_threadpool(assess_transaction, txn_dict, state)

        decision_rec = assessment_record.get("decision_record", {})
        mapped_result = {
            "assessment_id": assessment_record.get("assessment_id"),
            "transaction_id": assessment_record.get("transaction_id"),
            "primary_risk_probability": assessment_record.get("primary_risk_probability"),
            "confidence_in_probability": assessment_record.get("confidence_in_probability"),
            "decision_record": {
                "decision": decision_rec.get("decision", "REVIEW"),
                "decision_reason": decision_rec.get("decision_reason"),
                "blocking_guardrail_status": decision_rec.get("blocking_guardrail_status")
            },
            "rule_evidence": assessment_record.get("rule_evidence", []),
            "model_evidence": assessment_record.get("model_evidence", []),
            "explanation_record": assessment_record.get("explanation_record")
        }
        return mapped_result

    except DuplicateAssessmentError as e:
        logger.warning(f"[{req_id}] Duplicate assessment: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate assessment.")
    except AssessmentServiceError as e:
        logger.error(f"[{req_id}] Assessment failure: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Assessment computation failed."
        )
    except DatabasePersistenceError as e:
        logger.error(f"[{req_id}] Persistence failure: {e}")
        err = ErrorResponse(
            error=ErrorDetail(
                code="HTTP_500",
                message="Audit persistence failed.",
                request_id=req_id
            )
        )
        return JSONResponse(status_code=500, content=jsonable_encoder({"error": err.error.model_dump(), "partial_result": e.decision_result}))
    except Exception as e:
        logger.error(f"[{req_id}] Unhandled error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error.")


@router.get("/health")
async def health():
    return {"status": "ok", "service": "razorbrain_api"}


@router.get("/ready")
async def ready(request: Request):
    state = request.app.state.razor_state

    if not getattr(state, "serving_model_ready", False):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Serving model unavailable.")

    return {
        "status": "ready",
        "model_c_ready": getattr(state, "is_ready", False),
        "serving_model_ready": True,
        "feature_contract_valid": True
    }


class EventAcceptedResponse(BaseModel):
    event_id: str
    status: str
    correlation_id: str
    message: str


@router.post(
    "/transactions/events",
    response_model=EventAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def submit_transaction_event(txn_request: TransactionRequest, request: Request, api_key: str = Depends(get_api_key)):
    state = request.app.state.razor_state
    if not state.is_ready or not state.broker:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RazorBrain ML infrastructure is not ready."
        )

    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    event = TransactionEvent(
        metadata=EventMetadata(
            event_type="transaction.received",
            correlation_id=req_id
        ),
        payload=txn_request
    )

    success = await state.broker.publish("transaction.received", event.model_dump())
    if not success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Processing queue is full. Please try again later."
        )

    return EventAcceptedResponse(
        event_id=event.metadata.event_id,
        status="ACCEPTED",
        correlation_id=event.metadata.correlation_id,
        message="Transaction accepted for processing."
    )


@router.post("/transactions/{assessment_id}/feedback", response_model=EvaluationFeedbackResponse)
def record_feedback(
    assessment_id: str,
    feedback: RecordFeedbackRequest,
    request: Request,
    api_key: str = Depends(get_api_key)
):
    state = request.app.state.razor_state
    try:
        with get_session(state.db_path) as conn:
            result = record_evaluation_feedback(
                conn,
                assessment_id,
                ground_truth=feedback.ground_truth.upper(),
                label_source=feedback.label_source,
                notes=feedback.notes
            )
            return result
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error recording feedback: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/evaluation", response_model=dict)
def get_evaluation_dashboard(
    request: Request,
    api_key: str = Depends(get_api_key)
):
    state = request.app.state.razor_state
    try:
        with get_session(state.db_path) as conn:
            metrics = get_evaluation_analytics(conn)
            timeseries = get_evaluation_timeseries(conn)
            return {
                "metrics": metrics,
                "timeseries": timeseries
            }
    except Exception as e:
        logger.error(f"Error fetching analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
