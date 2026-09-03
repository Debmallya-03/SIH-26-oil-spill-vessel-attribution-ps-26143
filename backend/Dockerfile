FROM python:3.11-slim

# /workspace/backend mirrors the repo's backend/ dir so the app's own
# REPO_ROOT/BACKEND_ROOT path resolution (parents[3]/parents[4] from
# app/modules/**) lines up the same way it does when run outside Docker.
WORKDIR /workspace/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
