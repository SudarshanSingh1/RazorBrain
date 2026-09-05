<div align="center">

<img src="https://razorpay.com/favicon.ico" width="56" />

<br />

# RazorBrain

<h3><strong>End-to-End MLOps Pipeline for Low-Latency Transaction Scoring and Continuous Model Monitoring</strong></h3>

<sub>Track 02 — AI Risk Manager &nbsp;·&nbsp; AI Buildathon 2026</sub>

<br />

![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI_0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React_TypeScript-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![AUC-ROC](https://img.shields.io/badge/AUC--ROC_0.9320-2B6BE6?style=for-the-badge)
![Tests](https://img.shields.io/badge/65_Tests_Passing-22863a?style=for-the-badge&logo=checkmarx&logoColor=white)

<br />

<table>
  <tr>
    <td align="center" width="340">
      <strong>Live Dashboard</strong><br />
      <sub>React UI — real-time fraud monitoring, scoring, and drift detection</sub><br /><br />
      <a href="https://razorbrains.onrender.com">
        <img src="https://img.shields.io/badge/razorbrains.onrender.com-61DAFB?style=for-the-badge&logoColor=black" alt="Live Dashboard" />
      </a>
    </td>
    <td align="center" width="340">
      <strong>Live API</strong><br />
      <sub>FastAPI inference server — /score, /batch, /audit, /health endpoints</sub><br /><br />
      <a href="https://razorbrain.onrender.com/">
        <img src="https://img.shields.io/badge/razorbrain.onrender.com-009688?style=for-the-badge&logoColor=white" alt="Live API" />
      </a>
    </td>
  </tr>
</table>

</div>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Evaluation Metrics](#evaluation-metrics)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Features](#features)
- [Model Training](#model-training)
- [Tech Stack](#tech-stack)
- [Environment Variables](#environment-variables)
- [Author](#author)

---

## Overview

RazorBrain is a production-grade fraud detection system that scores transactions in real time, generates explainable decisions with SHAP reason codes, and integrates directly with Razorpay's test-mode API. Every decision is logged to an immutable audit trail and can be exported as a chargeback evidence pack.

The system handles the full fraud detection lifecycle — from transaction ingestion and feature engineering, through ML inference and threshold routing, to merchant webhook delivery and drift monitoring.

| Signal | Value |
|---|---|
| **Fraud model** | XGBoost + isotonic calibration |
| **Decision paths** | ML inference or conservative cold-start rules |
| **Outputs** | Approve, step up with 2FA, or decline |
| **Controls** | Explainable reasons, immutable audit, drift monitoring |
| **Interfaces** | FastAPI, React, Razorpay test mode |

> **Important:** This project is configured for Razorpay **test mode**. Use test credentials in `.env` and never commit secrets.

---

## Architecture

The scoring path keeps low-history entities conservative while giving established entities the full calibrated model path.

### Scoring Pipeline

```mermaid
flowchart LR
  A[Checkout or webhook] --> B[FastAPI gateway]
  B --> C{Cold start?}
  C -->|Yes: under 10 txns| D[Conservative rule engine]
  C -->|No: warm entity| E[Feature engineering]
  E --> F[XGBoost model]
  F --> G[Isotonic calibration]
  D --> H[Risk probability]
  G --> H
  H --> I[Threshold engine]
  I -->|Low risk| J[APPROVE]
  I -->|Middle band| K[STEP_UP_2FA]
  I -->|High risk| L[DECLINE]
  J --> M[Append-only audit log]
  K --> M
  L --> M
  K --> N[Merchant webhook]
  L --> N
  M --> O[Evidence pack]
```

### Decision Routing

```mermaid
flowchart TD
  S[Transaction arrives] --> V{Schema and gateway checks pass?}
  V -->|No| X[Reject request]
  V -->|Yes| R{Entity history available?}
  R -->|Fewer than 10 txns| C[Cold-start rules]
  R -->|10 or more txns| M[Calibrated ML score]
  C --> P[p_fraud]
  M --> P
  P --> T{Compare with thresholds}
  T -->|p < approve| A[APPROVE]
  T -->|approve <= p < stepup| U[STEP_UP_2FA]
  T -->|p >= stepup| D[DECLINE]
  A --> L[Audit decision]
  U --> L
  D --> L
  U --> W[Fire merchant webhook]
  D --> W
```

---

## Evaluation Metrics

Evaluated on the IEEE-CIS Fraud Detection dataset — Validation transactions

<br />

<div align="center">
<img src="outputs/roc_curve.png" alt="ROC Curve" width="45%" />
<img src="outputs/precision_recall_curve.png" alt="PR Curve" width="45%" />
<img src="outputs/score_distribution.png" alt="Score Distribution" width="80%" />
<br /><sub>Precision–recall, ROC, and threshold distribution across HIGH_PRECISION and BALANCED modes</sub>
</div>

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
├── outputs/              # Generated ML reports and visuals
├── scripts/              # Automation and reporting scripts
├── compose.yaml          # Local multi-container orchestration
└── README.md             # Project documentation
```

---

## Quick Start

**Prerequisites:** Python 3.12, Node.js, Docker, Razorpay test account

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

## Features

### Core Capabilities

| Feature | Description |
|---|---|
| Real-time inference | Sub-50ms fraud scoring via XGBoost with calibration |
| Cold-start handling | Rule-based fallback for entities with fewer than 10 transaction history |
| Explainability | TreeSHAP reason codes for every decision |
| Razorpay integration | Direct test-mode order creation and webhook delivery |
| Immutable audit trail | Append-only SQLite log of all decisions |
| Drift monitoring | PSI and KL divergence detection between reference and current windows |

<br />

<div align="center">
<img src="outputs/shap_importance.png" alt="SHAP Feature Importance" width="80%" />
<br /><sub>Top features by mean absolute SHAP value — computed on the validation set</sub>
</div>

---

## Model Training

<div align="center">
<img src="outputs/eda.png" alt="EDA Snapshot" width="80%" />
<br /><sub>Exploratory data analysis — transaction amount distribution, class imbalance, and fraud rate by hour</sub>
</div>

---

## Tech Stack

| Component | Technology |
|---|---|
| API Server | FastAPI, Uvicorn, Pydantic |
| ML Model | XGBoost, scikit-learn |
| Explainability | SHAP (TreeSHAP) |
| Dashboard | React, TypeScript, Vite |
| Database | SQLite |
| Containerization | Docker, docker-compose |

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

GitHub: [SudarshanSingh1](https://github.com/SudarshanSingh1)

---

<div align="center">

Built for Razorpay AI Buildathon 2026

</div>
