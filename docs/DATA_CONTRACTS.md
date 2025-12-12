# Data Contracts

This document serves as the single source of truth for the data structures exchanged between the microservices in the SEPA Stock Screener backend. Adhering to these contracts is mandatory to ensure system reliability and maintainability.

All contracts are defined using Pydantic models in `backend-services/shared/contracts.py`. This provides runtime data validation and acts as living documentation. Below are the formal JSON Schema representations for each contract.

---

## 1. TickerList

A simple list of stock ticker symbols.

-   **Producer:** `ticker-service`
-   **Consumer:** `scheduler-service`, `screening-service`
-   **Pydantic Model:** `TickerList` (TypeAlias for `List[str]`)
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
-   **Pydantic Model:** `List[PriceDataItem]`
-   **Description:** This is the primary data object used for all quantitative analysis. The data is sorted by date in ascending order (oldest to newest).
-   **JSON Schema (for each item in the list):**
    ```json
    {
      "title": "PriceDataItem",
      "type": "object",
      "properties": {
        "formatted_date": {
          "title": "Formatted Date",
          "type": "string"
        },
        "open": {
          "title": "Open",
          "type": ["number", "null"]
        },
        "high": {
          "title": "High",
          "type": ["number", "null"]
        },
        "low": {
          "title": "Low",
          "type": ["number", "null"]
        },
        "close": {
          "title": "Close",
          "type": ["number", "null"]
        },
        "volume": {
          "title": "Volume",
          "type": ["integer", "null"]
        },
        "adjclose": {
          "title": "Adjclose",
          "type": ["number", "null"]
        }
      },
      "required": ["formatted_date"]
    }
    ```

---

## 3. CoreFinancials

Provides essential, high-level fundamental data points for a single stock ticker, used for the leadership screening phase.

-   **Producer:** `data-service`
-   **Consumer:** `leadership-service`
-   **Pydantic Model:** `CoreFinancials`
-   **Description:** A lean data object designed for the "Just-in-Time" data retrieval strategy. It is only fetched for stocks that have already passed the initial trend and VCP screens. The `quarterly_earnings` list focuses on EPS-related data, while `quarterly_financials` provides broader income statement figures like total revenue.
-   **JSON Schema:**
    ```json
    {
      "title": "CoreFinancials",
      "type": "object",
      "properties": {
        "ticker": { "title": "Ticker", "type": "string" },
        "marketCap": { "title": "Marketcap", "type": ["number", "null"], "default": 0 },
        "sharesOutstanding": { "title": "Sharesoutstanding", "type": ["number", "null"], "default": 0 },
        "floatShares": { "title": "Floatshares", "type": ["number", "null"], "default": 0 },
        "industry": { "title": "Industry", "type": ["string", "null"] },
        "ipoDate": { "title": "Ipodate", "type": ["string", "null"] },
        "annual_earnings": {
          "title": "Annual Earnings",
          "type": "array",
          "items": { "$ref": "#/definitions/EarningItem" }
        },
        "quarterly_earnings": {
          "title": "Quarterly Earnings",
          "type": "array",
          "items": { "$ref": "#/definitions/EarningItem" }
        },
        "quarterly_financials": {
          "title": "Quarterly Financials",
          "type": "array",
          "items": { "$ref": "#/definitions/QuarterlyFinancialItem" }
        }
      },
      "required": ["ticker", "annual_earnings", "quarterly_earnings", "quarterly_financials"],
      "definitions": {
        "EarningItem": {
          "title": "EarningItem",
          "type": "object",
          "properties": {
            "Revenue": { "title": "Revenue", "type": ["number", "null"] },
            "Earnings": { "title": "Earnings", "type": ["number", "null"] },
            "Net Income": { "title": "Net Income", "type": ["number", "null"] }
          }
        },
        "QuarterlyFinancialItem": {
            "title": "QuarterlyFinancialItem",
            "type": "object",
            "properties": {
                "Net Income": { "title": "Net Income", "type": ["number", "null"] },
                "Total Revenue": { "title": "Total Revenue", "type": ["number", "null"] }
            }
        }
      }
    }
    ```

---

## 4. NewsData

A list of recent news articles for a specific ticker.

-   **Producer:** `data-service`
-   **Consumer(s):** `ranking-service`, `frontend-app`
-   **Pydantic Model:** `List[NewsDataItem]`
-   **Description:** Provides news context for a stock, intended for qualitative analysis or for display in the UI.
-   **JSON Schema (for each item in the list):**
    ```json
    {
      "title": "NewsDataItem",
      "type": "object",
      "properties": {
        "uuid": { "title": "Uuid", "type": "string" },
        "title": { "title": "Title", "type": "string" },
        "description": { "title": "Description", "type": "string" },
        "url": { "title": "Url", "type": "string" },
        "source": { "title": "Source", "type": "string" },
        "published_at": { "title": "Published At", "type": "string" }
      },
      "required": ["uuid", "title", "description", "url", "source", "published_at"]
    }
    ```

---

## 5. IndustryPeers

Provides the industry classification and a list of peer companies for a given ticker.

-   **Producer:** `data-service`
-   **Consumer(s):** `leadership-service`
-   **Pydantic Model:** `IndustryPeers`
-   **Description:** Used by the leadership service to perform relative strength and leadership analysis within a stock's specific industry group.
-   **JSON Schema:**
    ```json
    {
      "title": "IndustryPeers",
      "type": "object",
      "properties": {
        "industry": { "title": "Industry", "type": ["string", "null"] },
        "peers": {
          "title": "Peers",
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "required": ["peers"]
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
-   **Batch Pydantic Model:** `List[str]`
-   **Single Ticker Pydantic Model:** `ScreeningResultSingle`
-   **JSON Schema (for single ticker):**
    ```json
    {
      "title": "ScreeningResultSingle",
      "type": "object",
      "properties": {
        "ticker": { "title": "Ticker", "type": "string" },
        "passes": { "title": "Passes", "type": "boolean" },
        "details": {
          "title": "Details",
          "type": "object",
          "additionalProperties": { "type": "boolean" }
        }
      },
      "required": ["ticker", "passes", "details"]
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
-   **Batch Pydantic Model:** `List[VCPAnalysisBatchItem]`
-   **Single Ticker Pydantic Model:** `VCPAnalysisSingle`
-   **JSON Schema (for single ticker):**
    ```json
    {
      "title": "VCPAnalysisSingle",
      "type": "object",
      "properties": {
        "ticker": { "title": "Ticker", "type": "string" },
        "vcp_pass": { "title": "Vcp Pass", "type": "boolean" },
        "vcpFootprint": { "title": "Vcpfootprint", "type": "string" },
        "chart_data": { "$ref": "#/definitions/VCPChartData" },
        "vcp_details": {
          "anyOf": [{ "$ref": "#/definitions/VCPDetails" }, { "type": "null" }]
        }
      },
      "required": ["ticker", "vcp_pass", "vcpFootprint", "chart_data"],
      "definitions": {
        "VCPChartData": {
          "title": "VCPChartData",
          "type": "object",
          "properties": {
            "detected": { "title": "Detected", "type": "boolean" },
            "vcpLines": { "title": "Vcplines", "type": "array", "items": { "type": "object" }},
            "buyPoints": { "title": "Buypoints", "type": "array", "items": { "type": "object" }},
            "sellPoints": { "title": "Sellpoints", "type": "array", "items": { "type": "object" }},
            "ma50": { "title": "Ma50", "type": "array", "items": { "type": "object" }},
            "historicalData": { "title": "Historicaldata", "type": "array", "items": { "type": "object" }}
          },
          "required": ["detected", "vcpLines", "buyPoints", "sellPoints", "ma50", "historicalData"]
        },
        "VCPDetailCheck": {
          "title": "VCPDetailCheck",
          "type": "object",
          "properties": {
            "pass": { "title": "Pass", "type": "boolean" },
            "message": { "title": "Message", "type": "string" }
          },
          "required": ["pass", "message"]
        },
        "VCPDetails": {
          "title": "VCPDetails",
          "type": "object",
          "properties": {
            "pivot_validation": { "$ref": "#/definitions/VCPDetailCheck" },
            "volume_validation": { "$ref": "#/definitions/VCPDetailCheck" }
          },
          "required": ["pivot_validation", "volume_validation"]
        }
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
-   **Batch Pydantic Model:** `LeadershipProfileBatch`
-   **Single Ticker Pydantic Model:** `LeadershipProfileSingle`
-   **JSON Schema (for single ticker):**
    ```json
    {
      "title": "LeadershipProfileSingle",
      "type": "object",
      "properties": {
        "ticker": { "title": "Ticker", "type": "string" },
        "passes": { "title": "Passes", "type": "boolean" },
        "leadership_summary": { "$ref": "#/definitions/LeadershipSummary" },
        "profile_details": {
          "title": "Profile Details",
          "type": "object",
          "additionalProperties": { "$ref": "#/definitions/ProfileDetail" }
        },
        "details": {
          "title": "Details",
          "type": "object",
          "additionalProperties": { "$ref": "#/definitions/LeadershipMetricDetail" }
        },
        "industry": { "title": "Industry", "type": ["string", "null"] },
        "metadata": { "$ref": "#/definitions/LeadershipProfileMetadata" }
      },
      "required": ["ticker", "passes", "leadership_summary", "profile_details", "details", "metadata"],
      "definitions": {
        "LeadershipSummary": {
          "title": "LeadershipSummary",
          "type": "object",
          "properties": {
            "qualified_profiles": {
              "title": "Qualified Profiles",
              "type": "array",
              "items": { "type": "string" }
            },
            "message": { "title": "Message", "type": "string" }
          },
          "required": ["qualified_profiles", "message"]
        },
        "ProfileDetail": {
          "title": "ProfileDetail",
          "type": "object",
          "properties": {
            "pass": { "title": "Pass", "type": "boolean" },
            "passed_checks": { "title": "Passed Checks", "type": "integer" },
            "total_checks": { "title": "Total Checks", "type": "integer" }
          },
          "required": ["pass", "passed_checks", "total_checks"]
        },
        "LeadershipMetricDetail": {
          "title": "LeadershipMetricDetail",
          "type": "object",
          "properties": {
            "pass": { "title": "Pass", "type": "boolean" },
            "message": { "title": "Message", "type": "string" }
          },
          "required": ["pass", "message"]
        },
        "LeadershipProfileMetadata": {
          "title": "LeadershipProfileMetadata",
          "type": "object",
          "properties": {
            "execution_time": { "title": "Execution Time", "type": "number" }
          },
          "required": ["execution_time"]
        }
      }
    }
    ```
-   **JSON Schema (for batch response):**
    ```json
    {
        "title": "LeadershipProfileBatch",
        "type": "object",
        "properties": {
            "passing_candidates": {
                "title": "Passing Candidates",
                "type": "array",
                "items": {
                    "$ref": "#/definitions/LeadershipProfileForBatch"
                }
            },
            "unique_industries_count": {
                "title": "Unique Industries Count",
                "type": "integer"
            },
            "metadata": {
                "$ref": "#/definitions/LeadershipProfileBatchMetadata"
            }
        },
        "required": [
            "passing_candidates",
            "unique_industries_count",
            "metadata"
        ],
        "definitions": {
            "LeadershipSummary": {
                "title": "LeadershipSummary",
                "type": "object",
                "properties": {
                    "qualified_profiles": {
                        "title": "Qualified Profiles",
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    },
                    "message": {
                        "title": "Message",
                        "type": "string"
                    }
                },
                "required": [
                    "qualified_profiles",
                    "message"
                ]
            },
            "ProfileDetail": {
                "title": "ProfileDetail",
                "type": "object",
                "properties": {
                    "pass": {
                        "title": "Pass",
                        "type": "boolean"
                    },
                    "passed_checks": {
                        "title": "Passed Checks",
                        "type": "integer"
                    },
                    "total_checks": {
                        "title": "Total Checks",
                        "type": "integer"
                    }
                },
                "required": [
                    "pass",
                    "passed_checks",
                    "total_checks"
                ]
            },
            "LeadershipProfileForBatch": {
                "title": "LeadershipProfileForBatch",
                "type": "object",
                "properties": {
                    "ticker": {
                        "title": "Ticker",
                        "type": "string"
                    },
                    "passes": {
                        "title": "Passes",
                        "type": "boolean"
                    },
                    "leadership_summary": {
                        "$ref": "#/definitions/LeadershipSummary"
                    },
                    "profile_details": {
                        "title": "Profile Details",
                        "type": "object",
                        "additionalProperties": {
                            "$ref": "#/definitions/ProfileDetail"
                        }
                    },
                    "industry": {
                        "title": "Industry",
                        "type": [
                            "string",
                            "null"
                        ]
                    }
                },
                "required": [
                    "ticker",
                    "passes",
                    "leadership_summary",
                    "profile_details"
                ]
            },
            "LeadershipProfileBatchMetadata": {
                "title": "LeadershipProfileBatchMetadata",
                "type": "object",
                "properties": {
                    "total_processed": {
                        "title": "Total Processed",
                        "type": "integer"
                    },
                    "total_passed": {
                        "title": "Total Passed",
                        "type": "integer"
                    },
                    "execution_time": {
                        "title": "Execution Time",
                        "type": "number"
                    }
                },
                "required": [
                    "total_processed",
                    "total_passed",
                    "execution_time"
                ]
            }
        }
    }
    ```
---

## 9. ScreeningJobResult

A summary document detailing the statistics and results of a completed screening pipeline run.

-   **Producer:** `scheduler-service`
-   **Consumer(s):** MongoDB (`screening_jobs` collection), `api-gateway`/`frontend-app`
-   **Pydantic Model:** `ScreeningJobResult`
-   **Description:** This object provides a high-level overview of the screening funnel's performance for a given run. It is stored in the database for historical analysis.
-   **JSON Schema:**
    ```json
    {
      "title": "ScreeningJobResult",
      "type": "object",
      "properties": {
        "job_id": { "title": "Job Id", "type": "string" },
        "processed_at": { "title": "Processed At", "type": "string", "format": "date-time" },
        "total_process_time": { "title": "Total Process Time", "type": "number" },
        "total_tickers_fetched": { "title": "Total Tickers Fetched", "type": "integer" },
        "trend_screen_survivors_count": { "title": "Trend Screen Survivors Count", "type": "integer" },
        "vcp_survivors_count": { "title": "Vcp Survivors Count", "type": "integer" },
        "final_candidates_count": { "title": "Final Candidates Count", "type": "integer" },
        "industry_diversity": { "$ref": "#/definitions/IndustryDiversity" },
        "final_candidates": {
          "title": "Final Candidates",
          "type": "array",
          "items": { "$ref": "#/definitions/FinalCandidate" }
        }
      },
      "required": ["job_id", "processed_at", "total_process_time", "total_tickers_fetched", "trend_screen_survivors_count", "vcp_survivors_count", "final_candidates_count", "industry_diversity", "final_candidates"],
      "definitions": {
        "FinalCandidate": {
          "title": "FinalCandidate",
          "type": "object",
          "properties": {
            "ticker": { "title": "Ticker", "type": "string" },
            "vcp_pass": { "title": "Vcp Pass", "type": "boolean" },
            "vcpFootprint": { "title": "Vcpfootprint", "type": "string" },
            "leadership_results": { "title": "Leadership Results", "type": "object" }
          },
          "required": ["ticker", "vcp_pass", "vcpFootprint", "leadership_results"]
        },
        "IndustryDiversity": {
          "title": "IndustryDiversity",
          "type": "object",
          "properties": {
            "unique_industries_count": { "title": "Unique Industries Count", "type": "integer" }
          },
          "required": ["unique_industries_count"]
        }
      }
    }
    ```
---

## 10. MarketHealth

This is the comprehensive data payload for the frontend's Market Health page, providing a full overview of market conditions and leadership trends in a single object.

-   **Producer:** `monitoring-service`
-   **Consumer(s):** `frontend-app`
-   **Pydantic Model:** `MarketHealthResponse`
-   **Description:** This contract aggregates two key pieces of information: a high-level `market_overview` (including the market stage, correction depth, and breadth indicators) and a detailed breakdown of the current market `leaders_by_industry`. This structure allows the UI to build the entire Market page from a single API call.
-   **JSON Schema:**
    ```json
    {
      "title": "MarketHealthResponse",
      "type": "object",
      "properties": {
        "market_overview": {
          "$ref": "#/definitions/MarketOverview"
        },
        "leaders_by_industry": {
          "$ref": "#/definitions/MarketLeaders"
        }
      },
      "required": [
        "market_overview",
        "leaders_by_industry"
      ],
      "definitions": {
        "MarketOverview": {
          "title": "MarketOverview",
          "type": "object",
          "properties": {
            "market_stage": {
              "description": "Market stage per UI contract.",
              "enum": [
                "Bullish",
                "Bearish",
                "Neutral",
                "Recovery"
              ],
              "type": "string"
            },
            "correction_depth_percent": {
              "description": "The depth of the current market correction as a percentage.",
              "type": "number"
            },
            "high_low_ratio": {
              "description": "Ratio of 52-week highs to 52-week lows.",
              "type": "number"
            },
            "new_highs": {
              "description": "Absolute count of stocks making new 52-week highs.",
              "type": "integer"
            },
            "new_lows": {
              "description": "Absolute count of stocks making new 52-week lows.",
              "type": "integer"
            }
          },
          "required": [
            "market_stage",
            "correction_depth_percent",
            "high_low_ratio",
            "new_highs",
            "new_lows"
          ]
        },
        "LeadingStock": {
          "title": "LeadingStock",
          "type": "object",
          "properties": {
            "ticker": {
              "type": "string"
            },
            "percent_change_3m": {
              "description": "3-month percentage return",
              "type": [
                "number",
                "null"
              ]
            }
          },
          "required": [
            "ticker"
          ]
        },
        "LeadingIndustry": {
          "title": "LeadingIndustry",
          "type": "object",
          "properties": {
            "industry": {
              "type": "string"
            },
            "stock_count": {
              "type": "integer",
              "description": "Number of stocks in this industry making new 52-week highs"
            },      
            "stocks": {
              "items": {
                "$ref": "#/definitions/LeadingStock"
              },
              "type": "array"
            }
          },
          "required": [
            "industry",
            "stocks"
          ]
        },
        "MarketLeaders": {
          "title": "MarketLeaders",
          "type": "object",
          "properties": {
            "leading_industries": {
              "items": {
                "$ref": "#/definitions/LeadingIndustry"
              },
              "type": "array"
            }
          },
          "required": [
            "leading_industries"
          ]
        }
      }
    }
    ```

---

## 11. MarketBreadth

Provides the essential market breadth statistics, specifically the number of stocks making new 52-week highs versus new 52-week lows.

-   **Producer:** `data-service`
-   **Consumer(s):** `monitoring-service`
-   **Pydantic Model:** `MarketBreadthResponse`
-   **Description:** This is a lean data object called by the `monitoring-service` to serve as a key component of its overall market health assessment. It centralizes the potentially expensive calculation of scanning all tickers for new highs/lows.
-   **JSON Schema:**
    ```json
    {
      "title": "MarketBreadthResponse",
      "type": "object",
      "properties": {
        "new_highs": {
          "title": "New Highs",
          "type": "integer"
        },
        "new_lows": {
          "title": "New Lows",
          "type": "integer"
        },
        "high_low_ratio": {
          "title": "High Low Ratio",
          "type": "number"
        }
      },
      "required": [
        "new_highs",
        "new_lows",
        "high_low_ratio"
      ]
    }
    ```

---

## 12. IndustryBreadth

Represents the leadership breadth within a specific industry by providing a count of stocks contributing to the industry's strength (e.g., number of stocks at new highs).

-   **Producer:** `data-service`
-   **Consumer(s):** `monitoring-service`
-   **Pydantic Model:** `IndustryBreadthItem`
-   **Description:** Used by the `monitoring-service` to rank industries based on the quantity of leading stocks, providing an alternative to ranking by average percentage return. This helps identify broad, durable industry-wide trends.
-   **JSON Schema:**
    ```json
    {
        "title": "IndustryBreadthItem",
        "type": "object",
        "properties": {
            "industry": {
                "title": "Industry",
                "type": "string"
            },
            "breadth_count": {
                "title": "Breadth Count",
                "type": "integer"
            }
        },
        "required": [
            "industry",
            "breadth_count"
        ]
    }
    ```

---

## 13. ScreenerQuoteList (52w highs)

A flat list of minimally projected screener quotes for stocks making 52-week highs. This is returned by the data-service and consumed by the monitoring-service to derive breadth and leadership without leaking the full upstream Yahoo response.

-   **Producer:** `data-service`
-   **Consumer(s):** `monitoring-service`
-   **Pydantic Model:** `ScreenerQuoteList` (List of `ScreenerQuote`)
-   **Description:** The projection includes only fields used by downstream computations and UI composition: `symbol`, `industry`, `shortName`, `sector`, `regularMarketPrice`, `fiftyTwoWeekHigh`, `fiftyTwoWeekHighChangePercent`, `marketCap`. Upstream fields are intentionally omitted to reduce payload and enforce a stable contract.
-   **Endpoint:** GET `/market/screener/52w_highs` (region defaults to `US`)

-   **JSON Schema (for each list item):**
  ```json
  {
  "title": "ScreenerQuote",
  "type": "object",
  "properties": {
  "symbol": { "type": "string" },
  "industry": { "type": ["string", "null"] },
  "shortName": { "type": ["string", "null"] },
  "sector": { "type": ["string", "null"] },
  "regularMarketPrice": { "type": ["number", "null"] },
  "fiftyTwoWeekHigh": { "type": ["number", "null"] },
  "fiftyTwoWeekHighChangePercent": { "type": ["number", "null"] },
  "marketCap": { "type": ["number", "null"] }
  },
  "required": ["symbol"]
  }
  ```

- **Example Payload**:
  ```json
  [
    {
    "symbol": "NVDA",
    "industry": "Semiconductors",
    "shortName": "NVIDIA Corporation",
    "sector": "Technology",
    "regularMarketPrice": 123.45,
    "fiftyTwoWeekHigh": 130.0,
    "fiftyTwoWeekHighChangePercent": -0.05,
    "marketCap": 2220000000000
    },
    {
    "symbol": "MSFT",
    "industry": "Software - Infrastructure",
    "shortName": "Microsoft Corporation",
    "sector": "Technology",
    "regularMarketPrice": 410.1,
    "fiftyTwoWeekHigh": 415.0,
    "fiftyTwoWeekHighChangePercent": -0.012,
    "marketCap": 3100000000000
    }
  ]
  ```

- **Notes**:
  - The list is already filtered for US tickers when `region=US` (the default).
  - Only the specified fields are returned to minimize payload and enforce a stable inter-service contract.

---

## 14. DeleteArchiveResponse

Success response for the DELETE /monitor/archive/:ticker endpoint (Hard Delete).

-   **Producer:** `monitoring-service`
-   **Consumer(s):** `frontend-app` (via api-gateway)
-   **Pydantic Model:** `DeleteArchiveResponse`
-   **Description:** Returns only a message string confirming the deletion. Internal fields (archived_at, reason, failed_stage) are intentionally not exposed to prevent information leakage and maintain a clean contract boundary.
-   **JSON Schema:**
    ```
    {
      "title": "DeleteArchiveResponse",
      "type": "object",
      "properties": {
        "message": {
          "title": "Message",
          "type": "string",
          "description": "Confirmation message including the deleted ticker"
        }
      },
      "required": ["message"],
      "additionalProperties": false
    }
    ```
-   **Example Payload:**
    ```
    {
      "message": "Archived ticker AAPL permanently deleted."
    }
    ```

---

## 15. ApiError

Standard error response envelope for all API error conditions across the system.

-   **Producer:** All services
-   **Consumer(s):** `frontend-app`, all internal service consumers
-   **Pydantic Model:** `ApiError`
-   **Description:** Provides a uniform error contract for 400 Bad Request, 404 Not Found, 503 Service Unavailable, and other HTTP error statuses. Ensures consistent error handling and client-side parsing across the entire API surface.
-   **JSON Schema:**
    ```
    {
      "title": "ApiError",
      "type": "object",
      "properties": {
        "error": {
          "title": "Error",
          "type": "string",
          "description": "Human-readable error message"
        }
      },
      "required": ["error"]
    }
    ```
-   **Example Payloads:**
    ```
    {
      "error": "Invalid ticker format"
    }
    ```
    ```
    {
      "error": "Ticker not found"
    }
    ```
    ```
    {
      "error": "Service unavailable"
    }
    ```

---

## 16. TickerPathParam

Path parameter validation model for ticker symbols used across monitoring endpoints.

-   **Producer:** N/A (validation contract only)
-   **Consumer(s):** `monitoring-service` route handlers
-   **Pydantic Model:** `TickerPathParam`
-   **Description:** Enforces format constraints for ticker path parameters: uppercase letters, digits, dot, and hyphen only; length 1-10 characters. Case normalization (to uppercase) is handled by service/route layers, not by this contract. This contract validates the shape and character set only.
-   **Constant:** `MAX_TICKER_LEN = 10`
-   **JSON Schema:**
    ```
    {
      "title": "TickerPathParam",
      "type": "object",
      "properties": {
        "ticker": {
          "title": "Ticker",
          "type": "string",
          "minLength": 1,
          "maxLength": 10,
          "pattern": "^[A-Za-z0-9.\\-]+$",
          "description": "Stock ticker symbol (1-10 chars, letters/digits/dot/hyphen only)"
        }
      },
      "required": ["ticker"]
    }
    ```
-   **Example Valid Values:**
    - `"AAPL"`
    - `"BRK.B"`
    - `"SHOP.TO"`
    - `"A"` (single character, valid)
    - `"ABCDEFGHIJ"` (10 characters, at max threshold)
-   **Example Invalid Values:**
    - `""` (empty, below min length)
    - `"AAPL@"` (contains invalid character `@`)
    - `"ABCDEFGHIJK"` (11 characters, exceeds max length)

---

## 17. AnalyzeFreshnessBatchRequest
-   **Producer:** `scheduler-service`
-   **Consumer:** `analysis-service`
-   **Pydantic Models:** `AnalyzeFreshnessBatchRequest`
-   **Description:** Request body for POST /analyze/freshness/batch.
-   **Request JSON Schema:**
    ```json
    {
      "title": "AnalyzeFreshnessBatchRequest",
      "type": "object",
      "properties": {
        "tickers": {
          "title": "Tickers",
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "required": ["tickers"]
    }
    ```

---

## 18. AnalyzeFreshnessBatchItem
-   **Producer:** `analysis-service`
-   **Consumer:** `scheduler-service`, `monitoring-service`
-   **Pydantic Models:** `AnalyzeFreshnessBatchItem`
-   **Description:**   Freshness result for a single ticker from `POST /analyze/freshness/batch` The analysis-service returns a rich payload using the field name `passes_freshness_check`; the shared contract maps this into the boolean property `fresh` via an alias for convenience in orchestrators.

-   **Request JSON Schema:**
    ```json
    {
      "title": "AnalyzeFreshnessBatchItem",
      "type": "object",
      "properties": {
        "ticker": {
        "title": "Ticker",
        "type": "string"
        },
        "fresh": {
        "title": "Fresh",
        "type": "boolean",
        "description": "Mapped from analysis-service field 'passes_freshness_check'."
        },
        "vcp_detected": {
        "title": "VCP Detected",
        "type": ["boolean", "null"],
        "description": "Whether a VCP pattern was detected for this ticker."
        },
        "days_since_pivot": {
        "title": "Days Since Pivot",
        "type": ["integer", "null"],
        "description": "Number of trading days since the most recent pivot low."
        },
        "message": {
        "title": "Message",
        "type": ["string", "null"],
        "description": "Human-readable explanation of the freshness decision."
        },
        "vcpFootprint": {
        "title": "VCP Footprint",
        "type": ["string", "null"],
        "description": "Text footprint summarizing the VCP contractions."
        }
      },
      "required": ["ticker", "fresh"],
      "additionalProperties": true
    }
    ```
- **Notes:**
  - On the wire, the analysis-service returns `passes_freshness_check`.  
  - The `AnalyzeFreshnessBatchItem` model uses `fresh` with `alias='passes_freshness_check'`
    so downstream services can work with a consistent boolean flag while still accepting
    the existing JSON shape.  
  - The additional fields are optional and provide richer context for monitoring-service
    status logic but are not required for basic orchestration.
    
---

## 19. DeleteArchiveResponse
-   **Producer:** `monitoring-service`
-   **Consumer:** `frontend-app` (via api-gateway)
-   **Pydantic Models:** `DeleteArchiveResponse`
-   **Description:** Returns only a message string confirming the deletion. Internal fields (archived_at, reason, failed_stage) are intentionally not exposed to prevent information leakage and maintain a clean contract boundary.
-   **Request JSON Schema:**
    ```json
    {
      "title": "DeleteArchiveResponse",
      "type": "object",
      "properties": {
        "message": {
          "title": "Message",
          "type": "string",
          "description": "Confirmation message including the deleted ticker"
        }
      },
      "required": ["message"],
      "additionalProperties": false
    }
    ```
-   **Example Payload:**
    ```json
    {
      "message": "Archived ticker AAPL permanently deleted."
    }
    ```
---

## 20. WatchlistFavouriteRequest / WatchlistFavouriteResponse

Request and response contracts for the POST `/monitor/watchlist/:ticker/favourite` endpoint.

-   **Producer:** `monitoring-service`
-   **Consumer:** `frontend-app` (via api-gateway)
-   **Pydantic Models:** `WatchlistFavouriteRequest`, `WatchlistFavouriteResponse`
-   **Description:** The request enforces strict boolean validation (no coercion from strings or integers). The response is message-only and forbids extra fields to prevent internal data leakage.

-   **Request JSON Schema:**
    ```json
    {
    "title": "WatchlistFavouriteRequest",
    "type": "object",
    "properties": {
      "is_favourite": {
        "title": "Is Favourite",
        "type": "boolean",
        "description": "Strict boolean; strings like 'true' or integers like 1 are rejected."
      }
    },
    "required": ["is_favourite"]
    }
    ```
-   **Response JSON Schema:**
    ```json
    {
    "title": "WatchlistFavouriteResponse",
    "type": "object",
    "properties": {
    "message": {
      "title": "Message",
      "type": "string",
      "description": "Confirmation message including the ticker and new favourite state."
      }
    },
    "required": ["message"],
    "additionalProperties": false
    }
    ```

## 21. WatchlistBatchRemoveRequest
-   **Producer:** Frontend  
-   **Consumer:** `monitoring-service`  
-   **Pydantic Model:** `WatchlistBatchRemoveRequest`  
-   **Description:** Request body for batch removal of watchlist items via `POST /monitor/watchlist/batch/remove`.

-   **Example Payload:**
    ```json
    {
    "tickers": ["AAPL", "MSFT", "GOOGL"]
    }
    ```

-   **Schema:**
    - `tickers` (required): List of ticker symbol strings. Must contain at least one ticker. Maximum 1000 tickers per request (enforced at service layer).

---

## 22. WatchlistBatchRemoveResponse
-   **Producer:** `monitoring-service`  
-   **Consumer:** Frontend  
-   **Pydantic Model:** `WatchlistBatchRemoveResponse`  
-   **Description:** Success response for batch watchlist removal. Provides both aggregate counts (for summary displays) and explicit ticker lists (for detailed UI feedback on which specific symbols were removed or not found).

-   **Fields:**
    - `message`: Human-readable summary message
    - `removed`: Integer count of successfully removed tickers
    - `notfound`: Integer count of requested tickers not found
    - `removed_tickers`: List[str] - explicit list of tickers that were removed
    - `not_found_tickers`: List[str] - explicit list of tickers that were not present

-   **Example Payload:**
    ```json
    {
    "message": "Successfully removed 3 tickers from the watchlist (not found: 0): AAPL, MSFT, GOOGL",
    "removed": ["AAPL", "MSFT", "GOOGL"],
    "notfound": [],
    "removed": 3,
    "notfound": 0
    }
    ```
-   **Schema:**
    - `tickers` (required): List of ticker symbol strings. Must contain at least one ticker. Maximum 1000 tickers per request (enforced at service layer).
---

## 23. InternalBatchAddRequest

Request body for batch addition of tickers to the watchlist via `POST /monitor/internal/watchlist/batch/add` (internal endpoint).

- **Producer:** `scheduler-service`, `monitoring-service`
- **Consumer:** `monitoring-service`
- **Pydantic Model:** `InternalBatchAddRequest`
- **Description:** Request body for adding multiple tickers to the watchlist in a single operation. This is an internal-only endpoint not exposed through the API gateway.

- **Example Payload:**
  ```json
  {
    "tickers": ["AAPL", "MSFT", "GOOGL"]
  }
  ```

- **JSON Schema:**
  ```json
  {
    "title": "InternalBatchAddRequest",
    "type": "object",
    "properties": {
      "tickers": {
        "title": "Tickers",
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "List of ticker symbols to add to the watchlist"
      }
    },
    "required": ["tickers"],
    "additionalProperties": false
  }
  ```

---

## 24. InternalBatchAddResponse

Success response for batch addition of tickers to the watchlist.

- **Producer:** `monitoring-service`
- **Consumer:** `scheduler-service`, `monitoring-service`
- **Pydantic Model:** `InternalBatchAddResponse`
- **Description:** Returns aggregate counts and a summary message. Does not expose internal arrays or database fields. Designed for internal service-to-service communication.

- **Example Payload:**
  ```json
  {
    "message": "Batch add completed: added 2, skipped 1. Sample: AAPL, MSFT",
    "added": 2,
    "skipped": 1
  }
  ```

- **JSON Schema:**
  ```json
  {
    "title": "InternalBatchAddResponse",
    "type": "object",
    "properties": {
      "message": {
        "title": "Message",
        "type": "string",
        "description": "Summary message including key tickers for traceability"
      },
      "added": {
        "title": "Added",
        "type": "integer",
        "description": "Number of tickers newly added to the watchlist"
      },
      "skipped": {
        "title": "Skipped",
        "type": "integer",
        "description": "Number of tickers that already existed in the watchlist"
      }
    },
    "required": ["message", "added", "skipped"],
    "additionalProperties": false
  }
  ```

**Schema:**
- `message` (string, required): Human-readable summary including sample ticker identifiers for traceability
- `added` (integer, required): Count of tickers successfully added to the watchlist
- `skipped` (integer, required): Count of tickers that already existed in the watchlist and were not re-added

---

## 25. InternalBatchUpdateStatusItem
-   **Producer**: `scheduler-service`
-   **Consumer**: `monitoring-service`  
-   **Pydantic Models:** `InternalBatchUpdateStatusItem`
-   **Description**: Single item within batch status update request for watchlist refresh pipeline.

-   **Fields:**
    - `ticker`: Stock symbol (required)
    - `status`: LastRefreshStatus enum value (PENDING, PASS, FAIL, UNKNOWN)
    - `failed_stage`: Optional string indicating which screening stage failed (e.g., "vcp", "leadership")
    - `current_price`: Optional float - current market price
    - `pivot_price`: Optional float - identified pivot price for VCP pattern
    - `pivot_proximity_percent`: Optional float - distance from pivot as percentage
    - `vcp_pass`: Optional bool - whether stock passed VCP pattern screening
    - `is_pivot_good`: Optional bool - whether pivot meets quality criteria
    - `pattern_age_days`: Optional int - age of VCP pattern in days
    - `has_pivot`: Optional bool - whether a pivot point was identified
    - `is_at_pivot`: Optional bool - whether price is currently at pivot
    - `has_pullback_setup`: Optional bool - whether stock is in pullback zone
    - `vol_last`: Optional int - most recent day's volume
    - `vol_50d_avg`: Optional int - 50-day average volume
    - `vol_vs_50d_ratio`: Optional float - ratio of current volume to 50D average
    - `day_change_pct`: Optional float - daily price change percentage
    - `is_leader`: Optional bool - whether stock meets leadership criteria

-   **Validation:**
    - `extra="forbid"` - rejects unexpected fields for security
    - All rich VCP/volume/pattern fields support Phase 1/2 status derivation logic

---

## 26. InternalBatchUpdateStatusRequest

-   **Producer**: `scheduler-service`
-   **Consumer**: `monitoring-service`  
-   **Pydantic Models:** `InternalBatchUpdateStatusRequest`
-   **Status:** **Legacy - Used only in deprecated batch update endpoint**
-   **Description**: Request payload for the deprecated `POST /monitor/internal/watchlist/batch/update-status` endpoint. This contract is attached to the legacy batch update flow and should not be used for new implementations. Prefer the orchestrated refresh flow via `POST /monitor/internal/watchlist/refresh-status`.

-   **JSON Schema**:
    ```json
    {
      "title": "InternalBatchUpdateStatusRequest",
      "type": "object",
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "$ref": "#/definitions/InternalBatchUpdateStatusItem"
          },
          "description": "List of watchlist items to update with new status"
        }
      },
      "required": ["items"],
      "definitions": {
        "InternalBatchUpdateStatusItem": {
          "title": "InternalBatchUpdateStatusItem",
          "type": "object",
          "properties": {
              "ticker": { "type": "string" },
              "status": { "$ref": "#/definitions/LastRefreshStatus" },
              "failed_stage": { "type": ["string", "null"] },
              "current_price": { "type": ["number", "null"] },
              "pivot_price": { "type": ["number", "null"] },
              "pivot_proximity_percent": { "type": ["number", "null"] },
              "vcp_pass": { "type": ["boolean", "null"] },
              "is_pivot_good": { "type": ["boolean", "null"] },
              "pattern_age_days": { "type": ["integer", "null"] },
              "has_pivot": { "type": ["boolean", "null"] },
              "is_at_pivot": { "type": ["boolean", "null"] },
              "has_pullback_setup": { "type": ["boolean", "null"] },
              "vol_last": { "type": ["integer", "null"] },
              "vol_50d_avg": { "type": ["integer", "null"] },
              "vol_vs_50d_ratio": { "type": ["number", "null"] },
              "day_change_pct": { "type": ["number", "null"] },
              "is_leader": { "type": ["boolean", "null"] }
          },
          "required": ["ticker", "status"]
        },
        "LastRefreshStatus": {
          "title": "LastRefreshStatus",
          "type": "string",
          "enum": ["PENDING", "PASS", "FAIL", "UNKNOWN"]
        }
      }
    }
    ```

---

## 27. InternalBatchUpdateStatusResponse

-   **Producer**: `monitoring-service`
-   **Consumer**: `scheduler-service`
-   **Status:** **Legacy - Used only in deprecated batch update endpoint**
-   **Description**: Success response for the deprecated batch status update endpoint. This contract is part of the legacy flow and has been superseded by the orchestrated refresh flow.
-   **JSON Schema**:
```json
{
  "type": "object",
  "properties": {
    "message": {
      "type": "string",
      "description": "Human-readable summary with sample tickers"
    },
    "updated": {
      "type": "integer",
      "description": "Number of watchlist items successfully updated"
    },
    "tickers": {
      "type": "array",
      "items": {"type": "string"},
      "description": "List of tickers that were updated (only existing watchlist items)"
    }
  },
  "required": ["message", "updated", "tickers"]
}
```

-   **Example**:
```json
{
  "message": "Batch status update completed for 3 watchlist items. Sample: AAPL, CRM, MSFT",
  "updated": 3,
  "tickers": ["AAPL", "CRM", "MSFT"]
}
```

---

## 28. InternalBatchArchiveFailedRequest
-   **Producer:** `scheduler-service`
-   **Consumer:** `monitoring-service`
-   **Pydantic Models:** `InternalBatchArchiveFailedRequest`
-   **Status:** **Legacy - Used only in deprecated batch update endpoint**
-   **Description:**  Request payload for the deprecated POST /monitor/internal/watchlist/batch/archive-failed endpoint.
-   **Request JSON Schema:**
    ```json
    {
      "title": "InternalBatchArchiveFailedRequest",
      "type": "object",
      "properties": {
        "items": {
          "title": "Items",
          "type": "array",
          "items": {
            "$ref": "#/definitions/InternalBatchArchiveFailedItem"
          }
        }
      },
      "required": ["items"],
      "definitions": {
        "InternalBatchArchiveFailedItem": {
          "title": "InternalBatchArchiveFailedItem",
          "type": "object",
          "properties": {
            "ticker": { "title": "Ticker", "type": "string" },
            "failed_stage": { "title": "Failed Stage", "type": "string" }
          },
          "required": ["ticker", "failed_stage"]
        }
      }
    }
    ```

---

## 29. WatchlistRefreshStatusResponse

Success response for the internal watchlist refresh orchestrator endpoint, summarizing the outcome of a full refresh run.

-   **Producer:** `monitoring-service`
-   **Consumer(s):** `scheduler-service` (Celery task `refresh_watchlist_task`, job history), internal tools/automation
-   **Pydantic Model:** `WatchlistRefreshStatusResponse`
-   **Endpoint:** `POST /monitor/internal/watchlist/refresh-status`
-   **Description:** Returns a human-readable summary and aggregate counts for items updated in place, archived, and failed during a watchlist refresh operation. This is an internal-only contract and is not exposed to the frontend.

-   **JSON Schema:**
    ```json
    {
      "title": "WatchlistRefreshStatusResponse",
      "type": "object",
      "properties": {
        "message": {
          "title": "Message",
          "type": "string",
          "description": "Summary message including counts and sample tickers for traceability"
        },
        "updated_items": {
          "title": "updated_items",
          "type": "integer",
          "description": "Number of watchlist items whose status was updated in place"
        },
        "archived_items": {
          "title": "archived_items",
          "type": "integer",
          "description": "Number of watchlist items moved to archive in this run"
        },
        "failed_items": {
          "title": "failed_items",
          "type": "integer",
          "description": "Number of items that failed to process due to downstream/service errors"
        }
      },
      "required": [
        "message",
        "updated_items",
        "archived_items",
        "failed_items"
      ],
      "additionalProperties": false
    }
    ```

-   **Example Payload:**
    ```json
    {
      "message": "Watchlist status refresh completed successfully.",
      "updated_items": 32,
      "archived_items": 5,
      "failed_items": 0
    }
    ```

---

## 30. WatchlistListResponse

Response body for `GET /monitor/watchlist`, returning the current watchlist items and associated metadata.

-   **Producer:** `monitoring-service`
-   **Consumer(s):** `frontend-app`
-   **Pydantic Model:** `WatchlistListResponse`
-   **Description:** Provides the full set of watchlist entries for the (single) user along with a simple metadata object. Each item exposes both the UI-facing status label and the underlying health status enum, aligning backend and frontend representations.

-   **JSON Schema:**
    ```json
    {
        "title": "WatchlistListResponse",
        "type": "object",
        "properties": {
            "items": {
                "title": "Items",
                "type": "array",
                "items": {
                    "$ref": "#/definitions/WatchlistItem"
                },
                "description": "List of watchlist items for the current user"
            },
            "metadata": {
                "title": "Metadata",
                "allOf": [
                    {
                        "$ref": "#/definitions/WatchlistMetadata"
                    }
                ],
                "description": "Response metadata including item count"
            }
        },
        "required": [
            "items",
            "metadata"
        ],
        "additionalProperties": false,
        "definitions": {
            "WatchlistItem": {
                "title": "WatchlistItem",
                "type": "object",
                "properties": {
                    "ticker": {
                        "title": "Ticker",
                        "type": "string",
                        "description": "Stock symbol"
                    },
                    "status": {
                        "title": "Status",
                        "allOf": [
                            {
                                "$ref": "#/definitions/WatchlistStatus"
                            }
                        ],
                        "description": "UI-facing status label (Pending, Failed, Watch, Buy Alert, Buy Ready)"
                    },
                    "date_added": {
                        "title": "Date Added",
                        "type": [
                            "string",
                            "null"
                        ],
                        "format": "date-time",
                        "description": "Timestamp when ticker was added to the watchlist"
                    },
                    "is_favourite": {
                        "title": "Is Favourite",
                        "type": "boolean",
                        "description": "Whether the user has marked this ticker as a favourite"
                    },
                    "last_refresh_status": {
                        "title": "Last Refresh Status",
                        "allOf": [
                            {
                                "$ref": "#/definitions/LastRefreshStatus"
                            }
                        ],
                        "description": "Latest health-check outcome enum"
                    },
                    "last_refresh_at": {
                        "title": "Last Refresh At",
                        "type": [
                            "string",
                            "null"
                        ],
                        "format": "date-time",
                        "description": "Timestamp of the most recent refresh run"
                    },
                    "failed_stage": {
                        "title": "Failed Stage",
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "Pipeline stage where the item failed (e.g. screen, vcp, freshness)"
                    },
                    "current_price": {
                        "title": "Current Price",
                        "type": [
                            "number",
                            "null"
                        ],
                        "description": "Latest price used by the refresh job"
                    },
                    "pivot_price": {
                        "title": "Pivot Price",
                        "type": [
                            "number",
                            "null"
                        ],
                        "description": "Detected VCP pivot price, if any"
                    },
                    "pivot_proximity_percent": {
                        "title": "Pivot Proximity Percent",
                        "type": [
                            "number",
                            "null"
                        ],
                        "description": "Distance from pivot as a percentage (negative = below pivot)"
                    },
                    "vcp_pass": {
                        "title": "VCP Pass",
                        "type": [
                            "boolean",
                            "null"
                        ],
                        "description": "Overall VCP validation result"
                    },
                    "vcpFootprint": {
                        "title": "VCP Footprint",
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "VCP pattern signature (e.g., '10D 5.2% | 13D 5.0%')"
                    },
                    "is_pivot_good": {
                        "title": "Is Pivot Good",
                        "type": [
                            "boolean",
                            "null"
                        ],
                        "description": "Pivot quality flag from VCP analysis"
                    },
                    "pattern_age_days": {
                        "title": "Pattern Age Days",
                        "type": [
                            "integer",
                            "null"
                        ],
                        "description": "Age of VCP pattern in days since formation"
                    },
                    "has_pivot": {
                        "title": "Has Pivot",
                        "type": [
                            "boolean",
                            "null"
                        ],
                        "description": "Whether a valid pivot point was identified"
                    },
                    "is_at_pivot": {
                        "title": "Is At Pivot",
                        "type": [
                            "boolean",
                            "null"
                        ],
                        "description": "Price is currently at/near the actionable pivot zone"
                    },
                    "has_pullback_setup": {
                        "title": "Has Pullback Setup",
                        "type": [
                            "boolean",
                            "null"
                        ],
                        "description": "Stock is in a recognised pullback setup zone"
                    },
                    "days_since_pivot": {
                        "title": "Days Since Pivot",
                        "type": [
                            "integer",
                            "null"
                        ],
                        "description": "Days since the most recent pivot low formation"
                    },
                    "fresh": {
                        "title": "Fresh",
                        "type": [
                            "boolean",
                            "null"
                        ],
                        "description": "Passes freshness threshold (typically < 90 days)"
                    },
                    "message": {
                        "title": "Message",
                        "type": [
                            "string",
                            "null"
                        ],
                        "description": "Human-readable explanation of freshness/status decision"
                    },
                    "is_leader": {
                        "title": "Is Leader",
                        "type": "boolean",
                        "description": "Whether this ticker currently qualifies as a leadership candidate"
                    },
                    "vol_last": {
                        "title": "Vol Last",
                        "type": [
                            "number",
                            "null"
                        ],
                        "description": "Most recent session's volume"
                    },
                    "vol_50d_avg": {
                        "title": "Vol 50d Avg",
                        "type": [
                            "number",
                            "null"
                        ],
                        "description": "Average volume over the last 50 trading sessions"
                    },
                    "vol_vs_50d_ratio": {
                        "title": "Vol Vs 50d Ratio",
                        "type": [
                            "number",
                            "null"
                        ],
                        "description": "Ratio of current volume to 50D average (e.g., 2.1 for 2.1x)"
                    },
                    "day_change_pct": {
                        "title": "Day Change Pct",
                        "type": [
                            "number",
                            "null"
                        ],
                        "description": "Percentage change from previous close to current close"
                    }
                },
                "required": [
                    "ticker",
                    "status",
                    "is_favourite",
                    "last_refresh_status",
                    "is_leader"
                ],
                "additionalProperties": false
            },
            "WatchlistStatus": {
                "title": "WatchlistStatus",
                "type": "string",
                "enum": [
                    "Pending",
                    "Failed",
                    "Watch",
                    "Buy Alert",
                    "Buy Ready"
                ],
                "description": "Allowed UI-facing status labels for watchlist items"
            },
            "LastRefreshStatus": {
                "title": "LastRefreshStatus",
                "type": "string",
                "enum": [
                    "PENDING",
                    "PASS",
                    "FAIL",
                    "UNKNOWN"
                ],
                "description": "Internal health status of the last refresh run"
            },
            "WatchlistMetadata": {
                "title": "WatchlistMetadata",
                "type": "object",
                "properties": {
                    "count": {
                        "title": "Count",
                        "type": "integer",
                        "description": "Total number of items returned in the watchlist"
                    }
                },
                "required": [
                    "count"
                ],
                "additionalProperties": false
            }
        }
    }
    ```

-   **Example Payload:**
    ```json
    {
        "items": [
            {
                "ticker": "NVDA",
                "status": "Buy Ready",
                "date_added": "2025-09-20T10:00:00Z",
                "is_favourite": false,
                "last_refresh_status": "PASS",
                "last_refresh_at": "2025-11-01T12:00:00Z",
                "failed_stage": null,
                "current_price": 850.0,
                "pivot_price": 855.0,
                "pivot_proximity_percent": -0.58,
                "vcp_pass": true,
                "vcpFootprint": "10D 5.2% | 13D 5.0% | 10D 6.2%",
                "is_pivot_good": true,
                "pattern_age_days": 15,
                "has_pivot": true,
                "is_at_pivot": true,
                "has_pullback_setup": false,
                "days_since_pivot": 15,
                "fresh": true,
                "message": "Pivot is fresh (formed 15 days ago) and is not extended.",
                "is_leader": true,
                "vol_last": 317900.0,
                "vol_50d_avg": 250000.0,
                "vol_vs_50d_ratio": 1.27,
                "day_change_pct": -0.35
            }
        ],
        "metadata": {
            "count": 1
        }
    }
    ```
---

## 31. WatchlistMetrics

Compact price and volume summary metrics for watchlist items, computed by data-service from recent historical price data.

-   **Producer:** `data-service`
-   **Consumer(s):** `monitoring-service`
-   **Pydantic Models:** `WatchlistMetricsItem`, `WatchlistMetricsBatchResponse`
-   **Description:** This contract provides the essential price/volume metrics needed for watchlist status derivation and UI display. Instead of returning full OHLCV time series, data-service computes and returns only the four summary metrics the monitoring-service needs: current price, last volume, 50-day average volume, and daily price change percentage. This keeps the watchlist refresh pipeline lightweight while centralizing market data calculations in data-service per the SRP.

-   **Single Item JSON Schema (WatchlistMetricsItem):**
    ```json
    {
    "title": "WatchlistMetricsItem",
    "type": "object",
    "properties": {
    "current_price": {
    "title": "Current Price",
    "type": ["number", "null"],
    "description": "Most recent close price"
    },
    "vol_last": {
    "title": "Vol Last",
    "type": ["number", "null"],
    "description": "Most recent session's volume"
    },
    "vol_50d_avg": {
    "title": "Vol 50d Avg",
    "type": ["number", "null"],
    "description": "Average volume over the last 50 trading sessions"
    },
    "day_change_pct": {
    "title": "Day Change Pct",
    "type": ["number", "null"],
    "description": "Percentage change from previous close to current close"
    }
    },
    "additionalProperties": false
    }
    ```

-   **Batch Response JSON Schema (WatchlistMetricsBatchResponse):**
    ```json
    {
    "title": "WatchlistMetricsBatchResponse",
    "type": "object",
    "properties": {
    "metrics": {
    "title": "Metrics",
    "type": "object",
    "additionalProperties": {
    "$ref": "#/definitions/WatchlistMetricsItem"
    },
    "description": "Mapping of ticker symbol to its computed metrics"
    }
    },
    "required": ["metrics"],
    "definitions": {
    "WatchlistMetricsItem": {
    "title": "WatchlistMetricsItem",
    "type": "object",
    "properties": {
    "current_price": { "type": ["number", "null"] },
    "vol_last": { "type": ["number", "null"] },
    "vol_50d_avg": { "type": ["number", "null"] },
    "day_change_pct": { "type": ["number", "null"] }
    }
    }
    }
    }
    ```
-   **Example Batch Request:**
    ```json
    {
    "tickers": ["HG", "INTC", "PATH"]
    }
    ```
-   **Example Batch Response:**
    ```json
    {
    "metrics": {
    "HG": {
    "current_price": 18.97,
    "vol_last": 317900.0,
    "vol_50d_avg": 250000.0,
    "day_change_pct": -0.35
    },
    "INTC": {
    "current_price": 23.45,
    "vol_last": 42100000.0,
    "vol_50d_avg": 38500000.0,
    "day_change_pct": 1.2
    },
    "PATH": {
    "current_price": null,
    "vol_last": null,
    "vol_50d_avg": null,
    "day_change_pct": null
    }
    }
    }
    ```
-   **Notes:**
    - All metrics are nullable to handle cases where data is unavailable or incomplete.
    - The monitoring-service orchestrator uses these metrics to compute derived fields like `vol_vs_50d_ratio` (vol_last / vol_50d_avg).
    - Failed tickers return all-null metrics rather than being excluded from the response, allowing orchestrator to distinguish "no data" from "ticker not requested".
    - This endpoint is internal-only (not exposed via api-gateway) and is called exclusively by monitoring-service's `POST /monitor/internal/watchlist/refresh-status` orchestrator.

**Last updated**: 2025-11-20
