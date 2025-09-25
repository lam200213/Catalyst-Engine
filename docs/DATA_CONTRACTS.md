# Data Contracts

This document serves as the single source of truth for the data structures exchanged between the microservices in the SEPA Stock Screener backend. Adhering to these contracts is mandatory to ensure system reliability and maintainability.

---

## 1. TickerList

A simple list of stock ticker symbols.

-   **Producer:** `ticker-service`
-   **Consumer:** `scheduler-service`
-   **Schema:** `List[str]`
-   **Description:** The initial, complete list of all stock tickers fetched from the source. This object initiates the screening funnel.
-   **Example Payload:**
    ```json
    [
        "AAPL",
        "MSFT",
        "GOOGL"
    ]
    ```

---

## 2. PriceData

Contains the full OHLCV (Open, High, Low, Close, Volume) time-series data for a single stock ticker.

-   **Producer:** `data-service`
-   **Consumers:** `screening-service`, `analysis-service`, `leadership-service`
-   **Schema:** `List[Dict[str, Union[str, float, int]]]`
-   **Key Fields (per dictionary in list):**
    -   `formatted_date: str`
    -   `open: float`
    -   `high: float`
    -   `low: float`
    -   `close: float`
    -   `volume: int`
    -   `adjclose: float`
-   **Description:** This is the primary data object used for all quantitative analysis. The data is sorted by date in ascending order (oldest to newest).
-   **Example Payload:**
    ```json
    [
        {
            "formatted_date": "2023-01-02",
            "open": 152.5,
            "high": 153.5,
            "low": 151.5,
            "close": 153.0,
            "volume": 1200000,
            "adjclose": 152.8
        },
        {
            "formatted_date": "2023-01-03",
            "open": 153.0,
            "high": 155.0,
            "low": 152.0,
            "close": 154.5,
            "volume": 1100000,
            "adjclose": 154.3
        }
    ]
    ```

---

## 3. CoreFinancials

Provides essential, high-level fundamental data points for a single stock ticker, used for the leadership screening phase.

-   **Producer:** `data-service`
-   **Consumer:** `leadership-service`
-   **Schema:** `Dict[str, Union[str, float, List[Dict]]]`
-   **Key Fields:**
    -   `ticker: str`
    -   `marketCap: float | None`
    -   `sharesOutstanding: float | None`
    -   `floatShares: float | None`
    -   `ipoDate: str | None`
    -   `annual_earnings: List[Dict]`
    -   `quarterly_earnings: List[Dict]`
-   **Description:** A lean data object designed for the "Just-in-Time" data retrieval strategy. It is only fetched for stocks that have already passed the initial trend and VCP screens.
-   **Example Payload:**
    ```json
    {
        "ticker": "AAPL",
        "marketCap": 2750000000000.0,
        "sharesOutstanding": 15730000000.0,
        "floatShares": 15720000000.0,
        "ipoDate": "1980-12-12",
        "annual_earnings": [
            {"Revenue": 394328000000, "Earnings": 99803000000},
            {"Revenue": 365817000000, "Earnings": 94680000000}
        ],
        "quarterly_earnings": [
            {"Revenue": 90146000000, "Earnings": 20721000000},
            {"Revenue": 82959000000, "Earnings": 19442000000}
        ]
    }
    ```

---

## 4. NewsData

A list of recent news articles for a specific ticker.

-   **Producer:** `data-service`
-   **Consumer(s):** `ranking-service` (Post-MVP), `frontend-app` (Post-MVP)
-   **Schema:** `List[Dict[str, any]]`
-   **Key Fields (per article object):**
    -   `uuid: str`
    -   `title: str`
    -   `description: str`
    -   `url: str`
    -   `source: str`
    -   `published_at: str`
-   **Description:** Provides news context for a stock, intended for qualitative analysis stages like PRP ranking or for display in the UI.
-   **Example Payload:**
    ```json
    [
        {
            "uuid": "a1b2c3d4",
            "title": "Tech Giant Unveils New Product",
            "description": "Shares surged today after the announcement...",
            "url": "[https://example.com/news/123](https://example.com/news/123)",
            "source": "example.com",
            "published_at": "2025-09-25T10:00:00.000000Z"
        }
    ]
    ```

---

## 5. IndustryPeers

Provides the industry classification and a list of peer companies for a given ticker.

-   **Producer:** `data-service`
-   **Consumer(s):** `leadership-service`
-   **Schema:** `Dict[str, Union[str, List[str]]]`
-   **Key Fields:**
    -   `industry: str | None`
    -   `peers: List[str]`
-   **Description:** Used by the leadership service to perform relative strength and leadership analysis within a stock's specific industry group.
-   **Example Payload:**
    ```json
    {
        "industry": "Semiconductors",
        "peers": [
            "NVDA",
            "AVGO",
            "QCOM",
            "TXN"
        ]
    }
    ```

---

## 6. ScreeningResult

Communicates the outcome of the SEPA trend screening. The format differs between the single-ticker and batch endpoints.

-   **Producer:** `screening-service`
-   **Consumers:** `scheduler-service` (batch), `api-gateway`/`frontend-app` (single)
-   **Description:**
    -   The batch endpoint (used by the scheduler) returns a simple list of ticker strings that passed the screen.
    -   The single ticker endpoint (used by the UI for detailed analysis) returns a boolean result with a breakdown of each rule.
-   **Batch Schema:** `List[str]`
-   **Example Batch Payload:**
    ```json
    [
        "AAPL",
        "NVDA",
        "AMD"
    ]
    ```
-   **Single Ticker Schema:** `Dict[str, Union[str, bool, Dict]]`
    -   **Key Fields:**
        -   `ticker: str`
        -   `passes: bool`
        -   `details: Dict[str, bool]`
-   **Example Single Payload:**
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
        }
    }
    ```

---

## 7. VCPAnalysis

Communicates the outcome of the Volatility Contraction Pattern (VCP) analysis. The format differs for batch and single-ticker requests.

-   **Producer:** `analysis-service`
-   **Consumers:** `scheduler-service` (batch), `api-gateway`/`frontend-app` (single)
-   **Description:**
    -   The batch endpoint returns a lean list of passing tickers for the orchestration pipeline.
    -   The single ticker endpoint returns a rich object with full details and data for chart visualization.
-   **Batch Schema:** `List[Dict[str, Union[str, bool]]]`
    -   **Key Fields (per item):**
        -   `ticker: str`
        -   `vcp_pass: bool`
        -   `vcpFootprint: str`
-   **Example Batch Payload:**
    ```json
    [
        {
            "ticker": "NVDA",
            "vcp_pass": true,
            "vcpFootprint": "15W 31/3 4T"
        },
        {
            "ticker": "AMD",
            "vcp_pass": true,
            "vcpFootprint": "12W 24/2 3T"
        }
    ]
    ```
-   **Single Ticker Schema:** `Dict[str, Any]`
    -   **Key Fields:**
        -   `ticker: str`
        -   `vcp_pass: bool`
        -   `vcpFootprint: str`
        -   `chart_data: Dict`
        -   `vcp_details: Dict` (only in 'full' mode)
-   **Example Single Payload:**
    ```json
    {
        "ticker": "NVDA",
        "vcp_pass": true,
        "vcpFootprint": "15W 31/3 4T",
        "chart_data": {
            "detected": true,
            "vcpLines": [{"time": "2023-05-10", "value": 300.5}, {"time": "2023-06-15", "value": 280.0}],
            "buyPoints": [{"value": 480.50}],
            "sellPoints": [{"value": 450.0}],
            "ma50": [...],
            "historicalData": [...]
        },
        "vcp_details": {
            "pivot_validation": {"pass": true, "message": "Pivot is recent."},
            "volume_validation": {"pass": true, "message": "Demand is contracting."}
        }
    }
    ```

---

## 8. LeadershipProfile

Contains the result of the leadership screening for a single ticker. The format differs for batch and single-ticker requests.

-   **Producer:** `leadership-service`
-   **Consumers:** `scheduler-service` (batch), `api-gateway`/`frontend-app` (single)
-   **Description:**
    -   The batch endpoint returns a list of only the candidates that pass all leadership criteria.
    -   The single ticker endpoint returns a full breakdown of the analysis for one ticker.
-   **Batch Schema:** `Dict[str, Any]`
    -   **Key Fields:**
        -   `passing_candidates: List[Dict]` (List of Single Ticker Schema objects)
        -   `unique_industries_count: int`
        -   `metadata: Dict`
-   **Example Batch Payload:**
    ```json
    {
        "passing_candidates": [
            {
                "ticker": "AMD",
                "passes": true,
                "details": {
                    "is_small_to_mid_cap": true,
                    "is_recent_ipo": false,
                    "has_strong_yoy_eps_growth": true
                },
                "industry": "Semiconductors"
            }
        ],
        "unique_industries_count": 1,
        "metadata": {
            "total_processed": 50,
            "total_passed": 1,
            "execution_time": 15.123
        }
    }
    ```
-   **Single Ticker Schema:** `Dict[str, Any]`
    -   **Key Fields:**
        -   `ticker: str`
        -   `passes: bool`
        -   `details: Dict`
        -   `industry: str | None`
        -   `metadata: Dict`
-   **Example Single Payload:**
    ```json
    {
        "ticker": "AMD",
        "passes": true,
        "details": {
            "is_small_to_mid_cap": { "pass": true, "message": "Market Cap is $150.0B" },
            "is_recent_ipo": { "pass": false, "message": "IPO date is older than 10 years" },
            "has_strong_yoy_eps_growth": { "pass": true, "message": "YoY EPS growth is 45%" },
            "is_industry_leader": { "pass": true, "message": "Ranked 2 of 25 in industry."}
        },
        "industry": "Semiconductors",
        "metadata": {
            "execution_time": 0.891
        }
    }
    ```

---

## 9. ScreeningJobResult

A summary document detailing the statistics and results of a completed screening pipeline run.

-   **Producer:** `scheduler-service`
-   **Consumer(s):** MongoDB (`screening_jobs` collection), `api-gateway`/`frontend-app` (for historical job review)
-   **Schema:** `Dict[str, Any]`
-   **Key Fields:**
    -   `job_id: str`
    -   `processed_at: datetime`
    -   `total_process_time: float`
    -   `total_tickers_fetched: int`
    -   `trend_screen_survivors_count: int`
    -   `vcp_survivors_count: int`
    -   `final_candidates_count: int`
    -   `industry_diversity: Dict`
    -   `final_candidates: List[Dict]` (List of enriched LeadershipProfile objects)
-   **Description:** This object provides a high-level overview of the screening funnel's performance for a given run. It is stored in the database for historical analysis and logging. The `final_candidates` are the fully enriched objects stored in the `screening_results` collection.
-   **Example Payload (stored in `screening_jobs` collection):**
    ```json
    {
        "job_id": "20250925-083000-A1B2C3D4",
        "processed_at": "2025-09-25T08:35:15.123Z",
        "total_process_time": 315.12,
        "total_tickers_fetched": 7800,
        "trend_screen_survivors_count": 850,
        "vcp_survivors_count": 95,
        "final_candidates_count": 12,
        "industry_diversity": {
            "unique_industries_count": 8
        },
        "final_candidates": [
            {
                "ticker": "NVDA",
                "vcp_pass": true,
                "vcpFootprint": "15W 31/3 4T",
                "leadership_results": { ... }
            }
        ]
    }
    ```