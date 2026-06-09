import os
import pandas as pd
import re

# NGEN Data Loader
# Version: 1.0.0
# Built for: Altus Family Office
# Last updated: 2024-05-22

# Dynamic base directory: look for 'downloads/holdings' in the current working directory
BASE_DIR = os.path.join(os.getcwd(), "downloads", "holdings")

FOLDER_MAPPING = {
    "Contra_Fund": "Contra Fund",
    "Dividend_Yield_Fund": "Dividend Yield Fund",
    "ELSS": "ELSS",
    "Flexi_Cap_Fund": "Flexi Cap Fund",
    "Focused_Fund": "Focused Fund",
    "Large_&_Mid_Cap_Fund": "Large & Mid Cap Fund",
    "Large_Cap_Fund": "Large Cap Fund",
    "Mid_Cap_Fund": "Mid Cap Fund",
    "Multi_Cap_Fund": "Multi Cap Fund",
    "Small_Cap_Fund": "Small Cap Fund",
    "Value_Fund": "Value Fund",
}

def scan_downloads(base_dir: str) -> dict:
    """
    Scans the directory for per-fund holdings CSVs and builds a catalog.
    Returns: { "Equity": { "Category Name": [ {"fund_name": "...", "amficode": 123, "filepath": "..."}, ... ] } }
    """
    if not os.path.exists(base_dir):
        return {}

    catalog = {"Equity": {}}
    
    # Iterate through subfolders (categories)
    for folder_name in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder_name)
        
        if not os.path.isdir(folder_path):
            continue
            
        display_category = FOLDER_MAPPING.get(folder_name)
        if not display_category:
            continue
            
        fund_list = []
        
        # Scan files in the category folder
        if os.path.exists(folder_path):
            for filename in os.listdir(folder_path):
                if not filename.startswith("NGEN_Holdings_") or not filename.endswith(".csv"):
                    continue
                    
                filepath = os.path.join(folder_path, filename)
                
                try:
                    # 1. Extract amficode from filename (last numeric segment)
                    # Format: NGEN_Holdings_<FundName>_<amficode>.csv
                    match = re.search(r'(\d+)\.csv$', filename)
                    amficode = int(match.group(1)) if match else 0
                    
                    # 2. Extract fund_name from Row 1 of CSV
                    # Format: "Positions Over Time - <Fund Name>"
                    with open(filepath, 'r', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                        fund_name = first_line.replace("Positions Over Time - ", "").strip()
                    
                    if not fund_name:
                        fund_name = filename.replace("NGEN_Holdings_", "").replace(f"_{amficode}.csv", "").replace("_", " ")

                    fund_list.append({
                        "fund_name": fund_name,
                        "amficode": amficode,
                        "filepath": filepath
                    })
                    
                except Exception:
                    # Skip unreadable or malformed files silently
                    continue
        
        if fund_list:
            # Sort funds alphabetically by name
            fund_list.sort(key=lambda x: x["fund_name"])
            catalog["Equity"][display_category] = fund_list
            
    return catalog

def load_fund_holdings(filepath: str) -> pd.DataFrame:
    """
    Loads fund holdings from CSV, skipping the title row.
    Row 2 is used as headers. Data values like "-" are kept as strings.
    """
    try:
        # Skip Row 1 (Title Row), use Row 2 as Header
        df = pd.read_csv(filepath, skiprows=1)
        
        # Strip potential whitespace from column names
        df.columns = [str(c).strip() for c in df.columns]
        
        return df
    except Exception:
        return pd.DataFrame()

def get_all_fund_names(catalog: dict) -> list:
    """Returns a flat, sorted list of all fund_names found in the catalog."""
    names = []
    equity_group = catalog.get("Equity", {})
    for cat_list in equity_group.values():
        for fund in cat_list:
            names.append(fund["fund_name"])
    return sorted(list(set(names)))

def get_funds_by_category(catalog: dict, category: str) -> list:
    """Returns the list of fund dictionaries for a specific display category name."""
    return catalog.get("Equity", {}).get(category, [])

if __name__ == "__main__":
    # Local test
    cat = scan_downloads(BASE_DIR)
    for group, categories in cat.items():
        print(f"Group: {group}")
        for cname, flist in categories.items():
            print(f"  - {cname}: {len(flist)} funds")
            if flist:
                print(f"    Example: {flist[0]['fund_name']} ({flist[0]['amficode']})")

# === END OF ngen_data_loader.py ===
