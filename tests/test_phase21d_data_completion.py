import pandas as pd
from scripts.run_phase21d_data_completion import LIMIT,PAIRS,YEARS,validate_completion

def inventory():
    return [{"pair":pair,"year":year,"exists":True,"parses":True,"missing_columns":[],"malformed_timestamps":0,"monotonic":True,"duplicate_timestamps":0,"nonpositive_price_rows":0,"ohlc_invalid_rows":0,"schema_validation_error":None,"last_timestamp":min(pd.Timestamp(f"{year}-12-31T20:00Z"),LIMIT).isoformat()} for pair in PAIRS for year in YEARS]

def coverage():return {"common_start":"2024-01-01T22:04:00+00:00","common_end":LIMIT.isoformat()}

def test_raw_completion_validator_accepts_complete_integrity():
    result=validate_completion(inventory(),coverage());assert result["valid"];assert result["classification"]=="HOLDOUT_DATA_READY";assert result["raw_rows_sufficient_to_attempt_phase21d"]

def test_raw_completion_validator_rejects_missing_pair_year():
    result=validate_completion(inventory()[:-1],coverage());assert not result["valid"];assert "missing_pair_year_archives" in result["failures"]

def test_raw_completion_validator_rejects_duplicates_and_future_boundary():
    rows=inventory();rows[0]["duplicate_timestamps"]=1;rows[-1]["last_timestamp"]="2026-08-22T00:00:00+00:00";result=validate_completion(rows,coverage());assert not result["valid"];assert any(x.startswith("integrity:") for x in result["failures"]);assert any(x.startswith("beyond_authorized_boundary:") for x in result["failures"])
