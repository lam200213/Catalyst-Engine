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
│   ├── data-service/        # Python/Flask - Facade for fetching and caching data
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── finnhub_provider.py
│   │   │   ├── marketaux_provider.py
│   │   │   └── yfin/
│   │   │       ├── __init__.py
│   │   │       ├── yahoo_client.py
│   │   │       ├── price_provider.py
│   │   │       └── financials_provider.py
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── test_app.py
│   │   │   ├── test_finnhub_provider.py
│   │   │   └── test_marketaux_provider.py
│   │   ├── app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── leadership-service/  # Python/Flask - Applies leadership criteria
│   │   ├── tests/
│   │   │   ├── test_integration.py
│   │   │   ├── test_financial_health_checks.py
│   │   │   ├── test_market_relative_checks.py
│   │   │   ├── test_industry_peer_checks.py
│   │   ├── app.py
│   │   ├── checks/
│   │   │   ├── financial_health_checks.py
│   │   │   ├── market_relative_checks.py
│   │   │   ├── industry_peer_checks.py
│   │   ├── data_fetcher.py          # Service Client: Handles communication with data-service
│   │   ├── Dockerfile
│   │   └── requirements.txt
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
│   └── shared/              # Data contract
│       ├── __init__.py 
│       ├── contracts.py
├── frontend-app/            # React/Vite - User Interface
│   ├── scripts/
│   │   └── verify-structure.cjs
│   ├── src/
│   │   ├── components/      # Reusable React components
│   │   ├── hooks/           # Custom React hooks for state logic
│   │   ├── services/        # API communication logic
│   │   ├── App.jsx          # Main application orchestrator
│   │   ├── App.test.jsx
│   │   ├── main.jsx         # Application entry point
│   │   ├── setupTests.js
│   │   └── theme.js
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