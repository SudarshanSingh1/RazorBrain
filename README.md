# RazorBrain

RazorBrain is a production-oriented fraud risk assessment platform combining machine learning, deterministic risk rules, hybrid decisioning, investigation workflows, explainability, monitoring, and operational controls.

---

## Features

- ML fraud scoring
- Calibrated risk probability
- Decision engine
- Deterministic risk rules
- Hybrid risk fusion
- Investigation management
- Step-up verification
- Transaction explainability
- Monitoring and alerts
- Model and policy registry
- API security and idempotency
- Docker deployment

---

## Architecture

```text
Transaction
    ↓
Feature Validation
    ↓
ML Fraud Model
    ↓
Calibrated Probability
    ↓
Explainability
    ↓
Rule Engine
    ↓
Risk Fusion
    ↓
Decision Engine
    ↓
Investigation / Step-Up / Final Action
    ↓
Audit & Monitoring
```

---

## Tech Stack

**Backend:**
- Python
- FastAPI
- XGBoost
- SQLite

**Frontend:**
- React
- TypeScript
- Vite

**Deployment:**
- Docker
- Render

---

## Run Locally

git clone https://github.com/your-org/RazorBrain.git
cd RazorBrain
docker compose up --build

---

## Environment Variables

### Backend
- `RAZORBRAIN_API_KEY`: The API key required to access the backend API endpoints (e.g., `X-API-Key` header).
- `RAZORBRAIN_DB_PATH`: Path to the SQLite database (default: `razorbrain_api.db`).
- `RAZORBRAIN_CORS_ORIGINS`: Comma-separated list of allowed CORS origins.

### Frontend
- `VITE_API_URL`: The URL where the RazorBrain backend API is deployed (e.g., `http://localhost:8000` for development or `https://api.razorbrain.onrender.com` for production).
- `VITE_API_KEY`: Frontend API key matching the backend's `RAZORBRAIN_API_KEY`.

---

## Deployment

- **Backend** deploys as a separate web service via Docker.
- **Frontend** deploys as a separate static site (e.g., on Render, Vercel, Netlify).
- The frontend connects to the backend through the `VITE_API_URL` environment variable.
- The UI features a global connection state manager that displays backend connection status and offers graceful exponential backoff retries when the API is temporarily unavailable.

---

## Project Structure

```
RazorBrain/
├── api/                  # FastAPI backend application
├── model/                # ML pipeline, inference, and explainability
├── database/             # SQLite database migrations and access
├── frontend/             # React/Vite frontend UI
├── tests/                # Automated test suite
├── data/                 # Model artifacts (.joblib)
├── docker-compose.yml    # Local multi-container orchestration
├── render.yaml           # Render deployment blueprint
└── README.md             # Project documentation
```
