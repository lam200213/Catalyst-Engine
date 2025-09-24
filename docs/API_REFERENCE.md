# API Gateway Endpoints
The frontend communicates exclusively with the API Gateway, which proxies requests to the appropriate backend services.

- **GET `/tickers`** 
  - Retrieves a list of all US stock tickers from the ticker-service.  
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/tickers
    ```

* **GET `/price/:ticker`**
    * Proxies to: `data-service`
    * Retrieves historical price data for a ticker, with caching.
    * **Note:** The `source` parameter is handled by the `data-service` directly, not the gateway.
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/price/AAPL?source=yfinance
    ```

* **GET `/news/:ticker`**
    * Proxies to: `data-service`
    * Retrieves recent news articles for a ticker, with caching.
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/news/AAPL
    ```

- **POST `/price/batch`**
  - Proxies to: `data-service`
  - Retrieves historical price data for a batch of tickers. This is more efficient than making individual requests for each ticker.
  - **Example Usage:**
    ```bash
    curl -X POST http://localhost:3000/price/batch \
      -H "Content-Type: application/json" \
      -d '{"tickers": ["AAPL", "GOOGL", "MSFT", "FAKETICKER"], "source": "yfinance"}'
    ```
  - **Response Body (JSON):**
    - Returns two lists: `success` for tickers where data was retrieved, and `failed` for tickers that could not be processed.
    ```json
    {
      "success": [
        {"ticker": "AAPL", "data": [...]},
        {"ticker": "GOOGL", "data": [...]},
        {"ticker": "MSFT", "data": [...]}
      ],
      "failed": ["FAKETICKER"]
    }
    ```

- **POST `/cache/clear`**  
  - Proxies to: data-service
  - Purpose: Manually clears all cached data (prices and news) from the MongoDB database. This is a developer utility to ensure fresh data is fetched from source APIs after deploying code changes.

  - **Example Usage:**
      ```Bash
        curl -X POST http://localhost:3000/cache/clear
      ```

  - **Example Success Response:**
      ```JSON
      {
        "message": "All data service caches have been cleared."
      }

- **GET `/screen/:ticker`**
  - Proxies to the Screening Service.
  - Applies the 7 quantitative screening criteria to the specified ticker and returns a detailed pass/fail result.
  - **Error Handling for Invalid Tickers:** Returns `502 Bad Gateway` with a descriptive error message.
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
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/financials/core/AAPL
    ```
  - **Example Response (`GET /financials/core/AAPL`):**
  ```json
  {
    "marketCap": 2800000000000,
    "sharesOutstanding": 15500000000,
    "floatShares": 15400000000,
    "ipoDate": "1980-12-12",
    "quarterly_earnings": [
      {
        "date": "3Q2024",
        "revenue": 90000000000,
        "earnings": 25000000000
      }
    ],
    "quarterly_financials": [
        {
            "date": "2024-06-30",
            "Basic EPS": 1.53
        }
    ]
  }

- **GET `/leadership/<path:ticker>`**  
  - Proxies to: `leadership-service`
  - Purpose: Applies the 10 "Leadership Profile" criteria to the specified ticker.
  - **Example Usage:**
    ```bash
    curl http://localhost:3000/leadership/AAPL
    ```
   - **Example Success Response:**
    ```json
    {
      "ticker": "AAPL",
      "passes": true,
      "details": {
        "is_small_to_mid_cap": {
          "pass": true,
          "message": "Market cap $2,8T is within the range of $300M to $10B."
        },
        "is_recent_ipo": {
          "pass": false,
          "message": "IPO was 43.7 years ago, which is older than the 10-year threshold."
        },
        "has_limited_float": {
          "pass": false,
          "message": "Float is 99.8%, which is above the 20% threshold."
        },
        "has_accelerating_growth": {
          "pass": true,
          "message": "All metrics (Earnings, Revenue, Margin) show accelerating quarter-over-quarter growth."
        },
        "is_industry_leader": {
            "pass": true,
            "rank": 1
        }
      },
      "metadata": {
        "execution_time": 0.458
      }
    }
    ```

- **GET `/leadership/industry_rank/:ticker`**  
  - Proxies to: `leadership-service`
  - Purpose: Ranks the specified ticker against its industry peers based on revenue, market cap, and net income.
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

# Internal Service Communication

## `scheduler-service` -> `analysis-service`

For efficient batch processing, the **`scheduler-service`** calls the **`analysis-service`** using the `?mode=fast` query parameter. This instructs the `analysis-service` to perform a "fail-fast" evaluation, immediately stopping and returning a fail status for a ticker that does not meet a VCP criterion, thus conserving system resources.

## Internal Data Service Endpoints
- The following endpoints are used for internal service-to-service communication and are not exposed through the public API Gateway. They are documented here for completeness.

- **POST `/financials/core/batch`**  
  - Proxies to: data-service
  - Purpose: Retrieves core financial data for a batch of tickers. This is used by the leadership-service to efficiently gather the necessary data for its industry peer ranking analysis.

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
        "passing_candidates": [
          {
            "ticker": "AAPL",
            "passes": true,
            "details": {
              "is_small_to_mid_cap": {
                  "pass": true,
                  "message": "Market cap is within the required range."
              }
            }
          }
        ],
        "metadata": {
          "total_processed": 2,
          "total_passed": 1,
          "execution_time": 1.234
        }
      }
      ```