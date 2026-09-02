# RazorBrain

AI-powered transaction risk management for defensive fraud detection.

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=flat-square&logo=react&logoColor=61DAFB)
![XGBoost](https://img.shields.io/badge/XGBoost-191A1B?style=flat-square&logo=xgboost&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)

RazorBrain analyzes transaction-level signals to estimate fraud risk, combines machine-learning with deterministic rules, produces explainable risk decisions, and surfaces evidence through an operational interface to protect against fraudulent activity.

## Key Capabilities

| Capability | Description |
|------------|-------------|
| Risk Scoring | Estimate transaction-level fraud risk |
| Explainability | Surface the factors behind a risk assessment |
| Rule Analysis | Apply deterministic defensive signals |
| Decisioning | Route transactions to Allow, Review, or Block |
| Evaluation | Measure performance on held-out data |
| Auditability | Preserve important decision evidence |

## System Overview

RazorBrain is designed as a multi-layered risk pipeline. Incoming transactions pass through validation and feature engineering before being evaluated concurrently by machine-learning models, defensive rules, and anomaly detection. These signals are synthesized into a final risk decision, which is then passed to an explanation layer and persisted for audit and evaluation purposes. 

```text
                    ┌──────────────────┐
                    │    Transaction   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    Validation    │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Feature Pipeline │
                    └────────┬─────────┘
                             │
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
        ┌─────────┐     ┌─────────┐    ┌──────────┐
        │   ML    │     │  Rules  │    │ Anomaly  │
        └────┬────┘     └────┬────┘    └─────┬────┘
             └───────────────┼───────────────┘
                             ▼
                    ┌──────────────────┐
                    │  Risk Decision   │
                    └────────┬─────────┘
                             │
                     ┌───────┴────────┐
                     ▼                ▼
                Explanation       Audit /
                                  Evaluation
```
*(Note: This is a conceptual architecture representing the intended system design.)*

## Risk Decisioning

The decision model transforms raw data through the following flow:
Risk signals → Risk score → Decision

Decisions are categorized into **Allow**, **Review**, or **Block**. A critical safety rule governs this process: a single weak signal (such as a new device, a new location, or an unusually high amount) must not independently force a Block decision. Multiple independent signals are required to support high-risk automated actions.

## Explainability

RazorBrain explicitly separates Risk Determination from Risk Explanation. 

The ML and risk engines determine the final risk assessment. The explanation layer (using tools like SHAP) surfaces the influential features and evidence that contributed to that assessment. The explanation model is strictly constrained:
- It must never change the risk score.
- It must never change the decision.
- It must never invent transaction facts.
- It must explicitly handle unavailable information.

## Evaluation

Model development relies on strictly separated data splits: training data, validation data, and held-out test data. The test set remains completely untouched during model development to ensure honest assessment. Performance is measured using robust metrics including Precision, Recall, F1, PR-AUC, Confusion Matrix, and False-positive cost. 

Evaluation results will be reported once the model pipeline is complete.

## Project Structure

```text
RazorBrain/
├── backend/
├── frontend/
├── data/
├── model/
├── evaluation/
├── tests/
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

| Directory | Responsibility |
|-----------|----------------|
| backend | API and application services |
| frontend | Web interface |
| data | Dataset and data resources |
| model | ML components |
| evaluation | Model evaluation |
| tests | Automated tests |

## Technology

| Layer | Technology |
|------|------------|
| Backend | Python, FastAPI |
| ML | XGBoost, scikit-learn, SHAP |
| Data | Pandas, NumPy |
| Frontend | React, TypeScript |
| Storage | PostgreSQL |
| Infrastructure | Docker |

## Engineering Principles

- Reuse existing code before creating new code.
- Prefer incremental improvements over unnecessary rewrites.
- Keep modules focused and responsibilities clear.
- Avoid duplicate logic and unnecessary dependencies.
- Use standard professional naming.
- Keep secrets outside source control.
- Validate inputs and handle missing data safely.
- Separate risk determination from explanation generation.
- Test important behavior before expanding the system.

## Safety

- Defensive fraud detection only.
- Synthetic data for development and demonstration.
- No offensive or abuse-enabling functionality.
- Secrets remain outside source control.
- The explanation layer cannot make risk decisions.
- Missing or unreliable data should reduce confidence rather than crash the system.

## Getting Started

The repository is currently establishing its foundation. Setup and execution instructions will be provided as application components are implemented.

## Status

RazorBrain is under active development. Repository foundation and architecture are being established before implementation of the risk pipeline.
