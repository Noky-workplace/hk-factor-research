"""Aggregate Stock Connect flow history via akshare (northbound + southbound daily net flow).
The valid `symbol` keys change between akshare versions, so we discover them, then fetch.
Usage:  python flows.py
"""
import os, pandas as pd, akshare as ak
os.makedirs("free_data", exist_ok=True)
CANDIDATES = ["南向资金", "北向资金", "港股通sh", "港股通sz", "沪股通", "深股通",
              "港股通(沪)", "港股通(深)", "沪深港通", "南下资金"]
got = {}
for sym in CANDIDATES:
    try:
        df = ak.stock_hsgt_hist_em(symbol=sym)
        print(f"OK  {sym}: {df.shape} {list(df.columns)[:6]}")
        got[sym] = df
    except KeyError:
        pass                                    # not a valid key in this version
    except Exception as e:
        print(f"ERR {sym}: {type(e).__name__}: {str(e)[:80]}")
if not got:
    # last resort: read the symbol map straight out of the installed source
    import inspect, re
    src = inspect.getsource(ak.stock_hsgt_hist_em)
    print("\nNo candidate worked. Valid keys appear to be:")
    print(set(re.findall(r'"([^"]{2,12})":\s*"', src)))
else:
    for sym, df in got.items():
        name = {"南向资金": "southbound", "北向资金": "northbound"}.get(sym, sym)
        df.to_parquet(f"free_data/flow_{name}.parquet", index=False)
        print("saved", name, df.shape)
# daily market summary (works reliably; southbound rows are 资金方向 == 南向)
try:
    s = ak.stock_hsgt_fund_flow_summary_em()
    s.to_parquet("free_data/flow_summary_today.parquet", index=False); print("saved flow_summary_today", s.shape)
except Exception as e:
    print("summary failed:", e)
