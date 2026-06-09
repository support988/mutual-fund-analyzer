import pandas as pd
import numpy as np
from mf_parser import parse_mf_csv
import matplotlib.pyplot as plt
import io
import price_fetcher
from collections import Counter
import os

class MFAnalyzer:
    def __init__(self):
        self.funds = {} # fund_name -> {df, dates, file_path}
        self.all_dates = set()

    def add_fund(self, file_path):
        parsed = parse_mf_csv(file_path)
        if parsed:
            fund_name = parsed['fund_name']
            self.funds[fund_name] = {
                'df': parsed['df'],
                'dates': parsed['dates'],
                'file_path': file_path
            }
            self.all_dates.update(parsed['dates'])
            return fund_name
        return None

    def remove_fund(self, fund_name):
        if fund_name in self.funds:
            del self.funds[fund_name]
            # Recalculate all_dates
            self.all_dates = set()
            for f in self.funds.values():
                self.all_dates.update(f['dates'])

    def load_from_directory(self, directory_path, pattern="*.csv"):
        import glob
        files = glob.glob(os.path.join(directory_path, pattern))
        loaded = []
        for f in files:
            name = self.add_fund(f)
            if name:
                loaded.append(name)
        return loaded

    def get_latest_month(self):
        if not self.all_dates:
            return None
        return max(self.all_dates)

    def get_master_holdings(self, asset_type_filter="Equity", analysis_date=None, smart_patching=False):
        """
        Aggregates holdings across all loaded funds efficiently.
        """
        if not self.funds:
            return pd.DataFrame()

        all_holdings = []
        
        for fund_name, info in self.funds.items():
            df = info['df']
            available_dates = info['dates']
            
            target_date = None
            if analysis_date:
                past_dates = [d for d in available_dates if d <= analysis_date]
                if past_dates:
                    target_date = max(past_dates)
                elif smart_patching:
                    target_date = max(available_dates)
            else:
                target_date = max(available_dates)

            if target_date and target_date in df.columns:
                temp = df[df[target_date] > 0].copy()
                if asset_type_filter:
                    temp = temp[temp['Type'] == asset_type_filter]
                
                # Keep Name, Sector, Type and the allocation value
                temp = temp[['Name', 'Sector', 'Type', target_date]].copy()
                temp['fund_name'] = fund_name
                temp = temp.rename(columns={target_date: 'Allocation'})
                all_holdings.append(temp)

        if not all_holdings:
            return pd.DataFrame()

        # Efficiently combine all holdings
        combined = pd.concat(all_holdings, ignore_index=True)
        
        # Pivot to get wide format
        # We use max for Sector/Type in case there are minor discrepancies between funds for the same stock
        pivot = combined.pivot_table(
            index=['Name', 'Sector', 'Type'], 
            columns='fund_name', 
            values='Allocation', 
            aggfunc='first'
        ).reset_index()
        
        # Fill NaNs with 0 for fund columns
        fund_cols = list(self.funds.keys())
        present_fund_cols = [c for c in fund_cols if c in pivot.columns]
        pivot[present_fund_cols] = pivot[present_fund_cols].fillna(0)

        pivot['Funds Count'] = (pivot[present_fund_cols] > 0).sum(axis=1)
        pivot['Avg Allocation %'] = pivot[present_fund_cols].mean(axis=1)
        pivot['Total Weight'] = pivot[present_fund_cols].sum(axis=1)

        return pivot.sort_values(by='Total Weight', ascending=False)

    def get_common_new_entrants(self, months_lookback=3, asset_type_filter="Equity"):
        """
        Identifies stocks that were not in a fund's portfolio N months ago but are present now.
        Returns a summary of these 'New Entrants' across all funds.
        """
        if not self.funds:
            return pd.DataFrame()
            
        new_entrants_list = []
        
        for fund_name, info in self.funds.items():
            df = info['df']
            dates = info['dates']
            if len(dates) < 2:
                continue
                
            latest_date = dates[-1]
            # Find date approx N months ago
            lookback_idx = max(0, len(dates) - 1 - months_lookback)
            lookback_date = dates[lookback_idx]
            
            # A "New Entrant" is >0% now and was 0% (or not present) at lookback_date
            mask = (df[latest_date] > 0) & (df[lookback_date] == 0)
            if asset_type_filter:
                mask = mask & (df['Type'] == asset_type_filter)
                
            new_ones = df[mask].copy()
            for _, row in new_ones.iterrows():
                new_entrants_list.append({
                    'Stock': row['Name'],
                    'Fund': self._get_short_fund_name(fund_name),
                    'Sector': row['Sector'],
                    'Latest %': row[latest_date],
                    'Change %': row[latest_date] - row[lookback_date]
                })
        
        if not new_entrants_list:
            return pd.DataFrame()
            
        new_df = pd.DataFrame(new_entrants_list)
        
        # Aggregate to find common ones
        summary = new_df.groupby('Stock').agg({
            'Fund': list,
            'Sector': 'first',
            'Latest %': ['count', 'mean', 'sum'],
            'Change %': 'mean'
        }).reset_index()
        
        summary.columns = ['Stock', 'Funds List', 'Sector', 'Fund Count', 'Avg %', 'Total %', 'Avg Change']
        
        # Clean up Funds List for display
        summary['Funds List'] = summary['Funds List'].apply(lambda x: ", ".join(x))
        
        return summary.sort_values(by='Fund Count', ascending=False)

    def get_overlap_matrix(self, asset_type_filter="Equity"):
        """
        Calculates overlap matrices efficiently by pre-extracting latest holdings.
        """
        fund_names = list(self.funds.keys())
        if not fund_names:
            return {'count': pd.DataFrame(), 'weight': pd.DataFrame()}

        # Pre-extract latest holdings for all funds
        latest_holdings = {}
        for name in fund_names:
            info = self.funds[name]
            df = info['df']
            latest_date = max(info['dates'])
            holdings = df[(df['Type'] == asset_type_filter) & (df[latest_date] > 0)][['Name', latest_date]].copy()
            holdings.columns = ['Name', 'Allocation']
            latest_holdings[name] = holdings

        n = len(fund_names)
        count_matrix = pd.DataFrame(100.0, index=fund_names, columns=fund_names)
        weight_matrix = pd.DataFrame(100.0, index=fund_names, columns=fund_names)

        for i in range(n):
            f1 = fund_names[i]
            h1 = latest_holdings[f1]
            
            for j in range(i + 1, n):
                f2 = fund_names[j]
                h2 = latest_holdings[f2]
                
                if h1.empty or h2.empty:
                    count_matrix.loc[f1, f2] = count_matrix.loc[f2, f1] = 0.0
                    weight_matrix.loc[f1, f2] = weight_matrix.loc[f2, f1] = 0.0
                    continue

                merged = pd.merge(h1, h2, on='Name', suffixes=('_1', '_2'))
                
                # Count Overlap
                overlap_count = len(merged)
                c_overlap = round(overlap_count / min(len(h1), len(h2)) * 100, 1)
                count_matrix.loc[f1, f2] = count_matrix.loc[f2, f1] = c_overlap
                
                # Weight Overlap
                w_overlap = round(merged[['Allocation_1', 'Allocation_2']].min(axis=1).sum(), 1)
                weight_matrix.loc[f1, f2] = weight_matrix.loc[f2, f1] = w_overlap

        return {'count': count_matrix, 'weight': weight_matrix}

    def get_common_holdings(self, fund1_name, fund2_name):
        if fund1_name not in self.funds or fund2_name not in self.funds:
            return pd.DataFrame()

        df1 = self.funds[fund1_name]['df']
        df2 = self.funds[fund2_name]['df']
        
        latest1 = max(self.funds[fund1_name]['dates'])
        latest2 = max(self.funds[fund2_name]['dates'])
        
        h1 = df1[df1[latest1] > 0][['Name', 'Sector', latest1]].rename(columns={latest1: 'Fund 1 %'})
        h2 = df2[df2[latest2] > 0][['Name', 'Sector', latest2]].rename(columns={latest2: 'Fund 2 %'})
        
        merged = pd.merge(h1, h2, on=['Name', 'Sector'], how='inner')
        merged['Delta'] = merged['Fund 1 %'] - merged['Fund 2 %']
        
        return merged

    def get_stock_time_series(self, stock_name):
        dates = sorted(list(self.all_dates))
        time_series = pd.DataFrame({'Date': dates})
        fund_cols = []

        for fund_name, info in self.funds.items():
            df = info['df']
            stock_data = df[df['Name'].str.lower() == stock_name.lower()]
            if not stock_data.empty:
                available_dates = [d for d in dates if d in df.columns]
                vals = stock_data[available_dates].iloc[0]
                temp_df = pd.DataFrame({'Date': available_dates, fund_name: vals.values})
                time_series = pd.merge(time_series, temp_df, on='Date', how='left')
                fund_cols.append(fund_name)

        if not fund_cols:
            return time_series

        time_series['AVERAGE'] = time_series[fund_cols].replace(0, float('nan')).mean(axis=1).fillna(0).round(2)
        return time_series

    def get_best_common_date(self):
        """
        Finds the latest date where the majority of funds have data.
        """
        if not self.all_dates:
            return None
        
        date_counts = Counter()
        for info in self.funds.values():
            date_counts.update(info['dates'])
        
        if not date_counts:
            return None
            
        # Sort dates descending
        sorted_dates = sorted(date_counts.keys(), reverse=True)
        total_funds = len(self.funds)
        
        # Prefer the latest date that has most funds
        best_date = sorted_dates[0]
        max_count = date_counts[best_date]
        
        for d in sorted_dates:
            if date_counts[d] >= max_count:
                max_count = date_counts[d]
                best_date = d
            if date_counts[d] == total_funds:
                return d
                
        return best_date

    def get_sector_data(self, analysis_date=None, smart_patching=False):
        if not self.funds:
            return pd.DataFrame()
            
        sector_fund_map = {}
        for fund_name, info in self.funds.items():
            df = info['df']
            available_dates = info['dates']
            
            target_date = None
            if analysis_date:
                past_dates = [d for d in available_dates if d <= analysis_date]
                if past_dates:
                    target_date = max(past_dates)
                elif smart_patching:
                    target_date = max(available_dates)
            else:
                target_date = max(available_dates)

            if target_date and target_date in df.columns:
                equity_df = df[(df['Type'] == 'Equity') & (df[target_date] > 0)]
                sector_sums = equity_df.groupby('Sector')[target_date].sum()
                sector_fund_map[fund_name] = sector_sums
        
        if not sector_fund_map:
            return pd.DataFrame()

        sector_df = pd.DataFrame(sector_fund_map).fillna(0)
        sector_df['Average'] = sector_df.mean(axis=1)
        return sector_df

    def get_trends(self, asset_type_filter=None):
        if not self.funds:
            return {}

        results = {}
        for fund_name, info in self.funds.items():
            df = info['df']
            dates = info['dates']
            if len(dates) < 2:
                continue

            latest = dates[-1]
            prev = dates[-2]
            base = dates[-3] if len(dates) >= 3 else dates[-2]

            df_trend = df.copy()
            if asset_type_filter:
                df_trend = df_trend[df_trend['Type'] == asset_type_filter].copy()
            df_trend[latest] = pd.to_numeric(df_trend[latest], errors='coerce').fillna(0)
            df_trend[prev] = pd.to_numeric(df_trend[prev], errors='coerce').fillna(0)
            df_trend[base] = pd.to_numeric(df_trend[base], errors='coerce').fillna(0)
            df_trend['Change'] = df_trend[latest] - df_trend[base]

            top_inc = df_trend[df_trend['Change'] > 0].sort_values('Change', ascending=False).head(5)
            top_dec = df_trend[df_trend['Change'] < 0].sort_values('Change', ascending=True).head(5)
            new_entries = df_trend[(df_trend[latest] > 0) & (df_trend[prev] == 0)]
            exited = df_trend[(df_trend[latest] == 0) & (df_trend[prev] > 0)]

            results[fund_name] = {
                'top_increase': top_inc[['Name', 'Change', latest]],
                'top_decrease': top_dec[['Name', 'Change', latest]],
                'new_entries': new_entries[['Name', 'Sector', latest]],
                'exited': exited[['Name', 'Sector', prev]]
            }
        return results

    def _get_short_fund_name(self, name):
        patterns = [" - Direct (G)", " - Direct (IDCW)", " - Regular (G)", " Fund"]
        short = name
        for p in patterns:
            short = short.replace(p, "")
        return short.strip()

    def _aggregate_active_buy_signal(self, fund_details, price_change_3m):
        if not fund_details:
            return None

        fund_signals = []
        for fd in fund_details:
            signal = price_fetcher.calculate_active_buy_signal(
                fd['change_3m'],
                price_change_3m,
                fd['alloc_3m_ago']
            ).copy()
            signal['fund'] = fd['fund']
            signal['latest_alloc'] = fd['latest_alloc']
            signal['alloc_3m_ago'] = fd['alloc_3m_ago']
            signal['change_3m'] = fd['change_3m']
            fund_signals.append(signal)

        signal_counts = Counter(s['signal'] for s in fund_signals)
        total = len(fund_signals)
        top_signal, top_count = signal_counts.most_common(1)[0]
        distribution = ", ".join(f"{signal}: {count}" for signal, count in signal_counts.most_common())

        if top_count > total / 2:
            representative = next(s for s in fund_signals if s['signal'] == top_signal)
            return {
                'signal': top_signal,
                'score_bonus': representative['score_bonus'],
                'explanation': f"Fund-level majority: {top_signal} in {top_count}/{total} funds ({distribution})",
                'fund_signals': fund_signals
            }

        positive_count = sum(signal_counts.get(s, 0) for s in ['strong_buy', 'active_buy'])
        negative_count = sum(signal_counts.get(s, 0) for s in ['partial_sell', 'reducing'])
        neutral_count = sum(signal_counts.get(s, 0) for s in ['passive_drift', 'none'])

        if positive_count > total / 2:
            return {
                'signal': 'active_buy',
                'score_bonus': 15,
                'explanation': f"Positive fund-level majority in {positive_count}/{total} funds ({distribution})",
                'fund_signals': fund_signals
            }
        if negative_count > total / 2:
            return {
                'signal': 'reducing',
                'score_bonus': -15,
                'explanation': f"Negative fund-level majority in {negative_count}/{total} funds ({distribution})",
                'fund_signals': fund_signals
            }
        if neutral_count > total / 2:
            return {
                'signal': 'passive_drift',
                'score_bonus': 0,
                'explanation': f"Neutral fund-level majority in {neutral_count}/{total} funds ({distribution})",
                'fund_signals': fund_signals
            }

        return {
            'signal': 'mixed',
            'score_bonus': 0,
            'explanation': f"No fund-level majority ({distribution})",
            'fund_signals': fund_signals
        }

    def get_investment_prospects(self, asset_type_filter="Equity", analysis_date=None, smart_patching=False):
        if not self.funds:
            return []

        master_holdings = self.get_master_holdings(
            asset_type_filter=asset_type_filter, 
            analysis_date=analysis_date, 
            smart_patching=smart_patching
        )
        if master_holdings.empty:
            return []
            
        prospect_stocks = master_holdings[master_holdings['Funds Count'] >= 2]
        total_funds = len(self.funds)
        
        preliminary_prospects = []
        for _, row in prospect_stocks.iterrows():
            stock_name = row['Name']
            sector = row['Sector']
            funds_holding_count = row['Funds Count']
            
            breadth_score = (funds_holding_count / total_funds) * 100
            
            momentum_changes = []
            increase_count = 0
            new_entrant_count = 0
            fund_details = []
            total_alloc_3m_ago = 0
            funds_holding_3m_ago = 0
            
            consecutive_reduction = 0
            
            for fund_name, info in self.funds.items():
                df = info['df']
                dates = info['dates']
                stock_filter = (df['Name'] == stock_name)
                if asset_type_filter:
                    stock_filter = stock_filter & (df['Type'] == asset_type_filter)
                stock_row = df[stock_filter]
                
                # Determine individual target date
                target_date = None
                if analysis_date:
                    past_dates = [d for d in dates if d <= analysis_date]
                    if past_dates: target_date = max(past_dates)
                    elif smart_patching: target_date = max(dates)
                else:
                    target_date = max(dates)
                
                if target_date and target_date in stock_row.columns and not stock_row.empty and stock_row[target_date].iloc[0] > 0:
                    latest_val = float(stock_row[target_date].iloc[0])
                    
                    # Find 1m and 3m ago relative to target_date
                    try:
                        idx = dates.index(target_date)
                    except ValueError:
                        continue
                    prev = dates[idx-1] if idx >= 1 else None
                    # For momentum, let's use 3 periods if possible
                    base_3m = dates[idx-3] if idx >= 3 else (dates[0] if idx > 0 else None)

                    val_prev = float(stock_row[prev].iloc[0]) if prev and prev in stock_row.columns else 0.0
                    val_base = float(stock_row[base_3m].iloc[0]) if base_3m and base_3m in stock_row.columns else 0.0
                    
                    if val_base > 0:
                        funds_holding_3m_ago += 1
                        
                    total_alloc_3m_ago += val_base
                    change_3m = latest_val - val_base
                    momentum_changes.append(change_3m)
                    if change_3m > 0: increase_count += 1
                    if val_prev == 0:
                        new_entrant_count += 1
                        
                    monthly_series = {}
                    for d in dates:
                        if d in stock_row.columns:
                            monthly_series[d.strftime('%Y-%m-%d')] = float(stock_row[d].iloc[0])

                    fund_details.append({
                        'fund': self._get_short_fund_name(fund_name),
                        'latest_alloc': latest_val,
                        'alloc_1m_ago': val_prev,
                        'alloc_3m_ago': val_base,
                        'change_1m': latest_val - val_prev,
                        'change_3m': change_3m,
                        'monthly_series': monthly_series
                    })
            
            breadth_acceleration = funds_holding_count - funds_holding_3m_ago
            momentum_score = sum(momentum_changes) / len(momentum_changes) if momentum_changes else 0.0
            conviction_score = (increase_count / funds_holding_count) * 100

            # Base Score
            base_score = (breadth_score * 0.25) + \
                         (momentum_score * 10 * 0.30) + \
                         (conviction_score * 0.20) + \
                         (min(breadth_acceleration * 5, 15))
            
            new_entrant_bonus = 10 if new_entrant_count >= 2 else 0
            preliminary_score = base_score + new_entrant_bonus

            preliminary_prospects.append({
                'stock': stock_name,
                'sector': sector,
                'funds_holding': funds_holding_count,
                'total_funds': total_funds,
                'breadth_score': breadth_score,
                'momentum_score': momentum_score,
                'conviction_score': conviction_score,
                'new_entrants': new_entrant_count,
                'composite_score': preliminary_score,
                'base_score': base_score,
                'fund_details': fund_details,
                'breadth_acceleration': breadth_acceleration,
                'new_entrant_bonus': new_entrant_bonus,
                'consecutive_reduction': consecutive_reduction, # Would need same relative logic if kept
                'total_alloc_3m_ago': total_alloc_3m_ago
            })
            
        # Sort and take top 20 for enrichment (reduces API calls)
        preliminary_prospects.sort(key=lambda x: x['composite_score'], reverse=True)
        top_candidates = preliminary_prospects[:20]
        
        final_prospects = []
        for p in top_candidates:
            stock_name = p['stock']
            price_data = None
            active_buy_signal = None
            price_data_available = False
            
            try:
                # Optimized: Only fetch for top candidates
                price_data = price_fetcher.get_price_data(stock_name)
                if price_data:
                    active_buy_signal = self._aggregate_active_buy_signal(
                        p['fund_details'],
                        price_data['price_change_3m']
                    )
                    price_data_available = True
            except Exception as e:
                print(f"Price fetch error for {stock_name}: {e}")

            active_buy_bonus = active_buy_signal['score_bonus'] if active_buy_signal else 0
            p['active_buy_signal'] = active_buy_signal
            p['price_data'] = price_data
            p['price_data_available'] = price_data_available
            p['composite_score'] = min(100, max(0, p['composite_score'] + active_buy_bonus))
            p['bulk_deals'] = None
            p['sector_rotation_flag'] = False
            p['sector_momentum_count'] = 0
            final_prospects.append(p)
            
        final_prospects.sort(key=lambda x: x['composite_score'], reverse=True)
        top_prospects = final_prospects[:10]
        
        sector_counts = Counter([p['sector'] for p in top_prospects])
        for p in top_prospects:
            p['sector_momentum_count'] = sector_counts[p['sector']]
            if sector_counts[p['sector']] >= 3:
                p['sector_rotation_flag'] = True
                
        return top_prospects

    def get_conviction_entrants(self, asset_type_filter="Equity", min_allocation=1.0):
        """
        Analyzes new entrants with high conviction (large initial allocation).
        """
        res = self.get_common_new_entrants(asset_type_filter=asset_type_filter)
        if res.empty:
            return pd.DataFrame()
        
        filtered = res[res['Avg %'] >= min_allocation].copy()
        if filtered.empty:
            return pd.DataFrame()

        def get_conviction(avg):
            if avg >= 2.0: return 'High'
            if avg >= 1.0: return 'Medium'
            return 'Low'
        
        filtered['Conviction'] = filtered['Avg %'].apply(get_conviction)

        def get_inference(row):
            count = row['Fund Count']
            conv = row['Conviction']
            if count >= 4 and conv == 'High':
                return "Strong institutional consensus. Multiple funds entering with large allocation — high confidence new bet."
            if count >= 4 and conv == 'Medium':
                return "Broad interest but moderate sizing. Worth watching for further buildup."
            if count >= 2 and conv == 'High':
                return "Few funds but high conviction sizing. Early mover signal — monitor for more funds joining."
            if count >= 2 and conv == 'Medium':
                return "Early stage entry with moderate allocation. Insufficient evidence yet — watch next month."
            return "Low conviction entry. Likely exploratory position or rebalancing noise."

        filtered['Inference'] = filtered.apply(get_inference, axis=1)
        return filtered.sort_values(by='Avg %', ascending=False)

    def get_buildup_acceleration(self, asset_type_filter="Equity", min_funds=2):
        """
        Identifies stocks where funds are accelerating their buildup (buying more this month than last).
        """
        if not self.funds:
            return pd.DataFrame()
            
        acceleration_list = []
        for fund_name, info in self.funds.items():
            dates = info['dates']
            df = info['df']
            if len(dates) < 4:
                continue
                
            idx = len(dates) - 1
            # Current, Prev, 2m ago, 3m ago
            d_cols = [dates[idx], dates[idx-1], dates[idx-2], dates[idx-3]]
            
            if not all(d in df.columns for d in d_cols):
                continue
                
            mask = (df[dates[idx]] > 0) & (df['Type'] == asset_type_filter)
            valid_df = df[mask]
            
            for _, row in valid_df.iterrows():
                # [idx, idx-1, idx-2, idx-3]
                latest = float(row[dates[idx]])
                m1 = float(row[dates[idx-1]])
                m2 = float(row[dates[idx-2]])
                m3 = float(row[dates[idx-3]])
                
                early_change = m2 - m3
                recent_change = latest - m2
                acceleration = recent_change - early_change
                
                if acceleration > 0 and recent_change > 0:
                    acceleration_list.append({
                        'Stock': row['Name'],
                        'Fund': self._get_short_fund_name(fund_name),
                        'Sector': row['Sector'],
                        'latest_alloc': latest,
                        'early_change': early_change,
                        'recent_change': recent_change,
                        'acceleration': acceleration
                    })
                    
        if not acceleration_list:
            return pd.DataFrame()
            
        acc_df = pd.DataFrame(acceleration_list)
        summary = acc_df.groupby('Stock').agg({
            'Sector': 'first',
            'Fund': list,
            'acceleration': 'mean',
            'latest_alloc': 'mean'
        }).reset_index()
        
        summary['Fund Count'] = summary['Fund'].apply(len)
        summary = summary[summary['Fund Count'] >= min_funds].copy()
        
        if summary.empty:
            return pd.DataFrame()
            
        summary = summary.rename(columns={
            'acceleration': 'Avg Acceleration',
            'latest_alloc': 'Avg Latest Alloc',
            'Fund': 'Funds List'
        })
        
        summary['Funds List'] = summary['Funds List'].apply(lambda x: ", ".join(x))
        
        def get_inf(row):
            count = row['Fund Count']
            accel = row['Avg Acceleration']
            if count >= 4 and accel >= 0.5:
                return "Aggressive buildup across many funds. Funds are urgently increasing bets — strong buy signal."
            if count >= 4 and accel < 0.5:
                return "Broad but gradual buildup. Consistent accumulation without urgency — positive but not rushed."
            if count >= 2 and accel >= 0.5:
                return "Fast acceleration in select funds. Early aggressive movers — watch if others follow."
            if count >= 2 and accel < 0.5:
                return "Slow steady buildup in few funds. Accumulation in early stages — monitor trend."
            return "Isolated buildup. Not yet a cross-fund theme."
            
        summary['Inference'] = summary.apply(get_inf, axis=1)
        cols = ['Stock', 'Sector', 'Fund Count', 'Avg Acceleration', 'Avg Latest Alloc', 'Funds List', 'Inference']
        return summary[cols].sort_values(by='Avg Acceleration', ascending=False)

    def get_partial_exits(self, asset_type_filter="Equity", exit_threshold=0.5, months_lookback=3):
        """
        Detects stocks where multiple funds are meaningful reducing their exposure.
        """
        if not self.funds:
            return pd.DataFrame()
            
        exits_list = []
        for fund_name, info in self.funds.items():
            dates = info['dates']
            df = info['df']
            if len(dates) < 2:
                continue
                
            latest_date = dates[-1]
            lookback_idx = max(0, len(dates) - 1 - months_lookback)
            lookback_date = dates[lookback_idx]
            
            if latest_date not in df.columns or lookback_date not in df.columns:
                continue
                
            mask = df['Type'] == asset_type_filter
            valid_df = df[mask]
            
            for _, row in valid_df.iterrows():
                old_val = float(row[lookback_date])
                new_val = float(row[latest_date])
                
                if old_val > 0 and new_val > 0 and new_val < old_val:
                    reduction_pct = ((old_val - new_val) / old_val) * 100
                    if reduction_pct >= exit_threshold * 100:
                        exits_list.append({
                            'Stock': row['Name'],
                            'Fund': self._get_short_fund_name(fund_name),
                            'Sector': row['Sector'],
                            'Old Alloc': old_val,
                            'New Alloc': new_val,
                            'Reduction %': reduction_pct
                        })
                        
        if not exits_list:
            return pd.DataFrame()
            
        exit_df = pd.DataFrame(exits_list)
        summary = exit_df.groupby('Stock').agg({
            'Fund': list,
            'Reduction %': 'mean',
            'New Alloc': 'mean',
            'Sector': 'first'
        }).reset_index()
        
        summary['Fund Count'] = summary['Fund'].apply(len)
        summary = summary.rename(columns={
            'Reduction %': 'Avg Reduction %',
            'New Alloc': 'Avg New Alloc',
            'Fund': 'Funds List'
        })
        
        def get_strength(avg):
            if avg >= 50: return 'Strong'
            if avg >= 25: return 'Moderate'
            return 'Mild'
            
        summary['Exit Strength'] = summary['Avg Reduction %'].apply(get_strength)
        
        def get_inf(row):
            count = row['Fund Count']
            strength = row['Exit Strength']
            if count >= 4 and strength == 'Strong':
                return "Mass distribution detected. Most funds cutting position by half or more — strong exit signal. Avoid or reduce exposure."
            if count >= 4 and strength == 'Moderate':
                return "Broad trimming across funds. Not a full exit but meaningful reduction in conviction — caution advised."
            if count >= 2 and strength == 'Strong':
                return "Sharp reduction in select funds. Early distribution signal — watch if others follow before acting."
            if count >= 2 and strength == 'Moderate':
                return "Moderate trimming in few funds. Could be profit booking or rebalancing — not alarming yet."
            return "Mild reduction. Likely routine rebalancing rather than a conviction change."
            
        summary['Inference'] = summary.apply(get_inf, axis=1)
        summary['Funds List'] = summary['Funds List'].apply(lambda x: ", ".join(x))
        cols = ['Stock', 'Sector', 'Fund Count', 'Avg Reduction %', 'Avg New Alloc', 'Exit Strength', 'Funds List', 'Inference']
        return summary[cols].sort_values(by=['Fund Count', 'Avg Reduction %'], ascending=[False, False])

    def get_herd_entries(self, asset_type_filter="Equity", min_funds=4, months_lookback=1):
        """
        Identifies stocks where many funds have newly entered within a short period.
        """
        if not self.funds:
            return pd.DataFrame()
            
        entries_list = []
        for fund_name, info in self.funds.items():
            dates = info['dates']
            df = info['df']
            if len(dates) < 2:
                continue
                
            latest_date = dates[-1]
            lookback_idx = max(0, len(dates) - 1 - months_lookback)
            lookback_date = dates[lookback_idx]
            
            if latest_date not in df.columns or lookback_date not in df.columns:
                continue
                
            mask = (df[latest_date] > 0) & (df[lookback_date] == 0) & (df['Type'] == asset_type_filter)
            new_entries = df[mask]
            
            for _, row in new_entries.iterrows():
                entries_list.append({
                    'Stock': row['Name'],
                    'Fund': self._get_short_fund_name(fund_name),
                    'Sector': row['Sector'],
                    'Latest Alloc': float(row[latest_date])
                })
                
        if not entries_list:
            return pd.DataFrame()
            
        herd_df = pd.DataFrame(entries_list)
        summary = herd_df.groupby('Stock').agg({
            'Fund': list,
            'Latest Alloc': 'mean',
            'Sector': 'first'
        }).reset_index()
        
        summary['Fund Count'] = summary['Fund'].apply(len)
        summary = summary[summary['Fund Count'] >= min_funds].copy()
        
        if summary.empty:
            return pd.DataFrame()
            
        summary = summary.rename(columns={
            'Latest Alloc': 'Avg Alloc',
            'Fund': 'Funds List'
        })
        
        def get_risk(count):
            if count >= 6: return 'High'
            if count >= 4: return 'Medium'
            return 'Low'
            
        summary['Crowding Risk'] = summary['Fund Count'].apply(get_risk)
        
        def get_inf(row):
            count = row['Fund Count']
            risk = row['Crowding Risk']
            if count >= 6 and risk == 'High':
                return "Extreme herding detected. Too many funds entering simultaneously — crowding risk is real. Strong momentum but fragile if sentiment shifts."
            if count >= 5 and risk == 'High':
                return "Heavy herding. High short-term momentum but watch for crowding unwind if any fund starts exiting."
            if count == 4 and risk == 'Medium':
                return "Moderate herding. Broad interest forming — good early signal if conviction sizes are also high."
            return "Threshold herd entry. Monitor whether this broadens or stalls next month."
            
        summary['Inference'] = summary.apply(get_inf, axis=1)
        summary['Funds List'] = summary['Funds List'].apply(lambda x: ", ".join(x))
        cols = ['Stock', 'Sector', 'Fund Count', 'Avg Alloc', 'Crowding Risk', 'Funds List', 'Inference']
        return summary[cols].sort_values(by='Fund Count', ascending=False)

    def get_prospects_export_data(self, asset_type_filter="Equity"):
        prospects = self.get_investment_prospects(asset_type_filter=asset_type_filter)
        all_dates = sorted(list(self.all_dates))
        
        for p in prospects:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
            fund_names = []
            for fd in p['fund_details']:
                dates_sorted = sorted(fd['monthly_series'].keys())
                vals = [fd['monthly_series'][d] for d in dates_sorted]
                date_objs = [pd.to_datetime(d) for d in dates_sorted]
                ax1.plot(date_objs, vals, label=fd['fund'], alpha=0.5, linewidth=1.2)
                fund_names.append(fd['fund'])
            
            ts = self.get_stock_time_series(p['stock'])
            ax1.plot(ts['Date'], ts['AVERAGE'], label='AVERAGE', linewidth=2.5, color='black', marker='o', markersize=4)
            ax1.set_title(p['stock'])
            ax1.set_ylabel("Allocation %")
            ax1.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize='small')
            ax1.grid(True)
            
            short_funds = [fd['fund'] for fd in p['fund_details']]
            latest_allocs = [fd['latest_alloc'] for fd in p['fund_details']]
            colors = []
            for fd in p['fund_details']:
                if fd['change_3m'] > 0: colors.append('green')
                elif fd['change_3m'] < 0: colors.append('red')
                else: colors.append('grey')
            
            bars = ax2.bar(short_funds, latest_allocs, color=colors)
            ax2.set_ylabel("Allocation %")
            latest_month_label = all_dates[-1].strftime('%b-%y') if all_dates else ""
            ax2.set_title(f"Latest Snapshot - {latest_month_label}")
            plt.setp(ax2.get_xticklabels(), rotation=30, horizontalalignment='right')
            
            for bar in bars:
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height, f'{height:.1f}%', ha='center', va='bottom')
            fig.tight_layout()
            p['figure'] = fig
            plt.close(fig)
        return prospects
