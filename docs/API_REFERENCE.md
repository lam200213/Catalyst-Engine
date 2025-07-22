# API Gateway Endpoints
The frontend communicates exclusively with the API Gateway, which proxies requests to the appropriate backend services.

- **GET `/tickers`** 
  - Retrieves a list of all US stock tickers from the ticker-service.  

* **GET `/data/:ticker`**
    * Proxies to: `data-service`
    * Retrieves historical price data for a ticker, with caching.
    * **Note:** The `source` parameter is handled by the `data-service` directly, not the gateway.

* **GET `/news/:ticker`**
    * Proxies to: `data-service`
    * Retrieves recent news articles for a ticker, with caching.

- **POST `/data/batch`**
  - Proxies to: `data-service`
  - Retrieves historical price data for a batch of tickers. This is more efficient than making individual requests for each ticker.
  - **Request Body (JSON):**
    ```json
    {
      "tickers": ["AAPL", "GOOGL", "MSFT", "FAKETICKER"],
      "source": "yfinance"
    }
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
  - Performs VCP analysis on historical data and returns a pass/fail boolean, a VCP footprint string, and detailed data for charting.
  - **Query Parameters**:
    - `mode` (optional): Set to `fast` to enable fail-fast evaluation for batch processing. If omitted, defaults to `full` evaluation, which returns a detailed breakdown of all checks.
  - **Error Handling**: Returns `502 Bad Gateway` if the data-service cannot find the ticker, and `503 Service Unavailable` if the data-service cannot be reached.
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

# Internal Service Communication

## `scheduler-service` -> `analysis-service`

For efficient batch processing, the **`scheduler-service`** calls the **`analysis-service`** using the `?mode=fast` query parameter. This instructs the `analysis-service` to perform a "fail-fast" evaluation, immediately stopping and returning a fail status for a ticker that does not meet a VCP criterion, thus conserving system resources.