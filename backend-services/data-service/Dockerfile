# Base image with better compatibility for scientific packages
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Create a non-root user and group with a dedicated home directory for caching
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup --home /home/appuser --shell /sbin/nologin appuser

# Set the HOME environment variable so libraries like yfinance know where to write cache files
ENV HOME=/home/appuser

#  Install curl development headers needed for curl_cffi
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Change ownership of the app and home directories to the appuser
RUN chown -R appuser:appgroup /app && \
    chown -R appuser:appgroup /home/appuser

# Switch to the non-root user
USER appuser

# Command to run the application
CMD ["python", "app.py"]