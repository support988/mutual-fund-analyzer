import pandas as pd
import numpy as np
from mf_parser import parse_mf_csv
import matplotlib.pyplot as plt
import io
import price_fetcher
from collections import Counter

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

    def get_latest_month(self):
        if not self.all_dates:
            return None
        return max(self.all_dates)

    def get_master_holdings(self, asset_type_filter="Equity"):
        latest_month = self.get_latest_month()
        if not latest_month:
            return pd.DataFrame()

        master_list = []
        for fund_name, info in self.funds.items():
            df = info['df']
            if latest_month in df.columns:
                temp = df[df[latest_month] > 0].copy()
                if asset_type_filter:
                    temp = temp[temp['Type'] == asset_type_filter]
                
                temp = temp[['Name', 'Sector', 'Type', latest_month]]
                temp = temp.rename(columns={latest_month: fund_name})
                master_list.append(temp)

        if not master_list:
            return pd.DataFrame()

        from functools import reduce
        master_list_renamed = []
        for i, temp in enumerate(master_list):
            if i == 0:
                master_list_renamed.append(temp)
            else:
                master_list_renamed.append(temp.drop(columns=['Sector', 'Type'], errors='ignore'))
        merged = reduce(
            lambda left, right: pd.merge(left, right, on='Name', how='outer'),
            master_list_renamed
        )
        merged = merged.fillna(0)

        fund_cols = list(self.funds.keys())
        present_fund_cols = [c for c in fund_cols if c in merged.columns]
        
        merged['Funds Count'] = (merged[present_fund_cols] > 0).sum(axis=1)
        merged['Avg Allocation %'] = merged[present_fund_cols].mean(axis=1)
        merged['Total Weight'] = merged[present_fund_cols].sum(axis=1)

        return merged.sort_values(by='Total Weight', ascending=False)

    def get_overlap_matrix(self):
        fund_names = list(self.funds.keys())
        n = len(fund_names)
        
        count_matrix = pd.DataFrame(index=fund_names, columns=fund_names)
        weight_matrix = pd.DataFrame(index=fund_names, columns=fund_names)

        for i in range(n):
            for j in range(n):
                f1 = fund_names[i]
                f2 = fund_names[j]
                
                if i == j:
                    count_matrix.loc[f1, f2] = 100.0
                    weight_matrix.loc[f1, f2] = 100.0
                    continue
                
                df1 = self.funds[f1]['df']
                df2 = self.funds[f2]['df']
                
                latest1 = max(self.funds[f1]['dates'])
                latest2 = max(self.funds[f2]['dates'])
                
                e1 = df1[(df1['Type'] == 'Equity') & (df1[latest1] > 0)][['Name', latest1]].rename(columns={latest1: 'alloc1'})
                e2 = df2[(df2['Type'] == 'Equity') & (df2[latest2] > 0)][['Name', latest2]].rename(columns={latest2: 'alloc2'})
                
                s1 = set(e1['Name'])
                s2 = set(e2['Name'])
                
                common_names = s1.intersection(s2)
                
                if not s1 or not s2:
                    c_overlap = 0.0
                else:
                    c_overlap = round(len(common_names) / min(len(s1), len(s2)) * 100, 1)
                count_matrix.loc[f1, f2] = c_overlap
                
                if not common_names:
                    w_overlap = 0.0
                else:
                    merged = pd.merge(e1, e2, on='Name')
                    merged['min_alloc'] = merged[['alloc1', 'alloc2']].min(axis=1)
                    w_overlap = round(merged['min_alloc'].sum(), 1)
                weight_matrix.loc[f1, f2] = w_overlap

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

        def calc_avg(row):
            vals = [row[f] for f in fund_cols if f in row.index and pd.notna(row[f]) and row[f] > 0]
            return round(sum(vals) / len(vals), 2) if vals else 0.0

        time_series['AVERAGE'] = time_series.apply(calc_avg, axis=1)
        return time_series

    def get_sector_data(self):
        latest_month = self.get_latest_month()
        if not latest_month:
            return pd.DataFrame()
            
        sector_fund_map = {}
        for fund_name, info in self.funds.items():
            df = info['df']
            if latest_month in df.columns:
                equity_df = df[(df['Type'] == 'Equity') & (df[latest_month] > 0)]
                sector_sums = equity_df.groupby('Sector')[latest_month].sum()
                sector_fund_map[fund_name] = sector_sums
        
        sector_df = pd.DataFrame(sector_fund_map).fillna(0)
        sector_df['Average'] = sector_df.mean(axis=1)
        return sector_df

    def get_trends(self, asset_type_filter=None):
        latest_month = self.get_latest_month()
        if not latest_month:
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
        if short.endswith(" Fund"):
            short = short[:-5]
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

    def get_investment_prospects(self, asset_type_filter="Equity"):
        latest_month = self.get_latest_month()
        if not latest_month:
            return []

        master_holdings = self.get_master_holdings(asset_type_filter=asset_type_filter)
        if master_holdings.empty:
            return []
            
        prospect_stocks = master_holdings[master_holdings['Funds Count'] >= 2]
        total_funds = len(self.funds)
        
        all_dates = sorted(list(self.all_dates))
        base_month = all_dates[-3] if len(all_dates) >= 3 else (all_dates[0] if all_dates else None)

        preliminary_prospects = []
        for _, row in prospect_stocks.iterrows():
            stock_name = row['Name']
            sector = row['Sector']
            funds_holding_count = row['Funds Count']
            
            breadth_score = (funds_holding_count / total_funds) * 100
            
            funds_holding_3m_ago = 0
            if base_month:
                for fund_name, info in self.funds.items():
                    df = info['df']
                    if base_month in df.columns:
                        stock_filter = (df['Name'] == stock_name)
                        if asset_type_filter:
                            stock_filter = stock_filter & (df['Type'] == asset_type_filter)
                        if not df[stock_filter & (df[base_month] > 0)].empty:
                            funds_holding_3m_ago += 1
            breadth_acceleration = funds_holding_count - funds_holding_3m_ago

            momentum_changes = []
            increase_count = 0
            new_entrant_count = 0
            fund_details = []
            total_alloc_3m_ago = 0
            
            consecutive_reduction = 0
            if len(all_dates) >= 2:
                for m_idx in range(len(all_dates)-1, 0, -1):
                    curr_m = all_dates[m_idx]
                    prev_m = all_dates[m_idx-1]
                    all_reduced = True
                    reduced_any = False
                    for fund_name, info in self.funds.items():
                        df = info['df']
                        stock_filter = (df['Name'] == stock_name)
                        if asset_type_filter:
                            stock_filter = stock_filter & (df['Type'] == asset_type_filter)
                        stock_row = df[stock_filter]
                        if not stock_row.empty:
                            c_val = stock_row[curr_m].iloc[0] if curr_m in stock_row.columns else 0
                            p_val = stock_row[prev_m].iloc[0] if prev_m in stock_row.columns else 0
                            if c_val > 0 or p_val > 0:
                                reduced_any = True
                                if c_val >= p_val:
                                    all_reduced = False
                                    break
                    if all_reduced and reduced_any:
                        consecutive_reduction += 1
                    else:
                        break

            for fund_name, info in self.funds.items():
                df = info['df']
                dates = info['dates']
                stock_filter = (df['Name'] == stock_name)
                if asset_type_filter:
                    stock_filter = stock_filter & (df['Type'] == asset_type_filter)
                stock_row = df[stock_filter]
                
                if latest_month in stock_row.columns and not stock_row.empty and stock_row[latest_month].iloc[0] > 0:
                    latest_val = float(stock_row[latest_month].iloc[0])
                    base = dates[-3] if len(dates) >= 3 else (dates[0] if len(dates) > 0 else None)
                    prev = dates[-2] if len(dates) >= 2 else None
                    
                    val_prev = float(stock_row[prev].iloc[0]) if prev and prev in stock_row.columns else 0.0
                    val_base = float(stock_row[base].iloc[0]) if base and base in stock_row.columns else 0.0
                    
                    total_alloc_3m_ago += val_base
                    change_3m = latest_val - val_base
                    momentum_changes.append(change_3m)
                    if change_3m > 0: increase_count += 1
                    if prev and prev in stock_row.columns and float(stock_row[prev].iloc[0]) == 0:
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
            
            momentum_score = sum(momentum_changes) / len(momentum_changes) if momentum_changes else 0.0
            conviction_score = (increase_count / funds_holding_count) * 100

            # Base Score (no price data yet)
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
                'composite_score': preliminary_score, # Temporary
                'base_score': base_score,
                'fund_details': fund_details,
                'breadth_acceleration': breadth_acceleration,
                'new_entrant_bonus': new_entrant_bonus,
                'consecutive_reduction': consecutive_reduction,
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
        return prospects
