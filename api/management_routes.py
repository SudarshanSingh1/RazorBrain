from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any, Optional
from pydantic import BaseModel

from api.management_service import ModelManagementService, PolicyManagementService, ManagementError
from api.security import get_admin_key

router = APIRouter(prefix="/management", tags=["Model & Policy Management"])

def get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "razorbrain_api.db")


# ── Models ──────────────────────────────────────────────────────────────

class ModelRegistrationRequest(BaseModel):
    model_name: str
    model_version: str
    artifact_path: str
    artifact_checksum: Optional[str] = None
    feature_contract_version: str
    model_type: Optional[str] = "xgboost"
    calibration_version: Optional[str] = None
    training_metadata: Optional[Dict[str, Any]] = None
    description: Optional[str] = None

@router.get("/models", response_model=Dict[str, Any])
async def list_models(request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = ModelManagementService(get_db_path(request))
    return {"success": True, "models": svc.list_models()}

@router.get("/models/active", response_model=Dict[str, Any])
async def get_active_model(request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = ModelManagementService(get_db_path(request))
    model = svc.get_active_model()
    if not model:
        raise HTTPException(status_code=404, detail="No active model found")
    return {"success": True, "model": model}

@router.get("/models/{model_id}", response_model=Dict[str, Any])
async def get_model(model_id: str, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = ModelManagementService(get_db_path(request))
    model = svc.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"success": True, "model": model}

@router.post("/models/register", response_model=Dict[str, Any])
async def register_model(payload: ModelRegistrationRequest, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = ModelManagementService(get_db_path(request))
    try:
        model = svc.register_model(payload.dict())
        return {"success": True, "model": model}
    except ManagementError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/models/{model_id}/activate", response_model=Dict[str, Any])
async def activate_model(model_id: str, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = ModelManagementService(get_db_path(request))
    try:
        model = svc.activate_model(model_id)
        return {"success": True, "model": model}
    except ManagementError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/models/{model_id}/rollback", response_model=Dict[str, Any])
async def rollback_model(model_id: str, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = ModelManagementService(get_db_path(request))
    try:
        model = svc.activate_model(model_id, is_rollback=True)
        return {"success": True, "model": model}
    except ManagementError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Policies ────────────────────────────────────────────────────────────

class PolicyCreationRequest(BaseModel):
    policy_name: str
    policy_version: str
    configuration: Dict[str, Any]
    configuration_checksum: Optional[str] = None
    description: Optional[str] = None

@router.get("/policies", response_model=Dict[str, Any])
async def list_policies(request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = PolicyManagementService(get_db_path(request))
    return {"success": True, "policies": svc.list_policies()}

@router.get("/policies/active", response_model=Dict[str, Any])
async def get_active_policy(request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = PolicyManagementService(get_db_path(request))
    policy = svc.get_active_policy()
    if not policy:
        raise HTTPException(status_code=404, detail="No active policy found")
    return {"success": True, "policy": policy}

@router.get("/policies/{policy_id}", response_model=Dict[str, Any])
async def get_policy(policy_id: str, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = PolicyManagementService(get_db_path(request))
    policy = svc.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"success": True, "policy": policy}

@router.post("/policies", response_model=Dict[str, Any])
async def create_policy(payload: PolicyCreationRequest, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = PolicyManagementService(get_db_path(request))
    try:
        policy = svc.create_policy(payload.dict())
        return {"success": True, "policy": policy}
    except ManagementError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/policies/{policy_id}/activate", response_model=Dict[str, Any])
async def activate_policy(policy_id: str, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = PolicyManagementService(get_db_path(request))
    try:
        policy = svc.activate_policy(policy_id)
        return {"success": True, "policy": policy}
    except ManagementError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/policies/{policy_id}/rollback", response_model=Dict[str, Any])
async def rollback_policy(policy_id: str, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = PolicyManagementService(get_db_path(request))
    try:
        policy = svc.activate_policy(policy_id, is_rollback=True)
        return {"success": True, "policy": policy}
    except ManagementError as e:
        raise HTTPException(status_code=400, detail=str(e))
