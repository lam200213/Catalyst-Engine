#!/bin/bash
# run_all_tests.sh - A script to run pytest in all backend services.

# List of all services that have pytest tests
SERVICES=(
    "api-gateway"
    "ticker-service"
    "data-service"
    "screening-service"
    "analysis-service"
    "scheduler-service"
    "leadership-service"
    "monitoring-service"
)

# --- Script Logic ---
# Run the script with an optional argument: ./run_all_tests.sh --fail-fast for Efficient Debugging
# In this mode, the script will immediately stop after the first service fails its tests.

# Check for a --fail-fast argument
STOP_ON_FAILURE=false
if [[ "$1" == "--fail-fast" ]]; then
  STOP_ON_FAILURE=true
  echo "Running in --fail-fast mode. The script will stop on the first failure."
fi

# Arrays to hold the names of services that pass or fail
declare -a passed_services
declare -a failed_services
overall_status=0 # Overall exit code for the script; 0 for success, 1 for failure

echo "🚀 Starting tests for all services..."
echo "------------------------------------"

for service in "${SERVICES[@]}"; do
    echo ""
    echo "--> Running tests for: $service"
    # The -T flag disables pseudo-tty allocation, which is best practice for automated scripts
    docker-compose exec -T "$service" python -m pytest
    status=$?

    if [ $status -ne 0 ]; then
        echo "❌ Tests FAILED for: $service"
        failed_services+=("$service")
        overall_status=1 # Mark the overall run as failed
        if [ "$STOP_ON_FAILURE" = true ]; then
            echo "------------------------------------"
            echo "Stopping execution due to --fail-fast."
            break # Exit the loop immediately
        fi
    else
        echo "✅ Tests PASSED for: $service"
        passed_services+=("$service")
    fi
    echo "------------------------------------"
done

# --- Final Summary ---
echo ""
echo "===================================="
echo "📊 Test Run Summary"
echo "===================================="
echo ""
echo "PASSED services: (${#passed_services[@]})"
for service in "${passed_services[@]}"; do
    echo "  - ✅ $service"
done
echo ""
echo "FAILED services: (${#failed_services[@]})"
if [ ${#failed_services[@]} -eq 0 ]; then
    echo "  - None"
else
    for service in "${failed_services[@]}"; do
        echo "  - ❌ $service"
    done
fi
echo ""
echo "===================================="

# --- Exit with overall status ---
if [ $overall_status -ne 0 ]; then
    echo "🔥 Overall result: FAILURE"
    exit 1
else
    echo "🎉 Overall result: SUCCESS"
    exit 0
fi