# MongoDB Database Schema
This document outlines the schema for each collection used in the MongoDB stock_analysis database. These schemas are enforced by the Pydantic models defined in backend-services/shared/contracts.py and are used for data persistence across various microservices.

## General Principles

- **Database**: All collections reside within the stock_analysis database.
- **Data Integrity**: While MongoDB is schema-flexible, our application layer enforces the structures defined below through Pydantic models to ensure data consistency.
- **Caching**: The data-service utilizes Redis for application-level caching of API responses (prices, financials, news). MongoDB is used for persistent storage only.

## 1. screening_jobs

Stores a summary document for each completed screening pipeline run, providing a high-level overview of the job's outcome.

- **Primary Service**: scheduler-service
- **Schema**: Based on the ScreeningJobResult Pydantic model.

```json
{
  "job_id": "string", // Unique identifier for the job (e.g., "20251015-123000-ABC123DE")
  "processed_at": "ISODate", // Timestamp when the job was completed
  "total_process_time": "float", // Total execution time in seconds
  "total_tickers_fetched": "integer", // Total tickers from ticker-service
  "trend_screen_survivors_count": "integer",
  "vcp_survivors_count": "integer",
  "final_candidates_count": "integer",
  "industry_diversity": {
    "unique_industries_count": "integer"
  },
  "final_candidates": [
    // This array is stored in the document but is often large.
    // Individual candidates are also stored in the `screening_results` collection for easier querying.
    // See the schema for 'screening_results' for the structure of each item.
  ]
}
```

## 2. screening_results
Stores the detailed information for each individual stock that passed all stages of a specific screening run.

- **Primary Service**: scheduler-service
- **Schema**: Based on the FinalCandidate Pydantic model.

```json
{
  "job_id": "string", // Foreign key linking to the `screening_jobs` collection
  "processed_at": "ISODate", // Timestamp when this specific result was stored
  "ticker": "string",
  "vcp_pass": "boolean",
  "vcpFootprint": "string", // e.g., "10D 8.6% | 5D 5.3%"
  "leadership_results": {
    "ticker": "string",
    "passes": "boolean",
    "leadership_summary": {
      "qualified_profiles": ["string"],
      "message": "string"
    },
    "profile_details": {
      "explosive_grower": { "pass": "boolean", "passed_checks": "integer", "total_checks": "integer" },
      "high_potential_setup": { "pass": "boolean", "passed_checks": "integer", "total_checks": "integer" },
      "market_favorite": { "pass": "boolean", "passed_checks": "integer", "total_checks": "integer" }
    },
    "industry": "string"
  }
}
```

## 3. Stage Survivor Collections
These collections are primarily for logging and debugging, storing only the tickers that passed each specific stage of the screening funnel for a given job.

- **Primary Service**: scheduler-service
- **Collections**:

1. trend_survivors
2. vcp_survivors
3. leadership_survivors

- **Schema (for all survivor collections)**:

```json
{
  "job_id": "string", // Foreign key linking to the `screening_jobs` collection
  "ticker": "string"  // The ticker symbol that passed this stage
}
```

## 4. ticker_status
Maintains a record of tickers that have been identified as delisted to prevent unnecessary API calls for them in the future.

- **Primary Services**: ticker-service, data-service

- **Schema**:

```json
{
  "_id": "ObjectId",
  "ticker": "string", // Indexed for fast lookups
  "status": "string", // e.g., "delisted"
  "reason": "string", // Reason for being marked as delisted (e.g., "Provider returned 404")
  "last_updated": "ISODate"
}
```

## 5. market_trends
Stores the calculated market trend context for specific dates, preventing recalculation and providing historical context.

- **Primary** Service: data-service
- **Schema**:

```json
{
  "_id": "ObjectId",
  "date": "string", // Format: "YYYY-MM-DD", has a unique index
  "trend": "string", // "Bullish", "Bearish", or "Neutral"
  "pass": "boolean", // True if trend is not "Bearish"
  "details": {
    "^GSPC": "string", // Trend for S&P 500
    "^DJI": "string",  // Trend for Dow Jones
    "^IXIC": "string"  // Trend for NASDAQ
  },
  "createdAt": "ISODate"
}
```

## 6. portfolio_items
Stores the stock positions for the user's portfolio. In the current phase, it operates in single-user mode.

- **Primary Service**: monitoring-service
- **Schema**:

```json
{
  "_id": "ObjectId",
  "user_id": "string", // Hardcoded to "single_user_mode" for this phase
  "ticker": "string",
  "buy_price": "float",
  "buy_date": "ISODate",
  "first_bottom_date": "ISODate", // Determined automatically by the analysis-service
  "initial_pe": "float",
  "stop_loss_percent": "float",
  "last_updated": "ISODate"
}
```

## 7. watchlist_items
Stores the stocks the user is tracking in their watchlist.

- **Primary Service**: monitoring-service
- **Schema**:

```json
{
  "_id": "ObjectId",
  "user_id": "string", // Hardcoded to "single_user_mode" for this phase
  "ticker": "string",
  "status": "string", // "Watch", "Buy Alert", "Buy Ready"
  "date_added": "ISODate",
  "last_updated": "ISODate"
}
```
