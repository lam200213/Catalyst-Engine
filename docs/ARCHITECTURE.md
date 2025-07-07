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
│   │   │   ├── finnhub_provider.py
│   │   │   ├── marketaux_provider.py
│   │   │   └── yfinance_provider.py
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── test_app.py
│   │   │   ├── test_finnhub_provider.py
│   │   │   └── test_marketaux_provider.py
│   │   ├── app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── screening-service/   # Python/Flask - Applies the 8 SEPA screening criteria
│   │   ├── tests/
│   │   │   └── test_screening_logic.py
│   │   ├── app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── ticker-service/      # Python/Flask - Fetches all US stock tickers
│       ├── tests/
│       │   └── test_app.py
│       ├── app.py
│       ├── Dockerfile
│       └── requirements.txt
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
| **API Gateway** | **Python, Flask, Requests, Flask-Cors** |
| **Data Service** | **Python, Flask, PyMongo, Requests, yfinance, finnhub-python, python-dotenv** |
| **Analysis & Screening Services** | **Python, Flask, NumPy, Requests** |
| **Ticker Service** | **Python, Flask, Pandas, Requests** |
| **Data Caching** | MongoDB |
| **Frontend UI & Charting** | React (Vite), TradingView Lightweight Charts, Chakra UI, Axios |
| **Test** | Pytest, requests-mock, Vitest, React Testing Library |
| **Local Orchestration** | Docker, Docker Compose |