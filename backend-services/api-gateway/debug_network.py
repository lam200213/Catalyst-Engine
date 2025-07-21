# backend-services/api-gateway/debug_network.py

import socket
import requests
import os

# A dictionary of all services and their INTERNAL ports
SERVICES = {
    "data-service": 3001,
    "screening-service": 3002,
    "analysis-service": 3003,
    "scheduler-service": 3004,
    "ticker-service": 5001, # Use the corrected port from our last fix
    "mongodb": 27017,
}

print("--- Starting Network Health Check ---")
all_passed = True

for service_name, port in SERVICES.items():
    print(f"\n[INFO] Testing service: {service_name} on port {port}")
    
    # Step 1: Test DNS Resolution
    try:
        ip_address = socket.gethostbyname(service_name)
        print(f"  [DNS] PASS: '{service_name}' resolved to {ip_address}")
    except socket.gaierror as e:
        print(f"  [DNS] FAIL: Could not resolve '{service_name}'. Error: {e}")
        all_passed = False
        continue # Skip HTTP check if DNS fails

    # Step 2: Test HTTP Connectivity (for Flask services)
    if service_name != "mongodb":
        # All our Flask apps have a root '/' health check
        url = f"http://{service_name}:{port}/"
        try:
            # Use a short timeout
            response = requests.get(url, timeout=5)
            if response.status_code < 500: # Any non-server-error is a pass
                 print(f"  [HTTP] PASS: Connected to {url} and got status {response.status_code}.")
            else:
                 print(f"  [HTTP] FAIL: Connected to {url} but got server error: {response.status_code}.")
                 all_passed = False
        except requests.exceptions.RequestException as e:
            print(f"  [HTTP] FAIL: Could not connect to {url}. Error: {e}")
            all_passed = False

print("\n--- Network Health Check Complete ---")
if all_passed:
    print("✅ All services appear to be connected and responding.")
else:
    print("❌ One or more network checks failed. Please review the output above.")