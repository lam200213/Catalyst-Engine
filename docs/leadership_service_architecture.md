# Leadership Service Architecture

## 1. Overview

The leadership-service is a core component of the SEPA Stock Screener, responsible for evaluating individual stocks against a rigorous set of 10 leadership criteria inspired by Mark Minervini's trading principles. Its primary function is to act as a crucial filter in the screening pipeline, analyzing stocks that have already passed the initial Trend and VCP screens to identify true market leaders with strong fundamentals and superior relative strength.

The service operates on a "Just-in-Time" data retrieval model, fetching detailed financial, peer, and market data only when required for analysis, thus optimizing system resources and minimizing external API calls.

## 2. System Architecture & Data Flow

The service integrates seamlessly into the existing microservices ecosystem, acting as a downstream consumer of the data-service and an upstream provider for the scheduler-service and the public api-gateway.

```mermaid
flowchart TD
    subgraph User/Scheduler
        A[API Gateway]
        B[Scheduler Service]
    end

    subgraph Downstream Services
        D[Data Service]
    end

    subgraph Leadership Service
        C[API Layer: app.py]
        C1[Service Client: data_fetcher.py]
        C2[Orchestrator: helper_functions.py]
        C3[Check Modules]
    end

    Client[Client Front End] -- HTTP Requests --> A
    A -- GET /leadership/:ticker --> C
    B -- POST /leadership/batch --> C
    C --> C1
    C1 -- Fetches price, financials, peers, market data --> D
    C -- Invokes --> C2
    C2 -- Aggregates data & runs checks --> C3

    subgraph "Check Modules"
        direction LR
        C3_1[Financial Health]
        C3_2[Market Relative]
        C3_3[Industry Peer]
    end
    
    C2 --> C3_1
    C2 --> C3_2
    C2 --> C3_3
```

### Data Flow:

1. **Request Initiation**: A request is initiated either by a user for a single ticker via the api-gateway (/leadership/:ticker) or by the scheduler-service for a batch of tickers (/leadership/batch).

2. **API Handling (app.py)**: The Flask application receives the request, performs initial input validation, and orchestrates the subsequent steps.

3. **Data Fetching (data_fetcher.py)**: The service's dedicated data client fetches all necessary data from the data-service in parallel, including core financials, historical prices, industry peers, and market trend context.

4. **Analysis Orchestration (helper_functions.py)**: The main analyze_ticker_leadership function receives the aggregated data. It then systematically executes all 10 leadership checks.

5. **Logic Execution (checks/*.py)**: Each check is performed by a dedicated function within the appropriate module, returning a detailed pass/fail result with a descriptive message.

6. **Response Aggregation**: The orchestrator compiles the results from all checks into a final JSON object, determines the overall passes status, and returns it to the API layer.

7. **Contract Validation**: Before sending the final HTTP response, the output data is validated against the formal Pydantic data contracts (LeadershipProfileSingle or LeadershipProfileBatch) to ensure system-wide data integrity.

## 3. Core Modules & Responsibilities

### app.py

**Role**: API Layer & Request Handler.

**Responsibilities**:

- Defines all Flask routes (/leadership/<ticker>, /leadership/batch, /leadership/industry_rank/<ticker>, /health).
- Handles incoming HTTP requests, including parsing JSON payloads and URL parameters.
- Implements robust input validation to prevent common vulnerabilities (e.g., path traversal).
- Orchestrates the high-level workflow by calling the data_fetcher and helper_functions.
- Manages concurrent processing for batch requests using a ThreadPoolExecutor.
- Sets up and configures structured, thread-safe logging with ticker context.
- Validates final outgoing responses against Pydantic contracts.

### data_fetcher.py

**Role**: Dedicated Service Client.

**Responsibilities**:

- Manages all communication with the upstream data-service.
- Implements resilient data fetching logic using a shared requests.Session with connection pooling and an automatic retry strategy.
- Contains specific functions for each required data type:
  - fetch_financial_data, fetch_batch_financials
  - fetch_price_data, fetch_batch_price_data
  - fetch_peer_data
  - fetch_index_data, fetch_market_trends
- Abstracts away the complexities of HTTP requests from the main application logic.

### helper_functions.py

**Role**: Analysis Orchestrator & Utility Hub.

**Responsibilities**:

- Contains the primary analyze_ticker_leadership function, which serves as the central orchestrator for running all 10 leadership checks.
- Houses the validate_data_contract utility function, providing a single, consistent way to enforce Pydantic contracts on data received from the data-service.
- Includes the fetch_general_data_for_analysis function to efficiently retrieve market context data (indices, trends) common to all analyses.

### checks/ Directory

This module contains the core business logic, with each file dedicated to a specific category of analysis.

- **financial_health_checks.py**: Performs checks related to the company's intrinsic financial characteristics (e.g., market cap, IPO date, float, earnings growth).
- **market_relative_checks.py**: Compares the stock's performance and behavior against the broader market context (e.g., performance during rallies, reaction to market trends).
- **industry_peer_checks.py**: Analyzes the stock's standing within its specific industry by ranking it against its peers on key metrics.
- **utils.py**: Provides common utility functions for the check modules, such as the failed_check helper for creating consistent failure responses.

## 4. Leadership Metrics Deep Dive

A stock must pass all applicable metrics to be considered a leadership candidate.

### 1. Small to Mid-Cap ($300M–$10B)

**Logic**: Leadership profiles are typically found in companies with significant room for growth.

**Function**: check_is_small_to_mid_cap

**Implementation**: Checks if the company's marketCap is between $300 million and $10 billion.

### 2. Early-Stage Company (≤10 Years Post-IPO)

**Logic**: Younger, innovative companies often exhibit the most explosive growth.

**Function**: check_is_early_stage

**Implementation**: Calculates the number of years since the company's ipoDate. Passes if the result is 10 years or less.

### 3. Limited Float

**Logic**: A smaller supply of available shares (float) can lead to more powerful price moves when demand increases.

**Function**: check_has_limited_float

**Implementation**: Passes if the company's floatShares is less than 100 million, categorizing it as "Low" or "Medium" float.

### 4. Accelerating Growth (EPS, Sales, Margin)

**Logic**: True leaders show not just growth, but accelerating growth.

**Function**: check_accelerating_growth

**Implementation**: Calculates the Quarter-over-Quarter (QoQ) growth rates for Earnings, Revenue, and Net Margin for the last 3 quarters. Passes only if all three metrics show strictly increasing growth rates over this period.

### 5. Strong YoY EPS Growth (>25%)

**Logic**: Demonstrates strong annual momentum in profitability.

**Function**: check_yoy_eps_growth

**Implementation**: Compares the most recent quarter's Earnings Per Share (EPS) to the same quarter from the previous year. Passes if the growth is greater than 25%. Growth rates are highlighted as "Standard," "High," or "Exceptional."

### 6. Consecutive Quarterly Growth (>20%)

**Logic**: Indicates sustained, high-velocity growth in recent periods.

**Function**: check_consecutive_quarterly_growth

**Implementation**: Calculates the QoQ EPS growth for each of the last 4 quarters. Passes if all four quarters individually show growth greater than 20%.

### 7. Positive Recent Earnings

**Logic**: The company must be profitable.

**Function**: check_positive_recent_earnings

**Implementation**: Checks if the EPS for both the most recent quarter and the last full fiscal year are positive.

### 8. Market Trend Alignment

**Logic**: The stock's behavior should be strong relative to the overall market's condition.

**Function**: evaluate_market_trend_impact

**Implementation**:

- Determines Market Context: Classifies the current market as 'Bullish', 'Bearish', or 'Neutral' based on recent trend data.
- Conditional Checks:
  - In a Bearish market, it passes if the stock's decline from its 52-week high is shallower than the S&P 500's decline.
  - In a Bullish or Neutral market, it passes if the stock has recently made a new 52-week high, indicating leadership.
  - In a Recovery Phase (just after a market bottom), it passes if the stock makes a new high within 20 days of the market's turning point.

### 9. Industry Leadership (Top 3 Rank)

**Logic**: A true leader must be one of the top performers in its specific industry.

**Function**: analyze_industry_leadership

**Implementation**:

- Fetches a list of the company's industry peers.
- Batch-fetches financial data for the company and all its peers.
- Ranks all companies on Revenue, Market Cap (as a proxy for market share), and Net Income.
- Calculates a combined score and a final rank. Passes if the company's final rank is in the top 3.

**Note**: The 10th metric, "Outperformance in Market Rally", is currently encompassed within the logic of the evaluate_market_trend_impact function, which checks for new highs during market recovery phases.