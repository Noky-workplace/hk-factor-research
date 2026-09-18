import pandas as pd, numpy as np
O="/mnt/user-data/outputs/bbg_dataset"
px=pd.read_parquet(f"{O}/prices_daily.parquet")
fund=pd.read_parquet(f"{O}/fundamentals_semiannual.parquet")

# monthly total-return index per stock
px=px.dropna(subset=["tri"])
m=px.set_index("date").groupby("ticker")["tri"].resample("ME").last().unstack(0)
ret=m.pct_change()                          # monthly total return
close_m=px.set_index("date").groupby("ticker")["close"].resample("ME").last().unstack(0)

# --- Momentum: 12-1 month ---
mom=m.shift(1)/m.shift(12)-1               # return from t-12 to t-1 (skip last month)

# --- Value: book/price, point-in-time (use latest fundamentals ANNOUNCED before month-end) ---
f=fund.dropna(subset=["bvps"]).sort_values("announce_date")
bp=pd.DataFrame(index=m.index,columns=m.columns,dtype=float)
for t,g in f.groupby("ticker"):
    if t not in bp.columns: continue
    s=g.set_index("announce_date")["bvps"]
    s=s[~s.index.duplicated(keep="last")]
    bp[t]=s.reindex(m.index,method="ffill")
bp=bp/close_m

def quintile_ls(signal, fwd_ret, q=5):
    out=[]
    for d in signal.index:
        s=signal.loc[d].dropna(); r=fwd_ret.loc[d] if d in fwd_ret.index else None
        if r is None or len(s)<30: continue
        r=r.reindex(s.index).dropna(); s=s.reindex(r.index)
        if len(s)<30: continue
        rk=pd.qcut(s.rank(method="first"),q,labels=False)
        top=r[rk==q-1].mean(); bot=r[rk==0].mean()
        out.append((d,top,bot,top-bot,r.mean()))
    return pd.DataFrame(out,columns=["date","top","bottom","long_short","universe"]).set_index("date")

fwd=ret.shift(-1)   # next month's return, aligned to signal date
res={}
for name,sig in [("Momentum 12-1",mom),("Value B/P",bp)]:
    r=quintile_ls(sig,fwd)
    r=r.loc["2017-01-31":"2026-08-31"]
    res[name]=r
    ann=r.long_short.mean()*12; vol=r.long_short.std()*np.sqrt(12)
    tstat=r.long_short.mean()/r.long_short.std()*np.sqrt(len(r))
    print(f"{name:14s} months={len(r):3d}  top={r.top.mean()*12:6.1%}/yr  bottom={r.bottom.mean()*12:6.1%}/yr  "
          f"long-short={ann:6.1%}/yr  vol={vol:5.1%}  Sharpe={ann/vol:4.2f}  t={tstat:4.2f}  hit={ (r.long_short>0).mean():.0%}")
    cum=(1+r[["top","bottom","long_short","universe"]]).cumprod()
    cum.to_csv(f"{O}/factor_{name.split()[0].lower()}_cumulative.csv")
    res[name+"_cum"]=cum

# print yearly cumulative long-short for chart
for name in ["Momentum 12-1","Value B/P"]:
    c=res[name+"_cum"]["long_short"]; y=c.resample("YE").last()
    print(name, [f"{d.year}:{v:.2f}" for d,v in y.items()])
u=res["Momentum 12-1_cum"]["universe"].resample("YE").last(); print("EW universe",[f"{d.year}:{v:.2f}" for d,v in u.items()])
