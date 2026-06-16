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
        # Force integer to avoid type mismatch in column lookups
        lookback_months = int(lookback_months)
        
        # Defensive: Explicit relevant months list
        # We need 0, 1, 2 for acceleration and 'lookback_months' for shares baseline
        relevant_months = sorted(list(set([0, 1, 2, lookback_months])))

        # Filter for relevant months
        history = df[df['months_back'].isin(relevant_months)]
        
        # Pivot for weights (acceleration check)
        w_pivot = history.pivot_table(index=['stock_name', 'fund_name', 'sector', 'marketcapcat'], 
                                   columns='months_back', values='perc').reset_index()
        
        # Pivot for shares (actual accumulation check)
        s_pivot = history.pivot_table(index=['stock_name', 'fund_name'], 
                                   columns='months_back', values='shares').reset_index()
        
        # Defensive: Normalize column labels to integers (handles string-casting in some environments)
        for p_df in [w_pivot, s_pivot]:
            p_df.columns = [int(c) if (isinstance(c, str) and c.isdigit()) else c for c in p_df.columns]

        # Defensive: Ensure all required columns exist in w_pivot and fillna
        required_w = [0, 1, 2]
        for col in required_w:
            if col not in w_pivot.columns:
                w_pivot[col] = 0.0
        w_pivot[required_w] = w_pivot[required_w].fillna(0.0)
        
        # Defensive: Ensure required columns exist in s_pivot and fillna
        required_s = [0, lookback_months]
        for col in required_s:
            if col not in s_pivot.columns:
                s_pivot[col] = 0.0
        # set() handles case where lookback_months is 0
        s_pivot[list(set(required_s))] = s_pivot[list(set(required_s))].fillna(0.0)

        # Acceleration logic - Explicitly assigned before filtering
        w_pivot['delta_recent'] = w_pivot[0] - w_pivot[1]
        w_pivot['delta_prev'] = w_pivot[1] - w_pivot[2]
        
        accelerating = w_pivot[(w_pivot['delta_recent'] > w_pivot['delta_prev']) & 
                               (w_pivot['delta_recent'] > 0) & 
                               (w_pivot['delta_prev'] > 0)].copy()
        
        if accelerating.empty:
            return pd.DataFrame()
            
        # Merge shares data - Explicitly select and rename to avoid collisions
        s_subset = s_pivot[['stock_name', 'fund_name']].copy()
        s_subset['curr_shares'] = s_pivot[0]
        s_subset['init_shares'] = s_pivot[lookback_months]
        
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

    def get_institutional_intelligence(self, stock_name: str, lookback_months: int = 3):
        """
        Generates 10 features of institutional intelligence for a specific stock.
        """
        if self.master_df.empty:
            return None
            
        lookback_months = int(lookback_months)
        stock_df = self.master_df[self.master_df['stock_name'].str.lower() == stock_name.lower()].copy()
        if stock_df.empty:
            return None

        # 1. Basic Metrics
        latest_date = stock_df['date'].max()
        curr_month_df = stock_df[stock_df['months_back'] == 0]
        prev_month_df = stock_df[stock_df['months_back'] == 1]
        baseline_df = stock_df[stock_df['months_back'] == lookback_months]
        
        # New Entrants (Strict: were not in the fund at all during lookback window before current month)
        prior_holdings = stock_df[(stock_df['months_back'] > 0) & (stock_df['months_back'] <= lookback_months)]
        prior_funds = prior_holdings[prior_holdings['shares'] > 0]['fund_name'].unique()
        
        curr_funds = curr_month_df[curr_month_df['shares'] > 0]
        new_entrant_list = curr_funds[~curr_funds['fund_name'].isin(prior_funds)]
        new_entrants_count = len(new_entrant_list)
        new_entrant_names = new_entrant_list['fund_name'].tolist()

        # Exits
        baseline_funds = baseline_df[baseline_df['shares'] > 0]['fund_name'].unique()
        curr_funds_all = curr_month_df[curr_month_df['shares'] > 0]['fund_name'].unique()
        exit_list = [f for f in baseline_funds if f not in curr_funds_all]
        exits_count = len(exit_list)

        # Buildup Acceleration check for this specific stock
        accel_df = self.get_buildup_acceleration(min_funds=1, lookback_months=lookback_months)
        is_accelerating = not accel_df[accel_df['stock_name'].str.lower() == stock_name.lower()].empty
        
        # Herd Entry check
        herd_df = self.get_herd_entries(min_funds=1, lookback_months=lookback_months)
        herd_entry_data = herd_df[herd_df['stock_name'].str.lower() == stock_name.lower()]
        is_herd_entry = not herd_entry_data.empty
        herd_count = herd_entry_data['funds_entering'].iloc[0] if is_herd_entry else 0

        # Partial Exits check
        pe_df = self.get_partial_exits(reduction_threshold_pct=30, lookback_months=lookback_months, min_funds=1)
        is_partial_exit = not pe_df[pe_df['stock_name'].str.lower() == stock_name.lower()].empty

        # 2. Sentiment Score Calculation
        sector_info = self.get_sector_peers_activity(stock_name, lookback_months)
        
        # Top Holder Changes
        top_holder_addition = 0
        top_holder_deduction = 0
        weight_pivot, shares_pivot = self.get_stock_detail(stock_name)
        if not weight_pivot.empty and len(weight_pivot) >= 2:
            latest_w = weight_pivot.iloc[0]
            prev_w = weight_pivot.iloc[1]
            top_3_funds = latest_w.sort_values(ascending=False).head(3).index.tolist()
            for f in top_3_funds:
                if f in prev_w.index:
                    if latest_w[f] > prev_w[f] * 1.05: top_holder_addition += 10
                    if latest_w[f] < prev_w[f] * 0.95: top_holder_deduction += 10

        POSITIVE_WEIGHTS = {
            "new_entrants": 10,       # capped at 30 total
            "acceleration": 15,
            "herd_entry": 20,
            "large_herd_bonus": 10,
            "sector_rotation": 15,
            "top_holder_addition_cap": 20,
        }
        NEGATIVE_WEIGHTS = {
            "partial_exit": 15,
            "per_exit": 10,            # reduced from 15
            "exit_cap": 40,            # NEW: symmetric cap, similar magnitude to positive side's max (~75-95)
            "top_holder_deduction_cap": 20,
            "broad_selling": 20,
        }

        positive_total = 0
        positive_total += min(30, new_entrants_count * POSITIVE_WEIGHTS["new_entrants"])
        if is_accelerating:
            positive_total += POSITIVE_WEIGHTS["acceleration"]
        if is_herd_entry:
            positive_total += POSITIVE_WEIGHTS["herd_entry"]
            if herd_count > 5:
                positive_total += POSITIVE_WEIGHTS["large_herd_bonus"]
        if sector_info['is_rotation']:
            positive_total += POSITIVE_WEIGHTS["sector_rotation"]
        positive_total += min(POSITIVE_WEIGHTS["top_holder_addition_cap"], top_holder_addition)

        negative_total = 0
        if is_partial_exit:
            negative_total += NEGATIVE_WEIGHTS["partial_exit"]
        # Cap exits at a comparable magnitude to the positive side's realistic max (~75-90)
        negative_total += min(NEGATIVE_WEIGHTS["exit_cap"], exits_count * NEGATIVE_WEIGHTS["per_exit"])
        negative_total += min(NEGATIVE_WEIGHTS["top_holder_deduction_cap"], top_holder_deduction)

        # THESE TWO LINES ARE MANDATORY
        positive_total = min(70, positive_total)
        negative_total = min(70, negative_total)

        net_shift = positive_total - negative_total
        score = 50 + net_shift
        score = max(0, min(100, score))

        print("\n--- SENTIMENT SCORE DEBUG ---")
        print(f"Stock: {stock_name}")
        print(f"positive_total (capped): {positive_total}, negative_total (capped): {negative_total}, net_shift: {net_shift}, final score: {score}")
        print(f"new_entrants: {new_entrants_count}, exits: {exits_count}, accel: {is_accelerating}, herd: {is_herd_entry} ({herd_count} funds)")
        print(f"rotation: {sector_info['is_rotation']}, partial_exit: {is_partial_exit}")
        print(f"top_holder_add: {top_holder_addition}, top_holder_ded: {top_holder_deduction}")
        print("--- END DEBUG ---\n")

        # 3. Accumulation vs Distribution
        # Compare current shares total vs baseline shares total for funds present in both OR new entrants
        # Actually, let's just sum all net changes
        all_funds = set(curr_month_df['fund_name']) | set(baseline_df['fund_name'])
        added_shares = 0
        removed_shares = 0
        
        s_curr = curr_month_df.set_index('fund_name')['shares'].to_dict()
        s_base = baseline_df.set_index('fund_name')['shares'].to_dict()
        
        for f in all_funds:
            c = s_curr.get(f, 0)
            b = s_base.get(f, 0)
            diff = c - b
            if diff > 0: added_shares += diff
            else: removed_shares += abs(diff)
            
        acc_ratio = 50  # Default to neutral when insufficient history
        if baseline_df.empty:
            acc_ratio = 50  # Cannot determine direction without baseline
        elif (added_shares + removed_shares) > 0:
            acc_ratio = (added_shares / (added_shares + removed_shares)) * 100

        # 4. Smart Money Heatmap (AMC)
        def get_amc(name):
            AMC_PREFIXES = {
                "Aditya Birla": ["Aditya"],
                "Motilal Oswal": ["Motilal"],
                "Baroda BNP": ["Baroda"],
                "Franklin India": ["Franklin"],
                "ICICI Prudential": ["ICICI"],
                "LIC MF": ["LIC"],
                "Invesco India": ["Invesco"],
                "Nippon India": ["Nippon"],
                "Canara Robeco": ["Canara"],
                "Kotak": ["Kotak"],
                "HDFC": ["HDFC"],
                "DSP": ["DSP"],
                "Tata": ["Tata"],
                "SBI": ["SBI"],
                "Axis": ["Axis"],
                "Mirae": ["Mirae"],
                "Quant": ["Quant"],
                "Bandhan": ["Bandhan"],
                "Edelweiss": ["Edelweiss"],
                "WhiteOak": ["WhiteOak"],
                "Sundaram": ["Sundaram"],
                "Union": ["Union"],
                "UTI": ["UTI"],
                "PGIM": ["PGIM"],
                "JM": ["JM"],
                "Navi": ["Navi"],
                "ITI": ["ITI"],
                "Groww": ["Groww"],
                "Samco": ["Samco"],
                "Trust": ["Trust"],
                "NJ": ["NJ"],
            }
            parts = name.split(' ')
            first_word = parts[0]
            for amc_name, prefixes in AMC_PREFIXES.items():
                if first_word in prefixes:
                    return amc_name
            return first_word

        stock_df['amc'] = stock_df['fund_name'].apply(get_amc)
        amc_latest = stock_df[stock_df['months_back'] == 0]
        amc_base = stock_df[stock_df['months_back'] == lookback_months]
        
        amc_stats = []
        for amc in stock_df['amc'].unique():
            c_df = amc_latest[amc_latest['amc'] == amc]
            b_df = amc_base[amc_base['amc'] == amc]
            
            buying = 0
            selling = 0
            
            all_amc_funds = set(c_df['fund_name']) | set(b_df['fund_name'])
            c_map = c_df.set_index('fund_name')['shares'].to_dict()
            b_map = b_df.set_index('fund_name')['shares'].to_dict()
            
            net_shares = 0
            for f in all_amc_funds:
                cv = c_map.get(f, 0)
                bv = b_map.get(f, 0)
                if cv > bv: buying += 1
                elif cv < bv: selling += 1
                net_shares += (cv - bv)
            
            if buying > 0 or selling > 0:
                signal = "Neutral"
                if net_shares > 0 and buying > selling: signal = "Strong Buy" if buying > 2 else "Buy"
                elif net_shares < 0 and selling > buying: signal = "Sell"
                
                amc_stats.append({
                    "AMC": amc,
                    "Buying Funds": buying,
                    "Selling Funds": selling,
                    "Net Flow": "Positive" if net_shares > 0 else "Negative",
                    "Signal": signal,
                    "net_shares": net_shares
                })
        
        amc_stats = sorted(amc_stats, key=lambda x: abs(x['net_shares']), reverse=True)

        # 5. Market Phase Detector
        phase = "Neutral"
        confidence = 50
        
        if is_accelerating and acc_ratio > 70 and new_entrants_count > 0:
            phase = "Markup"
            confidence = acc_ratio
        elif new_entrants_count > 0 and exits_count <= 1 and acc_ratio > 60:
            phase = "Accumulation"
            confidence = acc_ratio
        elif new_entrants_count > 0 and acc_ratio > 50:
            phase = "Early Accumulation"
            confidence = acc_ratio * 0.8
        elif is_partial_exit and exits_count > 2 and acc_ratio < 40:
            phase = "Distribution"
            confidence = 100 - acc_ratio
        elif exits_count > 2 and acc_ratio < 30:
            phase = "Decline"
            confidence = 100 - acc_ratio
        elif acc_ratio > 50 and is_accelerating:
            phase = "Moderate Accumulation"
            confidence = acc_ratio * 0.7

        # 6. Timeline Narrative
        timeline = []
        unique_months = sorted(stock_df['months_back'].unique(), reverse=True)
        for mb in unique_months:
            m_df = stock_df[stock_df['months_back'] == mb]
            m_date = m_df['date'].iloc[0].strftime('%b %Y')
            
            # Events in this month
            events = []
            # Find new entrants in this specific month compared to mb+1
            if mb < max(unique_months):
                prev_m_funds = stock_df[stock_df['months_back'] == mb + 1]['fund_name'].unique()
                curr_m_funds = m_df['fund_name'].unique()
                new_m = [f for f in curr_m_funds if f not in prev_m_funds]
                if new_m:
                    unique_amcs = list(dict.fromkeys([get_amc(f) for f in new_m]))
                    amc_str = ", ".join(unique_amcs[:3])
                    if len(unique_amcs) > 3: amc_str += "..."
                    events.append(f"{len(new_m)} new funds entered ({amc_str})")
                
                ex_m = [f for f in prev_m_funds if f not in curr_m_funds]
                if ex_m:
                    events.append(f"{len(ex_m)} funds exited")
            
            if events:
                timeline.append({"month": m_date, "event": " | ".join(events)})
            else:
                timeline.append({"month": m_date, "event": "No significant activity"})

        # 7. Buyer Categories
        aggressive = []
        quiet = []
        exiting_categories = []
        
        for f in all_funds:
            cv = s_curr.get(f, 0)
            bv = s_base.get(f, 0)
            if bv == 0 and cv > 0:
                aggressive.append(f)  # New entrant = most aggressive by definition
            elif cv > bv * 1.5 and bv > 0:
                aggressive.append(f)
            elif cv > bv * 1.1 and cv <= bv * 1.5:
                quiet.append(f)  # 10-50% increase = quiet accumulator
            elif bv > 0 and cv == 0:
                exiting_categories.append(f)  # Full exit
            elif bv > 0 and cv < bv * 0.5:
                exiting_categories.append(f)  # >50% reduction

        return {
            "stock_name": stock_name,
            "sector": stock_df['sector'].iloc[0],
            "metrics": {
                "new_entrants": new_entrants_count,
                "exits": exits_count,
                "is_accelerating": is_accelerating,
                "is_partial_exit": is_partial_exit,
                "is_herd_entry": is_herd_entry,
                "herd_count": herd_count
            },
            "new_entrant_names": new_entrant_names[:5],
            "exit_names": exit_list[:5],
            "sentiment_score": score,
            "acc_ratio": acc_ratio,
            "amc_stats": amc_stats[:10],
            "phase": phase,
            "confidence": confidence,
            "sector_info": sector_info,
            "timeline": timeline[-5:], # Last 5 events
            "categories": {
                "aggressive": aggressive[:5],
                "quiet": quiet[:5],
                "exiting": exiting_categories[:5]
            }
        }

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
