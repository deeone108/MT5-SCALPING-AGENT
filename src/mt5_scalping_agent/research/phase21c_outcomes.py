"""Exact-timestamp outcome construction for the frozen Phase 21C hypothesis."""
from __future__ import annotations
from collections.abc import Mapping
import numpy as np
import pandas as pd
from mt5_scalping_agent.research.cross_pair_edge_discovery import pip_size
from mt5_scalping_agent.research.phase21c_prospective import PAIRS,HOLDING_MINUTES,target_reversion_direction,_deduplicate
from mt5_scalping_agent.research.time_alignment import validated_time_index

def build_event_outcomes(events:pd.DataFrame,observations:pd.DataFrame,costs:Mapping[str,object],*,start:object,end_exclusive:object,holdout_authorized:bool=False)->pd.DataFrame:
    start_ts,end_ts=pd.Timestamp(start),pd.Timestamp(end_exclusive)
    start_ts=start_ts.tz_localize("UTC") if start_ts.tz is None else start_ts.tz_convert("UTC")
    end_ts=end_ts.tz_localize("UTC") if end_ts.tz is None else end_ts.tz_convert("UTC")
    if start_ts>=end_ts:raise ValueError("evaluation range must be non-empty")
    if end_ts>pd.Timestamp("2024-01-01",tz="UTC") and not holdout_authorized:raise PermissionError("post-2023 evaluation requires explicit holdout authorization")
    if not {"pair","event_time","residual"}.issubset(events) or not {"pair","time","close"}.issubset(observations):raise ValueError("missing required columns")
    selected=events.copy();selected["event_time"]=pd.to_datetime(selected.event_time,utc=True);selected=selected[(selected.event_time>=start_ts)&(selected.event_time<end_ts)]
    if not set(selected.pair).issubset(PAIRS):raise ValueError("pair outside frozen universe")
    selected=_deduplicate(selected);prices=observations.copy();prices["time"]=pd.to_datetime(prices.time,utc=True);rows=[]
    for event in selected.itertuples(index=False):
        pair,event_time=str(event.pair),pd.Timestamp(event.event_time);direction=target_reversion_direction(pair,float(event.residual));pair_prices=prices[prices.pair.eq(pair)].sort_values("time");times=validated_time_index(pair_prices.time,name=f"{pair} observation time");series=pd.Series(pair_prices.close.to_numpy(float),index=times);entry_time=event_time+pd.Timedelta(1,unit="min");exit_time=entry_time+pd.Timedelta(HOLDING_MINUTES,unit="min");path=series.reindex(pd.date_range(entry_time,exit_time,freq="1min"))
        status="AVAILABLE" if path.notna().all() else "MISSING_EXACT_ENTRY" if pd.isna(path.iloc[0]) else "MISSING_EXACT_EXIT" if pd.isna(path.iloc[-1]) else "MISSING_EXACT_PATH";row={"pair":pair,"event_time":event_time,"entry_time":entry_time,"exit_time":exit_time,"direction":direction,"status":status}
        if status=="AVAILABLE":
            movement=direction*(path.to_numpy()-float(path.iloc[0]))/pip_size(pair);model=costs[pair];stress=float(model["stress"]["round_trip_cost_pips"]);base=float(model["base"]["round_trip_cost_pips"]);row.update(gross_directional_pips=float(movement[-1]),stress_cost_pips=stress,base_cost_pips=base,stress_spread_points=float(model["stress"]["spread_points"]),stress_slippage_points=float(model["stress"]["slippage_points"]),commission_per_lot_per_side_usd=float(model["commission_per_lot_per_side_usd"]),net_directional_pips=float(movement[-1]-stress),base_net_directional_pips=float(movement[-1]-base),mfe_pips=float(movement.max()),mae_pips=float(movement.min()))
        rows.append(row)
    return pd.DataFrame(rows)
