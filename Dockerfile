# Backend (FastAPI) container — connects to GCP Cloud SQL for PostgreSQL.
FROM python:3.11-slim

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY backend ./backend
COPY database ./database
COPY integrations ./integrations
COPY demo_data ./demo_data
COPY video/out/featured.mp4 ./video/out/featured.mp4

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
