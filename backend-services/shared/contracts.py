# backend-services/shared/contracts.py
"""
This module defines the Pydantic models that serve as the formal data contracts
for all inter-service communication in the SEPA Stock Screener backend.

These models ensure data consistency, provide automatic validation, and act as
living documentation for the data structures exchanged between microservices.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypeAlias, Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, StrictBool, StrictInt, field_serializer
from enum import Enum

# --- Enums: Watchlist/Archive/Freshness ---
class ArchiveReason(str, Enum):
    """
    Reason for archiving a watchlist item.
    
    Values:
    - MANUAL_DELETE: User explicitly removed the item via DELETE /monitor/watchlist/:ticker
    - FAILED_HEALTH_CHECK: Item failed automated health check and was auto-archived by the orchestrator
    
    Usage: Used in archived_watchlist_items.reason field and by the orchestrator for auto-archiving.
    """
    MANUAL_DELETE = "MANUAL_DELETE"
    FAILED_HEALTH_CHECK = "FAILED_HEALTH_CHECK"

class LastRefreshStatus(str, Enum):
    """
    Health-check status for watchlist items after automated refresh.
    
    Values:
    - PENDING: Item is queued for refresh but not yet processed
    - PASS: Item passed all health checks (screening, VCP, freshness, data)
    - FAIL: Item failed at least one health check stage
    - UNKNOWN: Default state for new items or when refresh encountered errors
    
    Usage: Stored in watchlistitems.last_refresh_status and drives status derivation logic
    in the watchlist status engine. Also used in InternalBatchUpdateStatusItem for legacy flow.
    """
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"

class WatchlistStatus(str, Enum):
    """
    UI-facing status labels derived from last_refresh_status and VCP/pivot/volume signals.
    
    Values must align with the status derivation logic in monitoring-service's
    watchlist_status_service.py.
    
    Values:
    - Pending: Not yet analyzed or refresh in progress
    - Failed: Failed health check
    - Watch: Passed health check but no actionable setup
    - Buy Alert: Passed with maturing VCP pattern or pullback setup
    - Buy Ready: Passed with pivot proximity within buy band
    """
    PENDING = "Pending"
    FAILED = "Failed"
    WATCH = "Watch"
    BUY_ALERT = "Buy Alert"
    BUY_READY = "Buy Ready"

class JobStatus(str, Enum):
    """
    Lifecycle status for asynchronous jobs.
    """
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class JobType(str, Enum):
    """
    Types of background jobs orchestrated by the scheduler.
    """
    SCREENING = "SCREENING"
    WATCHLIST_REFRESH = "WATCHLIST_REFRESH"
# --- Contract 1: TickerList ---
TickerList: TypeAlias = List[str]
"""A simple list of stock ticker symbols (e.g., ["AAPL", "MSFT"])."""

# --- Contract 2: PriceData ---
class PriceDataItem(BaseModel):
    """Represents a single time-series data point for a stock."""
    formatted_date: str
    open: Optional[float] = None # as some tickers have no data during the period, ie CNFRZ, USBC
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    adjclose: Optional[float] = None


# --- Contract 3: CoreFinancials ---
class EarningItem(BaseModel):
    """Represents a single earnings report (annual or quarterly)."""
    Revenue: Optional[float] = None # Make optional to handle sparse data
    Earnings: Optional[float] = None # Make optional and float
    Net_Income: Optional[float] = Field(None, alias='Net Income')

class QuarterlyFinancialItem(BaseModel):
    """Represents a single quarterly financial report for net income calculations."""
    Net_Income: Optional[float] = Field(None, alias='Net Income')
    Total_Revenue: Optional[float] = Field(None, alias='Total Revenue')

class CoreFinancials(BaseModel):
    """Essential fundamental data for the Leadership screen."""
    ticker: str
    marketCap: Optional[float] = 0
    sharesOutstanding: Optional[float] = 0
    floatShares: Optional[float] = 0
    industry: Optional[str] = None
    ipoDate: Optional[str] = None
    annual_earnings: List[EarningItem]
    quarterly_earnings: List[EarningItem]
    quarterly_financials: List[QuarterlyFinancialItem]

# --- Contract 4: NewsData ---
class NewsDataItem(BaseModel):
    """Represents a single news article."""
    uuid: str
    title: str
    description: str
    url: str
    source: str
    published_at: str


# --- Contract 5: IndustryPeers ---
class IndustryPeers(BaseModel):
    """Industry classification and peer companies for a ticker."""
    industry: Optional[str] = None
    peers: List[str]


# --- Contract 6: ScreeningResult ---
class ScreeningResultSingle(BaseModel):
    """Detailed breakdown of the SEPA trend screen for one ticker."""
    ticker: str
    passes: bool
    details: Dict[str, bool]


# --- Contract 7: VCPAnalysis ---
class VCPAnalysisBatchItem(BaseModel):
    """Lean result for a single ticker from a batch VCP analysis."""
    ticker: str
    vcp_pass: bool
    vcpFootprint: str = Field(
        ...,
        description="SEPA Signature (e.g., '40W-31/3-4T') followed by raw contraction details."
    )

class VCPContractionItem(BaseModel):
    """
    Latest Add:
    Represents a single contraction ("T") within a detected VCP pattern.
    Used for granular visualization on the frontend.
    """
    start_date: str = Field(..., description="Date of the contraction peak")
    start_price: float = Field(..., description="Price at the contraction peak")
    end_date: str = Field(..., description="Date of the contraction trough")
    end_price: float = Field(..., description="Price at the contraction trough")
    depth_percent: float = Field(..., description="Percentage depth of this contraction (0.0 to 1.0)")

class VCPChartData(BaseModel):
    """Data required for visualizing the VCP chart."""
    detected: bool
    # vcpLines is deprecated in favor of vcpContractions but kept for backward compatibility if needed
    vcpLines: List[Dict[str, Any]]
    # New fields for specific visualization
    vcpContractions: Optional[List[VCPContractionItem]] = None
    pivotPrice: Optional[float] = None
    
    # Diagnostic fields for visualization
    vcp_pass: Optional[bool] = Field(None, description="Pass/Fail status specific to the chart context")
    rejection_reason: Optional[str] = Field(None, description="Concise reason for VCP failure")

    buyPoints: List[Dict[str, Any]]
    sellPoints: List[Dict[str, Any]]
    ma20: List[Dict[str, Any]]
    ma50: List[Dict[str, Any]]
    ma150: List[Dict[str, Any]]
    ma200: List[Dict[str, Any]] 
    historicalData: List[Dict[str, Any]]


class VCPDetailCheck(BaseModel):
    """Represents the pass/fail status of a specific VCP validation."""
    model_config = ConfigDict(populate_by_name=True)
    passes: bool = Field(..., alias='pass')
    message: str

class VCPDetails(BaseModel):
    """Detailed breakdown of VCP validation checks."""
    pivot_validation: VCPDetailCheck
    volume_validation: VCPDetailCheck = Field(
        ...,
        description="Validates if volume dries up at the pivot (contracts below 50D avg)."
    )


class VCPAnalysisSingle(BaseModel):
    """Rich result object for a single-ticker VCP analysis."""
    ticker: str
    vcp_pass: bool
    vcpFootprint: str = Field(
        ...,
        description="SEPA Signature (e.g., '40W-31/3-4T') followed by raw contraction details."
    )
    chart_data: VCPChartData
    vcp_details: Optional[VCPDetails] = None


# --- Contract 8: LeadershipProfile ---
class LeadershipMetricDetail(BaseModel):
    """Represents the pass/fail status of a single leadership metric."""
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    passes: bool = Field(..., alias='pass')
    message: str


class LeadershipProfileMetadata(BaseModel):
    """Execution metadata for a leadership screen."""
    execution_time: float

class LeadershipSummary(BaseModel):
    qualified_profiles: List[str]
    message: str

class ProfileDetail(BaseModel):
    pass_status: bool = Field(..., alias='pass') # Use alias to allow 'pass' as field name
    passed_checks: int
    total_checks: int

    model_config = ConfigDict(populate_by_name=True)

class LeadershipProfileSingle(BaseModel):
    """Detailed breakdown of the leadership screen for one ticker."""
    ticker: str
    passes: bool  # The overall pass/fail flag
    leadership_summary: LeadershipSummary
    profile_details: Dict[str, ProfileDetail]
    details: Dict[str, LeadershipMetricDetail]
    industry: Optional[str] = None
    metadata: LeadershipProfileMetadata


class LeadershipProfileForBatch(BaseModel):
    """Schema for candidates inside the leadership batch result."""
    ticker: str
    passes: bool
    leadership_summary: LeadershipSummary
    profile_details: Dict[str, ProfileDetail]
    industry: Optional[str] = None


class LeadershipProfileBatchMetadata(BaseModel):
    """Execution metadata for a batch leadership screen."""
    total_processed: int
    total_passed: int
    execution_time: float


class LeadershipProfileBatch(BaseModel):
    """Result object for a batch leadership screen."""
    passing_candidates: List[LeadershipProfileForBatch]
    unique_industries_count: int
    metadata: LeadershipProfileBatchMetadata

# --- Contract 9: ScreeningJobResult ---
class FinalCandidate(BaseModel):
    """Represents a final, fully screened candidate stock."""
    ticker: str
    vcp_pass: bool
    vcpFootprint: str
    leadership_results: Dict[str, Any]


class IndustryDiversity(BaseModel):
    """Summary of industry representation in final results."""
    unique_industries_count: int


class ScreeningJobResult(BaseModel):
    """Summary document for a completed screening pipeline run."""
    job_id: str
    processed_at: datetime
    total_process_time: float
    total_tickers_fetched: int
    trend_screen_survivors_count: int
    vcp_survivors_count: int
    final_candidates_count: int
    industry_diversity: IndustryDiversity
    final_candidates: List[FinalCandidate]


# --- Contract 10: MarketHealth ---
class MarketOverview(BaseModel):
    """Market health overview data."""
    market_stage: Literal['Bullish', 'Bearish', 'Neutral', 'Recovery'] = Field(..., description="Market stage per UI contract.")
    correction_depth_percent: float = Field(..., description="The depth of the current market correction as a percentage.")
    high_low_ratio: float = Field(..., description="Ratio of 52-week highs to 52-week lows.")
    new_highs: int = Field(..., description="Absolute count of stocks making new 52-week highs.")
    new_lows: int = Field(..., description="Absolute count of stocks making new 52-week lows.")
    as_of_date: datetime = Field(
        ..., 
        description="The timestamp (UTC) representing when this market snapshot was valid or generated."
    )

class LeadingStock(BaseModel):
    """Represents a leading stock."""
    ticker: str
    percent_change_3m: Optional[float] = Field(None, description="3-month percentage return")

class LeadingIndustry(BaseModel):
    """Represents a leading industry with its leading stocks, creates the nested structure"""
    industry: str
    stock_count: int  # Number of stocks contributing to this industry's leadership
    stocks: List[LeadingStock]

class MarketLeaders(BaseModel):
    """List of ranked industries"""
    leading_industries: List[LeadingIndustry]


class MarketHealthResponse(BaseModel):
    """The complete data payload for the /market page, served by the monitoring-service."""
    market_overview: MarketOverview
    leaders_by_industry: MarketLeaders
    # Full analysis data for major indices to render charts
    indices_analysis: Optional[Dict[str, VCPAnalysisSingle]] = None

# --- Contract 11: MarketBreadth ---
class MarketBreadthResponse(BaseModel):
    """The data payload for market breadth, served by the data-service."""
    new_highs: int
    new_lows: int
    high_low_ratio: float

# --- Contract 12: IndustryBreadth ---
class IndustryBreadthItem(BaseModel):
    industry: str
    breadth_count: int

# --- Contract 13: ScreenerQuote ---

class ScreenerQuote(BaseModel):
    """
    A minimal screener quote shape returned by data-service for 52-week highs.
    This projection intentionally limits fields to what downstream services use.
    """
    symbol: str
    industry: Optional[str] = None
    shortName: Optional[str] = None
    sector: Optional[str] = None
    regularMarketPrice: Optional[float] = None
    fiftyTwoWeekHigh: Optional[float] = None
    fiftyTwoWeekHighChangePercent: Optional[float] = None
    marketCap: Optional[float] = None

ScreenerQuoteList: TypeAlias = List[ScreenerQuote]

# --- Contract 14: Requests: Watchlist/Archive ---

class BatchRemoveRequest(BaseModel):
    tickers: List[str]

class WatchlistBatchRemoveRequest(BatchRemoveRequest):
    """
    Request body for POST /monitor/watchlist/batch/remove.

    Alias around BatchRemoveRequest to keep internal and public semantics aligned.
    """
    model_config = ConfigDict(populate_by_name=True)

class InternalBatchAddRequest(BaseModel):
    tickers: List[str]

class WatchlistItem(BaseModel):
    """
    Represents a single watchlist item in GET /monitor/watchlist response
    Aligns with Phase 2 UI interface requirements
    """
    ticker: str = Field(..., description="Stock symbol")
    status: WatchlistStatus = Field(..., description="Derived status: Pending, Failed, Buy Ready, Buy Alert, Watch")
    date_added: Optional[datetime] = Field(None, description="When ticker was added to watchlist")
    is_favourite: bool = Field(False, description="Whether user marked as favourite")
    last_refresh_status: LastRefreshStatus = Field(..., description="Health check status enum")
    last_refresh_at: Optional[datetime] = Field(None, description="Last health check timestamp")
    failed_stage: Optional[str] = Field(None, description="Stage where health check failed")
    current_price: Optional[float] = Field(None, description="Latest price from refresh job")
    pivot_price: Optional[float] = Field(None, description="VCP pivot price if identified")
    pivot_proximity_percent: Optional[float] = Field(None, description="% from pivot (negative=below)")
    is_leader: bool = Field(False, description="Whether passed leadership criteria")
    vol_last: Optional[float] = Field(
        None,
        description="Most recent session's volume for this ticker"
    )
    vol_50d_avg: Optional[float] = Field(
        None,
        description="Average volume over the last 50 trading sessions"
    )
    vol_vs_50d_ratio: Optional[float] = Field(
        None,
        description="Ratio of current volume to 50D average (e.g., 2.1 = 2.1x)"
    )
    day_change_pct: Optional[float] = Field(
        None,
        description="Last session price change in percent vs prior close"
    )
    # VCP Pattern Fields
    vcp_pass: Optional[bool] = Field(None, description="Overall VCP validation result")
    vcpFootprint: Optional[str] = Field(None, description="VCP pattern signature (e.g., '10D 5.2% | 13D 5.0%')")
    is_pivot_good: Optional[bool] = Field(None, description="Pivot quality flag from VCP analysis")
    pattern_age_days: Optional[int] = Field(None, description="Days since VCP pattern formation")
    
    # Pivot Setup Flags
    has_pivot: Optional[bool] = Field(None, description="Whether a valid pivot point exists")
    is_at_pivot: Optional[bool] = Field(None, description="Price is at or near the pivot")
    has_pullback_setup: Optional[bool] = Field(None, description="Controlled pullback setup detected")
    days_since_pivot: Optional[int] = Field(None, description="Days since pivot formation (freshness counter)")
    
    # Freshness Check
    fresh: Optional[bool] = Field(None, description="Passes freshness threshold (typically < 90 days)")
    message: Optional[str] = Field(None, description="Human-readable explanation of status/freshness")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ticker": "NVDA",
                "status": "Buy Ready",
                "date_added": "2025-09-20T10:00:00Z",
                "is_favourite": False,
                "last_refresh_status": "PASS",
                "last_refresh_at": "2025-11-01T12:00:00Z",
                "failed_stage": None,
                "current_price": 850.00,
                "pivot_price": 855.00,
                "pivot_proximity_percent": -0.58,
                "is_leader": True,
                "vol_last": 317900.0,
                "vol_50d_avg": 250000.0,
                "vol_vs_50d_ratio": 1.27,
                "day_change_pct": -0.35,
                "vcp_pass": True,
                "vcpFootprint": "10D 5.2% | 13D 5.0% | 10D 6.2%",
                "is_pivot_good": True,
                "pattern_age_days": 15,
                "has_pivot": True,
                "is_at_pivot": True,
                "has_pullback_setup": False,
                "days_since_pivot": 15,
                "fresh": True,
                "message": "Pivot is fresh (formed 15 days ago) and is not extended."
            }
        }
    )

class WatchlistMetadata(BaseModel):
    """Metadata for watchlist response"""
    count: int = Field(..., description="Total number of watchlist items returned")

class WatchlistListResponse(BaseModel):
    """
    Response schema for GET /monitor/watchlist
    Represents the complete watchlist with metadata
    """
    items: List[WatchlistItem] = Field(..., description="List of watchlist items")
    metadata: WatchlistMetadata = Field(..., description="Response metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "ticker": "NVDA",
                        "status": "Buy Ready",
                        "date_added": "2025-09-20T10:00:00Z",
                        "is_favourite": False,
                        "last_refresh_status": "PASS",
                        "last_refresh_at": "2025-11-01T12:00:00Z",
                        "failed_stage": None,
                        "current_price": 850.00,
                        "pivot_price": 855.00,
                        "pivot_proximity_percent": -0.58,
                        "is_leader": True,
                        "vol_last": 317900.0,
                        "vol_50d_avg": 250000.0,
                        "vol_vs_50d_ratio": 1.27,
                        "day_change_pct": -0.35,
                    }
                ],
                "metadata": {"count": 1}
            }
        }
    )

# generic shape (keeps service-specific fields flexible)

class ArchiveListResponse(BaseModel):
    archived_items: List[Dict[str, Any]]
    metadata: WatchlistMetadata

class WatchlistBatchRemoveResponse(BaseModel):
    """
    Success payload for POST /monitor/watchlist/batch/remove.

    - removed: number of tickers successfully removed
    - notfound: number of requested tickers not found in the watchlist
    - removed_tickers: list of tickers actually removed (for UI detail)
    - not_found_tickers: list of tickers requested but not present
    - message: human-readable summary for UI display
    """
    message: str = Field(..., description="Summary message including key tickers")
    removed: StrictInt = Field(..., description="Number of tickers successfully removed")
    notfound: StrictInt = Field(..., description="Number of requested tickers not found")
    removed_tickers: List[str] = Field(
        default_factory=list,
        description="Tickers actually removed in this batch",
    )
    not_found_tickers: List[str] = Field(
        default_factory=list,
        description="Tickers requested but not found in the watchlist",
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "message": "Removed 1 watchlist item. Not found: 0. Sample: AAPL",
                "removed": 1,
                "notfound": 0,
                "removed_tickers": ["AAPL"],
                "not_found_tickers": [],
            }
        },
    )

class InternalBatchAddResponse(BaseModel):
    """
    Success payload for POST /monitor/internal/watchlist/batch/add.

    Exposes only an aggregate message and counts; internal arrays (added/ skipped
    ticker lists, errors) remain service-internal and are not part of the contract.
    """
    message: str = Field(..., description="Summary message including key tickers")
    added: StrictInt = Field(..., description="Number of tickers newly added to the watchlist")
    skipped: StrictInt = Field(..., description="Number of tickers that already existed and were skipped")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "message": "Batch add completed: added 2, skipped 1. Sample: AAPL, MSFT",
                "added": 2,
                "skipped": 1,
            },
        },
    )

# --- Contract 16: Freshness: Analyze batch ---

class AnalyzeFreshnessBatchRequest(BaseModel):
    tickers: List[str]

class AnalyzeFreshnessBatchItem(BaseModel):
    """
    Freshness result from analysis-service /analyze/freshness/batch.

    - Producer: analysis-service
    - Consumer: monitoring-service, scheduler-service
    """
    ticker: str

    # Primary boolean used by orchestrators
    fresh: bool = Field(..., alias="passes_freshness_check")

    # Richer context for status logic (all optional, extra='allow' for forward-compat)
    vcp_detected: Optional[bool] = None
    days_since_pivot: Optional[int] = None
    message: Optional[str] = None
    vcpFootprint: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")

# --- Contract 17: Ticker Validation ---
MAX_TICKER_LEN: int = 10
"""Maximum allowed length for stock ticker symbols in path parameters and requests."""

class TickerPathParam(BaseModel):
    """
    Path parameter validation for ticker symbols.
    Enforces format constraints: uppercase letters, digits, dot, hyphen only; length 1-10.
    Case normalization is handled by service/route layers, not this contract.
    """
    ticker: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TICKER_LEN,
        pattern=r"^[A-Za-z0-9.\-]+$",
        description="Stock ticker symbol (1-10 chars, letters/digits/dot/hyphen only)"
    )
# --- Contract 18: Generic Error Response ---
class ApiError(BaseModel):
    """
    Standard error response envelope for all API error conditions.
    Used for 400 Bad Request, 404 Not Found, 503 Service Unavailable, etc.
    """
    error: str = Field(..., description="Human-readable error message")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"error": "Invalid ticker format"},
                {"error": "Ticker not found"},
                {"error": "Service unavailable"}
            ]
        }
    )
# --- Contract 19: Responses: DELETE /monitor/archive/:ticker ---
class DeleteArchiveResponse(BaseModel):
    """
    Success response for DELETE /monitor/archive/:ticker (Hard Delete).
    Returns only a message string; internal fields (archived_at, reason, failed_stage) are not exposed.
    """
    message: str = Field(..., description="Confirmation message including the deleted ticker")

    model_config = ConfigDict(
        extra="forbid",  # Reject any additional fields to prevent internal leakage
        json_schema_extra={
            "example": {"message": "Archived ticker AAPL permanently deleted."}
        }
    )

# --- Contract 19: Responses: Watchlist Favourite ---
class WatchlistFavouriteRequest(BaseModel):
    """
    Request body for POST /monitor/watchlist/<ticker>/favourite
    """
    is_favourite: StrictBool = Field(..., alias="is_favourite")
    model_config = ConfigDict(populate_by_name=True)

# Success response must be message-only and forbid extra fields
class WatchlistFavouriteResponse(BaseModel):
    """
    Success payload for POST /monitor/watchlist/<ticker>/favourite
    """
    message: str
    model_config = ConfigDict(extra="forbid")

# --- Contract 20: Responses: Watchlist refresh orchestrator ---
class WatchlistRefreshStatusResponse(BaseModel):
    """
    Success payload for POST /monitor/internal/watchlist/refresh-status.

    Exposes only an aggregate message and counts for:
    - updated_items: number of watchlist items updated in place (List A)
    - archived_items: number of items moved from watchlistitems to archived_watchlist_items (List B)
    - failed_items: number of items that failed processing in this run
    """

    message: str = Field(
        ...,
        description="Summary message including counts and sample tickers for traceability",
    )
    updated_items: StrictInt = Field(
        ...,
        description="Number of watchlist items whose status was updated in place",
    )
    archived_items: StrictInt = Field(
        ...,
        description="Number of watchlist items moved to archive in this run",
    )
    failed_items: StrictInt = Field(
        ...,
        description="Number of items that failed to process due to downstream/service errors",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "message": "Watchlist status refresh completed successfully.",
                "updated_items": 32,
                "archived_items": 5,
                "failed_items": 0,
            }
        },
    )

# --- Contract 21: Responses: Watchlist Summary metrics ---
class WatchlistMetricsItem(BaseModel):
    """
    Summary metrics for a watchlist ticker, computed by data-service.
    """
    current_price: Optional[float] = None
    vol_last: Optional[float] = None
    vol_50d_avg: Optional[float] = None
    day_change_pct: Optional[float] = None  # last session % change vs prior close

class WatchlistMetricsBatchResponse(BaseModel):
    """
    Response for POST /data/watchlist-metrics/batch.
    Mapping of ticker -> metrics.
    """
    metrics: Dict[str, WatchlistMetricsItem]

# --- Contract 22: Async Job Models (Week 10) ---

class JobProgressEvent(BaseModel):
    """
    Canonical SSE event payload for job progress streaming.
    Strictly adheres to snake_case and ISO 8601 UTC ('Z') formatting.
    """
    job_id: str
    job_type: str  # String to allow flexibility, typically matches JobType enum
    status: str    # String, typically matches JobStatus enum
    step_current: int
    step_total: int
    step_name: str
    message: str
    updated_at: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "job_id": "job-123-uuid",
                "job_type": "SCREENING",
                "status": "RUNNING",
                "step_current": 2,
                "step_total": 5,
                "step_name": "vcp_analysis",
                "message": "Processed 50/100 tickers",
                "updated_at": "2026-01-18T12:00:00Z"
            }
        }
    )

    @field_serializer('updated_at')
    def serialize_dt(self, dt: datetime, _info):
        """
        Enforce 'Z' suffix for UTC datetimes instead of +00:00.
        Essential for strict SSE client compatibility.
        """
        if dt.tzinfo is None:
            # Assume UTC if naive, though tests should provide aware datetimes
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


class ScreeningJobRunRecord(BaseModel):
    """
    Persistence model for the lifecycle of a screening or maintenance job.
    Stored in the 'screening_jobs' MongoDB collection.
    
    Supports 'Split Persistence':
    - Lifecycle fields (status, timestamps) are top-level.
    - Result metrics are nested in 'result_summary'.
    - Large survivor lists are nested in 'results'.
    """
    job_id: str
    job_type: str = "SCREENING"
    status: str = "PENDING"
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Configuration inputs
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    # Error tracking
    error_message: Optional[str] = None
    error_step: Optional[str] = None
    
    # Progress snapshot (subset of JobProgressEvent for quick DB lookups)
    progress_snapshot: Optional[Dict[str, Any]] = None
    progress_log: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

    # Week 10: Nested Results (Split Persistence)
    # detailed survivor lists
    results: Optional[Dict[str, List[str]]] = None
    # ScreeningJobResult dump (metrics)
    result_summary: Optional[Dict[str, Any]] = None

    # Legacy / Compatibility fields (Top-level metrics duplication)
    # These may be populated for backward compatibility with existing dashboards
    total_tickers_fetched: Optional[int] = None
    trend_screen_survivors_count: Optional[int] = None
    vcp_survivors_count: Optional[int] = None
    final_candidates_count: Optional[int] = None

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore" # Allow schema evolution without breaking readers
    )

class JobCompleteEvent(BaseModel):
    """
    SSE event payload emitted when a job finishes successfully.
    """
    job_id: str
    job_type: str
    status: Literal["SUCCESS"] = "SUCCESS"
    completed_at: datetime
    summary_counts: Optional[Dict[str, int]] = None

    @field_serializer('completed_at')
    def serialize_dt(self, dt: datetime, _info):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

class JobErrorEvent(BaseModel):
    """
    SSE event payload emitted when a job fails.
    """
    job_id: str
    job_type: str
    status: Literal["FAILED"] = "FAILED"
    error_message: str
    completed_at: datetime

    @field_serializer('completed_at')
    def serialize_dt(self, dt: datetime, _info):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')