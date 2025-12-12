- **POST `/data/return/1m/batch` (deprecated)**
  - Service: `data-service`
  - Purpose: Equivalent to POST /data/return/batch with period="1mo".
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

- **POST `/monitor/internal/watchlist/batch/update-status`** *(DEPRECATED - Week 7+)*
  - Service: `monitoring-service`
  - **Status:** DEPRECATED/RETIRED. Superseded by /monitor/internal/watchlist/refresh-status.
  - **Legacy Purpose**: Internal-only endpoint called by scheduler-service to update health check status for multiple watchlist items after refresh pipeline completes. 
  - **Access**: Internal only (called by scheduler-service `refresh_watchlist_task`)
  - **Example Usage**:
    ```bash
    curl -X POST http://localhost:3006/monitor/internal/watchlist/batch/update-status \
      -H "Content-Type: application/json" \
      -d '{
        "items": [
          {"ticker": "AAPL", "status": "PASS", "failed_stage": null},
          {"ticker": "MSFT", "status": "FAIL", "failed_stage": "screening"}
        ]
      }'
    ```
  - **Request Body**: `InternalBatchUpdateStatusRequest`
    ```json
    {
      "items": [
        {
          "ticker": "AAPL",
          "status": "PASS",
          "failed_stage": null
        },
        {
          "ticker": "CRM",
          "status": "FAIL",
          "failed_stage": "vcp"
        }
      ]
    }
    ```
  - **Response**: `InternalBatchUpdateStatusResponse` (200 OK)
    ```json
    {
      "message": "Batch status update completed for 2 watchlist items. Sample: AAPL, CRM",
      "updated": 2,
      "tickers": ["AAPL", "CRM"]
    }
    ```
  - **Data Contracts**:
    - Request: `InternalBatchUpdateStatusRequest`
    - Response: `InternalBatchUpdateStatusResponse`
    - Error: `ApiError`
  - **Error Responses**:
    - 400: Invalid request body or malformed items
    - 503: Database connection failure