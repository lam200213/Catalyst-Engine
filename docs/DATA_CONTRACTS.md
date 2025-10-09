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