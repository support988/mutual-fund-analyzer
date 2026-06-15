import streamlit as st
import pandas as pd
import os
import matplotlib.pyplot as plt
from datetime import datetime

from analyzer import MFAnalyzer
from exporter import export_to_excel
from path_utils import get_app_data_path
from ngen_data_loader import scan_downloads, BASE_DIR
from stock_signals_tab import render_stock_signals_tab

# --- Cached Resource for Stock Activity Engine ---
@st.cache_resource
def load_engine():
    # v1.0.1 - Force refresh for new methods
    from stock_activity_engine import StockActivityEngine
    engine = StockActivityEngine(BASE_DIR)
    engine.load_all()
    return engine

# --- Versioned Cached Data Helpers ---
# We pass 'version' to ensure the cache is invalidated when selection changes, 
# without clearing the global cache (which would kill the parse_mf_csv cache).

@st.cache_data
def get_master_holdings_cached(_analyzer, version, asset_type_filter, analysis_date, smart_patching):
    return _analyzer.get_master_holdings(asset_type_filter, analysis_date, smart_patching)

@st.cache_data
def get_overlap_matrix_cached(_analyzer, version, asset_type_filter):
    return _analyzer.get_overlap_matrix(asset_type_filter)

@st.cache_data
def get_common_new_entrants_cached(_analyzer, version, months_lookback, asset_type_filter):
    return _analyzer.get_common_new_entrants(months_lookback, asset_type_filter)

@st.cache_data
def get_trends_cached(_analyzer, version):
    return _analyzer.get_trends()

@st.cache_data
def get_conviction_entrants_cached(_analyzer, version, asset_type_filter, min_allocation):
    return _analyzer.get_conviction_entrants(asset_type_filter, min_allocation)

@st.cache_data
def get_buildup_acceleration_cached(_analyzer, version, asset_type_filter, min_funds):
    return _analyzer.get_buildup_acceleration(asset_type_filter, min_funds)

@st.cache_data
def get_partial_exits_cached(_analyzer, version, asset_type_filter, exit_threshold, months_lookback):
    return _analyzer.get_partial_exits(asset_type_filter, exit_threshold, months_lookback)

@st.cache_data
def get_herd_entries_cached(_analyzer, version, asset_type_filter, min_funds, months_lookback):
    return _analyzer.get_herd_entries(asset_type_filter, min_funds, months_lookback)

# Set page config
st.set_page_config(page_title="MF Portfolio Tracker", layout="wide")

# --- Session State Initialization ---
if 'catalog' not in st.session_state:
    st.session_state.catalog = scan_downloads(BASE_DIR)

if 'selection_version' not in st.session_state:
    st.session_state.selection_version = 0

# Initialize multiselect keys if not present
for group, categories in st.session_state.catalog.items():
    for cat_name, fund_list in categories.items():
        ms_key = f"ms_{cat_name}"
        if ms_key not in st.session_state:
            # Default: Start empty as per user request
            st.session_state[ms_key] = []

if 'analyzer' not in st.session_state:
    st.session_state.analyzer = MFAnalyzer()
    # No pre-loading of funds on first open; analyzer stays empty until user selects funds in sidebar

# --- Sidebar: Controls & Selection ---
st.sidebar.title("Controls")

# 1. File Uploads
uploaded_files = st.sidebar.file_uploader("Upload MF CSVs", type="csv", accept_multiple_files=True)
if uploaded_files:
    for uploaded_file in uploaded_files:
        temp_path = os.path.join(os.getcwd(), f"temp_{uploaded_file.name}")
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        fund_name = st.session_state.analyzer.add_fund(temp_path)
    st.session_state.selection_version += 1
    st.sidebar.success("Files processed!")

# 2. Bulk Actions
col1, col2 = st.sidebar.columns(2)
if col1.button("Clear Selection"):
    for group, categories in st.session_state.catalog.items():
        for cat_name in categories:
            st.session_state[f"ms_{cat_name}"] = []
    st.session_state.analyzer = MFAnalyzer()
    st.session_state.selection_version += 1
    st.rerun()

if col2.button("Reset to All"):
    for group, categories in st.session_state.catalog.items():
        for cat_name, fund_list in categories.items():
            st.session_state[f"ms_{cat_name}"] = [f["fund_name"] for f in fund_list]
    st.session_state.selection_version += 1
    st.rerun()

# 3. Excel Export
if st.session_state.analyzer.funds:
    if st.sidebar.button("📥 Prepare Excel Export"):
        with st.sidebar:
            with st.spinner("Generating Excel report..."):
                temp_export = "temp_export.xlsx"
                try:
                    if export_to_excel(st.session_state.analyzer, temp_export):
                        with open(temp_export, "rb") as f:
                            st.download_button(
                                label="Download Ready",
                                data=f,
                                file_name="MF_Analysis_Export.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        os.remove(temp_export)
                except Exception as e:
                    st.error(f"Export failed: {e}")

st.sidebar.divider()
st.sidebar.title("Mutual Fund Selection")

# 4. Categorized Selection using Multiselect
all_selected_paths = set()
for group, categories in st.session_state.catalog.items():
    for cat_name, fund_list in categories.items():
        with st.sidebar.expander(f"{cat_name} ({len(fund_list)})"):
            ms_key = f"ms_{cat_name}"
            
            # Select All / Clear Buttons for the category
            bcol1, bcol2 = st.columns(2)
            if bcol1.button("Select All", key=f"all_btn_{cat_name}"):
                st.session_state[ms_key] = [f["fund_name"] for f in fund_list]
                st.session_state.selection_version += 1
                st.rerun()
            if bcol2.button("Clear", key=f"clr_btn_{cat_name}"):
                st.session_state[ms_key] = []
                st.session_state.selection_version += 1
                st.rerun()
            
            selected_names = st.multiselect(
                "Select Funds",
                options=[f["fund_name"] for f in fund_list],
                key=ms_key
            )
            
            # Map selected names back to paths
            name_to_path = {f["fund_name"]: f["filepath"] for f in fund_list}
            for name in selected_names:
                all_selected_paths.add(name_to_path[name])

# --- Sync Analyzer with Selection ---
current_analyzer_paths = set(f['file_path'] for f in st.session_state.analyzer.funds.values())
catalog_paths = set()
for g, cats in st.session_state.catalog.items():
    for c, flist in cats.items():
        for f in flist:
            catalog_paths.add(f["filepath"])

current_catalog_paths = current_analyzer_paths.intersection(catalog_paths)

if current_catalog_paths != all_selected_paths:
    to_add = all_selected_paths - current_catalog_paths
    to_remove = current_catalog_paths - all_selected_paths
    
    # Remove
    to_remove_names = [name for name, info in st.session_state.analyzer.funds.items() if info['file_path'] in to_remove]
    for name in to_remove_names:
        st.session_state.analyzer.remove_fund(name)
    
    # Add
    for path in to_add:
        st.session_state.analyzer.add_fund(path)
    
    st.session_state.selection_version += 1
    st.rerun()

# --- Main UI ---
st.title("Mutual Fund Portfolio Overlap & Concentration Tracker")

tabs = st.tabs([
    "File Management", "Overlap Analysis", 
    "Concentration Tracker", "Trend Analysis", 
    "Behavioral Insights", "Stock Signals"
])

ver = st.session_state.selection_version

# 1. File Management
with tabs[0]:
    st.header("Currently Loaded Funds")
    fund_list = list(st.session_state.analyzer.funds.keys())
    if fund_list:
        st.write(f"Total funds loaded: **{len(fund_list)}**")
        
        # Display as a searchable dataframe for performance
        funds_df = pd.DataFrame([
            {"Fund Name": name, "Category": "Uploaded" if info['file_path'].startswith("temp_") else "Catalog"} 
            for name, info in st.session_state.analyzer.funds.items()
        ])
        st.dataframe(funds_df, use_container_width=True, hide_index=True)
        
        st.info("💡 Use the sidebar to add or remove funds from the analysis.")
    else:
        st.write("No funds loaded.")
        st.info("Please select Mutual Funds from the sidebar or upload CSV files to begin.")

# 2. Overlap Analysis
with tabs[1]:
    st.header("Overlap Analysis")
    if not st.session_state.analyzer.funds:
        st.warning("No funds loaded. Select or upload CSVs to analyze overlap.")
    else:
        matrices = get_overlap_matrix_cached(st.session_state.analyzer, ver, asset_type_filter="Equity")
        st.subheader("Overlap Count (%)")
        st.dataframe(matrices['count'].style.background_gradient(cmap='RdYlGn', axis=None).format("{:.1f}%"), use_container_width=True)
        st.subheader("Overlap Weight (%)")
        st.dataframe(matrices['weight'].style.background_gradient(cmap='RdYlGn', axis=None).format("{:.1f}%"), use_container_width=True)

# 3. Concentration Tracker
with tabs[2]:
    st.header("Concentration Tracker")
    if not st.session_state.analyzer.funds:
        st.warning("No funds loaded. Select or upload CSVs to track concentration.")
    else:
        col1, col2 = st.columns(2)
        asset_filter_c = col1.selectbox("Asset Type", ["All", "Equity", "Debt", "Others"], index=1, key="conc_asset_filter")
        
        filter_val_c = asset_filter_c if asset_filter_c != "All" else None
        master_all = get_master_holdings_cached(
            st.session_state.analyzer, ver,
            asset_type_filter=filter_val_c,
            analysis_date=None, 
            smart_patching=True
        )
        
        if not master_all.empty:
            all_stocks = sorted(master_all['Name'].tolist())
            selected_stock = col2.selectbox("Select Stock to Track", all_stocks, key="stock_selector")
            
            if selected_stock:
                ts_df = st.session_state.analyzer.get_stock_time_series(selected_stock)
                st.subheader(f"Allocation History: {selected_stock}")
                
                fig, ax = plt.subplots(figsize=(10, 5))
                x_axis = ts_df['Date']
                
                for fund in ts_df.columns:
                    if fund in ['Date', 'AVERAGE']:
                        continue
                    if ts_df[fund].sum() > 0:
                        ax.plot(x_axis, ts_df[fund], marker='o', linewidth=2, label=fund)
                
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

# 4. Trend Analysis
with tabs[3]:
    st.header("Trend Analysis")
    if not st.session_state.analyzer.funds:
        st.warning("No funds loaded. Select or upload CSVs to see trends.")
    else:
        st.subheader("🔥 Common New Entrants (Last 3 Months)")
        st.info("Stocks that were NOT in a fund's portfolio 3 months ago but are present now.")
        
        with st.container(border=True):
            col1, col2 = st.columns(2)
            lookback = col1.slider("Months Lookback", 1, 12, 3)
            ent_asset_filter = col2.selectbox("Asset Type", ["Equity", "All"], index=0, key="ent_asset_filter")
            
            filter_val_e = ent_asset_filter if ent_asset_filter != "All" else None
            common_entrants = get_common_new_entrants_cached(st.session_state.analyzer, ver, lookback, filter_val_e)
            
            if not common_entrants.empty:
                st.dataframe(common_entrants, use_container_width=True, hide_index=True)
            else:
                st.write("No common new entrants found in the selected period.")

        st.divider()
        st.subheader("Individual Fund Activity")
        trends = get_trends_cached(st.session_state.analyzer, ver)
        if trends:
            for fund, data in trends.items():
                with st.expander(f"Fund Activity: {fund}", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("#### ✨ New Entrants (Current Month)")
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

# 5. Behavioral Insights
with tabs[4]:
    st.header("Behavioral Insights & Qualitative Analysis")
    if not st.session_state.analyzer.funds:
        st.warning("No funds loaded. Select or upload CSVs to see behavioral insights.")
    else:
        st.info("Automated institutional sentiment analysis based on recent holding patterns.")
        
        # Conviction Entrants
        st.subheader("🚀 High Conviction Entrants")
        st.markdown("*New entries where funds took a significant initial position (>=1%).*")
        with st.container(border=True):
            col1, col2 = st.columns(2)
            min_alloc = col1.slider("Min Initial Allocation (%)", 0.5, 5.0, 1.0, step=0.1)
            conv_asset_filter = col2.selectbox("Asset Type", ["Equity", "All"], index=0, key="conv_asset_filter")
            
            filter_val_conv = "Equity" if conv_asset_filter == "Equity" else None
            df_conv = get_conviction_entrants_cached(st.session_state.analyzer, ver, filter_val_conv, min_alloc)
            if not df_conv.empty:
                st.dataframe(df_conv, use_container_width=True, hide_index=True)
            else:
                st.write("No high conviction entries found with current filters.")

        # Buildup Acceleration
        st.subheader("📈 Buildup Acceleration")
        st.markdown("*Stocks where funds are increasing their buying speed compared to previous months.*")
        with st.container(border=True):
            col1, col2 = st.columns(2)
            accel_min_funds = col1.number_input("Min Funds Showing Acceleration", 1, 10, 2)
            accel_asset_filter = col2.selectbox("Asset Type", ["Equity", "All"], index=0, key="accel_asset_filter")
            
            filter_val_accel = "Equity" if accel_asset_filter == "Equity" else None
            df_accel = get_buildup_acceleration_cached(st.session_state.analyzer, ver, filter_val_accel, accel_min_funds)
            if not df_accel.empty:
                st.dataframe(df_accel, use_container_width=True, hide_index=True)
            else:
                st.write("No accelerated buildups detected.")

        # Partial Exits
        st.subheader("⚠️ Partial Exits (Distribution)")
        st.markdown("*Stocks where multiple funds are significantly reducing their exposure.*")
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)
            exit_thresh = col1.slider("Reduction Threshold (%)", 10, 90, 50)
            exit_lookback = col2.number_input("Lookback Months", 1, 12, 3, key="exit_lookback")
            exit_asset_filter = col3.selectbox("Asset Type", ["Equity", "All"], index=0, key="exit_asset_filter")
            
            filter_val_exit = "Equity" if exit_asset_filter == "Equity" else None
            df_exits = get_partial_exits_cached(st.session_state.analyzer, ver, filter_val_exit, exit_thresh/100, exit_lookback)
            if not df_exits.empty:
                st.dataframe(df_exits, use_container_width=True, hide_index=True)
            else:
                st.write("No significant partial exits detected.")

        # Herd Entries
        st.subheader("👥 Herd Entries (Crowding Risk)")
        st.markdown("*Stocks being bought by many funds simultaneously — potential momentum or crowding.*")
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)
            herd_min_funds = col1.number_input("Min Funds Entering", 1, 20, 4)
            herd_lookback = col2.number_input("Lookback Months", 1, 12, 1, key="herd_lookback")
            herd_asset_filter = col3.selectbox("Asset Type", ["Equity", "All"], index=0, key="herd_asset_filter")
            
            filter_val_herd = "Equity" if herd_asset_filter == "Equity" else None
            df_herd = get_herd_entries_cached(st.session_state.analyzer, ver, filter_val_herd, herd_min_funds, herd_lookback)
            if not df_herd.empty:
                st.dataframe(df_herd, use_container_width=True, hide_index=True)
            else:
                st.write("No herd entries detected in the selected period.")

# 6. Stock Signals
with tabs[5]:
    engine = load_engine()
    render_stock_signals_tab(engine)
