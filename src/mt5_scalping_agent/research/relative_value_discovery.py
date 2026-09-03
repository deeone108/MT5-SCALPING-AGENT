"""Phase 21A causal relative-value diagnostics; never strategy or execution code."""
from __future__ import annotations
import numpy as np
import pandas as pd
from mt5_scalping_agent.research.time_alignment import validated_time_index
from mt5_scalping_agent.research.cross_pair_edge_discovery import causal_bars, causal_percentile, oriented_return, session_label, benjamini_hochberg, pip_size
BUCKETS=(0,.5,.7,.8,.9,.95,.99,1.000001)
def require_development(frame):
 t=pd.to_datetime(frame.time,utc=True)
 if (t>=pd.Timestamp('2024-01-01',tz='UTC')).any(): raise ValueError('Phase 21A rejects 2024+ timestamps')
def standardize_prior(values,window): return values/values.shift(1).rolling(window,min_periods=window).std(ddof=1).replace(0,np.nan)
def causal_percentile_valid(values,window):
 valid=values.dropna(); return causal_percentile(valid,window).reindex(values.index)
def bucket(values): return pd.cut(values,BUCKETS,labels=['0-50','50-70','70-80','80-90','90-95','95-99','99-100'],right=False,include_lowest=True).astype('string')
def common_residuals(m1_by_pair):
 frames={}
 for pair,m1 in m1_by_pair.items():
  require_development(m1); m5=causal_bars(m1,5); ret=oriented_return(pair,m5['return']); frames[pair]=pd.DataFrame({'time':m5.completed_time,'z':standardize_prior(ret,20*24*12),'raw_oriented':ret,'session':m5.completed_time.map(session_label),'vol':causal_percentile((m5.high-m5.low)/pip_size(pair),20*24*12)})
 wide=pd.DataFrame({p:f.set_index('time').z for p,f in frames.items()})
 out={}
 for pair,f in frames.items():
  common=wide.drop(columns=pair).mean(axis=1).where(wide.drop(columns=pair).notna().all(axis=1)); x=f.set_index('time').copy(); x['common']=common; x['residual']=x.z-x.common; x['abs_residual']=x.residual.abs(); x['residual_percentile']=causal_percentile_valid(x.abs_residual,20*24*12); x['bucket']=bucket(x.residual_percentile); x['year']=x.index.year; x['pair']=pair; out[pair]=x.reset_index(names='event_time')
 return out
def entry_events(frame):
 extreme=frame.bucket.isin(['90-95','95-99','99-100']); entered=extreme&~extreme.shift(fill_value=False); return frame.loc[entered].copy()
def dedup(frame,minutes=60):
 keep=[]; last=None
 for i,t in enumerate(frame.event_time):
  if last is None or t>=last+pd.Timedelta(minutes,unit='min'): keep.append(i); last=t
 return frame.iloc[keep].copy()
def outcomes(frame,horizons=(5,10,15,30,60)):
 out=frame.copy(); r=out.residual.to_numpy(float); times=validated_time_index(out.event_time,name='event_time'); lookup=pd.Series(np.arange(len(out)),index=times)
 for h in horizons:
  target=times+pd.Timedelta(minutes=h); pos=lookup.reindex(target).to_numpy(); future=np.full(len(out),np.nan); valid=pd.notna(pos); future[valid]=r[pos[valid].astype(int)]; current=np.abs(r); f=np.abs(future); out[f'outcome_{h}m_status']=np.where(valid,'AVAILABLE','MISSING_EXACT_ENDPOINT'); out[f'change_{h}m']=f-current; out[f'ratio_{h}m']=np.divide(f,current,out=np.full(len(out),np.nan),where=current>0); out[f'sign_persistence_{h}m']=pd.array(np.where(valid,np.sign(r)==np.sign(future),None),dtype='boolean'); out[f'zero_cross_{h}m']=pd.array(np.where(valid,np.sign(r)!=np.sign(future),None),dtype='boolean')
 return out
def pairwise(frames):
 wide=pd.DataFrame({p:f.set_index('event_time').z for p,f in frames.items()}); rows=[]
 names=list(wide)
 for i,a in enumerate(names):
  for b in names[i+1:]:
   d=wide[a]-wide[b]; rows.append({'pair_a':a,'pair_b':b,'n':int(d.notna().sum()),'mean_abs_dislocation':float(d.abs().mean()),'p95_abs_dislocation':float(d.abs().quantile(.95))})
 return rows
def bootstrap_difference(events,value,treated,samples=5000,seed=21021):
 d=pd.DataFrame({'v':events[value],'t':treated,'day':pd.to_datetime(events.event_time,utc=True).dt.date}).dropna(); w=d.groupby(['day','t']).v.mean().unstack().dropna()
 if w.empty:return {'n':0,'mean':None,'ci95':[None,None],'p_value':None}
 x=(w[True]-w[False]).to_numpy(); rng=np.random.default_rng(seed); means=x[rng.integers(len(x),size=(samples,len(x)))].mean(1); return {'n':len(d),'mean':float(x.mean()),'ci95':[float(np.quantile(means,.025)),float(np.quantile(means,.975))],'p_value':float(2*min((means<=0).mean(),(means>=0).mean())),'samples':samples,'seed':seed}
def fdr(rows):
 usable=[x for x in rows if x['p_value'] is not None]; adj=benjamini_hochberg([x['p_value'] for x in usable]); return [{**x,**a} for x,a in zip(usable,adj,strict=True)]
