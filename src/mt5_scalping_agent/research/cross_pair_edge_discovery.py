"""Causal descriptive research primitives for Phase 19A; never a trading strategy."""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from mt5_scalping_agent.data.validation import validate_ohlcv
from mt5_scalping_agent.research.time_alignment import exact_positions
PIP_SIZES={"EURUSD":.0001,"GBPUSD":.0001,"USDJPY":.01,"USDCAD":.0001}; USD_SIGN={"EURUSD":-1.,"GBPUSD":-1.,"USDJPY":1.,"USDCAD":1.}; HORIZONS=(5,10,15,30,60)
def pip_size(pair):
    if pair.upper() not in PIP_SIZES: raise ValueError(f"unsupported pair: {pair}")
    return PIP_SIZES[pair.upper()]
def oriented_return(pair, returns): return returns.astype(float)*USD_SIGN[pair.upper()]
def causal_bars(m1, minutes):
    if minutes not in (5,15): raise ValueError("Phase 19A supports only M5 and M15")
    source=validate_ohlcv(m1); frame=source.set_index("time").resample(f"{minutes}min",label="left",closed="left").agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),count=("close","count")).dropna().reset_index(); frame=frame.loc[frame["count"]==minutes].copy(); frame["completed_time"]=frame["time"]+pd.to_timedelta(int(minutes)-1,unit="min"); frame["return"]=frame["close"].pct_change(); return frame.reset_index(drop=True)
def causal_standardize(values, window): return values/values.shift(1).rolling(window,min_periods=window).std(ddof=1).replace(0,np.nan)
def causal_percentile(values, window):
    """Exact empirical <= rank against prior finite window; current is algebraically removed."""
    rank=values.rolling(window+1,min_periods=window+1).rank(method="max",pct=False)
    return (rank-1.0)/window
def session_label(timestamp):
    value=pd.Timestamp(timestamp); l=value.tz_convert(ZoneInfo("Europe/London")); n=value.tz_convert(ZoneInfo("America/New_York")); t=value.tz_convert(ZoneInfo("Asia/Tokyo")); a=8<=l.hour<13; b=8<=n.hour<13
    return "london_new_york_overlap" if a and b else "london" if a else "new_york" if b else "asia_tokyo" if 9<=t.hour<15 else "other"
def add_pair_features(pair,m1,*,volatility_window=20*96):
    pip=pip_size(pair); m5,m15=causal_bars(m1,5),causal_bars(m1,15)
    for f in (m5,m15):
        f["return_pips"]=(f.close-f.open)/pip; f["absolute_return_pips"]=f.return_pips.abs(); f["body_pips"]=f.return_pips; f["true_range_pips"]=(f.high-f.low)/pip; f["range_normalized"]=f.true_range_pips/f.true_range_pips.shift(1).rolling(volatility_window,min_periods=volatility_window).mean(); f["displacement_percentile"]=causal_percentile(f.absolute_return_pips,volatility_window); f["volatility_percentile"]=causal_percentile(f.true_range_pips.shift(1).rolling(volatility_window,min_periods=volatility_window).std(ddof=1),volatility_window); f["session"]=f.completed_time.map(session_label)
    m15["usd_return"]=oriented_return(pair,m15["return"]); m15["usd_z"]=causal_standardize(m15.usd_return,volatility_window); m15["factor_percentile"]=causal_percentile(m15.usd_z.abs(),volatility_window); return m5,m15
def leave_one_out_factor(frames):
    wide=pd.DataFrame({p:f.set_index("completed_time").usd_z for p,f in frames.items()}); out={}
    for pair,frame in frames.items():
        other=wide.drop(columns=pair); factor=other.mean(axis=1).where(other.notna().all(axis=1)); breadth=other.mul(np.sign(wide[pair]),axis=0).gt(0).sum(axis=1).where(factor.notna()&wide[pair].notna()); out[pair]=frame.merge(pd.DataFrame({"completed_time":wide.index,"usd_factor":factor.to_numpy(),"factor_breadth":breadth.to_numpy()}),on="completed_time",how="left")
    return out
def structural_events(pair,m5,m15):
    pip=pip_size(pair); f=m5.copy(); high=f.high.shift(1).rolling(12,min_periods=12).max(); low=f.low.shift(1).rolling(12,min_periods=12).min(); direction=pd.Series(np.where(f.close>high,1,np.where(f.close<low,-1,0)),index=f.index); c1,c2=f.close.shift(-1),f.close.shift(-2); valid=(direction!=0)&high.notna()&c2.notna(); accepted=((direction==1)&(c1>=high)&(c2>=high))|((direction==-1)&(c1<=low)&(c2<=low)); boundary=pd.Series(np.where(direction>0,high,low),index=f.index); e=pd.DataFrame({"pair":pair,"break_time":f.completed_time[valid].to_numpy(),"event_time":f.completed_time.shift(-2)[valid].to_numpy(),"direction":direction[valid].to_numpy(),"state":np.where(accepted[valid],"acceptance","rejection"),"break_distance_pips":(direction[valid]*(f.close[valid]-boundary[valid])/pip).to_numpy(),"session":f.completed_time.shift(-2)[valid].map(session_label).to_numpy(),"displacement_percentile":f.displacement_percentile[valid].to_numpy(),"volatility_percentile":f.volatility_percentile[valid].to_numpy()}); return e.join(m15.set_index("completed_time")[["usd_factor","factor_breadth"]],on="event_time")
def attach_forward_outcomes(events,m1,pair):
    out=events.copy(); prices=validate_ohlcv(m1).set_index("time").close; array=prices.to_numpy(float); loc,_=exact_positions(prices.index,out.event_time,(0,)); ref=np.where(loc>=0,array[np.maximum(loc,0)],np.nan); direction=out.direction.to_numpy(float)[:,None]
    for horizon in HORIZONS:
        _,positions=exact_positions(prices.index,out.event_time,range(1,horizon+1)); ok=(loc>=0)&(positions>=0).all(1); path=np.full((len(out),horizon),np.nan); path[ok]=array[positions[ok]]; moves=direction*(path-ref[:,None])/pip_size(pair); out[f"outcome_{horizon}m_status"]=np.where(ok,"AVAILABLE","MISSING_EXACT_PATH"); out[f"forward_{horizon}m_pips"]=moves[:,-1]; out[f"mfe_{horizon}m_pips"]=np.where(ok,np.nanmax(moves,1),np.nan); out[f"mae_{horizon}m_pips"]=np.where(ok,np.nanmin(moves,1),np.nan)
    return out
def deduplicate_events(events,minutes=60):
    keep=[]
    for _,g in events.sort_values("event_time").groupby("pair",sort=False):
        times=pd.DatetimeIndex(g.event_time); selected=np.zeros(len(g),bool); last=None
        for i,when in enumerate(times):
            if last is None or when>=last+pd.Timedelta(minutes=int(minutes)): selected[i]=True; last=when
        keep.append(g.iloc[np.flatnonzero(selected)])
    return pd.concat(keep,ignore_index=True) if keep else events.iloc[:0].copy()
def opportunity_to_cost(events,base_cost,stress_cost,horizon=60):
    x=events[f"mfe_{horizon}m_pips"].dropna()
    def s(cost): return {"median_ocr":float(x.median()/cost) if len(x) else None,"threshold_proportions":{str(k):float((x>=k*cost).mean()) if len(x) else None for k in (2,4,6,8,10)}}
    return {"horizon_minutes":horizon,"base":s(base_cost),"stress":s(stress_cost)}
def benjamini_hochberg(p_values,q=.05):
    order=np.argsort(p_values); n=len(p_values); adj=np.empty(n); run=1.
    for rank in range(n,0,-1): i=order[rank-1]; run=min(run,p_values[i]*n/rank); adj[i]=run
    return [{"p_value":float(p),"q_value":float(adj[i]),"survives_fdr":bool(adj[i]<=q)} for i,p in enumerate(p_values)]
def day_block_bootstrap_mean(events,column,*,samples=5000,seed=19019):
    d=events.dropna(subset=[column]);
    if d.empty:return {"n":0,"days":0,"mean":None,"standard_error":None,"ci95":[None,None],"samples":samples,"seed":seed}
    groups=[g[column].to_numpy(float) for _,g in d.groupby(pd.to_datetime(d.event_time,utc=True).dt.date)]; rng=np.random.default_rng(seed); means=np.array([np.concatenate([groups[i] for i in rng.integers(len(groups),size=len(groups))]).mean() for _ in range(samples)]); return {"n":len(d),"days":len(groups),"mean":float(d[column].mean()),"standard_error":float(means.std(ddof=1)),"ci95":[float(np.quantile(means,.025)),float(np.quantile(means,.975))],"samples":samples,"seed":seed}
