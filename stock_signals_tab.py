import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from stock_activity_engine import StockActivityEngine
from price_data_fetcher import get_price_metrics

# --- Cached Signal Wrappers ---
@st.cache_data
def run_new_entries(_engine, threshold_pct, lookback_months):
    return _engine.get_new_entries(threshold_pct, lookback_months)

@st.cache_data
def run_buildup_acceleration(_engine, min_funds, lookback_months):
    return _engine.get_buildup_acceleration(min_funds, lookback_months)

@st.cache_data
def run_partial_exits(_engine, reduction_threshold_pct, lookback_months, min_funds):
    return _engine.get_partial_exits(reduction_threshold_pct, lookback_months, min_funds)

@st.cache_data
def run_herd_entries(_engine, min_funds, lookback_months):
    return _engine.get_herd_entries(min_funds, lookback_months)

@st.cache_data(ttl=3600)
def _cached_price_metrics(stock_name):
    return get_price_metrics(stock_name)

def render_stock_signals_tab(engine: StockActivityEngine):
    st.header("📊 Stock Signals")
    st.caption("Stock-centric intelligence across all fund categories")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "🆕 New Entries",
        "📈 Buildup Acceleration", 
        "⚠️ Partial Exits",
        "👥 Herd Entries"
    ])

    # Tab 1: New Entries
    with tab1:
        st.info("💡 Each fund is compared against its own latest available month — so all 316 funds participate even if their data update dates differ.")
        col1, col2, col3 = st.columns([2, 2, 1])
        threshold_pct = col1.number_input("Min Entry Weight (%)", 0.5, 10.0, 1.0, 0.5, key="ni_threshold")
        lookback_months = col2.number_input("Lookback Months", 1, 12, 3, 1, key="ni_lookback")
        run_new = col3.button("🔍 Run", key="run_new_entries")
        
        if run_new:
            st.session_state["new_entries_df"] = run_new_entries(engine, threshold_pct, lookback_months)
            
        df = st.session_state.get("new_entries_df")
        if df is not None:
            if not df.empty:
                event = st.dataframe(
                    df,
                    column_config={
                        "entry_date": st.column_config.DateColumn("Entry Date", format="DD-MM-YYYY"),
                        "entry_weight": st.column_config.NumberColumn("Entry Weight %", format="%.2f%%"),
                        "funds_entering_count": st.column_config.NumberColumn("Funds Entering"),
                        "already_holding_count": st.column_config.NumberColumn("Already Holding"),
                        "total_fund_coverage": st.column_config.NumberColumn("Total Coverage")
                    },
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="df_new_entries"
                )
                _render_export_button(df, "new_entries")
                st.caption("'Already Holding' = funds that owned this stock before this month. 'Total Coverage' = new entrants + existing holders.")
                
                if event.selection and event.selection.get("rows"):
                    selected_stock = df.iloc[event.selection["rows"][0]]["stock_name"]
                    st.divider()
                    _render_stock_detail(engine, selected_stock, lookback_months, threshold_pct)
                else:
                    st.caption("👆 Click any row above to view detailed stock analysis")
            else:
                st.info("No new entries found with current filters.")

    # Tab 2: Buildup Acceleration
    with tab2:
        st.info("💡 Each fund is compared against its own latest available month — so all 316 funds participate even if their data update dates differ.")
        col1, col2, col3 = st.columns([2, 2, 1])
        min_funds = col1.number_input("Min Funds", 1, 20, 3, 1, key="ba_min_funds")
        lookback_months = col2.number_input("Lookback Months", 2, 12, 3, 1, key="ba_lookback")
        run_accel = col3.button("🔍 Run", key="run_buildup_acceleration")
        
        if run_accel:
            st.session_state["buildup_accel_df"] = run_buildup_acceleration(engine, min_funds, lookback_months)
            
        df = st.session_state.get("buildup_accel_df")
        if df is not None:
            if not df.empty:
                event = st.dataframe(
                    df,
                    column_config={
                        "avg_recent_delta": st.column_config.NumberColumn("Avg Recent Delta %", format="%.2f%%"),
                        "funds_accelerating": st.column_config.NumberColumn("Funds Accelerating"),
                        "avg_shares_change_pct": st.column_config.NumberColumn("Avg Shares Change %", format="%.2f%%"),
                        "accumulation_type": st.column_config.TextColumn("Activity Type")
                    },
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="df_buildup_accel"
                )
                _render_export_button(df, "buildup_accel")
                st.caption("💡 'Active Accumulation' = shares held actually increased >5%. 'Passive Drift' = weight % increased mainly due to relative portfolio value shifts.")
                
                if event.selection and event.selection.get("rows"):
                    selected_stock = df.iloc[event.selection["rows"][0]]["stock_name"]
                    st.divider()
                    _render_stock_detail(engine, selected_stock, lookback_months, 1.0)
                else:
                    st.caption("👆 Click any row above to view detailed stock analysis")
            else:
                st.info("No buildup acceleration detected with current filters.")

    # Tab 3: Partial Exits
    with tab3:
        st.info("💡 Each fund is compared against its own latest available month — so all 316 funds participate even if their data update dates differ.")
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        reduction_threshold_pct = col1.number_input("Reduction Threshold (%)", 10, 90, 50, 5, key="pe_threshold")
        lookback_months = col2.number_input("Lookback Months", 2, 12, 5, 1, key="pe_lookback")
        min_funds = col3.number_input("Min Funds", 1, 10, 2, 1, key="pe_min_funds")
        run_exits = col4.button("🔍 Run", key="run_partial_exits")
        
        if run_exits:
            st.session_state["partial_exits_df"] = run_partial_exits(engine, reduction_threshold_pct, lookback_months, min_funds)
            
        df = st.session_state.get("partial_exits_df")
        if df is not None:
            if not df.empty:
                event = st.dataframe(
                    df,
                    column_config={
                        "avg_reduction_pct": st.column_config.NumberColumn("Avg Reduction %", format="%.2f%%"),
                        "avg_peak_weight": st.column_config.NumberColumn("Avg Peak Weight %", format="%.2f%%"),
                        "avg_current_weight": st.column_config.NumberColumn("Avg Current Weight %", format="%.2f%%"),
                        "funds_reducing": st.column_config.NumberColumn("Funds Reducing"),
                        "avg_shares_change_pct": st.column_config.NumberColumn("Avg Shares Change %", format="%.2f%%"),
                        "exit_type": st.column_config.TextColumn("Activity Type")
                    },
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="df_partial_exits"
                )
                _render_export_button(df, "partial_exits")
                st.caption("💡 'Active Selling' = shares held actually decreased >5%. 'Passive Dilution' = weight % decreased mainly due to relative portfolio value shifts.")
                
                if event.selection and event.selection.get("rows"):
                    selected_stock = df.iloc[event.selection["rows"][0]]["stock_name"]
                    st.divider()
                    _render_stock_detail(engine, selected_stock, lookback_months, 1.0)
                else:
                    st.caption("👆 Click any row above to view detailed stock analysis")
            else:
                st.info("No partial exits detected with current filters.")

    # Tab 4: Herd Entries
    with tab4:
        st.info("💡 Each fund is compared against its own latest available month — so all 316 funds participate even if their data update dates differ.")
        col1, col2, col3 = st.columns([2, 2, 1])
        min_funds = col1.number_input("Min Funds", 2, 20, 5, 1, key="he_min_funds")
        lookback_months = col2.number_input("Lookback Months", 1, 6, 3, 1, key="he_lookback")
        run_herd = col3.button("🔍 Run", key="run_herd_entries")
        
        if run_herd:
            st.session_state["herd_entries_df"] = run_herd_entries(engine, min_funds, lookback_months)
            
        df = st.session_state.get("herd_entries_df")
        if df is not None:
            if not df.empty:
                event = st.dataframe(
                    df,
                    column_config={
                        "avg_entry_weight": st.column_config.NumberColumn("Avg Entry Weight %", format="%.2f%%"),
                        "funds_entering": st.column_config.NumberColumn("Funds Entering"),
                        "first_entry_date": st.column_config.DateColumn("First Entry Date", format="DD-MM-YYYY")
                    },
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="df_herd_entries"
                )
                _render_export_button(df, "herd_entries")
                
                if event.selection and event.selection.get("rows"):
                    selected_stock = df.iloc[event.selection["rows"][0]]["stock_name"]
                    st.divider()
                    _render_stock_detail(engine, selected_stock, lookback_months, 1.0)
                else:
                    st.caption("👆 Click any row above to view detailed stock analysis")
            else:
                st.info("No herd entries detected with current filters.")

def _render_export_button(df, key):
    export_df = df.copy()
    for col in ['entry_date', 'first_entry_date']:
        if col in export_df.columns:
            export_df[col] = pd.to_datetime(export_df[col]).dt.strftime('%d-%m-%Y')
    
    csv = export_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=f"stock_signals_{key}.csv",
        mime="text/csv",
        key=f"dl_{key}"
    )

def _render_stock_detail(engine, stock_name, lookback_months, threshold_pct):
    weight_pivot, shares_pivot, new_entrant_funds = engine.get_stock_detail_with_entrants(
        stock_name, lookback_months, threshold_pct
    )
    
    if weight_pivot.empty:
        st.warning(f"No historical data found for {stock_name}")
        return

    st.subheader(f"📌 {stock_name}")

    price_data = _cached_price_metrics(stock_name)
    if price_data["error"]:
        st.caption(f"⚠️ Price data unavailable ({price_data['ticker']}) — {price_data['error']}")
    else:
        cols = st.columns(6)
        cols[0].metric("LTP (₹)", f"{price_data['ltp']:.2f}")
        for i, (label, key) in enumerate([
            ("1M", "change_1m"), ("3M", "change_3m"), ("6M", "change_6m"),
            ("YTD", "change_ytd"), ("1Y", "change_1y")
        ], start=1):
            val = price_data[key]
            cols[i].metric(label, f"{val:+.2f}%" if val is not None else "N/A")
    
    # --- Sector Context ---
    sector_info = engine.get_sector_peers_activity(stock_name, lookback_months)
    with st.expander("🌐 Sector Context", expanded=False):
        st.write(f"**Sector:** {sector_info['sector']}")
        if sector_info['is_rotation']:
            st.info(f"🔎 {sector_info['peer_count']} other {sector_info['sector']} stocks also show New Entries this month: {', '.join(sector_info['peers'])}")
            st.markdown("**Verdict:** → Possible sector-wide rotation")
        else:
            st.write(f"No other {sector_info['sector']} stocks show New Entries — appears stock-specific.")

    if new_entrant_funds:
        st.success(f"🆕 New Entrants ({len(new_entrant_funds)}): " + ", ".join(new_entrant_funds))
    
    # --- VIEW TOGGLE ---
    view_mode = st.radio(
        "📊 View Mode",
        ["Weight %", "Shares Held"],
        horizontal=True,
        key=f"view_mode_{stock_name}"
    )

    if view_mode == "Weight %":
        active_pivot = weight_pivot
        y_label = "Portfolio Weight %"
        hover_fmt = '%{x|%b %Y}: %{y:.2f}%'
    else:
        active_pivot = shares_pivot
        y_label = "Shares Held"
        hover_fmt = '%{x|%b %Y}: %{y:,.0f} shares'

    # --- Chart 1: New Entrants Only ---
    if new_entrant_funds:
        st.markdown(f"**New Entrant Funds — {view_mode} Trajectory**")
        fig1 = go.Figure()
        for fund in new_entrant_funds:
            if fund in active_pivot.columns:
                series = active_pivot[fund].replace(0, None)
                fig1.add_trace(go.Scatter(
                    x=active_pivot.index, y=series, name=fund,
                    mode='lines+markers', line=dict(width=3),
                    hovertemplate=hover_fmt
                ))
        fig1.update_layout(
            xaxis_title="Month", yaxis_title=y_label,
            hovermode="x unified", height=350,
            legend=dict(orientation="h", y=-0.3)
        )
        st.plotly_chart(fig1, use_container_width=True, key=f"chart1_{stock_name}_{view_mode}")
    
    # --- Chart 2: Top 10 Holders Only (Ranked by weight even in shares view) ---
    st.markdown(f"**Top 10 Holders — {view_mode} Trajectory**")
    latest_weights = weight_pivot.iloc[0].sort_values(ascending=False)
    top_10_funds = latest_weights.head(10).index.tolist()
    
    fig2 = go.Figure()
    for fund in top_10_funds:
        if fund in active_pivot.columns:
            series = active_pivot[fund].replace(0, None)
            is_new = fund in new_entrant_funds
            fig2.add_trace(go.Scatter(
                x=active_pivot.index, y=series, name=fund,
                mode='lines+markers',
                line=dict(width=3 if is_new else 1.5, dash='solid' if is_new else 'dot'),
                hovertemplate=hover_fmt
            ))
    fig2.update_layout(
        xaxis_title="Month", yaxis_title=y_label,
        hovermode="x unified", height=400,
        legend=dict(orientation="v", x=1.02, y=1)
    )
    st.plotly_chart(fig2, use_container_width=True, key=f"chart2_{stock_name}_{view_mode}")
    
    # --- Full data tables ---
    with st.expander(f"📋 Full Holdings History — All {len(weight_pivot.columns)} Funds"):
        table_tab1, table_tab2 = st.tabs(["Weight % Table", "Shares Held Table"])
        with table_tab1:
            st.dataframe(weight_pivot.style.format("{:.2f}", na_rep="-"), use_container_width=True)
        with table_tab2:
            st.dataframe(shares_pivot.style.format("{:,.0f}", na_rep="-"), use_container_width=True)
