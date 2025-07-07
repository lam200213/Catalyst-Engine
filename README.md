# SEPA Stock Screener & VCP Analyzer

## Project Objective
To deliver a locally-runnable, containerized web application that allows users to identify stocks passing key quantitative SEPA criteria and visually analyze their Volatility Contraction Pattern (VCP) on a chart.

## Last Updated
2025-07-07
Production Hardening

## Key Features (Current MVP)
* **Ticker Universe Generation:** Retrieves a comprehensive list of all US stock tickers (NYSE, NASDAQ, AMEX) via a dedicated Python service. 
- **Modular Data Acquisition and Caching**: Utilizes a **Facade Pattern** in the `data-service` to fetch data from multiple sources (Finnhub, yfinance), and caches financial data (price/fundamentals from sources, news from MarketAux) to minimize redundant API calls.  
- **Quantitative Screening**: Screens stocks based on Mark Minervini's 8 Trend Template criteria.
- **VCP Analysis**: Algorithmically analyzes a stock's Volatility Contraction Pattern (VCP).
- **Dynamic Chart Visualization**: Displays charts with VCP trendlines, buy pivot points, and stop-loss levels.
* **Microservices Architecture:** A robust, containerized environment managed through a central API Gateway, all powered by Python.
- **Containerized Environment**: Fully containerized for consistent, one-command startup.

## Project Structure
The application follows a microservices architecture. The frontend communicates with a single API Gateway, which routes requests to the appropriate backend service.

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

## Getting Started

### Prerequisites
Ensure the following software is installed on your system:
- Git
- Docker
- Docker Compose (usually included with Docker Desktop)

### Installation & Setup
Follow these steps to set up and run the application locally:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/sepa-stock-screener.git
   cd sepa-stock-screener
   ```

2. **Create a `.env` file**:
   Copy the `.env.example` file to `.env` in the project root and add your Finnhub API key.
   In Linux and macOS environments:
   ```bash
   cp .env.example .env
   ```
  
  In Windows PowerShell
  ``` PowerShell
  Copy-Item .env.example .env
  ```

   Open `.env` and replace `YOUR_FINNHUB_API_KEY` and `YOUR_MARKETAUX_API_KEY` with your actual key if have. (Finnhub API key is only needed if you specifically request it as a data source; MARKETAUX API key is necessary for the news-fetching feature)

3. **Run the application**:
   Build and start all services using Docker Compose.
   ```bash
   docker-compose up
   ```
   This command builds Docker images for each service and starts all containers.

4. **Access the application**:
   - **Frontend UI**: [http://localhost:5173](http://localhost:5173) (default port: 5173)
   - **API Gateway**: [http://localhost:3000](http://localhost:3000) (all API requests from the frontend are sent here)

## Production Environment
The docker-compose.yml file is configured for a production-like environment. It uses optimized, static builds for the frontend and runs backend services without debug mode enabled. For development with features like hot-reloading, you will need to modify the docker-compose.yml file to use Dockerfile.dev for the frontend and mount local volumes for the backend services.

## API Gateway Endpoints
The frontend communicates exclusively with the API Gateway, which proxies requests to the appropriate backend services.

- **GET `/ticker`** 
  - Retrieves a list of all US stock tickers from the ticker-service.  

* **GET `/data/:ticker`**
    * Proxies to: `data-service`
    * Retrieves historical price data for a ticker, with caching.
    * **Note:** The `source` parameter is handled by the `data-service` directly, not the gateway.

* **GET `/news/:ticker`**
    * Proxies to: `data-service`
    * Retrieves recent news articles for a ticker, with caching.

- **GET `/screen/:ticker`**
  - Proxies to the Screening Service.
  - Applies the 7 quantitative screening criteria to the specified ticker and returns a detailed pass/fail result.
  - **Error Handling for Invalid Tickers:** Returns `502 Bad Gateway` with a descriptive error message.
  - **Example Success Response:**
    ```json
    {
      "ticker": "AAPL",
      "passes": true,
      "details": {
        "current_price_above_ma150_ma200": true,
        "ma150_above_ma200": true,
        "ma200_trending_up": true,
        "ma50_above_ma150_ma200": true,
        "current_price_above_ma50": true,
        "price_30_percent_above_52_week_low": true,
        "price_within_25_percent_of_52_week_high": true
      },
      "values": {
        "current_price": 170.00,
        "ma_50": 165.00,
        "ma_150": 155.00,
        "ma_200": 150.00,
        "low_52_week": 120.00,
        "high_52_week": 180.00
      }
    }
    ```
  - **Example Error Response (for invalid ticker):**
    ```json
    {
      "error": "Invalid or non-existent ticker: FAKETICKERXYZ",
      "details": "Could not retrieve price data for FAKETICKERXYZ from yfinance."
    }
    ```

- **GET `/analyze/:ticker`**  
  - Proxies to the Analysis Service.  
  - Performs VCP analysis on historical data and returns a standardized payload containing the analysis results and historical data used for charting.
  - **Error Handling**: Returns `502 Bad Gateway` if the data-service cannot find the ticker, and `503 Service Unavailable` if the data-service cannot be reached.
  - **Example Success Response:**
    ```json
    {
      "ticker": "AAPL",
      "analysis": {
        "detected": true,
        "message": "VCP analysis complete.",
        "vcpLines": [{"time": "2024-06-10", "value": 195.0}, ...],
        "buyPoints": [{"value": 196.95}],
        "sellPoints": [{"value": 188.10}],
        "ma20": [{"time": "2024-07-01", "value": 192.5}, ...],
        "ma50": [{"time": "2024-07-01", "value": 190.0}, ...],
        "ma150": [{"time": "2024-07-01", "value": 185.0}, ...],
        "ma200": [{"time": "2024-07-01", "value": 180.0}, ...],
        "lowVolumePivotDate": "2024-06-25",
        "volumeTrendLine": [
            {"time": "2024-06-10", "value": 5500000},
            {"time": "2024-06-25", "value": 2500000}
        ]
      },
      "historicalData": [
        {"formatted_date": "2024-01-01", "open": 170.0, "high": 172.0, "low": 169.0, "close": 171.5, "volume": 5000000},
        ...
      ]
    }
    ```

 - **POST `/cache/clear`**  
- Proxies to: data-service
- Purpose: Manually clears all cached data (prices and news) from the MongoDB database. This is a developer utility to ensure fresh data is fetched from source APIs after deploying code changes.

- **Example Usage:**
    ```Bash
    {
      curl -X POST http://localhost:3000/cache/clear
    }
    ```

- **Example Success Response:**
    ```JSON
    {
      "message": "All data service caches have been cleared."
    }
    ```

## **Common Errors & Troubleshooting**

### **Container Name Conflict**

**Error:** You might see an error like this when running docker-compose up:

Error response from daemon: Conflict. The container name "/some-service" is already in use by container...

**Cause:** This happens when a previous Docker session was stopped improperly (e.g., by closing the terminal) without using docker-compose down. This leaves behind *stopped* containers that still occupy their names, preventing new ones from starting. This will also make the application unreachable in your browser, causing an ERR\_CONNECTION\_REFUSED error.

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
   ```
