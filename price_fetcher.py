import yfinance as yf
import pandas as pd
import logging
from datetime import datetime, timedelta
from nse_symbol_map import resolve_nse_symbol
from YahooFinanceLoader import YahooFinanceLoader

logger = logging.getLogger(__name__)

_price_cache = {}
_extended_cache = {}

def get_price_data(mf_name: str, months_back: int = 14) -> dict or None:
    symbol = resolve_nse_symbol(mf_name)
    if not symbol:
        logger.warning("Yahoo price fetch skipped: requested=%s, error=no Yahoo ticker mapping", mf_name)
        print(f"Yahoo price fetch skipped: requested={mf_name}, error=no Yahoo ticker mapping")
        return None
        
    cached = _price_cache.get(symbol)
    if cached and cached.get('_months_back', 0) >= months_back:
        logger.info(
            "Yahoo price cache hit: requested=%s, yahoo_ticker=%s, latest_price=%s",
            mf_name, symbol, cached.get('current_price')
        )
        return cached
        
    try:
        end_date = datetime.now()
        period = max(months_back * 23 + 30, 260)
        logger.info("Yahoo price fetch: requested=%s, yahoo_ticker=%s, period=%s", mf_name, symbol, period)
        print(f"Yahoo price fetch: requested={mf_name}, yahoo_ticker={symbol}, period={period}")

        loader = YahooFinanceLoader(tf="daily", end_date=end_date + timedelta(days=1), period=period)
        hist = loader.get(symbol)
        
        if hist is None or hist.empty:
            logger.warning("Yahoo price fetch returned no data: requested=%s, yahoo_ticker=%s", mf_name, symbol)
            print(f"Yahoo price fetch returned no data: requested={mf_name}, yahoo_ticker={symbol}")
            return None
            
        # Ensure index is timezone-naive
        if hist.index.tz is not None:
            hist.index = hist.index.tz_localize(None)

        hist = hist.dropna(subset=['Close'])
        if hist.empty:
            logger.warning("Yahoo price fetch returned no usable close data: requested=%s, yahoo_ticker=%s", mf_name, symbol)
            print(f"Yahoo price fetch returned no usable close data: requested={mf_name}, yahoo_ticker={symbol}")
            return None
            
        current_price = hist['Close'].dropna().iloc[-1]
        logger.info(
            "Yahoo price fetched: requested=%s, yahoo_ticker=%s, latest_price=%.2f",
            mf_name, symbol, current_price
        )
        print(f"Yahoo price fetched: requested={mf_name}, yahoo_ticker={symbol}, latest_price={current_price:.2f}")
        price_52w_high = hist['High'].iloc[-252:].max() if len(hist) >= 252 else hist['High'].max()
        price_52w_low = hist['Low'].iloc[-252:].min() if len(hist) >= 252 else hist['Low'].min()
        pct_below_52w_high = ((price_52w_high - current_price) / price_52w_high) * 100
        
        # EMAs
        ema50 = hist['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        ema100 = hist['Close'].ewm(span=100, adjust=False).mean().iloc[-1]
        ema200 = hist['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
        
        ema_status = "Unknown"
        if current_price > ema200: ema_status = "Above 200"
        elif current_price > ema100: ema_status = "Above 100"
        elif current_price < ema50: ema_status = "Below 50"
        else: ema_status = "Below 200"

        volume_spike = False
        latest_volume_spike_date = None
        volume_spike_ratio = None
        price_change_since_volume_spike = None
        days_since_volume_spike = None

        if len(hist) >= 64:
            hist = hist.copy()
            hist['avg_volume_63d'] = hist['Volume'].rolling(63).mean().shift(1)
            hist['volume_ratio'] = hist['Volume'] / hist['avg_volume_63d']
            recent = hist.iloc[-63:]
            spike_rows = recent[recent['volume_ratio'] >= 2.0]
            if not spike_rows.empty:
                spike_row = spike_rows.iloc[-1]
                spike_date = spike_rows.index[-1]
                spike_price = spike_row['Close']
                volume_spike = True
                latest_volume_spike_date = spike_date.strftime('%Y-%m-%d')
                volume_spike_ratio = float(spike_row['volume_ratio'])
                price_change_since_volume_spike = ((current_price - spike_price) / spike_price) * 100
                days_since_volume_spike = int((hist.index[-1] - spike_date).days)

        # Returns
        price_now = current_price
        
        def get_ret(days):
            target = end_date - timedelta(days=days)
            idx = hist.index.get_indexer([target], method='nearest')[0]
            if idx < 0: return 0.0
            p_old = hist['Close'].iloc[idx]
            return ((price_now - p_old) / p_old) * 100

        # YTD
        ytd_start = datetime(end_date.year, 1, 1)
        idx_ytd = hist.index.get_indexer([ytd_start], method='nearest')[0]
        p_ytd = hist['Close'].iloc[idx_ytd] if idx_ytd >= 0 else current_price
        ytd_ret = ((price_now - p_ytd) / p_ytd) * 100

        result = {
            'symbol': symbol,
            '_months_back': months_back,
            'current_price': float(current_price),
            'ema50': float(ema50),
            'ema100': float(ema100),
            'ema200': float(ema200),
            'ema_status': ema_status,
            'volume_spike': volume_spike,
            'latest_volume_spike_date': latest_volume_spike_date,
            'volume_spike_ratio': volume_spike_ratio,
            'price_change_since_volume_spike': price_change_since_volume_spike,
            'days_since_volume_spike': days_since_volume_spike,
            'price_52w_high': float(price_52w_high),
            'price_52w_low': float(price_52w_low),
            'pct_below_52w_high': float(pct_below_52w_high),
            'price_change_1m': get_ret(30),
            'price_change_3m': get_ret(90),
            'price_change_6m': get_ret(180),
            'ytd_return': ytd_ret,
            'monthly_closes': {}
        }
        
        resampled = hist['Close'].resample('ME').last()
        for dt, price in resampled.items():
            result['monthly_closes'][dt.strftime('%Y-%m-%d')] = float(price)

        _price_cache[symbol] = result
        return result
        
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
        return None

def get_extended_data(mf_name: str) -> dict:
    symbol = resolve_nse_symbol(mf_name)
    if not symbol:
        return {}
    
    if symbol in _extended_cache:
        return _extended_cache[symbol]
        
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Market Cap in Cr (usually given in absolute value, divide by 10^7 for Crore)
        mkt_cap = info.get('marketCap')
        mkt_cap_cr = (mkt_cap / 10000000) if mkt_cap else None
        
        # Earnings Date
        earnings_date = None
        upcoming_earnings_flag = False
        try:
            calendar = ticker.calendar
            e_dates = []
            if isinstance(calendar, dict):
                e_dates = calendar.get('Earnings Date') or calendar.get('Earnings Dates') or []
            elif isinstance(calendar, pd.DataFrame) and not calendar.empty:
                if 'Earnings Date' in calendar.index:
                    e_dates = calendar.loc['Earnings Date'].tolist()
                elif 'Earnings Date' in calendar.columns:
                    e_dates = calendar['Earnings Date'].dropna().tolist()

            if e_dates:
                if not isinstance(e_dates, (list, tuple)):
                    e_dates = [e_dates]
                earnings_date_obj = e_dates[0]
                if isinstance(earnings_date_obj, pd.Timestamp):
                    earnings_date_obj = earnings_date_obj.to_pydatetime()
                earnings_dt = earnings_date_obj.date() if hasattr(earnings_date_obj, 'date') else earnings_date_obj
                earnings_date = earnings_dt.strftime('%Y-%m-%d')
                if 0 <= (earnings_dt - datetime.now().date()).days <= 30:
                    upcoming_earnings_flag = True
        except:
            pass

        data = {
            'promoter_holding_pct': info.get('heldPercentInsiders', 0) * 100 if info.get('heldPercentInsiders') else None,
            'fii_holding_pct': info.get('heldPercentInstitutions', 0) * 100 if info.get('heldPercentInstitutions') else None,
            'dii_holding_pct': None, # yfinance doesn't easily split FII/DII in info
            'pe_ratio': info.get('trailingPE'),
            'pb_ratio': info.get('priceToBook'),
            'market_cap_cr': mkt_cap_cr,
            'earnings_date': earnings_date,
            'upcoming_earnings_flag': upcoming_earnings_flag
        }
        _extended_cache[symbol] = data
        return data
    except Exception as e:
        print(f"Error fetching extended data for {symbol}: {e}")
        return {}

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
