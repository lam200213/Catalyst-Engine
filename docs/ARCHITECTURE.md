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
│   │   │       ├── price_provider.py
│   │   │       └── financials_provider.py
│   │   │       └── market_data__provider.py
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── test_app.py
│   │   │   ├── test_finnhub_provider.py
│   │   │   └── test_marketaux_provider.py
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
│   │   │   ├── test_industry_peer_checks.py
│   │   ├── app.py
│   │   ├── checks/          # Business logic for each leadership check
│   │   │   ├── financial_health_checks.py
│   │   │   ├── market_relative_checks.py
│   │   │   ├── industry_peer_checks.py
│   │   │   ├── utils.py
│   │   ├── data_fetcher.py  # Service Client: Handles communication with data-service
│   │   ├── helper_functions.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── monitoring-service/
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── test_integration.py
│   │   │   ├── test_unit.py
│   │   │   ├── test_market_leaders_logic.py
│   │   ├── app.py
│   │   ├── market_health_utils.py
│   │   ├── market_leaders.py
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
│   ├── scripts/
│   │   └── verify-structure.cjs
│   ├── src/
│   │   ├── components/      # Reusable React components
│   │   ├── hooks/           # Custom React hooks for state logic
│   │   ├── pages/           # Top-level page components
│   │   ├── services/        # API communication logic and mockdata
│   │   ├── App.jsx          # Main application component with routing
│   │   ├── App.test.jsx
│   │   ├── main.jsx         # Application entry point
│   │   ├── setupTests.js
│   │   └── theme.js         # Chakra UI theme configuration
│   ├── Dockerfile           # For production builds
│   ├── Dockerfile.dev       # For development environment
│   ├── nginx.conf
│   ├── package.json
│   └── vitest.config.js
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

### Frontend and Monitoring-Service Communication

The Market Health feature introduces a key interaction flow:

1. The frontend-app's /market page initiates a request to the api-gateway at GET /monitor/market-health.

2. The api-gateway proxies this request to the monitoring-service.

3. The monitoring-service acts as an orchestrator. It calls various endpoints on the data-service (e.g., to get market index data, find top-performing industries) to gather the necessary information.

4. The data-service fetches data from external sources or its cache and returns it to the monitoring-service.

5. The monitoring-service aggregates and formats the data into the MarketHealthResponse contract and sends it back up the chain to the frontend-app for rendering.