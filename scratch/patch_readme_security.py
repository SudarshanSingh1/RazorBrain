with open("README.md", "r") as f:
    text = f.read()

security_section = """
## Phase 18: Security & Recovery Boundaries
- **Authentication**: Minimal API Key authentication (`RAZORBRAIN_API_KEY`) is supported for protected endpoints.
- **Authorization**: Role-based access control (RBAC) is NOT implemented.
- **Secret Handling**: All secrets remain server-side. No API keys or tokens are stored in the frontend source code.
- **CORS Policy**: Currently configured as wildcard (`*`) for development simplicity.
- **Input Limits**: Strict Pydantic string and numeric bounds prevent memory exhaustion and overflow.
- **Error Handling**: Global exception handlers prevent Python traceback leakage.
- **Event Recovery**: Stale `PROCESSING` events caused by process crashes are cleanly transitioned to `PROCESSING_FAILED` upon restart.
- **Restart Limitation**: **Events in the in-memory queue are lost if the process terminates.** The persistent ledger does not recreate queued payloads.
- **Audit Limitations**: The database API is strictly append-only, but cryptographic immutability of the audit log is not implemented.
"""

if "## Phase 18: Security & Recovery Boundaries" not in text:
    text += "\n" + security_section

with open("README.md", "w") as f:
    f.write(text)
