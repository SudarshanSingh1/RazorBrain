import uuid
import logging
from fastapi.responses import JSONResponse
from fastapi import APIRouter, Request, HTTPException, status, Depends
from api.security import get_api_key

from api.schemas import TransactionRequest, RiskAssessmentResponse, ErrorResponse, ErrorDetail
from api.service import assess_transaction, AssessmentServiceError, DatabasePersistenceError
from database.repository import DuplicateAssessmentError

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
        
    req_id = getattr(request.state, "request_id", str(uuid.uuid4())) # Trace identifier
    
    txn_dict = txn_request.model_dump()
    
    try:
        from fastapi.concurrency import run_in_threadpool
        assessment_record = await run_in_threadpool(assess_transaction, txn_dict, state)
        # Ensure we return valid schema mapping
        return assessment_record
        
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
        # Return 500 but embed the identical authoritative decision payload so the client can still act on it.
        # This guarantees decision immutability during secondary failures.
        err = ErrorResponse(
            error=ErrorDetail(
                code="HTTP_500",
                message="Audit persistence failed.",
                request_id=req_id
            )
        )
        return JSONResponse(status_code=500, content={"error": err.error.model_dump(), "partial_result": e.decision_result})
    except Exception as e:
        logger.error(f"[{req_id}] Unhandled error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error.")


@router.get("/health")
async def health():
    return {"status": "ok", "service": "razorbrain_api"}


@router.get("/ready")
async def ready(request: Request):
    state = request.app.state.razor_state
    if state.is_ready:
        return {"status": "ready"}
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Not ready.")

from api.events import TransactionEvent, EventMetadata
from pydantic import BaseModel

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
    
    # Construct the internal event
    event = TransactionEvent(
        metadata=EventMetadata(
            event_type="transaction.received",
            correlation_id=req_id
        ),
        payload=txn_request
    )
    
    # Publish to the internal broker
    success = await state.broker.publish("transaction.received", event.model_dump())
    
    if not success:
        # Backpressure response
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
