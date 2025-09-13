# backend-services/leadership-service/checks/industry_peer_checks.py
# handle the peer ranking logic

import logging
import pandas as pd
from .utils import failed_check
from data_fetcher import fetch_peer_data, fetch_batch_financials

# Get a logger that's a child of the app.logger, so it inherits the file handler
logger = logging.getLogger('app.logic')

DATA_SERVICE_URL = "http://data-service:3001"

# Functions for financial statements (like check_yoy_eps_growth) expect newest-to-oldest data, 
# while functions for price history expect oldest-to-newest, due to the data properties.

def get_and_check_industry_leadership(ticker, details):
    """
    Orchestrates the entire industry leadership check: fetches necessary data
    and then calls the analysis function. This is the single entry point.
    """
    metric_key = 'is_industry_leader'
    
    # --- 1. Fetch all necessary data ---
    peers_data, error = fetch_peer_data(ticker)
    if error:
        logging.error(f"Failed to fetch peer data for {ticker}: {error[0]}")
        details.update(failed_check(metric_key, f"Upstream error: {error[0]}"))
        return # Stop execution for this check

    raw_peer_tickers = peers_data.get("peers", [])
    if not raw_peer_tickers:
        logging.warning(f"No peer data found for {ticker}")
        details.update(failed_check(metric_key, "No peer data was found for this ticker."))
        return

    peer_tickers = [t.strip().replace('/', '-') for t in raw_peer_tickers if t]
    all_tickers = list(set(peer_tickers + [ticker]))
    
    batch_financials, error = fetch_batch_financials(all_tickers)
    if error:
        logging.error(f"Failed to fetch batch financials: {error[0]}")
        details.update(failed_check(metric_key, f"Upstream error fetching batch financials: {error[0]}"))
        return
        
    batch_financial_data = batch_financials.get("success", {})

    # --- 2. Call the original analysis function with the fetched data ---
    check_industry_leadership(ticker, peers_data, batch_financial_data, details)


def check_industry_leadership(ticker, peers_data, batch_financial_data, details):
    """
    Analyzes a company's industry peers and ranks them based on revenue and market cap.

    Args:
        ticker (str): The stock ticker symbol of the company to analyze.
        peers_data (dict): The JSON response from the /industry/peers/<ticker> endpoint.
        batch_financial_data (dict): The JSON response from the /financials/core/batch endpoint.
        details (dict): A dictionary to store the result.

    Returns:
        dict: A JSON object containing the ticker's rank and industry details,
              or an error message if data cannot be processed.
    """
    metric_key = 'is_industry_leader'
    try:
        # -- data handling -- 
        industry_name = peers_data.get("industry")

        if not industry_name:
            details.update(failed_check(metric_key, f"No industry data found for {ticker}."))
            return 
        
        # Filter out any peers with incomplete data and prepare for DataFrame
        processed_data = []
        for ticker_symbol, data in batch_financial_data.items():
            # Ensure data is valid and annual_earnings is a non-empty list
            if data and isinstance(data.get('annual_earnings'), list) and data['annual_earnings']:
                most_recent_annual = data['annual_earnings'][0]
                revenue = most_recent_annual.get('Revenue')
                net_income = most_recent_annual.get('Net Income')
                market_cap = data.get('marketCap')

                # Ensure all required metrics are present and not None
                if revenue is not None and net_income is not None and market_cap is not None:
                    processed_data.append({
                        'ticker': ticker_symbol,
                        'revenue': revenue,
                        'marketCap': market_cap,
                        'netIncome': net_income
                    })

        if not processed_data:
            details.update(failed_check(metric_key, "No complete financial data available for ranking after filtering."))
            return

        # -- screening -- 
        # Create a pandas DataFrame
        df = pd.DataFrame(processed_data)

        # Rank by revenue, market cap, and net income (descending)
        # method='min' assigns the lowest rank in case of ties
        df['revenue_rank'] = df['revenue'].rank(ascending=False, method='min')
        df['market_cap_rank'] = df['marketCap'].rank(ascending=False, method='min')
        df['earnings_rank'] = df['netIncome'].rank(ascending=False, method='min')

        # Combine score (lower combined rank is better)
        df['combined_score'] = df['revenue_rank'] + df['market_cap_rank'] + df['earnings_rank']

        # The stock with the lowest score (e.g., 3) will receive the best final_rank (1).
        df['final_rank'] = df['combined_score'].rank(method='min').astype(int)

        # Sort by combined rank to get the final ranking
        df = df.sort_values(by='final_rank').reset_index(drop=True)

        # Find the rank of the original ticker
        ticker_rank_info = df[df['ticker'] == ticker]

        if not ticker_rank_info.empty:
            final_rank = int(ticker_rank_info['final_rank'].iloc[0])
        else:
            final_rank = None # Should not happen if original ticker was included in all_tickers

        is_pass = final_rank is not None and final_rank <= 3
        message = (
            f"Passes. Ticker ranks #{final_rank} out of {len(df)} in its industry."
            if is_pass
            else f"Fails. Ticker ranks #{final_rank} out of {len(df)}, outside the top 3."
        )

        details[metric_key] = {
            "pass": is_pass,
            "industry": industry_name,
            "rank": final_rank,
            "total_peers_ranked": len(df),
            "ranked_peers_data": df.to_dict(orient='records'), # Optional: include full ranked data
            "message": message,
        }
    except Exception as e:
        logging.error(f"Error in check_industry_leadership for {ticker}: {e}", exc_info=True)
        details.update(failed_check(metric_key, f"An unexpected error occurred: {e}"))