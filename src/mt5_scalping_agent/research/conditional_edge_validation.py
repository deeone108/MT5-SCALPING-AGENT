"""Post-discovery Phase 19B descriptive diagnostics; not strategy code."""
from __future__ import annotations
import numpy as np
import pandas as pd
from mt5_scalping_agent.data.validation import validate_ohlcv
from mt5_scalping_agent.research.time_alignment import exact_positions
from mt5_scalping_agent.research.cross_pair_edge_discovery import HORIZONS, pip_size
PATH_HORIZONS=(1,2,3,5,10,15,20,30,45,60)
def raw_displacement_events(pair,m5,m15):
    out=m5.loc[m5.return_pips.ne(0),["completed_time","return_pips","displacement_percentile","volatility_percentile","session"]].copy(); out.columns=["event_time","target_displacement_pips","displacement_percentile","volatility_percentile","session"]; out["pair"]=pair; out["direction"]=np.sign(out.target_displacement_pips).astype(int); out["family"]="raw_m5_displacement"; return out

def structural_break_events(pair,m5,m15):
    high=m5.high.shift(1).rolling(12,min_periods=12).max(); low=m5.low.shift(1).rolling(12,min_periods=12).min(); direction=np.where(m5.close>high,1,np.where(m5.close<low,-1,0)); mask=direction!=0; out=pd.DataFrame({"pair":pair,"event_time":m5.completed_time[mask].to_numpy(),"direction":direction[mask],"family":"structural_break","target_displacement_pips":m5.return_pips[mask].to_numpy(),"session":m5.session[mask].to_numpy(),"volatility_percentile":m5.volatility_percentile[mask].to_numpy(),"displacement_percentile":m5.displacement_percentile[mask].to_numpy()}); return out

def attach_path(events,m1,pair):
    out=events.copy(); close=validate_ohlcv(m1).set_index("time").close; arr=close.to_numpy(float); loc,pos=exact_positions(close.index,out.event_time,PATH_HORIZONS); _,minute_pos=exact_positions(close.index,out.event_time,range(1,61)); valid=(loc>=0)&(pos>=0).all(1)&(minute_pos>=0).all(1); out=out.loc[valid].copy(); loc=loc[valid]; pos=pos[valid]; minute_pos=minute_pos[valid]; ref=arr[loc]; direction=out.direction.to_numpy(float)[:,None]; values=arr[pos]; moves=direction*(values-ref[:,None])/pip_size(pair)
    for i,h in enumerate(PATH_HORIZONS): out[f"path_{h}m_pips"]=moves[:,i]
    movement=direction*(arr[minute_pos]-ref[:,None])/pip_size(pair); out["mfe_60m_pips"]=np.max(movement,1); out["mae_60m_pips"]=np.min(movement,1); out["time_to_mfe_minutes"]=np.argmax(movement,1)+1; out["time_to_mae_minutes"]=np.argmin(movement,1)+1; out["mfe_before_mae"]=out.time_to_mfe_minutes<out.time_to_mae_minutes; out["mae_before_mfe"]=out.time_to_mae_minutes<out.time_to_mfe_minutes; return out

def lead_lag(oriented,lag):
    """Predefined lag: source return known at t predicts target return t+lag."""
    return oriented.shift(lag)
def leave_one_year_out(events,column):
    years=pd.to_datetime(events.event_time,utc=True).dt.year; return [{"excluded_year":int(year),"n":int((years!=year).sum()),"mean":float(events.loc[years!=year,column].mean())} for year in sorted(years.unique())]
def concentration(events,column):
    x=events[column].dropna().abs(); total=x.sum(); return {"top5_abs_share":float(x.nlargest(5).sum()/total) if total else None,"top10_abs_share":float(x.nlargest(10).sum()/total) if total else None}
