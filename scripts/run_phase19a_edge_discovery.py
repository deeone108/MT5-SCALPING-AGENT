"""Run Phase 19A descriptive four-pair edge discovery; no broker or strategy code."""
from __future__ import annotations
import json
from datetime import UTC, datetime
from math import erfc, sqrt
from pathlib import Path
import pandas as pd
from mt5_scalping_agent.data import LocalResearchArchive
from mt5_scalping_agent.research.cross_pair import DEVELOPMENT_END, DEVELOPMENT_START
from mt5_scalping_agent.research.cross_pair_edge_discovery import (add_pair_features, attach_forward_outcomes, benjamini_hochberg, day_block_bootstrap_mean, deduplicate_events, leave_one_out_factor, opportunity_to_cost, structural_events)
from mt5_scalping_agent.research.manifest import fingerprint_files, sha256_value, write_json_atomic

PAIRS=("EURUSD","GBPUSD","USDJPY","USDCAD")

def _summary(events: pd.DataFrame) -> dict[str, object]:
    rows=[]
    for (pair,state), group in events.groupby(["pair","state"]):
        values=group["forward_15m_pips"].dropna()
        mean=float(values.mean()) if len(values) else None
        se=float(values.std(ddof=1)/sqrt(len(values))) if len(values)>1 else None
        p=erfc(abs(mean/se)/sqrt(2)) if se and se>0 else 1.0
        rows.append({"pair":pair,"state":state,"n":int(len(values)),"mean_15m_pips":mean,"median_15m_pips":float(values.median()) if len(values) else None,"median_mfe_60m_pips":float(group["mfe_60m_pips"].median()),"median_mae_60m_pips":float(group["mae_60m_pips"].median()),"p_value":p,"bootstrap":day_block_bootstrap_mean(group,"forward_15m_pips")})
    fdr=benjamini_hochberg([r["p_value"] for r in rows]) if rows else []
    for row, adjustment in zip(rows,fdr): row.update(adjustment)
    return {"primary_sample":"60-minute deduplicated events","comparisons":rows}

def main() -> int:
    root=Path("data"); report_dir=Path("reports/phase19a"); archive=LocalResearchArchive(root)
    files=[root/"dukascopy_annual"/f"{pair}_m1_{year}.csv.gz" for pair in PAIRS for year in range(2019,2024)]
    manifest={"phase":"19A","purpose":"descriptive/inferential market behaviour study; not a strategy or backtest","period":{"start":DEVELOPMENT_START.isoformat(),"end_exclusive":DEVELOPMENT_END.isoformat()},"post_selection_accessed":False,"mt5_accessed":False,"seed":19019,"archive_files":fingerprint_files(files,Path.cwd()),"code_hash":sha256_value(Path("src/mt5_scalping_agent/research/cross_pair_edge_discovery.py").read_text(encoding="utf-8"))}
    write_json_atomic(report_dir/"manifest.json",manifest)
    m1={pair:archive.load_m1(pair,DEVELOPMENT_START,DEVELOPMENT_END) for pair in PAIRS}
    features={pair:add_pair_features(pair,frame) for pair,frame in m1.items()}
    factored=leave_one_out_factor({pair:items[1] for pair,items in features.items()})
    raw=[]
    for pair in PAIRS:
        events=attach_forward_outcomes(structural_events(pair,features[pair][0],factored[pair]),m1[pair],pair)
        raw.append(events)
    unrestricted=pd.concat(raw,ignore_index=True); primary=deduplicate_events(unrestricted)
    costs=json.loads(Path("reports/cross_pair_feasibility/roboforex_ecn_cross_pair_cost_models.json").read_text(encoding="utf-8"))["models"]
    opportunity={pair:opportunity_to_cost(primary.loc[primary.pair==pair],float(costs[pair]["base"]["round_trip_cost_pips"]),float(costs[pair]["stress"]["round_trip_cost_pips"])) for pair in PAIRS}
    summary=_summary(primary)
    quality={pair:{"m1_rows":len(m1[pair]),"m5_rows":len(features[pair][0]),"m15_rows":len(features[pair][1])} for pair in PAIRS}
    factor={pair:{"available":int(factored[pair]["usd_factor"].notna().sum()),"missing":int(factored[pair]["usd_factor"].isna().sum())} for pair in PAIRS}
    structure={"raw_events":len(unrestricted),"deduplicated_events":len(primary),"removed_fraction":1-len(primary)/len(unrestricted) if len(unrestricted) else None,"by_pair":primary.groupby("pair").size().to_dict()}
    for name,document in {"data_quality":quality,"factor_diagnostics":factor,"displacement_analysis":summary,"structure_analysis":structure,"cross_pair_confirmation":summary,"session_regime_analysis":{str(key): int(value) for key, value in primary.groupby(["session", "state"]).size().items()},"yearly_stability":primary.assign(year=pd.to_datetime(primary.event_time,utc=True).dt.year).groupby(["pair", "year"])["forward_15m_pips"].agg(["count", "mean", "median"]).reset_index().to_dict(orient="records"),"pair_stability":primary.groupby("pair")["forward_15m_pips"].agg(["count", "mean", "median"]).reset_index().to_dict(orient="records"),"economic_opportunity":opportunity,"statistical_tests":summary}.items(): write_json_atomic(report_dir/f"{name}.json",document)
    classification="WEAK_EVIDENCE" if any(item["survives_fdr"] for item in summary["comparisons"]) else "NO_EVIDENCE"
    write_json_atomic(report_dir/"phase19a_summary.json",{"classification":classification,"manifest":manifest,"structure":structure,"statistics":summary,"opportunity":opportunity,"stop":"Phase 19A complete; no Strategy 19 is created."})
    print(f"Report: {report_dir/'phase19a_summary.json'}"); return 0
if __name__=="__main__": raise SystemExit(main())