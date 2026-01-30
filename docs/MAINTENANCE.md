# **Dependency Management and Maintenance Protocol**

This document outlines the procedure for managing and updating package dependencies for all backend services to ensure stability and prevent breaking changes from upstream libraries.

## **1\. Automated Dependency Monitoring**

This project uses GitHub's Dependabot to automatically check for outdated dependencies.

* **Frequency**: Dependabot is configured to scan for new package versions weekly.

* **Target**: Initially, it monitors the pip package ecosystem for the data-service.

* **Action**: When a new version is available, Dependabot will automatically create a pull request (PR) with the proposed changes to the requirements.txt file.

## **2\. Manual Verification Protocol**

All Dependabot PRs, or any manual dependency update, must be verified using the following steps before being merged.

### **Step 2.1: Pull the Changes**

Pull the feature branch containing the requirements.txt update to your local machine to begin the verification process.

### **Step 2.2: Rebuild the Service's Docker Image**

You must rebuild the Docker image for the specific service to install the new package version. Use the

docker-compose build command5.

Bash

\# Example for rebuilding the data-service  
docker-compose build data-service

### **Step 2.3: Run Verification Tests**

Execute the service's test suite to confirm that the updated package has not introduced any breaking changes or regressions6.

Bash

\# First, ensure the application stack is running  
docker-compose up \-d

\# Execute tests inside the specific service container  
docker-compose exec \<service-name\> pytest  
\# Example: docker-compose exec data-service pytest

### **Step 2.4: Merge the Pull Request**

If all tests pass, the dependency update is considered safe, and the pull request can be merged. If tests fail, document the errors in the pull request and close it. Do not merge failing updates.

## 3. CI/CD & Testing Protocol

The project uses **GitHub Actions** for Continuous Integration. The workflow is split into two distinct phases to optimize speed and reliability:

1.  **Matrix Unit Tests**: Runs in parallel for every service. These run in **isolation** (no database, no sidecars) to ensure fast feedback.
2.  **Integration Tests**: Runs sequentially after unit tests pass. These boot the full backend stack (databases, message brokers) to test service interoperability.

### 3.1. Running Unit Tests Locally (CI Mirror)

To replicate the CI's unit test environment locally—which prevents "it works on my machine" issues caused by local env vars or running services—use the following command pattern. This forces the test to run inside a fresh container without starting dependencies.

```bash
# Template
SERVICE=<service-name>
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps \
  -e PYTHONPATH=/app \
  --entrypoint python "$SERVICE" -m pytest -q tests/unit

# Example: Run unit tests for monitoring-service
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps \
  -e PYTHONPATH=/app \
  --entrypoint python monitoring-service -m pytest -q tests/unit
```

**Key Flags Explained:**
* `--no-deps`: Prevents Docker from starting MongoDB/Redis. Tests must mock these interactions.
* `--rm`: Cleans up the container immediately after the test finishes.
* `-e PYTHONPATH=/app`: Ensures imports work correctly relative to the container root, matching the production structure.

### 3.2. Running Integration Tests Locally

Integration tests require the infrastructure to be running.

```bash
# 1. Start the backend infrastructure
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d mongodb redis data-service

# 2. Run the integration suite
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
  -e PYTHONPATH=/app \
  --entrypoint python monitoring-service -m pytest tests/integration
```

### 3.3. Simulating GitHub Actions Locally

You can use [nektos/act](https://github.com/nektos/act) to simulate the full GitHub Actions workflow on your machine.

**Prerequisites:**
* Ensure local ports `27017` (Mongo) and `6379` (Redis) are free, or stop your local services, as `act` will attempt to bind them.

**Command:**
```bash
# Run the specific Pull Request workflow
act pull_request -W .github/workflows/ci.yml \
  -P ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest \
  --container-architecture linux/amd64
```