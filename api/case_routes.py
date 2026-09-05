"""
Case Management API Routes for RazorBrain.

Provides structured endpoints for querying, assigning, investigating,
escalating, and resolving investigation cases.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.case_service import (
    CaseNotFoundError,
    CasePolicy,
    CaseService,
    CaseServiceError,
    ConcurrencyConflictError,
    InvalidStateTransitionError,
)
from api.security import get_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases", tags=["Case Management"])


def get_case_service(request: Request) -> CaseService:
    state = getattr(request.app.state, "razor_state", None)
    db_path = getattr(state, "db_path", "razorbrain_api.db") if state else "razorbrain_api.db"
    policy = getattr(state, "case_policy", None) or CasePolicy()
    return CaseService(db_path=db_path, policy=policy)


# ── Pydantic Request & Response Schemas ───────────────────────────────────────

class CreateCaseRequest(BaseModel):
    transaction_id: str = Field(..., min_length=1, max_length=100)
    assessment_id: str = Field(..., min_length=1, max_length=100)
    final_decision: str = Field(..., min_length=1, max_length=50)
    decision_reason: str = Field(..., min_length=1, max_length=200)
    decision_snapshot: Dict[str, Any] = Field(default_factory=dict)
    risk_snapshot: Dict[str, Any] = Field(default_factory=dict)
    rule_snapshot: Dict[str, Any] = Field(default_factory=dict)
    priority_override: Optional[str] = None
    assigned_to: Optional[str] = None
    actor: str = "ANALYST"


class AssignCaseRequest(BaseModel):
    assigned_to: str = Field(..., min_length=1, max_length=100)
    expected_version: int = Field(..., ge=1)
    actor: str = "ANALYST"


class InvestigateCaseRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    notes: Optional[str] = None
    actor: str = "ANALYST"


class EscalateCaseRequest(BaseModel):
    escalation_reason: str = Field(..., min_length=3, max_length=500)
    expected_version: int = Field(..., ge=1)
    actor: str = "ANALYST"


class ResolveCaseRequest(BaseModel):
    resolution_type: str = Field(..., min_length=1, max_length=50)
    resolution_notes: Optional[str] = Field(None, max_length=2000)
    expected_version: int = Field(..., ge=1)
    actor: str = "ANALYST"


class CaseItem(BaseModel):
    case_id: str
    transaction_id: str
    assessment_id: str
    status: str
    priority: str
    assigned_to: Optional[str] = None
    created_from_decision: str
    created_from_reason: str
    version: int
    created_at: str
    updated_at: str
    resolved_at: Optional[str] = None
    audit_metadata: Optional[Dict[str, Any]] = None


class CaseDetailResponse(BaseModel):
    success: bool
    case: Dict[str, Any]
    events: List[Dict[str, Any]]


class PaginationMetadata(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class CaseListStats(BaseModel):
    open_cases: int
    investigating_cases: int
    escalated_cases: int
    resolved_cases: int
    high_critical_open: int
    resolved_today: int


class CaseListResponse(BaseModel):
    success: bool
    items: List[CaseItem]
    pagination: PaginationMetadata
    stats: CaseListStats


# ── Route Handlers ────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=CaseDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an investigation case manually",
)
async def create_case_endpoint(
    payload: CreateCaseRequest,
    service: CaseService = Depends(get_case_service),
    api_key: Optional[str] = Depends(get_api_key),
):
    try:
        case = service.create_case(
            transaction_id=payload.transaction_id,
            assessment_id=payload.assessment_id,
            final_decision=payload.final_decision,
            decision_reason=payload.decision_reason,
            decision_snapshot=payload.decision_snapshot,
            risk_snapshot=payload.risk_snapshot,
            rule_snapshot=payload.rule_snapshot,
            priority_override=payload.priority_override,
            assigned_to=payload.assigned_to,
            actor=payload.actor,
        )
        events = service.get_case_events(case["case_id"])
        return CaseDetailResponse(success=True, case=case, events=events)
    except CaseServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected failure creating case: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create case.")


@router.get(
    "",
    response_model=CaseListResponse,
    status_code=status.HTTP_200_OK,
    summary="List investigation cases with filtering and pagination",
)
async def list_cases_endpoint(
    status_filter: Optional[str] = Query(None, alias="status"),
    priority_filter: Optional[str] = Query(None, alias="priority"),
    assigned_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    created_from: Optional[str] = Query(None),
    created_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str = Query("created_at"),
    sort_direction: str = Query("desc"),
    service: CaseService = Depends(get_case_service),
    api_key: Optional[str] = Depends(get_api_key),
):
    result = service.list_cases(
        status=status_filter,
        priority=priority_filter,
        assigned_to=assigned_to,
        search=search,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
        sort=sort,
        sort_direction=sort_direction,
    )
    return CaseListResponse(
        success=True,
        items=[CaseItem(**item) for item in result["items"]],
        pagination=PaginationMetadata(**result["pagination"]),
        stats=CaseListStats(**result["stats"]),
    )


@router.get(
    "/{case_id}",
    response_model=CaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get case details, risk snapshots, and event timeline",
)
async def get_case_endpoint(
    case_id: str,
    service: CaseService = Depends(get_case_service),
    api_key: Optional[str] = Depends(get_api_key),
):
    try:
        case = service.get_case(case_id)
        events = service.get_case_events(case_id)
        return CaseDetailResponse(success=True, case=case, events=events)
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving case {case_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve case.")


@router.post(
    "/{case_id}/investigate",
    response_model=CaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Transition case to INVESTIGATING",
)
async def start_investigation_endpoint(
    case_id: str,
    payload: InvestigateCaseRequest,
    service: CaseService = Depends(get_case_service),
    api_key: Optional[str] = Depends(get_api_key),
):
    try:
        case = service.start_investigation(
            case_id=case_id,
            actor=payload.actor,
            expected_version=payload.expected_version,
            notes=payload.notes,
        )
        events = service.get_case_events(case_id)
        return CaseDetailResponse(success=True, case=case, events=events)
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ConcurrencyConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CaseServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{case_id}/assign",
    response_model=CaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign an investigation case to an analyst",
)
async def assign_case_endpoint(
    case_id: str,
    payload: AssignCaseRequest,
    service: CaseService = Depends(get_case_service),
    api_key: Optional[str] = Depends(get_api_key),
):
    try:
        case = service.assign_case(
            case_id=case_id,
            assigned_to=payload.assigned_to,
            actor=payload.actor,
            expected_version=payload.expected_version,
        )
        events = service.get_case_events(case_id)
        return CaseDetailResponse(success=True, case=case, events=events)
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConcurrencyConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CaseServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{case_id}/escalate",
    response_model=CaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Escalate an investigation case",
)
async def escalate_case_endpoint(
    case_id: str,
    payload: EscalateCaseRequest,
    service: CaseService = Depends(get_case_service),
    api_key: Optional[str] = Depends(get_api_key),
):
    try:
        case = service.escalate_case(
            case_id=case_id,
            escalation_reason=payload.escalation_reason,
            actor=payload.actor,
            expected_version=payload.expected_version,
        )
        events = service.get_case_events(case_id)
        return CaseDetailResponse(success=True, case=case, events=events)
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ConcurrencyConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CaseServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{case_id}/resolve",
    response_model=CaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve an investigation case",
)
async def resolve_case_endpoint(
    case_id: str,
    payload: ResolveCaseRequest,
    service: CaseService = Depends(get_case_service),
    api_key: Optional[str] = Depends(get_api_key),
):
    try:
        case = service.resolve_case(
            case_id=case_id,
            resolution_type=payload.resolution_type,
            resolution_notes=payload.resolution_notes,
            actor=payload.actor,
            expected_version=payload.expected_version,
        )
        events = service.get_case_events(case_id)
        return CaseDetailResponse(success=True, case=case, events=events)
    except CaseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ConcurrencyConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CaseServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
