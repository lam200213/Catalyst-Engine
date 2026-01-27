# Detailed Architecture

## Project Structure

```
/
├── backend-services/
│   ├── analysis-service/    # Python/Flask - Performs VCP analysis
│   │   ├── tests/
│   │   │   ├── test_integration.py
│   │   │   └── test_unit.py
│   │   ├── app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── api-gateway/         # Python/Flask - Routes requests to other services
│   │   ├── tests/
│   │   │   └── test_gateway.py
│   │   ├── app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── data-service/        # Python/Flask - for fetching and caching data
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── finnhub_provider.py
│   │   │   ├── marketaux_provider.py
│   │   │   └── yfin/
│   │   │       ├── __init__.py
│   │   │       ├── yahoo_client.py
│   │   │       └── webshare_proxies.py
│   │   │       ├── price_provider.py
│   │   │       └── financials_provider.py
│   │   │       └── market_data__provider.py
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── test_app.py 
│   │   │   ├── test_integration.py
│   │   │   ├── test_finnhub_provider.py
│   │   │   ├── test_marketaux_provider.py
│   │   │   └── test_market_data_provider.py
│   │   ├── app.py
│   │   ├── helper_functions.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── leadership-service/  # Python/Flask - Applies leadership criteria
│   │   ├── tests/
│   │   │   ├── test_integration.py
│   │   │   ├── test_financial_health_checks.py
│   │   │   ├── test_market_relative_checks.py
│   │   │   └── test_industry_peer_checks.py
│   │   ├── app.py
│   │   ├── checks/          # Business logic for each leadership check
│   │   │   ├── financial_health_checks.py
│   │   │   ├── market_relative_checks.py
│   │   │   ├── industry_peer_checks.py
│   │   │   └── utils.py
│   │   ├── data_fetcher.py  # Service Client: Handles communication with data-service
│   │   ├── helper_functions.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── scheduler-service/  # Python/Flask - Orchestrator
│   │   ├── tests/
│   │   │   ├── conftest.py             # Shared fixtures
│   │   │   ├── unit/                   # Fast, mocked tests
│   │   │   │   ├── test_job_service.py
│   │   │   │   ├── test_progress_emitter.py
│   │   │   │   └── test_contracts.py
│   │   │   ├── integration/            # Real DB/Celery tests
│   │   │   │   ├── test_api_endpoints.py
│   │   │   │   ├── test_celery_tasks.py
│   │   │   │   └── test_sse_streaming.py
│   │   │   ├── e2e/
│   │   │   │   └── test_screening_pipeline.py
│   │   ├── services/                   # Shared Business Logic
│   │   │   ├── job_service.py          # Job lifecycle (CRUD, State transitions)
│   │   │   ├── progress_emitter.py     # Progress event helpers
│   │   │   └── __init__.py
│   │   ├── app.py
│   │   ├── celery_app.py               # Celery config & Beat schedule
│   │   ├── tasks.py                    # Celery tasks (Worker entrypoint)
│   │   ├── db.py                       # Singleton DB connection
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── monitoring-service/
│   │   ├── tests/
│   │   │   ├── conftest.py     
│   │   │   ├── routes/
│   │   │   │   ├── test_health.py
│   │   │   │   ├── test_method_constraints.py
│   │   │   │   ├── test_response_format.py
│   │   │   │   ├── test_watchlist_get_basic.py
│   │   │   │   ├── test_watchlist_get_exclusions.py
│   │   │   │   ├── test_watchlist_get_exclusions_edges.py
│   │   │   │   ├── test_watchlist_get_scaling.py
│   │   │   │   ├── test_watchlist_put_basic.py
│   │   │   │   ├── test_watchlist_put_format.py
│   │   │   │   ├── test_watchlist_contract_validation.py
│   │   │   │   ├── test_watchlist_security.py
│   │   │   │   ├── test_orchestrator_endpoint.py
│   │   │   │   └── test_error_handling.py
│   │   │   ├── services/
│   │   │   │   ├── test_update_orchestrator.py
│   │   │   │   ├── test_watchlist_service_add.py
│   │   │   │   ├── test_watchlist_service_add_edges.py
│   │   │   │   ├── test_watchlist_service_get_core.py
│   │   │   │   ├── test_watchlist_service_status_derivation.py
│   │   │   │   ├── test_watchlist_status_service.py
│   │   │   │   ├── test_watchlist_service_scaling.py
│   │   │   │   └── test_watchlist_service_security.py
│   │   │   ├── db/
│   │   │   │   ├── test_mongo_connect.py
│   │   │   │   ├── test_mongo_indexes.py
│   │   │   │   ├── test_mongo_watchlist_crud.py
│   │   │   │   ├── test_mongo_watchlist_security.py
│   │   │   │   ├── test_mongo_watchlist_list.py
│   │   │   │   ├── test_mongo_toggle_favourite.py
│   │   │   │   ├── test_mongo_archive_crud.py
│   │   │   │   ├── test_mongo_bulk_ops.py
│   │   │   │   └── test_mongo_types_and_assertions.py
│   │   │   ├── integration/
│   │   │   │   ├── test_integration_market_health.py
│   │   │   │   ├── test_integration_leaders.py
│   │   │   │   ├── test_integration_watchlist_put_format.py
│   │   │   │   └── test_mongo_client_integration.py
│   │   │   ├── contracts/
│   │   │   │   ├── test_api_contract_compliance.py
│   │   │   │   ├── test_market_leaders_contract_validation.py
│   │   │   │   └── test_watchlist_contract_validation.py
│   │   │   ├── unit/
│   │   │   │   ├── test_market_leaders_logic.py
│   │   │   │   └── test_market_health_unit.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── watchlist_service.py # Business logic for watchlist CRUD operations & contract mapping
│   │   │   ├── watchlist_status_service.py # Pure business logic for status derivation (fall-through, stale, guardrails)
│   │   │   ├── portfolio_service.py # Portfolio alerts & data enrichment
│   │   │   ├── downstream_clients.py # Encapsulates HTTP calls to other services for the orchestrator
│   │   │   └── update_orchestrator.py # Drives the orchestrator endpoint by coordinating downstream calls, status derivation, and bulk persistence
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── mongo_client.py # MongoDB interaction layer including TTL index on archived_watchlist_items and user+ticker compound indexes
│   │   ├── app.py
│   │   ├── market_health_utils.py
│   │   ├── market_leaders.py
│   │   ├── helper_functions.py
│   │   ├── data_fetcher.py
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   ├── screening-service/   # Python/Flask - Applies the 8 SEPA screening criteria
│   │   ├── tests/
│   │   │   └── test_screening_logic.py
│   │   ├── app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── ticker-service/      # Python/Flask - Fetches all US stock tickers
│   │   ├── tests/
│   │   │   └── test_app.py
│   │   ├──  app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── shared/              # Pydantic models for inter-service data contracts
│       ├── __init__.py 
│       ├── contracts.py
├── frontend-app/            # React/Vite - User Interface
│   ├── src/                 # See FRONTEND_ARCHITECTURE.md for detailed structure
│   │   ├── components/      # 8 UI components + 7 tests
│   │   ├── hooks/           # 5 custom hooks + 4 tests
│   │   ├── pages/           # 4 page components
│   │   ├── services/        # 5 API clients + 2 test files
│   │   └── types/           # TypeScript contract definitions
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── package.json
│   📘 **For detailed frontend architecture, see FRONTEND_ARCHITECTURE.md**
├── scripts/
│   └── check-debug-mode.sh
├── .env.example
├── .gitignore
├── docker-compose.yml       # Orchestrates all services for local deployment
└── README.md
```

## Technology Stack

| Component | Technology |
| :---- | :---- |
| **API Gateway** | Python, Flask, Requests, Flask-Cors |
| **Data Service** | Python, Flask, PyMongo, yfinance, finnhub-python, curl-cffi |
| **Analysis & Screening Services** | Python, Flask, NumPy, Requests |
| **Leadership Service** | Python, Flask, Pandas, NumPy, Requests |
| **Scheduler Service** | Python, Flask, Requests, APScheduler |
| **Ticker Service** | Python, Flask, Pandas, Requests |
| **Data Caching** | Redis |
| **Data Persistence** | MongoDB |
| **Frontend UI & Charting** | React (Vite), TradingView Lightweight Charts, Chakra UI |
| **Asynchronous Tasks** | Celery |
| **Real-time Updates** | Server-Sent Events (SSE) |
| **Testing** | Pytest, Vitest, React Testing Library |
| **Local Orchestration** | Docker, Docker Compose |

## Concurrency Burden

The data-service, which is the component that actually interacts with the external world (Yahoo Finance), has full control over the concurrency. 
The heavy lifting of parallelization is handled by the data-service, as it is the one doing the slow, external I/O-bound work.

## Communication Flow

The system is designed with a microservices architecture. The `api-gateway` is the single entry point for the frontend application. It routes requests to the appropriate backend service.

### Screening-Service and Data-Service Communication

A key interaction is between the `screening-service` and the `data-service`. When a screening request is received, the `screening-service` needs to fetch historical price data for a list of tickers.

To optimize this process, the `screening-service` now communicates with the `data-service` using a batch endpoint:

*   **Endpoint:** `/price/batch`
*   **Method:** `POST`
*   **Payload:** A JSON object containing a list of stock tickers.
*   **Response:** A JSON object containing the historical price data for all requested tickers.

This batching mechanism significantly reduces the number of HTTP requests between the services, improving performance and efficiency, especially when screening a large number of tickers. The `screening-service` processes the tickers in chunks to avoid overwhelming the `data-service` with a single, massive request.

### Scheduler-Service and Monitoring-Service Communication
**Watchlist Health Check Flow:**

1. Frontend or scheduler triggers `POST /jobs/watchlist/refresh` on scheduler-service
2. Scheduler-service enqueues Celery task `refresh_watchlist_task`
3. Task calls monitoring-service's internal orchestrator endpoint:  
   `POST /monitor/internal/watchlist/refresh-status`
4. Monitoring-service orchestrator:
   - Loads active watchlist items from MongoDB
   - Calls screening-service (`POST /screen/batch`)
   - Calls analysis-service (`POST /analyze/batch`, `POST /analyze/freshness/batch`)
   - Calls data-service (`POST /data/return/batch`)
   - Derives status signals via `watchlist_status_service`
   - Performs bulk updates (`watchlistitems`) and bulk archiving (`archived_watchlist_items` with `ArchiveReason.FAILED_HEALTH_CHECK`)
5. Returns `WatchlistRefreshStatusResponse` with `updated_items`, `archived_items`, `failed_items`
6. Scheduler persists summary in job metadata and updates job status

### Frontend and Monitoring-Service Communication

The Market Health feature introduces a key interaction flow:

1. The frontend-app's /market page initiates a request to the api-gateway at GET /monitor/market-health.

2. The api-gateway proxies this request to the monitoring-service.

3. The monitoring-service acts as an orchestrator. It calls various endpoints on the data-service (e.g., to get market index data, find top-performing industries) to gather the necessary information.

4. The data-service fetches data from external sources or its cache and returns it to the monitoring-service.

5. The monitoring-service aggregates and formats the data into the MarketHealthResponse contract and sends it back up the chain to the frontend-app for rendering.

## Documentation Index
This repository maintains multiple architecture documents for different concerns:

| Document | Scope | Audience |
|:---|:---|:---|
| **ARCHITECTURE.md** (this file) | High-level system architecture, microservices communication | Full-stack developers, DevOps |
| **FRONTEND_ARCHITECTURE.md** | Frontend structure, patterns, testing standards | Frontend developers |
| **DATABASE_SCHEMA.md** | MongoDB collections, indexes, data models | Backend developers, DBAs |
| **DATA_CONTRACTS.md** | API request/response contracts (Pydantic models) | Full-stack developers, API consumers |
| **API_REFERENCE.md** | Endpoint catalog, authentication, error codes | Frontend developers, integrators |
| **FRONTEND_TESTING_STANDARD.md** | TDD workflow, test structure, AAA pattern | Frontend developers |
