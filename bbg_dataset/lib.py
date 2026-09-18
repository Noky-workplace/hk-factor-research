"""Shared research library: point-in-time panel, portfolio engine with real turnover + HK costs, DSR."""
import pandas as pd, numpy as np
from scipy import stats
O="/mnt/user-data/outputs/bbg_dataset"
ONE_WAY_COST=0.002       # stamp 0.1% + fees 0.012% + commission 0.03% + half-spread ~0.05% (liquid HSI names)
BORROW_ANNUAL=0.01       # 1%/yr generic borrow on short leg

def load():
    px=pd.read_parquet(f"{O}/prices_daily.parquet").dropna(subset=["tri"])
    fund=pd.read_parquet(f"{O}/fundamentals_semiannual.parquet")
    mac=pd.read_parquet(f"{O}/macro_series.parquet").pivot(index="date",columns="series",values="value")
    st=pd.read_csv(f"{O}/static_snapshot.csv")
    dv=pd.read_csv(f"{O}/dividends.csv",parse_dates=["declared_date","ex_date","pay_date"])
    return px,fund,mac,st,dv

def monthly_frames(px):
    p=px.set_index("date")
    tri=p.groupby("ticker")["tri"].resample("ME").last().unstack(0)
    close=p.groupby("ticker")["close"].resample("ME").last().unstack(0)
    mcap=p.groupby("ticker")["mktcap"].resample("ME").last().unstack(0)
    dret=p.pivot_table(index="date",columns="ticker",values="tri").pct_change()
    return tri,close,mcap,dret

def pit_ffill(fund,col,index,key="announce_date"):
    """Latest value of `col` announced on or before each month-end (point-in-time)."""
    out=pd.DataFrame(index=index,columns=sorted(fund.ticker.unique()),dtype=float)
    f=fund.dropna(subset=[col]).sort_values(key)
    for t,g in f.groupby("ticker"):
        s=g.set_index(key)[col].sort_index(); s=s[~s.index.duplicated(keep="last")]
        out[t]=s.reindex(index,method="ffill")
    return out

def ttm(fund,col):
    """Trailing-12m sum of a semi-annual flow, keyed by announce_date."""
    f=fund.sort_values(["ticker","period_end"]).copy()
    f[col+"_ttm"]=f.groupby("ticker")[col].transform(lambda s:s.rolling(2).sum())
    return f

def zscore_within(df,groups=None):
    """Cross-sectional z-score each row; optionally within sector groups."""
    if groups is None:
        return df.sub(df.mean(1),axis=0).div(df.std(1),axis=0)
    out=df.copy()*np.nan
    for g,cols in groups.items():
        cols=[c for c in cols if c in df.columns]
        if len(cols)<3: continue
        sub=df[cols]; out[cols]=sub.sub(sub.mean(1),axis=0).div(sub.std(1),axis=0)
    return out

def quintile_portfolio(signal,fwd_ret,q=5,min_n=30):
    """Returns DataFrame with top/bottom/univ monthly returns and actual weights for turnover."""
    recs=[]; w_top={}; w_bot={}
    for d in signal.index:
        s=signal.loc[d].dropna()
        if d not in fwd_ret.index or len(s)<min_n: continue
        r=fwd_ret.loc[d].reindex(s.index).dropna(); s=s.reindex(r.index)
        if len(s)<min_n: continue
        rk=pd.qcut(s.rank(method="first"),q,labels=False)
        top=r.index[rk==q-1]; bot=r.index[rk==0]
        w_top[d]=pd.Series(1/len(top),index=top); w_bot[d]=pd.Series(1/len(bot),index=bot)
        recs.append((d,r[top].mean(),r[bot].mean(),r.mean()))
    df=pd.DataFrame(recs,columns=["date","top","bot","univ"]).set_index("date")
    df["to_top"]=turnover(w_top); df["to_bot"]=turnover(w_bot)
    return df

def turnover(wdict):
    ds=sorted(wdict); out=pd.Series(index=ds,dtype=float); prev=None
    for d in ds:
        w=wdict[d]
        out[d]=1.0 if prev is None else 0.5*(w.subtract(prev,fill_value=0).abs().sum())
        prev=w
    return out

def net(gross,to_long,to_short=None):
    """Net monthly return: cost = one-way cost x traded fraction, both sides of the trade."""
    c=2*ONE_WAY_COST*to_long.fillna(1)
    if to_short is not None: c=c+2*ONE_WAY_COST*to_short.fillna(1)+BORROW_ANNUAL/12
    return gross-c

def stats_row(x,label):
    x=x.dropna(); a=x.mean()*12; v=x.std()*np.sqrt(12); sr=a/v if v>0 else np.nan
    t=x.mean()/x.std()*np.sqrt(len(x)) if x.std()>0 else np.nan
    c=(1+x).cumprod(); mdd=(c/c.cummax()-1).min()
    return dict(strategy=label,ann_ret=a,ann_vol=v,sharpe=sr,t=t,maxdd=mdd,worst=x.min(),n=len(x),
                skew=stats.skew(x),kurt=stats.kurtosis(x,fisher=False))

def deflated_sharpe(sr_monthly,n_obs,skew,kurt,n_trials,sr_var_trials):
    """Bailey & Lopez de Prado (2014). sr_monthly = observed monthly Sharpe. Returns (DSR prob, expected max SR under H0)."""
    g=0.5772156649
    emax=np.sqrt(sr_var_trials)*((1-g)*stats.norm.ppf(1-1/n_trials)+g*stats.norm.ppf(1-1/(n_trials*np.e)))
    num=(sr_monthly-emax)*np.sqrt(n_obs-1)
    den=np.sqrt(1-skew*sr_monthly+(kurt-1)/4*sr_monthly**2)
    return stats.norm.cdf(num/den),emax
