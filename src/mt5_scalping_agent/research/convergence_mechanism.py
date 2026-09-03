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
