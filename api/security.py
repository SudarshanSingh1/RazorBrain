import os
from typing import List
from fastapi import Security, HTTPException, status, Request
from fastapi.security import APIKeyHeader
from api.security_service import SecurityService, AuthenticationError

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_db_path(request: Request) -> str:
    return getattr(request.app.state, "razor_state", None).db_path if getattr(request.app.state, "razor_state", None) else "razorbrain_api.db"

def get_api_key_metadata(request: Request, api_key: str = Security(api_key_header)):
    if os.environ.get("RAZORBRAIN_TEST_MODE") == "1":
        request.state.client_identity = "test_client"
        return {"id": "ak_test", "role": "ADMIN"}
        
    if not api_key:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key"
        )
        
    fallback_key = os.environ.get("RAZORBRAIN_API_KEY")
    svc = SecurityService(get_db_path(request))
    
    try:
        meta = svc.authenticate_key(api_key, fallback_env_key=fallback_key)
        # Store identity for rate limiting or logging
        request.state.client_identity = meta["id"]
        return meta
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

def get_api_key(request: Request, api_key: str = Security(api_key_header)):
    """Legacy dependency returning just the string if valid."""
    # We still authenticate to ensure it's valid
    get_api_key_metadata(request, api_key)
    return api_key

def require_role(allowed_roles: List[str]):
    def role_checker(request: Request, api_key: str = Security(api_key_header)):
        meta = get_api_key_metadata(request, api_key)
        if meta["role"] not in allowed_roles and "ADMIN" not in meta["role"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation."
            )
        return meta
    return role_checker

def get_admin_key(request: Request, api_key: str = Security(api_key_header)):
    checker = require_role(["ADMIN"])
    return checker(request, api_key)

from api.rate_limit_service import rate_limiter, RateLimitExceeded

def rate_limit(endpoint_name: str, capacity: int = 100, refill_rate: float = 10.0):
    def _rate_limit_dep(request: Request):
        identity = getattr(request.state, "client_identity", request.client.host if request.client else "unknown")
        try:
            rate_limiter.check_rate_limit(identity, endpoint_name, capacity, refill_rate)
        except RateLimitExceeded as e:
            getattr(request.state, "request_id", "unknown")
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please retry later.",
                headers={"Retry-After": str(e.retry_after)}
            )
    return _rate_limit_dep
