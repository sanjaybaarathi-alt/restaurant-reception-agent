FROM node:24-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm test
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LANGGRAPH_STRICT_MSGPACK=true
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY --from=frontend-build /frontend/dist ./frontend/dist
COPY alembic.ini ./
COPY main.py ./
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 appuser
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data
USER appuser

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8080"]
