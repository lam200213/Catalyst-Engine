# MongoDB Database Schema
This document outlines the schema for each collection used in the MongoDB `stock_analysis` database. These schemas are enforced by the Pydantic models defined in `backend-services/shared/contracts.py` and are used for data persistence across various microservices.

## General Principles

- **Database**: All collections reside within the `stock_analysis` database.
- **Data Integrity**: While MongoDB is schema-flexible, our application layer enforces the structures defined below through Pydantic models to ensure data consistency.
- **Caching**: The `data-service` utilizes Redis for application-level caching of API responses (prices, financials, news). MongoDB is used for persistent storage only.

## 1. screening_jobs

Stores a summary document for each completed screening pipeline run, providing a high-level overview of the job's outcome.

- **Primary Service**: `scheduler-service`
- **Schema**: Based on the `ScreeningJobResult` Pydantic model.

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

- **Primary Service**: `scheduler-service`
- **Schema**: Based on the `FinalCandidate` Pydantic model.

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

- **Primary Service**: `scheduler-service`
- **Collections**:
  1. `trend_survivors`
  2. `vcp_survivors`
  3. `leadership_survivors`

- **Schema (for all survivor collections)**:

```json
{
  "job_id": "string", // Foreign key linking to the `screening_jobs` collection
  "ticker": "string"  // The ticker symbol that passed this stage
}
```

## 4. ticker_status
Maintains a record of tickers that have been identified as delisted to prevent unnecessary API calls for them in the future.

- **Primary Services**: `ticker-service`, `data-service`
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

- **Primary Service**: `data-service`
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
  "created_at": "ISODate"
}
```

## 6. portfolio_items
Stores the stock positions for the user's portfolio. In the current phase, it operates in single-user mode.

- **Primary Service**: `monitoring-service`
- **Schema**:

```json
{
  "_id": "ObjectId",
  "user_id": "string", // Hardcoded to "single_user_mode" for this phase
  "ticker": "string",
  "buy_price": "float",
  "buy_date": "ISODate",
  "first_base_date": "ISODate", // Determined automatically by the analysis-service
  "initial_pe": "float",
  "stop_loss_percent": "float",
  "last_updated": "ISODate"
}
```

## 7. watchlistitems

Stores the user's active watchlist. Tickers in this collection are actively monitored and periodically re-validated by scheduled health checks.

- **Primary Service**: `monitoring-service`
- **Collection Name**: `watchlistitems`
- **Indexes**: 
  - Unique compound index on `(user_id, ticker)` to prevent duplicates per user.
  - Index on `user_id` for efficient user-scoped queries.
- **Schema**:
  **Core Fields:**
    - `user_id`: String (always "single_user_mode" in current implementation)
    - `ticker`: String (normalized uppercase)
    - `date_added`: DateTime
    - `is_favourite`: Boolean
    - `last_refresh_status`: String enum (PENDING, PASS, FAIL, UNKNOWN)
    - `last_refresh_at`: DateTime
    - `failed_stage`: Optional String (e.g., "vcp", "leadership")

    **VCP Pattern Fields:**
    - `current_price`: Float
    - `pivot_price`: Float - identified pivot price
    - `pivot_proximity_percent`: Float - distance from pivot as percentage
    - `vcp_pass`: Boolean - VCP pattern screening result
    - `is_pivot_good`: Boolean - pivot quality flag
    - `pattern_age_days`: Integer - age of pattern (used for freshness checks)

    **Volume Analysis Fields:**
    - `has_pivot`: Boolean - pivot point identified
    - `is_at_pivot`: Boolean - price at pivot
    - `has_pullback_setup`: Boolean - in pullback zone
    - `vol_last`: Integer - most recent volume
    - `vol_50d_avg`: Integer - 50-day average volume
    - `vol_vs_50d_ratio`: Float - current vs 50D volume ratio
    - `day_change_pct`: Float - daily price change percentage

    **Leadership Field:**
    - `is_leader`: Boolean - meets leadership criteria

    **Indexes:**
    - `{ user_id: 1, ticker: 1 }` (unique) - primary lookup and uniqueness constraint
    - `{ user_id: 1, last_refresh_status: 1 }` - status filtering

- **Flow**:  
  Bulk status updates and auto-archiving are now performed exclusively by the monitoring-service internal refresh orchestrator endpoint (`POST /monitor/internal/watchlist/refresh-status`). Manual delete operations via `DELETE /monitor/watchlist/:ticker` still set `archived_at` and `reason=MANUAL_DELETE` before moving items to the archive collection.

- **TTL Behavior**: No automatic document expiration. Items remain in this collection until explicitly moved to `archived_watchlist_items` via:
  - Manual batch removal (POST `/monitor/watchlist/batch/remove`)
  - Manual single deletion (DELETE `/monitor/watchlist/:ticker`)
  - Automated health check failure archival (scheduled job)

## 8. archived_watchlist_items

Stores a "graveyard" of tickers that were removed from the active watchlist, providing a user-facing audit trail. Items may be removed either automatically (failed health check) or manually by the user.

- **Primary Service**: `monitoring-service`
- **Collection Name**: `archived_watchlist_items`
- **TTL**: Documents are automatically deleted 90 days after `archived_at` timestamp via MongoDB TTL index.
- **Indexes**:
  - TTL index on `archived_at` with `expireAfterSeconds: 7776000` (90 days)
  - Index on `user_id` for user-scoped queries
- **Schema**:

```
{
  "_id": "ObjectId",
  "user_id": "string", // Partition key (for future multi-user support)
  "ticker": "string", // e.g., "CRM", uppercase normalized
  "archived_at": "ISODate", // When the item was moved to this collection (used for TTL)
  "archived_at": "ISODate", // Alternative field name (legacy support for some queries)
  "reason": "string", // Archive reason enum: "MANUAL_DELETE" | "FAILED_HEALTH_CHECK"
  "failed_stage": "string | null", // Stage where health check failed (only set when reason is "FAILED_HEALTH_CHECK")
}
```

**Archive Reason Values**:
- `"MANUAL_DELETE"`: User manually removed the item via:
  - Batch remove endpoint: POST `/monitor/watchlist/batch/remove`
  - Single delete endpoint: DELETE `/monitor/watchlist/:ticker`
- `"FAILED_HEALTH_CHECK"`: Item was automatically archived by the scheduled health check job after failing validation criteria (screening, VCP, or freshness checks).

**Field Naming Notes**:
- Multiple field name variants exist due to different code paths and migrations:
  - User ID: `user_id` (preferred) 
  - Archive timestamp: `archived_at` (used for TTL index)
  - Failed stage: `failed_stage` (bulk operations, health check operations)

**Data Flow**:
  Items that fail automated health checks (screening, VCP, freshness, or data stages) are moved from `watchlistitems` to `archived_watchlist_items` by the orchestrator with `reason=FAILED_HEALTH_CHECK` and the failed stage recorded in `failed_stage`. Manual deletions use `reason=MANUAL_DELETE`. The TTL index on `archived_at` ensures automatic expiration after 90 days for audit and recovery purposes.

---
