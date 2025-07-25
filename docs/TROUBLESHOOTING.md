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