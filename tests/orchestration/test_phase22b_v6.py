import hashlib,json
from pathlib import Path
from mt5_scalping_agent.orchestration.hashing import canonical_json_bytes
ROOT=Path(__file__).resolve().parents[2]; P=ROOT/'research/phase22b_spec_v6.json'; H='343b6918acb62a68065eb16ecfc7fd05704fe8a77695d8417f7f81062475d56d'
def test_v6_final_contract():
 v=json.loads(P.read_text(encoding='utf-8')); assert hashlib.sha256(canonical_json_bytes(v)).hexdigest()==H
 assert v['status']=='FROZEN_PENDING_INDEPENDENT_REVIEW' and v['task_id']=='PH22B-REMEDIATION-006'
 assert v['specification_binding']['hash_state']=='EXTERNAL_CANONICAL_HASH_REQUIRED'
 h=next(x for x in v['hypothesis_inventory'] if x['id']=='H_NORM')
 assert h['null'].startswith('R < 4') and h['alternative'].startswith('R >= 4') and 'post-observation' in h['threshold_provenance']
 assert 'classification' in h['classification_separation'] and 'post-observation' in v['normalization_artifact_tests']['threshold_provenance']
 assert all(x not in P.read_text(encoding='utf-8') for x in ('this v2 hash','this v3 hash','TO_BE_COMPUTED','DRAFT_PENDING_FREEZE'))

def test_v6_has_no_stale_advancement_version():
 text=P.read_text(encoding='utf-8'); assert 'frozen v4' not in text and 'exact v4' not in text and 'this exact frozen specification' in text
