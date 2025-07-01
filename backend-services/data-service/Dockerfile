# Use this Dockerfile for api-gateway, data-service, screening-service, and analysis-service
# It uses a multi-stage build for security and smaller image size.

# Stage 1: The Builder
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Stage 2: The Final Production Image
FROM python:3.11-alpine
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app .
RUN chown -R appuser:appgroup /app
USER appuser
CMD ["python", "app.py"]
