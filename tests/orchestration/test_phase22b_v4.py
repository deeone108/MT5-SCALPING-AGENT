import hashlib
import json
from pathlib import Path
from mt5_scalping_agent.orchestration.hashing import canonical_json_bytes

ROOT=Path(__file__).resolve().parents[2]
SPEC=ROOT/'research/phase22b_spec_v4.json'
EXPECTED='540065f088b22cd36c3c8b3140efe4ccff1a3cd422c2d983019d30b8de3978c6'

def load(): return json.loads(SPEC.read_text(encoding='utf-8'))

def test_v4_hash_and_immutable_predecessor():
 v=load(); assert hashlib.sha256(canonical_json_bytes(v)).hexdigest()==EXPECTED
 assert v['supersession']['immutable_predecessor']=='research/phase22b_spec_v3.json'

def test_v4_estimator_covariance_bootstrap_are_frozen():
 i=load()['inference']; e=i['estimator_contract']; c=i['covariance_and_wald_contract']; b=i['bootstrap_contract']
 assert all(k in e for k in ('estimator','arithmetic','transformed_system','solver','rcond','rank_rule','condition_rule','forbidden_fallbacks','failure'))
 assert 'DGELSD' in e['solver'] and 'CR1' in c['estimator'] and c['cluster']=='UTC calendar date; all pairs for a date are one cluster'
 assert b['resamples']==10000 and b['seed']==22002 and 'PCG64' in b['rng'] and 'method=linear' in b['confidence_interval']
 assert '>=' in b['h_raw_p_value'] and 'signed zeros' in b['h_raw_p_value']

def test_v4_single_hraw_and_post_observation_gates():
 v=load(); assert [h['id'] for h in v['hypothesis_inventory']].count('H_RAW')==1
 assert len(v['primary_hypotheses'])==1 and v['primary_hypotheses'][0]['id']=='H_RAW'
 assert 'post-observation' in v['effect_size_and_stability']['threshold_provenance']
 assert 'post-observation' in v['confounding_rules']['threshold_provenance']

def test_v4_session_and_interactions_are_complete():
 v=load(); s=v['models_and_estimands']['sensitivity_models']['S_SESSION']
 assert s['predictors']==s['coefficient_names'] and not any('utc_hour__' in x for x in s['predictors'])
 assert len(v['interaction_tests'])==7
 for item in v['interaction_tests']:
  assert item['added_columns'] and item['restriction_order']==item['added_columns']
  assert item['coefficient_names'][-len(item['added_columns']):] == item['added_columns']
  assert 'covariance' in item and 'failure' in item

def test_v4_fail_first_and_no_stale_authorization_version():
 v=load(); assert v['terminal_classification_algorithm'][0]['state']=='PHASE_22B_INVALID_RESEARCH_RUN'
 assert 'exclusively PHASE_22B_INVALID_RESEARCH_RUN' in v['advancement_and_rejection']['insufficient_evidence']
 assert 'this v2 hash' not in SPEC.read_text(encoding='utf-8')
 assert 'this v3 hash' not in SPEC.read_text(encoding='utf-8')
 assert v['authority']['design_task_allowed_data_windows']==[] and v['authority']['live_execution_authorized'] is False
