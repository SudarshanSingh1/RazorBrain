FROM python:3.11-slim

# Avoid writing .pyc files; output logs without buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (build-essential needed for some C extensions if no wheel available)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml
COPY pyproject.toml .

# Install dependencies using pip (we'll copy the rest later to use docker cache)
# Installing razor_brain in editable mode or just installing its dependencies
RUN pip install --no-cache-dir .

# Copy application source
COPY api/ api/
COPY database/ database/
COPY model/ model/
COPY data/ data/
COPY tests/ tests/

# We'll need a directory for SQLite persistence
RUN mkdir -p /app/data_store && chown -R 1000:1000 /app/data_store

# Create a non-root user
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Start command
CMD ["sh", "-c", "uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
