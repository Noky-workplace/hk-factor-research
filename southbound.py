"""
Scrape per-stock Stock Connect SOUTHBOUND shareholding from HKEXnews (official source).
Only ~12 months are available online; older history needs a written request to HKEX.

Usage:
    python southbound.py --probe 2026-09-17     # inspect one date, prints tables found
    python southbound.py                        # scrape last 12 months into ./free_data/
    python southbound.py --start 2026-01-01 --end 2026-09-17

Writes free_data/southbound/YYYY-MM-DD.csv (resumable: existing dates are skipped)
then free_data/southbound_holdings.parquet combining them all.
"""
import argparse, os, re, sys, time, random
import pandas as pd, requests
from io import StringIO

URL = "https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=hk"
OUT = "free_data/southbound"
HDRS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": URL}

def hidden_fields(html):
    out = {}
    for name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION", "today"]:
        m = re.search(rf'name="{name}"[^>]*value="([^"]*)"', html)
        if m: out[name] = m.group(1)
    return out

def fetch(session, date):
    """date: datetime.date -> raw html for that shareholding date"""
    r = session.get(URL, headers=HDRS, timeout=45); r.raise_for_status()
    f = hidden_fields(r.text)
    payload = {**f,
               "__EVENTTARGET": "btnSearch",
               "__EVENTARGUMENT": "",
               "sortBy": "stockcode",
               "sortDirection": "asc",
               "txtShareholdingDate": date.strftime("%Y/%m/%d"),
               "originalShareholdingDate": date.strftime("%Y/%m/%d"),
               "alertMsg": ""}
    r2 = session.post(URL, data=payload, headers=HDRS, timeout=60); r2.raise_for_status()
    return r2.text

def response_date(html):
    m = re.search(r'name="txtShareholdingDate"[^>]*value="(\d{4}/\d{2}/\d{2})"', html)
    return m.group(1) if m else None

def parse(html, date):
    """HKEXnews renders a table with stock code / name / shareholding / % of issued shares."""
    rd = response_date(html)
    if rd and rd != date.strftime("%Y/%m/%d"):
        raise RuntimeError(f"server returned {rd}, asked for {date:%Y/%m/%d} (holiday, or POST ignored)")
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        tables = []
    best = None
    for t in tables:
        if t.shape[0] > 50 and t.shape[1] >= 3:
            if best is None or t.shape[0] > best.shape[0]: best = t
    if best is None: return None
    df = best.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    # normalise: find the code / shareholding / percent columns by content
    def pick(pats):
        for c in df.columns:
            if any(p in c.lower() for p in pats): return c
        return None
    c_code = pick(["stock code", "code", "代号"])
    c_name = pick(["stock name", "name", "名称"])
    c_hold = pick(["shareholding", "持股"])
    c_pct  = pick(["% of", "percent", "百分比"])
    keep = {k: v for k, v in {"code": c_code, "name": c_name, "shareholding": c_hold, "pct": c_pct}.items() if v}
    if "code" not in keep or "shareholding" not in keep: return None
    out = df[[keep[k] for k in keep]].copy(); out.columns = list(keep)
    # cells look like "Stock Code:  1" / "Shareholding in CCASS: 66,510,871" / "...: 1.72%"
    out["code"] = out["code"].astype(str).str.extract(r"(\d+)\s*$")[0].str.zfill(5)
    if "name" in out: out["name"] = out["name"].astype(str).str.replace(r"^\s*Name:\s*", "", regex=True).str.strip()
    out["shareholding"] = pd.to_numeric(out["shareholding"].astype(str).str.extract(r"([\d,]+)\s*$")[0].str.replace(",", ""), errors="coerce")
    if "pct" in out: out["pct"] = pd.to_numeric(out["pct"].astype(str).str.extract(r"([\d.]+)\s*%?\s*$")[0], errors="coerce")
    out = out.dropna(subset=["code", "shareholding"])
    out["date"] = pd.Timestamp(date)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe"); ap.add_argument("--start"); ap.add_argument("--end")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    s = requests.Session()

    if a.probe:
        d = pd.Timestamp(a.probe).date()
        html = fetch(s, d)
        print("html len", len(html), "| server date:", response_date(html), "| requested:", d)
        try: tables = pd.read_html(StringIO(html))
        except ValueError: tables = []
        print("tables found:", len(tables))
        for i, t in enumerate(tables):
            print(f"  [{i}] shape={t.shape} cols={list(t.columns)[:6]}")
            if t.shape[0] > 10: print(t.head(3).to_string()[:600])
        df = parse(html, d)
        print("\nPARSED:", None if df is None else df.shape)
        if df is not None: print(df.head(8).to_string())
        return

    end = pd.Timestamp(a.end).date() if a.end else pd.Timestamp.today().date()
    start = pd.Timestamp(a.start).date() if a.start else (pd.Timestamp(end) - pd.DateOffset(months=12)).date()
    days = pd.bdate_range(start, end)
    print(f"{len(days)} business days {start} → {end}")
    ok = fail = skip = 0
    for d in days:
        p = f"{OUT}/{d.date()}.csv"
        if os.path.exists(p): skip += 1; continue
        try:
            df = parse(fetch(s, d.date()), d.date())
            if df is None or len(df) < 50:
                fail += 1; print(f"  {d.date()} no data (holiday?)")
            else:
                df.to_csv(p, index=False); ok += 1
                if ok % 20 == 0: print(f"  {d.date()} ok ({ok} saved)")
        except Exception as e:
            fail += 1; print(f"  {d.date()} ERR {type(e).__name__}: {str(e)[:90]}")
        time.sleep(random.uniform(1.0, 2.0))       # be polite to HKEX
    print(f"done: {ok} saved, {skip} already had, {fail} empty/failed")

    files = sorted(f for f in os.listdir(OUT) if f.endswith(".csv"))
    if files:
        all_df = pd.concat([pd.read_csv(f"{OUT}/{f}", parse_dates=["date"]) for f in files])
        all_df.to_parquet("free_data/southbound_holdings.parquet", index=False)
        print("combined:", all_df.shape, "→ free_data/southbound_holdings.parquet")

if __name__ == "__main__":
    main()
