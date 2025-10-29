# backend-services/shared/contracts.py
"""
This module defines the Pydantic models that serve as the formal data contracts
for all inter-service communication in the SEPA Stock Screener backend.

These models ensure data consistency, provide automatic validation, and act as
living documentation for the data structures exchanged between microservices.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, TypeAlias, Literal 
from pydantic import BaseModel, ConfigDict, Field

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
    vcpFootprint: str


class VCPChartData(BaseModel):
    """Data required for visualizing the VCP chart."""
    detected: bool
    vcpLines: List[Dict[str, Any]]
    buyPoints: List[Dict[str, Any]]
    sellPoints: List[Dict[str, Any]]
    ma50: List[Dict[str, Any]]
    historicalData: List[Dict[str, Any]]


class VCPDetailCheck(BaseModel):
    """Represents the pass/fail status of a specific VCP validation."""
    model_config = ConfigDict(populate_by_name=True)
    passes: bool = Field(..., alias='pass')
    message: str

class VCPDetails(BaseModel):
    """Detailed breakdown of VCP validation checks."""
    pivot_validation: VCPDetailCheck
    volume_validation: VCPDetailCheck


class VCPAnalysisSingle(BaseModel):
    """Rich result object for a single-ticker VCP analysis."""
    ticker: str
    vcp_pass: bool
    vcpFootprint: str
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

class LeadingStock(BaseModel):
    """Represents a leading stock."""
    ticker: str
    percent_change_3m: Optional[float] = Field(None, description="3-month percentage return")

class LeadingIndustry(BaseModel):
    """Represents a leading industry with its leading stocks, creates the nested structure"""
    industry: str
    stocks: List[LeadingStock]

class MarketLeaders(BaseModel):
    """List of ranked industries"""
    leading_industries: List[LeadingIndustry]


class MarketHealthResponse(BaseModel):
    """The complete data payload for the /market page, served by the monitoring-service."""
    market_overview: MarketOverview
    leaders_by_industry: MarketLeaders

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