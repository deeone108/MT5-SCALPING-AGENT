import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from mt5_scalping_agent.research.phase21b_completion import *
def events(labels):
 return pd.DataFrame({'event_time':pd.date_range('2020-01-01',periods=len(labels),freq='12h',tz='UTC'),'mechanism':labels})
def test_b5_bootstrap_and_fdr():
 x=events(['x']*20); x['convergent']=True; x['target_contribution']=2.; x['contributor_contribution']=1.; r=pairwise_test(x,'target',1); assert r['observed_pairwise_delta']==1 and r['bootstrap_replicates']==5000; assert apply_fdr([{**r,'raw_p':0.01}])[0]['FDR_survival']
def test_b6_bootstrap_and_pass_inputs():
 x=events(['TARGET_REVERSAL']*8+['COMMON_CATCH_UP']*2); r=stability_test(x,.6,'TARGET_REVERSAL',2); assert r['delta']==pytest.approx(.6) and not r['category_changed']
def test_b7_bootstrap():
 a=events(['TARGET_REVERSAL']*8+['COMMON_CATCH_UP']*2); b=events(['TARGET_REVERSAL']*7+['COMMON_CATCH_UP']*3); r=method_test(a,b,3); assert r['method_difference']==pytest.approx(.2) and r['bootstrap_replicates']==5000
def test_method_a_residual_volatility():
 t=pd.date_range('2019-01-01',periods=5*365,freq='D',tz='UTC'); r=residual_volatility_stability(pd.Series(np.tile([-1.,1.],913)[:len(t)]),t); assert r['pass']
def test_method_b_coefficient_drift():
 t=pd.date_range('2019-01-01',periods=500,freq='D',tz='UTC'); r=coefficient_drift(pd.DataFrame({'B':np.full(500,.3)},index=t)); assert r['coefficient_pass'] and r['coefficients'][0]['sign_reversal_proportion']==0
def test_block_median_and_economics_inference():
 x=events(['x']*20); x['multiple']=3.; b=block_median_distribution(x,'multiple',5); assert len(b)==5000 and np.all(b==3)
def test_trading_day_concentration():
 x=events(['x']*10); x['effect']=1.; r=concentration(x,'effect'); assert r['top10_event']==1 and r['trading_day']['largest']==.2
def test_classification_engine_all_states():
 p={'TARGET_REVERSAL':.5,'COMMON_CATCH_UP':.2,'BOTH_CONTRIBUTE':.2,'NEITHER_OR_AMBIGUOUS':.05,'NON_CONVERGENT':.05}; base={'complete':True,'prospective':False,'delta':.3,'b1_pass':True,'b6_pass':True,'relationship_pass':True,'proportions':p}; assert classify({**base,'prospective':True})=='HUMAN_GATE_REQUIRED_PROSPECTIVE_HYPOTHESIS'; assert classify(base)=='TARGET_REVERSAL_PHENOMENON'; pc={**p,'TARGET_REVERSAL':.2,'COMMON_CATCH_UP':.5}; assert classify({**base,'delta':-.3,'proportions':pc})=='COMMON_CATCH_UP_PHENOMENON'; pm={**p,'TARGET_REVERSAL':.25,'COMMON_CATCH_UP':.2,'BOTH_CONTRIBUTE':.45}; assert classify({**base,'delta':.05,'proportions':pm})=='MIXED_CONVERGENCE_PHENOMENON'; assert classify({**base,'b6_pass':False})=='MECHANISM_UNSTABLE'; pn={'TARGET_REVERSAL':.1,'COMMON_CATCH_UP':.08,'BOTH_CONTRIBUTE':.05,'NEITHER_OR_AMBIGUOUS':.37,'NON_CONVERGENT':.4}; assert classify({**base,'delta':.02,'proportions':pn})=='NO_ACTIONABLE_MECHANISM'; assert classify({**base,'complete':False})=='PHASE_21B_INCOMPLETE'
def test_semantic_validator(tmp_path:Path):
 names=('manifest','mechanism_by_horizon','target_movement','common_movement','joint_mechanism','contribution_fractions','path_geometry','adverse_widening','target_mfe_mae','pairwise_decomposition','one_leg_economics','two_leg_economics','year_analysis','leave_one_year_out','session_analysis','volatility_analysis','extremeness_analysis','concentration','bootstrap','fdr','method_b','relationship_stability','b4a_one_leg_economics','b4b_two_leg_economics','b5_pairwise_attribution','b6_regime_stability','b7_method_b_robustness','method_a_relationship_stability','method_b_relationship_stability','trading_day_concentration')
 horizon=[{'pair':p,'horizon':h} for p in PAIRS for h in HORIZONS]
 mfe=[{**r,'N_eligible':1,'N_unavailable':0,**{k:0 for k in ('MFE_mean','MFE_median','MFE_p25','MFE_p75','MFE_p90','MAE_mean','MAE_median','MAE_p25','MAE_p75','MAE_p90','MFE_before_MAE_rate','MAE_before_MFE_rate','median_time_to_MFE','median_time_to_MAE')},'status':'AVAILABLE'} for r in horizon]
 inference={'bootstrap_replicates':5000,'BH_q':.1,'FDR_survival':False}
 payloads={'mechanism_by_horizon':horizon,'target_mfe_mae':mfe,
  'b4a_one_leg_economics':{'tests':[{**inference,'B4A_pass':False} for _ in range(4)],'overall_pass':False},
  'b4b_two_leg_economics':{'tests':[{**inference,'economic_pass':False} for _ in range(6)],'overall_pass':False},
  'b5_pairwise_attribution':{'tests':[dict(inference) for _ in range(12)],'unordered':[{} for _ in range(6)],'overall_pass':False},
  'b6_regime_stability':{'tests':[{**inference,'group_pass':False,'group_type':k} for k in ('year','leave_one_year_out','session','volatility')],'overall_pass':False},
  'b7_method_b_robustness':{'tests':[{**inference,'pair_pass':False} for _ in range(4)],'overall_pass':False},
  'method_a_relationship_stability':{'pairs':[{'pair':p} for p in PAIRS],'overall_pass':False},
  'method_b_relationship_stability':{'pairs':[{'pair':p} for p in PAIRS],'overall_pass':False}}
 base={'schema_version':1,'run_id':'r','phase21b_specification_hash':'sha256:x','research_period':{'end_exclusive':'2024-01-01T00:00:00+00:00'}}
 for n in names:(tmp_path/f'{n}.json').write_text(json.dumps({**base,'payload':payloads.get(n,{})}))
 evidence={'complete':True,'prospective':False,'delta':0.,'b1_pass':False,'b6_pass':False,'relationship_pass':False,'proportions':{'TARGET_REVERSAL':.05,'COMMON_CATCH_UP':.05,'BOTH_CONTRIBUTE':.01,'NEITHER_OR_AMBIGUOUS':.09,'NON_CONVERGENT':.8}}
 (tmp_path/'phase21b_summary.json').write_text(json.dumps({**base,'payload':{'classification_evidence':evidence,'classification':'NO_ACTIONABLE_MECHANISM','status':'NO_ACTIONABLE_MECHANISM'}}))
 result=validate_run(tmp_path,'r','sha256:x'); assert result['valid'],result; (tmp_path/'b5_pairwise_attribution.json').unlink(); assert not validate_run(tmp_path,'r','sha256:x')['valid']

def test_semantic_validator_rejects_missing_horizon_and_inference(tmp_path:Path):
 test_semantic_validator(tmp_path); doc=json.loads((tmp_path/'target_mfe_mae.json').read_text()); doc['payload'].pop(); (tmp_path/'target_mfe_mae.json').write_text(json.dumps(doc)); result=validate_run(tmp_path,'r','sha256:x'); assert 'target_mfe_mae:pair_horizon_coverage' in result['invalid_components']
