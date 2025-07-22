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