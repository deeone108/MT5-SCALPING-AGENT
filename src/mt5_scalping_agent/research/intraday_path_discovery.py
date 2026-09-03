"""Causal Phase 20A intraday path research; never strategy or execution code."""
from __future__ import annotations
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from mt5_scalping_agent.data.validation import validate_ohlcv
from mt5_scalping_agent.research.cross_pair_edge_discovery import causal_percentile, pip_size, session_label, benjamini_hochberg

PATH_WINDOWS=(5,15,30,60); FORWARD_WINDOWS=(5,10,15,30,60)
VOL_BUCKETS=(0,.5,.7,.8,.9,.95,.99,1.000001); PER_BUCKETS=(0,.2,.4,.6,.8,.95,1.000001)

def require_development_only(frame: pd.DataFrame) -> None:
    times=pd.to_datetime(frame['time'],utc=True)
    if (times>=pd.Timestamp('2024-01-01',tz='UTC')).any(): raise ValueError('Phase 20A rejects 2024+ timestamps')

def _bucket(values: pd.Series, boundaries: tuple[float,...]) -> pd.Series:
    labels=[f'{int(boundaries[i]*100)}-{int(min(boundaries[i+1],1)*100)}' for i in range(len(boundaries)-1)]
    return pd.cut(values,bins=boundaries,labels=labels,right=False,include_lowest=True).astype('string')

def _run_metrics(signs: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    changes=(signs[:,1:]!=signs[:,:-1]) & (signs[:,1:]!=0) & (signs[:,:-1]!=0)
    reversals=changes.sum(axis=1)
    current=np.zeros(len(signs),dtype=int); longest=np.zeros(len(signs),dtype=int); prior=np.zeros(len(signs),dtype=int)
    for col in range(signs.shape[1]):
        value=signs[:,col]; current=np.where((value!=0)&(value==prior),current+1,np.where(value!=0,1,0)); longest=np.maximum(longest,current); prior=value
    return reversals,longest

def _window_metrics(prices: np.ndarray, returns: np.ndarray, positions: np.ndarray, width: int, pip: float, *, forward: bool, direction: np.ndarray | None=None) -> dict[str,np.ndarray]:
    offsets=np.arange(1,width+1) if forward else np.arange(-width+1,1)
    idx=positions[:,None]+offsets
    path_returns=returns[idx]
    start=prices[positions] if forward else prices[positions-width]
    end=prices[positions+width] if forward else prices[positions]
    signed=(end-start)/pip
    length=np.abs(path_returns).sum(axis=1)/pip
    per=np.divide(np.abs(signed),length,out=np.full(len(signed),np.nan),where=length>0)
    directional=np.divide(signed,length,out=np.full(len(signed),np.nan),where=length>0)
    reversals,runs=_run_metrics(np.sign(path_returns))
    result={'signed':signed,'absolute':np.abs(signed),'length':length,'per':per,'directional_efficiency':directional,'reversals':reversals,'run_length':runs}
    if forward:
        oriented=(prices[idx]-prices[positions,None])/pip*direction[:,None]
        mfe=oriented.max(axis=1); mae=oriented.min(axis=1); tmfe=oriented.argmax(axis=1)+1; tmae=oriented.argmin(axis=1)+1
        result.update({'mfe':mfe,'mae':mae,'time_to_mfe':tmfe,'time_to_mae':tmae,'mfe_before_mae':tmfe<tmae})
    return result

def transition_label(times: pd.Series) -> pd.Series:
    """Fixed local-civil-clock transition labels, inherently DST-aware."""
    utc=pd.to_datetime(times,utc=True); london=utc.dt.tz_convert(ZoneInfo('Europe/London')); new_york=utc.dt.tz_convert(ZoneInfo('America/New_York')); tokyo=utc.dt.tz_convert(ZoneInfo('Asia/Tokyo'))
    out=np.full(len(utc),'none',dtype=object)
    out[(tokyo.dt.hour==15)&(tokyo.dt.minute==0)]='asia_to_london'
    out[(london.dt.hour==8)&(london.dt.minute==0)]='london_open'
    out[(new_york.dt.hour==8)&(new_york.dt.minute==0)]='overlap_onset'
    out[(new_york.dt.hour==10)&(new_york.dt.minute==0)]='overlap_mature'
    out[(london.dt.hour==12)&(london.dt.minute==0)]='london_fading'
    out[(new_york.dt.hour==12)&(new_york.dt.minute==0)]='late_new_york'
    return pd.Series(out,index=times.index,dtype='string')

def build_observations(pair: str, m1: pd.DataFrame) -> pd.DataFrame:
    """Build completed-M5 observations and causal path/state measures from M1 closes."""
    require_development_only(m1); frame=validate_ohlcv(m1).reset_index(drop=True); prices=frame.close.to_numpy(float); pip=pip_size(pair); returns=np.diff(prices,prepend=prices[0])
    if not frame.time.diff().iloc[1:].eq(pd.Timedelta(minutes=1)).all(): raise ValueError('build_observations requires consecutive M1 timestamps')
    positions=np.arange(60, len(frame)-60, 5, dtype=int); times=pd.to_datetime(frame.time.iloc[positions],utc=True).reset_index(drop=True)
    out=pd.DataFrame({'pair':pair,'event_time':times,'session':times.map(session_label),'transition':transition_label(times)})
    for width in PATH_WINDOWS:
        pre=_window_metrics(prices,returns,positions,width,pip,forward=False)
        out[f'pre_{width}m_signed_pips']=pre['signed']; out[f'pre_{width}m_per']=pre['per']; out[f'pre_{width}m_volatility']=np.std(returns[positions[:,None]+np.arange(-width+1,1)],axis=1,ddof=1)/pip
    direction=np.sign(out['pre_15m_signed_pips'].to_numpy(float)); direction[direction==0]=np.nan; out['pre_direction']=direction
    for width in FORWARD_WINDOWS:
        future=_window_metrics(prices,returns,positions,width,pip,forward=True,direction=np.nan_to_num(direction,nan=0.0))
        for name,value in future.items(): out[f'forward_{width}m_{name}']=value
        out[f'continuation_{width}m_pips']=future['signed']*np.nan_to_num(direction,nan=0.0); out[f'reversal_{width}m_pips']=-out[f'continuation_{width}m_pips']
    history=20*24*12
    for width in (5,15,30):
        vol=out[f'pre_{width}m_volatility']; out[f'vol_{width}m_percentile']=causal_percentile(vol,history); baseline=vol.shift(1).rolling(history,min_periods=history).median(); change=vol/baseline; out[f'vol_{width}m_change']=change; out[f'vol_{width}m_change_percentile']=causal_percentile(change,history); out[f'vol_{width}m_bucket']=_bucket(out[f'vol_{width}m_percentile'],VOL_BUCKETS); out[f'vol_{width}m_change_bucket']=_bucket(out[f'vol_{width}m_change_percentile'],VOL_BUCKETS)
        per=out[f'pre_{width}m_per']; out[f'per_{width}m_percentile']=causal_percentile(per,history); out[f'per_{width}m_bucket']=_bucket(out[f'per_{width}m_percentile'],PER_BUCKETS)
    return out

def deduplicate_observations(events: pd.DataFrame, minutes: int=60) -> pd.DataFrame:
    chosen=[]
    for _, group in events.sort_values('event_time').groupby('pair',sort=False):
        elapsed=group.event_time.diff().ge(pd.Timedelta(minutes,unit='min')); keep=elapsed.copy(); keep.iloc[0]=True; last=None
        values=[]
        for when in group.event_time:
            select=last is None or when>=last+pd.Timedelta(minutes,unit='min'); values.append(select)
            if select: last=when
        chosen.append(group.loc[np.asarray(values)])
    return pd.concat(chosen,ignore_index=True)

def path_quality_table(events: pd.DataFrame, state: str, *, outcome: str='forward_60m_signed') -> list[dict[str,object]]:
    rows=[]
    for (pair,bucket), group in events.dropna(subset=[state]).groupby(['pair',state],sort=True):
        rows.append({'pair':pair,'bucket':str(bucket),'n':len(group),'median_mfe':float(group['forward_60m_mfe'].median()),'median_mae':float(group['forward_60m_mae'].median()),'median_per':float(group['forward_60m_per'].median()),'median_directional_efficiency':float(group['forward_60m_directional_efficiency'].median()),'median_time_to_mfe':float(group['forward_60m_time_to_mfe'].median()),'mfe_before_mae_rate':float(group['forward_60m_mfe_before_mae'].mean()),'mean_directional_pips':float(group[outcome].mean())})
    return rows

def block_bootstrap_difference(events: pd.DataFrame, value: str, group_mask: pd.Series, *, samples: int=5000, seed: int=20020) -> dict[str,object]:
    data=events[[value,'event_time']].copy(); data['treated']=group_mask.to_numpy(); data=data.dropna(); data['day']=pd.to_datetime(data.event_time,utc=True).dt.date
    daily=data.groupby(['day','treated'])[value].mean().unstack(fill_value=np.nan); daily=daily.dropna()
    if daily.empty:return {'n':0,'mean_difference':None,'ci95':[None,None],'p_value':None,'samples':samples,'seed':seed}
    differences=(daily.get(True)-daily.get(False)).to_numpy(float); rng=np.random.default_rng(seed); draw=rng.integers(0,len(differences),size=(samples,len(differences))); means=differences[draw].mean(axis=1); p=float(2*min((means<=0).mean(),(means>=0).mean()))
    return {'n':int(len(data)),'days':int(len(differences)),'mean_difference':float(differences.mean()),'ci95':[float(np.quantile(means,.025)),float(np.quantile(means,.975))],'p_value':p,'samples':samples,'seed':seed}

def leave_one_year_out(events: pd.DataFrame, value: str) -> list[dict[str,object]]:
    years=pd.to_datetime(events.event_time,utc=True).dt.year
    return [{'excluded_year':int(year),'n':int((years!=year).sum()),'mean':float(events.loc[years!=year,value].mean())} for year in sorted(years.unique())]

def fdr_tests(results: list[dict[str,object]]) -> list[dict[str,object]]:
    usable=[r for r in results if r.get('p_value') is not None]; adjusted=benjamini_hochberg([float(r['p_value']) for r in usable]); return [{**row,**adj} for row,adj in zip(usable,adjusted,strict=True)]

def ocr_quality(events: pd.DataFrame, costs: dict[str,dict[str,float]]) -> list[dict[str,object]]:
    rows=[]
    for pair,group in events.groupby('pair'):
        for scenario,cost in costs[pair].items():
            ocr=group.forward_60m_mfe/cost; rows.append({'pair':pair,'scenario':scenario,'n':len(group),'median_ocr':float(ocr.median()),'mfe_ge_2x':float((ocr>=2).mean()),'mfe_ge_4x':float((ocr>=4).mean()),'mfe_ge_6x':float((ocr>=6).mean()),'mfe_ge_8x':float((ocr>=8).mean()),'mfe_ge_10x':float((ocr>=10).mean()),'median_mae':float(group.forward_60m_mae.median()),'median_per':float(group.forward_60m_per.median()),'mfe_before_mae_rate':float(group.forward_60m_mfe_before_mae.mean()),'median_time_to_mfe':float(group.forward_60m_time_to_mfe.median())})
    return rows
