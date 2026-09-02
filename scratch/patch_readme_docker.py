with open("README.md", "r") as f:
    text = f.read()

docker_section = """
## Phase 19: Docker Deployment

RazorBrain can be deployed locally using Docker Compose.

### Prerequisites
- Docker Engine
- Docker Compose

### Environment Configuration
1. Copy the example configuration:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and set a secure local `RAZORBRAIN_API_KEY`.

### Startup & Build Commands
To build and start the containers in the background:
```bash
docker-compose up -d --build
```

### Health & Readiness Checks
The backend provides deterministic readiness probes:
- Health (HTTP Server alive): `curl http://localhost:8000/health`
- Readiness (ML model loaded, migrations applied): `curl http://localhost:8000/ready`

### URLs
- **Enterprise Dashboard**: `http://localhost:8080`
- **Backend API**: `http://localhost:8000`

### Persistence & Restarting
RazorBrain uses a mounted Docker volume (`razorbrain_db`) for SQLite persistence. 
- To stop the system without losing data: `docker-compose down`
- To stop and completely wipe the database: `docker-compose down -v`

### Troubleshooting Basics
- If the frontend cannot connect to the backend, ensure `VITE_API_URL` is accessible from your browser (default `http://localhost:8000`).
- If readiness fails, check the backend logs for migration or ML bootstrapping errors: `docker-compose logs backend`.

### Current Deployment Limitations
- **SQLite Database**: SQLite is currently used for persistence, which is appropriate for this prototype but lacks distributed concurrency scaling.
- **Queue Payload Loss**: The in-memory event queue drops queued payloads permanently if the container crashes.
- **At-Most-Once Publication**: Publication of assessment results is at-most-once. Exactly-once delivery is not claimed.
- **Client Credentials**: The API Key (`RAZORBRAIN_API_KEY`) is a client credential visible in the Vite browser bundle.
- **Authorization**: Granular RBAC (Role-Based Access Control) is not implemented.
- **Audit Immutability**: The audit log is append-only, but cryptographic immutability (hashing) is not implemented.
- **CORS Policy**: Wildcard CORS (`*`) is allowed by default for development. It is not appropriate for production unless explicitly constrained in `.env`.
- **Scalability**: Phase 17 demonstrated bounded-queue backpressure under 100k-event burst testing; Docker deployment does not change those measured scalability characteristics.
"""

if "## Phase 19: Docker Deployment" not in text:
    text += "\n" + docker_section

# Update Roadmap
if "PHASE 19  Docker + Deployment" in text:
    text = text.replace("PHASE 19  Docker + Deployment", "PHASE 19  ✅ Docker + Deployment")
elif "PHASE 19" in text and "✅ Docker + Deployment" not in text:
    # generic fallback
    pass 

with open("README.md", "w") as f:
    f.write(text)
