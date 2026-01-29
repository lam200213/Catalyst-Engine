#!/bin/bash

# ==============================================================================
# SEPA Stock Screener - Universal Test Runner
# ==============================================================================
# Usage:
#   ./scripts/run_tests.sh [unit|e2e|frontend|all]
#
# Prerequisite: Docker must be running.
# ==============================================================================

TYPE=${1:-all}

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting SEPA Test Runner... Mode: ${TYPE}${NC}"

# ------------------------------------------------------------------------------
# 1. Backend Unit & Integration Tests (Dynamic Discovery)
# ------------------------------------------------------------------------------
run_backend_tests() {
    echo -e "\n${YELLOW}=== Running Backend Service Tests ===${NC}"
    
    # Iterate through all subdirectories in backend-services
    for service_dir in backend-services/*/; do
        service_name=$(basename "$service_dir")
        
        # Check if directory has a 'tests' folder
        if [ -d "${service_dir}tests" ]; then
            echo -e "${YELLOW}Testing Service: ${service_name}...${NC}"
            
            # Determine test command based on maturity
            # If 'tests/unit' exists, target it specifically to be safe, otherwise run all in 'tests'
            if [ -d "${service_dir}tests/unit" ]; then
                TEST_CMD="pytest tests/unit"
            else
                TEST_CMD="pytest tests"
            fi

            # Run tests inside the container to ensure dependency/contract integrity
            # Using --rm to clean up after execution
            docker-compose -f docker-compose.yml run --rm --entrypoint "$TEST_CMD" "$service_name"
            
            if [ $? -eq 0 ]; then
                echo -e "${GREEN}✔ ${service_name} Passed${NC}"
            else
                echo -e "${RED}✘ ${service_name} Failed${NC}"
                # Allow continuing to other services? Uncomment exit to stop on first fail.
                # exit 1 
            fi
        else
            echo -e "Skipping ${service_name} (No tests found)"
        fi
    done
}

# ------------------------------------------------------------------------------
# 2. Frontend Tests (Standardized)
# ------------------------------------------------------------------------------
run_frontend_tests() {
    echo -e "\n${YELLOW}=== Running Frontend Tests ===${NC}"
    
    # Assuming frontend is in root or 'frontend' dir. Adjust path as needed.
    # Leveraging the container ensures node_modules consistency.
    docker-compose -f docker-compose.yml run --rm --entrypoint "npm run test:ci" frontend-app
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✔ Frontend Passed${NC}"
    else
        echo -e "${RED}✘ Frontend Failed${NC}"
    fi
}

# ------------------------------------------------------------------------------
# 3. E2E Tests (Full Stack - Week 10 Requirements)
# ------------------------------------------------------------------------------
run_e2e_tests() {
    echo -e "\n${YELLOW}=== Running E2E Full Stack Tests (Week 10 Pipeline) ===${NC}"
    
    # 1. Spin up the FULL stack (Prod + Dev config pattern as requested)
    # We use -d to run in background, then execute tests against it.
    echo "Booting full stack..."
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
    
    # 2. Wait for Health (Crucial for Async/Celery/Mongo)
    echo "Waiting for services to stabilize..."
    sleep 15 # Simple wait. For robustness, use a healthcheck loop script.

    # 3. Execute the E2E test suite from within the scheduler-service
    # (Since scheduler orchestrates the Week 10 pipeline)
    echo "Executing Pipeline Tests..."
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml exec -T scheduler-service pytest tests/e2e
    
    TEST_EXIT_CODE=$?
    
    # 4. Teardown (Optional: Keep it running for debugging if failed?)
    # echo "Tearing down..."
    # docker-compose -f docker-compose.yml -f docker-compose.prod.yml down

    if [ $TEST_EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}✔ E2E Pipeline Passed${NC}"
    else
        echo -e "${RED}✘ E2E Pipeline Failed${NC}"
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# Execution Logic
# ------------------------------------------------------------------------------

if [ "$TYPE" == "unit" ]; then
    run_backend_tests
elif [ "$TYPE" == "frontend" ]; then
    run_frontend_tests
elif [ "$TYPE" == "e2e" ]; then
    run_e2e_tests
elif [ "$TYPE" == "all" ]; then
    run_backend_tests
    run_frontend_tests
    # E2E is usually expensive, often run separately in CI. 
    # Uncomment below to include in 'all', or keep separate.
    # run_e2e_tests 
else
    echo "Unknown mode. Use: unit | frontend | e2e | all"
fi