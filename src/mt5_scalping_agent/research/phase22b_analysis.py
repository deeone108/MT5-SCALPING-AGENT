"""Frozen Phase 22B stage analysis and non-actionable evidence assembly."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
import ctypes
import os
import threading
from typing import Any, Mapping, Sequence
import hashlib
import json

import numpy as np
import pandas as pd
import scipy
from scipy import linalg
from scipy.stats import chi2

from .phase22b_mechanism import (
    SPEC_SHA256,
    InvalidResearchRun,
    benjamini_hochberg,
    bootstrap_summary,
    build_design_matrix,
    daily_block_bootstrap,
    exact_model_complete_case,
    enforce_minimum_contrast_cells,
    fit_wls_clustered_day,
    model_contract,
    wald_test,
)


V12_SPEC_SHA256="12eb328ccc433a4dd75128fafdfb56fe293e30c96bc0962510554b218621610f"
_EPS = np.finfo(np.float64).eps
_TINY = np.finfo(np.float64).tiny
_RCOND = 1e-12
_CONDITION_CEILING = 1e12


def _array_hash(value: np.ndarray, dtype: str = "<f8") -> str:
    return hashlib.sha256(np.asarray(value, dtype=dtype).tobytes(order="C")).hexdigest()


@dataclass(frozen=True)
class DayBlock:
    year: int; utc_day: str; A: np.ndarray; b: np.ndarray; n: int
    R: np.ndarray; d: np.ndarray; input_sha256: str


def build_day_blocks(rows: pd.DataFrame, contract: Mapping[str, Any]) -> tuple[list[DayBlock], tuple[str, ...]]:
    required={"year","utc_day","anchor_utc_ns","pair","source_row_ordinal"}
    if not required.issubset(rows): raise InvalidResearchRun(f"bootstrap ordering columns missing: {sorted(required-set(rows))}")
    ordered=rows.sort_values(["year","utc_day","anchor_utc_ns","pair","source_row_ordinal"],kind="stable").reset_index(drop=True)
    x,y,w,names=build_design_matrix(ordered,contract)
    if not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(w).all() or (w<=0).any(): raise InvalidResearchRun("invalid block input")
    blocks=[]; years=ordered.year.to_numpy(); labels=ordered.utc_day.astype(str).to_numpy()
    for year in sorted(int(v) for v in np.unique(years)):
        for day in sorted(set(labels[years==year])):
            idx=np.flatnonzero((years==year)&(labels==day)); xg,yg,wg=x[idx],y[idx],w[idx]; root=np.sqrt(wg); xw,yw=xg*root[:,None],yg*root
            a=xw.T@xw; a=(a+a.T)/2; b=xw.T@yw; q,r=linalg.qr(xw,mode="economic",pivoting=False,check_finite=True); d=q.T@yw
            for j in range(min(r.shape)):
                if r[j,j]<0: r[j,:]*=-1; d[j]*=-1
            blocks.append(DayBlock(year,day,a,b,len(idx),r,d,_array_hash(np.column_stack((xg,yg,wg)))))
    if not blocks: raise InvalidResearchRun("no UTC-day blocks")
    return blocks,tuple(names)


def _schedule_for_blocks(blocks: Sequence[DayBlock],resamples:int,seed:int)->tuple[np.ndarray,str,str]:
    by_year={}
    for block in blocks: by_year.setdefault(block.year,[]).append(block.utc_day)
    schedule,_=bootstrap_draw_schedule(by_year,resamples=resamples,seed=seed)
    if schedule.shape[1]!=len(blocks): raise InvalidResearchRun("schedule/block mismatch")
    schedule=schedule.astype(np.int64); rng=np.random.Generator(np.random.PCG64(seed)); draw_hash=hashlib.sha256()
    for _ in range(resamples):
        for year in sorted(by_year):
            count=len(by_year[year]); draw=rng.integers(0,count,size=count,endpoint=False).astype("<i8"); draw_hash.update(draw.tobytes())
    return schedule,_array_hash(schedule,"<i8"),draw_hash.hexdigest()


def _block_arrays(blocks:Sequence[DayBlock])->tuple[np.ndarray,np.ndarray,np.ndarray]:
    return np.stack([g.A for g in blocks]),np.stack([g.b for g in blocks]),np.asarray([g.n for g in blocks],dtype=np.int64)


def _normal_system(blocks:Sequence[DayBlock],m:np.ndarray,arrays:tuple[np.ndarray,np.ndarray,np.ndarray]|None=None)->tuple[np.ndarray,np.ndarray,int]:
    aa,bb,nn=_block_arrays(blocks) if arrays is None else arrays; weights=np.asarray(m,dtype=np.float64)
    a=np.sum(weights[:,None,None]*aa,axis=0,dtype=np.float64); b=np.sum(weights[:,None]*bb,axis=0,dtype=np.float64)
    return (a+a.T)/2,b,int(np.dot(np.asarray(m,dtype=np.int64),nn))


def _stack_factor(blocks:Sequence[DayBlock],m:np.ndarray)->tuple[np.ndarray,np.ndarray]:
    parts=[(np.sqrt(np.float64(c))*g.R,np.sqrt(np.float64(c))*g.d) for g,c in zip(blocks,m,strict=True) if c>0]
    if not parts: raise InvalidResearchRun("empty fallback factor")
    return np.vstack([x for x,_ in parts]),np.concatenate([y for _,y in parts])


def matrix_only_preflight(blocks:Sequence[DayBlock],schedule:np.ndarray,*,max_fallbacks:int|None=None)->dict[str,Any]:
    if schedule.ndim!=2 or schedule.shape[1]!=len(blocks) or (schedule<0).any(): raise InvalidResearchRun("invalid preflight schedule")
    k=blocks[0].A.shape[0]; paths=[]; kappas=[]; arrays=_block_arrays(blocks)
    for m in schedule:
        a,_,n=_normal_system(blocks,m,arrays); values=np.linalg.eigvalsh(a)
        if not np.isfinite(values).all() or values[-1]<=0 or n<=k: raise InvalidResearchRun("invalid bootstrap matrix")
        kappa=float(values[-1]/values[0]) if values[0]>0 else float("inf"); rank=int(np.count_nonzero(values>(_RCOND**2)*values[-1]))
        primary=rank==k and np.sqrt(kappa)<=_CONDITION_CEILING and 256*_EPS*kappa<.5 and 4096*_EPS*kappa**2<.5
        if primary:
            try: linalg.cholesky(a,lower=False,check_finite=True)
            except linalg.LinAlgError: primary=False
        paths.append("SPD" if primary else "STACKED_QR_SVD"); kappas.append(kappa)
    count=paths.count("STACKED_QR_SVD"); limit=max_fallbacks if max_fallbacks is not None else max(1,len(schedule)//100)
    if count>limit: raise InvalidResearchRun(f"fallback count {count} exceeds frozen limit {limit}")
    codes=np.asarray([p!="SPD" for p in paths],dtype="<i1")
    return {"paths":paths,"kappa_a":kappas,"fallback_count":count,"preflight_sha256":hashlib.sha256(codes.tobytes()+np.asarray(kappas,dtype="<f8").tobytes()).hexdigest()}


def _compressed_fit(blocks:Sequence[DayBlock],m:np.ndarray,path:str,arrays:tuple[np.ndarray,np.ndarray,np.ndarray]|None=None):
    arrays=_block_arrays(blocks) if arrays is None else arrays; a,b,n=_normal_system(blocks,m,arrays); k=a.shape[0]; g=int(np.sum(m))
    if g<=1 or n<=k: raise InvalidResearchRun("insufficient logical counts")
    if path=="SPD":
        values=np.linalg.eigvalsh(a); kappa=float(values[-1]/values[0]); beta=linalg.solve(a,b,assume_a="pos",check_finite=True); bread=linalg.solve(a,np.eye(k),assume_a="pos",check_finite=True)
        eta_beta,eta_cov=256*_EPS*kappa,4096*_EPS*kappa**2
    elif path=="STACKED_QR_SVD":
        matrix,target=_stack_factor(blocks,m); _,s,vt=np.linalg.svd(matrix,full_matrices=False); rank=int(np.count_nonzero(s>_RCOND*s[0])) if s.size else 0
        if rank!=k or s[-1]<=0 or s[0]/s[-1]>_CONDITION_CEILING: raise InvalidResearchRun("fallback rank/condition failure")
        beta,_,fit_rank,_=np.linalg.lstsq(matrix,target,rcond=_RCOND)
        if fit_rank!=k: raise InvalidResearchRun("fallback fit rank failure")
        bread=(vt.T*(1/s**2))@vt; kappa=float(s[0]/s[-1]); eta_beta,eta_cov=256*_EPS*kappa,8192*_EPS*kappa**2
    else: raise InvalidResearchRun("unknown solver path")
    # The fallback factor is overdetermined, so its raw residual is not a
    # backward-error measure.  Check the mathematically identical normal
    # equations, while path selection remains matrix-only.
    denominator=np.linalg.norm(a,np.inf)*np.linalg.norm(beta,np.inf)+np.linalg.norm(b,np.inf); rho=0. if denominator==0 else float(np.linalg.norm(a@beta-b,np.inf)/denominator)
    if rho>256*_EPS*k or eta_beta>=.5 or eta_cov>=.5 or not np.isfinite([rho,eta_beta,eta_cov]).all(): raise InvalidResearchRun("numerical envelope failure")
    aa,bb,_=arrays; scores=bb-np.matmul(aa,beta); meat=np.sum(np.asarray(m,dtype=np.float64)[:,None,None]*(scores[:,:,None]*scores[:,None,:]),axis=0,dtype=np.float64)
    covariance=(g/(g-1))*((n-1)/(n-k))*bread@meat@bread; covariance=(covariance+covariance.T)/2
    eb=float(eta_beta/(1-eta_beta)*max(np.linalg.norm(beta),_TINY)); ec=float(eta_cov/(1-eta_cov)*max(np.linalg.norm(covariance,"fro"),_TINY))
    if not np.isfinite(beta).all() or not np.isfinite(covariance).all(): raise InvalidResearchRun("non-finite compressed fit")
    return beta,covariance,eb,ec,rho,n,g


def compressed_model_bootstrap(rows:pd.DataFrame,contract:Mapping[str,Any],*,resamples:int=10_000,seed:int=22002,contrast_vectors:Mapping[str,Sequence[float]]|None=None)->dict[str,Any]:
    blocks,names=build_day_blocks(rows,contract); arrays=_block_arrays(blocks); schedule,schedule_hash,draw_hash=_schedule_for_blocks(blocks,resamples,seed); preflight=matrix_only_preflight(blocks,schedule)
    vectors={label:np.asarray(v,dtype=np.float64) for label,v in (contrast_vectors or {}).items()}
    if any(v.shape!=(len(names),) for v in vectors.values()): raise InvalidResearchRun("invalid contrast vector")
    coefficients=np.empty((resamples,len(names))); intervals=np.empty((resamples,len(names),2)); ebv=np.empty(resamples); ecv=np.empty(resamples); rhov=np.empty(resamples); covariance_hashes=[]
    contrasts={label:np.empty(resamples) for label in vectors}; contrast_intervals={label:np.empty((resamples,2)) for label in vectors}
    for start in range(0,resamples,128):
        for i in range(start,min(start+128,resamples)):
            beta,cov,eb,ec,rho,_,_=_compressed_fit(blocks,schedule[i],preflight["paths"][i],arrays); coefficients[i]=beta; intervals[i,:,0]=np.nextafter(beta-eb,-np.inf); intervals[i,:,1]=np.nextafter(beta+eb,np.inf); ebv[i],ecv[i],rhov[i]=eb,ec,rho; covariance_hashes.append(_array_hash(cov))
            for label,v in vectors.items():
                center=float(v@beta); radius=float(np.linalg.norm(v)*eb); contrasts[label][i]=center; contrast_intervals[label][i]=[np.nextafter(center-radius,-np.inf),np.nextafter(center+radius,np.inf)]
    material=b"".join(bytes.fromhex(x.input_sha256)+x.A.astype("<f8").tobytes()+x.b.astype("<f8").tobytes()+np.asarray([x.n],dtype="<i8").tobytes() for x in blocks)
    provenance={"draw_indices_sha256":draw_hash,"schedule_sha256":schedule_hash,"multiplicity_sha256":_array_hash(schedule,"<i8"),"block_statistics_sha256":hashlib.sha256(material).hexdigest(),"preflight_sha256":preflight["preflight_sha256"],"path_sha256":hashlib.sha256("\n".join(preflight["paths"]).encode()).hexdigest(),"coefficient_sha256":_array_hash(coefficients),"coefficient_interval_sha256":_array_hash(intervals),"covariance_sha256":hashlib.sha256("".join(covariance_hashes).encode()).hexdigest(),"e_beta_sha256":_array_hash(ebv),"e_cov_sha256":_array_hash(ecv),"backward_error_sha256":_array_hash(rhov),"numpy_version":np.__version__,"scipy_version":scipy.__version__}
    provenance["replay_sha256"]=hashlib.sha256(b"".join(bytes.fromhex(provenance[k]) for k in sorted(provenance) if k.endswith("sha256"))).hexdigest()
    return {"representation_version":"PH22B_BOOTSTRAP_SUFFICIENT_STATS_V1","coefficient_names":list(names),"coefficients":coefficients,"coefficient_intervals":intervals,"contrasts":contrasts,"contrast_intervals":contrast_intervals,"paths":preflight["paths"],"fallback_count":preflight["fallback_count"],"provenance":provenance}


def certified_quantile(intervals:np.ndarray,probability:float)->tuple[float,float]:
    values=np.asarray(intervals,dtype=np.float64)
    if values.ndim!=2 or values.shape[1]!=2 or not np.isfinite(values).all() or (values[:,0]>values[:,1]).any(): raise InvalidResearchRun("invalid bootstrap intervals")
    low=np.quantile(np.sort(values[:,0],kind="stable"),probability,method="linear"); high=np.quantile(np.sort(values[:,1],kind="stable"),probability,method="linear")
    return float(np.nextafter(low,-np.inf)),float(np.nextafter(high,np.inf))


def certified_attenuation_interval(beta_before:float,radius_before:float,beta_after:float,radius_after:float)->tuple[float,float]:
    before=(np.nextafter(beta_before-radius_before,-np.inf),np.nextafter(beta_before+radius_before,np.inf)); after=(np.nextafter(beta_after-radius_after,-np.inf),np.nextafter(beta_after+radius_after,np.inf))
    if before[0]<=0<=before[1]: raise InvalidResearchRun("attenuation denominator interval contains zero")
    ratios=[n/d for n in after for d in before]
    return float(np.nextafter(1-max(ratios),-np.inf)),float(np.nextafter(1-min(ratios),np.inf))


def compressed_pair_day_bootstrap(rows: pd.DataFrame, responses: Sequence[str], *, resamples: int=10_000, seed: int=22002) -> dict[str, Any]:
    """Frozen non-regression bootstrap on per-day/pair/exposure sums and counts."""
    required={"year","utc_day","pair","exposure",*responses}
    if not required.issubset(rows): raise InvalidResearchRun(f"pair-day columns missing: {sorted(required-set(rows))}")
    ordered=rows.sort_values(["year","utc_day","pair","exposure"],kind="stable")
    days=[]; by_year={}
    for (year,day),frame in ordered.groupby(["year","utc_day"],sort=True):
        contrasts={}
        for response in responses:
            grouped=frame.groupby(["pair","exposure"],sort=True)[response].agg(["sum","count"]).unstack("exposure")
            eligible=grouped.dropna(subset=[("sum","WIDE"),("sum","TIGHT")])
            if eligible.empty: raise InvalidResearchRun("no eligible pair-day contrast")
            contrasts[response]=float(np.mean(eligible[("sum","WIDE")]/eligible[("count","WIDE")]-eligible[("sum","TIGHT")]/eligible[("count","TIGHT")]))
        by_year.setdefault(int(year),[]).append(str(day)); days.append((int(year),str(day),contrasts))
    schedule,_=bootstrap_draw_schedule(by_year,resamples=resamples,seed=seed); schedule=schedule.astype(np.int64)
    centers={response:np.empty(resamples) for response in responses}; bounds={response:np.empty((resamples,2)) for response in responses}
    years=sorted(by_year); offsets={}; offset=0
    for year in years: offsets[year]=(offset,offset+len(by_year[year])); offset+=len(by_year[year])
    for b,multiplicity in enumerate(schedule):
        for response in responses:
            yearly=[]; yearly_radius=[]
            for year in years:
                lo,hi=offsets[year]; terms=np.asarray([multiplicity[i]*days[i][2][response] for i in range(lo,hi)],dtype=np.float64); denominator=float(np.sum(multiplicity[lo:hi]))
                if denominator<=0: raise InvalidResearchRun("empty logical bootstrap year")
                total=float(np.sum(terms,dtype=np.float64)); q=2*int(np.count_nonzero(terms)); gamma=(q*_EPS)/(1-q*_EPS) if q*_EPS<.5 else float("inf")
                yearly.append(total/denominator); yearly_radius.append(gamma*float(np.sum(np.abs(terms),dtype=np.float64))/denominator)
            center=float(np.mean(yearly)); radius=float(np.sum(yearly_radius)/len(yearly)); centers[response][b]=center
            bounds[response][b]=[np.nextafter(center-radius,-np.inf),np.nextafter(center+radius,np.inf)]
    return {"centers":centers,"intervals":bounds,"provenance":{"multiplicity_sha256":_array_hash(schedule,"<i8"),"center_hashes":{k:_array_hash(v) for k,v in centers.items()},"interval_hashes":{k:_array_hash(v) for k,v in bounds.items()}}}


def certified_ratio_distribution(numerator:np.ndarray,numerator_intervals:np.ndarray,denominator:np.ndarray,denominator_intervals:np.ndarray)->tuple[np.ndarray,np.ndarray]:
    values=np.abs(np.asarray(numerator))/np.abs(np.asarray(denominator)); intervals=np.empty((len(values),2))
    for i,(n_bounds,d_bounds) in enumerate(zip(numerator_intervals,denominator_intervals,strict=True)):
        if d_bounds[0]<=0<=d_bounds[1]: raise InvalidResearchRun("ratio denominator interval contains zero")
        n_abs=(0.,max(abs(n_bounds[0]),abs(n_bounds[1]))) if n_bounds[0]<=0<=n_bounds[1] else (min(abs(n_bounds[0]),abs(n_bounds[1])),max(abs(n_bounds[0]),abs(n_bounds[1])))
        d_abs=(min(abs(d_bounds[0]),abs(d_bounds[1])),max(abs(d_bounds[0]),abs(d_bounds[1])))
        intervals[i]=[np.nextafter(n_abs[0]/d_abs[1],-np.inf),np.nextafter(n_abs[1]/d_abs[0],np.inf)]
    return values,intervals


def _resident_bytes() -> int:
    class Counters(ctypes.Structure):
        _fields_=[("cb",ctypes.c_ulong),("PageFaultCount",ctypes.c_ulong),("PeakWorkingSetSize",ctypes.c_size_t),("WorkingSetSize",ctypes.c_size_t),("QuotaPeakPagedPoolUsage",ctypes.c_size_t),("QuotaPagedPoolUsage",ctypes.c_size_t),("QuotaPeakNonPagedPoolUsage",ctypes.c_size_t),("QuotaNonPagedPoolUsage",ctypes.c_size_t),("PagefileUsage",ctypes.c_size_t),("PeakPagefileUsage",ctypes.c_size_t)]
    counters=Counters(); counters.cb=ctypes.sizeof(counters)
    if os.name!="nt": raise InvalidResearchRun("RSS measurement unavailable")
    get_process=ctypes.windll.kernel32.GetCurrentProcess; get_process.restype=ctypes.c_void_p
    get_memory=ctypes.windll.psapi.GetProcessMemoryInfo; get_memory.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]; get_memory.restype=ctypes.c_int
    if not get_memory(get_process(),ctypes.byref(counters),counters.cb):
        raise InvalidResearchRun("RSS measurement unavailable")
    return int(counters.WorkingSetSize)


def benchmark_compressed_bootstrap(*,resamples:int=10_000,days:int=1096,k:int=80,fallback_count:int=100,seed:int=22002,population_count:int=23)->dict[str,Any]:
    rng=np.random.Generator(np.random.PCG64(seed)); blocks=[]
    for day in range(days):
        r=np.eye(k)*(1+day/max(days,1)); a=r.T@r; b=rng.standard_normal(k); blocks.append(DayBlock(2019+day%3,f"D{day:04d}",a,b,k+1,r,b/np.diag(r),hashlib.sha256(str(day).encode()).hexdigest()))
    schedule,digest,_=_schedule_for_blocks(blocks,resamples,seed); paths=["STACKED_QR_SVD" if i<fallback_count else "SPD" for i in range(resamples)]; baseline=_resident_bytes(); peak=[baseline]; stop=threading.Event()
    def sample_rss():
        while not stop.wait(.02): peak[0]=max(peak[0],_resident_bytes())
    sampler=threading.Thread(target=sample_rss,daemon=True); sampler.start(); started=perf_counter()
    arrays=_block_arrays(blocks)
    for m,path in zip(schedule,paths,strict=True): _compressed_fit(blocks,m,path,arrays)
    wall=perf_counter()-started; stop.set(); sampler.join(); peak[0]=max(peak[0],_resident_bytes()); additional=max(0,peak[0]-baseline); projected=wall*population_count
    return {"resamples":resamples,"days":days,"K":k,"fallback_count":fallback_count,"wall_seconds":wall,"peak_additional_rss_bytes":additional,"population_count":population_count,"full_workload_estimated_seconds":projected,"schedule_sha256":digest,"passes_30_minutes":wall<=1800,"passes_4_gib":additional<4*1024**3,"passes_12_hours":projected<12*3600}


SCIENTIFIC_STATES = (
    "GENUINE_SPREAD_STATE_PHENOMENON",
    "NORMALIZATION_ARTIFACT",
    "VOLATILITY_OR_ACTIVITY_CONFOUNDING",
    "SESSION_OR_LIQUIDITY_PROXY",
    "PAIR_SPECIFIC_EFFECT",
    "MIXED_MECHANISM",
    "PHENOMENON_NOT_CONFIRMED",
)


def _fit(rows: pd.DataFrame, contract: Mapping[str, Any]):
    x, y, weights, names = build_design_matrix(rows, contract)
    return fit_wls_clustered_day(x, y, weights, names, rows["utc_day"])


def pair_day_contrast(rows: pd.DataFrame, response: str) -> float:
    grouped = rows.groupby(["year", "pair", "utc_day", "exposure"], sort=True)[response].mean().unstack()
    eligible = grouped.dropna(subset=["WIDE", "TIGHT"])
    if eligible.empty:
        raise InvalidResearchRun("no eligible pair-day contrast")
    yearly = (eligible["WIDE"] - eligible["TIGHT"]).groupby(level="year").mean()
    return float(yearly.mean())


def _model_effect(rows: pd.DataFrame, contract: Mapping[str, Any]) -> float:
    return _fit(rows, contract).coefficient("exposure__WIDE")


def _attenuation_stat(rows: pd.DataFrame, before: Mapping[str, Any], after: Mapping[str, Any]) -> float:
    base = _model_effect(rows, before)
    current = _model_effect(rows, after)
    if base == 0 or not np.isfinite([base, current]).all():
        raise InvalidResearchRun("invalid attenuation coefficient")
    return float(1.0 - current / base)


def _cached_daily_block_bootstrap(rows: pd.DataFrame, statistic, *, resamples: int, seed: int = 22002) -> np.ndarray:
    """Exact PCG64 day bootstrap with immutable ordered day blocks cached once."""
    required = {"year", "utc_day", "anchor_utc_ns", "pair"}
    if resamples <= 0 or not required.issubset(rows):
        raise InvalidResearchRun("bootstrap ordering input failure")
    ordered = rows.sort_values(["year", "utc_day", "anchor_utc_ns", "pair"], kind="stable")
    years = sorted(int(value) for value in ordered["year"].unique())
    days = {year: sorted(ordered.loc[ordered["year"] == year, "utc_day"].astype(str).unique()) for year in years}
    blocks = {(year, day): ordered.loc[(ordered["year"] == year) & (ordered["utc_day"].astype(str) == day)].copy() for year in years for day in days[year]}
    rng = np.random.Generator(np.random.PCG64(seed)); output = np.empty(resamples, dtype=np.float64)
    for iteration in range(resamples):
        copies = []
        for year in years:
            draw = rng.integers(0, len(days[year]), size=len(days[year]), endpoint=False)
            for position, index in enumerate(draw):
                day = days[year][int(index)]; copied = blocks[(year, day)].copy()
                copied["bootstrap_day_id"] = f"{year}:{position:06d}:{day}"; copied["utc_day"] = copied["bootstrap_day_id"]
                copies.append(copied)
        sample = pd.concat(copies, ignore_index=True).sort_values(["year", "bootstrap_day_id", "anchor_utc_ns", "pair"], kind="stable")
        output[iteration] = float(statistic(sample))
        if not np.isfinite(output[iteration]): raise InvalidResearchRun("non-finite bootstrap statistic")
    return output

def _attrition_dimensions(rows: pd.DataFrame, contract: Mapping[str, Any]) -> dict[str, Any]:
    work = rows.copy()
    if "anchor_utc_ns" in work:
        work["utc_month"] = pd.to_datetime(work["anchor_utc_ns"], unit="ns", utc=True).dt.strftime("%Y-%m")
    dimensions = {}
    for dimension in ("pair", "year", "utc_month"):
        if dimension not in work:
            continue
        values = {}
        for level, subset in work.groupby(dimension, sort=True, dropna=False):
            _, counts = exact_model_complete_case(subset, contract)
            values[str(level)] = counts
        dimensions["month" if dimension == "utc_month" else dimension] = values
    return dimensions

def _ci(values: np.ndarray) -> dict[str, float]:
    if values.size == 0 or not np.isfinite(values).all():
        raise InvalidResearchRun("non-finite bootstrap distribution")
    low, high = np.quantile(values, [0.025, 0.975], method="linear")
    return {"ci_low": float(low), "ci_high": float(high), "replicates": int(values.size)}


def _model_inference(rows: pd.DataFrame, contract: Mapping[str, Any], resamples: int) -> dict[str, Any]:
    point = _model_effect(rows, contract)
    compressed = compressed_model_bootstrap(rows, contract, resamples=resamples, seed=22002)
    index = compressed["coefficient_names"].index("exposure__WIDE")
    values = compressed["coefficients"][:, index]
    intervals = compressed["coefficient_intervals"][:, index, :]
    ambiguous = (intervals[:, 0] < 0.0) & (intervals[:, 1] > 0.0)
    if ambiguous.any():
        raise InvalidResearchRun("bootstrap p-value interval straddles null boundary")
    ci_low = certified_quantile(intervals, 0.025)[0]
    ci_high = certified_quantile(intervals, 0.975)[1]
    return {"point": point, "ci_low": ci_low, "ci_high": ci_high, "replicates": int(values.size),
            "p_one_sided": float((1 + np.count_nonzero(intervals[:, 0] >= 0.0)) / (resamples + 1)),
            "compressed_bootstrap_provenance": compressed["provenance"], "fallback_count": compressed["fallback_count"]}


def _interaction_levels(hypothesis: str) -> tuple[str, tuple[Any, ...]]:
    return {
        "H_VOL": ("vol_q", ("Q1", "Q2", "Q3", "Q4", "Q5")),
        "H_ACTIVITY": ("activity_q", ("Q1", "Q2", "Q3", "Q4", "Q5")),
        "H_HOUR": ("utc_hour", tuple(range(24))),
        "H_SESSION": ("session", ("ASIAN", "LONDON_PRE_OVERLAP", "LONDON_NEW_YORK_OVERLAP", "NEW_YORK_POST_OVERLAP", "OFF_SESSION")),
        "H_IMPULSE": ("impulse_sign", ("NEG", "ZERO", "POS")),
        "H_PAIR": ("pair", ("EURUSD", "GBPUSD", "USDJPY", "USDCAD")),
        "H_LIQUIDITY": ("trailing_spread_q", ("Q1", "Q2", "Q3", "Q4", "Q5")),
    }[hypothesis]


def _linear_contrast(result: Any, hypothesis: str, variable: str, level: Any, reference: Any) -> float:
    value = result.coefficient("exposure__WIDE")
    if level != reference:
        suffix = f"{level:02d}" if variable == "utc_hour" else str(level)
        value += result.coefficient(f"WIDE__{variable}__{suffix}")
    return float(value)


def _interaction_strata(rows: pd.DataFrame, contract: Mapping[str, Any], hypothesis: str, resamples: int) -> dict[str, Any]:
    variable, levels = _interaction_levels(hypothesis)
    reference = levels[0]
    cells = enforce_minimum_contrast_cells(rows, [variable])
    output = {}
    for level in levels:
        counts = cells["counts"].get(str(level), cells["counts"].get(level, {}))
        if int(counts.get("WIDE", 0)) < 20 or int(counts.get("TIGHT", 0)) < 20:
            output[str(level)] = {"status": "INSUFFICIENT", "counts": counts}
    if len(output) == len(levels):
        return output
    fitted = _fit(rows, contract)
    names = list(fitted.coefficient_names)
    vectors = {}
    for level in levels:
        if str(level) in output:
            continue
        vector = np.zeros(len(names), dtype=np.float64)
        vector[names.index("exposure__WIDE")] = 1.0
        if level != reference:
            suffix = f"{level:02d}" if variable == "utc_hour" else str(level)
            vector[names.index(f"WIDE__{variable}__{suffix}")] = 1.0
        vectors[str(level)] = vector
    compressed = compressed_model_bootstrap(rows, contract, resamples=resamples, seed=22002, contrast_vectors=vectors)
    for level in levels:
        counts = cells["counts"].get(str(level), cells["counts"].get(level, {}))
        if int(counts.get("WIDE", 0)) < 20 or int(counts.get("TIGHT", 0)) < 20:
            output[str(level)] = {"status": "INSUFFICIENT", "counts": counts}
            continue
        point = _linear_contrast(fitted, hypothesis, variable, level, reference)
        values = compressed["contrasts"][str(level)]; bounds = compressed["contrast_intervals"][str(level)]
        output[str(level)] = {"status": "EVALUABLE", "point": point,
                              "ci_low": certified_quantile(bounds, .025)[0], "ci_high": certified_quantile(bounds, .975)[1],
                              "replicates": int(len(values)), "counts": counts,
                              "compressed_bootstrap_provenance": compressed["provenance"]}
    return output

def analyse_stage(rows: pd.DataFrame, spec: Mapping[str, Any], *, bootstrap_resamples: int = 10_000) -> dict[str, Any]:
    """Run every frozen model and hypothesis for one authorized stage."""
    if rows.empty or not {"year", "pair", "utc_day", "exposure"}.issubset(rows):
        raise InvalidResearchRun("empty or malformed stage rows")
    models: dict[str, Any] = {}
    fitted = {}
    complete_cases = {}
    attrition = {}
    contrast_cells = {}
    for name in ("M0", "M1", "M2", "M3", "M4", "S_SESSION"):
        contract = model_contract(spec, name)
        complete, model_attrition = exact_model_complete_case(rows, contract)
        cells = enforce_minimum_contrast_cells(complete)
        if not cells["evaluable"]:
            raise InvalidResearchRun(f"{name} has fewer than 20 observations in a contrast arm")
        result = _fit(complete, contract)
        complete_cases[name] = complete
        attrition[name] = {"total": model_attrition, **_attrition_dimensions(rows, contract)}
        contrast_cells[name] = cells
        fitted[name] = result
        models[name] = {"exposure__WIDE": result.coefficient("exposure__WIDE"), "rank": result.rank, "condition_number": result.condition_number}

    interactions: dict[str, Any] = {}
    raw_p: dict[str, float] = {}
    for definition in spec["interaction_tests"]:
        hypothesis = definition["hypothesis_id"]
        contract = model_contract(spec, hypothesis)
        complete, model_attrition = exact_model_complete_case(rows, contract)
        interaction_groupers = {
            "H_VOL": ["vol_q"], "H_ACTIVITY": ["activity_q"], "H_HOUR": ["utc_hour"],
            "H_SESSION": ["session"], "H_IMPULSE": ["impulse_sign"],
            "H_PAIR": ["pair"], "H_LIQUIDITY": ["trailing_spread_q"],
        }
        if hypothesis not in interaction_groupers:
            raise InvalidResearchRun(f"unknown frozen interaction: {hypothesis}")
        cells = enforce_minimum_contrast_cells(complete, interaction_groupers[hypothesis])
        result = _fit(complete, contract)
        complete_cases[hypothesis] = complete
        attrition[hypothesis] = {"total": model_attrition, **_attrition_dimensions(rows, contract)}
        contrast_cells[hypothesis] = cells
        test = wald_test(result, definition["restriction_order"])
        interactions[hypothesis] = {**test, "strata": _interaction_strata(complete, contract, hypothesis, bootstrap_resamples)}
        raw_p[hypothesis] = float(test["raw_p"])

    outcomes = {}
    m0 = model_contract(spec, "M0")
    outcome_responses=("Y_RAW_ABS_60S_PIPS", "Y_CURRENT_SPREAD_UNITS", "Y_TRAILING_SPREAD_UNITS", "Y_FIXED_DISCOVERY_SCALE")
    for response in outcome_responses:
        contract = {**m0, "response": response}
        key = f"M0:{response}"
        complete, model_attrition = exact_model_complete_case(rows, contract)
        cells = enforce_minimum_contrast_cells(complete)
        attrition[key], contrast_cells[key] = {"total": model_attrition, **_attrition_dimensions(rows, contract)}, cells
        if not cells["evaluable"]:
            raise InvalidResearchRun(f"required primary stage outcome has no evaluable contrast: {response}")
        complete_cases[key] = complete
        outcomes[response] = {"pair_day_point": pair_day_contrast(complete, response),
                              "M0": _model_inference(complete, contract, bootstrap_resamples)}
    direct_by_response={response:compressed_pair_day_bootstrap(complete_cases["M0:"+response],[response],resamples=bootstrap_resamples,seed=22002) for response in outcome_responses}
    for response in outcome_responses:
        direct=direct_by_response[response]; outcomes[response]["pair_day_bootstrap"]={"ci_low":certified_quantile(direct["intervals"][response],.025)[0],"ci_high":certified_quantile(direct["intervals"][response],.975)[1],"replicates":bootstrap_resamples,"provenance":direct["provenance"]}
    fixed = outcomes["Y_FIXED_DISCOVERY_SCALE"]["pair_day_point"]
    if fixed == 0:
        raise InvalidResearchRun("zero fixed-scale contrast")
    ratio = abs(outcomes["Y_CURRENT_SPREAD_UNITS"]["pair_day_point"]) / abs(fixed)
    m4_diagnostics = {}
    for response in ("Y_RAW_ABS_60S_PIPS", "Y_CURRENT_SPREAD_UNITS", "Y_TRAILING_SPREAD_UNITS", "Y_FIXED_DISCOVERY_SCALE"):
        contract = {**model_contract(spec, "M4"), "response": response}
        key = f"M4:{response}"
        complete, model_attrition = exact_model_complete_case(rows, contract)
        cells = enforce_minimum_contrast_cells(complete)
        attrition[key], contrast_cells[key] = {"total": model_attrition, **_attrition_dimensions(rows, contract)}, cells
        if not cells["evaluable"]:
            raise InvalidResearchRun(f"required M4 outcome has no evaluable contrast: {response}")
        complete_cases[key] = complete
        m4_diagnostics[response] = _model_inference(complete, contract, bootstrap_resamples)
        if response == "Y_FIXED_DISCOVERY_SCALE":
            converted = complete.copy()
            positive = converted["Y_FIXED_DISCOVERY_SCALE"] > 0
            pair_scales = (converted.loc[positive, "Y_RAW_ABS_60S_PIPS"] / converted.loc[positive, "Y_FIXED_DISCOVERY_SCALE"]).groupby(converted.loc[positive, "pair"]).median()
            scale = converted["pair"].map(pair_scales)
            if not np.isfinite(scale).all() or (scale <= 0).any():
                raise InvalidResearchRun("fixed discovery scale cannot be converted to pips")
            converted["Y_FIXED_DISCOVERY_SCALE_PIPS"] = converted["Y_FIXED_DISCOVERY_SCALE"] * scale.to_numpy(dtype=np.float64)
            converted_contract = {**contract, "response": "Y_FIXED_DISCOVERY_SCALE_PIPS"}
            m4_diagnostics[response]["converted_to_pips"] = _model_inference(converted, converted_contract, bootstrap_resamples)
    primary_bootstrap = {k: v for k, v in m4_diagnostics["Y_RAW_ABS_60S_PIPS"].items() if k != "point"}
    raw_p["H_RAW"] = primary_bootstrap["p_one_sided"]
    ratio_index=complete_cases["M0:Y_CURRENT_SPREAD_UNITS"].index.intersection(complete_cases["M0:Y_FIXED_DISCOVERY_SCALE"].index); ratio_direct=compressed_pair_day_bootstrap(rows.loc[ratio_index],["Y_CURRENT_SPREAD_UNITS","Y_FIXED_DISCOVERY_SCALE"],resamples=bootstrap_resamples,seed=22002)
    ratio_bootstrap,ratio_intervals=certified_ratio_distribution(ratio_direct["centers"]["Y_CURRENT_SPREAD_UNITS"],ratio_direct["intervals"]["Y_CURRENT_SPREAD_UNITS"],ratio_direct["centers"]["Y_FIXED_DISCOVERY_SCALE"],ratio_direct["intervals"]["Y_FIXED_DISCOVERY_SCALE"])
    if np.any((ratio_intervals[:,0]<4.0)&(ratio_intervals[:,1]>4.0)): raise InvalidResearchRun("normalization ratio interval straddles boundary")
    raw_p["H_NORM"] = float((1 + np.count_nonzero(ratio_intervals[:,1] < 4.0)) / (bootstrap_resamples + 1))
    denominator_independent = {
        "raw_m4": m4_diagnostics["Y_RAW_ABS_60S_PIPS"]["point"] <= -0.05 and m4_diagnostics["Y_RAW_ABS_60S_PIPS"]["ci_high"] < 0,
        "fixed_m4": m4_diagnostics["Y_FIXED_DISCOVERY_SCALE"]["converted_to_pips"]["point"] <= -0.05 and m4_diagnostics["Y_FIXED_DISCOVERY_SCALE"]["converted_to_pips"]["ci_high"] < 0,
        "trailing_m4": m4_diagnostics["Y_TRAILING_SPREAD_UNITS"]["point"] < 0 and m4_diagnostics["Y_TRAILING_SPREAD_UNITS"]["ci_high"] < 0,
        "current_spread_m0_negative": outcomes["Y_CURRENT_SPREAD_UNITS"]["M0"]["point"] < 0,
        "amplification_at_least_four": ratio >= 4.0,
    }
    fdr = {}
    for family in spec["inference"]["multiple_testing"]["families"]:
        members = family["members"]
        fdr[family["id"]] = benjamini_hochberg({name: raw_p[name] for name in members}, members, family["q"])

    attenuation = {}
    for before, after in zip(("M0", "M1", "M2", "M3"), ("M1", "M2", "M3", "M4")):
        common = complete_cases[before].index.intersection(complete_cases[after].index)
        paired = rows.loc[common].copy()
        before_contract, after_contract = model_contract(spec, before), model_contract(spec, after)
        point = _attenuation_stat(paired, before_contract, after_contract)
        before_boot=compressed_model_bootstrap(paired,before_contract,resamples=bootstrap_resamples,seed=22002); after_boot=compressed_model_bootstrap(paired,after_contract,resamples=bootstrap_resamples,seed=22002)
        jb=before_boot["coefficient_names"].index("exposure__WIDE"); ja=after_boot["coefficient_names"].index("exposure__WIDE"); values=np.empty(bootstrap_resamples); bounds=np.empty((bootstrap_resamples,2))
        for i in range(bootstrap_resamples):
            base=before_boot["coefficients"][i,jb]; current=after_boot["coefficients"][i,ja]; values[i]=1-current/base
            base_radius=max(base-before_boot["coefficient_intervals"][i,jb,0],before_boot["coefficient_intervals"][i,jb,1]-base); current_radius=max(current-after_boot["coefficient_intervals"][i,ja,0],after_boot["coefficient_intervals"][i,ja,1]-current)
            bounds[i]=certified_attenuation_interval(base,base_radius,current,current_radius)
        attenuation[f"{before}_to_{after}"] = {"point": point, "ci_low": certified_quantile(bounds,.025)[0], "ci_high": certified_quantile(bounds,.975)[1], "replicates": int(len(values)),"before_provenance":before_boot["provenance"],"after_provenance":after_boot["provenance"]}
    return {
        "models": models,
        "outcomes": outcomes,
        "m4_outcomes": m4_diagnostics,
        "denominator_independent_predicates": denominator_independent,
        "amplification_ratio": float(ratio),
        "amplification_ratio_bootstrap":{"ci_low":certified_quantile(ratio_intervals,.025)[0],"ci_high":certified_quantile(ratio_intervals,.975)[1],"replicates":bootstrap_resamples,"provenance":ratio_direct["provenance"]},
        "interactions": interactions,
        "raw_p_values": raw_p,
        "fdr": fdr,
        "attenuation": attenuation,
        "primary_bootstrap": primary_bootstrap,
        "complete_case_attrition": attrition,
        "contrast_cells": contrast_cells,
        "row_count": int(len(rows)),
    }


def classify_phase22b(gates: Mapping[str, bool], *, operational_errors: Sequence[str] = ()) -> str:
    """Apply frozen terminal precedence to precomputed auditable gate truths."""
    if operational_errors:
        return "PHASE_22B_INVALID_RESEARCH_RUN"
    required = {
        "raw_all_gates", "no_full_confounder", "normalization_replication", "raw_denominator_failure",
        "amplification_both", "m2_material_both", "vol_activity_fdr_both", "session_or_liquidity_material_both",
        "session_or_liquidity_fdr_both", "pair_specific_both", "two_partial_or_interaction_blocks", "raw_effect_remains",
    }
    missing = required - set(gates)
    if missing:
        raise InvalidResearchRun(f"classification gates missing: {sorted(missing)}")
    if gates["raw_all_gates"] and gates["no_full_confounder"]:
        return SCIENTIFIC_STATES[0]
    if gates["normalization_replication"] and gates["raw_denominator_failure"] and gates["amplification_both"]:
        return SCIENTIFIC_STATES[1]
    if gates["m2_material_both"] and gates["vol_activity_fdr_both"]:
        return SCIENTIFIC_STATES[2]
    if gates["session_or_liquidity_material_both"] and gates["session_or_liquidity_fdr_both"]:
        return SCIENTIFIC_STATES[3]
    if gates["pair_specific_both"]:
        return SCIENTIFIC_STATES[4]
    if gates["two_partial_or_interaction_blocks"] and gates["raw_effect_remains"]:
        return SCIENTIFIC_STATES[5]
    return SCIENTIFIC_STATES[6]


def non_actionable_evidence(*, run_id: str, code_version: str, authorization_id: str, stage: Mapping[str, Any], provenance_hashes: Mapping[str, str]) -> dict[str, Any]:
    """Build schema-shaped evidence that cannot represent a trade decision."""
    if len(code_version) != 40 or any(len(value) != 64 for value in provenance_hashes.values()):
        raise InvalidResearchRun("invalid evidence provenance")
    return {
        "schema_version": 1, "candidate_id": "P22A_SPR_ABS_15s_60s", "specification_hash": V12_SPEC_SHA256,
        "code_version": code_version, "dataset_authorization_id": authorization_id, "research_run_id": run_id,
        "actionable": False, "strategy_eligible": False, "trade_direction": None,
        "primary_raw_pip_effect": stage.get("models", {}).get("M4"),
        "normalized_diagnostic_effect": {"outcomes": stage.get("outcomes", {}), "amplification_ratio": stage.get("amplification_ratio")},
        "confidence_intervals": {"primary": stage.get("primary_bootstrap", {})}, "raw_p_values": stage.get("raw_p_values", {}),
        "adjusted_p_values": {family: {key: value["adjusted_p"] for key, value in tests.items()} for family, tests in stage.get("fdr", {}).items()},
        "fdr_decisions": {family: {key: value["rejected"] for key, value in tests.items()} for family, tests in stage.get("fdr", {}).items()},
        "temporal_replication_results": {}, "pair_stability": {}, "concentration_diagnostics": {}, "session_diagnostics": {},
        "regime_diagnostics": {"interactions": stage.get("interactions", {}), "attenuation": stage.get("attenuation", {})},
        "missingness": {}, "limitations": ["Retrospective internal mechanism attribution only", "Not a strategy and not evidence of profitability"],
        "terminal_scientific_classification": None,
        "reviewer_verdicts": {"statistical_validator": "PENDING", "qa_reviewer": "PENDING"},
        "reviewer_artifact_hashes": {"statistical_validator": None, "qa_reviewer": None}, "provenance_hashes": dict(provenance_hashes),
    }


def canonical_artifact_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _adjusted_contrasts(rows: pd.DataFrame, groupers: list[str], response: str) -> tuple[dict[str, float], dict[str, Any]]:
    cells = enforce_minimum_contrast_cells(rows, groupers)
    estimates: dict[str, float] = {}
    keys = rows[groupers].drop_duplicates().sort_values(groupers, kind="stable") if groupers else pd.DataFrame(index=[0])
    for _, key_row in keys.iterrows():
        selected = rows
        labels = []
        for name in groupers:
            selected = selected.loc[selected[name] == key_row[name]]
            labels.append(str(key_row[name]))
        counts = selected.groupby("exposure").size()
        if int(counts.get("WIDE", 0)) < 20 or int(counts.get("TIGHT", 0)) < 20:
            continue
        table = selected.groupby(["pair", "utc_day", "exposure"], sort=True)[response].mean().unstack()
        table = table.dropna(subset=["WIDE", "TIGHT"])
        if not table.empty:
            estimates["|".join(labels) if labels else "ALL"] = float((table["WIDE"] - table["TIGHT"]).mean())
    return estimates, cells


def _largest_fraction(values) -> float:
    absolute = [abs(float(value)) for value in values]
    total = sum(absolute)
    return 0.0 if total == 0 else float(max(absolute, default=0.0) / total)


def stability_diagnostics(rows: pd.DataFrame, response: str = "Y_RAW_ABS_60S_PIPS", *, spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """V7 covariate-adjusted pair/year/session and concentration diagnostics."""
    required = {"year", "pair", "utc_day", "session", "anchor_utc_ns", "exposure", response}
    if not required.issubset(rows) or spec is None:
        raise InvalidResearchRun("stability diagnostics require columns and frozen spec")
    contract = {**model_contract(spec, "M4"), "response": response}
    complete, attrition = exact_model_complete_case(rows, contract)
    x, y, _, names = build_design_matrix(complete, contract)
    result = _fit(complete, contract)
    exposure_index = names.index("exposure__WIDE")
    working = complete.copy()
    # Remove fitted nuisance contribution while retaining the exposure component and raw scale.
    working["adjusted_response"] = y - (x @ result.coefficients - x[:, exposure_index] * result.coefficients[exposure_index])
    working["utc_month"] = pd.to_datetime(working["anchor_utc_ns"], unit="ns", utc=True).dt.strftime("%Y-%m")
    diagnostics, cell_evidence = {}, {}
    for label, groupers in (("pair", ["pair"]), ("year", ["year"]), ("session", ["session"]),
                            ("month", ["utc_month"]), ("day", ["utc_day"])):
        diagnostics[label], cell_evidence[label] = _adjusted_contrasts(working, groupers, "adjusted_response")
    absolute_days = sorted((abs(value) for value in diagnostics["day"].values()), reverse=True)
    absolute_months = [abs(value) for value in diagnostics["month"].values()]
    day_total, month_total = sum(absolute_days), sum(absolute_months)
    return {**diagnostics, "negative_pair_count": sum(v < 0 for v in diagnostics["pair"].values()),
            "negative_core_session_count": sum(v < 0 for k, v in diagnostics["session"].items() if k != "OFF_SESSION"),
            "largest_pair_fraction": _largest_fraction(diagnostics["pair"].values()),
            "top_five_day_fraction": 0.0 if day_total == 0 else float(sum(absolute_days[:5]) / day_total),
            "largest_month_fraction": 0.0 if month_total == 0 else float(max(absolute_months, default=0.0) / month_total),
            "complete_case_attrition": attrition, "contrast_cells": cell_evidence,
            "adjustment_model": "M4 nuisance-residualized"}

def development_gate_truths(stage: Mapping[str, Any], diagnostics: Mapping[str, Any]) -> dict[str, bool]:
    """Evaluate only gates observable in the 2019-2021 development stage."""
    effect_m0 = float(stage["models"]["M0"]["exposure__WIDE"])
    effect_m4 = float(stage["models"]["M4"]["exposure__WIDE"])
    ci = stage["primary_bootstrap"]
    years = diagnostics["year"]
    return {
        "raw_effect_minimum": effect_m4 <= -0.05,
        "raw_ci_below_zero": float(ci.get("ci_high", float("inf"))) < 0,
        "adjustment_retention": effect_m0 != 0 and effect_m4 < 0 and abs(effect_m4) >= 0.5 * abs(effect_m0),
        "pair_stability": diagnostics["negative_pair_count"] >= 3 and diagnostics["largest_pair_fraction"] < 0.5,
        "development_year_stability": all(float(years.get(str(year), 0.0)) < 0 for year in (2019, 2020, 2021)),
        "session_stability": diagnostics["negative_core_session_count"] >= 3,
        "day_concentration": diagnostics["top_five_day_fraction"] < 0.5,
        "month_concentration": diagnostics["largest_month_fraction"] < 0.5,
    }


def build_result_manifest(*, task_id: str, run_id: str, code_version: str, artifact_path: str, artifact_sha256: str, tests: Sequence[str]) -> dict[str, Any]:
    """Build a pending-review result; never advance the project phase."""
    if len(code_version) != 40 or len(artifact_sha256) != 64:
        raise InvalidResearchRun("invalid result-manifest provenance")
    return {
        "schema_version": 1, "task_id": task_id, "assigned_role": "research_implementer",
        "status": "FROZEN_PENDING_REVIEW", "terminal_state": "DEVELOPMENT_ARTIFACT_FROZEN_PENDING_REVIEW",
        "research_run_id": run_id, "specification_hash_used": V12_SPEC_SHA256, "code_version": code_version,
        "artifacts": [{"path": artifact_path, "sha256": artifact_sha256, "hash_mode": "canonical_json"}],
        "tests": list(tests), "reviewer_status": {"statistical_validator": "PENDING", "qa_reviewer": "PENDING"},
        "requested_transition": "INDEPENDENT_DEVELOPMENT_REVIEW", "data_windows_accessed": ["2019", "2020", "2021"],
        "prohibited_data_accessed": [], "actionable": False, "strategy_eligible": False, "trade_direction": None,
    }

def cluster_robust_score_diagnostic(rows: pd.DataFrame, contract: Mapping[str, Any]) -> dict[str, Any]:
    """Frozen v9 two-sided efficient-score diagnostic; supporting and non-gating."""
    required={"utc_day","anchor_utc_ns","pair","source_row_ordinal"}
    if not required.issubset(rows): raise InvalidResearchRun("score ordering columns missing")
    ordered=rows.sort_values(["utc_day","anchor_utc_ns","pair","source_row_ordinal"],kind="stable").reset_index(drop=True)
    x,y,w,names=build_design_matrix(ordered,contract);j=names.index("exposure__WIDE");z=x[:,j];c=np.delete(x,j,axis=1);rw=np.sqrt(w)
    def fit(target):
        beta,_,rank,sv=np.linalg.lstsq(c*rw[:,None],target*rw,rcond=1e-12)
        condition=float(sv[0]/sv[-1]) if len(sv) else float("inf")
        if rank!=c.shape[1] or len(sv)!=c.shape[1] or not np.isfinite(condition) or condition>1e12: raise InvalidResearchRun("score restricted fit failure")
        return beta,int(rank),condition
    gamma,rr,rc=fit(y);aux,ar,ac=fit(z);e=y-c@gamma;r=z-c@aux;terms=w*r*e
    u=float(np.sum(terms,dtype=np.float64));info=float(np.sum(w*r*r,dtype=np.float64));labels=ordered.utc_day.astype(str).to_numpy();days=sorted(set(labels));n,k,g=len(y),x.shape[1],len(days)
    scores=np.asarray([np.sum(terms[labels==day],dtype=np.float64) for day in days]);variance=float((g/(g-1))*((n-1)/(n-k))*np.sum(scores*scores)) if g>1 and n>k else float("nan")
    if not np.isfinite([u,info,variance]).all() or info<=0 or variance<=0: raise InvalidResearchRun("score information/variance failure")
    q=0.0 if u==0 else float(u*u/variance);p=float(chi2.sf(q,1));result={"diagnostic_id":"M4_EXPOSURE_CLUSTER_ROBUST_SCORE","role":"SUPPORTING_ROBUSTNESS_DIAGNOSTIC_ONLY_NON_GATING","U":0.0 if u==0 else u,"information":info,"variance_cr1":variance,"statistic":q,"df":1,"p_value":p,"N":n,"G":g,"K":k,"restricted_rank":rr,"restricted_condition":rc,"auxiliary_rank":ar,"auxiliary_condition":ac}
    result["canonical_sha256"]=canonical_artifact_hash(result);return result


def certified_predicate(interval: Sequence[float], boundary: float, operator: str) -> bool:
    low,high=map(float,interval)
    if not np.isfinite([low,high,boundary]).all() or low>high: raise InvalidResearchRun("invalid certified interval")
    decided={"<":(high<boundary,low>=boundary),"<=":(high<=boundary,low>boundary),">":(low>boundary,high<=boundary),">=":(low>=boundary,high<boundary)}
    if operator not in decided: raise InvalidResearchRun("unknown certified predicate")
    yes,no=decided[operator]
    if yes:return True
    if no:return False
    raise InvalidResearchRun("certified interval straddles decision boundary")


def bootstrap_draw_schedule(year_days: Mapping[int, Sequence[str]],resamples:int=10_000,seed:int=22002):
    years=sorted(year_days);rng=np.random.Generator(np.random.PCG64(seed));width=sum(len(year_days[y]) for y in years);out=np.zeros((resamples,width),dtype=np.int32)
    for b in range(resamples):
        offset=0
        for year in years:
            count=len(year_days[year]);out[b,offset:offset+count]=np.bincount(rng.integers(0,count,size=count,endpoint=False),minlength=count);offset+=count
    return out,hashlib.sha256(out.astype("<i4").tobytes()).hexdigest()


def stratified_permutation_diagnostic(*args,**kwargs):
    raise InvalidResearchRun("v7 permutation superseded by frozen v9 score diagnostic")

def assert_future_perturbation_invariant(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    """Fail closed unless future-only perturbations preserve all causal exposure inputs."""
    protected = ["anchor_utc_ns", "quote_utc_ns", "spread_pips", "trailing_median_spread_pips",
                 "recent_micro_volatility_pips", "recent_quote_count", "baseline_quote_count",
                 "impulse_15s_pips", "quote_age_seconds", "baseline_quote_rate",
                 "baseline_micro_volatility_pips", "exposure", "vol_q", "activity_q",
                 "impulse_sign", "impulse_abs_q", "trailing_spread_q"]
    missing = [name for name in protected if name not in before or name not in after]
    if missing or len(before) != len(after):
        raise InvalidResearchRun(f"leakage perturbation interface mismatch: {missing}")
    try:
        pd.testing.assert_frame_equal(before[protected].reset_index(drop=True), after[protected].reset_index(drop=True), check_exact=True)
    except AssertionError as exc:
        raise InvalidResearchRun("future perturbation changed causal exposure/control") from exc
    return True

def deterministic_replay(run):
    """Execute twice and require identical canonical bytes."""
    first=run(); second=run()
    a=json.dumps(first,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    b=json.dumps(second,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    if a!=b: raise InvalidResearchRun("deterministic replay mismatch")
    return first,hashlib.sha256(a).hexdigest()


def authoritative_result_manifest(*, task: Mapping[str,Any], base_commit: str, inputs: Sequence[Mapping[str,str]], artifacts: Sequence[Mapping[str,str]], commands: Sequence[str], tests: Sequence[Mapping[str,Any]], files_changed: Sequence[str], start_time: str, end_time: str) -> dict[str,Any]:
    """Construct RESULT_MANIFEST.schema.json-complete pending-review evidence."""
    return {"schema_version":1,"task_id":task["task_id"],"role":"research_implementer","status":"COMPLETE","base_commit":base_commit,"result_commit":None,"inputs":list(inputs),"artifacts":list(artifacts),"commands":list(commands),"tests":list(tests),"data_accessed":["2019","2020","2021"],"prohibitions_verified":["no 2022+","no strategy/PnL/backtest/execution"],"handoff":{"to_role":"statistical_validator_and_qa_reviewer","requested_decision":"INDEPENDENT_IMPLEMENTATION_AND_DEVELOPMENT_REVIEW","limitations":["retrospective mechanism attribution only","non-actionable"]},"data_windows_accessed":["2019","2020","2021"],"tests_executed":[str(x.get("command","")) for x in tests],"review_status":[{"statistical_validator":"PENDING"},{"qa_reviewer":"PENDING"}],"end_time":end_time,"safety_checks":[{"live_execution_authorized":False},{"actionable":False}],"dataset_hash_used":task["required_dataset_hash"],"files_changed":list(files_changed),"test_results":list(tests),"artifact_hashes":{x["path"]:x["sha256"] for x in artifacts},"terminal_result":"DEVELOPMENT_ARTIFACT_FROZEN_PENDING_REVIEW","start_time":start_time,"specification_hash_used":task["required_spec_hash"]}
