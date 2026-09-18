import pandas as pd, numpy as np, warnings; warnings.filterwarnings("ignore")
from lib import *
O="/mnt/user-data/outputs/bbg_dataset"
px=pd.read_parquet(f"{O}/prices_daily_v2.parquet").dropna(subset=["tri"])
mac=pd.read_parquet(f"{O}/macro_series.parquet").pivot(index="date",columns="series",values="value")
st=pd.read_csv(f"{O}/static_snapshot_v2.csv")
tri,close,mcap,dret=monthly_frames(px); ret=tri.pct_change(); fwd=ret.shift(-1)
# liquidity-tiered costs: half-spread by median daily turnover (HKD)
adv=px.set_index("date").groupby("ticker")["turnover"].resample("ME").median().unstack(0).reindex(tri.index)
adv=adv.reindex(columns=tri.columns)
def cost_tier(a):
    # HKD ADV -> one-way cost: stamp .1% + fees .012% + comm .03% + half-spread by tier
    hs=pd.Series(np.select([a>5e8,a>1e8,a>2e7],[0.0005,0.0010,0.0025],default=0.0050),index=a.index)
    return 0.001+0.00012+0.0003+hs
mom=tri.shift(1)/tri.shift(12)-1
res=[]
def run(sig,label,cols,tier=True):
    s=sig[cols] if cols is not None else sig
    Q=quintile_portfolio(s,fwd,min_n=20)
    if Q.empty: return
    Q=Q.loc["2017-01-31":"2026-08-31"]
    # average cost of the traded names, approximated by universe-median tier
    if tier:
        med=adv.reindex(Q.index).median(1)
        ow=cost_tier(med)
    else:
        ow=pd.Series(0.002,index=Q.index)
    ls=(Q.top-Q.bot)-2*ow*Q.to_top.fillna(1)-2*ow*Q.to_bot.fillna(1)-0.01/12
    lo=Q.top-2*ow*Q.to_top.fillna(1)
    for nm,x in [("L/S",ls),("long-only",lo)]:
        for per,(a,b) in {"IS":("2017-01-31","2021-12-31"),"OOS":("2022-01-31","2026-08-31"),"FULL":("2017-01-31","2026-08-31")}.items():
            r=stats_row(x.loc[a:b],f"{label} {nm}"); r["period"]=per; r["nstocks"]=len(s.columns); res.append(r)
hsi_only=[c for c in tri.columns if c in pd.read_csv(f"{O}/members_HSI.csv")["ticker"].tolist()]
run(mom,"Momentum HSI-95",hsi_only)
run(mom,"Momentum 197-stock",None)
R=pd.DataFrame(res)
piv=R.pivot_table(index="strategy",columns="period",values=["ann_ret","sharpe","t"])
piv=piv.reindex(columns=pd.MultiIndex.from_product([["ann_ret","sharpe","t"],["IS","OOS","FULL"]]))
print("== universe size effect (liquidity-tiered costs) ==")
print(piv.round(2).to_string())
print("\nuniverse: 197 tickers; monthly quintiles of ~39 vs ~19 before")
print("median ADV tiers (HKD):"); print(adv.median(1).resample("YE").median().round(-6).to_string())
R.to_csv(f"{O}/universe_size_comparison.csv",index=False)
