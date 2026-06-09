"""
NGEN Markets – Holdings History Downloader
==========================================
Fetches "Positions Over Time" (Asset Allocation → Positions Over Time tab)
for every Direct fund across all specified SEBI categories.

Output format matches the NGEN UI CSV exactly:
  Row 1  : Title header  "Positions Over Time - <Fund Name>"
  Row 2  : Columns       Type, Name, Sector, <date1>, <date2>, ...
  Row 3+ : One row per security, dates as columns (wide/pivot format)
  Values : % allocation (e.g. 3.49), "-" where not held

Output folder structure (inside --out dir):
  holdings/
    <Category>/
      NGEN_Holdings_<FundName>_<amficode>.csv   ← one file per fund
    NGEN_Holdings_<Category>_Merged.csv          ← all funds stacked (long format)
    NGEN_Holdings_ALL_Merged.csv                 ← everything merged (long format)

Requirements:
    pip install requests pandas

Usage:
    python ngen_holdings_history.py
    python ngen_holdings_history.py --out "C:/MyFolder" --months 24
    python ngen_holdings_history.py --category "Flexi Cap Fund" --months 12
    python ngen_holdings_history.py --equity-only
"""

import requests
import pandas as pd
import argparse
import os
import time
from datetime import date

# ─── CONFIG ──────────────────────────────────────────────────────────────────

BASE_URL = "https://ngenjs.ngenmarkets.in/execute"
AMFI_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

CATEGORIES = [
    "Contra Fund",
    "Dividend Yield Fund",
    "ELSS",
    "Flexi Cap Fund",
    "Focused Fund",
    "Large & Mid Cap Fund",
    "Large Cap Fund",
    "Mid Cap Fund",
    "Multi Cap Fund",
    "Small Cap Fund",
    "Value Fund",
    "Sectoral/Thematic Fund",
    "Equity Index Fund",
    "ETFs Equity",
]

HEADERS = {
    "Accept":             "application/json, text/javascript, */*; q=0.01",
    "Accept-Language":    "en-US,en;q=0.9",
    "Connection":         "keep-alive",
    "Origin":             "https://ai.ngenmarkets.in",
    "Referer":            "https://ai.ngenmarkets.in/",
    "Sec-Fetch-Dest":     "empty",
    "Sec-Fetch-Mode":     "cors",
    "Sec-Fetch-Site":     "same-site",
    "User-Agent":         ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/148.0.0.0 Safari/537.36"),
    "sec-ch-ua":          '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile":   "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# ─── ISIN LOOKUP ─────────────────────────────────────────────────────────────

def build_isin_lookup() -> dict:
    """Download AMFI NAV file → {amficode (int): fund_isin (str)}."""
    try:
        print("  Fetching Fund ISINs from AMFI...", end=" ", flush=True)
        r = requests.get(AMFI_URL, timeout=20,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        lookup = {}
        for line in r.text.splitlines():
            parts = line.split(";")
            if len(parts) >= 3:
                code = parts[0].strip()
                isin = parts[1].strip()
                if code.isdigit() and isin.startswith("INF"):
                    lookup[int(code)] = isin
        print(f"OK  {len(lookup):,} ISINs loaded")
        return lookup
    except Exception as e:
        print(f"WARNING  Could not load ISIN data ({e}). Fund ISIN column will be blank.")
        return {}

# ─── STEP 1: Fund list for a category ────────────────────────────────────────

def fetch_fund_list(category: str, top: int = 500) -> list:
    today = date.today().strftime("%d-%b-%Y").lstrip("0")
    query = (
        f"exec c_mksort_schemes_ngenclass_raw "
        f"'''{category}''','',0,'Direct Fund','','fs_ngen','DESC',"
        f"{top},'{today}',0,-10,-100,'onemonth',-1000"
    )
    resp = requests.get(BASE_URL, params={"a": query},
                        headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [
        {
            "amficode": int(item["amficode"]),
            "name":     item.get("name", f"Fund_{item['amficode']}"),
            "category": item.get("category", category),
        }
        for item in data
        if item.get("amficode")
    ]

# ─── STEP 2: Holdings history for one fund ───────────────────────────────────

def fetch_holdings(amficode: int, months: int = 12) -> list:
    """Calls: exec c_getHoldingsHistory <amficode>, <months>"""
    query = f"exec c_getHoldingsHistory {amficode},{months}"
    resp  = requests.get(BASE_URL, params={"a": query},
                         headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()

# ─── FORMAT DATE: "2026-04-30T00:00:00.000Z" → "30-Apr-26" ──────────────────

def fmt_date(iso: str) -> str:
    """Convert ISO date string to NGEN UI display format: 30-Apr-26"""
    try:
        from datetime import datetime
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
        # %d gives 2-digit day. If we want 1-digit for 1-9, we use lstrip('0')
        # However, %d-%b-%y is safest for parsing back.
        return d.strftime("%d-%b-%y")
    except Exception:
        return iso[:10]

# ─── BUILD WIDE-FORMAT DF MATCHING NGEN UI CSV ───────────────────────────────

def holdings_to_wide(raw: list, fund_name: str,
                     equity_only: bool = False) -> pd.DataFrame:
    """
    Converts raw API list → wide pivot matching NGEN UI export:
      Columns: Type | Name | Sector | <date1> | <date2> | ...
      Dates:   sorted newest → oldest (left to right)
      Values:  perc float, NaN filled with "-"
    """
    if not raw:
        return pd.DataFrame()

    rows = []
    for h in raw:
        if equity_only and h.get("assetClass", "").lower() != "equity":
            continue
        mark_iso = h.get("markDate", "")
        rows.append({
            "Type":    h.get("type", "-"),
            "Name":    h.get("name", "-"),
            "Sector":  h.get("sector", "-"),
            "_date":   mark_iso[:10],           # YYYY-MM-DD for sorting
            "_disp":   fmt_date(mark_iso),      # display label
            "perc":    h.get("perc", None),
        })

    if not rows:
        return pd.DataFrame()

    df_long = pd.DataFrame(rows)

    # Build display-date map sorted newest → oldest
    date_map = (df_long[["_date", "_disp"]]
                .drop_duplicates()
                .sort_values("_date", ascending=False))
    ordered_dates   = date_map["_date"].tolist()
    ordered_display = date_map["_disp"].tolist()

    # Pivot: index = (Type, Name, Sector), columns = _date
    pivot = df_long.pivot_table(
        index=["Type", "Name", "Sector"],
        columns="_date",
        values="perc",
        aggfunc="first",
    ).reset_index()

    # Reorder date columns newest → oldest
    date_cols_present = [d for d in ordered_dates if d in pivot.columns]
    pivot = pivot[["Type", "Name", "Sector"] + date_cols_present]

    # Rename date columns to display format
    date_rename = dict(zip(ordered_dates, ordered_display))
    pivot = pivot.rename(columns=date_rename)

    # Replace NaN with "-"
    disp_cols = [date_rename[d] for d in date_cols_present]
    pivot[disp_cols] = pivot[disp_cols].fillna("-")

    # Sort: Equity first, then by most-recent-date desc
    most_recent = disp_cols[0] if disp_cols else None
    if most_recent:
        def sort_key(row):
            v = row[most_recent]
            return (0 if row["Type"] == "Equity" else 1,
                    -float(v) if v != "-" else 0)
        pivot = pivot.iloc[pivot.apply(sort_key, axis=1).argsort()].reset_index(drop=True)

    return pivot

# ─── LONG FORMAT for merged files ────────────────────────────────────────────

def holdings_to_long(raw: list, fund_name: str, amficode: int,
                     fund_isin: str, category: str,
                     equity_only: bool = False) -> pd.DataFrame:
    """Long format for category/global merged CSVs."""
    rows = []
    for h in raw:
        if equity_only and h.get("assetClass", "").lower() != "equity":
            continue
        rows.append({
            "Fund Name":  fund_name,
            "AMFI Code":  amficode,
            "Fund ISIN":  fund_isin,
            "Category":   category,
            "markDate":   h.get("markDate", "")[:10],
            "type":       h.get("type", "-"),
            "assetClass": h.get("assetClass", "-"),
            "sector":     h.get("sector", "-"),
            "name":       h.get("name", "-"),
            "marketcapcat": h.get("marketcapcat") or "-",
            "rating":     h.get("rating", "-"),
            "perc":       h.get("perc", None),
            "value":      h.get("value", None),
            "shares":     h.get("shares", None),
        })
    return pd.DataFrame(rows)

# ─── WRITE WIDE CSV with title header (matching NGEN UI export) ──────────────

def save_wide_csv(df_wide: pd.DataFrame, fund_name: str, path: str):
    """
    Writes CSV with NGEN-style title row:
      Row 1: "Positions Over Time - <Fund Name>"
      Row 2: column headers
      Row 3+: data
    """
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(f"Positions Over Time - {fund_name}\n")
    df_wide.to_csv(path, index=False, mode="a", encoding="utf-8")

# ─── SAFE FILENAME ────────────────────────────────────────────────────────────

def safe(s: str) -> str:
    return (s.replace("/", "-").replace("\\", "-")
             .replace(":", "").replace("*", "")
             .replace("?", "").replace('"', "")
             .replace("<", "").replace(">", "")
             .replace("|", "").replace(" ", "_"))

# ─── MAIN RUNNER ─────────────────────────────────────────────────────────────

def run(categories: list, months: int, out_dir: str,
        equity_only: bool, delay: float):

    holdings_dir = os.path.join(out_dir, "holdings")
    os.makedirs(holdings_dir, exist_ok=True)

    isin_lookup = build_isin_lookup()

    all_long_dfs = []

    for category in categories:
        print(f"\n{'='*60}")
        print(f"  Category: {category}")
        print(f"{'='*60}")

        try:
            funds = fetch_fund_list(category)
            print(f"  Found {len(funds)} Direct funds")
        except Exception as e:
            print(f"  ERROR Could not fetch fund list: {e}")
            continue

        if not funds:
            print("  No funds returned, skipping.")
            continue

        cat_dir = os.path.join(holdings_dir, safe(category))
        os.makedirs(cat_dir, exist_ok=True)

        cat_long_dfs = []

        for i, fund in enumerate(funds, 1):
            amfi  = fund["amficode"]
            name  = fund["name"]
            fisin = isin_lookup.get(amfi, "-")

            print(f"  [{i:3}/{len(funds)}] {name[:55]:<55}", end=" ", flush=True)

            try:
                raw = fetch_holdings(amfi, months)

                # ── Wide CSV (per fund, matching UI format) ──────────────────
                df_wide = holdings_to_wide(raw, name, equity_only)
                if df_wide.empty:
                    print("WARNING  no data")
                    time.sleep(delay)
                    continue

                fname = f"NGEN_Holdings_{safe(name)}_{amfi}.csv"
                fpath = os.path.join(cat_dir, fname)
                save_wide_csv(df_wide, name, fpath)

                n_months = len(df_wide.columns) - 3   # subtract Type/Name/Sector
                n_rows   = len(df_wide)
                print(f"OK  {n_months} months, {n_rows} securities -> {fname}")

                # ── Long format for merged files ─────────────────────────────
                df_long = holdings_to_long(raw, name, amfi, fisin,
                                           category, equity_only)
                if not df_long.empty:
                    cat_long_dfs.append(df_long)
                    all_long_dfs.append(df_long)

            except requests.HTTPError as e:
                print(f"ERROR HTTP {e.response.status_code}")
            except Exception as e:
                print(f"ERROR {e}")

            time.sleep(delay)

        # ── Category merged (long) ────────────────────────────────────────────
        if cat_long_dfs:
            cat_merged = pd.concat(cat_long_dfs, ignore_index=True)
            cat_path   = os.path.join(holdings_dir,
                                      f"NGEN_Holdings_{safe(category)}_Merged.csv")
            cat_merged.to_csv(cat_path, index=False, encoding="utf-8")
            print(f"\n  DONE Category merged ({len(cat_merged):,} rows) -> {cat_path}")

    # ── Global merged (long) ──────────────────────────────────────────────────
    if all_long_dfs:
        all_merged = pd.concat(all_long_dfs, ignore_index=True)
        all_path   = os.path.join(holdings_dir, "NGEN_Holdings_ALL_Merged.csv")
        all_merged.to_csv(all_path, index=False, encoding="utf-8")
        n_funds = all_merged["AMFI Code"].nunique()
        print(f"\n{'='*60}")
        print(f"  ALL DONE -- {n_funds} funds, {len(all_merged):,} total rows")
        print(f"  Global merged file -> {all_path}")
        print(f"{'='*60}")
    else:
        print("\n  No data was saved.")

# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download NGEN Markets Holdings History (Positions Over Time)"
    )
    parser.add_argument("--out", "-o", default="downloads",
                        help="Output root folder (default: downloads/)")
    parser.add_argument("--months", "-m", type=int, default=12,
                        help="Months of history to fetch per fund (default: 12)")
    parser.add_argument("--category", "-c", default=None,
                        help="Fetch only one category e.g. 'Flexi Cap Fund'")
    parser.add_argument("--equity-only", action="store_true",
                        help="Keep only rows where type == 'Equity'")
    parser.add_argument("--delay", "-d", type=float, default=0.3,
                        help="Seconds between requests (default: 0.3)")
    args = parser.parse_args()

    cats = [args.category] if args.category else CATEGORIES

    print(f"\nNGEN Holdings History Downloader")
    print(f"  Output folder : {args.out}/holdings/")
    print(f"  Months        : {args.months}")
    print(f"  Categories    : {len(cats)}")
    print(f"  Equity only   : {args.equity_only}")
    print(f"  Request delay : {args.delay}s")

    run(categories=cats, months=args.months, out_dir=args.out,
        equity_only=args.equity_only, delay=args.delay)


if __name__ == "__main__":
    main()
