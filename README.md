# SEPA Stock Screener & VCP Analyzer

## Project Objective
To deliver a locally-runnable, containerized web application that allows users to identify stocks passing key quantitative SEPA criteria and visually analyze their Volatility Contraction Pattern (VCP) on a chart.

## Last Updated
2025-06-30 23:41 HKT
Major architectural update: Refactored the entire backend to a consistent, all-Python stack for improved maintainability. Added a dedicated ticker-service.

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
│   ├── api-gateway/         \# Python/Flask  
│   ├── data-service/        \# Python/Flask (Facade for Data Providers)
       ├── providers/
       │   ├── __init__.py               # Makes 'providers' a Python package
       │   ├── yfinance_provider.py      # Logic to fetch data from Yahoo Finance
       │   └── finnhub_provider.py       # Logic to fetch data from Finnhub
       ├── app.py                        # Main Flask application with data source routing
       ├── Dockerfile
       └── requirements.txt              # Python dependencies
│   ├── screening-service/   \# Python/Flask  
│   ├── analysis-service/    \# Python/Flask  
│   └── ticker-service/      \# Python/Flask  
├── frontend-app/  
├── .env.example  
├── docker-compose.yml  
└── README.md
```

## Technology Stack

| Component | Technology |
| :---- | :---- |
| **API Gateway** | **Python, Flask, Requests** |
| **Data Service** | **Python, Flask, PyMongo, Requests** |
| **Quantitative Services** | **Python, Flask, NumPy** |
| **Ticker Service** | **Python, Flask, Pandas** |
| **Data Caching** | MongoDB |
| **Frontend UI & Charting** | React (Vite), TradingView Lightweight Charts |
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
   ```bash
   cp .env.example .env
   ```
   Open `.env` and replace `YOUR_MARKETAUX_API_KEY` with your actual key.

3. **Run the application**:
   Build and start all services using Docker Compose.
   ```bash
   docker-compose up --build
   ```
   This command builds Docker images for each service and starts all containers.

4. **Access the application**:
   - **Frontend UI**: [http://localhost:5173](http://localhost:5173) (default port: 5173)
   - **API Gateway**: [http://localhost:3000](http://localhost:3000) (all API requests from the frontend are sent here)

## API Gateway Endpoints
The frontend communicates exclusively with the API Gateway, which proxies requests to the appropriate backend services.

- **GET `/ticker`** 
  - Retrieves a list of all US stock tickers from the ticker-service.  

* **GET `/data/:ticker?source=<provider>`**
    * Proxies to: `data-service`
    * Retrieves historical price data for a ticker.
    * `provider` can be `finnhub` (default) or `yfinance`.

- **GET `/screen/:ticker`**  
  - Proxies to the Screening Service.  
  - Applies the 8 quantitative screening criteria to the specified ticker and returns a pass/fail result.

- **GET `/analyze/:ticker`**  
  - Proxies to the Analysis Service.  
  - Performs VCP analysis on historical data and returns a standardized payload containing the analysis results and historical data used for charting.