"""Frozen aggregate inference and success classification for Phase 21C."""
from __future__ import annotations
import numpy as np
import pandas as pd
from mt5_scalping_agent.research.phase21c_prospective import PAIRS,BOOTSTRAP_REPLICATES,BOOTSTRAP_SEED

def _maximum_losing_run(values:np.ndarray)->int:
    best=run=0
    for value in values:
        run=run+1 if value<=0 else 0;best=max(best,run)
    return best

def _pair_metrics(frame:pd.DataFrame,requested:int)->dict[str,object]:
    x=frame[frame.status.eq("AVAILABLE")].sort_values("event_time");net=x.net_directional_pips.to_numpy(float);positive,negative=net[net>0].sum(),-net[net<0].sum()
    return {"event_count":len(x),"availability_rate":len(x)/requested if requested else 0.,"mean_net_pips":float(net.mean()) if len(net) else None,"median_net_pips":float(np.median(net)) if len(net) else None,"win_rate":float((net>0).mean()) if len(net) else None,"gross_mean_pips":float(x.gross_directional_pips.mean()) if len(x) else None,"cost_mean_pips":float(x.stress_cost_pips.mean()) if len(x) else None,"profit_factor":float(positive/negative) if negative else None,"median_mae":float(x.mae_pips.median()) if len(x) else None,"p90_mae":float(x.mae_pips.quantile(.1)) if len(x) else None,"median_mfe":float(x.mfe_pips.median()) if len(x) else None,"p90_mfe":float(x.mfe_pips.quantile(.9)) if len(x) else None,"maximum_consecutive_losing_events":_maximum_losing_run(net)}

def _aggregate_bootstrap(frame:pd.DataFrame)->dict[str,object]:
    x=frame[frame.status.eq("AVAILABLE")].copy();x["day"]=pd.to_datetime(x.event_time,utc=True).dt.date;days=sorted(x.day.unique());table=x.groupby(["day","pair"]).net_directional_pips.agg(["sum","count"]);sums=np.array([[table.loc[(d,p),"sum"] if (d,p) in table.index else 0. for p in PAIRS] for d in days]);counts=np.array([[table.loc[(d,p),"count"] if (d,p) in table.index else 0 for p in PAIRS] for d in days]);rng=np.random.default_rng(BOOTSTRAP_SEED);distribution=np.empty(BOOTSTRAP_REPLICATES)
    for start in range(0,BOOTSTRAP_REPLICATES,250):
        size=min(250,BOOTSTRAP_REPLICATES-start);draws=rng.integers(len(days),size=(size,len(days)));sample_sums=sums[draws].sum(1);sample_counts=counts[draws].sum(1);distribution[start:start+size]=np.mean(sample_sums/sample_counts,axis=1)
    p=float((distribution<=0).mean())
    return {"replicates":BOOTSTRAP_REPLICATES,"seed":BOOTSTRAP_SEED,"ci95":[float(np.quantile(distribution,.025)),float(np.quantile(distribution,.975))],"raw_p_one_sided":p,"alpha":.05,"survives":p<=.05}

def evaluate_hypothesis(outcomes:pd.DataFrame)->dict[str,object]:
    requested=outcomes.groupby("pair").size().to_dict();metrics={pair:_pair_metrics(outcomes[outcomes.pair.eq(pair)],int(requested.get(pair,0))) for pair in PAIRS};counts={pair:int(metrics[pair]["event_count"]) for pair in PAIRS};total=sum(counts.values())
    if total<500 or any(value<75 for value in counts.values()):return {"classification":"INSUFFICIENT_HOLDOUT_SAMPLE","event_count":total,"pair_metrics":metrics,"minimums":{"aggregate":500,"per_pair":75}}
    means={pair:float(metrics[pair]["mean_net_pips"]) for pair in PAIRS};equal_weight=float(np.mean(list(means.values())));bootstrap=_aggregate_bootstrap(outcomes);available=outcomes[outcomes.status.eq("AVAILABLE")];absolute_total=float(available.net_directional_pips.abs().sum());top10=float(available.net_directional_pips.abs().nlargest(10).sum()/absolute_total) if absolute_total else 1.;denominator=sum(abs(v) for v in means.values());contribution={pair:abs(value)/denominator if denominator else 1. for pair,value in means.items()}
    checks={"aggregate_positive":equal_weight>0,"three_pairs_positive":sum(v>0 for v in means.values())>=3,"negative_pair_does_not_reverse_aggregate":sum(means.values())>0,"bootstrap_ci_positive":bootstrap["ci95"][0]>0,"bootstrap_test_survives":bootstrap["survives"],"pair_concentration":max(contribution.values())<=.5,"top10_event_concentration":top10<=.2}
    return {"classification":"PROSPECTIVE_HYPOTHESIS_PASSED" if all(checks.values()) else "PROSPECTIVE_HYPOTHESIS_FAILED","event_count":total,"pair_metrics":metrics,"equal_weight_mean_net_pips":equal_weight,"bootstrap":bootstrap,"pair_absolute_effect_contribution":contribution,"top10_event_absolute_effect_contribution":top10,"checks":checks}
