"""
Monitoring & Alerting API Routes for RazorBrain.

Provides endpoints for listing, acknowledging, and resolving alerts,
running monitoring evaluations, and fetching system health summaries.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.alert_service import (
    AlertNotFoundError,
    AlertService,
    InvalidAlertTransitionError,
    VALID_SEVERITIES,
    VALID_STATUSES,
    VALID_CATEGORIES,
)
from api.monitoring_service import MonitoringService
from api.security import get_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Monitoring & Alerts"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_alert_service(request: Request) -> AlertService:
    state = getattr(request.app.state, "razor_state", None)
    db_path = getattr(state, "db_path", "razorbrain_api.db") if state else "razorbrain_api.db"
    return AlertService(db_path=db_path)


def _get_monitoring_service(request: Request) -> MonitoringService:
    state = getattr(request.app.state, "razor_state", None)
    db_path = getattr(state, "db_path", "razorbrain_api.db") if state else "razorbrain_api.db"
    return MonitoringService(db_path=db_path)


# ── Request Schemas ───────────────────────────────────────────────────────────

class AcknowledgeRequest(BaseModel):
    acknowledged_by: str = Field("operator", min_length=1, max_length=100)


# ── Alert Endpoints ───────────────────────────────────────────────────────────

@router.get("/alerts")
def list_alerts(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status (OPEN, ACKNOWLEDGED, RESOLVED)"),
    severity: Optional[str] = Query(None, description="Filter by severity (INFO, WARNING, CRITICAL)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _api_key: str = Depends(get_api_key),
):
    """List alerts with optional filtering."""
    if status and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    if severity and severity not in VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    svc = _get_alert_service(request)
    return svc.list_alerts(
        status=status, severity=severity, category=category,
        source=source, since=since, until=until,
        limit=limit, offset=offset,
    )


@router.get("/alerts/{alert_id}")
def get_alert(request: Request, alert_id: str, _api_key: str = Depends(get_api_key)):
    """Get a single alert by ID."""
    svc = _get_alert_service(request)
    try:
        return {"alert": svc.get_alert(alert_id)}
    except AlertNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    request: Request, alert_id: str,
    body: Optional[AcknowledgeRequest] = None,
    _api_key: str = Depends(get_api_key),
):
    """Acknowledge an alert."""
    svc = _get_alert_service(request)
    ack_by = body.acknowledged_by if body else "operator"
    try:
        alert = svc.acknowledge_alert(alert_id, acknowledged_by=ack_by)
        return {"success": True, "alert": alert}
    except AlertNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except InvalidAlertTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(request: Request, alert_id: str, _api_key: str = Depends(get_api_key)):
    """Resolve an alert."""
    svc = _get_alert_service(request)
    try:
        alert = svc.resolve_alert(alert_id)
        return {"success": True, "alert": alert}
    except AlertNotFoundError:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    except InvalidAlertTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── Monitoring Endpoints ──────────────────────────────────────────────────────

@router.get("/monitoring/summary")
def get_monitoring_summary(request: Request, _api_key: str = Depends(get_api_key)):
    """Get an aggregated monitoring health summary."""
    state = getattr(request.app.state, "razor_state", None)
    db_path = getattr(state, "db_path", "razorbrain_api.db") if state else "razorbrain_api.db"

    monitoring = MonitoringService(db_path=db_path)
    alert_svc = AlertService(db_path=db_path)
    metrics = getattr(state, "metrics_collector", None)

    return monitoring.get_monitoring_summary(
        alert_service=alert_svc,
        metrics_collector=metrics,
    )


@router.post("/monitoring/evaluate")
def run_monitoring_evaluation(request: Request, _api_key: str = Depends(get_api_key)):
    """
    Trigger a monitoring evaluation cycle. Evaluates all conditions
    and creates/updates alerts as needed.
    """
    state = getattr(request.app.state, "razor_state", None)
    db_path = getattr(state, "db_path", "razorbrain_api.db") if state else "razorbrain_api.db"

    monitoring = MonitoringService(db_path=db_path)
    alert_svc = AlertService(db_path=db_path)
    metrics = getattr(state, "metrics_collector", None)

    conditions = monitoring.evaluate_all(metrics_collector=metrics)
    created_alerts = []
    errors = []

    for condition in conditions:
        try:
            alert = alert_svc.create_or_update_alert(**condition)
            created_alerts.append(alert)
        except Exception as e:
            errors.append({"condition": condition.get("alert_type"), "error": str(e)})
            logger.error(f"Alert creation failed for {condition.get('alert_type')}: {e}")

    return {
        "success": True,
        "evaluated_conditions": len(conditions),
        "alerts_created_or_updated": len(created_alerts),
        "alerts": created_alerts,
        "errors": errors,
    }


@router.get("/monitoring/thresholds")
def get_thresholds(request: Request, _api_key: str = Depends(get_api_key)):
    """Return current monitoring threshold configuration."""
    monitoring = _get_monitoring_service(request)
    return {"thresholds": monitoring.thresholds}
