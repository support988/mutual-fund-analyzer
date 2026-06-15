import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os

_SYMBOL_MAP = None
# Use relative path for cloud compatibility
MAP_PATH = os.path.join(os.path.dirname(__file__), "downloads", "stock_symbol_map.csv")

def _load_symbol_map():
    global _SYMBOL_MAP
    if _SYMBOL_MAP is None:
        if os.path.exists(MAP_PATH):
            df = pd.read_csv(MAP_PATH)
            # Map ngen_name to yf_ticker
            _SYMBOL_MAP = dict(zip(df['ngen_name'], df['yf_ticker']))
        else:
            _SYMBOL_MAP = {}
    return _SYMBOL_MAP

def _get_ticker(stock_name: str) -> str:
    symbol_map = _load_symbol_map()
    ticker = symbol_map.get(stock_name)
    if ticker and pd.notna(ticker):
        return ticker
    # Fallback logic
    fallback = stock_name.upper().replace(" ", "").replace(".", "")
    return f"{fallback}.NS"

def get_price_metrics(stock_name: str) -> dict:
    ticker = _get_ticker(stock_name)
    result = {
        "ticker": ticker, "ltp": None,
        "change_1m": None, "change_3m": None, "change_6m": None,
        "change_ytd": None, "change_1y": None, "error": None
    }
    try:
        data = yf.download(ticker, period="2y", interval="1d", progress=False, auto_adjust=True)
        if data.empty:
            result["error"] = f"No data for {ticker}"
            return result

        # Handle multi-index columns if present (yfinance sometimes returns them)
        if isinstance(data.columns, pd.MultiIndex):
            close = data['Close'][ticker].dropna()
        else:
            close = data['Close'].dropna()

        if close.empty:
            result["error"] = f"Close price column empty for {ticker}"
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
