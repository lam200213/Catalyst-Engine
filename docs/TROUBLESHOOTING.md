# Common Errors & Troubleshooting

### **Container Name Conflict**

**Error:** You might see an error like this when running docker-compose up:

Error response from daemon: Conflict. The container name "/some-service" is already in use by container...

**Cause:** This happens when a previous Docker session was stopped improperly (e.g., by closing the terminal) without using docker-compose down. This leaves behind *stopped* containers that still occupy their names, preventing new ones from starting. This will also make the application unreachable in your browser, causing an ERR_CONNECTION_REFUSED error.

**Solution:**

1. **Stop and Remove the Application Stack:** The standard command to fix this is docker-compose down. This gracefully stops and removes all containers and networks for the project.  
   ```Bash  
   docker-compose down
   ```

2. **Forceful Cleanup (If Needed):** For stubborn cases or to perform a general cleanup, you can use docker container prune to remove all stopped containers on your system.  
   ```Bash  
   docker container prune
   ```

3. **Relaunch:** You can now start the application again.  
   ```Bash  
   docker-compose up --build -d

---

# Developer Diagnostic Tools 🛠️

The repository includes scripts to help diagnose common issues quickly. These should be your first step when troubleshooting problems that aren't simple container conflicts.

### **1. Running All Backend Tests**

For a comprehensive health check of all services' business logic, you can run the entire backend test suite with a single command. This script executes `pytest` inside each service container, providing a complete report of any failures.

**When to Use**: After making changes to a service to ensure you haven't introduced regressions elsewhere.

**Command**:
Run the following command to give the script execution permissions for the first time.
   ```Bash  
   chmod +x scripts/run_all_tests.sh
   ```

Run all pytest suites with one command
   ```Bash  
   ./scripts/run_all_tests.sh
   ```

### **2.  Checking Inter-Service Network Connectivity**

If you encounter 502 Bad Gateway or 503 Service Unavailable errors in the UI, it often indicates a networking problem between the services or that a specific service has failed to start. You can diagnose this using the network debugging script.

**When to Use**: When the application is running but API calls are failing.

**Command**:
First, ensure the application stack is running with "docker-compose up -d". Then, execute the script inside the api-gateway container:

   ```Bash  
   docker-compose exec api-gateway python debug_network.py
   ```

This script will test DNS resolution and HTTP connectivity from the gateway to all other services and print a PASS or FAIL status for each one, helping you quickly identify the point of failure.

### **3.  Diagnosing Leadership Service 404 Errors**

If you encounter the error {"error":"Failed to fetch data from data-service (status 404)"} when calling the /leadership/:ticker endpoint, it means the leadership-service is unable to get the data it needs from the data-service. This can be due to a network issue, a problem with the data-service itself, or an issue with fetching data from the external provider (Yahoo Finance).

A dedicated diagnostic script is available to trace this specific data flow and pinpoint the problem.

**When to Use**: When a call to GET /leadership/:ticker returns a 404 or 502 error related to the data-service.

What to Expect:
First, ensure the application stack is running with docker-compose up -d. Then, execute the script inside the api-gateway container:

   ```Bash  
   docker-compose exec api-gateway python diagnose_leadership_issue.py
   ```
**What to Expect**:
The script tests the connection from within the Docker network to each of the critical data-service endpoints that the leadership-service relies on.

A successful run will look like this, indicating the problem is likely within the leadership-service's own code:

   ```Bash  
   --- Starting Leadership Service Dependency Diagnosis ---
   ...
   [INFO] Testing Endpoint: Core Financials
   [PASS] Successfully connected. Status Code: 200.
   [PASS] Response contains valid JSON.
   ...
   --- Diagnosis Complete ---
   ✅ All required data-service endpoints responded successfully...
   ```

A failed run will highlight the specific endpoint that is failing and provide next steps for debugging:

   ```Bash  
   --- Starting Leadership Service Dependency Diagnosis ---
   ...
   [INFO] Testing Endpoint: Core Financials
   [FAIL] data-service returned a 404 Not Found.
            This is the likely source of the error in leadership-service.
            Next Steps: Check the 'data-service' logs...
   ...
   --- Diagnosis Complete ---
   ❌ One or more checks failed. Review the output above...
   ```

### **4. Debugging External API Connectivity (e.g., Finnhub)**

**When to Use**: When a service fails to fetch data from an external provider like Finnhub, and you suspect an issue with the API key or network connectivity from within the container.

**Command**:

1. **Check if the API Key is Present in the Container:** This command verifies that the environment variable from your .env file was successfully passed into the running container.

   ```Bash  
   docker-compose exec data-service python -c "import os; print(os.getenv('FINNHUB_API_KEY'))"
   ```

   **Expected Success Output**: Your full Finnhub API key.
   
   **Expected Failure Output**: None or a blank line. If you see this, check for typos in your .env file or restart your containers with docker-compose down && docker-compose up --build -d.

2. **Test Direct API Connectivity with curl:** This command bypasses all application code and directly tests if the container can reach the Finnhub API with your key.

One-Time Setup (If needed): The data-service container does not include curl by default. Run this command once to install it:

   ```Bash  
   docker-compose exec -u root data-service sh -c "apt-get update && apt-get install -y curl"
   ```

Test Command:
Replace YOUR_API_KEY with your actual key from the .env file.

   ```Bash  
   docker-compose exec data-service curl "[https://finnhub.io/api/v1/stock/peers?symbol=NVDA&token=YOUR_API_KEY](https://finnhub.io/api/v1/stock/peers?symbol=NVDA&token=YOUR_API_KEY)"
   ```

   **Expected Success Output**: A JSON list of ticker symbols, like ["NVDA","AVGO","AMD",...].
   
   **Expected Failure Output**: A JSON error, like {"error":"Invalid API key"}.