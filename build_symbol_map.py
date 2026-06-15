"""
One-time script: build stock_symbol_map.csv mapping every NGEN holding 
name to its NSE/BSE symbol and ISIN, using local bhavcopy files.
"""
import pandas as pd
import glob
import os
import re
from rapidfuzz import process, fuzz
from stock_activity_engine import StockActivityEngine

DOWNLOADS_DIR = r"D:\Mukul\TV\Project\MF\downloads"
OUTPUT_PATH = os.path.join(DOWNLOADS_DIR, "stock_symbol_map.csv")

def clean_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    cleaned = name.upper()
    # Remove common suffixes/words
    for suffix in [" LTD", " LIMITED", " INDIA", " CO.", " CO", " CORPN.", " CORPORATION", 
                    " INDUSTRIES", " INDS.", " INDS", "(G)", " PVT", " PRIVATE"]:
        cleaned = cleaned.replace(suffix, "")
    # Remove dots, extra spaces, ampersands normalization
    cleaned = cleaned.replace(".", "").replace("&", "AND")
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

COMMON_MAPS = {
    "Sbi": "SBIN", "Sbi Life Insuran": "SBILIFE", "Sbi Cards": "SBICARD",
    "Hdfc Bank": "HDFCBANK", "Hdfc Life": "HDFCLIFE", "Hdfc Amc": "HDFCAMC",
    "Icici Bank": "ICICIBANK", "Icici Pru Life": "ICICIPRULI", "Icici Lombard": "ICICIGI",
    "Kotak Mah. Bank": "KOTAKBANK", "Axis Bank": "AXISBANK",
    "Reliance Industr": "RELIANCE", "Infosys": "INFY", "Tcs": "TCS",
    "Itc": "ITC", "Tech Mahindra": "TECHM", "Wipro": "WIPRO",
    "Larsen & Toubro": "LT", "Bharti Airtel": "BHARTIARTL",
    "Bharat Electron": "BEL", "Bharat Forge": "BHARATFORG",
    "Hindalco": "HINDALCO", "Hindustan Unilever": "HINDUNILVR", "Hind. Unilever": "HINDUNILVR",
    "Maruti Suzuki": "MARUTI", "Mahindra & Mahindra": "M&M", "Tata Motors Pveh": "TATAMOTORS",
    "Tata Steel": "TATASTEEL", "Tata Power Co.": "TATAPOWER", "Tata Consumer": "TATACONSUM",
    "Ultratech Cem.": "ULTRACEMCO", "Shree Cement": "SHREECEM", "Ambuja Cements": "AMBUJACEM",
    "Power Fin.Corpn.": "PFC", "Rec Ltd": "RECLTD", "Bajaj Finserv": "BAJFINANCE",
    "Bajaj Auto": "BAJAJ-AUTO", "Bajaj Finance": "BAJFINANCE",
    "Adani Enterp.": "ADANIENT", "Adani Ports": "ADANIPORTS", "Adani Power": "ADANIPOWER",
    "Adani Energy Sol": "ADANIENSOL", "Adani Green": "ADANIGREEN",
    "B H E L": "BHEL", "S A I L": "SAIL", "Cg Power & Ind": "CGPOWER",
    "Samvardh. Mothe.": "MOTHERSON", "Persistent Syste": "PERSISTENT",
    "Au Small Finance": "AUBANK", "Pnb Housing": "PNBHOUSING",
    "Natco Pharma": "NATCOPHARM", "Aurobindo Pharma": "AUROPHARMA",
    "Sun Pharma": "SUNPHARMA", "Dr Reddys Labs": "DRREDDY", "Cipla": "CIPLA",
    "Divis Lab": "DIVISLAB", "Lupin": "LUPIN", "Torrent Pharma": "TORNTPHARM",
    "Apar Inds.": "APARINDS", "Finolex Cables": "FINCABLES",
    "Welspun Corp": "WELCORP", "Bank Of Maha": "MAHABANK",
    "Granules India": "GRANULES", "Marksans Pharma": "MARKSANS",
    "Vedanta Aluminium": "VEDL", "A B B": "ABB", "Solar Industries": "SOLARINDS",
    "Ntpc": "NTPC", "Ongc": "ONGC", "Coal India": "COALINDIA", "Power Grid": "POWERGRID",
    "Indusind Bank": "INDUSINDBK", "Federal Bank": "FEDERALBNK", "Bank Of Baroda": "BANKBARODA",
    "Punjab National Bank": "PNB", "Canara Bank": "CANBK",
    "Asian Paints": "ASIANPAINT", "Nestle India": "NESTLEIND", "Britannia": "BRITANNIA",
    "Dabur India": "DABUR", "Marico": "MARICO", "Godrej Consumer": "GODREJCP",
    "Titan Company": "TITAN", "Trent": "TRENT", "Avenue Supermarts": "DMART",
    "Pidilite Inds.": "PIDILITIND", "Havells India": "HAVELLS",
    "Eicher Motors": "EICHERMOT", "Hero Motocorp": "HEROMOTOCO", "Tvs Motor Co.": "TVSMOTOR",
    "Indian Hotels Co": "INDHOTEL", "Interglobe Aviat": "INDIGO",
    "Zomato": "ETERNAL", "Eternal": "ETERNAL", "Nykaa": "NYKAA",
    "Polycab India": "POLYCAB", "Dixon Technol.": "DIXON",
    "Jsw Steel": "JSWSTEEL", "Jindal Steel": "JINDALSTEL",
    "Lt Foods": "LTFOODS", "Page Industries": "PAGEIND",
    "Muthoot Finance": "MUTHOOTFIN", "Cholaman.Inv.&Fn": "CHOLAFIN",
    "Indian Railway Catering & Tourism Corp": "IRCTC", "Irctc": "IRCTC",
    "Container Corpn.": "CONCOR", "Gail (India)": "GAIL",
    "Bharat Petroleum": "BPCL", "Hindustan Petrol": "HINDPETRO", "Indian Oil Corpn": "IOC",
    "Dlf": "DLF", "Srf": "SRF", "Bse": "BSE", "Ncc": "NCC", "Ghcl": "GHCL", "Infy": "INFY",
}

# --- Step 1: Auto-discover bhavcopy files ---
all_csvs = glob.glob(os.path.join(DOWNLOADS_DIR, "*.csv")) + glob.glob(os.path.join(DOWNLOADS_DIR, "*.CSV"))
print("CSV files found in downloads folder:")
for f in all_csvs:
    print(f"  {os.path.basename(f)}")

nse_file, bse_file = None, None
for f in all_csvs:
    try:
        df_head = pd.read_csv(f, nrows=5)
        cols_upper = [c.strip().upper() for c in df_head.columns]
        if 'TCKRSYMB' in cols_upper and 'ISIN' in cols_upper:
            if 'SRC' in cols_upper:
                src_val = str(df_head['Src'].iloc[0]).upper() if not df_head['Src'].empty else ""
                if 'NSE' in src_val: nse_file = f
                elif 'BSE' in src_val: bse_file = f
            if not nse_file and 'NSE' in os.path.basename(f).upper(): nse_file = f
            if not bse_file and 'BSE' in os.path.basename(f).upper(): bse_file = f
    except Exception as e:
        print(f"  Could not read {f}: {e}")

if not nse_file or not bse_file:
    print(f"NSE detected: {nse_file}, BSE detected: {bse_file}")
    raise SystemExit("Fix file detection and re-run.")

# --- Step 2: Load NGEN stock names ---
engine = StockActivityEngine(r"D:\Mukul\TV\Project\MF\downloads\holdings")
engine.load_all()
ngen_names = sorted(engine.master_df['stock_name'].unique())

# --- Step 3: Load NSE & BSE bhavcopy ---
def load_bhav(filepath, is_nse):
    df = pd.read_csv(filepath)
    df.columns = [c.strip().upper() for c in df.columns]
    if 'TCKRSYMB' in df.columns:
        df = df.rename(columns={'TCKRSYMB': 'SYMBOL', 'FININSTRMNM': 'NAME'})
    
    isin_col = next((c for c in df.columns if 'ISIN' in c), None)
    
    if is_nse:
        if 'SCTYSRS' in df.columns: df = df[df['SCTYSRS'].str.strip() == 'EQ']
        elif 'SERIES' in df.columns: df = df[df['SERIES'].str.strip() == 'EQ']
        df = df[['SYMBOL', isin_col]].drop_duplicates()
        df.columns = ['nse_symbol', 'isin']
    else:
        # For BSE, SC_NAME or NAME
        name_col = next((c for c in df.columns if 'NAME' in c and 'COMPANY' not in c), 'NAME')
        df = df[['SYMBOL', name_col, isin_col]].drop_duplicates()
        df.columns = ['bse_code', 'bse_name', 'isin']
    
    df['isin'] = df['isin'].str.strip()
    return df

nse_df = load_bhav(nse_file, True)
bse_df = load_bhav(bse_file, False)

# --- Step 4: Master ISIN lookup ---
master = nse_df.merge(bse_df, on='isin', how='outer')
master['match_name'] = master['bse_name'].fillna(master['nse_symbol'])
match_candidates = master.dropna(subset=['match_name']).copy()
match_candidates['clean_match_name'] = match_candidates['match_name'].apply(clean_name)

# Lookup for exact symbol matches
nse_symbol_lookup = {str(row['nse_symbol']).upper(): row for _, row in master.dropna(subset=['nse_symbol']).iterrows()}

# --- Step 5: Matching logic ---
results = []
for ngen_name in ngen_names:
    cleaned_ngen = clean_name(ngen_name).replace(" ", "")
    match_method = None
    row = None
    score = 0
    
    # Priority 1: COMMON_MAPS override
    if ngen_name in COMMON_MAPS:
        symbol = COMMON_MAPS[ngen_name]
        found = master[master['nse_symbol'] == symbol]
        if not found.empty:
            row = found.iloc[0]
            match_method = "common_map"
            score = 100
        else:
            results.append({
                "ngen_name": ngen_name, "nse_symbol": symbol, "bse_code": None,
                "isin": None, "matched_name": ngen_name, "match_score": 100,
                "yf_ticker": f"{symbol}.NS", "match_method": "common_map"
            })
            continue

    # Priority 2: Exact match against NSE symbol
    if not match_method and cleaned_ngen in nse_symbol_lookup:
        row = nse_symbol_lookup[cleaned_ngen]
        match_method = "exact"
        score = 100

    # Priority 3: Fuzzy match on cleaned names
    if not match_method:
        best_match = process.extractOne(
            clean_name(ngen_name), match_candidates['clean_match_name'].tolist(), scorer=fuzz.WRatio
        )
        if best_match:
            _, score, idx = best_match
            row = match_candidates.iloc[idx]
            match_method = "fuzzy"

    if row is not None:
        nse_symbol = row['nse_symbol'] if pd.notna(row['nse_symbol']) else None
        bse_code = row['bse_code'] if pd.notna(row['bse_code']) else None
        results.append({
            "ngen_name": ngen_name,
            "nse_symbol": nse_symbol,
            "bse_code": bse_code,
            "isin": row['isin'],
            "matched_name": row['match_name'],
            "match_score": score,
            "yf_ticker": f"{nse_symbol}.NS" if nse_symbol else f"{bse_code}.BO",
            "match_method": match_method
        })
    else:
        results.append({
            "ngen_name": ngen_name, "nse_symbol": None, "bse_code": None,
            "isin": None, "matched_name": None, "match_score": 0,
            "yf_ticker": None, "match_method": "none"
        })

map_df = pd.DataFrame(results).sort_values("match_score")
map_df.to_csv(OUTPUT_PATH, index=False)

print(f"\n✅ Saved {OUTPUT_PATH}")
print(f"Resolved via NSE symbol exact match: {len([r for r in results if r.get('match_method')=='exact'])}")
print(f"Resolved via COMMON_MAPS: {len([r for r in results if r.get('match_method')=='common_map'])}")
print(f"Resolved via fuzzy match (score>=85): {len([r for r in results if r.get('match_method')=='fuzzy' and r.get('match_score')>=85])}")
print(f"Still unresolved (score<85): {len([r for r in results if r.get('match_score')<85])}")

low_conf = map_df[map_df['match_score'] < 85]
print("\n--- LOW CONFIDENCE MATCHES ---")
print(low_conf[['ngen_name', 'matched_name', 'yf_ticker', 'match_score', 'match_method']].to_string(index=False))
