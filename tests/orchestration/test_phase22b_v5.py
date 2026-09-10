import hashlib,json
from pathlib import Path
from mt5_scalping_agent.orchestration.hashing import canonical_json_bytes
ROOT=Path(__file__).resolve().parents[2]; P=ROOT/'research/phase22b_spec_v5.json'; H='cee1e5d9e45a5a84f73932daccfa4c3dc5566cfb537733c139b1bc873dfe655e'
def test_v5_final_contract():
 v=json.loads(P.read_text(encoding='utf-8')); assert hashlib.sha256(canonical_json_bytes(v)).hexdigest()==H
 assert v['status']=='FROZEN_PENDING_INDEPENDENT_REVIEW' and v['task_id']=='PH22B-REMEDIATION-005'
 assert v['specification_binding']['hash_state']=='EXTERNAL_CANONICAL_HASH_REQUIRED'
 h=next(x for x in v['hypothesis_inventory'] if x['id']=='H_NORM')
 assert h['null'].startswith('R < 4') and h['alternative'].startswith('R >= 4') and 'post-observation' in h['threshold_provenance']
 assert 'classification' in h['classification_separation'] and 'post-observation' in v['normalization_artifact_tests']['threshold_provenance']
 assert all(x not in P.read_text(encoding='utf-8') for x in ('this v2 hash','this v3 hash','TO_BE_COMPUTED','DRAFT_PENDING_FREEZE'))
