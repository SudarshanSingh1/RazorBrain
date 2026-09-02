with open("api/app.py", "r") as f:
    text = f.read()

# Add exception handler for Exception to prevent traceback leak
handler_code = """
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
"""

if "global_exception_handler" not in text:
    text += handler_code

# Add Security Headers Middleware
headers_code = """
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response

app.add_middleware(SecurityHeadersMiddleware)
"""

if "SecurityHeadersMiddleware" not in text:
    text = text.replace("app.add_middleware(RequestIDMiddleware)", headers_code + "\napp.add_middleware(RequestIDMiddleware)")

with open("api/app.py", "w") as f:
    f.write(text)
