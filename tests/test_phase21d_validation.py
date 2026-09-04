import json
from pathlib import Path
from scripts.run_phase21d_validation import COST_SHA,HYPOTHESIS_SHA,PAIRS,REQUIRED,validate

def valid_documents():
    criteria={f"C{i}":{"pass":False} for i in range(1,9)}
    return {"manifest":{"hypothesis_sha256":HYPOTHESIS_SHA,"cost_model_sha256":COST_SHA,"holdout_start":"2024-01-01T00:00:00+00:00"},"holdout_data_integrity":{"pairs":{p:{} for p in PAIRS}},"event_population":{"pairs":{p:{} for p in PAIRS}},"pair_results":{},"year_results":{},"bootstrap":{"replicates":10_000,"seed":21_003},"concentration":{},"success_criteria":{"criteria":criteria},"phase21d_summary":{"classification":"INSUFFICIENT_HOLDOUT_SAMPLE"}}

def write_documents(path:Path,documents):
    for name in REQUIRED:(path/f"{name}.json").write_text(json.dumps(documents[name]))

def test_semantic_validator_accepts_reproducible_insufficient_sample(tmp_path):
    write_documents(tmp_path,valid_documents());result=validate(tmp_path,"run");assert result["valid"];assert result["classification_recomputed"]=="INSUFFICIENT_HOLDOUT_SAMPLE"

def test_semantic_validator_rejects_wrong_fingerprint(tmp_path):
    documents=valid_documents();documents["manifest"]["hypothesis_sha256"]="wrong";write_documents(tmp_path,documents);assert "hypothesis_fingerprint" in validate(tmp_path,"run")["invalid_components"]

def test_semantic_validator_rejects_missing_pair_and_bootstrap_change(tmp_path):
    documents=valid_documents();documents["event_population"]["pairs"].pop("USDCAD");documents["bootstrap"]["seed"]=1;write_documents(tmp_path,documents);result=validate(tmp_path,"run");assert "four_pair_event_coverage" in result["invalid_components"];assert "bootstrap_specification" in result["invalid_components"]

def test_semantic_validator_reproduces_pass_and_failure(tmp_path):
    documents=valid_documents();documents["success_criteria"]["criteria"]={f"C{i}":{"pass":True} for i in range(1,9)};documents["phase21d_summary"]["classification"]="PROSPECTIVE_HYPOTHESIS_VALIDATED";write_documents(tmp_path,documents);assert validate(tmp_path,"run")["valid"]
    documents["success_criteria"]["criteria"]["C3"]["pass"]=False;documents["phase21d_summary"]["classification"]="PROSPECTIVE_HYPOTHESIS_FAILED";write_documents(tmp_path,documents);assert validate(tmp_path,"run")["valid"]
