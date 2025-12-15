# backend-services/monitoring-service/Dockerfile
# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Create a non-root user and group for security
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup --home /home/appuser --shell /sbin/nologin appuser

# 1) Copy and install service deps (from service subfolder)
COPY monitoring-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 2) Copy shared contracts package
COPY shared ./shared

# 3) Copy the service code into /app (so app.py stays at /app/app.py like today)
COPY monitoring-service/ ./

# Make port 3006 available to the world outside this container
EXPOSE 3006

# Change ownership of the app and home directories to the appuser
RUN chown -R appuser:appgroup /app && \
    chown -R appuser:appgroup /home/appuser

# Switch to the non-root user
USER appuser

# Command to run the application
CMD ["python", "app.py"]