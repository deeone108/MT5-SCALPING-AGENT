from unittest.mock import Mock

import pytest

from mt5_scalping_agent.orchestration.data_resolver import (
    ApprovedPartitionResolver,
    guarded_read_partition,
)
from mt5_scalping_agent.orchestration.errors import OrchestrationError


H64 = "a" * 64
SPEC = "b" * 64
COMMIT = "c" * 40


def state(allowed=("2019", "2020", "2021")):
    return {
        "allowed_data_windows": list(allowed),
        "locked_data_windows": ["2022", "2023"],
        "forbidden_data_windows": ["2024+"],
    }


def task(allowed=("2019", "2020", "2021")):
    windows = list(allowed)
    return {
        "schema_version": 1,
        "task_id": "PH22B-RI-SYNTHETIC",
        "phase": "PHASE_22B",
        "phase_id": "PHASE_22B",
        "assigned_role": "research_implementer",
        "objective": "synthetic guard test",
        "inputs": [],
        "allowed_paths": ["synthetic/"],
        "forbidden_paths": ["data/"],
        "allowed_data_window": windows,
        "required_spec_hash": SPEC,
        "required_dataset_hash": H64,
        "base_commit": COMMIT,
        "branch": "task/synthetic",
        "worktree": "synthetic",
        "required_tests": ["guarded_resolver"],
        "required_reviewers": ["qa_reviewer"],
        "completion_conditions": ["synthetic"],
        "status": "READY",
        "allowed_data": [{"root_sha256": H64, "partitions": windows}],
        "prohibited_actions": ["2024+"],
        "required_outputs": ["synthetic"],
    }


def metadata(partition="2019", symbol="EURUSD", **changes):
    value = {
        "partition": partition,
        "symbol": symbol,
        "dataset_root_sha256": H64,
        "partition_sha256": "d" * 64,
        "provenance_sha256": "e" * 64,
    }
    value.update(changes)
    return {f"{symbol}:{partition}": value}


def invoke(*, partition="2019", symbol="EURUSD", catalog=None, resolver=None, reader=None, task_value=None, state_value=None):
    return guarded_read_partition(
        state=state_value or state(),
        task=task_value or task(),
        partition=partition,
        symbol=symbol,
        metadata_catalog=catalog if catalog is not None else metadata(partition, symbol),
        resolver=resolver or ApprovedPartitionResolver({f"{symbol}:{partition}": "opaque"}),
        reader=reader or Mock(return_value="rows"),
    )


@pytest.mark.parametrize("partition", ["2018", "2022", "2023", "2024", "2024+"])
def test_denied_windows_never_call_reader(partition):
    reader = Mock()
    with pytest.raises(OrchestrationError, match="DATA_ACCESS_GATE_DENIED"):
        invoke(partition=partition, reader=reader)
    assert reader.call_count == 0


def test_unsupported_symbol_never_calls_reader():
    reader = Mock()
    with pytest.raises(OrchestrationError, match="unsupported symbol"):
        invoke(symbol="XAUUSD", reader=reader)
    assert reader.call_count == 0


def test_unlisted_partition_never_calls_reader():
    reader = Mock()
    restricted = task(("2019",))
    restricted["allowed_data"] = [{"root_sha256": H64, "partitions": []}]
    with pytest.raises(OrchestrationError, match="not listed in task"):
        invoke(reader=reader, task_value=restricted)
    assert reader.call_count == 0


@pytest.mark.parametrize(
    "change",
    [
        {"provenance_sha256": "unknown"},
        {"partition_sha256": None},
        {"dataset_root_sha256": "f" * 64},
        {"partition": "2020"},
    ],
)
def test_unverifiable_or_mismatched_metadata_never_calls_reader(change):
    reader = Mock()
    with pytest.raises(OrchestrationError):
        invoke(reader=reader, catalog=metadata(**change))
    assert reader.call_count == 0


def test_unapproved_resolver_bypass_never_calls_reader():
    reader = Mock()
    with pytest.raises(OrchestrationError, match="unapproved resolver"):
        invoke(reader=reader, resolver=lambda value: value)
    assert reader.call_count == 0


def test_authorization_occurs_before_metadata_lookup():
    class ExplodingCatalog(dict):
        def get(self, key, default=None):
            raise AssertionError("metadata was touched before authorization")

    reader = Mock()
    with pytest.raises(OrchestrationError, match="DATA_ACCESS_GATE_DENIED"):
        invoke(partition="2022", catalog=ExplodingCatalog(), reader=reader)
    assert reader.call_count == 0


def test_authorized_partition_is_resolved_then_read_once():
    reader = Mock(return_value={"synthetic": True})
    result = invoke(reader=reader)
    assert result == {"synthetic": True}
    reader.assert_called_once_with("opaque")


def _monthly_contract():
    import hashlib
    import json
    import pandas as pd
    from mt5_scalping_agent.orchestration.data_resolver import canonical_catalog_hash
    units, locators, payloads = [], [], {}
    for month in range(1, 13):
        start = pd.Timestamp(year=2019, month=month, day=1, tz="UTC")
        end = start + pd.offsets.MonthBegin(1)
        uid = f"EURUSD-2019-{month:02d}"
        payload = uid.encode()
        units.append({"unit_id":uid,"partition_id":"EURUSD-2019","pair":"EURUSD","year":2019,"month":month,"start_utc":start.isoformat(),"end_utc":end.isoformat(),"status":"VALIDATED","normalized_sha256":hashlib.sha256(payload).hexdigest()})
        stem = f"EURUSD_{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}_MT5_TICKS.parquet"
        payloads[f"C:/data/EURUSD/2019/{stem}"] = payload
        locators.append({"unit_id":uid,"partition_id":"EURUSD-2019","pair":"EURUSD","year":2019,"month":month,"raw_path":uid+".npz","normalized_path":f"C:/data/EURUSD/2019/{stem}","metadata_path":uid+".json"})
    meta={"authorization_id":"AUTH","dataset_root_sha256":H64,"units":units}
    loc={"authorization_id":"AUTH","dataset_root_sha256":H64,"units":locators}
    tv=task(); tv["data_authorization"]={"symbols":["EURUSD"],"years":[2019],"partitions":["EURUSD-2019"],"authorization_id":"AUTH"}
    tv["inputs"]=[{"path":"governance/data_catalogs/phase22b_2019_2021_metadata.json","sha256":canonical_catalog_hash(meta),"hash_mode":"canonical_json"},{"path":"governance/data_catalogs/phase22b_2019_2021_locators.json","sha256":canonical_catalog_hash(loc),"hash_mode":"canonical_json"}]
    return tv,meta,loc,payloads


def test_monthly_resolver_authorizes_before_catalog_loaders():
    from mt5_scalping_agent.orchestration.data_resolver import guarded_load_monthly_pair_year
    explode=Mock(side_effect=AssertionError("catalog touched"))
    with pytest.raises(OrchestrationError,match="DATA_ACCESS_GATE_DENIED"):
        guarded_load_monthly_pair_year(state=state(),task=task(),year=2022,pair="EURUSD",metadata_catalog_loader=explode,locator_catalog_loader=explode,metadata_catalog_sha256=H64,locator_catalog_sha256=H64,byte_reader=Mock(),parser=Mock())
    assert explode.call_count==0


def test_monthly_resolver_validates_every_unit_before_first_read_and_hashes_before_parse():
    import io
    import pandas as pd
    from mt5_scalping_agent.orchestration.data_resolver import guarded_load_monthly_pair_year,canonical_catalog_hash
    tv,meta,loc,payloads=_monthly_contract(); byte_reader=Mock(side_effect=lambda key:payloads[key])
    def parser(payload):
        uid=payload.decode(); month=int(uid[-2:]); start=pd.Timestamp(year=2019,month=month,day=1,tz="UTC").value
        return pd.DataFrame({"timestamp_utc_ns":pd.Series([start],dtype="int64"),"bid":pd.Series([1.0],dtype="float64"),"ask":pd.Series([1.1],dtype="float64")})
    frame,provenance=guarded_load_monthly_pair_year(state=state(),task=tv,year=2019,pair="EURUSD",metadata_catalog_loader=lambda:meta,locator_catalog_loader=lambda:loc,metadata_catalog_sha256=canonical_catalog_hash(meta),locator_catalog_sha256=canonical_catalog_hash(loc),byte_reader=byte_reader,parser=parser)
    assert len(frame)==12 and len(provenance)==12 and byte_reader.call_count==12
    broken=dict(meta); broken["units"]=[dict(x) for x in meta["units"]]; broken["units"][-1]["month"]=11
    tv2=dict(tv); tv2["inputs"]=[dict(x) for x in tv["inputs"]]; tv2["inputs"][0]["sha256"]=canonical_catalog_hash(broken)
    byte_reader.reset_mock()
    with pytest.raises(OrchestrationError,match="cross-catalog"):
        guarded_load_monthly_pair_year(state=state(),task=tv2,year=2019,pair="EURUSD",metadata_catalog_loader=lambda:broken,locator_catalog_loader=lambda:loc,metadata_catalog_sha256=canonical_catalog_hash(broken),locator_catalog_sha256=canonical_catalog_hash(loc),byte_reader=byte_reader,parser=parser)
    assert byte_reader.call_count==0
    bad_payloads=dict(payloads); bad_payloads[loc["units"][0]["normalized_path"]]=b"substitution"
    parse=Mock(side_effect=parser)
    with pytest.raises(OrchestrationError,match="byte hash"):
        guarded_load_monthly_pair_year(state=state(),task=tv,year=2019,pair="EURUSD",metadata_catalog_loader=lambda:meta,locator_catalog_loader=lambda:loc,metadata_catalog_sha256=canonical_catalog_hash(meta),locator_catalog_sha256=canonical_catalog_hash(loc),byte_reader=lambda key:bad_payloads[key],parser=parse)
    assert parse.call_count==0

def test_monthly_locator_identity_is_checked_before_reader():
    from mt5_scalping_agent.orchestration.data_resolver import guarded_load_monthly_pair_year, canonical_catalog_hash
    tv, meta, loc, payloads = _monthly_contract()
    loc = dict(loc); loc["units"] = [dict(x) for x in loc["units"]]
    loc["units"][0]["normalized_path"] = "C:/locked/EURUSD/2022/substitution.parquet"
    tv["inputs"][1]["sha256"] = canonical_catalog_hash(loc)
    reader = Mock()
    with pytest.raises(OrchestrationError, match="locator escapes"):
        guarded_load_monthly_pair_year(state=state(), task=tv, year=2019, pair="EURUSD", metadata_catalog_loader=lambda:meta, locator_catalog_loader=lambda:loc, metadata_catalog_sha256=canonical_catalog_hash(meta), locator_catalog_sha256=canonical_catalog_hash(loc), byte_reader=reader, parser=Mock())
    assert reader.call_count == 0