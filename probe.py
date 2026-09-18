"""Probe: find the right akshare functions in YOUR installed version + inspect the HKEXnews form.
Run:  python probe.py           (inside the venv, from ~/hk-quant)
Paste the whole output back into the chat.
"""
import inspect, sys
print("python", sys.version.split()[0])
try:
    import akshare as ak
    print("akshare", ak.__version__)
except Exception as e:
    sys.exit(f"akshare import failed: {e}")

KEYS = ["ggt","hsgt","hk_hold","hold_stock","shareholding","ccass","south","hk_ggt","short","sell","hk_"]
names = [n for n in dir(ak) if not n.startswith("_")]

def show(title, hits):
    print(f"\n===== {title} ({len(hits)}) =====")
    for n in hits:
        try:
            sig = str(inspect.signature(getattr(ak, n)))
        except Exception:
            sig = "(?)"
        doc = (getattr(ak, n).__doc__ or "").strip().splitlines()
        first = doc[0][:110] if doc else ""
        print(f"{n}{sig}\n    {first}")

show("Stock Connect / 港股通 / 沪深港通", [n for n in names if any(k in n for k in ["ggt","hsgt"])])
show("CCASS / shareholding / 持股", [n for n in names if any(k in n for k in ["ccass","hold","shareholding"])])
show("HK short selling / 沽空", [n for n in names if "hk" in n and any(k in n for k in ["short","sell","sg"])])
show("Other HK stock funcs", [n for n in names if n.startswith("stock_hk_")][:60])

# --- live smoke tests on the most likely candidates ---
print("\n===== SMOKE TESTS =====")
def try_call(label, fn, **kw):
    try:
        df = fn(**kw)
        print(f"OK  {label}: shape={getattr(df,'shape',None)} cols={list(getattr(df,'columns',[]))[:8]}")
        try:
            print("    head:", df.head(2).to_dict("records"))
        except Exception:
            pass
    except Exception as e:
        print(f"ERR {label}: {type(e).__name__}: {str(e)[:120]}")

for nm, kwargs in [
    ("stock_hk_ggt_components_em", {}),
    ("stock_hsgt_hist_em", {"symbol": "港股通sh"}),
    ("stock_hsgt_fund_flow_summary_em", {}),
    ("stock_hsgt_hold_stock_em", {"market": "北向持股", "indicator": "今日排行"}),
    ("stock_hk_hot_rank_em", {}),
]:
    fn = getattr(ak, nm, None)
    if fn is None:
        print(f"--- {nm}: not present in this version")
    else:
        try_call(nm, fn, **kwargs)

# --- HKEXnews southbound shareholding form: dump the field names we must POST ---
print("\n===== HKEXNEWS FORM FIELDS =====")
try:
    import requests, re
    url = "https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=hk"
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    print("status", r.status_code, "len", len(r.text))
    for m in re.finditer(r'<(input|select)[^>]*name="([^"]+)"[^>]*>', r.text):
        tag, name = m.group(1), m.group(2)
        val = re.search(r'value="([^"]{0,40})"', m.group(0))
        print(f"  {tag:6s} {name:45s} {val.group(1) if val else ''}")
except Exception as e:
    print("HKEXnews probe failed:", type(e).__name__, str(e)[:160])
