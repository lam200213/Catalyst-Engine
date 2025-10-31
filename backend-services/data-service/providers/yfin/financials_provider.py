# backend-services/data-service/providers/yfin/financials_provider.py
import yfinance as yf
import datetime as dt
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import yahoo_client, price_provider # Use relative import
from helper_functions import is_ticker_delisted, mark_ticker_as_delisted
from curl_cffi import requests as cffi_requests

#DEBUG
import logging
import json

# Proxies are now loaded from an environment variable for better configuration management.
import os # Add os import for environment variable access
PROXIES = [p.strip() for p in os.getenv("YAHOO_FINANCE_PROXIES", "").split(',') if p.strip()]

logger = logging.getLogger(__name__)

# --- Soft-coded Yahoo Finance Scraper Selectors ---
# These class names are specific to the Yahoo Finance financial statements page.
# Yahoo may update its website structure, causing these to fail.
# If the scraper stops working, inspect the page's HTML and update these values.
# - YF_ROW_CLASS: Represents a row in the financial table (e.g., "Total Revenue").
# - YF_HEADER_ROW_CLASS: Represents the header row containing the dates.
YF_ROW_CLASS = 'yf-t22klz'
YF_HEADER_ROW_CLASS = 'yf-1yyu1pc'
# --- End Selectors ---

def _transform_income_statements(statements, shares_outstanding):
    """Helper to extract raw values and manually calculate EPS if not provided."""
    transformed = []
    for s in statements:
        net_income = s.get('netIncome', {}).get('raw')
        total_revenue = s.get('totalRevenue', {}).get('raw')
        
        # Try to get pre-calculated EPS first
        eps = (s.get('basicEps') or {}).get('raw')
        
        # Fallback: Manually calculate EPS if not available and data is valid
        if eps is None and net_income is not None and shares_outstanding is not None and shares_outstanding > 0:
            eps = net_income / shares_outstanding

        transformed.append({
            'Earnings': eps,
            'Net Income': net_income,
            'Revenue': total_revenue,
            'Total Revenue': total_revenue,
        })
    return transformed

def _fetch_financials_with_yfinance(ticker):
    """
    Fetches financials for a ticker using the yfinance library.
    IMPORTANT: This function DOES NOT handle its own exceptions.
    It allows them to propagate up to be handled by a decorator (e.g., retry logic), now with integrated rotating proxy support.
    """
    try:    
        session=yahoo_client.get_yf_session()
        stock = yf.Ticker(ticker, session=session)
        info = stock.info

        # The 'info' dictionary must exist and contain essential data to be useful.
        if not info or 'marketCap' not in info:
            logger.debug(f"yfinance info missing key fields for {ticker}.")
            return None

        # --- DEBUGGING BLOCK ---
    # Print the exact data received to the container's logs
        print("--- LEADERSHIP-SERVICE DEBUG ---", flush=True)
        print(f"Data received from data-service for {ticker}:", flush=True)
        # # Use json.dumps for pretty-printing the dictionary
        print(json.dumps(info, indent=2), flush=True)
        print("--- END DEBUG ---", flush=True)
        # --- END DEBUGGING BLOCK ---

        # --- IPO Date Handling ---
        # Yahoo Finance provides the 'firstTradeDateEpoch', which is the timestamp
        # of the first trade recorded. This serves as a reliable proxy for the IPO date.
        ipo_date = None

        ipo_date_timestamp = info.get('firstTradeDateMilliseconds')
        # Represents the number of milliseconds since the Unix epoch.
        # divide the millisecond value by 1000 to the number of seconds since the Unix epoch
        
        if ipo_date_timestamp:
            # Ensure the timestamp value is a number before converting.
            if isinstance(ipo_date_timestamp, (int, float)):
                try:
                    ipo_date_timestamp_val = ipo_date_timestamp / 1000
                    ipo_date = dt.datetime.fromtimestamp(ipo_date_timestamp_val).strftime('%Y-%m-%d')
                except (ValueError, TypeError) as e:
                    # Log if the timestamp is invalid (e.g., out of range).
                    logger.debug(f"Could not convert epoch '{ipo_date_timestamp}' to date for {ticker}. Error: {e}")
            else:
                logger.debug(f"Expected epoch for 'firstTradeDateEpoch' to be a number, but got {type(ipo_date_timestamp)} for {ticker}.")
        
        # --- Financial Statement Fetching ---
        q_income_stmt = stock.quarterly_income_stmt
        a_income_stmt = stock.income_stmt

        # --- Financial Statement Formatting ---
        def format_income_statement(df):
            if df is None or df.empty:
                logger.debug(f"Income statement DataFrame for {ticker} is empty or None. Skipping formatting.")
                return []
            
            # debug log to inspect the raw DataFrame from yfinance
            logger.debug(f"Raw income statement dtypes for {ticker}:\n{df.dtypes}")

            df_t = df.transpose()
            # This ensures consistency with the fallback method and prevents errors in leadership_logic.
            if 'Total Revenue' in df_t.columns:
                df_t['Revenue'] = df_t['Total Revenue']
            else:
                df_t['Revenue'] = None
            
            # Manually calculate EPS if not present, using sharesOutstanding from the info dict.
            shares_outstanding = info.get('sharesOutstanding')
            # Initialize 'Earnings' column with data from 'Basic EPS' if it exists
            if 'Basic EPS' in df_t.columns:
                df_t['Earnings'] = df_t['Basic EPS']
            else:
                # Use a Pandas Series of Nones to correctly initialize the column
                df_t['Earnings'] = pd.Series([None] * len(df_t), index=df_t.index)
            
            # Identify rows (quarters) where 'Earnings' is null or NaN
            mask_missing_eps = pd.isnull(df_t['Earnings'])
            
            # Add a robust try-except block and type coercion around the EPS calculation
            if shares_outstanding and 'Net Income' in df_t.columns:
                try:
                    # Coerce 'Net Income' to a numeric type. Any non-numeric values become NaN.
                    net_income_numeric = pd.to_numeric(df_t.loc[mask_missing_eps, 'Net Income'], errors='coerce')
                    # Perform division; operations with NaN will result in NaN, which is handled later.
                    df_t.loc[mask_missing_eps, 'Earnings'] = net_income_numeric / shares_outstanding
                except Exception as e:
                    logger.error(f"Error during fallback EPS calculation for {ticker}: {e}. Some 'Earnings' values may be null.")

            # Convert the DataFrame to a list of dictionaries
            records = df_t.reset_index().to_dict('records')
            
            # Final loop to replace any pandas NaN/NaT with None for perfect JSON compatibility
            for record in records:
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None
            return records

        quarterly_financials = format_income_statement(q_income_stmt)
        annual_financials = format_income_statement(a_income_stmt)

        # --- CONSTRUCT THE FINAL OBJECT ---
        # Consolidate all data into the final dictionary before logging and returning.
        final_data_object = {
            'ticker': ticker,
            'marketCap': info.get('marketCap'),
            'sharesOutstanding': info.get('sharesOutstanding'),
            'floatShares': info.get('floatShares'),
            'industry': info.get('industry'),
            'ipoDate': ipo_date,
            'annual_earnings': annual_financials,
            'quarterly_earnings': quarterly_financials,
            'quarterly_financials': quarterly_financials, # Retained for compatibility
            # Also include the raw info object for complete debugging if needed
            'raw_info': info 
        }

        # --- LOGGING/SAVING BLOCK ---
        # Save the *final constructed data object* to a structured log file.
        try:
            log_dir = os.path.join('/app/logs', 'finance_fetches')
            date_str = dt.datetime.now().strftime('%Y-%m-%d')
            ticker_log_dir = os.path.join(log_dir, date_str)
            os.makedirs(ticker_log_dir, exist_ok=True)
            
            # 1. Save the clean, structured JSON file
            json_file_path = os.path.join(ticker_log_dir, f"{ticker}.json")
            with open(json_file_path, 'w') as f:
                # Use a custom encoder to handle potential non-serializable data like NaN
                class CustomEncoder(json.JSONEncoder):
                    def default(self, obj):
                        if isinstance(obj, float) and (obj != obj):  # NaN
                            return None
                        if isinstance(obj, (pd.Timestamp, dt.datetime, dt.date)):
                            return obj.isoformat()  # Or str(obj) for a simple string representation
                        return json.JSONEncoder.default(self, obj)
                json.dump(final_data_object, f, indent=4, cls=CustomEncoder)
            logger.debug(f"Successfully saved structured financial data for {ticker} to {json_file_path}")
        
        except Exception as log_e:
            logger.error(f"Failed to save financial fetch logs for {ticker}: {log_e}")
        # --- END LOGGING/SAVING BLOCK ---

        # Return the final data object
        del final_data_object['raw_info']
        return final_data_object

    except Exception as e:
        logger.error(f"Failed to fetch financials for {ticker}: {e}")
        return None
    
def _fetch_financials_with_fallback(ticker_symbol, start_time):
    """Fallback method: Scrapes financials directly if yfinance fails."""
    logger.debug(f"Primary yfinance fetch failed for {ticker_symbol} (likely delisted or no summary data). Falling back to direct API.")
    try:
        modules = "summaryDetail,assetProfile,financialData,defaultKeyStatistics,incomeStatementHistory,incomeStatementHistoryQuarterly,balanceSheetHistory,cashflowStatementHistory"
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker_symbol}"
        params = {"modules": modules}
        response = yahoo_client.execute_request(url, params=params)

        qs = (response or {}).get("quoteSummary") or {}
        result = qs.get("result") or []
        if not result:
            logger.debug("Yahoo API fallback response has no 'result' field.")
            return None
        
        info = result[0]

        summary_detail = info.get('summaryDetail') or {}
        default_key_stats = info.get('defaultKeyStatistics') or {}
        
        shares_outstanding = (default_key_stats.get('sharesOutstanding') or {}).get('raw')

        annual_history = info.get('incomeStatementHistory', {}).get('incomeStatementHistory', [])
        quarterly_history = info.get('incomeStatementHistoryQuarterly', {}).get('incomeStatementHistory', [])

        annual_earnings_list = _transform_income_statements(annual_history, shares_outstanding)
        quarterly_earnings_list = _transform_income_statements(quarterly_history, shares_outstanding)
        
        data = {
            'ticker': ticker_symbol,
            'marketCap': (summary_detail.get('marketCap') or {}).get('raw'),
            'sharesOutstanding': shares_outstanding,
            'floatShares': (default_key_stats.get('floatShares') or {}).get('raw'),
            'ipoDate': (default_key_stats.get('ipoDate') or {}).get('fmt'), 
            'annual_earnings': annual_earnings_list,
            'quarterly_earnings': quarterly_earnings_list,
            'quarterly_financials': quarterly_earnings_list
        }
        
        duration = time.time() - start_time
        logger.debug(f"Yahoo Finance API fallback call for {ticker_symbol} took {duration:.2f} seconds.")
        return data
    
    except cffi_requests.errors.RequestsError as e:
        if e.response and e.response.status_code == 404:
            mark_ticker_as_delisted(ticker_symbol, "Yahoo Finance API call failed with status 404.")
            logger.debug(f"Fallback for {ticker_symbol} also failed with 404. Ticker is confirmed unavailable.")
        else:
            if e.response:
                logger.error(f"HTTPError: {e.response.status_code} Client Error for url: {e.response.url}")
            logger.error(f"A curl_cffi request error occurred during fallback for {ticker_symbol}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Exception in get_core_financials fallback for {ticker_symbol}")
        return None


def get_core_financials(ticker_symbol: str) -> dict | None:
    """
    Fetches core financial data points required for Leadership Profile screening.
    For S&P 500 (^GSPC), returns market data including current price, SMAs, and 52-week highs/lows.
    For other tickers, returns standard financial data.
    This function now prioritizes the yfinance library and uses the direct API call as a fallback.
    """
    start_time = time.time()
    logger.debug(f"Attempting to get core financials for {ticker_symbol}")

    # Pre-flight check to see if we already know this ticker is delisted
    if is_ticker_delisted(ticker_symbol):
        logger.debug(f"Skipping core financials for {ticker_symbol} because it is delisted.")
        return None

    # --- Special Handling for Market Indices ---
    if ticker_symbol in ['^GSPC', '^DJI', '^IXIC']:
        # Define date range ending yesterday to ensure consistency and avoid partial data.
        yesterday = dt.date.today() - dt.timedelta(days=1)
        start_of_period = yesterday - dt.timedelta(days=365)
        hist = price_provider._get_single_ticker_data(ticker_symbol, start_date=start_of_period)
        if not hist:
            logger.debug(f"No historical data for index {ticker_symbol}")
            return None

        df = pd.DataFrame(hist)
        # Ensure DataFrame has enough data for calculations
        if df.empty or len(df) < 2:
            return None

        data = {
            'ticker': ticker_symbol,
            'current_price': float(df['close'].iloc[-1]),
            'sma_50': float(df['close'].tail(50).mean()) if len(df) >= 50 else float(df['close'].mean()),
            'sma_200': float(df['close'].tail(200).mean()) if len(df) >= 200 else float(df['close'].mean()),
            'high_52_week': float(df['high'].max()),
            'low_52_week': float(df['low'].min())
        }
        return data
    
    try:
        # --- Primary Fetching Strategy (yfinance library) ---
        # Prioritize fetching with the yfinance helper function.
        extended_financials_data = _fetch_financials_with_yfinance(ticker_symbol)
        if extended_financials_data:
            duration = time.time() - start_time
            logger.debug(f"yfinance library call for {ticker_symbol} took {duration:.2f} seconds.")
            return extended_financials_data
    except Exception as e:
        logger.warning(f"Primary yfinance fetch for {ticker_symbol} failed with error: {e}. Attempting fallback.")

    # --- Fallback Fetching Strategy (Direct API Call) ---
    logger.debug(f"Primary yfinance fetch failed for {ticker_symbol} (likely delisted or no summary data). Falling back to direct API.")
    return _fetch_financials_with_fallback(ticker_symbol, start_time)
        
def get_batch_core_financials(tickers: list[str], executor: ThreadPoolExecutor) -> dict:
    """
    Fetches core financial data for a list of tickers in parallel.
    """
    results = {}

    # Create a future for each ticker
    # Each ticker is fetched individually.
    future_to_ticker = {executor.submit(get_core_financials, ticker): ticker for ticker in tickers}
    for future in as_completed(future_to_ticker):
        ticker = future_to_ticker[future]
        try:
            data = future.result()
            results[ticker] = data
        except Exception as e:
            logger.error(f"Failed to process {ticker} in batch after all retries. Error: {e}")
            results[ticker] = None
        # Add a random delay to avoid hammering the API
        # time.sleep(random.uniform(2, 5)) 

    return results
