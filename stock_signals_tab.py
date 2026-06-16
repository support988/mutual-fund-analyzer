import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from stock_activity_engine import StockActivityEngine
from price_data_fetcher import get_price_metrics
from groq import Groq

groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

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
    intel = engine.get_institutional_intelligence(stock_name, lookback_months)
    if not intel:
        st.warning(f"Insufficient data to generate intelligence for {stock_name}")
        return

    st.title(f"🏛️ Institutional Intelligence: {stock_name}")
    st.caption(f"Analysis based on {lookback_months}-month window | Sector: {intel['sector']}")

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
            
            st.divider()
            st.markdown("### 🔄 Market Phase")
            st.markdown(f"**Phase:** `{intel['phase']}`")
            st.progress(intel['confidence']/100)
            st.caption(f"Confidence: {intel['confidence']:.1f}%")

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
            neut = 100 - bull - bear
            
            st.caption(f"Bullish: {bull:.1f}%")
            st.progress(bull/100)
            st.caption(f"Neutral: {neut:.1f}%")
            st.progress(neut/100)
            st.caption(f"Bearish: {bear:.1f}%")
            st.progress(bear/100)

    # --- ROW 3: Research Summary ---
    with st.container(border=True):
        st.markdown("### 📝 Institutional Research Summary")
        summary_template = f"""
        Institutional participation in **{stock_name}** appears to be {label.lower()}. 
        Fresh entries are { 'emerging' if intel['metrics']['new_entrants'] > 0 else 'absent' } 
        while selling pressure remains { 'significant' if intel['metrics']['exits'] > 0 else 'fragmented' }. 
        Sector participation indicates that the movement may be { 'part of a broader rotation' if intel['sector_info']['is_rotation'] else 'stock-specific' } into **{intel['sector']}**. 
        Overall, the stock appears to be in a **{intel['phase']}** phase. 
        Sustained additions over the coming months will be critical for a trend reversal or continuation.
        """
        
        # Behavior Classification (Feature 6)
        behaviours = []
        if intel['metrics']['new_entrants'] > 5: behaviours.append("Herd Entry")
        elif intel['metrics']['new_entrants'] > 2: behaviours.append("Coordinated Entry")
        elif intel['metrics']['new_entrants'] > 0: behaviours.append("Lone Buyer")
        if intel['sector_info']['is_rotation']: behaviours.append("Sector Rotation")
        if intel['metrics']['is_accelerating']: behaviours.append("Broad Accumulation")
        if intel['metrics']['is_partial_exit']: behaviours.append("Broad Distribution")

        with st.spinner("Generating research summary..."):
            try:
                prompt = f"""Generate a 3-sentence institutional research summary for {stock_name}.
Data: Sector={intel['sector']}, Phase={intel['phase']}, 
Sentiment={intel['sentiment_score']}/100, 
New Entrants={intel['metrics']['new_entrants']}, 
Exits={intel['metrics']['exits']},
Accumulation Ratio={intel['acc_ratio']:.1f}%,
Sector Rotation={intel['sector_info']['is_rotation']},
Behaviour={' + '.join(behaviours) if behaviours else 'Passive Holding'}.
Write in the style of a sell-side equity research note. Be specific, use the numbers. No filler phrases."""

                response = groq_client.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200
                )
                st.write(response.choices[0].message.content)
            except Exception as e:
                st.write(summary_template)
                st.caption(f"(Groq unavailable: {e})")
        
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
    weight_pivot, shares_pivot, _ = engine.get_stock_detail_with_entrants(stock_name, lookback_months, threshold_pct)
    
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
