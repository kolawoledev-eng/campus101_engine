# grade99 API — build from this directory:
#   cd engine && docker build -t grade99-api .
#
# Run locally (pass secrets via env; never copy .env into the image):
#   docker run -p 8000:8000 \
#     -e ANTHROPIC_API_KEY=... \
#     -e ANTHROPIC_MODEL=claude-sonnet-4-6 \
#     -e SUPABASE_URL=... \
#     -e SUPABASE_SERVICE_KEY=... \
#     grade99-api
#
# Hosted deploy: point your host (Railway / Fly.io / Cloud Run / etc.) at this Dockerfile
# and set the same env vars in the dashboard. Use the HTTPS URL in Flutter:
#   flutter run --dart-define=API_BASE=https://your-service.example.com

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1'

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
