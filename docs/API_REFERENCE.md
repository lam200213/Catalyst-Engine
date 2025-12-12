# API Gateway Endpoints
The frontend communicates exclusively with the API Gateway, which proxies requests to the appropriate backend services.

- **GET `/tickers`** 
  - Purpose: Retrieves a list of all US stock tickers from the ticker-service.  
  - **Data Contract:** Produces [`TickerList`](./DATA_CONTRACTS.md#1-tickerlist).
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/tickers
    ```

* **GET `/price/:ticker`**
  - Proxies to: `data-service`
  - Purpose: Retrieves historical price data for a ticker, with caching.
  - **Query Parameters**:
        - `source` (optional): The data source, e.g., 'yfinance'. Defaults to 'yfinance'.
        - `period` (optional): The period of data to fetch (e.g., "1y", "6mo", "max"). Overridden by `start_date`. Defaults to "1y".
        - `start_date` (optional): The start date for fetching data in YYYY-MM-DD format. Takes precedence over `period`.
      * **Data Contract:** Produces [`PriceData`](./DATA_CONTRACTS.md#2-pricedata).
    - **Example Usage:**
      ```bash
      curl http://localhost:3000/price/AAPL?source=yfinance&period=6mo
      curl http://localhost:3000/price/AAPL?start_date=2023-01-01
      ```

* **GET `/news/:ticker`**
  - Proxies to: `data-service`
  - Purpose: Retrieves recent news articles for a ticker, with caching.
  - **Data Contract:** Produces [`NewsData`](./DATA_CONTRACTS.md#4-newsdata).
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/news/AAPL
    ```

- **POST `/price/batch`**
  - Proxies to: `data-service`
  - Purpose: Retrieves historical price data for a batch of tickers. This is more efficient than making individual requests for each ticker.
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
    - Returns two lists: `success` for tickers where data was retrieved, and `failed` for tickers that could not be processed.
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

- **POST `/cache/clear`**  
  - Proxies to: data-service
  - Purpose: Manually clears cached data from Redis. This is a developer utility to force a refresh of data from source APIs. It can clear all caches or a specific type of cache.
  - **Data Contract:** N/A
  - **Request Body (JSON, optional):**
    - Specify a `type` to clear a specific cache. If the body is omitted or `type` is `"all"`, all caches are cleared.
    - Valid types: `"price"`, `"news"`, `"financials"`, `"industry"`.
  - **Example Usage:**
      ```Bash
        curl -X POST http://localhost:3000/cache/clear
      ```
  - **Example Success Response:**
      ```JSON
      {
        "message": "All data service caches have been cleared."
      }
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
        "message": "Cleared 1542 entries from the 'price' cache.",
      }
      ```
  - **Example Error Response (Invalid Type):**
      ```json
      {
        "error": "Invalid cache type 'invalid_type'. Valid types are: ['price', 'news', 'financials', 'industry'] or 'all'."
      }
      ```

- **GET `/screen/:ticker`**
  - Proxies to the Screening Service.
  - Purpose: Applies the 7 quantitative screening criteria to the specified ticker and returns a detailed pass/fail result.
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

- **GET `/analyze/:ticker`**  
  - Proxies to the Analysis Service.  
  - Purpose: Performs VCP analysis on historical data and returns a pass/fail boolean, a VCP footprint string, and detailed data for charting.
  - **Query Parameters**:
    - `mode` (optional): Set to `fast` to enable fail-fast evaluation for batch processing. If omitted, defaults to `full` evaluation, which returns a detailed breakdown of all checks.
  - **Error Handling**: Returns `502 Bad Gateway` if the data-service cannot find the ticker, and `503 Service Unavailable` if the data-service cannot be reached.
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
          "is_pivot_good": true,
          "is_correction_deep": true,
          "is_demand_dry": true
      },
      "chart_data": {
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
        ],
        "historicalData": [...]
      }
    }
    ```

- **POST `/analyze/batch`**  
  - Proxies to the Analysis Service.  
  - Purpose: Analyzes a batch of tickers (typically those that have passed the trend screen) against the Volatility Contraction Pattern (VCP) criteria. This is a critical internal endpoint called by the scheduler-service to efficiently process candidates in the screening funnel.
  - **Data Contract:** Produces a list of [`VCPAnalysisBatchItem`](./DATA_CONTRACTS.md#7-vcpanalysis).
  - **Request Body**:
    ```json
    {
      "tickers": ["AAPL", "GOOGL", "TSLA"],
      "mode": "fast"
    }
    ```
  - **Query Parameters**:
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
        "vcp_footprint": "8D 6.5% | 4D 7.1% | 2D 10.1% | 4D 6.5% | 4D 6.8% | 2D 2.9% | 5D 16.6% | 8D 21.7% | 8D 16.4% | 3D 7.7% | 4D 7.4% | 1D 5.8% | 13D 10.2% | 9D 10.1% | 7D 5.0% | 4D 6.7%",
      },
      {
        "ticker": "NET",
        "vcp_pass": true,
        "vcp_footprint": "9D 6.6% | 9D 5.0% | 2D 3.0% | 26D 18.9% | 2D 6.1% | 20D 33.4% | 10D 21.3% | 7D 8.7% | 5D 4.5% | 5D 11.5% | 13D 17.4% | 4D 6.5% | 6D 4.4%",
      }
    ]
    ```

- **POST /analyze/freshness/batch**
  - Proxies to the Analysis Service. 
  - Purpose: Checks the "freshness" of the analysis data for a list of specified tickers. This is used by the scheduler-service to determine which tickers need to be re-analyzed.
  - **Data Contract**: 
    - Data Contract (Request): AnalysisFreshnessRequest (see shared/contracts.py)
    - Data Contract (Response): AnalysisFreshnessResponse (see shared/contracts.py)
  - **Request Body (Example)**:
  ```json
  {
    "tickers": ["AAPL", "MSFT", "GOOG"]
  }
  ```

  - **Response Body (Success Example)**:
```json
{
  "freshness_data": [
    {
      "ticker": "AAPL",
      "last_updated_utc": "2025-11-06T18:00:00Z",
      "is_fresh": true
    },
    {
      "ticker": "MSFT",
      "last_updated_utc": "2025-10-01T12:00:00Z",
      "is_fresh": false
    },
    {
      "ticker": "GOOG",
      "last_updated_utc": null,
      "is_fresh": false
    }
  ]
}
```

- **GET `/financials/core/:ticker`**  
  - Purpose: Retrieves core fundamental data required for the Leadership Profile screening. Data is cached to improve performance.
  - **Data Contract:** Produces [`CoreFinancials`](./DATA_CONTRACTS.md#3-corefinancials).
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/financials/core/AAPL
    ```
  - **Example Response (`GET /financials/core/AAPL`):**
  ```json
  {
    "ticker": "AAPL",
    "marketCap": 2800000000000,
    "sharesOutstanding": 15500000000,
    "floatShares": 15400000000,
    "ipoDate": "1980-12-12",
    "annual_earnings": [
        { "Revenue": 383285000000, "Earnings": 6.13, "Net Income": 96995000000 }
    ],
    "quarterly_earnings": [
        { "Revenue": 90753000000, "Earnings": 1.53, "Net Income": 23636000000 }
    ],
    "quarterly_financials": [
        { "Net Income": 23636000000, "Total Revenue": 90753000000 }
    ]
  }

- **GET `/leadership/<path:ticker>`**  
  - Proxies to: `leadership-service`
  - Purpose: Applies the 9 leadership criteria, grouped into 3 distinct profiles, to the specified ticker. 
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

- **GET `/industry/peers/:ticker`**
  - Proxies to: data-service
  - Purpose: Retrieves industry classification and a list of peer tickers. Used by the leadership-service.
  - **Data Contract:** Produces [`IndustryPeers`](./DATA_CONTRACTS.md#5-industrypeers).
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/industry/peers/NVDA
    ```
  - **Example Usage (from another service):**
    ```python
    import requests
    data_service_url = "http://data-service:3001"
    response = requests.get(f"{data_service_url}/industry/peers/NVDA")
    ```
  - **Example Success Response:**
    ```json
    {
      "industry": "Semiconductors",
      "peers": ["AVGO", "QCOM", "AMD", "INTC"]
    }
    ```

- **GET `/leadership/industry_rank/:ticker`**  
  - Proxies to: `leadership-service`
  - Purpose: Ranks the specified ticker against its industry peers based on revenue, market cap, and net income.
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

- **GET `/health`**  
  - Proxies to: data-service, leadership-service
  - Purpose: A standard health check endpoint used for service monitoring to confirm that the service is running and responsive.

  - **Data Contract:** N/A
  - **Example Usage (from a monitoring tool or another service)**
      ```bash
      curl http://localhost:3005/health
      ```

      ```bash
      curl http://localhost:3001/health
      ```

  - **Example Success Response for data-service:**
      ```JSON
      {
        "mongo": true,
        "ok": true,
        "redis": true,
        "yf_pool_ready": true
      }
      ```

  - **Example Success Response for leadership-service:**
      ```JSON
      {
        "status": "healthy"
      }
      ```

- **POST `/jobs/screening/start`**
  - Proxies to: `scheduler-service`
  - Purpose: Triggers a new, full screening pipeline job. The scheduler fetches all tickers, runs them through the trend and VCP screens, and persists the final candidates and a job summary to the database.
  - Purpose: Triggers a new, full screening pipeline job.
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
      "final_candidates_count": 12
    }
    ```

- **POST `/jobs/watchlist/refresh`**
  - Proxies to: `scheduler-service`
  - Purpose: Triggers a new watchlist health check job. The scheduler enqueues a Celery task (`refresh_watchlist_task`) which calls monitoring-service's **internal orchestrator endpoint** `POST /monitor/internal/watchlist/refresh-status` to perform the full refresh pipeline.
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

- **GET `/monitor/market-health`**
- Proxies to: `monitoring-service`
  - Purpose: Orchestrates calls to internal services to build the complete data payload for the frontend's market health page. It calls the `data-service` to get market breadth (new highs/lows) and identify leading industries.
  - **Data Contract**: Produces [`MarketHealthResponse`](./DATA_CONTRACTS.md#10-markethealth).
  - **Example Usage**:
    ```bash
    curl http://localhost:3000/monitor/market-health
    ```
  - **Example Success Response**:
    ```json
    {
      "market_overview": {
        "market_stage": "Bullish",
        "correction_depth_percent": -5.2,
        "high_low_ratio": 2.0,
        "new_highs": 150,
        "new_lows": 75
      },
      "leaders_by_industry": {
        "leading_industries": [
          {
            "industry": "Semiconductors",
            "stocks": [
              { "ticker": "NVDA", "percent_change_3m": 15.5 },
              { "ticker": "AVGO", "percent_change_3m": 11.2 }
            ]
          },
          {
            "industry": "Software - Infrastructure",
            "stocks": [
              { "ticker": "CRWD", "percent_change_3m": 12.1 }
            ]
          }
        ]
      }
    }
    ```

- **GET `/monitor/watchlist`**
  - Proxies to: monitoring-service
  - Purpose: Retrieves all stocks from the user's watchlist, excluding any tickers currently in the portfolio (mutual exclusivity).
  - **Query Parameters:**
    - `exclude` (optional): Comma-separated list of tickers to exclude (typically portfolio tickers)
      - Example: `?exclude=CRWD,NET,DDOG`
  - **Example Success Response:**
    - 200 OK
      ```JSON
      {
        "items": [
          {
          "ticker": "NET",
          "status": "Buy Ready",
          "date_added": "2025-09-20T10:00:00Z",
          "is_favourite": false,
          "last_refresh_status": "PASS",
          "last_refresh_at": "2025-11-01T12:00:00Z",
          "failed_stage": null,
          "current_price": 85.10,
          "pivot_price": 86.00,
          "pivot_proximity_percent": -1.05,
          "is_leader": true
          }
        ],
        "metadata": {"count": 2}
      }
      ```
  - **Example Error Response:**
    - 503 Service Unavailable
      ```json
      { "error": "Service unavailable - database connection failed" }
      ```
    - 500 Internal Server Error
      ```json
      { "error": "Invalid response format from service" }
      ```
  - **Notes**:
    - ticker: Stock symbol (uppercase)
    - status: UI status derived from last_refresh_status and pivot proximity
    - date_added: When added to watchlist (may be null until populated)
    - is_favourite: User toggle to prevent auto-archiving
    - last_refresh_status: One of PENDING | PASS | FAIL | UNKNOWN
    - last_refresh_at: Last refresh timestamp (nullable)
    - failed_stage: Stage name if FAIL occurred (nullable)
    - current_price, pivot_price, pivot_proximity_percent, is_leader: Nullable until populated by refresh jobs

  - **Status Derivation Logic:**
    - `"Pending"`: `last_refresh_status == "PENDING"` or `UNKNOWN` (not yet analyzed).
    - `"Failed"`: `last_refresh_status == "FAIL"` (failed health check)
    - `"Buy Ready"`: `PASS` with a valid pivot, proximity within the buy band (e.g., 0% to 5%), and positive VCP/volume signals.
    - `"Buy Alert"`: `PASS` with a valid VCP base (either a maturing pivot with contraction OR a controlled pullback setup) and volume contraction.
    - `"Watch"`: `PASS` but no actionable VCP/volume setup, or stale/guardrailed pattern.
    - **Note:** Missing pivot data in rich mode defaults to "Watch" rather than "Buy Alert".

  - **Field Descriptions:**
    - `ticker`: Stock symbol
    - `status`: Derived status for UI display (see logic above)
    - `date_added`: When ticker was added to watchlist
    - `is_favourite`: User-controlled flag; prevents auto-archiving
    - `last_refresh_status`: Health check result enum (PENDING, PASS, FAIL, UNKNOWN)
    - `last_refresh_at`: Timestamp of last health check
    - `failed_stage`: Stage where health check failed (screening, vcp, freshness) if status=FAIL
    - `current_price`: Latest price from refresh job (null until populated)
    - `pivot_price`: VCP pivot price if identified (null if not found)
    - `pivot_proximity_percent`: % distance from pivot (negative=below, positive=above)
    - `is_leader`: Whether stock passed leadership profile criteria

  - **Mutual Exclusivity:**
    - The endpoint automatically excludes tickers present in `exclude` query param
    - Frontend should pass portfolio tickers via this param to maintain separation

  - **Error Responses:**
    - `503 Service Unavailable`: Database connection failure
    - `500 Internal Server Error`: Pydantic validation error or unexpected failure

- **PUT `/monitor/watchlist/:ticker`** 
  - Proxies to: `monitoring-service`
  - Purpose: Adds a ticker to the user's watchlist in an idempotent manner, handling re-introduction from archive automatically.
  - **Path parameter**:
    - ticker (required): Stock symbol. Allowed characters: [A-Z0-9.-], length 1–10. Case-insensitive in request; normalized to uppercase in processing.
  - **Behavior**:
    - Validates ticker format; returns 400 on invalid input.
    - Normalizes to uppercase before processing.
    - Inserts the ticker if not present, returning 201 Created.
    - If the ticker already exists in the watchlist, returns 200 OK (idempotent).
    - If the ticker previously existed in archive, removes it from archive and adds to watchlist (re-introduction).
  - **Example Usage**:
    ```bash
    curl -X PUT http://localhost:3000/monitor/watchlist/AAPL
    ```
  - **Example Success Response:**
    - 201 Created (first insert)
      ```json
      {
        "message": "Added to watchlist: AAPL",
        "item": {
          "ticker": "AAPL",
          "status": "Watch",
          "date_added": null,
          "is_favourite": false,
          "last_refresh_status": "PENDING",
          "last_refresh_at": null,
          "failed_stage": null,
          "current_price": null,
          "pivot_price": null,
          "pivot_proximity_percent": null,
          "is_leader": false
        }
      }
      ```
    - 200 OK (idempotent re-add)
      ```json
      {
        "message": "Already in watchlist: AAPL",
        "item": {
          "ticker": "AAPL",
          "status": "Watch",
          "date_added": null,
          "is_favourite": false,
          "last_refresh_status": "PENDING",
          "last_refresh_at": null,
          "failed_stage": null,
          "current_price": null,
          "pivot_price": null,
          "pivot_proximity_percent": null,
          "is_leader": false
        }
      }
      ```
  - **Example Error Response:**
    - 400 Bad Request
      ```json
      { "error": "Invalid ticker format: <value>" }
      ```
    - 503 Service Unavailable
      ```json
      { "error": "Service unavailable - database connection failed" }
      ```
    - 500 Internal Server Error
      ```json
      { "error": "Internal server error" }
      ```
  - **Notes**:
    - Dots and hyphens are valid (e.g., BRK.B, SHOP.TO, CRWD-N). URL encoding is supported; both BRK.B and BRK%2EB are accepted.
    - Request body is ignored; only the path parameter is used.

- **DELETE `/monitor/watchlist/<ticker>`** 
  - Proxies to: `monitoring-service`
  - Purpose: Removes a ticker from the active watchlist and moves it to the archive with reason `MANUAL_DELETE`. This is the single-ticker removal endpoint; for bulk operations, use `POST /monitor/watchlist/batch/remove`.
  - **Path parameter**:
    - ticker (required): 1–10 chars, letters/digits/dot/hyphen only (no spaces). Validation is case-insensitive; processing normalizes to uppercase.
  - **Behavior**:
    - Validates ticker format; returns 400 on invalid input.
    - Normalizes to uppercase before processing.
    - Atomically removes the ticker from `watchlistitems` and inserts it into `archived_watchlist_items` with `reason: "MANUAL_DELETE"` and `failed_stage: null`.
    - Returns 404 if the ticker is not found in the active watchlist.
    - Does not leak internal DB fields (`_id`, `user_id`, `archived_at`) in the response.
  - **Example Usage**:
    ```bash
    curl -X DELETE http://localhost:3000/monitor/watchlist/AAPL
    ```
  - **Example Success Response:**
    - 200 OK — application/json 
      ```json
      { "message": "AAPL moved to archive" }
      ```
  - **Example Error Response:**
    - 400 Bad Request — application/json — ApiError
      ```json
      { "error": "Invalid ticker format" }
      ```
    - 404 Not Found — application/json — ApiError
      ```json
      { "error": "Ticker not found" }
      ```
    - 503 Service Unavailable
      ```json
      { "error": "Service unavailable - database connection failed" }
      ```
  - **Notes**:
    - Dots and hyphens are valid (e.g., `BRK.B`, `SHOP.TO`, `CRWD-N`). URL encoding is supported; both `BRK.B` and `BRK%2EB` are accepted.
    - The archived item can be permanently deleted using `DELETE /monitor/archive/<ticker>`.
    - User scope is enforced internally via `DEFAULT_USER_ID` (single-user mode).
    - For batch removal (e.g., "Remove Selected" UI action), use `POST /monitor/watchlist/batch/remove` instead.
    
- **DELETE `/monitor/archive/:ticker`** 
  - Proxies to: `monitoring-service`
  - Purpose: Deletes an archived ticker permanently for the default user.
  - **Path parameter**:
    - ticker (required): 1–10 chars, letters/digits/dot/hyphen only (no spaces). Validation is case-insensitive; processing normalizes to uppercase.
  - **Example Usage**:
    ```bash
    curl -X DELETE http://localhost:3000/monitor/archive/BRK.B
    ```
  - **Example Success Response:**
    - 200 OK — application/json — DeleteArchiveResponse
      ```json
      { "message": "Archived ticker AAPL permanently deleted." }
      ```
  - **Example Error Response:**
    - 400 Bad Request — application/json — ApiError
      ```json
      { "error": "Invalid ticker format" }
      ```
    - 404 Not Found — application/json — ApiError
      ```json
      { "error": "Ticker not found" }
      ```
    - 503 Service Unavailable
      ```json
      { "error": "Service unavailable" }
      ```
  - **Notes**:
    - Hard delete is immediate and does not depend on collection TTL indices.
    - User scope is enforced internally; the operation deletes at most one document for DEFAULT_USER_ID and the specified ticker.

- **POST `/monitor/watchlist/:ticker/favourite`**
  - Proxies to: `monitoring-service`
  - Purpose: Toggles the `is_favourite` flag for a single watchlist item belonging to the default single-user.
  - Path parameter:
    - `ticker` (required): Stock symbol. Allowed characters: A-Z0-9.-, length 1-10. Case-insensitive in request; normalized to uppercase in processing.
  - Request Body (required): JSON
    ```
    { "is_favourite": true }
    ```
    - `is_favourite` (required): Boolean. Must be strictly `true` or `false` (no coercion from strings or numbers).
  - **Data Contract:** Consumes [`WatchlistFavouriteRequest`](./DATA_CONTRACTS.md#19-watchlistfavouriterequest), Produces [`WatchlistFavouriteResponse`](./DATA_CONTRACTS.md#19-watchlistfavouriteresponse).
  - Example Usage:
    ```bash
    curl -X POST http://localhost:3000/monitor/watchlist/AAPL/favourite \
      -H "Content-Type: application/json" \
      -d '{"is_favourite": true}'
    ```
  - Example Success Response:
    - **200 OK** (application/json) `WatchlistFavouriteResponse`
      ```
      { "message": "Watchlist item 'AAPL' favourite set to true" }
      ```
  - Example Error Responses:
    - **400 Bad Request** (application/json) `ApiError`
      ```json
      { "error": "Field 'is_favourite' must be a boolean" }
      ```
      ```json
      { "error": "Invalid ticker format" }
      ```
    - **404 Not Found** (application/json) `ApiError`
      ```json
      { "error": "Watchlist item 'ZZZZZ' not found" }
      ```
    - **503 Service Unavailable** (application/json) `ApiError`
      ```json
      { "error": "Database unavailable" }
      ```
  - Notes:
    - URL encoding is supported (e.g., `BRK%2EB` for `BRK.B`).
    - The route ignores any `X-User-Id` headers and operates under single-user mode.
    - Internal fields (`_id`, `user_id`, `archived_at`, `reason`, `failed_stage`) are never exposed in the response.

- **POST `/monitor/watchlist/batch/remove`**
  - Proxies to: `monitoring-service`
  - Purpose: Removes multiple tickers from the user's watchlist in a single batch operation. Removed items are automatically archived with reason `MANUAL_DELETE`. This endpoint backs the "Remove Selected" UI action.
  - **Request Body (JSON)**:
    - `tickers` (required): A list of stock ticker symbols to remove. Maximum 1000 tickers per request.
  - **Data Contract:**
    - Request: [`WatchlistBatchRemoveRequest`](./DATA_CONTRACTS.md#14-watchlistbatchremoverequest)
    - Response: [`WatchlistBatchRemoveResponse`](./DATA_CONTRACTS.md#15-watchlistbatchremoveresponse)
  - **Example Usage**:
    ```bash
    curl -X POST http://localhost:3000/monitor/watchlist/batch/remove \
      -H "Content-Type: application/json" \
      -d '{"tickers": ["AAPL", "MSFT", "GOOGL"]}'
    ```
  - **Example Success Response**:
    - 200 OK
      ```json
      {
        "message": "Successfully removed 3 tickers from the watchlist (not found: 0): AAPL, MSFT, GOOGL",
        "removed": 3,
        "notfound": 0
      }
      ```
  - **Example Error Response**:
    - 400 Bad Request
      ```json
      { "error": "Invalid request payload for batch remove" }
      ```
    - 400 Bad Request (over limit)
      ```json
      { "error": "Cannot remove more than 1000 tickers in a single request" }
      ```
    - 503 Service Unavailable
      ```json
      { "error": "Service unavailable - database connection failed" }
      ```
  - **Notes**:
    - Tickers are normalized to uppercase before processing.
    - Duplicate tickers in the request are handled idempotently.
    - Items not found in the watchlist are reported in the `notfound` count but do not cause an error.
    - All successfully removed items are moved to `archived_watchlist_items` with `reason: "MANUAL_DELETE"`.
    - User scope is enforced internally via `DEFAULT_USER_ID`.

# Internal Service Communication

## `scheduler-service` -> `analysis-service`

For efficient batch processing, the **`scheduler-service`** calls the **`analysis-service`** using the `?mode=fast` query parameter. This instructs the `analysis-service` to perform a "fail-fast" evaluation, immediately stopping and returning a fail status for a ticker that does not meet a VCP criterion, thus conserving system resources.

## Internal Data Service Endpoints
- The following endpoints are used for internal service-to-service communication and are not exposed through the public API Gateway. They are documented here for completeness.

- **POST `/financials/core/batch`**  
  - Proxies to: data-service
  - Purpose: Retrieves core financial data for a batch of tickers. This is used by the leadership-service to efficiently gather the necessary data for its industry peer ranking analysis.

  - **Data Contract:** The `success` object contains key-value pairs where each value adheres to the [`CoreFinancials`](./DATA_CONTRACTS.md#3-corefinancials) contract.
  - **Request Body:**
      ```JSON
      {
        "tickers": ["NVDA", "AVGO", "FAKETICKER"]
      }
      ```

  - **Example Usage (from another service)**
      ```PYTHON
      import requests

      data_service_url = "http://data-service:3001"
      payload = {"tickers": ["NVDA", "AVGO", "FAKETICKER"]}
      response = requests.post(f"{data_service_url}/financials/core/batch", json=payload)
      ```

  - **Example Success Response:**
      ```JSON
      {
        "success": {
          "NVDA": {
            "marketCap": 2220000000000,
            "sharesOutstanding": 2460000000,
            "ipoDate": "1999-01-22"
          },
          "AVGO": {
            "marketCap": 605000000000,
            "sharesOutstanding": 463000000,
            "ipoDate": "2009-08-06"
          }
        },
        "failed": ["FAKETICKER"]
      }
      ```

- **POST `/market-trend/calculate`**  
  - Proxies to: data-service
  - Purpose: On-demand endpoint to calculate, store, and return market trends for a specific list of dates. This is an internal utility endpoint.
  - **Data Contract:** N/A (Custom Response Structure)
  - **Request Body:**
      ```JSON
      {
        "dates": ["2025-08-26", "2025-08-25"]
      }
      ```

  - **Example Usage (from another service)**
      ```PYTHON
        import requests

        data_service_url = "http://data-service:3001"
        payload = {"dates": ["2025-08-26"]}
        response = requests.post(f"{data_service_url}/market-trend/calculate", json=payload)
      ```

  - **Example Success Response:**
      ```JSON
      {
        "trends": [
          {
            "date": "2025-08-26",
            "trend": "Bullish",
            "pass": true,
            "details": {
              "^GSPC": "Bullish",
              "^DJI": "Bullish",
              "^IXIC": "Bullish"
            },
            "createdAt": "..."
          }
        ]
      }
      ```

- **POST `/data/watchlist-metrics/batch`**  
  - Service: `data-service`
  - Purpose: Computes compact price and volume summary metrics for a batch of tickers to support watchlist status refresh. This is an internal endpoint called exclusively by monitoring-service's refresh orchestrator.
  - **Access:** Internal only (not exposed via api-gateway)
  - **Data Contract:** 
    - Request: `{"tickers": ["HG", "INTC", ...]}`
    - Response: Produces [`WatchlistMetricsBatchResponse`](./DATA_CONTRACTS.md#31-watchlistmetrics)
  - **Description:**  
    For each requested ticker, data-service fetches recent price history (typically 3 months) and computes four summary metrics:
    - `current_price`: Most recent close price
    - `vol_last`: Most recent session's volume
    - `vol_50d_avg`: Average volume over the last 50 trading sessions
    - `day_change_pct`: Daily percentage change from previous close
    
    These metrics enable the monitoring-service orchestrator to derive `vol_vs_50d_ratio` and apply volume-based status logic without transferring full OHLCV time series. Tickers with insufficient or unavailable data return all-null metrics rather than being excluded.
  
  - **Request Body:**
      ```
      {
        "tickers": ["HG", "INTC", "PATH"]
      }
      ```

  - **Example Usage (from monitoring-service)**
      ```
      import requests

      data_service_url = "http://data-service:3001"
      payload = {"tickers": ["HG", "INTC", "PATH"]}
      response = requests.post(f"{data_service_url}/data/watchlist-metrics/batch", json=payload)
      ```

  - **Example Success Response:**
      ```
      {
        "metrics": {
          "HG": {
            "current_price": 18.97,
            "vol_last": 317900.0,
            "vol_50d_avg": 250000.0,
            "day_change_pct": -0.35
          },
          "INTC": {
            "current_price": 23.45,
            "vol_last": 42100000.0,
            "vol_50d_avg": 38500000.0,
            "day_change_pct": 1.2
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

  - **Error Responses:**
    - `400 Bad Request`: Invalid request payload (missing or malformed `tickers` array)
      ```
      { "error": "Invalid request. 'tickers' array is required." }
      ```
    - `502 Bad Gateway`: Failed to fetch price history from provider
      ```
      { "error": "Failed to fetch price history for watchlist metrics" }
      ```
    - `500 Internal Server Error`: Unexpected failure during metric computation
      ```
      { "error": "Failed to compute watchlist metrics" }
      ```

  - **Notes:**
    - This endpoint is designed specifically for watchlist refresh and should not be confused with `/data/return/batch`, which returns simple percentage returns for the market-health page.
    - Metrics are computed on-demand from recent price history; no additional caching beyond existing price cache is used.
    - The endpoint validates price data against the `PriceDataItem` contract before computing metrics to ensure data integrity.

- **GET `/market-trends`**  
  - Proxies to: data-service
  - Purpose: Retrieves stored historical market trends. Can be filtered by a date range. Used by the leadership-service to provide historical context for its analysis.
  - Query Parameters:
    - start_date (optional): The start date for the filter (e.g., 2025-07-01).
    - end_date (optional): The end date for the filter (e.g., 2025-08-01).
  - **Data Contract:** N/A (Custom Response Structure)
  - **Example Usage (from another service)**
      ```PYTHON
      {
        import requests

        data_service_url = "http://data-service:3001"
        # Get all trends
        response = requests.get(f"{data_service_url}/market-trends")
        trends = response.json()

        # Get trends for a specific range
        response_filtered = requests.get(f"{data_service_url}/market-trends?start_date=2025-07-01&end_date=2025-07-31")
        trends_filtered = response_filtered.json()
      }
      ```

  - **Example Success Response:**
      ```JSON
      [
        {
          "date": "2025-07-26",
          "status": "Bullish"
        },
        {
          "date": "2025-07-25",
          "status": "Bullish"
        }
      ]
      ```

- **POST `/screen/batch`**  
  - Proxies to: screening-service
  - Purpose: Processes a list of tickers and returns only those that pass the 8 foundational SEPA trend criteria. It's a critical component of the main screening pipeline, called by the scheduler-service.
  - **Data Contract:** Produces `{"passing_tickers": TickerList}`. See [`TickerList`](./DATA_CONTRACTS.md#1-tickerlist).
  - **Request Body:**
      ```JSON
      {
        "tickers": ["AAPL", "GOOGL", "TSLA"]
      }
      ```

  - **Example Usage (from another service)**
      ```PYTHON
      import requests

      screening_service_url = "http://screening-service:3002"
      payload = {"tickers": ["AAPL", "GOOGL", "TSLA"]}
      response = requests.post(f"{screening_service_url}/screen/batch", json=payload)
      ```

  - **Example Success Response:**
      ```JSON
      {
        "passing_tickers": ["AAPL", "GOOGL"]
      }
      ```

- **POST `/leadership/batch`**  
  - Proxies to: leadership-service
  - Purpose: Screens a batch of tickers (typically those that have passed the trend and VCP screens) against the 10 "Leadership Profile" criteria. Called by the scheduler-service to efficiently find the top candidates.
  - **Data Contract:** Produces [`LeadershipProfileBatch`](./DATA_CONTRACTS.md#8-leadershipprofile).
  - **Request Body:**
      ```JSON
      {
        "tickers": ["AAPL", "GOOGL", "TSLA"]
      }
      ```

  - **Example Usage (from another service)**
      ```PYTHON
      import requests

      leadership_service_url = "http://leadership-service:3005"
      payload = {"tickers": ["AAPL", "GOOGL", "TSLA"]}
      response = requests.post(f"{leadership_service_url}/leadership/batch", json=payload)
      ```

  - **Example Success Response:**
      ```JSON
      {
        "tickers": ["NVDA", "AAPL", "TSLA"]
      }
      ```
  - **Example Usage (from another service)**
      ```PYTHON
      import requests

      leadership_service_url = "http://leadership-service:3005"
      payload = {"tickers": ["NVDA", "CRWD"]}
      response = requests.post(f"{leadership_service_url}/leadership/batch", json=payload)
      ```
  - **Example Success Response:**
      ```JSON
      {
          "passing_candidates": [
              {
                  "ticker": "NVDA",
                  "passes": true,
                  "leadership_summary": {
                      "qualified_profiles": ["Explosive Grower", "Market Favorite"],
                      "message": "Qualifies as a Explosive Grower, Market Favorite with supporting characteristics in other profiles."
                  },
                  "profile_details": {
                      "explosive_grower": { "pass": true, "passed_checks": 4, "total_checks": 4 },
                      "high_potential_setup": { "pass": false, "passed_checks": 1, "total_checks": 3 },
                      "market_favorite": { "pass": true, "passed_checks": 2, "total_checks": 2 }
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
- **GET `/market/sectors/industries`**
  - Service: `data-service`
  - Purpose: Provides a list of potential leader stocks, grouped by industry, sourced from Yahoo Finance sectors. This is a primary data source for the `monitoring-service`.
  - **Data Contract:** N/A (Custom Response: `Dict[str, List[str]]`)
  - **Example Usage (from another service)**:
      ```python
      import requests
      data_service_url = "http://data-service:3001"
      response = requests.get(f"{data_service_url}/market/sectors/industries")
      industry_candidates = response.json()
      ```
  - **Example Success Response**:
      ```json
      {
        "Semiconductors": ["NVDA", "AVGO", "QCOM", "AMD", "INTC"],
        "Software - Infrastructure": ["MSFT", "CRWD", "NET", "SNOW"]
      }
      ```

- **GET `/market/screener/day_gainers`**
  - Service: `data-service`
  - Purpose: Provides a fallback list of potential leader stocks, grouped by industry, sourced from the Yahoo Finance "Day Gainers" screener.
  - **Data Contract:** N/A (Custom Response: `Dict[str, List[str]]`)
  - **Example Usage (from another service)**:
      ```python
      import requests
      data_service_url = "http://data-service:3001"
      response = requests.get(f"{data_service_url}/market/screener/day_gainers")
      gainer_candidates = response.json()
      ```
  - **Example Success Response**:
      ```json
      {
        "Application Software": ["APP", "UIP"],
        "Internet Content & Information": ["GOOGL", "META"]
      }
      ```

- **POST `/data/return/batch`**
  - Service: `data-service`
  - Purpose: Batch percent returns over any yfinance-supported period. Used by the `monitoring-service` to efficiently gather performance data for ranking industries. 
  - **Data Contract:** N/A (Custom Response: `Dict[str, float | None]`)
  - **Request Body (JSON):**
      - `tickers` (required): A list of stock ticker strings.
      - `period` (optional): Allowed examples: "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max". If period is omitted, default is 3mo to emphasize medium-term leadership.
  - **Example Usage (from another service)**:
      ```python
      import requests
      data_service_url = "http://data-service:3001"
      payload = {"tickers": ["NVDA", "AAPL", "FAKETICKER"], "period": period}
      response = requests.post(f"{data_service_url}/data/return/batch", json=payload)
      returns = response.json()
      ```
  - **Example Success Response**:
      ```json
      {
        "NVDA": 15.5,
        "AAPL": 8.2,
        "FAKETICKER": null
      }
      ```

- **GET `/market/breadth`**
  - Service: `data-service`
  - Purpose: Retrieves aggregate market breadth data, specifically the total number of new 52-week highs and lows for a major exchange. This is the primary source for the `monitoring-service`'s market health overview.
  - **Data Contract:** Produces [`MarketBreadthResponse`](./DATA_CONTRACTS.md#11-marketbreadth).
  - **Example Usage (from another service)**:
      ```python
      import requests
      data_service_url = "http://data-service:3001"
      response = requests.get(f"{data_service_url}/market/breadth")
      breadth_data = response.json()
      ```
  - **Example Success Response**:
      ```json
      {
        "new_highs": 150,
        "new_lows": 75,
        "high_low_ratio": 2.0
      }
      ```

- **GET `/market/screener/52w_highs`**
  - Service: `data-service`
  - Purpose: Returns the full quotes list for the Yahoo Finance 52-week highs screener (US by default), used by monitoring-service to derive leading industries and breadth.
  - **Query Parameters**: region (optional, default: US)
  - **Data Contract:** [`ScreenerQuoteList`](./DATA_CONTRACTS.md#13-ScreenerQuote).
    - symbol: string
    - industry: string | null
    - shortName: string | null
    - sector: string | null
    - regularMarketPrice: number | null
    - fiftyTwoWeekHigh: number | null
    - fiftyTwoWeekHighChangePercent: number | null
    - marketCap: number | null
  - **Example Usage (from another service)**:
      ```python
      import requests
      data_service_url = "http://data-service:3001"
      response = requests.get(f"{data_service_url}/market/screener/52w_highs")
      leading_candidates = response.json()
      ```
  - **Example Success Response (truncated)**:
      ```json
      [
        {
          "symbol": "NVDA",
          "industry": "Semiconductors",
          "shortName": "NVIDIA Corporation",
          "sector": "Technology",
          "regularMarketPrice": 123.45,
          "fiftyTwoWeekHigh": 130.00,
          "fiftyTwoWeekHighChangePercent": -0.05,
          "marketCap": 2220000000000
        },
        {
          "symbol": "MSFT",
          "industry": "Software - Infrastructure",
          "shortName": "Microsoft Corporation",
          "sector": "Technology",
          "regularMarketPrice": 410.10,
          "fiftyTwoWeekHigh": 415.00,
          "fiftyTwoWeekHighChangePercent": -0.012,
          "marketCap": 3100000000000
        }
      ]
      ```
  - **Notes**:
    - The list is already filtered for US tickers when region=US.
    - Only the listed fields are returned to minimize payload and avoid leaking upstream fields.

- **GET `/monitor/internal/leaders`**
  - Service: `monitoring-service`
  - Purpose: Provides a ranked list of leading stocks grouped by industry, 52-week highs breadth; falls back to avg 1M returns if screener unavailable. This logic is consumed by the main `/monitor/market-health` endpoint.
  - **Data Contract**: Produces [`MarketLeaders`](./DATA_CONTRACTS.md#10-markethealth).
  - **Example Usage (from within the monitoring service)**:
      ```python
      # This is called internally, not a direct HTTP request from outside.
      from market_leaders import get_market_leaders
      leaders_data = get_market_leaders()
      ```
  - **Example Success Response**:
      ```json
      {
        "leading_industries": [
          {
            "industry": "Semiconductors",
            "stock_count": 12,
            "stocks": [
              { "ticker": "NVDA", "percent_change_3m": 15.5 },
              { "ticker": "AVGO", "percent_change_3m": 11.2 }
            ]
          }
        ]
      }
      ```

- **GET `/monitor/internal/health`**
  - Service: `monitoring-service`
  - Purpose: Returns a market health snapshot including market stage and correction depth. It retrieves breadth statistics (new highs/lows) by calling the `data-service`'s `/market/breadth` endpoint. This logic is consumed by the main `/monitor/market-health` endpoint.
  - **Query Parameters**: None. 
  - **Data Contract**: Produces [`MarketOverview`](./DATA_CONTRACTS.md#10-markethealth).
  - **Example Usage (from within the monitoring service)**:
      ```python
      # This is called internally, not a direct HTTP request from outside.
      from market_health_utils import get_market_health
      health_data = get_market_health()
      ```
  - **Example Success Response**:
      ```json
      {
        "market_stage": "Bullish",
        "correction_depth_percent": -5.2,
        "high_low_ratio": 2.0,
        "new_highs": 150,
        "new_lows": 75
      }
      ```

- **POST `/monitor/internal/watchlist/batch/add`**
  - Service: `monitoring-service`
  - Purpose: Adds multiple tickers to the watchlist in a single batch operation. Designed for internal automation and bulk import workflows. Normalizes tickers to uppercase, deduplicates, and handles re-introduction from archive automatically.
  - **Request Body (JSON)**:
    - `tickers` (required): A list of stock ticker symbols to add.
  - **Data Contract:**
    - Request: [`InternalBatchAddRequest`](./DATA_CONTRACTS.md#23-internalbatchaddrequest)
    - Response: [`InternalBatchAddResponse`](./DATA_CONTRACTS.md#24-internalbatchaddresponse)
  - **Example Usage**:
    ```bash
    curl -X POST http://monitoring-service:3006/monitor/internal/watchlist/batch/add \
      -H "Content-Type: application/json" \
      -d '{"tickers": ["AAPL", "MSFT", "GOOGL"]}'
    ```
  - **Example Success Response**:
    - 201 Created (when at least one ticker newly added)
      ```json
      {
        "message": "Batch add completed: added 3, skipped 0. Sample: AAPL, MSFT, GOOGL",
        "added": 3,
        "skipped": 0
      }
      ```
    - 200 OK (when all tickers already existed)
      ```json
      {
        "message": "Batch add completed: added 0, skipped 3. Sample: AAPL, MSFT, GOOGL",
        "added": 0,
        "skipped": 3
      }
      ```
  - **Example Error Response**:
    - 400 Bad Request
      ```json
      { "error": "Invalid request body for internal batch add" }
      ```
    - 400 Bad Request (validation failure)
      ```json
      { "error": "Invalid ticker format in tickers array" }
      ```
    - 503 Service Unavailable
      ```json
      { "error": "Service unavailable - database connection failed" }
      ```
  - **Notes**:
    - Tickers are normalized to uppercase and deduplicated before processing.
    - Items previously in `archived_watchlist_items` are automatically removed from archive and added to the active watchlist.
    - All successfully added items are initialized with `is_favourite: false` and `last_refresh_status: "PENDING"`.
    - User scope is enforced internally via `DEFAULT_USER_ID`.
    - This endpoint is internal-only and not exposed through the api-gateway.

- **POST `/monitor/watchlist/batch/remove`**
  - Service: `monitoring-service`
  - **Purpose**: Public endpoint to remove multiple tickers from the active watchlist.
  - **Response (200 OK):**
  ```json
  {
    "message": "Removed 1 watchlist item. Not found: 0. Sample: AAPL",
    "removed": 1,
    "notfound": 0,
    "removed_tickers": ["AAPL"],
    "not_found_tickers": []
  }
  ```

  - **Field Descriptions:**
  - `removed`: Count of tickers successfully removed
  - `notfound`: Count of requested tickers not found in watchlist
  - `removed_tickers`: List of specific tickers that were removed (for UI detail)
  - `not_found_tickers`: List of specific tickers that were requested but not present

  - **Use Case:**
  Frontend can display both summary counts and detailed per-ticker feedback (e.g., "Removed: AAPL. Not found: MSFT, TSLA").

- **POST `/monitor/watchlist/batch/add`**
  - Service: `monitoring-service`
  - Purpose: Public endpoint to add multiple tickers to the watchlist in a single batch operation. Useful for "Add All" features (e.g., adding all market leaders).
  - **Request Body (JSON)**:
    - `tickers` (required): A list of stock ticker symbols to add.
  - **Data Contract:**
    - Request: [`InternalBatchAddRequest`](./DATA_CONTRACTS.md#23-internalbatchaddrequest)
    - Response: [`InternalBatchAddResponse`](./DATA_CONTRACTS.md#24-internalbatchaddresponse)
  - **Example Usage**:
    ```bash
    curl -X POST http://monitoring-service:3006/monitor/watchlist/batch/add \
      -H "Content-Type: application/json" \
      -d '{"tickers": ["AAPL", "MSFT", "GOOGL"]}'
    ```
  - **Example Success Response**:
    - 201 Created (when at least one ticker newly added)
      ```json
      {
        "message": "Batch add completed: added 3, skipped 0. Sample: AAPL, MSFT, GOOGL",
        "added": 3,
        "skipped": 0
      }
      ```
    - 200 OK (when all tickers already existed)
      ```json
      {
        "message": "Batch add completed: added 0, skipped 3. Sample: AAPL, MSFT, GOOGL",
        "added": 0,
        "skipped": 3
      }
      ```
  - **Example Error Response**:
    - 400 Bad Request
      ```json
      { "error": "Invalid request body for internal batch add" }
      ```
    - 400 Bad Request (validation failure)
      ```json
      { "error": "Invalid ticker format in tickers array" }
      ```
    - 503 Service Unavailable
      ```json
      { "error": "Service unavailable - database connection failed" }
      ```
  - **Notes**:
    - Tickers are normalized to uppercase and deduplicated before processing.
    - Items previously in `archived_watchlist_items` are automatically removed from archive and added to the active watchlist.
    - All successfully added items are initialized with `is_favourite: false` and `last_refresh_status: "PENDING"`.
    - User scope is enforced internally via `DEFAULT_USER_ID`.

- **POST `/monitor/internal/watchlist/refresh-status`**
  - Service: monitoring-service
  - **Purpose:** Primary internal orchestrator to run the full watchlist refresh pipeline (screen, VCP, freshness, data enrichment, status derivation) and persist updated statuses and archives. Supersedes the deprecated batch update endpoints.
  - **Access:** Internal only (called by scheduler-service refresh_watchlist_task).
  - **Data Contract:** Produces [`WatchlistRefreshStatusResponse`](./DATA_CONTRACTS.md#29-watchlistrefreshstatusresponse)
  - **Description:**  
    This endpoint encapsulates the full watchlist health-check orchestration:
    1. Loads active watchlist items from MongoDB
    2. Calls screening-service (`POST /screen/batch`), analysis-service (`POST /analyze/batch`, `POST /analyze/freshness/batch`), and **data-service (`POST /data/watchlist-metrics/batch`)** to gather screening, VCP, freshness, and price/volume signals
    3. Computes `last_refresh_status` (PENDING, PASS, FAIL, UNKNOWN) and `failed_stage` for each ticker based on the funnel logic
    4. Enriches items with VCP, freshness, and data-service metrics, then derives final watchlist UI status (Buy Ready, Watch, etc.)
    5. Partitions items into Update List (PASS or Favourite) and Archive List (FAIL and Not Favourite)
    6. Performs bulk updates (List A: active items) and bulk archiving (List B: failed health checks with `ArchiveReason.FAILED_HEALTH_CHECK`)
    7. Returns aggregate counts (`updated_items`, `archived_items`, `failed_items`)
  - **Example Usage (internal):**
    ```
    curl -X POST http://monitoring-service:3006/monitor/internal/watchlist/refresh-status
    ```
  - **Request Body:** None (single-user mode).
  - **Response (200 OK):**
  ```json
  {
    "message": "Watchlist status refresh completed successfully.",
    "updated_items": 32,
    "archived_items": 5,
    "failed_items": 0
  }
  ```
  - **Response Fields:**
    - `message` (string): Human-readable summary of the refresh operation.
    - `updated_items` (integer): Count of active watchlist items whose status was updated.
    - `archived_items` (integer): Count of items archived due to failed health checks.
    - `failed_items` (integer): Count of items that could not be processed due to non-fatal downstream errors.
  - **Error Responses:**
    - `500 Internal Server Error` with `ApiError` if orchestrator fails.
    - `503 Service Unavailable` for database connectivity issues.
  - **Scheduler Integration:** The scheduler-service's `POST /jobs/watchlist/refresh` endpoint triggers a Celery task that calls this internal route and persists the summary response in the job metadata.
  - **Scheduler Integration:** The scheduler-service's `POST /jobs/watchlist/refresh` endpoint triggers a Celery task that calls this internal route and persists the summary response in the job metadata.  
  - **Notes:**
    - Prior to this change, the orchestrator called `/data/return/batch`, which returns simple percentage returns unsuitable for volume-based status logic. The new `/data/watchlist-metrics/batch` endpoint provides the necessary `current_price`, `vol_last`, `vol_50d_avg`, and `day_change_pct` metrics.
    - The orchestrator computes `vol_vs_50d_ratio` (vol_last / vol_50d_avg) from these metrics and uses it in status derivation rules like volume contraction thresholds.