"""Phase 21B mechanism attribution; descriptive research only."""
from __future__ import annotations
import numpy as np
import pandas as pd

def attribute(initial_residual,target_change,common_change):
    """Classify which leg reduces the signed target-minus-common residual."""
    reduction=-np.sign(initial_residual)*(target_change-common_change)
    target=-np.sign(initial_residual)*target_change; common=np.sign(initial_residual)*common_change
    return np.where(reduction<=0,'AMBIGUOUS',np.where((target>0)&(common>0),'BOTH',np.where(target>0,'TARGET_REVERSAL',np.where(common>0,'COMMON_COMPONENT_CATCH_UP','AMBIGUOUS'))))
def path_metrics(residuals,positions,horizon=60):
    r=np.asarray(residuals,float); pos=np.asarray(positions,int); initial=np.abs(r[pos]); paths=np.abs(r[pos[:,None]+np.arange(1,horizon+1)]); ratio=paths/initial[:,None]; widened=paths-initial[:,None]; return {'time_to_75':np.where((ratio<=.75).any(1),(ratio<=.75).argmax(1)+1,np.nan),'time_to_50':np.where((ratio<=.5).any(1),(ratio<=.5).argmax(1)+1,np.nan),'time_to_25':np.where((ratio<=.25).any(1),(ratio<=.25).argmax(1)+1,np.nan),'maximum_widening':widened.max(1),'time_to_max_widening':widened.argmax(1)+1}