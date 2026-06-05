import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from rapidfuzz import process, fuzz
import os

MF_KEYWORDS = [
    'Mutual Fund', 'MF', 'Asset Management', 'AMC', 'Trustee', 
    'Scheme', 'Fund', 'HDFC MF', 'SBI MF', 'Nippon', 'Axis MF',
    'Quant', 'Kotak MF', 'ICICI Pru', 'Mirae', 'DSP', 'Invesco',
    'Bandhan', 'Motilal', 'Franklin', 'UTI', 'Tata MF', 'Aditya Birla'
]

def _find_col(cols, aliases):
    cols_lower = [str(c).strip().lower() for c in cols]
    for alias in aliases:
        if alias.lower() in cols_lower:
            return cols[cols_lower.index(alias.lower())]
    return None

def parse_bulk_deals_csv(file_path: str) -> pd.DataFrame:
    print(f"DEBUG: Attempting to parse bulk deals from {file_path}")
    encodings = ['utf-8', 'latin-1', 'cp1252']
    df = None
    
    for enc in encodings:
        try:
            for skip in [0, 1, 2]:
                try:
                    temp_df = pd.read_csv(file_path, encoding=enc, skiprows=skip)
                    if not temp_df.empty and len(temp_df.columns) > 3:
                        df = temp_df
                        print(f"DEBUG: Successfully read with encoding={enc}, skiprows={skip}")
                        break
                except:
                    continue
            if df is not None:
                break
        except:
            continue
            
    if df is None:
        print(f"ERROR: Failed to read CSV {file_path} with any common encoding.")
        return pd.DataFrame()

    try:
        cols = [str(c).strip() for c in df.columns]
        df.columns = cols
        
        # Robust column mapping
        c_date = _find_col(cols, ['Date', 'Deal Date', 'Trade Date'])
        c_symbol = _find_col(cols, ['Symbol', 'Security Code', 'Scrip Code'])
        c_name = _find_col(cols, ['Security Name', 'Scrip Name'])
        c_client = _find_col(cols, ['Client Name', 'Party Name'])
        c_type = _find_col(cols, ['Buy/Sell', 'Buy / Sell', 'Deal Type', 'Type', 'B/S', 'Action'])
        c_qty = _find_col(cols, ['Quantity Traded', 'Quantity', 'Qty', 'Volume'])
        c_price = _find_col(cols, ['Trade Price / Wt. Avg. Price', 'Trade Price / Wght. Avg. Price', 'Price', 'Avg Price', 'Trade Price'])

        print(f"DEBUG: Column Mapping -> Date:{c_date}, Sym:{c_symbol}, Client:{c_client}, Type:{c_type}, Qty:{c_qty}, Price:{c_price}")

        if not all([c_date, c_symbol, c_client, c_type, c_qty, c_price]):
            missing = [k for k, v in {'Date':c_date, 'Symbol':c_symbol, 'Client':c_client, 'Type':c_type, 'Qty':c_qty, 'Price':c_price}.items() if not v]
            print(f"ERROR: Missing required columns: {missing}")
            return pd.DataFrame()

        normalized_df = pd.DataFrame()
        
        # Clean data (remove footers etc)
        df = df[df[c_symbol].notna() & (df[c_symbol].astype(str).str.strip() != '')]
        
        # Date parsing
        # Try multiple formats
        normalized_df['date'] = pd.to_datetime(df[c_date], errors='coerce')
        if normalized_df['date'].isna().any():
            # Try DD-Mon-YYYY specifically for NSE
            temp_dates = pd.to_datetime(df[c_date], format='%d-%b-%Y', errors='coerce')
            normalized_df['date'] = normalized_df['date'].fillna(temp_dates)
            
        normalized_df['symbol'] = df[c_symbol].astype(str).str.strip()
        normalized_df['security_name'] = df[c_name].astype(str).str.strip() if c_name else normalized_df['symbol']
        normalized_df['client_name'] = df[c_client].astype(str).str.strip()
        
        # Deal Type
        def clean_type(x):
            val = str(x).strip().upper()
            if val in ['BUY', 'B', 'PURCHASE']: return 'BUY'
            if val in ['SELL', 'S', 'SALE']: return 'SELL'
            return 'UNKNOWN'
            
        normalized_df['deal_type'] = df[c_type].apply(clean_type)
        
        # Numeric cleanup
        def clean_num(x):
            if pd.isna(x): return 0.0
            return float(str(x).replace(',', '').strip())
            
        normalized_df['quantity'] = df[c_qty].apply(clean_num)
        normalized_df['price'] = df[c_price].apply(clean_num)
        
        final_df = normalized_df.dropna(subset=['date'])
        final_df = final_df[final_df['deal_type'] != 'UNKNOWN']
        
        print(f"DEBUG: Successfully parsed {len(final_df)} valid bulk deal records.")
        return final_df
        
    except Exception as e:
        print(f"ERROR: Exception during bulk deal parsing: {str(e)}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def get_mf_bulk_activity(bulk_df: pd.DataFrame, stock_name: str, months_back: int = 3) -> dict:
    if bulk_df.empty:
        return {
            'mf_buy_count': 0, 'mf_sell_count': 0, 'mf_net_qty': 0,
            'mf_buyers': [], 'mf_sellers': [], 'total_buy_value': 0.0,
            'deals': [], 'verdict': 'No MF Activity'
        }
        
    latest_date = bulk_df['date'].max()
    cutoff_date = latest_date - timedelta(days=months_back * 30)
    df_recent = bulk_df[bulk_df['date'] >= cutoff_date].copy()
    
    def is_mf(name):
        name_str = str(name).upper()
        return any(kw.upper() in name_str for kw in MF_KEYWORDS)
    
    df_mf = df_recent[df_recent['client_name'].apply(is_mf)].copy()
    
    if df_mf.empty:
        return {
            'mf_buy_count': 0, 'mf_sell_count': 0, 'mf_net_qty': 0,
            'mf_buyers': [], 'mf_sellers': [], 'total_buy_value': 0.0,
            'deals': [], 'verdict': 'No MF Activity'
        }
        
    unique_securities = df_mf['security_name'].unique()
    match = process.extractOne(stock_name, unique_securities, scorer=fuzz.WRatio)
    
    if not match or match[1] < 80:
        return {
            'mf_buy_count': 0, 'mf_sell_count': 0, 'mf_net_qty': 0,
            'mf_buyers': [], 'mf_sellers': [], 'total_buy_value': 0.0,
            'deals': [], 'verdict': 'No MF Activity'
        }
        
    target_security = match[0]
    df_stock = df_mf[df_mf['security_name'] == target_security].copy()
    
    buys = df_stock[df_stock['deal_type'] == 'BUY']
    sells = df_stock[df_stock['deal_type'] == 'SELL']
    
    mf_buy_count = len(buys)
    mf_sell_count = len(sells)
    
    buy_qty = buys['quantity'].sum()
    sell_qty = sells['quantity'].sum()
    mf_net_qty = buy_qty - sell_qty
    
    mf_buyers = sorted(list(buys['client_name'].unique()))
    mf_sellers = sorted(list(sells['client_name'].unique()))
    
    total_buy_value = (buys['quantity'] * buys['price']).sum()
    
    if mf_buy_count > 0 and mf_sell_count == 0:
        verdict = 'Strong MF Buying'
    elif mf_buy_count > mf_sell_count and mf_buy_count > 0:
        verdict = 'Strong MF Buying' if mf_net_qty > 0 else 'Mixed'
    elif mf_sell_count > mf_buy_count and mf_sell_count > 0:
        verdict = 'MF Selling'
    elif mf_buy_count > 0 and mf_sell_count > 0:
        verdict = 'Mixed'
    else:
        verdict = 'No MF Activity'
        
    deals = df_stock.sort_values('date', ascending=False).to_dict('records')
    for d in deals:
        if isinstance(d['date'], pd.Timestamp):
            d['date'] = d['date'].strftime('%Y-%m-%d')
            
    return {
        'mf_buy_count': mf_buy_count,
        'mf_sell_count': mf_sell_count,
        'mf_net_qty': int(mf_net_qty),
        'mf_buyers': mf_buyers,
        'mf_sellers': mf_sellers,
        'total_buy_value': float(total_buy_value),
        'deals': deals,
        'verdict': verdict
    }
