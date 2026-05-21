# Build context = widget/  (backend + dist birlikte kopyalanır)
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 DIST_DIR=/app/dist

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY dist/ /app/dist/
COPY console/ /app/console/

EXPOSE 8090
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8090"]
