<div align="center">

<img src="https://razorpay.com/favicon.ico" width="56" />

<br />

# RazorBrain

<h3><strong>End-to-End MLOps & Fraud Risk Assessment Platform for Razorpay</strong></h3>

<sub>Track 02 — AI Risk Manager &nbsp;·&nbsp; AI Buildathon 2026</sub>

<br />

![Python](https://img.shields.io/badge/Python_3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React_TypeScript-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![XGBoost](https://img.shields.io/badge/XGBoost_Model-2B6BE6?style=for-the-badge)

<br />

<table>
  <tr>
    <td align="center" width="340">
      <strong>Live Dashboard</strong><br />
      <sub>React UI — Real-time fraud monitoring, transaction review & investigations</sub><br /><br />
      <a href="https://razorbrain-frontend.onrender.com">
        <img src="https://img.shields.io/badge/razorbrain--frontend.onrender.com-61DAFB?style=for-the-badge&logoColor=black" alt="Live Dashboard" />
      </a>
    </td>
    <td align="center" width="340">
      <strong>Live API</strong><br />
      <sub>FastAPI inference server — Scoring, risk rules, and hybrid decisioning</sub><br /><br />
      <a href="https://razorbrain.onrender.com/">
        <img src="https://img.shields.io/badge/razorbrain.onrender.com-009688?style=for-the-badge&logoColor=white" alt="Live API" />
      </a>
    </td>
  </tr>
</table>

</div>

---

## Overview

RazorBrain is a production-oriented fraud risk assessment platform combining machine learning, deterministic risk rules, hybrid decisioning, investigation workflows, and explainability.

---

## Architecture

```mermaid
flowchart LR
  A[Transaction] --> B[Feature Validation]
  B --> C[XGBoost ML Model]
  C --> D[Calibrated Probability]
  D --> E[Explainability]
  B --> F[Deterministic Rule Engine]
  D --> G[Hybrid Risk Fusion]
  F --> G
  G --> H[Decision Engine]
  H --> I[Investigation / Step-Up / Action]
  I --> J[Audit & Monitoring]
```

---

## Project Structure

```text
RazorBrain/
├── api/                  # FastAPI backend application
├── model/                # ML pipeline, inference, and explainability
├── database/             # SQLite database migrations and access
├── frontend/             # React/Vite frontend UI
├── tests/                # Automated test suite
├── data/                 # Model artifacts (.joblib)
├── docker-compose.yml    # Local multi-container orchestration
└── README.md             # Project documentation
```

---

## Quick Start

```bash
# Clone repository
git clone https://github.com/SudarshanSingh1/RazorBrain.git
cd RazorBrain

# Start with Docker
docker compose up --build
```

| Access Point | URL |
|---|---|
| Dashboard | http://localhost:5173 |
| API | http://localhost:8000 |
| Docs | http://localhost:8000/docs |

---

## Environment Variables

| Variable | Description |
|---|---|
| `RAZORBRAIN_API_KEY` | Backend API key for secure access |
| `RAZORBRAIN_CORS_ORIGINS` | Allowed CORS origins (e.g. `*`) |
| `VITE_API_URL` | Frontend connection to backend API |
| `VITE_API_KEY` | Frontend key matching backend API key |

---

## Author

**Sudarshan Kushwaha**

AI Buildathon 2026 — Track 02: AI Risk Manager
