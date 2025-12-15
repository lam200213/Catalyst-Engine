# Base image with better compatibility for scientific packages
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Create a non-root user for security
RUN addgroup --system appgroup && adduser --system appuser --ingroup appgroup

# 1) Copy and install service deps (from service subfolder)
COPY analysis-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 2) Copy shared contracts package
COPY shared ./shared

# 3) Copy the service code into /app (so app.py stays at /app/app.py like today)
COPY analysis-service/ ./

# Change ownership of the app directory
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Command to run the application
CMD ["python", "app.py"]