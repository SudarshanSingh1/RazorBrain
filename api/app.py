import logging
import uuid
import os

def _load_env_file(filepath: str = ".env"):
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", ""):
        return
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            pass

_load_env_file()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.lifespan import lifespan, app_state
from api.routes import router
from api.razorpay_routes import router as razorpay_router
from api.razorpay_routes import webhook_router
from api.dashboard_routes import router as dashboard_router
from api.predict_routes import router as predict_router
from api.case_routes import router as case_router
from api.schemas import ErrorResponse, ErrorDetail

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="RazorBrain API",
    description="Stateless HTTP API for RazorBrain Risk Assessments.",
    version="0.13.0",
    lifespan=lifespan
)

app.state.razor_state = app_state

app.include_router(router)
app.include_router(razorpay_router)
app.include_router(webhook_router)
app.include_router(dashboard_router)
app.include_router(predict_router)
app.include_router(case_router)

cors_origins_env = os.environ.get("RAZORBRAIN_CORS_ORIGINS", "*")
allow_origins = [origin.strip() for origin in cors_origins_env.split(",")] if cors_origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID")
        if not req_id:
            req_id = str(uuid.uuid4())
        request.state.request_id = req_id
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(RequestIDMiddleware)

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    err = ErrorResponse(
        error=ErrorDetail(
            code=f"HTTP_{exc.status_code}",
            message=exc.detail,
            request_id=req_id
        )
    )
    return JSONResponse(status_code=exc.status_code, content=err.model_dump())

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    err = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message=str(exc.errors()),
            request_id=req_id
        )
    )
    return JSONResponse(status_code=400, content=err.model_dump())

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.error(f"[{req_id}] Unhandled server error: {str(exc)}")
    err = ErrorResponse(
        error=ErrorDetail(
            code="HTTP_500",
            message="Internal Server Error.",
            request_id=req_id
        )
    )
    return JSONResponse(status_code=500, content=err.model_dump())
