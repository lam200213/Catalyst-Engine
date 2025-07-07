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