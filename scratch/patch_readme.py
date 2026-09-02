import re

with open("README.md", "r") as f:
    text = f.read()

# Replace the incorrect XGBoost/100K RPS claims
text = text.replace(
    "bound by the ML pipeline (SHAP explainer + XGBoost)",
    "bound by historical feature engineering (Pandas)"
)
text = text.replace(
    "Supporting 10K+ sustained RPS requires scaling out",
    "Scaling throughput requires scaling out"
)
text = text.replace(
    "scales linearly up to **~80 Requests Per Second (RPS)** per Python worker, achieving a P99 latency of ~620ms at a concurrency of 50.",
    "processes approximately ~90 Requests Per Second (RPS) per Python worker."
)

with open("README.md", "w") as f:
    f.write(text)
