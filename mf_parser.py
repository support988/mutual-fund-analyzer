import pandas as pd
import io
import datetime

def parse_mf_csv(file_path):
    """
    Parses the specific Mutual Fund CSV format.
    Row 1: Title (Extract fund name)
    Row 2: Headers (Type, Name, Sector, Dates...)
    Rows 3+: Data
    """
    try:
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        first_line = None
        csv_error = None
        df = None

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    first_line = f.readline().strip()
                df = pd.read_csv(file_path, skiprows=1, encoding=encoding)
                break
            except Exception as e:
                csv_error = e

        if df is None:
            raise csv_error
            
        fund_name = first_line.replace("Positions Over Time - ", "").strip()
        if not fund_name:
            fund_name = "Unknown Fund"
        
        # Clean column names (strip whitespace)
        df.columns = [c.strip() for c in df.columns]
        
        # Identify date columns (usually from index 3 onwards)
        # Format: DD-Mon-YY (e.g., 30-Apr-26)
        all_cols = list(df.columns)
        metadata_cols = ['Type', 'Name', 'Sector']
        date_cols = [c for c in all_cols if c not in metadata_cols]
        
        # Parse dates and rename columns to datetime objects for internal consistency
        date_mapping = {}
        for col in date_cols:
            try:
                dt = pd.to_datetime(col, format='%d-%b-%y')
                date_mapping[col] = dt
            except Exception:
                # If it's not a date, we might want to keep it or drop it.
                # In this specific format, they should all be dates.
                pass
        
        df = df.rename(columns=date_mapping)
        actual_date_cols = list(date_mapping.values())
        
        # Drop trailing unnamed columns created by trailing commas in CSV header
        df = df[[c for c in df.columns if not str(c).startswith('Unnamed:')]]
        actual_date_cols = [c for c in actual_date_cols if c in df.columns]
        
        # Data Cleaning:
        # 1. Skip rows where Name is blank or Type is "Net CA & Others"
        df = df[df['Name'].notna()]
        df = df[df['Name'].str.strip() != ""]
        df = df[df['Type'].str.strip() != "Net CA & Others"]
        
        # 2. Treat "-" as 0.0
        for col in actual_date_cols:
            df[col] = df[col].astype(str).replace('-', '0.0').replace('nan', '0.0').astype(float)
            
        # 3. Strip whitespace from Name and Sector
        df['Name'] = df['Name'].str.strip()
        df['Sector'] = df['Sector'].str.strip()
        
        return {
            'fund_name': fund_name,
            'df': df,
            'dates': sorted(actual_date_cols)
        }
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None
