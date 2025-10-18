# backend-services/monitoring-service/Dockerfile
# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Create a non-root user and group for security
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup --home /home/appuser --shell /sbin/nologin appuser

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the content of the local src directory to the working directory
COPY . .

# Make port 3006 available to the world outside this container
EXPOSE 3006

# Change ownership of the app and home directories to the appuser
RUN chown -R appuser:appgroup /app && \
    chown -R appuser:appgroup /home/appuser

# Switch to the non-root user
USER appuser

# Command to run the application
CMD ["python", "app.py"]