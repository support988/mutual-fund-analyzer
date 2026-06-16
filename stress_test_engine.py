
import pandas as pd
from stock_activity_engine import StockActivityEngine
import os

def stress_test():
    # Initialize engine
    holdings_path = "downloads/holdings"
    if not os.path.exists(holdings_path):
        print(f"Error: Path {holdings_path} not found.")
        return

    engine = StockActivityEngine(holdings_path)
    print("Loading data...")
    engine.load_all()
    
    if engine.master_df.empty:
        print("Master DF is empty. Stress test cannot proceed with real data.")
        return

    print("\n--- Testing Analytical Methods ---")
    
    tests = [
        ("New Entries (Normal)", lambda: engine.get_new_entries(threshold_pct=1.0, lookback_months=3)),
        ("New Entries (Extreme Threshold)", lambda: engine.get_new_entries(threshold_pct=10.0, lookback_months=12)),
        ("New Entries (Zero Threshold)", lambda: engine.get_new_entries(threshold_pct=0.0, lookback_months=1)),
        
        ("Buildup Accel (Normal)", lambda: engine.get_buildup_acceleration(min_funds=3, lookback_months=3)),
        ("Buildup Accel (High Lookback)", lambda: engine.get_buildup_acceleration(min_funds=1, lookback_months=12)),
        ("Buildup Accel (Large Min Funds)", lambda: engine.get_buildup_acceleration(min_funds=50, lookback_months=3)),
        
        ("Partial Exits (Normal)", lambda: engine.get_partial_exits(reduction_threshold_pct=50.0, lookback_months=5, min_funds=2)),
        ("Partial Exits (Aggressive)", lambda: engine.get_partial_exits(reduction_threshold_pct=10.0, lookback_months=12, min_funds=1)),
        
        ("Herd Entries (Normal)", lambda: engine.get_herd_entries(min_funds=5, lookback_months=3)),
        ("Herd Entries (Small Window)", lambda: engine.get_herd_entries(min_funds=1, lookback_months=1)),
    ]

    for name, func in tests:
        try:
            res = func()
            print(f"[PASS] {name}: Found {len(res)} rows")
        except Exception as e:
            print(f"[FAIL] {name}: {e}")

    print("\n--- Testing Detail Methods ---")
    sample_stock = engine.master_df['stock_name'].iloc[0]
    print(f"Testing detail for: {sample_stock}")
    
    try:
        w, s = engine.get_stock_detail(sample_stock)
        print(f"[PASS] get_stock_detail: {w.shape}")
    except Exception as e:
        print(f"[FAIL] get_stock_detail: {e}")

    try:
        w, s, ent = engine.get_stock_detail_with_entrants(sample_stock)
        print(f"[PASS] get_stock_detail_with_entrants: {len(ent)} entrants")
    except Exception as e:
        print(f"[FAIL] get_stock_detail_with_entrants: {e}")

    try:
        sector_res = engine.get_sector_peers_activity(sample_stock)
        print(f"[PASS] get_sector_peers_activity: {sector_res['sector']}")
    except Exception as e:
        print(f"[FAIL] get_sector_peers_activity: {e}")

if __name__ == "__main__":
    stress_test()
