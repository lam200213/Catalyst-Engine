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
)

echo "🚀 Starting tests for all services..."
echo "------------------------------------"

for service in "${SERVICES[@]}"; do
    echo ""
    echo "--> Running tests for: $service"
    docker-compose exec "$service" python -m pytest
    if [ $? -ne 0 ]; then
        echo "❌ Tests FAILED for: $service"
        echo "------------------------------------"
        # Optional: uncomment the next line to stop the script on the first failure
        # exit 1
    else
        echo "✅ Tests PASSED for: $service"
    fi
    echo "------------------------------------"
done

echo ""
echo "All tests completed."