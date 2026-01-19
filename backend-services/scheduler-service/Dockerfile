# Base image with better compatibility for scientific packages
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Create a non-root user for security
RUN addgroup --system appgroup && adduser --system appuser --ingroup appgroup

# Install curl for debugging purposes
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 1) Copy and install service deps (from service subfolder)
COPY scheduler-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 2) Copy shared contracts package
COPY shared ./shared

# 3) Copy the service code into /app (so app.py stays at /app/app.py like today)
COPY scheduler-service/ ./

# Change ownership of the app directory
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Command to run the application: one image, three modes (api | worker | beat)
# Use gunicorn+gevent for API mode to support concurrent SSE streams.
CMD ["sh", "-c", "if [ \"$SCHEDULER_MODE\" = \"worker\" ]; then celery -A celery_app.celery worker --loglevel=info; elif [ \"$SCHEDULER_MODE\" = \"beat\" ]; then celery -A celery_app.celery beat --loglevel=info; else gunicorn -k gevent --workers 1 --bind 0.0.0.0:$PORT app:app; fi"]