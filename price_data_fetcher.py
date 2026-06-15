import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os

_SYMBOL_MAP = None

def _load_symbol_map():
    global _SYMBOL_MAP
    if _SYMBOL_MAP is None:
        # Try multiple possible paths for Cloud vs Local compatibility
        possible_paths = [
            os.path.join(os.getcwd(), "downloads", "stock_symbol_map.csv"),
            os.path.join(os.path.dirname(__file__), "downloads", "stock_symbol_map.csv"),
            "downloads/stock_symbol_map.csv"
        ]
        
        map_file = None
        for p in possible_paths:
            if os.path.exists(p):
                map_file = p
                break
        
        if map_file:
            try:
                df = pd.read_csv(map_file)
                # Store with lower-case keys for case-insensitive matching
                _SYMBOL_MAP = {str(k).lower().strip(): v for k, v in zip(df['ngen_name'], df['yf_ticker'])}
            except Exception as e:
                _SYMBOL_MAP = {}
        else:
            _SYMBOL_MAP = {}
            
    # Emergency hardcoded overrides for high-volume stocks (Safety net for Cloud)
    emergency_overrides = {
        "bharti airtel": "BHARTIARTL.NS",
        "bharti airtel pp": "BHARTIARTL.NS",
        "sbi": "SBIN.NS",
        "reliance industries": "RELIANCE.NS",
        "hdfc bank": "HDFCBANK.NS",
        "icici bank": "ICICIBANK.NS",
        "itc": "ITC.NS",
        "infosys": "INFY.NS",
        "tcs": "TCS.NS"
    }
    for k, v in emergency_overrides.items():
        if k not in _SYMBOL_MAP:
            _SYMBOL_MAP[k] = v
            
    return _SYMBOL_MAP

def _get_ticker(stock_name: str) -> str:
    symbol_map = _load_symbol_map()
    ticker = symbol_map.get(str(stock_name).lower())
    if ticker and pd.notna(ticker):
        return ticker
    # Fallback logic
    fallback = str(stock_name).upper().replace(" ", "").replace(".", "")
    return f"{fallback}.NS"

def get_price_metrics(stock_name: str) -> dict:
    ticker = _get_ticker(stock_name)
    result = {
        "ticker": ticker, "ltp": None,
        "change_1m": None, "change_3m": None, "change_6m": None,
        "change_ytd": None, "change_1y": None, "error": None
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

    except Exception as e:
        result["error"] = str(e)

    return result
