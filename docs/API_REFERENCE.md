# API Gateway Endpoints Reference

This document catalogs all API endpoints exposed by the SEPA Stock Screener platform. Public-facing endpoints are accessible via the API Gateway for frontend consumption. Internal-only endpoints are used for service-to-service communication within the backend architecture.

**Gateway URL:** `http://localhost:3000`

***

## Table of Contents

1. [How the API Gateway Works](#how-the-api-gateway-works)
2. [Public-Facing APIs (Consumed by Frontend)](#public-facing-apis-consumed-by-frontend)
   - [Ticker Service Routes](#ticker-service-routes)
   - [Data Service Routes](#data-service-routes)
   - [Screening Service Routes](#screening-service-routes)
   - [Analysis Service Routes](#analysis-service-routes)
   - [Leadership Service Routes](#leadership-service-routes)
   - [Monitoring Service Routes](#monitoring-service-routes)
   - [Scheduler Service Routes](#scheduler-service-routes)
3. [Internal-Only APIs (Service-to-Service)](#internal-only-apis-service-to-service)
   - [Internal Data Service Routes](#internal-data-service-routes)
   - [Internal Screening Service Routes](#internal-screening-service-routes)
   - [Internal Analysis Service Routes](#internal-analysis-service-routes)
   - [Internal Leadership Service Routes](#internal-leadership-service-routes)
   - [Internal Monitoring Service Routes](#internal-monitoring-service-routes)

***

## How the API Gateway Works

The API Gateway uses a simple routing pattern based on the first path segment:

- **Route Pattern:** `/<service_key>/<path>`
- **Backend Forwarding:** Requests are forwarded to the appropriate backend service based on the service key
- **Service Keys:**
  - `tickers` → ticker-service (port 5001)
  - `price`, `news`, `financials`, `industry`, `cache` → data-service (port 3001)
  - `screen` → screening-service (port 3002)
  - `analyze` → analysis-service (port 3003)
  - `leadership` → leadership-service (port 3005)
  - `monitor` → monitoring-service (port 3006)
  - `jobs` → scheduler-service (port 3004)

***

# Public-Facing APIs (Consumed by Frontend)

These endpoints are intended for frontend consumption and are accessible via the API Gateway at `http://localhost:3000`.

## Ticker Service Routes

### **GET `/tickers`**
- **Proxies to:** ticker-service (port 5001)
- **Purpose:** Retrieves a list of all US stock tickers from the ticker-service.
- **Data Contract:** Produces [`TickerList`](./DATA_CONTRACTS.md#1-tickerlist).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/tickers
  ```

***

## Data Service Routes

### **GET `/price/:ticker`**
- **Proxies to:** data-service (port 3001)
- **Purpose:** Retrieves historical price data for a ticker, with caching.
- **Query Parameters:**
  - `source` (optional): The data source, e.g., 'yfinance'. Defaults to 'yfinance'.
  - `period` (optional): The period of data to fetch (e.g., "1y", "6mo", "max"). Overridden by `start_date`. Defaults to "1y".
  - `start_date` (optional): The start date for fetching data in YYYY-MM-DD format. Takes precedence over `period`.
- **Data Contract:** Produces [`PriceData`](./DATA_CONTRACTS.md#2-pricedata).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/price/AAPL?source=yfinance&period=6mo
  curl http://localhost:3000/price/AAPL?start_date=2023-01-01
  ```

### **POST `/price/batch`**
- **Proxies to:** data-service (port 3001)
- **Purpose:** Retrieves historical price data for a batch of tickers. More efficient than individual requests.
- **Request Body (JSON):**
  - `tickers` (required): A list of stock ticker strings.
  - `source` (required): The data source, e.g., 'yfinance'.
  - `period` (optional): The period of data to fetch (e.g., "1y", "6mo"). Overridden by `start_date`. Defaults to "1y".
  - `start_date` (optional): The start date for fetching data in YYYY-MM-DD format. Takes precedence over `period`.
- **Example Usage:**
  ```bash
  curl -X POST http://localhost:3000/price/batch \
    -H "Content-Type: application/json" \
    -d '{"tickers": ["AAPL", "GOOGL"], "source": "yfinance", "period": "6mo"}'
  ```
- **Response Body (JSON):**
  ```json
    {
      "success": {
        "AAPL": [
          {"formatted_date": "2024-01-01", "close": 180.0, ...}
        ],
        "GOOGL": [
          {"formatted_date": "2024-01-01", "close": 140.0, ...}
        ],
        "MSFT": [
          {"formatted_date": "2024-01-01", "close": 400.0, ...}
        ]
      },
      "failed": ["FAKETICKER"]
    }
    ```

### **GET `/news/:ticker`**
- **Proxies to:** data-service (port 3001)
- **Purpose:** Retrieves recent news articles for a ticker, with caching.
- **Data Contract:** Produces [`NewsData`](./DATA_CONTRACTS.md#4-newsdata).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/news/AAPL
  ```

### **GET `/financials/core/:ticker`**
- **Proxies to:** data-service (port 3001)
- **Purpose:** Retrieves core fundamental data required for the Leadership Profile screening. Data is cached.
- **Data Contract:** Produces [`CoreFinancials`](./DATA_CONTRACTS.md#3-corefinancials).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/financials/core/AAPL
  ```
- **Example Response:**
  ```json
  {
    "ticker": "AAPL",
    "marketCap": 2800000000000,
    "sharesOutstanding": 15500000000,
    "floatShares": 15400000000,
    "ipoDate": "1980-12-12",
    "annual_earnings": [
      {"Revenue": 383285000000, "Earnings": 6.13, "Net Income": 96995000000}
    ],
    "quarterly_earnings": [
      {"Revenue": 90753000000, "Earnings": 1.53, "Net Income": 23636000000}
    ],
    "quarterly_financials": [
      {"Net Income": 23636000000, "Total Revenue": 90753000000}
    ]
  }
  ```

### **POST `/cache/clear`**
- **Proxies to:** data-service (port 3001)
- **Purpose:** Manually clears cached data from Redis. Developer utility to force a refresh of data from source APIs. Can clear all caches or a specific type of cache.
- **Data Contract:** N/A
- **Request Body (JSON, optional):**
  - Specify a `type` to clear a specific cache. If the body is omitted or `type` is `"all"`, all caches are cleared.
  - Valid types: `"price"`, `"news"`, `"financials"`, `"industry"`.
- **Example Usage:**
  ```bash
  curl -X POST http://localhost:3000/cache/clear
  ```
- **Example Success Response:**
  ```json
  {
    "message": "All data service caches have been cleared."
  }
  ```
- **Example Usage (Clear only price cache):**
  ```bash
  curl -X POST http://localhost:3000/cache/clear \
    -H "Content-Type: application/json" \
    -d '{"type": "price"}'
  ```
- **Example Success Response (Specific):**
  ```json
  {
    "keys_deleted": 1542,
    "message": "Cleared 1542 entries from the 'price' cache."
  }
  ```
- **Example Error Response (Invalid Type):**
  ```json
  {
    "error": "Invalid cache type 'invalid_type'. Valid types are: ['price', 'news', 'financials', 'industry'] or 'all'."
  }
  ```

***

## Screening Service Routes

### **GET `/screen/:ticker`**
- **Proxies to:** screening-service (port 3002)
- **Purpose:** Applies the 7 quantitative screening criteria to the specified ticker and returns a detailed pass/fail result.
- **Error Handling for Invalid Tickers:** Returns `502 Bad Gateway` with a descriptive error message.
- **Data Contract:** Produces [`ScreeningResultSingle`](./DATA_CONTRACTS.md#6-screeningresult).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/screen/AAPL
  ```
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

***

## Analysis Service Routes

### **GET `/analyze/:ticker`**
- **Proxies to:** analysis-service (port 3003)
- **Purpose:** Performs VCP analysis on historical data and returns a pass/fail boolean, a VCP footprint string, and detailed data for charting.
- **Query Parameters:**
  - `mode` (optional): Set to `fast` to enable fail-fast evaluation for batch processing. If omitted, defaults to `full` evaluation, which returns a detailed breakdown of all checks.
- **Error Handling:** Returns `502 Bad Gateway` if the data-service cannot find the ticker, and `503 Service Unavailable` if the data-service cannot be reached.
- **Data Contract:** Produces [`VCPAnalysisSingle`](./DATA_CONTRACTS.md#7-vcpanalysis).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/analyze/AAPL?mode=fast
  ```
- **Example Success Response (`full` mode):**
  ```json
  {
    "ticker": "AAPL",
    "vcp_pass": true,
    "vcpFootprint": "10D 8.6% | 5D 5.3%",
    "vcp_details": {
      "pivot_validation": {
        "passes": true,
        "message": "Valid pivot detected."
      },
      "volume_validation": {
        "passes": true,
        "message": "Volume dried up at pivot."
      }
    },
    "chart_data": {
      "detected": true,
      "message": "VCP analysis complete.",
      "vcpLines": [{"time": "2024-06-10", "value": 195.0}, ...],
      "vcpContractions": [
        {
          "start_date": "2024-06-10",
          "start_price": 195.0,
          "end_date": "2024-06-20",
          "end_price": 178.2,
          "depth_percent": 0.086
        }
      ],
      "pivotPrice": 196.95,
      "buyPoints": [{"value": 196.95}],
      "sellPoints": [{"value": 188.10}],
      "ma20": [{"time": "2024-07-01", "value": 192.5}, ...],
      "ma50": [{"time": "2024-07-01", "value": 190.0}, ...],
      "ma150": [{"time": "2024-07-01", "value": 185.0}, ...],
      "ma200": [{"time": "2024-07-01", "value": 180.0}, ...],
      "historicalData": [...]
    }
  }
  ```

***

## Leadership Service Routes

### **GET `/leadership/:ticker`**
- **Proxies to:** leadership-service (port 3005)
- **Purpose:** Applies the 9 leadership criteria, grouped into 3 distinct profiles, to the specified ticker.
- **Data Contract:** Produces [`LeadershipProfileSingle`](./DATA_CONTRACTS.md#8-leadershipprofile).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/leadership/AAPL
  ```
- **Example Success Response:**
  ```json
  {
    "ticker": "NVDA",
    "passes": true,
    "leadership_summary": {
      "qualified_profiles": [
        "Explosive Grower",
        "Market Favorite"
      ],
      "message": "Qualifies as a Explosive Grower, Market Favorite with supporting characteristics in other profiles."
    },
    "profile_details": {
      "explosive_grower": {
        "pass": true,
        "passed_checks": 4,
        "total_checks": 4
      },
      "high_potential_setup": {
        "pass": false,
        "passed_checks": 1,
        "total_checks": 3
      },
      "market_favorite": {
        "pass": true,
        "passed_checks": 2,
        "total_checks": 2
      }
    },
    "details": {
      "is_small_to_mid_cap": {
        "pass": false,
        "message": "Market cap $2,220,000,000,000 is outside the required range."
      },
      "is_industry_leader": {
        "pass": true,
        "message": "Passes. Ticker ranks #1 out of 15 in its industry."
      }
    },
    "industry": "Semiconductors",
    "metadata": {
      "execution_time": 0.458
    }
  }
  ```

### **GET `/leadership/industry_rank/:ticker`**
- **Proxies to:** leadership-service (port 3005)
- **Purpose:** Ranks the specified ticker against its industry peers based on revenue, market cap, and net income.
- **Data Contract:** N/A (Custom Response Structure)
- **Example Usage:**
  ```bash
  curl http://localhost:3000/leadership/industry_rank/NVDA
  ```
- **Example Success Response:**
  ```json
  {
    "ticker": "NVDA",
    "industry": "Semiconductors",
    "rank": 1,
    "total_peers_ranked": 15,
    "ranked_peers_data": [
      {
        "ticker": "NVDA",
        "revenue": 60931000000,
        "marketCap": 2220000000000,
        "netIncome": 29760000000,
        "revenue_rank": 1.0,
        "market_cap_rank": 1.0,
        "earnings_rank": 1.0,
        "combined_rank": 3
      },
      {
        "ticker": "AVGO",
        "revenue": 35824000000,
        "marketCap": 605000000000,
        "netIncome": 11500000000,
        "revenue_rank": 2.0,
        "market_cap_rank": 2.0,
        "earnings_rank": 2.0,
        "combined_rank": 6
      }
    ]
  }
  ```

***

## Monitoring Service Routes

### **GET `/monitor/market-health`**
- **Proxies to:** monitoring-service (port 3006)
- **Purpose:** Orchestrates calls to internal services to build the complete data payload for the frontend's market health page. It calls the `data-service` to get market breadth (new highs/lows) and identify leading industries.
- **Data Contract:** Produces [`MarketHealthResponse`](./DATA_CONTRACTS.md#10-markethealth).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/monitor/market-health
  ```
- **Example Success Response:**
  ```json
  {
    "market_overview": {
      "market_stage": "Bullish",
      "correction_depth_percent": -5.2,
      "high_low_ratio": 2.0,
      "new_highs": 150,
      "new_lows": 75,
      "as_of_date": "2025-11-01T12:00:00Z"
    },
    "leaders_by_industry": {
      "leading_industries": [
        {
          "industry": "Semiconductors",
          "stock_count": 2,
          "stocks": [
            {"ticker": "NVDA", "percent_change_3m": 15.5},
            {"ticker": "AVGO", "percent_change_3m": 11.2}
          ]
        },
        {
          "industry": "Software - Infrastructure",
          "stock_count": 1,
          "stocks": [
            {"ticker": "CRWD", "percent_change_3m": 12.1}
          ]
        }
      ]
    },
    "indices_analysis": {
      "^GSPC": {
        "ticker": "^GSPC",
        "vcp_pass": true,
        "vcpFootprint": "...",
        "chart_data": {...}
      }
    }
  }
  ```

### **GET `/monitor/watchlist`**
- **Proxies to:** monitoring-service (port 3006)
- **Purpose:** Retrieves all stocks from the user's watchlist, excluding any tickers currently in the portfolio (mutual exclusivity).
- **Query Parameters:**
  - `exclude` (optional): Comma-separated list of tickers to exclude (typically portfolio tickers)
    - Example: `?exclude=CRWD,NET,DDOG`
- **Data Contract:** Produces [`WatchlistListResponse`](./DATA_CONTRACTS.md#14-watchlist).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/monitor/watchlist
  curl http://localhost:3000/monitor/watchlist?exclude=CRWD,NET
  ```
- **Example Success Response:**
  ```json
  {
    "items": [
      {
        "ticker": "NVDA",
        "status": "Buy Ready",
        "date_added": "2025-09-20T10:00:00Z",
        "is_favourite": false,
        "last_refresh_status": "PASS",
        "last_refresh_at": "2025-11-01T12:00:00Z",
        "failed_stage": null,
        "current_price": 850.00,
        "pivot_price": 855.00,
        "pivot_proximity_percent": -0.58,
        "is_leader": true,
        "vol_last": 317900.0,
        "vol_50d_avg": 250000.0,
        "vol_vs_50d_ratio": 1.27,
        "day_change_pct": -0.35,
        "vcp_pass": true,
        "vcpFootprint": "10D 5.2% | 13D 5.0% | 10D 6.2%",
        "is_pivot_good": true,
        "pattern_age_days": 15,
        "has_pivot": true,
        "is_at_pivot": true,
        "has_pullback_setup": false,
        "days_since_pivot": 15,
        "fresh": true,
        "message": "Pivot is fresh (formed 15 days ago) and is not extended."
      }
    ],
    "metadata": {"count": 1}
  }
  ```
- **Example Error Response:**
  - 503 Service Unavailable
    ```json
    {"error": "Service unavailable - database connection failed"}
    ```
  - 500 Internal Server Error
    ```json
    {"error": "Invalid response format from service"}
    ```
- **Status Derivation Logic:**
  - `"Pending"`: `last_refresh_status == "PENDING"` or `UNKNOWN` (not yet analyzed).
  - `"Failed"`: `last_refresh_status == "FAIL"` (failed health check)
  - `"Buy Ready"`: `PASS` with a valid pivot, proximity within the buy band (e.g., 0% to 5%), and positive VCP/volume signals.
  - `"Buy Alert"`: `PASS` with a valid VCP base (either a maturing pivot with contraction OR a controlled pullback setup) and volume contraction.
  - `"Watch"`: `PASS` but no actionable VCP/volume setup, or stale/guardrailed pattern.
  - **Note:** Missing pivot data in rich mode defaults to "Watch" rather than "Buy Alert".

### **POST `/monitor/watchlist/batch/remove`**
- **Proxies to:** monitoring-service (port 3006)
- **Purpose:** Removes multiple tickers from the watchlist and archives them in a single batch operation.
- **Data Contract:**
  - Request: [`WatchlistBatchRemoveRequest`](./DATA_CONTRACTS.md#14-watchlist)
  - Response: [`WatchlistBatchRemoveResponse`](./DATA_CONTRACTS.md#14-watchlist)
- **Request Body:**
  ```json
  {"tickers": ["AAPL", "MSFT", "NONEXISTENT"]}
  ```
- **Example Usage:**
  ```bash
  curl -X POST http://localhost:3000/monitor/watchlist/batch/remove \
    -H "Content-Type: application/json" \
    -d '{"tickers": ["AAPL", "MSFT"]}'
  ```
- **Example Success Response:**
  ```json
  {
    "message": "Removed 2 watchlist items. Not found: 0. Sample: AAPL, MSFT",
    "removed": 2,
    "notfound": 0,
    "removed_tickers": ["AAPL", "MSFT"],
    "not_found_tickers": []
  }
  ```

### **DELETE `/monitor/watchlist/:ticker`**
- **Proxies to:** monitoring-service (port 3006)
- **Purpose:** Removes a single ticker from the watchlist and archives it with a MANUAL_DELETE reason.
- **Path Parameter:**
  - `ticker`: Stock ticker symbol to remove
- **Example Usage:**
  ```bash
  curl -X DELETE http://localhost:3000/monitor/watchlist/AAPL
  ```
- **Example Success Response:**
  ```json
  {
    "message": "Ticker AAPL removed from watchlist and archived."
  }
  ```
- **Example Error Response:**
  ```json
  {
    "error": "Ticker AAPL not found in watchlist"
  }
  ```

### **POST `/monitor/watchlist/:ticker/favourite`**
- **Proxies to:** monitoring-service (port 3006)
- **Purpose:** Toggles the favourite flag for a watchlist ticker. Favourited tickers are protected from auto-archiving.
- **Path Parameter:**
  - `ticker`: Stock ticker symbol
- **Data Contract:**
  - Request: [`WatchlistFavouriteRequest`](./DATA_CONTRACTS.md#19-watchlistfavourite)
  - Response: [`WatchlistFavouriteResponse`](./DATA_CONTRACTS.md#19-watchlistfavourite)
- **Request Body:**
  ```json
  {"is_favourite": true}
  ```
- **Example Usage:**
  ```bash
  curl -X POST http://localhost:3000/monitor/watchlist/NVDA/favourite \
    -H "Content-Type: application/json" \
    -d '{"is_favourite": true}'
  ```
- **Example Success Response:**
  ```json
  {
    "message": "Favourite status updated for NVDA"
  }
  ```

### **GET `/monitor/archive`**
- **Proxies to:** monitoring-service (port 3006)
- **Purpose:** Retrieves all archived watchlist items with their archive metadata.
- **Data Contract:** Produces [`ArchiveListResponse`](./DATA_CONTRACTS.md#14-watchlist).
- **Example Usage:**
  ```bash
  curl http://localhost:3000/monitor/archive
  ```
- **Example Success Response:**
  ```json
  {
    "archived_items": [
      {
        "ticker": "TSLA",
        "reason": "FAILED_HEALTH_CHECK",
        "archived_at": "2025-10-15T08:30:00Z",
        "failed_stage": "screening"
      },
      {
        "ticker": "AAPL",
        "reason": "MANUAL_DELETE",
        "archived_at": "2025-10-20T14:22:00Z",
        "failed_stage": null
      }
    ],
    "metadata": {"count": 2}
  }
  ```

### **DELETE `/monitor/archive/:ticker`**
- **Proxies to:** monitoring-service (port 3006)
- **Purpose:** Permanently deletes a ticker from the archived_watchlist_items collection (hard delete).
- **Path Parameter:**
  - `ticker`: Stock ticker symbol to permanently delete
- **Data Contract:** Produces [`DeleteArchiveResponse`](./DATA_CONTRACTS.md#19-deletearchive).
- **Example Usage:**
  ```bash
  curl -X DELETE http://localhost:3000/monitor/archive/AAPL
  ```
- **Example Success Response:**
  ```json
  {
    "message": "Archived ticker AAPL permanently deleted."
  }
  ```
- **Example Error Response:**
  ```json
  {
    "error": "Ticker AAPL not found in archive"
  }
  ```

***

## Scheduler Service Routes

### **POST `/jobs/screening/start`**
- **Proxies to:** scheduler-service (port 3004)
- **Purpose:** Triggers a new, full screening pipeline job. The scheduler fetches all tickers, runs them through the trend and VCP screens, and persists the final candidates and a job summary to the database.
- **Data Contract:** Produces [`ScreeningJobResult`](./DATA_CONTRACTS.md#9-screeningjobresult).
- **Example Usage:**
  ```bash
  curl -X POST http://localhost:3000/jobs/screening/start
  ```
- **Example Success Response:**
  ```json
  {
    "message": "Screening job completed successfully.",
    "job_id": "20250720-064530-AbcDE123",
    "processed_at": "2025-07-20T06:45:30.123456Z",
    "total_tickers_fetched": 8123,
    "trend_screen_survivors_count": 157,
    "vcp_survivors_count": 45,
    "final_candidates_count": 12,
    "industry_diversity": {
      "unique_industries_count": 8
    },
    "final_candidates": [
      {
        "ticker": "NVDA",
        "vcp_pass": true,
        "vcpFootprint": "10D 5.2% | 13D 5.0%",
        "leadership_results": {...}
      }
    ]
  }
  ```

### **POST `/jobs/watchlist/refresh`**
- **Proxies to:** scheduler-service (port 3004)
- **Purpose:** Triggers a new watchlist health check job. The scheduler enqueues a Celery task (`refresh_watchlist_task`) which calls monitoring-service's **internal orchestrator endpoint** `POST /monitor/internal/watchlist/refresh-status` to perform the full refresh pipeline.
- **Example Usage:**
  ```bash
  curl -X POST http://localhost:3000/jobs/watchlist/refresh
  ```
- **Example Success Response:**
  ```json
  {
    "message": "Watchlist refresh job completed",
    "job_id": "20251120-123456-AbcDE123",
    "updated_items": 32,
    "archived_items": 5,
    "failed_items": 0
  }
  ```

***

# Internal-Only APIs (Service-to-Service)

These endpoints are intended for inter-service communication within the backend architecture and are not designed for direct frontend consumption.

**Note on Direct Access:** Endpoints marked as "Served by: [service] (direct)" are NOT routable through the API Gateway. For service-to-service calls inside Docker, use the container DNS name (e.g., `http://data-service:3001`). For local development from the host machine, use `http://localhost:[port]`.

## Internal Data Service Routes

### **POST `/financials/core/batch`**
- **Served by:** data-service (direct)
- **Access:** Internal only - Reachable via gateway but intended for service-to-service use
- **Purpose:** Retrieves core financial data for a batch of tickers. Used by leadership-service for industry peer ranking.
- **Data Contract:** Success object contains key-value pairs where values adhere to [`CoreFinancials`](./DATA_CONTRACTS.md#3-corefinancials).
- **Request Body:**
  ```json
  {"tickers": ["NVDA", "AVGO", "FAKETICKER"]}
  ```
- **Example Usage (via gateway):**
  ```bash
  curl -s -X POST "http://localhost:3000/financials/core/batch" \
    -H "Content-Type: application/json" \
    -d '{"tickers":["NVDA","AVGO","FAKETICKER"]}' | jq .
  ```
- **Example Response:**
  ```json
  {
    "success": {
      "NVDA": {
        "ticker": "NVDA",
        "marketCap": 4580157423616.0,
        "sharesOutstanding": 24305000000.0,
        "floatShares": 23330430000.0,
        "industry": "Semiconductors",
        "ipoDate": "1999-01-22",
        "annual_earnings": [
          {"Revenue": 130497000000.0, "Earnings": 2.97, "Net Income": 72880000000.0}
        ],
        "quarterly_earnings": [
          {"Revenue": 57006000000.0, "Earnings": 1.31, "Net Income": 31910000000.0}
        ],
        "quarterly_financials": [
          {"Total Revenue": 57006000000.0, "Net Income": 31910000000.0}
        ]
      },
      "AVGO": {
        "ticker": "AVGO",
        "marketCap": 1669923995648.0,
        "sharesOutstanding": 4741273799.0,
        "floatShares": null,
        "industry": null,
        "ipoDate": "2009-08-06",
        "annual_earnings": [
          {"Revenue": 63887000000.0, "Earnings": 4.91, "Net Income": 23126000000.0}
        ],
        "quarterly_earnings": [
          {"Revenue": 18015000000.0, "Earnings": 1.8, "Net Income": 8518000000.0}
        ],
        "quarterly_financials": [
          {"Total Revenue": 18015000000.0, "Net Income": 8518000000.0}
        ]
      }
    },
    "failed": ["FAKETICKER"]
  }
  ```

### **GET `/industry/peers/:ticker`**
- **Served by:** data-service (direct)
- **Access:** Internal only - Reachable via gateway but intended for service-to-service use
- **Purpose:** Retrieves industry classification and a list of peer tickers. Used by the leadership-service.
- **Data Contract:** Produces [`IndustryPeers`](./DATA_CONTRACTS.md#5-industrypeers).
- **Example Usage (via gateway):**
  ```bash
  curl http://localhost:3000/industry/peers/NVDA
  ```
- **Example Success Response:**
  ```json
  {
    "industry": "Semiconductors",
    "peers": ["AVGO", "QCOM", "AMD", "INTC"]
  }
  ```

### **POST `/market-trend/calculate`**
- **Served by:** data-service (direct)
- **Access:** Internal only - NOT proxied via gateway
- **Purpose:** On-demand calculation and storage of market trends for specific dates. Internal utility endpoint.
- **Note:** This endpoint is NOT accessible via the API Gateway (service key `market-trend` not registered). Services must call data-service directly at `http://data-service:3001/market-trend/calculate` (inside Docker) or `http://localhost:3001/market-trend/calculate` (from host).
- **Request Body:**
  ```json
  {"dates": ["2025-08-26", "2025-08-25"]}
  ```
- **Example Usage (direct to data-service from host):**
  ```bash
  curl -X POST http://localhost:3001/market-trend/calculate \
    -H "Content-Type: application/json" \
    -d '{"dates": ["2025-08-26", "2025-08-25"]}'
  ```
- **Example Response:**
  ```json
  {
    "trends": [
      {
        "date": "2025-08-26",
        "trend": "Bullish",
        "pass": true,
        "details": {"^GSPC": "Bullish", "^DJI": "Bullish"}
      }
    ]
  }
  ```

### **GET `/market-trends`**
- **Served by:** data-service (direct)
- **Access:** Internal only - NOT proxied via gateway
- **Purpose:** Retrieves stored historical market trends with optional date range filtering. Used by leadership-service for historical context.
- **Note:** This endpoint is NOT accessible via the API Gateway (returns "Service not found"). Services must call data-service directly at `http://data-service:3001/market-trends` (inside Docker) or `http://localhost:3001/market-trends` (from host).
- **Query Parameters:**
  - `start_date` (optional): Start date filter (e.g., `2025-07-01`)
  - `end_date` (optional): End date filter (e.g., `2025-08-01`)
- **Example Usage (direct to data-service from host):**
  ```bash
  curl -s "http://localhost:3001/market-trends?start_date=2025-07-01&end_date=2025-08-01" | jq .
  ```
- **Example Response:**
  ```json
  [
    {"date": "2025-07-26", "trend": "Bullish"},
    {"date": "2025-07-25", "trend": "Bullish"}
  ]
  ```

### **GET `/market/sectors/industries`**
- **Served by:** data-service (direct)
- **Access:** Internal only - NOT proxied via gateway
- **Purpose:** Provides potential leader stocks grouped by industry from Yahoo Finance sectors. Primary source for monitoring-service.
- **Note:** This endpoint is NOT accessible via the API Gateway (service key `market` not registered). Services must call data-service directly at `http://data-service:3001/market/sectors/industries` (inside Docker) or `http://localhost:3001/market/sectors/industries` (from host).
- **Example Usage (direct to data-service from host):**
  ```bash
  curl http://localhost:3001/market/sectors/industries
  ```
- **Example Response:**
  ```json
  {
    "Semiconductors": ["NVDA", "AVGO", "QCOM"],
    "Software - Infrastructure": ["MSFT", "CRWD", "NET"]
  }
  ```

### **GET `/market/screener/day_gainers`**
- **Served by:** data-service (direct)
- **Access:** Internal only - NOT proxied via gateway
- **Purpose:** Fallback list of potential leaders from Yahoo Finance "Day Gainers" screener, grouped by industry.
- **Note:** This endpoint is NOT accessible via the API Gateway (service key `market` not registered). Services must call data-service directly at `http://data-service:3001/market/screener/day_gainers` (inside Docker) or `http://localhost:3001/market/screener/day_gainers` (from host).
- **Query Parameters:**
  - `limit` (optional): Maximum number of results to return (e.g., `200`)
- **Example Usage (direct to data-service from host):**
  ```bash
  curl "http://localhost:3001/market/screener/day_gainers?limit=200"
  ```
- **Example Response:**
  ```json
  {
    "Application Software": ["APP", "UIP"],
    "Internet Content & Information": ["GOOGL", "META"]
  }
  ```

### **GET `/market/screener/52w_highs`**
- **Served by:** data-service (direct)
- **Access:** Internal only - NOT proxied via gateway
- **Purpose:** Returns full quotes list for Yahoo Finance 52-week highs screener. Used by monitoring-service to derive leading industries.
- **Note:** This endpoint is NOT accessible via the API Gateway (service key `market` not registered). Services must call data-service directly at `http://data-service:3001/market/screener/52w_highs` (inside Docker) or `http://localhost:3001/market/screener/52w_highs` (from host).
- **Query Parameters:**
  - `region` (optional, default: `US`)
- **Data Contract:** [`ScreenerQuoteList`](./DATA_CONTRACTS.md#13-screenerquote)
- **Example Usage (direct to data-service from host):**
  ```bash
  curl "http://localhost:3001/market/screener/52w_highs"
  ```
- **Example Response (truncated):**
  ```json
  [
    {
      "symbol": "NVDA",
      "industry": "Semiconductors",
      "regularMarketPrice": 123.45,
      "fiftyTwoWeekHigh": 130.00,
      "marketCap": 2220000000000
    }
  ]
  ```

### **GET `/market/breadth`**
- **Served by:** data-service (direct)
- **Access:** Internal only - NOT proxied via gateway
- **Purpose:** Retrieves aggregate market breadth data (new 52-week highs/lows). Primary source for monitoring-service's market health overview.
- **Note:** This endpoint is NOT accessible via the API Gateway (service key `market` not registered). Services must call data-service directly at `http://data-service:3001/market/breadth` (inside Docker) or `http://localhost:3001/market/breadth` (from host).
- **Data Contract:** Produces [`MarketBreadthResponse`](./DATA_CONTRACTS.md#11-marketbreadth).
- **Response Format Note:** The data-service may return different key formats. Consumers should handle both variations:
  - Contract format: `{"new_highs": int, "new_lows": int, "high_low_ratio": float}`
  - Raw format: `{"newhighs": int, "newlows": int, "ratio": float}`
  - Monitoring-service normalizes the raw data-service keys to the MarketBreadthResponse contract format before returning `/monitor/market-health`.
- **Example Usage (direct to data-service from host):**
  ```bash
  curl http://localhost:3001/market/breadth
  ```
- **Example Response:**
  ```json
  {
    "new_highs": 150,
    "new_lows": 75,
    "high_low_ratio": 2.0
  }
  ```

### **POST `/data/return/batch`**
- **Served by:** data-service (direct)
- **Access:** Internal only - NOT proxied via gateway
- **Purpose:** Calculates batch percentage returns over yfinance-supported periods. Used by monitoring-service to rank industries.
- **Note:** This endpoint is NOT accessible via the API Gateway (service key `data` not registered). Services must call data-service directly at `http://data-service:3001/data/return/batch` (inside Docker) or `http://localhost:3001/data/return/batch` (from host).
- **Request Body:**
  - `tickers` (required): List of stock ticker strings
  - `period` (optional): Examples: `1mo`, `3mo`, `6mo`, `1y`, `ytd`, `max`. Default: `3mo`.
- **Example Usage (direct to data-service from host):**
  ```bash
  curl -X POST http://localhost:3001/data/return/batch \
    -H "Content-Type: application/json" \
    -d '{"tickers": ["NVDA", "AAPL", "TSLA"], "period": "3mo"}'
  ```
- **Example Response:**
  ```json
  {
    "NVDA": 15.5,
    "AAPL": 8.2,
    "FAKETICKER": null
  }
  ```

### **POST `/data/return/1m/batch`**
- **Served by:** data-service (direct)
- **Access:** Internal only - NOT proxied via gateway
- **Purpose:** Calculates batch percentage returns over a 1-month period. Specialized endpoint for monthly performance tracking.
- **Note:** This endpoint is NOT accessible via the API Gateway (service key `data` not registered). Services must call data-service directly at `http://data-service:3001/data/return/1m/batch` (inside Docker) or `http://localhost:3001/data/return/1m/batch` (from host).
- **Request Body:**
  - `tickers` (required): List of stock ticker strings
- **Example Usage (direct to data-service from host):**
  ```bash
  curl -X POST http://localhost:3001/data/return/1m/batch \
    -H "Content-Type: application/json" \
    -d '{"tickers": ["NVDA", "AAPL", "TSLA"]}'
  ```
- **Example Response:**
  ```json
  {
    "NVDA": 5.2,
    "AAPL": 3.1,
    "TSLA": -2.5
  }
  ```

### **POST `/data/watchlist-metrics/batch`**
- **Served by:** data-service (direct)
- **Access:** Internal only - NOT proxied via gateway
- **Purpose:** Computes compact price and volume summary metrics for watchlist tickers. Called exclusively by monitoring-service's refresh orchestrator.
- **Note:** This endpoint is NOT accessible via the API Gateway (service key `data` not registered). Services must call data-service directly at `http://data-service:3001/data/watchlist-metrics/batch` (inside Docker) or `http://localhost:3001/data/watchlist-metrics/batch` (from host).
- **Data Contract:**
  - Request: `{"tickers": ["HG", "INTC", ...]}`
  - Response: [`WatchlistMetricsBatchResponse`](./DATA_CONTRACTS.md#31-watchlistmetrics)
- **Description:** For each ticker, computes `current_price`, `vol_last`, `vol_50d_avg`, `day_change_pct` from recent price history (typically 3 months).
- **Request Body:**
  ```json
  {"tickers": ["HG", "INTC", "PATH"]}
  ```
- **Example Usage (direct to data-service from host):**
  ```bash
  curl -X POST http://localhost:3001/data/watchlist-metrics/batch \
    -H "Content-Type: application/json" \
    -d '{"tickers": ["HG", "INTC", "PATH"]}'
  ```
- **Example Response:**
  ```json
  {
    "metrics": {
      "HG": {
        "current_price": 18.97,
        "vol_last": 317900.0,
        "vol_50d_avg": 250000.0,
        "day_change_pct": -0.35
      },
      "PATH": {
        "current_price": null,
        "vol_last": null,
        "vol_50d_avg": null,
        "day_change_pct": null
      }
    }
  }
  ```

### **GET `/health`**
- **Served by:** data-service (direct)
- **Access:** Internal only
- **Purpose:** Health check endpoint for data-service monitoring to confirm that the service is running and responsive.
- **Data Contract:** N/A
- **Example Usage (from host):**
  ```bash
  curl http://localhost:3001/health
  ```
- **Example Success Response:**
  ```json
  {
    "mongo": true,
    "ok": true,
    "redis": true,
    "yf_pool_ready": true
  }
  ```

***

## Internal Screening Service Routes

### **POST `/screen/batch`**
- **Served by:** screening-service (direct)
- **Access:** Internal only - Reachable via gateway but intended for service-to-service use
- **Purpose:** Processes a batch of tickers and returns only those passing the 7 SEPA trend criteria. Critical component of screening pipeline called by scheduler-service.
- **Data Contract:** Produces `{"passing_tickers": TickerList}`. See [`TickerList`](./DATA_CONTRACTS.md#1-tickerlist).
- **Request Body:**
  ```json
  {"tickers": ["AAPL", "GOOGL", "TSLA"]}
  ```
- **Example Response:**
  ```json
  {"passing_tickers": ["AAPL", "GOOGL"]}
  ```

***

## Internal Analysis Service Routes

### **POST `/analyze/batch`**
- **Served by:** analysis-service (direct)
- **Access:** Internal only - Reachable via gateway but intended for service-to-service use
- **Purpose:** Analyzes a batch of tickers (typically those that have passed the trend screen) against the Volatility Contraction Pattern (VCP) criteria. This is a critical internal endpoint called by the scheduler-service to efficiently process candidates in the screening funnel.
- **Data Contract:** Produces a list of [`VCPAnalysisBatchItem`](./DATA_CONTRACTS.md#7-vcpanalysis).
- **Request Body:**
  ```json
  {
    "tickers": ["AAPL", "GOOGL", "TSLA"],
    "mode": "fast"
  }
  ```
- **Query Parameters:**
  - `mode` (optional): Set to `full` to return a detailed breakdown of all checks. If omitted, defaults to `fast` evaluation, which enables a fail-fast evaluation for batch processing.
- **Example Usage:**
  ```bash
  curl -X POST http://localhost:3000/analyze/batch \
    -H "Content-Type: application/json" \
    -d '{"tickers": ["CRWD", "NET"], "mode": "fast"}'
  ```
- **Example Success Response:**
  ```json
  [
    {
      "ticker": "CRWD",
      "vcp_pass": true,
      "vcpFootprint": "8D 6.5% | 4D 7.1% | 2D 10.1% | 4D 6.5% | 4D 6.8% | 2D 2.9% | 5D 16.6% | 8D 21.7% | 8D 16.4% | 3D 7.7% | 4D 7.4% | 1D 5.8% | 13D 10.2% | 9D 10.1% | 7D 5.0% | 4D 6.7%"
    },
    {
      "ticker": "NET",
      "vcp_pass": true,
      "vcpFootprint": "9D 6.6% | 9D 5.0% | 2D 3.0% | 26D 18.9% | 2D 6.1% | 20D 33.4% | 10D 21.3% | 7D 8.7% | 5D 4.5% | 5D 11.5% | 13D 17.4% | 4D 6.5% | 6D 4.4%"
    }
  ]
  ```

### **POST `/analyze/freshness/batch`**
- **Served by:** analysis-service (direct)
- **Access:** Internal only - Reachable via gateway but intended for service-to-service use
- **Purpose:** Checks the "freshness" of the analysis data for a list of specified tickers. This is used by the scheduler-service to determine which tickers need to be re-analyzed.
- **Data Contract:**
  - Request: [`AnalyzeFreshnessBatchRequest`](./DATA_CONTRACTS.md#17-freshness)
  - Response: List of [`AnalyzeFreshnessBatchItem`](./DATA_CONTRACTS.md#18-freshness)
- **Request Body (Example):**
  ```json
  {
    "tickers": ["AAPL", "MSFT", "GOOG"]
  }
  ```
- **Response Body (Success Example):**
  ```json
  [
    {
      "ticker": "AAPL",
      "passes_freshness_check": true,
      "vcp_detected": true,
      "days_since_pivot": 15,
      "vcpFootprint": "10D 5.2% | 13D 5.0% | 10D 6.2%",
      "message": "Pivot is fresh (formed 15 days ago) and is not extended."
    },
    {
      "ticker": "MSFT",
      "passes_freshness_check": false,
      "vcp_detected": true,
      "days_since_pivot": 120,
      "vcpFootprint": "8D 6.5% | 4D 7.1%",
      "message": "Pivot is stale (formed 120 days ago) and may be extended."
    },
    {
      "ticker": "GOOG",
      "passes_freshness_check": false,
      "vcp_detected": null,
      "days_since_pivot": null,
      "vcpFootprint": null,
      "message": "No prior analysis found in database."
    }
  ]
  ```

***

## Internal Leadership Service Routes

### **POST `/leadership/batch`**
- **Served by:** leadership-service (direct)
- **Access:** Internal only - Reachable via gateway but intended for service-to-service use
- **Purpose:** Screens a batch of tickers (typically VCP survivors) against the 9 Leadership Profile criteria. Called by scheduler-service to find top candidates.
- **Data Contract:** Produces [`LeadershipProfileBatch`](./DATA_CONTRACTS.md#8-leadershipprofile).
- **Request Body:**
  ```json
  {"tickers": ["NVDA", "CRWD"]}
  ```
- **Example Response:**
  ```json
  {
    "passing_candidates": [
      {
        "ticker": "NVDA",
        "passes": true,
        "leadership_summary": {
          "qualified_profiles": ["Explosive Grower", "Market Favorite"],
          "message": "Qualifies as a Explosive Grower, Market Favorite..."
        },
        "profile_details": {
          "explosive_grower": {
            "pass": true,
            "passed_checks": 4,
            "total_checks": 4
          }
        },
        "industry": "Semiconductors"
      }
    ],
    "unique_industries_count": 1,
    "metadata": {
      "total_processed": 2,
      "total_passed": 1,
      "execution_time": 5.123
    }
  }
  ```

### **GET `/health`**
- **Served by:** leadership-service (direct)
- **Access:** Internal only
- **Purpose:** Health check endpoint for leadership-service monitoring to confirm that the service is running and responsive.
- **Data Contract:** N/A
- **Example Usage (from host):**
  ```bash
  curl http://localhost:3005/health
  ```
- **Example Success Response:**
  ```json
  {
    "status": "healthy"
  }
  ```

***

## Internal Monitoring Service Routes

### **POST `/monitor/internal/watchlist/batch/add`**
- **Served by:** monitoring-service (direct)
- **Access:** Internal only - Reachable via gateway but intended for service-to-service use
- **Purpose:** Internal orchestrator endpoint for batch-adding tickers to the watchlist. Called by scheduler-service after screening pipeline completion.
- **Data Contract:**
  - Request: [`InternalBatchAddRequest`](./DATA_CONTRACTS.md#14-watchlist)
  - Response: [`InternalBatchAddResponse`](./DATA_CONTRACTS.md#14-watchlist)
- **Request Body:**
  ```json
  {"tickers": ["NVDA", "CRWD", "NET"]}
  ```
- **Example Response:**
  ```json
  {
    "message": "Batch add completed: added 2, skipped 1. Sample: NVDA, CRWD",
    "added": 2,
    "skipped": 1
  }
  ```

### **POST `/monitor/internal/watchlist/refresh-status`**
- **Served by:** monitoring-service (direct)
- **Access:** Internal only - Reachable via gateway but intended for service-to-service use
- **Purpose:** Internal orchestrator endpoint for refreshing watchlist item health statuses. Called by scheduler-service's Celery task to perform multi-stage health checks (screening → VCP → freshness → data metrics) and archive failed items.
- **Data Contract:** Produces [`WatchlistRefreshStatusResponse`](./DATA_CONTRACTS.md#20-watchlistrefresh).
- **Example Response:**
  ```json
  {
    "message": "Watchlist status refresh completed successfully.",
    "updated_items": 32,
    "archived_items": 5,
    "failed_items": 0
  }
  ```

***

## Notes

- **Timeout Configuration:** The API Gateway uses different timeout values for different services:
  - Jobs service (screening/watchlist refresh): 6000 seconds
  - Market health endpoint: 60 seconds
  - All other endpoints: 45 seconds

- **Error Handling:** The gateway returns standard HTTP error codes:
  - `400 Bad Request`: Malformed request or path traversal attempt
  - `404 Not Found`: Service not found in routing table
  - `502 Bad Gateway`: Error in service communication
  - `503 Service Unavailable`: Service connection failed
  - `504 Gateway Timeout`: Request exceeded timeout limit

- **CORS Configuration:** The gateway is configured to accept requests only from `http://localhost:5173` (the frontend development server).

- **Internal vs Public Endpoints:** Endpoints marked as "Internal only" are designed for inter-service communication. Those marked "Reachable via gateway but intended for service-to-service use" can technically be called through the gateway but are not meant for direct frontend consumption. Endpoints marked "NOT proxied via gateway" must be called directly at the service's port.

- **Gateway Service Key Registration:** The API Gateway only proxies requests for registered service keys: `tickers`, `price`, `news`, `financials`, `industry`, `cache`, `screen`, `analyze`, `leadership`, `monitor`, and `jobs`. Endpoints under unregistered prefixes like `/market/*`, `/data/*`, or `/market-trend/*` will return "Service not found" errors when called via the gateway and must be accessed directly at the service port.

- **Direct Access URLs:** When calling direct-access-only endpoints:
  - From inside Docker (service-to-service): Use container DNS names (e.g., `http://data-service:3001`)
  - From host machine (local development): Use localhost with mapped ports (e.g., `http://localhost:3001`)
