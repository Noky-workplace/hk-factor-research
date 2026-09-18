import pandas as pd, numpy as np
O="/mnt/user-data/outputs/bbg_dataset"
px=pd.read_parquet(f"{O}/prices_daily.parquet").dropna(subset=["tri"])
mac=pd.read_parquet(f"{O}/macro_series.parquet")
m=px.set_index("date").groupby("ticker")["tri"].resample("ME").last().unstack(0)
ret=m.pct_change(); fwd=ret.shift(-1); mom=m.shift(1)/m.shift(12)-1
w=mac.pivot(index="date",columns="series",values="value")
vhsi=w["VHSI Index"].dropna().resample("ME").last()
hsi_m=w["HSI Index"].dropna().resample("ME").last(); hsi_r=hsi_m.pct_change().shift(-1)

def legs(sig,fwd,q=5):
    out=[]
    for d in sig.index:
        s=sig.loc[d].dropna()
        if d not in fwd.index or len(s)<30: continue
        r=fwd.loc[d].reindex(s.index).dropna(); s=s.reindex(r.index)
        if len(s)<30: continue
        rk=pd.qcut(s.rank(method="first"),q,labels=False)
        out.append((d,r[rk==q-1].mean(),r[rk==0].mean(),r.mean()))
    return pd.DataFrame(out,columns=["date","top","bot","univ"]).set_index("date")
L=legs(mom,fwd).loc["2017-01-31":"2026-08-31"]
v=vhsi.reindex(L.index); hi=v>25

# candidate strategies (all rules fixed BEFORE looking at the holdout)
S=pd.DataFrame(index=L.index)
S["LS unconditional"]=L.top-L.bot
S["LS half when VHSI>25"]=(L.top-L.bot)*np.where(hi,0.5,1.0)
S["Long-only top quintile"]=L.top
S["LS calm / long-only stressed"]=np.where(hi,L.top,L.top-L.bot)
S["LS calm / long-only stressed (hedged)"]=np.where(hi,L.top-L.univ,L.top-L.bot)  # long top vs universe when stressed = market-neutral-ish
S["HSI buy&hold"]=hsi_r.reindex(L.index)

# HK costs: stamp 0.1% each side + ~0.1% commission/slippage -> ~0.2% one-way. Quintile turnover ~ 40%/month per leg.
COST=0.002; turnover={"LS unconditional":0.8,"LS half when VHSI>25":0.8,"Long-only top quintile":0.4,
                      "LS calm / long-only stressed":0.8,"LS calm / long-only stressed (hedged)":0.8,"HSI buy&hold":0.0}
def st(x):
    x=x.dropna(); a=x.mean()*12; vol=x.std()*np.sqrt(12); t=x.mean()/x.std()*np.sqrt(len(x))
    c=(1+x).cumprod(); mdd=(c/c.cummax()-1).min()
    return a,vol,a/vol,t,mdd,x.min()
for label,(a,b) in {"IN-SAMPLE 2017-2021":("2017-01-31","2021-12-31"),"OUT-OF-SAMPLE 2022-2026":("2022-01-31","2026-08-31"),"FULL":("2017-01-31","2026-08-31")}.items():
    print(f"\n== {label} ==   (net of ~0.2% one-way HK costs)")
    print(f"{'strategy':40s} {'ret':>7s} {'vol':>6s} {'Sharpe':>7s} {'t':>5s} {'maxDD':>7s} {'worst':>7s}")
    for c in S.columns:
        x=S[c].loc[a:b]-COST*turnover[c]
        r=st(x); print(f"{c:40s} {r[0]:7.1%} {r[1]:6.1%} {r[2]:7.2f} {r[3]:5.2f} {r[4]:7.1%} {r[5]:7.1%}")
print(f"\nstressed months (VHSI>25): in-sample {hi.loc[:'2021-12-31'].sum()}, out-of-sample {hi.loc['2022-01-31':].sum()}")
cum=(1+S[["LS unconditional","LS calm / long-only stressed","Long-only top quintile","HSI buy&hold"]]-COST*pd.Series(turnover)[["LS unconditional","LS calm / long-only stressed","Long-only top quintile","HSI buy&hold"]]).cumprod()
print(cum.resample("YE").last().round(2).T.to_string())
S.to_csv(f"{O}/split_sample_strategies.csv")
