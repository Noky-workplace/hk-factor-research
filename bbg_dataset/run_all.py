import pandas as pd, numpy as np, warnings; warnings.filterwarnings("ignore")
from lib import *
px,fund,mac,st,dv=load()
tri,close,mcap,dret=monthly_frames(px)
ret=tri.pct_change(); fwd=ret.shift(-1)
hsi=mac["HSI Index"].dropna(); hsi_m=hsi.resample("ME").last(); hsi_r=hsi_m.pct_change(); hsi_fwd=hsi_r.shift(-1)
vhsi=mac["VHSI Index"].dropna().resample("ME").last()
sector=st.set_index("ticker")["GICS_SECTOR_NAME"].to_dict()
groups={}
for t,s in sector.items(): groups.setdefault(s,[]).append(t)
IS=("2017-01-31","2021-12-31"); OOS=("2022-01-31","2026-08-31"); FULL=("2017-01-31","2026-08-31")
results=[]; trials=[]     # every strategy variant evaluated counts as a trial
def record(x,label,family):
    for per,(a,b) in {"IS":IS,"OOS":OOS,"FULL":FULL}.items():
        r=stats_row(x.loc[a:b],label); r["period"]=per; r["family"]=family; results.append(r)
    trials.append(stats_row(x.loc[FULL[0]:FULL[1]],label)["sharpe"]/np.sqrt(12))

# ============ A. MOMENTUM: market-state filter + dynamic beta hedge ============
mom=tri.shift(1)/tri.shift(12)-1
M=quintile_portfolio(mom,fwd).loc[FULL[0]:FULL[1]]
ls_gross=M.top-M.bot
record(net(M.top-M.bot,M.to_top,M.to_bot),"MOM L/S plain","A")
record(net(M.top,M.to_top),"MOM long-only","A")
# market state: bear if trailing 24m HSI return < 0 (Daniel-Moskowitz)
bear=(hsi_m/hsi_m.shift(24)-1<0).reindex(M.index)
x=np.where(bear,M.top,M.top-M.bot); tob=np.where(bear,0,M.to_bot)
record(net(pd.Series(x,index=M.index),M.to_top,pd.Series(tob,index=M.index)),"MOM L/S, drop short leg in bear state","A")
# dynamic beta hedge: hedge each leg with HSI using trailing 12m beta (ex-ante)
def beta(series,mkt,win=12):
    return series.rolling(win).cov(mkt)/mkt.rolling(win).var()
b_top=beta(M.top,hsi_r.reindex(M.index)).shift(1); b_bot=beta(M.bot,hsi_r.reindex(M.index)).shift(1)
hf=hsi_fwd.reindex(M.index)  # NOTE: M rows are signal dates; M.top is next-month return, so hedge with next-month HSI
hedged_ls=(M.top-b_top*hf)-(M.bot-b_bot*hf)
record(net(hedged_ls,M.to_top,M.to_bot),"MOM L/S, beta-hedged (12m ex-ante beta)","A")
record(net(M.top-b_top*hf,M.to_top),"MOM long-only, beta-hedged","A")
# CTH (current price / 12m high) as alternative descriptor
hi12=close.rolling(12).max(); cth=(close/hi12).shift(1)
C=quintile_portfolio(cth,fwd).loc[FULL[0]:FULL[1]]
record(net(C.top-C.bot,C.to_top,C.to_bot),"CTH (px/12m high) L/S","A")
record(net(C.top,C.to_top),"CTH long-only","A")

# ============ B. VALUE composite, dividend yield, low-vol, quality (sector-neutral) ============
f=ttm(fund,"eps"); f=ttm(f,"net_income"); f=ttm(f,"cfo")
eps_ttm=pit_ffill(f,"eps_ttm",tri.index); bvps=pit_ffill(fund,"bvps",tri.index)
ni_ttm=pit_ffill(f,"net_income_ttm",tri.index); cfo_ttm=pit_ffill(f,"cfo_ttm",tri.index)
roe=pit_ffill(fund,"roe",tri.index); debt=pit_ffill(fund,"total_debt",tri.index); sh=pit_ffill(fund,"shares_out",tri.index)
cols=[c for c in tri.columns if c in eps_ttm.columns]
EP=(eps_ttm/close)[cols]; BP=(bvps/close)[cols]
# dividend yield: trailing 12m dividends by ex-date
dvp=dv.dropna(subset=["ex_date","amount"]).copy(); dvp["m"]=dvp.ex_date.dt.to_period("M").dt.to_timestamp("M")
dsum=dvp.groupby(["ticker","m"])["amount"].sum().unstack(0).reindex(tri.index).fillna(0)
DY=(dsum.rolling(12).sum()/close).reindex(columns=cols)
equity=(bvps*sh); LEV=(debt/equity)[cols]; ACC=((ni_ttm-cfo_ttm)/equity)[cols]
VOL=dret.rolling(252).std().resample("ME").last().reindex(tri.index)[cols]*np.sqrt(252)
def sig(df): return zscore_within(df.replace([np.inf,-np.inf],np.nan),groups)
value=(sig(EP)+sig(BP)+sig(DY))/3
quality=(sig(roe[cols])-sig(LEV)-sig(ACC))/3
for name,s,fam in [("VALUE composite (E/P,B/P,DY) sector-neutral",value,"B"),("B/P only sector-neutral",sig(BP),"B"),
                   ("DIVIDEND YIELD sector-neutral",sig(DY),"B"),("LOW-VOL (short = high vol)",-sig(VOL),"B"),
                   ("QUALITY (ROE, -lev, -accruals) sector-neutral",quality,"B"),
                   ("MULTI-FACTOR (mom+value+quality+lowvol)",(sig(mom[cols])+value+quality-sig(VOL))/4,"B")]:
    Q=quintile_portfolio(s,fwd).loc[FULL[0]:FULL[1]]
    record(net(Q.top-Q.bot,Q.to_top,Q.to_bot),name+" L/S",fam)
    record(net(Q.top,Q.to_top),name+" long-only",fam)

# ============ C. PEAD via SUE (seasonal random walk on semi-annual EPS) ============
fe=fund.dropna(subset=["eps"]).sort_values(["ticker","period_end"]).copy()
fe["d"]=fe.groupby("ticker")["eps"].diff(2)                      # vs same half last year
fe["sd"]=fe.groupby("ticker")["d"].transform(lambda s:s.shift(1).rolling(6,min_periods=4).std())
fe["sue"]=(fe["d"]/fe["sd"]).clip(-5,5)
fe=fe.dropna(subset=["sue"])
# monthly: use SUE announced within the last 4 months (else NaN)
SUE=pd.DataFrame(index=tri.index,columns=cols,dtype=float)
for t,g in fe.groupby("ticker"):
    if t not in cols: continue
    s=g.set_index("announce_date")["sue"].sort_index(); s=s[~s.index.duplicated(keep="last")]
    ff=s.reindex(tri.index,method="ffill")
    last_ann=pd.Series(s.index,index=s.index).reindex(tri.index,method="ffill")
    stale=(tri.index-last_ann)>pd.Timedelta(days=125)
    SUE[t]=ff.where(~stale)
P=quintile_portfolio(SUE,fwd,min_n=20).loc[FULL[0]:FULL[1]]
record(net(P.top-P.bot,P.to_top,P.to_bot),"PEAD (SUE) L/S","C")
record(net(P.top,P.to_top),"PEAD (SUE) long-only","C")
# event-study: market-adjusted cumulative return from day +2 to +60 after announcement, by SUE quintile
dtri=px.pivot_table(index="date",columns="ticker",values="tri"); hsi_d=hsi.reindex(dtri.index).ffill()
ev=[]
for _,r in fe.iterrows():
    t=r.ticker; d=pd.Timestamp(r.announce_date)
    if t not in dtri.columns: continue
    idx=dtri.index.searchsorted(d)
    if idx+61>=len(dtri) or idx<2: continue
    s=dtri[t].iloc[idx+1:idx+62]; m=hsi_d.iloc[idx+1:idx+62]
    if s.isna().any(): continue
    car=(s.iloc[-1]/s.iloc[0]-1)-(m.iloc[-1]/m.iloc[0]-1)
    d0=(dtri[t].iloc[idx+1]/dtri[t].iloc[idx-1]-1)-(hsi_d.iloc[idx+1]/hsi_d.iloc[idx-1]-1)
    ev.append((t,d,r.sue,d0,car))
EV=pd.DataFrame(ev,columns=["ticker","ann","sue","ann_ret_0_1","car_2_60"])
EV["q"]=pd.qcut(EV.sue.rank(method="first"),5,labels=False)
pead_tbl=EV.groupby("q")[["ann_ret_0_1","car_2_60"]].mean(); pead_n=len(EV)
ttest=stats.ttest_ind(EV[EV.q==4].car_2_60,EV[EV.q==0].car_2_60)

# ============ D. Seasonality net of cost ============
dhsi=hsi.pct_change().dropna()
dts=dhsi.index; mon=pd.Series(dts.to_period("M"),index=dts)
pos=mon.groupby(mon).cumcount(); cnt=mon.groupby(mon).transform("size")
tom=((pos<=2)|(pos==cnt-1))                      # last day + first 3 days
lny={2016:"2016-02-08",2017:"2017-01-28",2018:"2018-02-16",2019:"2019-02-05",2020:"2020-01-25",2021:"2021-02-12",
     2022:"2022-02-01",2023:"2023-01-22",2024:"2024-02-10",2025:"2025-01-29",2026:"2026-02-17"}
lny_mask=pd.Series(False,index=dts)
for y,d in lny.items():
    d=pd.Timestamp(d); before=dts[dts<d][-3:]; after=dts[dts>d][:1]
    lny_mask[before]=True; lny_mask[after]=True
def seas(mask,label,trades_per_year):
    r=dhsi[mask]; other=dhsi[~mask]
    ann_in=r.mean()*252; ann_out=other.mean()*252
    days=mask.sum()/ (len(dts)/252)
    gross=r.mean()*days; cost=trades_per_year*2*ONE_WAY_COST
    t=stats.ttest_ind(r,other).statistic
    return dict(effect=label,avg_daily_in=r.mean(),avg_daily_out=other.mean(),t=t,days_per_year=days,
                gross_ann=gross,cost_ann=cost,net_ann=gross-cost)
seas_tbl=pd.DataFrame([seas(tom,"Turn-of-month (last1+first3)",12),seas(lny_mask,"Lunar NY (3 before,1 after)",1)])

# ============ E. Deflated Sharpe on the best net strategy ============
R=pd.DataFrame(results); full=R[R.period=="FULL"].sort_values("sharpe",ascending=False)
best=full.iloc[0]; n_trials=len(trials)+30   # +30 earlier variants tested in this project
sr_var=np.var(trials)
dsr,emax=deflated_sharpe(best["sharpe"]/np.sqrt(12),best["n"],best["skew"],best["kurt"],n_trials,sr_var)

# ============ output ============
R.to_csv(f"{O}/phase2_results.csv",index=False); EV.to_csv(f"{O}/phase2_pead_events.csv",index=False); seas_tbl.to_csv(f"{O}/phase2_seasonality.csv",index=False)
pd.set_option("display.width",200)
def show(fam):
    sub=R[R.family==fam].pivot(index="strategy",columns="period",values=["ann_ret","sharpe","maxdd"])
    sub=sub.reindex(columns=pd.MultiIndex.from_product([["ann_ret","sharpe","maxdd"],["IS","OOS","FULL"]]))
    print(sub.round(2).to_string())
print("\n### A. MOMENTUM (net of costs) ###"); show("A")
print("\n### B. VALUE / DIVIDEND / LOW-VOL / QUALITY, sector-neutral (net) ###"); show("B")
print("\n### C. PEAD (net) ###"); show("C")
print(f"\nPEAD event study ({pead_n} announcements): mean market-adj return by SUE quintile (0=most negative surprise)")
print((pead_tbl*100).round(2).to_string()); print(f"top-bottom CAR(+2,+60) t-stat = {ttest.statistic:.2f}")
print("\n### D. SEASONALITY (HSI, gross vs net of 0.2% one-way) ###"); print(seas_tbl.round(4).to_string())
print(f"\n### E. DEFLATED SHARPE ###\nbest FULL-sample strategy: {best.strategy}  annual Sharpe={best["sharpe"]:.2f}")
print(f"trials counted={n_trials}, Sharpe variance across trials (monthly)={sr_var:.4f}, expected max monthly SR under H0={emax:.3f} (annualised {emax*np.sqrt(12):.2f})")
print(f"Deflated Sharpe probability = {dsr:.3f}  ({'PASSES' if dsr>0.95 else 'FAILS'} the 95% bar)")
