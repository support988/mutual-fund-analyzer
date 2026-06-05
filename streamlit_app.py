import streamlit as st
import pandas as pd
import os
import json
import io
import matplotlib.pyplot as plt
from datetime import datetime

from analyzer import MFAnalyzer
from exporter import export_to_excel
import price_fetcher
import bulk_deals_parser
from path_utils import get_app_data_path

# Set page config
st.set_page_config(page_title="MF Portfolio Tracker", layout="wide")

# Initialize Session State
if 'analyzer' not in st.session_state:
    st.session_state.analyzer = MFAnalyzer()
    # Load default files from config.json
    config_path = get_app_data_path("config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                paths = json.load(f)
                for p in paths:
                    if os.path.exists(p):
                        st.session_state.analyzer.add_fund(p)
        except:
            pass

if 'bulk_df' not in st.session_state:
    st.session_state.bulk_df = None

if 'watchlist' not in st.session_state:
    watchlist_path = os.path.join(os.getcwd(), "watchlist.json")
    if os.path.exists(watchlist_path):
        with open(watchlist_path, 'r') as f:
            st.session_state.watchlist = json.load(f)
    else:
        st.session_state.watchlist = []

if 'prospects' not in st.session_state:
    st.session_state.prospects = []

# Sidebar
st.sidebar.title("Controls")
uploaded_files = st.sidebar.file_uploader("Upload MF CSVs", type="csv", accept_multiple_files=True)
if uploaded_files:
    for uploaded_file in uploaded_files:
        temp_path = os.path.join(os.getcwd(), f"temp_{uploaded_file.name}")
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.session_state.analyzer.add_fund(temp_path)
        os.remove(temp_path)
    st.sidebar.success("Files processed!")

if st.sidebar.button("Clear All Funds"):
    st.session_state.analyzer = MFAnalyzer()
    st.rerun()

# Export Logic
if st.session_state.analyzer.funds:
    if st.sidebar.button("Prepare Excel Export"):
        with st.sidebar:
            with st.spinner("Generating Excel report..."):
                temp_export = "temp_export.xlsx"
                try:
                    if export_to_excel(st.session_state.analyzer, temp_export):
                        with open(temp_export, "rb") as f:
                            st.download_button(
                                label="📥 Click to Download Export",
                                data=f,
                                file_name="MF_Analysis_Export.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        os.remove(temp_export)
                except Exception as e:
                    st.error(f"Export failed: {e}")

# Main UI
st.title("Mutual Fund Portfolio Overlap & Concentration Tracker")

if not st.session_state.analyzer.funds:
    st.info("Please upload Mutual Fund CSV files via the sidebar to begin.")
else:
    tabs = st.tabs([
        "File Management", "Portfolio Overview", "Overlap Analysis", 
        "Concentration Tracker", "Sector Breakdown", "Trend Analysis", 
        "Investment Prospects", "Watchlist"
    ])

    # 1. File Management
    with tabs[0]:
        st.header("Loaded Funds")
        fund_list = list(st.session_state.analyzer.funds.keys())
        if fund_list:
            for fund in fund_list:
                col1, col2 = st.columns([4, 1])
                col1.write(f"**{fund}**")
                if col2.button(f"Remove", key=f"remove_{fund}"):
                    st.session_state.analyzer.remove_fund(fund)
                    st.rerun()
        else:
            st.write("No funds loaded.")

    # 2. Portfolio Overview
    with tabs[1]:
        st.header("Master Holdings")
        col1, col2 = st.columns(2)
        asset_filter = col1.selectbox("Asset Type", ["All", "Equity", "Debt", "Others"], index=1)
        min_funds_filter = col2.number_input("Min Funds Holding", 1, 20, 1)
        
        filter_val = asset_filter if asset_filter != "All" else None
        master = st.session_state.analyzer.get_master_holdings(asset_type_filter=filter_val)
        
        if not master.empty:
            # Apply Min Funds Filter
            master = master[master['Funds Count'] >= min_funds_filter]
            
            search = st.text_input("Search Stocks", placeholder="Filter by name...")
            if search:
                master = master[master['Name'].str.contains(search, case=False)]
            st.dataframe(master, use_container_width=True, hide_index=True)
        else:
            st.write("No data available.")

    # 3. Overlap Analysis
    with tabs[2]:
        st.header("Overlap Analysis")
        matrices = st.session_state.analyzer.get_overlap_matrix()
        st.subheader("Overlap Count (%)")
        st.dataframe(matrices['count'].style.background_gradient(cmap='RdYlGn', axis=None).format("{:.1f}%"), use_container_width=True)
        st.subheader("Overlap Weight (%)")
        st.dataframe(matrices['weight'].style.background_gradient(cmap='RdYlGn', axis=None).format("{:.1f}%"), use_container_width=True)

    # 4. Concentration Tracker
    with tabs[3]:
        st.header("Concentration Tracker")
        col1, col2 = st.columns(2)
        asset_filter_c = col1.selectbox("Asset Type", ["All", "Equity", "Debt", "Others"], index=1, key="conc_asset_filter")
        
        filter_val_c = asset_filter_c if asset_filter_c != "All" else None
        master_all = st.session_state.analyzer.get_master_holdings(asset_type_filter=filter_val_c)
        
        if not master_all.empty:
            all_stocks = sorted(master_all['Name'].tolist())
            selected_stock = col2.selectbox("Select Stock to Track", all_stocks)
            
            if selected_stock:
                ts_df = st.session_state.analyzer.get_stock_time_series(selected_stock)
                st.subheader(f"Allocation History: {selected_stock}")
                
                # Plot
                fig, ax = plt.subplots(figsize=(10, 5))
                # The ts_df has 'Date' as a column or index depending on implementation
                # Based on analyzer.py, it returns a DataFrame with 'Date' as a column
                x_axis = ts_df['Date']
                
                for fund in ts_df.columns:
                    if fund in ['Date', 'AVERAGE']:
                        continue
                    # Plot only if there is at least one non-zero value
                    if ts_df[fund].sum() > 0:
                        # Use mask to handle zeros or NaNs if preferred, 
                        # but here we follow the original logic of plotting all points
                        ax.plot(x_axis, ts_df[fund], marker='o', linewidth=2, label=fund)
                
                # Plot Average with distinct style
                if 'AVERAGE' in ts_df.columns:
                    ax.plot(x_axis, ts_df['AVERAGE'], color='black', linewidth=3, linestyle='--', label='Average', marker='s')

                ax.set_title(f"Concentration Trend: {selected_stock}", fontsize=14)
                ax.set_ylabel("Weight (%)", fontsize=12)
                ax.set_xlabel("Date", fontsize=12)
                ax.grid(True, linestyle='--', alpha=0.7)
                ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
                plt.xticks(rotation=45)
                st.pyplot(fig)
                
                st.dataframe(ts_df, use_container_width=True, hide_index=True)
        else:
            st.write("No stocks found for the selected asset type.")

    # 5. Sector Breakdown
    with tabs[4]:
        st.header("Sector Breakdown")
        sector_df = st.session_state.analyzer.get_sector_data()
        if not sector_df.empty:
            fig, ax = plt.subplots(figsize=(12, 7))
            sector_df.plot(kind='bar', ax=ax, width=0.8)
            ax.set_title("Sector Allocation across Funds", fontsize=16)
            ax.set_ylabel("Weight (%)", fontsize=12)
            ax.set_xlabel("Sector", fontsize=12)
            ax.grid(axis='y', linestyle='--', alpha=0.7)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            st.pyplot(fig)
            
            st.dataframe(sector_df.style.format("{:.2f}%"), use_container_width=True)

    # 6. Trend Analysis
    with tabs[5]:
        st.header("New Entries & Exits")
        trends = st.session_state.analyzer.get_trends()
        if trends:
            for fund, data in trends.items():
                with st.expander(f"Fund Activity: {fund}", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("#### ✨ New Entrants")
                        if not data['new_entries'].empty:
                            st.table(data['new_entries'])
                        else:
                            st.write("No new entrants this month.")
                    with col2:
                        st.markdown("#### ❌ Exited Positions")
                        if not data['exited'].empty:
                            st.table(data['exited'])
                        else:
                            st.write("No exits this month.")
        else:
            st.write("Trend data unavailable.")

    # 7. Investment Prospects
    with tabs[6]:
        st.header("Investment Prospects")
        
        # Prospect Controls
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)
            min_funds = col1.number_input("Min Funds Holding", 1, 20, 2)
            min_score = col2.number_input("Min Composite Score", 0.0, 100.0, 10.0)
            asset_filter_p = col3.selectbox("Asset Type Filter", ["Equity Only", "All Asset Types"], key="prospect_filter")
            
            bulk_file = st.file_uploader("Upload Bulk Deals CSV (NSE/BSE)", type="csv")
            if bulk_file:
                temp_bulk = "temp_bulk.csv"
                with open(temp_bulk, "wb") as f:
                    f.write(bulk_file.getbuffer())
                st.session_state.bulk_df = bulk_deals_parser.parse_bulk_deals_csv(temp_bulk)
                os.remove(temp_bulk)
                st.success("Bulk deals parsed!")

            if st.button("🚀 Refresh Analysis"):
                with st.spinner("Analyzing prospects and fetching real-time data..."):
                    filter_val_p = "Equity" if asset_filter_p == "Equity Only" else None
                    prospects = st.session_state.analyzer.get_investment_prospects(asset_type_filter=filter_val_p)
                    st.session_state.prospects = prospects
                    st.success("Analysis complete!")
        
        if st.session_state.prospects:
            filtered = [
                p for p in st.session_state.prospects
                if p['funds_holding'] >= min_funds and p['composite_score'] >= min_score
            ]
            
            if filtered:
                display_list = []
                for p in filtered:
                    pd_data = p.get('price_data')
                    low_dist = ((pd_data['current_price'] - pd_data['price_52w_low']) / pd_data['price_52w_low']) * 100 if pd_data else 0
                    row = {
                        "Stock": p['stock'],
                        "Sector": p['sector'],
                        "Funds": p['funds_holding'],
                        "Score": f"{p['composite_score']:.2f}",
                        "Signal": p['active_buy_signal']['signal'] if p['active_buy_signal'] else "N/A",
                        "Price": f"{pd_data['current_price']:.2f}" if pd_data else "N/A",
                        "Off High": f"-{pd_data['pct_below_52w_high']:.1f}%" if pd_data else "N/A",
                        "Off Low": f"+{low_dist:.1f}%" if pd_data else "N/A",
                        "Vol Spike": "YES" if pd_data and pd_data.get('volume_spike') else "No"
                    }
                    
                    if pd_data and pd_data.get('volume_spike'):
                        row["Vol Ratio"] = f"{pd_data['volume_ratio']:.1f}x" if 'volume_ratio' in pd_data else f"{pd_data.get('volume_spike_ratio', 0):.1f}x"
                    else:
                        row["Vol Ratio"] = "-"

                    if st.session_state.bulk_df is not None:
                        act = bulk_deals_parser.get_mf_bulk_activity(st.session_state.bulk_df, p['stock'])
                        row['Bulk Verdict'] = act['verdict']
                    
                    display_list.append(row)
                
                st.subheader("Top Prospects Summary")
                prospect_df = pd.DataFrame(display_list)
                st.dataframe(prospect_df, use_container_width=True, hide_index=True)

                # Detail View
                st.divider()
                selected_prospect_name = st.selectbox("🔍 Select a Stock to Inspect Details", [p['stock'] for p in filtered])
                if selected_prospect_name:
                    p = next(item for item in filtered if item['stock'] == selected_prospect_name)
                    pd_data = p.get('price_data')
                    
                    st.subheader(f"Detailed Analysis: {p['stock']}")
                    
                    # Row 1: Key Metrics
                    m_col1, m_col2 = st.columns([1, 2])
                    with m_col1:
                        st.write("**Fundamental Data**")
                        if pd_data:
                            fund_data = {
                                "Metric": ["Current Price", "52W High", "52W Low", "EMA Status", "Vol Spike", "Spike Date", "Vol Ratio", "% Since Spike"],
                                "Value": [
                                    f"₹{pd_data['current_price']:.2f}",
                                    f"₹{pd_data['price_52w_high']:.2f}",
                                    f"₹{pd_data['price_52w_low']:.2f}",
                                    pd_data['ema_status'],
                                    "YES" if pd_data.get('volume_spike') else "No",
                                    pd_data.get('latest_volume_spike_date', "-"),
                                    f"{pd_data.get('volume_spike_ratio', 0):.1f}x" if pd_data.get('volume_spike') else "-",
                                    f"{pd_data.get('price_change_since_volume_spike', 0):.1f}%" if pd_data.get('volume_spike') else "-"
                                ]
                            }
                            st.table(pd.DataFrame(fund_data))
                        else:
                            st.write("Price data unavailable for this stock.")
                    
                    with m_col2:
                        st.write("**Monthly Allocation % per Fund**")
                        # Construct Monthly Table
                        all_dates = sorted(list(st.session_state.analyzer.all_dates))
                        date_headers = [d.strftime('%b-%y') for d in all_dates]
                        
                        monthly_data = []
                        for fd in p['fund_details']:
                            row = {"Fund": fd['fund']}
                            for d in all_dates:
                                val = fd['monthly_series'].get(d.strftime('%Y-%m-%d'), 0)
                                row[d.strftime('%b-%y')] = f"{val:.2f}%" if val > 0 else "0.00%"
                            monthly_data.append(row)
                        
                        # Add Average row
                        avg_row = {"Fund": "AVERAGE"}
                        ts_avg = st.session_state.analyzer.get_stock_time_series(p['stock'])
                        for d in all_dates:
                            val = ts_avg[ts_avg['Date'] == d]['AVERAGE'].iloc[0] if not ts_avg[ts_avg['Date'] == d].empty else 0
                            avg_row[d.strftime('%b-%y')] = f"{val:.2f}%"
                        monthly_data.append(avg_row)
                        
                        st.dataframe(pd.DataFrame(monthly_data), use_container_width=True, hide_index=True)

                    # Row 2: Charts
                    st.write("**Visual Trends**")
                    c_col1, c_col2 = st.columns([2, 1])
                    with c_col1:
                        fig1, ax1 = plt.subplots(figsize=(10, 5))
                        for fd in p['fund_details']:
                            dates_sorted = sorted(fd['monthly_series'].keys())
                            vals = [fd['monthly_series'][d] for d in dates_sorted]
                            date_objs = [datetime.strptime(d, '%Y-%m-%d') for d in dates_sorted]
                            ax1.plot(date_objs, vals, marker='o', label=fd['fund'], alpha=0.6)
                        
                        # Add Average Line
                        ts = st.session_state.analyzer.get_stock_time_series(p['stock'])
                        ax1.plot(ts['Date'], ts['AVERAGE'], color='black', linewidth=3, linestyle='--', label='OVERALL AVG', marker='s')
                        
                        ax1.set_title(f"Concentration History: {p['stock']}")
                        ax1.set_ylabel("Allocation %")
                        ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
                        ax1.grid(True, alpha=0.3)
                        plt.xticks(rotation=45)
                        st.pyplot(fig1)
                    
                    with c_col2:
                        fig2, ax2 = plt.subplots(figsize=(6, 5))
                        fund_names = [fd['fund'] for fd in p['fund_details']]
                        latest_vals = [fd['latest_alloc'] for fd in p['fund_details']]
                        colors = ['green' if fd['change_3m'] > 0 else ('red' if fd['change_3m'] < 0 else 'grey') for fd in p['fund_details']]
                        bars = ax2.bar(fund_names, latest_vals, color=colors)
                        ax2.set_ylabel("Allocation %")
                        ax2.set_title("Latest Fund Snapshot")
                        plt.xticks(rotation=45, ha='right')
                        for bar in bars:
                            h = bar.get_height()
                            ax2.text(bar.get_x() + bar.get_width()/2., h, f'{h:.1f}%', ha='center', va='bottom', fontsize=8)
                        st.pyplot(fig2)

                    # Bulk Deals for this stock
                    if st.session_state.bulk_df is not None:
                        st.write("**Recent Bulk Deals Activity**")
                        activity = bulk_deals_parser.get_mf_bulk_activity(st.session_state.bulk_df, p['stock'])
                        st.info(f"**Verdict:** {activity['verdict']}")
                        if activity['deals']:
                            st.table(pd.DataFrame(activity['deals']))
                        else:
                            st.write("No MF bulk deals found for this stock.")

            else:
                st.warning("No stocks match the current filter criteria.")
        
        # Formula Section
        st.divider()
        with st.expander("ℹ️ How is the Investment Prospect Score calculated?"):
            st.markdown("""
            The **Composite Score** is calculated using a multi-factor weighting model:
            
            1.  **Breadth Score (25%)**: Percentage of tracked funds holding the stock.
            2.  **Momentum Score (30%)**: Average change in allocation % across all funds over the last 3 months.
            3.  **Conviction Score (20%)**: Percentage of funds that have *increased* their allocation in the last 3 months.
            4.  **Breadth Acceleration (15%)**: Bonus points (up to 15) if the number of funds holding the stock is increasing.
            5.  **New Entrant Bonus (10 pts)**: Flat bonus if 2 or more funds have newly entered the stock in the last month.
            6.  **Technical Adjustment**: 
                *   **+15 pts** if a majority of funds have a 'Strong Buy' or 'Active Buy' signal based on their allocation patterns.
                *   **-15 pts** if a majority are 'Reducing'.
            
            *Final score is normalized between 0 and 100.*
            """)

    # 8. Watchlist
    with tabs[7]:
        st.header("Watchlist Management")
        
        col1, col2 = st.columns([3, 1])
        new_stock = col1.text_input("Add Stock Symbol (e.g., RELIANCE.NS)", placeholder="Enter Yahoo Ticker...")
        if col2.button("Add to Watchlist", use_container_width=True):
            if new_stock:
                clean_stock = new_stock.strip().upper()
                if clean_stock not in st.session_state.watchlist:
                    st.session_state.watchlist.append(clean_stock)
                    with open("watchlist.json", "w") as f:
                        json.dump(st.session_state.watchlist, f)
                    st.rerun()

        if st.session_state.watchlist:
            watch_data = []
            with st.spinner("Updating real-time prices..."):
                for stock in st.session_state.watchlist:
                    price_info = price_fetcher.get_price_data(stock)
                    if price_info:
                        watch_data.append({
                            "Symbol": stock,
                            "Price": f"{price_info.get('current_price'):.2f}",
                            "52W High": f"{price_info.get('price_52w_high'):.2f}",
                            "Off High (%)": f"{price_info.get('pct_below_52w_high'):.1f}%",
                            "EMA Status": price_info.get('ema_status')
                        })
                    else:
                        watch_data.append({"Symbol": stock, "Price": "Offline/Not Found"})
            
            st.dataframe(pd.DataFrame(watch_data), use_container_width=True, hide_index=True)
            
            st.divider()
            remove_stock = st.selectbox("Select Symbol to Remove", st.session_state.watchlist)
            if st.button("Remove Selected"):
                st.session_state.watchlist.remove(remove_stock)
                with open("watchlist.json", "w") as f:
                    json.dump(st.session_state.watchlist, f)
                st.rerun()
        else:
            st.info("Watchlist is empty. Add symbols to track them.")
