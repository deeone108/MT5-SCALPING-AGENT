"""Phase 21B mechanism attribution; descriptive research only."""
from __future__ import annotations
import numpy as np
import pandas as pd
from mt5_scalping_agent.research.time_alignment import exact_positions,validated_time_index

def attribute(initial_residual,target_change,common_change):
    """Classify which leg reduces the signed target-minus-common residual."""
    reduction=-np.sign(initial_residual)*(target_change-common_change)
    target=-np.sign(initial_residual)*target_change; common=np.sign(initial_residual)*common_change
    return np.where(reduction<=0,'AMBIGUOUS',np.where((target>0)&(common>0),'BOTH',np.where(target>0,'TARGET_REVERSAL',np.where(common>0,'COMMON_COMPONENT_CATCH_UP','AMBIGUOUS'))))
def path_metrics(residuals,times,positions,horizon=60,step_minutes=5):
    r=np.asarray(residuals,float); index=validated_time_index(times,name='event_time'); pos=np.asarray(positions,int); offsets=np.arange(step_minutes,horizon+1,step_minutes); _,future=exact_positions(index,index[pos],offsets); valid=(future>=0).all(1); initial=np.abs(r[pos]); paths=np.full((len(pos),len(offsets)),np.nan); paths[valid]=np.abs(r[future[valid]]); ratio=paths/initial[:,None]; widened=paths-initial[:,None]
    def first(mask): return np.where(valid&mask.any(1),offsets[mask.argmax(1)],np.nan)
    safe=np.where(valid[:,None],widened,-np.inf)
    maximum=np.max(safe,1); positive=maximum>0
    return {'status':np.where(valid,'AVAILABLE','MISSING_EXACT_PATH'),'valid':valid,'time_to_75':first(ratio<=.75),'time_to_50':first(ratio<=.5),'time_to_25':first(ratio<=.25),'maximum_widening':np.where(valid,np.maximum(maximum,0),np.nan),'time_to_max_widening':np.where(valid,np.where(positive,offsets[np.argmax(safe,1)],0),np.nan)}

EPS = 1e-10
MECHANISMS = ('TARGET_REVERSAL','COMMON_CATCH_UP','BOTH_CONTRIBUTE','NEITHER_OR_AMBIGUOUS','NON_CONVERGENT')

def contribution_arithmetic(initial_residual, future_residual, target_change, common_change):
    """Frozen Phase 21B signed contribution decomposition."""
    r0=np.asarray(initial_residual,float); rh=np.asarray(future_residual,float)
    target_change=np.asarray(target_change,float); common_change=np.asarray(common_change,float)
    reduction=np.abs(r0)-np.abs(rh); sign=np.sign(r0)
    target=-sign*target_change; common=sign*common_change
    remainder=reduction-target-common
    if not np.allclose(target+common+remainder,reduction,rtol=0,atol=EPS,equal_nan=True):
        raise ValueError('contribution reconstruction failed')
    return reduction,target,common,remainder

def mechanism_labels(reduction,target,common):
    """Return the exhaustive frozen event-level Phase 21B labels."""
    d=np.asarray(reduction,float); t=np.asarray(target,float); c=np.asarray(common,float)
    labels=np.full(d.shape,'NON_CONVERGENT',dtype=object); convergent=d>0
    labels[convergent]='NEITHER_OR_AMBIGUOUS'
    labels[convergent&(t>EPS)&(c<=EPS)]='TARGET_REVERSAL'
    labels[convergent&(c>EPS)&(t<=EPS)]='COMMON_CATCH_UP'
    labels[convergent&(t>EPS)&(c>EPS)]='BOTH_CONTRIBUTE'
    return labels

def adverse_path_metrics(initial_residual, residual_paths, offsets):
    """Measure widening strictly before first 50% convergence, or through horizon."""
    initial=np.abs(np.asarray(initial_residual,float)); paths=np.abs(np.asarray(residual_paths,float)); offsets=np.asarray(offsets,int)
    valid=np.isfinite(paths).all(1)&np.isfinite(initial)&(initial>0); ratio=paths/initial[:,None]
    out_w=np.full(len(initial),np.nan); out_t=np.full(len(initial),np.nan)
    for i in np.flatnonzero(valid):
        reached=np.flatnonzero(ratio[i]<=.5); stop=int(reached[0]) if len(reached) else len(offsets)
        segment=paths[i,:stop] if stop else np.empty(0)
        widening=np.maximum(segment-initial[i],0) if len(segment) else np.array([0.])
        worst=int(np.argmax(widening)); out_w[i]=widening[worst]; out_t[i]=offsets[worst] if len(segment) else 0
    return {'valid':valid,'max_pre_convergence_widening':out_w,'widening_ratio':out_w/initial,'time_to_worst_widening':out_t}

def target_excursions(reference, future_paths, direction, pip_size, offsets):
    """Descriptive native-pip favourable/adverse excursions in a frozen direction."""
    reference=np.asarray(reference,float); paths=np.asarray(future_paths,float); direction=np.asarray(direction,float); offsets=np.asarray(offsets,int)
    moves=direction[:,None]*(paths-reference[:,None])/float(pip_size); valid=np.isfinite(moves).all(1)
    mfe=np.where(valid,np.max(moves,axis=1),np.nan); mae=np.where(valid,np.min(moves,axis=1),np.nan)
    i_mfe=np.argmax(np.where(np.isfinite(moves),moves,-np.inf),axis=1); i_mae=np.argmin(np.where(np.isfinite(moves),moves,np.inf),axis=1)
    return {'valid':valid,'mfe':mfe,'mae':mae,'time_to_mfe':np.where(valid,offsets[i_mfe],np.nan),'time_to_mae':np.where(valid,offsets[i_mae],np.nan),'mfe_before_mae':valid&(i_mfe<i_mae),'mae_before_mfe':valid&(i_mae<i_mfe)}

def trading_day_bootstrap(frame, statistic, *, samples=5000, seed=21022):
    """Deterministically resample complete trading-day event blocks."""
    if frame.empty: return np.empty(0)
    days=[g for _,g in frame.groupby(pd.to_datetime(frame.event_time,utc=True).dt.date,sort=True)]
    rng=np.random.default_rng(seed); result=np.empty(samples)
    for i in range(samples): result[i]=statistic(pd.concat([days[j] for j in rng.integers(len(days),size=len(days))],ignore_index=True))
    return result