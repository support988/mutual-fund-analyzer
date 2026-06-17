import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os
from symbol_resolver import resolve_symbol

def get_price_metrics(stock_name: str) -> dict:
    ticker = resolve_symbol(stock_name)
    result = {
        "ticker": ticker, "ltp": None,
        "change_1m": None, "change_3m": None, "change_6m": None,
        "change_ytd": None, "change_1y": None, 
        "52w_high": None, "52w_low": None,
        "error": None
    }
    try:
        # Fetch data with higher reliability
        data = yf.download(ticker, period="2y", interval="1d", progress=False, auto_adjust=True)
        
        if data.empty:
            # Try a second attempt with just the ticker base if it ends in .NS
            if ticker.endswith(".NS"):
                alt_ticker = ticker.replace(".NS", ".BO")
                data = yf.download(alt_ticker, period="2y", interval="1d", progress=False, auto_adjust=True)
                if not data.empty:
                    result["ticker"] = alt_ticker
            
        if data.empty:
            result["error"] = f"No data found for {ticker} (tried fallback too)"
            return result

        # Extract Close prices safely
        if isinstance(data.columns, pd.MultiIndex):
            # Ticker might be the second level
            if 'Close' in data.columns.levels[0]:
                close_df = data['Close']
                # If ticker is a column in Close
                if ticker in close_df.columns:
                    close = close_df[ticker].dropna()
                elif result["ticker"] in close_df.columns:
                    close = close_df[result["ticker"]].dropna()
                else:
                    # Just take the first column of Close
                    close = close_df.iloc[:, 0].dropna()
            else:
                result["error"] = f"Close column missing in MultiIndex for {ticker}"
                return result
        else:
            if 'Close' in data.columns:
                close = data['Close'].dropna()
            else:
                result["error"] = f"Close column missing for {ticker}"
                return result

        if close.empty:
            result["error"] = f"Price history empty for {ticker}"
            return result

        ltp = float(close.iloc[-1])
        result["ltp"] = round(ltp, 2)
        latest_date = close.index[-1]

        def pct_change_from(days_back=None, target_date=None):
            if target_date is None:
                target_date = latest_date - timedelta(days=days_back)
            past = close[close.index <= target_date]
            if past.empty:
                return None
            past_price = float(past.iloc[-1])
            return round((ltp - past_price) / past_price * 100, 2) if past_price else None

        result["change_1m"] = pct_change_from(days_back=30)
        result["change_3m"] = pct_change_from(days_back=91)
        result["change_6m"] = pct_change_from(days_back=182)
        result["change_1y"] = pct_change_from(days_back=365)
        result["change_ytd"] = pct_change_from(target_date=datetime(latest_date.year, 1, 1))

        # Add 52w info using fast_info
        try:
            t_info = yf.Ticker(result["ticker"]).fast_info
            result["52w_high"] = round(float(t_info.year_high), 2)
            result["52w_low"] = round(float(t_info.year_low), 2)
        except Exception as e:
            print(f"[DEBUG] 52w fetch failed for {result['ticker']}: {e}")

    except Exception as e:
        result["error"] = str(e)

    return result

def calculate_active_buy_signal(alloc_change_3m: float, price_change_3m: float, alloc_3m_ago: float) -> dict:
    if alloc_change_3m > 0 and price_change_3m < 0:
        return {
            'signal': 'strong_buy',
            'score_bonus': 25,
            'explanation': f"Price fell {abs(price_change_3m):.1f}% but allocation rose {alloc_change_3m:.2f}% -> Fund actively accumulated"
        }
    
    if alloc_change_3m > 0 and price_change_3m > 0:
        expected_passive = alloc_3m_ago * (price_change_3m / 100.0)
        active_component = alloc_change_3m - expected_passive
        
        if active_component > 0.3:
            return {
                'signal': 'active_buy',
                'score_bonus': 15,
                'explanation': f"Allocation rose {alloc_change_3m:.2f}% ({active_component:+.2f}% active) while price rose {price_change_3m:.1f}%"
            }
        elif active_component >= -0.3:
            return {
                'signal': 'passive_drift',
                'score_bonus': 0,
                'explanation': f"Allocation change ({alloc_change_3m:+.2f}%) largely matches price movement ({price_change_3m:.1f}%)"
            }
        else:
            return {
                'signal': 'partial_sell',
                'score_bonus': -10,
                'explanation': f"Fund sold some units even as price rose (Active: {active_component:.2f}%)"
            }
            
    if alloc_change_3m <= 0:
        return {
            'signal': 'reducing',
            'score_bonus': -15,
            'explanation': "Fund is reducing allocation in this stock"
        }
        
    return {
        'signal': 'none',
        'score_bonus': 0,
        'explanation': "Insufficient data for active buy signal"
    }
