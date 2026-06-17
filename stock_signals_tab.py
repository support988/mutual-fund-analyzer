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

@st.cache_data
def run_screener(_engine, entry_threshold_pct, lookback_months, exit_threshold_pct, herd_min_funds):
    return _engine.get_screener_data(entry_threshold_pct, lookback_months, exit_threshold_pct, herd_min_funds)

@st.cache_data(ttl=1800)
def run_institutional_intelligence(_engine, stock_name, lookback_months):
    return _engine.get_institutional_intelligence(stock_name, lookback_months)

@st.cache_data(ttl=3600)
def _cached_price_metrics(stock_name):
    return get_price_metrics(stock_name)

def render_stock_signals_tab(engine: StockActivityEngine):
    st.header("📊 Stock Signals")
    st.caption("Stock-centric intelligence across all fund categories")
    
    tab0, tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 Stock Screener",
        "🆕 New Entries",
        "📈 Buildup Acceleration",
        "⚠️ Partial Exits",
        "👥 Herd Entries"
    ])

    # Tab 0: Unified Stock Screener
    with tab0:
        st.markdown(
            "**Cross-reference all 4 signal types in one view.** "
            "A stock appearing across multiple signals = higher conviction opportunity."
        )

        # ── Parameter Controls ──────────────────────────────────────────────
        with st.expander("⚙️ Screener Parameters", expanded=True):
            sc_col1, sc_col2, sc_col3, sc_col4, sc_col5 = st.columns([2, 2, 2, 2, 1])
            sc_entry_thresh = sc_col1.number_input(
                "Min Entry Weight (%)", 0.5, 5.0, 0.5, 0.5, key="sc_entry_thresh",
                help="Minimum allocation % for a fund entry to be counted as a New Entry signal"
            )
            sc_lookback = sc_col2.number_input(
                "Lookback Months", 1, 12, 3, 1, key="sc_lookback",
                help="How far back to look for entries, acceleration, and herd activity"
            )
            sc_exit_thresh = sc_col3.number_input(
                "Exit Threshold (%)", 10, 90, 30, 5, key="sc_exit_thresh",
                help="Minimum % reduction from peak weight to count as a Partial Exit signal"
            )
            sc_herd_min = sc_col4.number_input(
                "Min Herd Funds", 2, 20, 3, 1, key="sc_herd_min",
                help="Minimum number of funds that must enter simultaneously for Herd signal"
            )
            run_screener_btn = sc_col5.button(
                "🚀 Run", key="run_screener", type="primary", use_container_width=True
            )

        if run_screener_btn:
            with st.spinner("Running all 4 signal checks across the universe..."):
                st.session_state["screener_df"] = run_screener(
                    engine, sc_entry_thresh, sc_lookback, sc_exit_thresh, sc_herd_min
                )

        screener_df = st.session_state.get("screener_df")

        if screener_df is None:
            st.info("👆 Set parameters above and click **Run** to scan the full stock universe.")

        elif screener_df.empty:
            st.warning("No stocks found. Try loosening the parameters.")

        else:
            # ── Market-wide Signal Summary ───────────────────────────────────
            n_new   = int((screener_df['new_entry_funds']    > 0).sum())
            n_accel = int((screener_df['funds_accelerating'] > 0).sum())
            n_herd  = int((screener_df['herd_funds']         > 0).sum())
            n_exit  = int((screener_df['funds_reducing']     > 0).sum())
            n_multi = int((screener_df['signal_score']       >= 2).sum())

            mc1, mc2, mc3, mc4, mc5 = st.columns(5)
            mc1.metric("🆕 New Entry",      f"{n_new} stocks")
            mc2.metric("📈 Accelerating",   f"{n_accel} stocks")
            mc3.metric("👥 Herd Entry",     f"{n_herd} stocks")
            mc4.metric("⚠️ Partial Exit",   f"{n_exit} stocks")
            mc5.metric("🎯 Multi-Signal",   f"{n_multi} stocks",
                       help="Stocks scoring ≥ 2 on Signal Score")

            st.divider()

            # ── Live Filters ─────────────────────────────────────────────────
            with st.container(border=True):
                st.markdown("**🔧 Filters** — applied instantly on screener results")
                f1, f2, f3, f4 = st.columns([3, 2, 2, 3])

                all_sectors = sorted(screener_df['sector'].dropna().unique().tolist())
                sel_sectors = f1.multiselect("Sector", all_sectors, key="sc_sectors")

                all_caps = sorted(screener_df['marketcapcat'].dropna().unique().tolist())
                sel_caps = f2.multiselect("Market Cap", all_caps, key="sc_caps")

                min_score = f3.slider("Min Signal Score", -1, 3, 0, key="sc_min_score",
                                     help="-1 = exits only | 0 = any | 1+ = at least one bullish signal | 3 = all 3 bullish")

                with f4:
                    must_ne    = st.checkbox("Must have New Entry",      key="sc_must_ne")
                    must_accel = st.checkbox("Must have Acceleration",    key="sc_must_accel")
                    must_herd  = st.checkbox("Must have Herd Entry",      key="sc_must_herd")
                    excl_exits = st.checkbox("Exclude stocks with Exits", key="sc_excl_exits")

            # Apply filters
            filtered = screener_df.copy()
            if sel_sectors:
                filtered = filtered[filtered['sector'].isin(sel_sectors)]
            if sel_caps:
                filtered = filtered[filtered['marketcapcat'].isin(sel_caps)]
            filtered = filtered[filtered['signal_score'] >= min_score]
            if must_ne:    filtered = filtered[filtered['new_entry_funds']    > 0]
            if must_accel: filtered = filtered[filtered['funds_accelerating'] > 0]
            if must_herd:  filtered = filtered[filtered['herd_funds']         > 0]
            if excl_exits: filtered = filtered[filtered['funds_reducing']    == 0]

            st.caption(
                f"Showing **{len(filtered)}** stocks out of **{len(screener_df)}** "
                f"in the universe. Click any row to see full Institutional Intelligence."
            )

            # ── Main Screener Table ──────────────────────────────────────────
            display_cols = [
                'stock_name', 'sector', 'marketcapcat', 'total_funds_holding',
                'signal_score',
                'new_entry_funds', 'new_entry_avg_weight',
                'funds_accelerating', 'avg_recent_delta',
                'herd_funds', 'herd_avg_weight',
                'funds_reducing', 'avg_reduction_pct'
            ]
            display_df = filtered[[c for c in display_cols if c in filtered.columns]].copy()

            sc_event = st.dataframe(
                display_df,
                column_config={
                    "stock_name":           st.column_config.TextColumn("Stock"),
                    "sector":               st.column_config.TextColumn("Sector"),
                    "marketcapcat":         st.column_config.TextColumn("Market Cap"),
                    "total_funds_holding":  st.column_config.NumberColumn("Funds Holding"),
                    "signal_score":         st.column_config.ProgressColumn(
                                                "Signal Score", min_value=-1, max_value=3, format="%d"
                                            ),
                    "new_entry_funds":      st.column_config.NumberColumn("🆕 New Entry Funds"),
                    "new_entry_avg_weight": st.column_config.NumberColumn("Avg Entry Wt %", format="%.2f%%"),
                    "funds_accelerating":   st.column_config.NumberColumn("📈 Accel. Funds"),
                    "avg_recent_delta":     st.column_config.NumberColumn("Avg Δ Wt %", format="%.2f%%"),
                    "herd_funds":           st.column_config.NumberColumn("👥 Herd Funds"),
                    "herd_avg_weight":      st.column_config.NumberColumn("Herd Avg Wt %", format="%.2f%%"),
                    "funds_reducing":       st.column_config.NumberColumn("⚠️ Reducing Funds"),
                    "avg_reduction_pct":    st.column_config.NumberColumn("Avg Reduction %", format="%.2f%%"),
                },
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="df_screener"
            )

            # CSV export
            _render_export_button(display_df, "screener")

            # ── Drill-down: Institutional Intelligence ───────────────────────
            if sc_event.selection and sc_event.selection.get("rows"):
                selected_stock = filtered.iloc[sc_event.selection["rows"][0]]["stock_name"]
                st.divider()
                _render_stock_detail(engine, selected_stock, sc_lookback, sc_entry_thresh)
            else:
                st.caption("👆 Click any row above to view the full Institutional Intelligence card")

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
    intel = run_institutional_intelligence(engine, stock_name, lookback_months)
    if not intel:
        st.warning(f"Insufficient data to generate intelligence for {stock_name}")
        return

    st.title(f"🏛️ Institutional Intelligence: {stock_name}")
    st.caption(f"Analysis based on {lookback_months}-month window | Sector: {intel['sector']}")

    price_data = _cached_price_metrics(stock_name)
    if price_data:
        with st.container(border=True):
            st.markdown("### 📈 Price & Market Data")
            pc1, pc2, pc3, pc4, pc5, pc6, pc7 = st.columns(7)
            pc1.metric("LTP", f"₹{price_data.get('ltp', 'N/A')}")
            
            v1m = price_data.get('change_1m')
            pc2.metric("1M", f"{v1m}%" if v1m is not None else "N/A", delta=v1m if v1m is not None else None)
            v3m = price_data.get('change_3m')
            pc3.metric("3M", f"{v3m}%" if v3m is not None else "N/A", delta=v3m if v3m is not None else None)
            v6m = price_data.get('change_6m')
            pc4.metric("6M", f"{v6m}%" if v6m is not None else "N/A", delta=v6m if v6m is not None else None)
            vytd = price_data.get('change_ytd')
            pc5.metric("YTD", f"{vytd}%" if vytd is not None else "N/A", delta=vytd if vytd is not None else None)
            v1y = price_data.get('change_1y')
            pc6.metric("1Y", f"{v1y}%" if v1y is not None else "N/A", delta=v1y if v1y is not None else None)
            
            high = price_data.get('52w_high')
            low = price_data.get('52w_low')
            range_str = f"₹{low} — ₹{high}" if high and low else "Unavailable"
            pc7.metric("52W Range", range_str)

    # --- ROW 1: Thesis Card & Sentiment ---
    col_thesis, col_score = st.columns([3, 2])
    
    with col_thesis:
        with st.container(border=True):
            st.markdown("### 📜 Institutional Thesis")
            
            # What is happening?
            m = intel['metrics']
            happening = []
            if m['new_entrants'] > 0: happening.append(f"{m['new_entrants']} new funds entered")
            if m['is_accelerating']: happening.append("accumulation speed is accelerating")
            if m['is_herd_entry']: happening.append(f"herd entry detected ({m['herd_count']} funds)")
            if m['exits'] > 0: happening.append(f"{m['exits']} funds exited completely")
            if m['is_partial_exit']: happening.append("significant partial exits observed")
            
            narrative_happening = ". ".join(happening).capitalize() + "." if happening else "No significant institutional activity detected."
            st.write(f"**What is happening?**\n{narrative_happening}")
            
            # Who is buying/selling?
            b_col, s_col = st.columns(2)
            with b_col:
                st.write("**Top Buyers**")
                if intel['new_entrant_names']:
                    for n in intel['new_entrant_names']: st.caption(f"✅ {n}")
                else: st.caption("No new entrants")
            with s_col:
                st.write("**Top Sellers**")
                if intel['exit_names']:
                    for n in intel['exit_names']: st.caption(f"❌ {n}")
                else: st.caption("No complete exits")
            
            # Interpretation
            interpretation = ""
            if intel['sector_info']['is_rotation']:
                interpretation = f"Buying appears to be driven by sector rotation in **{intel['sector']}** rather than stock-specific events."
            else:
                interpretation = "The buying appears stock-specific, suggesting improving institutional conviction toward the company."
            st.write(f"**Interpretation:** {interpretation}")

    with col_score:
        with st.container(border=True):
            st.markdown("### 🚦 Institutional Sentiment")
            score = intel['sentiment_score']
            
            # Visual Gauge
            st.markdown(f"**Score: {score} / 100**")
            # Create a manual gauge-like progress bar
            color = "red"
            if score > 80: color = "green"; label = "Strong Bullish"
            elif score > 60: color = "blue"; label = "Bullish"
            elif score > 40: color = "gray"; label = "Neutral"
            elif score > 20: color = "orange"; label = "Bearish"
            else: color = "red"; label = "Very Bearish"
            
            st.progress(score/100)
            st.markdown(f"**Verdict:** <span style='color:{color}; font-weight:bold; font-size:20px;'>{label}</span>", unsafe_allow_html=True)
            st.caption(
                "_Score = 50 + min(70, positive signals) − min(70, negative signals). "
                "Positive: new entrants (+10 each, max 30), acceleration (+15), herd entry (+20, "
                "+10 bonus if >5 funds), sector rotation (+15), top holder buying (max +20). "
                "Negative: partial exit flag (−15), exits (−10 each, max −40), top holder selling (max −20)._"
            )
            
            st.divider()
            st.markdown("### 🔄 Market Phase")
            st.markdown(f"**Phase:** `{intel['phase']}`")
            st.progress(intel['confidence']/100)
            st.caption(f"Confidence: {intel['confidence']:.1f}%")
            st.caption(
                "_Phase inferred from combination of: new entrant count, exit count, acceleration "
                "status, and accumulation ratio thresholds. Confidence = accumulation ratio or its "
                "inverse, depending on phase direction._"
            )

    # --- ROW 2: Acc vs Dist & Probability ---
    col_acc, col_prob = st.columns(2)
    
    with col_acc:
        with st.container(border=True):
            st.markdown("### ⚖️ Accumulation vs Distribution")
            ar = intel['acc_ratio']
            dr = 100 - ar
            
            st.write(f"**Accumulation: {ar:.1f}%**")
            st.progress(ar/100)
            st.write(f"**Distribution: {dr:.1f}%**")
            st.progress(dr/100)
            
            if ar > 70: interp = "Strong Accumulation"
            elif ar > 50: interp = "Moderate Accumulation"
            elif ar > 40: interp = "Balanced"
            else: interp = "Distribution"
            st.info(f"Verdict: {interp}")
            st.caption(
                "_Accumulation % = total shares added ÷ (total shares added + total shares removed), "
                "across all funds holding this stock within the lookback window._"
            )

    with col_prob:
        with st.container(border=True):
            st.markdown("### 🎲 Probability Matrix")
            # Simplified probabilities based on sentiment score
            bull = min(95, max(5, score + (ar-50)/2))
            bear = min(95, max(5, (100-score) + (dr-50)/2))
            combined = bull + bear
            if combined > 95:
                bull = (bull / combined) * 95
                bear = (bear / combined) * 95
            
            neut = max(0, 100 - bull - bear)
            bull = round(bull, 1)
            bear = round(bear, 1)
            neut = round(neut, 1)
            st.caption(f"Bullish: {bull}%")
            st.progress(min(1.0, bull/100))
            st.caption(f"Neutral: {neut}%")
            st.progress(min(1.0, neut/100))
            st.caption(f"Bearish: {bear}%")
            st.progress(min(1.0, bear/100))
            st.caption(
                "_Bullish % ≈ sentiment score adjusted by accumulation ratio. "
                "Bearish % ≈ (100 − sentiment score) adjusted by distribution ratio. "
                "Derived from the same Institutional Sentiment Score above, not an independent calculation._"
            )

    # --- ROW 3: Research Summary ---
    with st.container(border=True):
        st.markdown("### 📝 Institutional Research Summary")
        
        # Behavior Classification (Feature 6)
        behaviours = []
        if intel['metrics']['new_entrants'] > 5: behaviours.append("Herd Entry")
        elif intel['metrics']['new_entrants'] > 2: behaviours.append("Coordinated Entry")
        elif intel['metrics']['new_entrants'] > 0: behaviours.append("Lone Buyer")
        if intel['sector_info']['is_rotation']: behaviours.append("Sector Rotation")
        if intel['metrics']['is_accelerating']: behaviours.append("Broad Accumulation")
        if intel['metrics']['is_partial_exit']: behaviours.append("Broad Distribution")

        summary = (
            f"{intel['metrics']['new_entrants']} funds entered {stock_name} "
            f"over the past {lookback_months} months against {intel['metrics']['exits']} exits, "
            f"producing an accumulation ratio of {intel['acc_ratio']:.0f}%. "
            f"Institutional sentiment scores at {intel['sentiment_score']}/100 ({label}), "
            f"with the stock currently in a {intel['phase']} phase. "
            f"{'Sector rotation across ' + intel['sector'] + ' peers supports the move.' if intel['sector_info']['is_rotation'] else 'Activity appears stock-specific rather than sector-driven.'}"
        )
        st.write(summary)

        with st.expander("🤖 AI Analysis (Groq)", expanded=False):
            if st.button("Generate AI Summary", key=f"groq_btn_{stock_name}"):
                with st.spinner("Generating AI research summary..."):
                    try:
                        from groq import Groq
                        import os
                        # Standard Streamlit approach: check secrets first (for Cloud), then env (for local)
                        api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
                        
                        if not api_key:
                            st.error("GROQ_API_KEY not found. Please set it in Streamlit Secrets or your .env file.")
                            st.stop()
                            
                        groq_client = Groq(api_key=api_key)
                        prompt = f"""
You are a senior institutional equity research analyst. Write a detailed, flowing analysis paragraph (150-200 words) about {stock_name} based on the following mutual fund holding data. Do not just list numbers - explain what they mean together and why an investor should care.

Data:
- Sector={intel['sector']}
- Phase={intel['phase']}
- Sentiment={intel['sentiment_score']}/100
- New Entrants={intel['metrics']['new_entrants']}
- Exits={intel['metrics']['exits']}
- Accumulation Ratio={intel['acc_ratio']:.1f}%
- Sector Rotation={intel['sector_info']['is_rotation']}
- Behaviour={' + '.join(behaviours) if behaviours else 'Passive Holding'}
"""
                        response = groq_client.chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=450
                        )
                        st.write(response.choices[0].message.content)
                    except Exception as e:
                        st.warning(f"Groq unavailable: {e}")
        
        st.markdown(f"**Current Behaviour:** `{' + '.join(behaviours) if behaviours else 'Passive Holding'}`")

    # --- ROW 4: Timeline & Heatmap ---
    col_time, col_heat = st.columns(2)
    
    with col_time:
        with st.container(border=True):
            st.markdown("### 📅 Timeline Narrative")
            for item in intel['timeline']:
                st.write(f"**{item['month']}**")
                st.caption(item['event'])

    with col_heat:
        with st.container(border=True):
            st.markdown("### 🌡️ Smart Money Heatmap (AMC)")
            heat_df = pd.DataFrame(intel['amc_stats'])
            if not heat_df.empty:
                st.dataframe(heat_df[['AMC', 'Buying Funds', 'Selling Funds', 'Net Flow', 'Signal']], use_container_width=True, hide_index=True)
            else:
                st.write("No AMC-level activity data available.")

    # --- ROW 5: Buyer Categories ---
    with st.container(border=True):
        st.markdown("### 👥 Institutional Player Profiles")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("🚀 **Aggressive Buyers**")
            if intel['categories']['aggressive']:
                for f in intel['categories']['aggressive']: st.caption(f)
            else: st.caption("None detected")
        with c2:
            st.write("🐢 **Quiet Accumulators**")
            if intel['categories']['quiet']:
                for f in intel['categories']['quiet']: st.caption(f)
            else: st.caption("None detected")
        with c3:
            st.write("🏃 **Exiting Funds**")
            if intel['categories']['exiting']:
                for f in intel['categories']['exiting']: st.caption(f)
            else: st.caption("None detected")

    st.divider()
    # --- EXISTING Trajectory Charts ---
    weight_pivot, shares_pivot, new_entrant_funds = engine.get_stock_detail_with_entrants(stock_name, lookback_months, threshold_pct)
    
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
