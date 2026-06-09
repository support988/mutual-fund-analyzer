import streamlit as st
import pandas as pd
import os
import glob
import matplotlib.pyplot as plt
from datetime import datetime
import ngen_holdings_history

def show_holdings_history(analyzer):
    st.header("NGEN Holdings History & Bulk Comparison")
    
    # 1. Sync Data Section
    with st.expander("🔄 Sync Data from NGEN Markets", expanded=False):
        col1, col2, col3 = st.columns([2, 1, 1])
        category = col1.selectbox("Category to Sync", ["ALL"] + ngen_holdings_history.CATEGORIES)
        months = col2.number_input("Months of History", 1, 60, 12)
        equity_only = col3.checkbox("Equity Only", value=True)
        
        if st.button("🚀 Start Download"):
            cats = ngen_holdings_history.CATEGORIES if category == "ALL" else [category]
            with st.spinner(f"Downloading data for {len(cats)} categories..."):
                try:
                    # Capture stdout to show progress in streamlit if possible, 
                    # but for now just call run
                    ngen_holdings_history.run(
                        categories=cats,
                        months=months,
                        out_dir="downloads",
                        equity_only=equity_only,
                        delay=0.1
                    )
                    st.success("Download Complete!")
                except Exception as e:
                    st.error(f"Download failed: {e}")

    # 2. Data Loading
    holdings_path = os.path.join("downloads", "holdings")
    if not os.path.exists(holdings_path):
        st.info("No holdings data found. Please sync data above first.")
        return

    # Scan available categories (folders)
    available_cats = [d for d in os.listdir(holdings_path) if os.path.isdir(os.path.join(holdings_path, d))]
    
    if not available_cats:
        st.warning("No category folders found in downloads/holdings.")
        return

    st.divider()
    
    # 3. Sidebar Selection Interface
    st.sidebar.markdown("### 📂 Analysis Selection")
    
    if 'history_selected_funds' not in st.session_state:
        st.session_state.history_selected_funds = {} # filepath -> fund_name
    
    if 'ngen_managed_paths' not in st.session_state:
        st.session_state.ngen_managed_paths = set()

    # Scan and organize all available funds
    all_available_funds = {} # category -> list of {name, path}
    for cat in available_cats:
        cat_dir = os.path.join(holdings_path, cat)
        fund_files = glob.glob(os.path.join(cat_dir, "NGEN_Holdings_*.csv"))
        all_available_funds[cat] = []
        for f in fund_files:
            base = os.path.basename(f)
            name_part = base.replace("NGEN_Holdings_", "")
            last_under = name_part.rfind("_")
            if last_under != -1:
                name_part = name_part[:last_under]
            name_part = name_part.replace("_", " ")
            all_available_funds[cat].append({"name": name_part, "path": f})
        all_available_funds[cat].sort(key=lambda x: x['name'])

    # Clear button
    if st.sidebar.button("🗑️ Clear All Selections"):
        # Remove from global analyzer
        for path in st.session_state.history_selected_funds:
            fund_name = st.session_state.history_selected_funds[path]
            if fund_name in analyzer.funds:
                analyzer.remove_fund(fund_name)
        st.session_state.history_selected_funds = {}
        st.session_state.ngen_managed_paths = set()
        st.rerun()

    # Create Expanders in Sidebar
    for cat, funds in all_available_funds.items():
        with st.sidebar.expander(f"➕ {cat}", expanded=False):
            # Bulk Selection for Category
            col_b1, col_b2 = st.columns(2)
            if col_b1.button("Select All", key=f"btn_all_{cat}"):
                with st.spinner(f"Loading {cat} funds..."):
                    for fund in funds:
                        f_path = fund['path']
                        if f_path not in st.session_state.history_selected_funds:
                            actual_name = analyzer.add_fund(f_path)
                            if actual_name:
                                st.session_state.history_selected_funds[f_path] = actual_name
                                st.session_state.ngen_managed_paths.add(f_path)
                st.rerun()
            
            if col_b2.button("Clear All", key=f"btn_none_{cat}"):
                for fund in funds:
                    f_path = fund['path']
                    if f_path in st.session_state.history_selected_funds:
                        actual_name = st.session_state.history_selected_funds[f_path]
                        analyzer.remove_fund(actual_name)
                        del st.session_state.history_selected_funds[f_path]
                        st.session_state.ngen_managed_paths.discard(f_path)
                st.rerun()
            
            st.divider()

            for fund in funds:
                f_path = fund['path']
                f_name_approx = fund['name']
                
                is_selected = f_path in st.session_state.history_selected_funds
                
                if st.checkbox(f_name_approx, value=is_selected, key=f"chk_{f_path}"):
                    if not is_selected:
                        # Add to global analyzer
                        actual_name = analyzer.add_fund(f_path)
                        if actual_name:
                            st.session_state.history_selected_funds[f_path] = actual_name
                            st.session_state.ngen_managed_paths.add(f_path)
                            st.rerun()
                else:
                    if is_selected:
                        # Remove from global analyzer
                        actual_name = st.session_state.history_selected_funds[f_path]
                        analyzer.remove_fund(actual_name)
                        del st.session_state.history_selected_funds[f_path]
                        if f_path in st.session_state.ngen_managed_paths:
                            st.session_state.ngen_managed_paths.remove(f_path)
                        st.rerun()

    selected_paths = list(st.session_state.history_selected_funds.keys())
    
    if not selected_paths:
        st.info("👈 Select funds from the sidebar categories to begin analysis. Selected funds will automatically appear in 'File Management'.")
        return

    # 4. Use the global analyzer for analysis
    hist_analyzer = analyzer

    # Tabs for different analysis views
    h_tabs = st.tabs(["Stock Trends", "Bulk Activity", "Fund Comparison"])

    # --- Tab 1: Stock Trends ---
    with h_tabs[0]:
        st.subheader("Breadth & Weight Trends")
        
        master = hist_analyzer.get_master_holdings(asset_type_filter=None)
        if not master.empty:
            all_stocks = sorted(master['Name'].unique().tolist())
            sel_stock = st.selectbox("Search Stock", all_stocks, key="hist_stock_sel")
            
            if sel_stock:
                ts_df = hist_analyzer.get_stock_time_series(sel_stock)
                
                col1, col2 = st.columns(2)
                
                # Breadth: How many funds hold it over time
                breadth_ts = []
                for _, row in ts_df.iterrows():
                    date = row['Date']
                    count = sum(1 for f in ts_df.columns if f not in ['Date', 'AVERAGE'] and row[f] > 0)
                    breadth_ts.append({'Date': date, 'Funds Count': count})
                breadth_df = pd.DataFrame(breadth_ts)
                
                with col1:
                    st.markdown("**Holders Count Over Time**")
                    fig1, ax1 = plt.subplots(figsize=(8, 4))
                    ax1.step(breadth_df['Date'], breadth_df['Funds Count'], where='post', color='blue', linewidth=2)
                    ax1.fill_between(breadth_df['Date'], breadth_df['Funds Count'], step='post', alpha=0.2, color='blue')
                    ax1.set_ylabel("Number of Funds")
                    plt.xticks(rotation=45)
                    st.pyplot(fig1)

                with col2:
                    st.markdown("**Average Weight % Over Time**")
                    fig2, ax2 = plt.subplots(figsize=(8, 4))
                    ax2.plot(ts_df['Date'], ts_df['AVERAGE'], color='black', linewidth=3, marker='s')
                    ax2.set_ylabel("Avg Weight (%)")
                    plt.xticks(rotation=45)
                    st.pyplot(fig2)
                
                st.markdown(f"**Individual Fund Allocations: {sel_stock}**")
                st.dataframe(ts_df, use_container_width=True, hide_index=True)

    # --- Tab 2: Bulk Activity ---
    with h_tabs[1]:
        st.subheader("What's being bought/sold in bulk?")
        
        latest_month = hist_analyzer.get_latest_month()
        if latest_month:
            all_dates = sorted(list(hist_analyzer.all_dates))
            if len(all_dates) >= 2:
                prev_month = all_dates[-2]
                st.info(f"Comparing {prev_month.strftime('%b-%y')} vs {latest_month.strftime('%b-%y')}")
                
                activity_data = []
                master_latest = hist_analyzer.get_master_holdings(asset_type_filter=None)
                
                # We need to calculate changes manually across all funds
                for _, row in master_latest.iterrows():
                    stock = row['Name']
                    sector = row['Sector']
                    
                    increases = 0
                    decreases = 0
                    new_entries = 0
                    exits = 0
                    total_change = 0
                    
                    for f_name, info in hist_analyzer.funds.items():
                        df = info['df']
                        if stock in df['Name'].values:
                            s_row = df[df['Name'] == stock]
                            curr_val = s_row[latest_month].iloc[0] if latest_month in s_row.columns else 0
                            prev_val = s_row[prev_month].iloc[0] if prev_month in s_row.columns else 0
                            
                            diff = curr_val - prev_val
                            total_change += diff
                            
                            if curr_val > prev_val:
                                if prev_val == 0: new_entries += 1
                                else: increases += 1
                            elif curr_val < prev_val:
                                if curr_val == 0: exits += 1
                                else: decreases += 1
                    
                    if increases + decreases + new_entries + exits > 0:
                        activity_data.append({
                            'Stock': stock,
                            'Sector': sector,
                            'New Entries': new_entries,
                            'Increases': increases,
                            'Decreases': decreases,
                            'Exits': exits,
                            'Net Change %': round(total_change, 2),
                            'Activity Score': (new_entries * 2 + increases) - (exits * 2 + decreases)
                        })
                
                act_df = pd.DataFrame(activity_data).sort_values('Activity Score', ascending=False)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.success("📈 Most Bullish Activity")
                    st.dataframe(act_df.head(15)[['Stock', 'New Entries', 'Increases', 'Net Change %']], hide_index=True)
                with col2:
                    st.error("📉 Most Bearish Activity")
                    st.dataframe(act_df.sort_values('Activity Score').head(15)[['Stock', 'Exits', 'Decreases', 'Net Change %']], hide_index=True)
                
                st.subheader("Full Activity Report")
                st.dataframe(act_df, use_container_width=True, hide_index=True)

    # --- Tab 3: Fund Comparison ---
    with h_tabs[2]:
        st.subheader("Compare Selected Funds Portfolio")
        
        if len(hist_analyzer.funds) >= 2:
            comp_df = hist_analyzer.get_master_holdings(asset_type_filter=None)
            # Filter to only selected funds
            fund_names = list(hist_analyzer.funds.keys())
            cols_to_keep = ['Name', 'Sector', 'Type'] + fund_names
            comp_df = comp_df[cols_to_keep]
            # Recalculate stats for these funds
            comp_df['Count'] = (comp_df[fund_names] > 0).sum(axis=1)
            comp_df = comp_df[comp_df['Count'] > 0]
            comp_df['Total %'] = comp_df[fund_names].sum(axis=1)
            
            st.dataframe(comp_df.sort_values('Total %', ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("Select 2 or more funds from the sidebar to compare.")

def get_ngen_categories():
    return ngen_holdings_history.CATEGORIES
