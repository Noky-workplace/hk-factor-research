import pandas as pd, numpy as np
O="/mnt/user-data/outputs/bbg_dataset"
px=pd.read_parquet(f"{O}/prices_daily.parquet").dropna(subset=["tri"])
mac=pd.read_parquet(f"{O}/macro_series.parquet")
m=px.set_index("date").groupby("ticker")["tri"].resample("ME").last().unstack(0)
ret=m.pct_change(); fwd=ret.shift(-1)
mom=m.shift(1)/m.shift(12)-1

def ls_series(sig,fwd,q=5):
    out=[]
    for d in sig.index:
        s=sig.loc[d].dropna()
        if d not in fwd.index or len(s)<30: continue
        r=fwd.loc[d].reindex(s.index).dropna(); s=s.reindex(r.index)
        if len(s)<30: continue
        rk=pd.qcut(s.rank(method="first"),q,labels=False)
        out.append((d,r[rk==q-1].mean(),r[rk==0].mean()))
    df=pd.DataFrame(out,columns=["date","top","bot"]).set_index("date")
    df["ls"]=df.top-df.bot; return df
base=ls_series(mom,fwd).loc["2017-01-31":"2026-08-31"]

# regime variables, all known at month-end t (applied to month t+1 return)
w=mac.pivot(index="date",columns="series",values="value")
vhsi=w["VHSI Index"].resample("ME").last()
hsi=w["HSI Index"].dropna()
hsi_m=hsi.resample("ME").last()
above200=(hsi>hsi.rolling(200).mean()).astype(float).resample("ME").last()
vhsi_hi=(vhsi>vhsi.rolling(24,min_periods=12).median())   # relative: above 2y median
dd=(hsi_m/hsi_m.cummax()-1)

def stats(x,label):
    a=x.mean()*12; v=x.std()*np.sqrt(12); t=x.mean()/x.std()*np.sqrt(len(x))
    mdd=((1+x).cumprod()/(1+x).cumprod().cummax()-1).min()
    worst=x.min()
    print(f"{label:38s} ret={a:6.1%}  vol={v:5.1%}  Sharpe={a/v:5.2f}  t={t:4.2f}  maxDD={mdd:6.1%}  worst m={worst:6.1%}")
    return dict(label=label,ret=a,vol=v,sharpe=a/v,t=t,mdd=mdd,worst=worst)

idx=base.index; rows=[]
print("== Momentum long-short, monthly, HSI 2017-2026 ==")
rows.append(stats(base.ls,"Unconditional"))
for thr in [20,25,30]:
    on=(vhsi.reindex(idx)<=thr).astype(float)
    rows.append(stats(base.ls*on,f"Off when VHSI > {thr}"))
on=(~vhsi_hi.reindex(idx)).astype(float); rows.append(stats(base.ls*on,"Off when VHSI > 2y median"))
on=above200.reindex(idx); rows.append(stats(base.ls*on,"Off when HSI < 200d MA"))
on=(dd.reindex(idx)>-0.15).astype(float); rows.append(stats(base.ls*on,"Off when HSI drawdown > 15%"))
# half-size instead of off
on=np.where(vhsi.reindex(idx)>25,0.5,1.0); rows.append(stats(base.ls*on,"Half size when VHSI > 25"))
# vol-target: scale by 15%/trailing 12m vol of the strategy
tv=base.ls.rolling(12).std().shift(1)*np.sqrt(12); sc=(0.15/tv).clip(0.25,2).fillna(1)
rows.append(stats(base.ls*sc,"Vol-target 15% (ex-ante)"))

print("\n== What happens in high-vol months? ==")
hi=vhsi.reindex(idx)>25
print(f"months VHSI>25: {hi.sum()} of {len(idx)}")
print(f"mom L/S avg monthly ret when VHSI<=25: {base.ls[~hi].mean():.2%}   when VHSI>25: {base.ls[hi].mean():.2%}")
print(f"top-quintile long-only when VHSI<=25: {base.top[~hi].mean():.2%}   >25: {base.top[hi].mean():.2%}")
print("\nWorst 5 momentum months:")
wm=base.ls.nsmallest(5)
for d,v in wm.items(): print(f"  return month {(d+pd.offsets.MonthEnd(1)).strftime('%Y-%m')}  {v:7.1%}   VHSI at prior month-end={vhsi.reindex(idx).loc[d]:.1f}   HSI>200d={bool(above200.reindex(idx).loc[d])}")

# cumulative for chart
cum=pd.DataFrame({"Unconditional":(1+base.ls).cumprod(),
                  "Off when VHSI>25":(1+base.ls*(vhsi.reindex(idx)<=25).astype(float)).cumprod(),
                  "Off when HSI<200dMA":(1+base.ls*above200.reindex(idx)).cumprod(),
                  "Vol-target 15%":(1+base.ls*sc).cumprod()})
y=cum.resample("YE").last().round(2); print("\n",y.T.to_string())
pd.DataFrame(rows).to_csv(f"{O}/momentum_regime_results.csv",index=False); cum.to_csv(f"{O}/momentum_regime_cumulative.csv")
