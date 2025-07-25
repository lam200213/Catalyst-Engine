# Latest Add:
import requests
import os

# Configuration
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
TICKER = "AAPL" # Use a common, reliable ticker for the test

# URLs for the data-service endpoints that leadership-service depends on
endpoints_to_test = {
    "Core Financials": f"{DATA_SERVICE_URL}/financials/core/{TICKER}",
    "Price History": f"{DATA_SERVICE_URL}/data/{TICKER}",
    "Industry Peers": f"{DATA_SERVICE_URL}/industry/peers/{TICKER}"
}

print("--- Starting Leadership Service Dependency Diagnosis ---")
print(f"This script will test the connection from this container (api-gateway) to the data-service endpoints required by the leadership-service for the ticker '{TICKER}'.")
print("-" * 50)

all_passed = True

for name, url in endpoints_to_test.items():
    print(f"\n[INFO] Testing Endpoint: {name}")
    print(f"       URL: {url}")
    
    try:
        response = requests.get(url, timeout=15)
        
        if response.status_code == 200:
            print(f"  [PASS] Successfully connected. Status Code: {response.status_code}.")
            # Optional: Check if response is valid JSON
            try:
                response.json()
                print("  [PASS] Response contains valid JSON.")
            except requests.exceptions.JSONDecodeError:
                print(f"  [FAIL] Response is not valid JSON. This could cause issues in the leadership-service.")
                print(f"         Response Text: {response.text[:100]}...")
                all_passed = False
        elif response.status_code == 404:
            print(f"  [FAIL] data-service returned a 404 Not Found.")
            print("         This is the likely source of the error in leadership-service.")
            print("         This means the data-service itself cannot find or fetch data for the ticker from its external provider (e.g., Yahoo Finance).")
            print("         Next Steps: Check the 'data-service' logs for errors related to 'yfinance_provider.py' or external API connection issues.")
            all_passed = False
        else:
            print(f"  [FAIL] Received an unexpected status code: {response.status_code}.")
            print(f"         Response Text: {response.text[:100]}...")
            all_passed = False
            
    except requests.exceptions.Timeout:
        print(f"  [FAIL] Connection timed out after 15 seconds.")
        print("         This indicates a network issue or that the 'data-service' is unresponsive.")
        all_passed = False
    except requests.exceptions.RequestException as e:
        print(f"  [FAIL] A network error occurred: {e}")
        print("         This could be a DNS resolution problem or a network connectivity issue within Docker.")
        all_passed = False

print("\n" + "-" * 50)
print("--- Diagnosis Complete ---")

if all_passed:
    print("✅ All required data-service endpoints responded successfully from within the Docker network.")
    print("   If the leadership-service is still failing, the issue is likely within the leadership-service itself.")
    print("   Next Steps: Check the 'leadership-service' logs for errors in its own logic or how it constructs request URLs.")
else:
    print("❌ One or more checks failed. Review the output above to identify the point of failure.")