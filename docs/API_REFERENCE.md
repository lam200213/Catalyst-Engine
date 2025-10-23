# API Gateway Endpoints
The frontend communicates exclusively with the API Gateway, which proxies requests to the appropriate backend services.

- **GET `/tickers`** 
  - Retrieves a list of all US stock tickers from the ticker-service.  
  - **Data Contract:** Produces [`TickerList`](./DATA_CONTRACTS.md#1-tickerlist).
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/tickers
    ```

* **GET `/price/:ticker`**
  - Proxies to: `data-service`
  - Retrieves historical price data for a ticker, with caching.
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
  - Retrieves recent news articles for a ticker, with caching.
  - **Data Contract:** Produces [`NewsData`](./DATA_CONTRACTS.md#4-newsdata).
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/news/AAPL
    ```

- **POST `/price/batch`**
  - Proxies to: `data-service`
  - Retrieves historical price data for a batch of tickers. This is more efficient than making individual requests for each ticker.
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
  - Applies the 7 quantitative screening criteria to the specified ticker and returns a detailed pass/fail result.
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
  - Performs VCP analysis on historical data and returns a pass/fail boolean, a VCP footprint string, and detailed data for charting.
  - **Query Parameters**:
    - `mode` (optional): Set to `fast` to enable fail-fast evaluation for batch processing. If omitted, defaults to `full` evaluation, which returns a detailed breakdown of all checks.
  - **Error Handling**: Returns `502 Bad Gateway` if the data-service cannot find the ticker, and `503 Service Unavailable` if the data-service cannot be reached.
  - **Data Contract:** Produces [`VCPAnalysisSingle`](./DATA_CONTRACTS.md#7-vcpanalysis).

  - **Example Usage:**
    ```bash
    curl http://localhost:3000/screen/AAPL
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
  - Analyzes a batch of tickers (typically those that have passed the trend screen) against the Volatility Contraction Pattern (VCP) criteria. This is a critical internal endpoint called by the scheduler-service to efficiently process candidates in the screening funnel.
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
  - Proxies to: leadership-service
  - Purpose: A standard health check endpoint used for service monitoring to confirm that the service is running and responsive.

  - **Data Contract:** N/A
  - **Example Usage (from a monitoring tool or another service)**
      ```bash
      curl http://leadership-service:3005/health
      ```

  - **Example Success Response:**
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
              { "ticker": "NVDA", "percent_change_1m": 15.5 },
              { "ticker": "AVGO", "percent_change_1m": 11.2 }
            ]
          },
          {
            "industry": "Software - Infrastructure",
            "stocks": [
              { "ticker": "CRWD", "percent_change_1m": 12.1 }
            ]
          }
        ]
      }
    }
    ```

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

- **POST `/data/return/1m/batch`**
  - Service: `data-service`
  - Purpose: Calculates the 1-month percentage return for a batch of tickers. Used by the `monitoring-service` to efficiently gather performance data for ranking industries.
  - **Data Contract:** N/A (Custom Response: `Dict[str, float | None]`)
  - **Request Body**:
      ```json
      {
        "tickers": ["NVDA", "AAPL", "FAKETICKER"]
      }
      ```
  - **Example Usage (from another service)**:
      ```python
      import requests
      data_service_url = "http://data-service:3001"
      payload = {"tickers": ["NVDA", "AAPL", "FAKETICKER"]}
      response = requests.post(f"{data_service_url}/data/return/1m/batch", json=payload)
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
  - Purpose: Provides a list of stocks making new 52-week highs, grouped by industry. This is used by the `monitoring-service` to identify currently leading industries and stocks.
  - **Data Contract:** N/A (Custom Response: `Dict[str, List[str]]`)
  - **Example Usage (from another service)**:
      ```python
      import requests
      data_service_url = "http://data-service:3001"
      response = requests.get(f"{data_service_url}/market/screener/52w_highs")
      leading_candidates = response.json()
      ```
  - **Example Success Response**:
      ```json
      {
        "Semiconductors": ["NVDA", "AVGO"],
        "Software - Infrastructure": ["MSFT", "CRWD", "NET"]
      }
      ```

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
            "stocks": [
              { "ticker": "NVDA", "percent_change_1m": 15.5 },
              { "ticker": "AVGO", "percent_change_1m": 11.2 }
            ]
          }
        ]
      }
      ```

- **GET `/monitor/internal/health`**
  - Service: `monitoring-service`
  - Purpose: Returns a market health snapshot including market stage and correction depth. It retrieves breadth statistics (new highs/lows) by calling the `data-service`'s `/market/breadth` endpoint. This logic is consumed by the main `/monitor/market-health` endpoint.
  - **Query Parameters**: None. The `tickers` parameter is no longer used as the calculation is centralized in the data-service.
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