import pandas as pd
import os
import glob
import numpy as np
from datetime import datetime

class StockActivityEngine:
    def __init__(self, holdings_folder: str):
        self.holdings_folder = holdings_folder
        self.master_df = pd.DataFrame()

    def load_all(self) -> None:
        """
        Reads all matching Merged CSVs from the top level of holdings_folder,
        skipping NGEN_Holdings_ALL_Merged.csv.
        """
        pattern = os.path.join(self.holdings_folder, "NGEN_Holdings_*_Merged.csv")
        files = glob.glob(pattern)
        
        all_dfs = []
        for file in files:
            if "NGEN_Holdings_ALL_Merged.csv" in file:
                continue
            
            try:
                # Robust separator detection
                with open(file, 'r', encoding='utf-8') as f:
                    first_line = f.readline()
                    sep = '\t' if '\t' in first_line else ','
                
                df = pd.read_csv(file, sep=sep)

                # Filter: type == "Equity" AND assetClass == "Equity"
                df = df[(df['type'] == 'Equity') & (df['assetClass'] == 'Equity')]
                
                # Parse markDate
                try:
                    df['date'] = pd.to_datetime(df['markDate'], format='%d-%m-%Y')
                except Exception:
                    df['date'] = pd.to_datetime(df['markDate'])
                
                # Stock name normalization
                df['stock_name'] = df['name'].str.strip().str.title()
                
                # Renaming columns
                df = df.rename(columns={
                    'Fund Name': 'fund_name',
                    'Category': 'category'
                })
                
                # Ensure perc is float
                df['perc'] = pd.to_numeric(df['perc'], errors='coerce').fillna(0.0)
                
                selected_cols = [
                    'stock_name', 'sector', 'marketcapcat', 'fund_name', 
                    'category', 'date', 'perc', 'shares', 'value'
                ]
                all_dfs.append(df[selected_cols])
                
            except Exception as e:
                print(f"Error loading {file}: {e}")
                
        if all_dfs:
            self.master_df = pd.concat(all_dfs, ignore_index=True)
            self.master_df = self.master_df.drop_duplicates()

            # --- Pre-compute fund-relative metadata ---
            fund_latest_date = self.master_df.groupby('fund_name')['date'].max()
            self.master_df['fund_latest_date'] = self.master_df['fund_name'].map(fund_latest_date)
            
            # Vectorized months difference
            self.master_df['months_back'] = (
                (self.master_df['fund_latest_date'].dt.year - self.master_df['date'].dt.year) * 12 +
                (self.master_df['fund_latest_date'].dt.month - self.master_df['date'].dt.month)
            )

            # --- Diagnostic Report ---
            total_rows = len(self.master_df)
            unique_funds = self.master_df['fund_name'].nunique()
            unique_dates = self.master_df['date'].nunique()
            unique_stocks = self.master_df['stock_name'].nunique()
            
            latest_date = self.master_df['date'].max()
            
            print("\n" + "="*50)
            print("🚀 STOCK ACTIVITY ENGINE - DIAGNOSTIC REPORT")
            print("="*50)
            print(f"1. Total Rows in master_df:   {total_rows:,}")
            print(f"2. Unique Fund Names:         {unique_funds}")
            print(f"3. Unique Dates (Months):      {unique_dates}")
            print(f"4. Unique Stocks:              {unique_stocks}")
            print(f"5. Global Latest Month:        {latest_date.strftime('%b %Y') if latest_date else 'N/A'}")
            print(f"   Latest Month Range: {fund_latest_date.min().strftime('%b %Y')} to {fund_latest_date.max().strftime('%b %Y')}")
            print(f"   Funds per latest month:")
            print(self.master_df.groupby('fund_latest_date')['fund_name'].nunique().to_string())
            print("="*50 + "\n")

    def get_new_entries(self, threshold_pct=1.0, lookback_months=3) -> pd.DataFrame:
        if self.master_df.empty:
            return pd.DataFrame()
            
        df = self.master_df
        
        # Step 1: Latest month rows meeting threshold
        latest = df[
            (df['months_back'] == 0) &
            (df['perc'] >= threshold_pct)
        ].copy()

        # Step 2: Any prior holding within lookback window
        prior = df[
            (df['months_back'] > 0) &
            (df['months_back'] <= lookback_months) &
            (df['perc'] > 0)
        ][['fund_name', 'stock_name']].drop_duplicates()
        prior['had_prior'] = True

        # Step 3: Keep only rows with NO prior holding
        result = latest.merge(prior, on=['fund_name', 'stock_name'], how='left')
        result = result[result['had_prior'].isna()].drop(columns=['had_prior', 'months_back', 'fund_latest_date'])

        if result.empty:
            return pd.DataFrame()

        # Step 4: funds_entering_count per stock
        result['funds_entering_count'] = result.groupby('stock_name')['fund_name'].transform('nunique')

        # Step 5: already_holding_count — funds that held stock in ANY prior month
        already = df[
            (df['months_back'] > 0) &
            (df['perc'] > 0)
        ].groupby('stock_name')['fund_name'].nunique().rename('already_holding_count')
        
        result = result.merge(already, on='stock_name', how='left')
        result['already_holding_count'] = result['already_holding_count'].fillna(0).astype(int)
        result['total_fund_coverage'] = result['funds_entering_count'] + result['already_holding_count']

        result = result.rename(columns={'date': 'entry_date', 'perc': 'entry_weight'})
        return result.sort_values('funds_entering_count', ascending=False).reset_index(drop=True)

    def get_buildup_acceleration(self, min_funds=3, lookback_months=3) -> pd.DataFrame:
        if self.master_df.empty:
            return pd.DataFrame()
            
        df = self.master_df
        # Filter for months 0, 1, 2 for acceleration, and also get shares at window start
        # Use lookback_months for initial shares calculation
        history = df[df['months_back'].isin([0, 1, 2, lookback_months])]
        
        # Pivot for weights (acceleration check)
        w_pivot = history.pivot_table(index=['stock_name', 'fund_name', 'sector', 'marketcapcat'], 
                                   columns='months_back', values='perc').reset_index()
        
        # Pivot for shares (actual accumulation check)
        s_pivot = history.pivot_table(index=['stock_name', 'fund_name'], 
                                   columns='months_back', values='shares').reset_index()
        
        # Ensure weight columns exist
        for col in [0, 1, 2]:
            if col not in w_pivot.columns:
                w_pivot[col] = 0.0
        w_pivot[[0, 1, 2]] = w_pivot[[0, 1, 2]].fillna(0.0)
        
        # Ensure shares columns exist (0 and lookback_months)
        for col in [0, lookback_months]:
            if col not in s_pivot.columns:
                s_pivot[col] = 0.0
        s_pivot[[0, lookback_months]] = s_pivot[[0, lookback_months]].fillna(0.0)

        # Acceleration logic
        w_pivot['delta_recent'] = w_pivot[0] - w_pivot[1]
        w_pivot['delta_prev'] = w_pivot[1] - w_pivot[2]
        
        accelerating = w_pivot[(w_pivot['delta_recent'] > w_pivot['delta_prev']) & 
                               (w_pivot['delta_recent'] > 0) & 
                               (w_pivot['delta_prev'] > 0)].copy()
        
        if accelerating.empty:
            return pd.DataFrame()
            
        # Merge shares data
        s_subset = s_pivot[['stock_name', 'fund_name', 0, lookback_months]].rename(columns={0: 'curr_shares', lookback_months: 'init_shares'})
        accelerating = accelerating.merge(s_subset, on=['stock_name', 'fund_name'], how='left')
        
        # Calculate shares change %
        accelerating['shares_change_pct'] = np.where(
            accelerating['init_shares'] > 0,
            (accelerating['curr_shares'] - accelerating['init_shares']) / accelerating['init_shares'] * 100,
            np.nan
        )

        # Classification (Active Accumulation, Passive Drift, Mixed)
        conds = [
            (accelerating['shares_change_pct'] > 5.0),
            (accelerating['shares_change_pct'] < -5.0),
            (accelerating['shares_change_pct'].between(-5.0, 5.0))
        ]
        choices = ["Active Accumulation", "Mixed (Other holdings growing faster)", "Passive Drift"]
        accelerating['acc_type'] = np.select(conds, choices, default="Unknown")

        # Summary
        summary = accelerating.groupby(['stock_name', 'sector', 'marketcapcat']).agg(
            funds_accelerating=('fund_name', 'count'),
            avg_recent_delta=('delta_recent', 'mean'),
            avg_shares_change_pct=('shares_change_pct', 'mean'),
            accumulation_type=('acc_type', lambda x: x.mode()[0] if not x.empty else "Mixed")
        ).reset_index()
        
        summary = summary[summary['funds_accelerating'] >= min_funds]
        
        if summary.empty:
            return pd.DataFrame()

        top_funds_map = accelerating.sort_values(['stock_name', 'delta_recent'], ascending=[True, False]) \
                                   .groupby('stock_name')['fund_name'] \
                                   .apply(lambda x: " | ".join(x.head(5))).rename('top_funds')
        
        summary = summary.merge(top_funds_map, on='stock_name', how='left')
        
        return summary.sort_values(by='funds_accelerating', ascending=False).reset_index(drop=True)

    def get_partial_exits(self, reduction_threshold_pct=50.0, lookback_months=5, min_funds=2) -> pd.DataFrame:
        if self.master_df.empty:
            return pd.DataFrame()
            
        df = self.master_df
        # Current month
        current = df[df['months_back'] == 0][['stock_name', 'fund_name', 'perc', 'shares']].rename(
            columns={'perc': 'current_perc', 'shares': 'curr_shares'}
        )
        
        # Window window
        window = df[(df['months_back'] > 0) & (df['months_back'] <= lookback_months)]
        
        # Peak
        peaks = window.groupby(['stock_name', 'fund_name', 'sector', 'marketcapcat']).agg(
            peak_perc=('perc', 'max'),
            peak_shares=('shares', 'max')
        ).reset_index()
        
        # Reduction
        merged = peaks[peaks['peak_perc'] >= 0.5].merge(current, on=['stock_name', 'fund_name'], how='left')
        merged['current_perc'] = merged['current_perc'].fillna(0.0)
        merged['curr_shares'] = merged['curr_shares'].fillna(0.0)
        merged['reduction_pct'] = (merged['peak_perc'] - merged['current_perc']) / merged['peak_perc'] * 100
        
        qualifying = merged[merged['reduction_pct'] >= reduction_threshold_pct].copy()
        
        if qualifying.empty:
            return pd.DataFrame()
            
        # Shares change
        qualifying['shares_change_pct'] = np.where(
            qualifying['peak_shares'] > 0,
            (qualifying['curr_shares'] - qualifying['peak_shares']) / qualifying['peak_shares'] * 100,
            np.nan
        )

        # Classification
        conds = [
            (qualifying['shares_change_pct'] < -5.0),
            (qualifying['shares_change_pct'] > 5.0),
            (qualifying['shares_change_pct'].between(-5.0, 5.0))
        ]
        choices = ["Active Selling", "Mixed (Other holdings growing faster — not actively sold)", "Passive Dilution"]
        qualifying['exit_type'] = np.select(conds, choices, default="Unknown")

        # Summary
        summary = qualifying.groupby(['stock_name', 'sector', 'marketcapcat']).agg(
            funds_reducing=('fund_name', 'count'),
            avg_reduction_pct=('reduction_pct', 'mean'),
            avg_peak_weight=('peak_perc', 'mean'),
            avg_current_weight=('current_perc', 'mean'),
            avg_shares_change_pct=('shares_change_pct', 'mean'),
            exit_type=('exit_type', lambda x: x.mode()[0] if not x.empty else "Mixed"),
            fund_names=('fund_name', lambda x: ", ".join(x))
        ).reset_index()
        
        summary = summary[summary['funds_reducing'] >= min_funds]
        
        return summary.sort_values(by='funds_reducing', ascending=False).reset_index(drop=True)

    def get_herd_entries(self, min_funds=5, lookback_months=3) -> pd.DataFrame:
        if self.master_df.empty:
            return pd.DataFrame()
            
        df = self.master_df
        # Window pairs
        window_mask = (df['months_back'] >= 0) & (df['months_back'] < lookback_months)
        within_window = df[window_mask & (df['perc'] > 0)]
        
        # Held Before pairs
        held_before = df[(df['months_back'] >= lookback_months) & (df['perc'] > 0)][['stock_name', 'fund_name']].drop_duplicates()
        held_before['had_before'] = True
        
        # Vectorized Herd filter
        herd = within_window.merge(held_before, on=['stock_name', 'fund_name'], how='left')
        herd = herd[herd['had_before'].isna()].copy()
        
        if herd.empty:
            return pd.DataFrame()
            
        # Aggregates
        herd['first_entry_date'] = herd.groupby(['stock_name', 'fund_name'])['date'].transform('min')
        
        summary = herd.groupby(['stock_name', 'sector', 'marketcapcat']).agg(
            funds_entering=('fund_name', 'nunique'),
            avg_entry_weight=('perc', 'mean'),
            first_entry_date=('first_entry_date', 'min'),
            fund_names=('fund_name', lambda x: ", ".join(set(x)))
        ).reset_index()
        
        summary = summary[summary['funds_entering'] >= min_funds]
        
        return summary.sort_values(by='funds_entering', ascending=False).reset_index(drop=True)

    def get_stock_detail(self, stock_name: str):
        if self.master_df.empty:
            return pd.DataFrame(), pd.DataFrame()
            
        df = self.master_df[self.master_df['stock_name'].str.lower() == stock_name.lower()]
        
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()
            
        weight_pivot = df.pivot_table(index='date', columns='fund_name', values='perc', aggfunc='first')
        shares_pivot = df.pivot_table(index='date', columns='fund_name', values='shares', aggfunc='first')
        
        weight_pivot = weight_pivot.sort_index(ascending=False).fillna(0.0)
        shares_pivot = shares_pivot.sort_index(ascending=False).fillna(0.0)
        return weight_pivot, shares_pivot

    def get_stock_detail_with_entrants(self, stock_name: str, lookback_months: int = 3, threshold_pct: float = 1.0):
        """
        Returns a tuple: (weight_pivot, shares_pivot, new_entrant_fund_names)
        """
        w_pivot, s_pivot = self.get_stock_detail(stock_name)
        
        # Reuse new entries logic, filtered to this stock
        new_entries_df = self.get_new_entries(threshold_pct=threshold_pct, lookback_months=lookback_months)
        if not new_entries_df.empty:
            new_entrant_funds = new_entries_df[
                new_entries_df['stock_name'].str.lower() == stock_name.lower()
            ]['fund_name'].unique().tolist()
        else:
            new_entrant_funds = []
        
        return w_pivot, s_pivot, new_entrant_funds

    def get_sector_peers_activity(self, stock_name: str, lookback_months: int = 1):
        """
        Analyze peer activity within the same sector to identify potential rotation.
        """
        if self.master_df.empty:
            return {"sector": "N/A", "peer_count": 0, "peers": [], "is_rotation": False}
            
        stock_info = self.master_df[self.master_df['stock_name'].str.lower() == stock_name.lower()]
        if stock_info.empty:
            return {"sector": "N/A", "peer_count": 0, "peers": [], "is_rotation": False}
        
        sector_name = stock_info['sector'].iloc[0]
        
        # Get all new entries in the window
        new_entries_df = self.get_new_entries(threshold_pct=1.0, lookback_months=lookback_months)
        
        if new_entries_df.empty:
            return {"sector": sector_name, "peer_count": 0, "peers": [], "is_rotation": False}
            
        peers_df = new_entries_df[
            (new_entries_df['sector'] == sector_name) & 
            (new_entries_df['stock_name'].str.lower() != stock_name.lower())
        ]
        
        peers_list = sorted(peers_df['stock_name'].unique().tolist())
        peer_count = len(peers_list)
        
        return {
            "sector": sector_name,
            "peer_count": peer_count,
            "peers": peers_list,
            "is_rotation": peer_count >= 1
        }
