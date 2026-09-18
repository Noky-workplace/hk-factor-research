import pandas as pd, numpy as np, warnings; warnings.filterwarnings("ignore")
from lib import *
px,fund,mac,st,dv=load()
M=pd.read_parquet(f"{O}/index_membership_history.parquet")
tri,close,mcap,dret=monthly_frames(px)
ret=tri.pct_change(); fwd=ret.shift(-1)
hsi=mac["HSI Index"].dropna(); hsi_m=hsi.resample("ME").last(); hsi_r=hsi_m.pct_change()

hsi_mem=M[M["index"]=="HSI"]
have=set(tri.columns)
cov=hsi_mem.groupby("asof")["ticker"].apply(lambda s:pd.Series({"n":len(s),"have":len(set(s)&have)}))
cov=hsi_mem.groupby("asof").agg(n=("ticker","size"),have=("ticker",lambda s:len(set(s)&have)))
print("== price coverage of historical HSI members ==")
print(cov.iloc[::8].assign(pct=lambda d:(d.have/d.n).round(2)).to_string())
print(f"\nhistorical members with NO price data: {len(set(hsi_mem["ticker"])-have)} of {hsi_mem["ticker"].nunique()}")
print("missing (these are the delisted/removed names):",sorted(set(hsi_mem["ticker"])-have)[:15])

# membership mask: a stock is in the universe from each asof until the next
asofs=sorted(hsi_mem["asof"].unique())
mask=pd.DataFrame(False,index=tri.index,columns=tri.columns)
for i,a in enumerate(asofs):
    end=asofs[i+1] if i+1<len(asofs) else tri.index.max()+pd.Timedelta(days=1)
    names=[t for t in hsi_mem[hsi_mem["asof"]==a].ticker if t in mask.columns]
    rows=(mask.index>=a)&(mask.index<end)
    mask.loc[rows,names]=True
print(f"\nuniverse size (PIT, price-available): mean {mask.sum(1).loc['2017':].mean():.0f}, min {mask.sum(1).loc['2017':].min()}, max {mask.sum(1).loc['2017':].max()}")

mom=tri.shift(1)/tri.shift(12)-1
res=[]
def run(sig,label,pit):
    s=sig.where(mask) if pit else sig
    Q=quintile_portfolio(s,fwd,min_n=20).loc["2017-01-31":"2026-08-31"]
    for nm,x,tl,ts in [("L/S",Q.top-Q.bot,Q.to_top,Q.to_bot),("long-only",Q.top,Q.to_top,None)]:
        r=net(x,tl,ts)
        for per,(a,b) in {"IS":("2017-01-31","2021-12-31"),"OOS":("2022-01-31","2026-08-31"),"FULL":("2017-01-31","2026-08-31")}.items():
            row=stats_row(r.loc[a:b],f"{label} {nm}"); row["period"]=per; row["universe"]="PIT" if pit else "survivor"
            res.append(row)
for pit in [False,True]:
    run(mom,"Momentum 12-1",pit)
R=pd.DataFrame(res)
piv=R.pivot_table(index=["strategy","universe"],columns="period",values=["ann_ret","sharpe","maxdd"])
piv=piv.reindex(columns=pd.MultiIndex.from_product([["ann_ret","sharpe","maxdd"],["IS","OOS","FULL"]]))
print("\n== MOMENTUM: survivor universe vs point-in-time universe (net of costs) ==")
print(piv.round(2).to_string())
R.to_csv(f"{O}/survivorship_comparison.csv",index=False)
