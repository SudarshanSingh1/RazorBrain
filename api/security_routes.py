from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any, Optional
from pydantic import BaseModel

from api.security_service import SecurityService, SecurityError
from api.security import get_admin_key

router = APIRouter(prefix="/security", tags=["Security & API Keys"])

def get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "razorbrain_api.db")

class CreateKeyRequest(BaseModel):
    name: str
    role: str = "SCORER"
    expires_at: Optional[str] = None

class RotateKeyRequest(BaseModel):
    new_name: str
    role: str = "SCORER"
    expires_at: Optional[str] = None

@router.get("/keys", response_model=Dict[str, Any])
async def list_keys(request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = SecurityService(get_db_path(request))
    return {"success": True, "keys": svc.list_api_keys()}

@router.post("/keys", response_model=Dict[str, Any])
async def create_key(payload: CreateKeyRequest, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = SecurityService(get_db_path(request))
    if payload.role not in ["ADMIN", "OPERATOR", "SCORER"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    try:
        meta, secret = svc.create_api_key(payload.name, payload.role, payload.expires_at)
        return {"success": True, "key": meta, "raw_secret": secret}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/keys/{key_id}/revoke", response_model=Dict[str, Any])
async def revoke_key(key_id: str, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = SecurityService(get_db_path(request))
    try:
        meta = svc.revoke_api_key(key_id)
        return {"success": True, "key": meta}
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/keys/{key_id}/rotate", response_model=Dict[str, Any])
async def rotate_key(key_id: str, payload: RotateKeyRequest, request: Request, admin_meta: dict = Depends(get_admin_key)):
    svc = SecurityService(get_db_path(request))
    try:
        meta, secret = svc.rotate_api_key(key_id, payload.new_name, payload.role, payload.expires_at)
        return {"success": True, "new_key": meta, "new_raw_secret": secret}
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
