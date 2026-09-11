"""Fail-closed, guard-before-read access to authorised research partitions.

This module deliberately accepts a pre-loaded metadata catalogue.  It never
enumerates a dataset directory and it calls the supplied reader only after all
control-plane and provenance checks have passed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence, TypeVar
import hashlib
import json

import pandas as pd
import numpy as np

from .errors import DATA_ACCESS_GATE_DENIED, MANIFEST_INVALID, OrchestrationError
from .gates import assert_data_access
from .task import validate_task


SUPPORTED_SYMBOLS = frozenset({"EURUSD", "GBPUSD", "USDJPY", "USDCAD"})
_HEX = frozenset("0123456789abcdef")
T = TypeVar("T")


def _sha256(value: object, field: str) -> str:
    text = str(value).lower()
    if len(text) != 64 or any(char not in _HEX for char in text):
        raise OrchestrationError(MANIFEST_INVALID, f"unverifiable {field}")
    return text


@dataclass(frozen=True)
class ApprovedPartitionResolver:
    """Exact metadata-key to opaque-locator mapping approved by the task owner."""

    locators: Mapping[str, object]

    def resolve(self, metadata_key: str) -> object:
        try:
            return self.locators[metadata_key]
        except KeyError as error:
            raise OrchestrationError(
                DATA_ACCESS_GATE_DENIED, "partition is not listed by approved resolver"
            ) from error


def guarded_read_partition(
    *,
    state: dict,
    task: dict,
    partition: str | int,
    symbol: str,
    metadata_catalog: Mapping[str, Mapping[str, object]],
    resolver: ApprovedPartitionResolver,
    reader: Callable[[object], T],
) -> T:
    """Read one partition only after authority and provenance are established.

    Validation order is security-significant: task manifest, authorization,
    metadata, approved resolver, then reader.  Any exception before the final
    line guarantees that ``reader`` has not been invoked.
    """

    validated_task = validate_task(task)
    window = str(partition)
    normalized_symbol = str(symbol).upper()

    # Authorization intentionally precedes catalogue lookup or locator access.
    assert_data_access(state, validated_task, [window])
    if normalized_symbol not in SUPPORTED_SYMBOLS:
        raise OrchestrationError(DATA_ACCESS_GATE_DENIED, f"unsupported symbol {symbol!r}")

    allowed_roots = {
        str(entry.get("root_sha256", "")).lower()
        for entry in validated_task.get("allowed_data", [])
        if window in {str(item) for item in entry.get("partitions", [])}
    }
    required_root = _sha256(validated_task["required_dataset_hash"], "task dataset root")
    if required_root not in allowed_roots:
        raise OrchestrationError(DATA_ACCESS_GATE_DENIED, "partition is not listed in task allowed_data")

    metadata_key = f"{normalized_symbol}:{window}"
    metadata = metadata_catalog.get(metadata_key)
    if not isinstance(metadata, Mapping):
        raise OrchestrationError(DATA_ACCESS_GATE_DENIED, "partition metadata is not listed")
    if str(metadata.get("partition")) != window or str(metadata.get("symbol", "")).upper() != normalized_symbol:
        raise OrchestrationError(MANIFEST_INVALID, "partition metadata identity mismatch")
    if _sha256(metadata.get("dataset_root_sha256"), "dataset root") != required_root:
        raise OrchestrationError(MANIFEST_INVALID, "partition metadata dataset root mismatch")
    _sha256(metadata.get("partition_sha256"), "partition hash")
    _sha256(metadata.get("provenance_sha256"), "partition provenance")

    if not isinstance(resolver, ApprovedPartitionResolver):
        raise OrchestrationError(DATA_ACCESS_GATE_DENIED, "unapproved resolver")
    locator = resolver.resolve(metadata_key)
    return reader(locator)


def guarded_load_verified_frame(*, state: dict, task: dict, partition: str | int, symbol: str, catalog_loader: Callable[[], Mapping[str, Mapping[str, object]]], resolver: ApprovedPartitionResolver, byte_reader: Callable[[object], bytes], parser: Callable[[bytes], pd.DataFrame]) -> pd.DataFrame:
    """Authorize before catalog access; hash bytes before parsing; verify payload."""
    validated = validate_task(task)
    window, normalized = str(partition), str(symbol).upper()
    assert_data_access(state, validated, [window])
    auth = validated.get("data_authorization", {})
    if normalized not in auth.get("symbols", []) or int(window) not in auth.get("years", []) or f"{normalized}-{window}" not in auth.get("partitions", []):
        raise OrchestrationError(DATA_ACCESS_GATE_DENIED, "pair-year not authorized")
    metadata = catalog_loader().get(f"{normalized}:{window}")
    if not isinstance(metadata, Mapping): raise OrchestrationError(DATA_ACCESS_GATE_DENIED, "metadata absent")
    required_root = _sha256(validated["required_dataset_hash"], "task dataset root")
    if _sha256(metadata.get("dataset_root_sha256"), "dataset root") != required_root: raise OrchestrationError(MANIFEST_INVALID, "dataset root mismatch")
    payload = byte_reader(resolver.resolve(f"{normalized}:{window}"))
    expected = _sha256(metadata.get("partition_sha256"), "partition hash")
    if not isinstance(payload, bytes) or hashlib.sha256(payload).hexdigest() != expected: raise OrchestrationError(MANIFEST_INVALID, "partition byte hash mismatch")
    frame = parser(payload)
    required = ["timestamp_utc_ns", "bid", "ask"]
    if not isinstance(frame, pd.DataFrame) or list(frame.columns) != required or frame.isna().any().any(): raise OrchestrationError(MANIFEST_INVALID, "frame schema/null failure")
    times=frame.timestamp_utc_ns.to_numpy(dtype="int64"); start=pd.Timestamp(f"{window}-01-01T00:00:00Z").value; end=pd.Timestamp(f"{int(window)+1}-01-01T00:00:00Z").value
    bid=frame.bid.to_numpy(float); ask=frame.ask.to_numpy(float)
    if (times<start).any() or (times>=end).any(): raise OrchestrationError(DATA_ACCESS_GATE_DENIED, "timestamp outside authorized year")
    if not np.isfinite(bid).all() or not np.isfinite(ask).all() or (bid<=0).any() or (ask<=0).any() or (ask<bid).any(): raise OrchestrationError(MANIFEST_INVALID, "invalid quotes")
    result=frame.copy(); result["source_row_ordinal"]=range(len(result))
    return result.sort_values(["timestamp_utc_ns","source_row_ordinal"],kind="stable").reset_index(drop=True)

def canonical_catalog_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def guarded_load_monthly_pair_year(
    *, state: dict, task: dict, year: int, pair: str,
    metadata_catalog_loader: Callable[[], Mapping[str, Any]],
    locator_catalog_loader: Callable[[], Mapping[str, Any]],
    metadata_catalog_sha256: str, locator_catalog_sha256: str,
    byte_reader: Callable[[object], bytes], parser: Callable[[bytes], pd.DataFrame],
    frame_visitor: Callable[[pd.DataFrame, Mapping[str, Any]], None] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Authorize first; validate both reviewed catalogs before any unit read."""
    validated = validate_task(task)
    window, normalized = str(year), str(pair).upper()
    assert_data_access(state, validated, [window])
    auth = validated.get("data_authorization", {})
    if normalized not in auth.get("symbols", ()) or year not in auth.get("years", ()) or f"{normalized}-{year}" not in auth.get("partitions", ()):
        raise OrchestrationError(DATA_ACCESS_GATE_DENIED, "pair-year not authorized")
    hashes = {str(x.get("path")): str(x.get("sha256", "")).lower() for x in validated.get("inputs", ()) if x.get("hash_mode") == "canonical_json"}
    mp = "governance/data_catalogs/phase22b_2019_2021_metadata.json"
    lp = "governance/data_catalogs/phase22b_2019_2021_locators.json"
    em, el = hashes.get(mp), hashes.get(lp)
    if not em or not el or _sha256(metadata_catalog_sha256, "metadata catalog hash") != em or _sha256(locator_catalog_sha256, "locator catalog hash") != el:
        raise OrchestrationError(MANIFEST_INVALID, "catalogs are not task-bound")
    metadata, locators = metadata_catalog_loader(), locator_catalog_loader()
    if canonical_catalog_hash(metadata) != em or canonical_catalog_hash(locators) != el:
        raise OrchestrationError(MANIFEST_INVALID, "catalog content hash mismatch")
    if metadata.get("authorization_id") != locators.get("authorization_id") or metadata.get("dataset_root_sha256") != locators.get("dataset_root_sha256"):
        raise OrchestrationError(MANIFEST_INVALID, "cross-catalog header mismatch")
    if metadata.get("authorization_id") != auth.get("authorization_id") or _sha256(metadata.get("dataset_root_sha256"), "catalog root") != _sha256(validated["required_dataset_hash"], "task root"):
        raise OrchestrationError(MANIFEST_INVALID, "catalog task binding mismatch")
    mu, lu = metadata.get("units"), locators.get("units")
    if not isinstance(mu, Sequence) or isinstance(mu, (str, bytes)) or not isinstance(lu, Sequence) or isinstance(lu, (str, bytes)):
        raise OrchestrationError(MANIFEST_INVALID, "catalog units malformed")
    try:
        md, ld = {str(x["unit_id"]): x for x in mu}, {str(x["unit_id"]): x for x in lu}
    except (KeyError, TypeError) as exc:
        raise OrchestrationError(MANIFEST_INVALID, "catalog unit identity missing") from exc
    if len(md) != len(mu) or len(ld) != len(lu):
        raise OrchestrationError(MANIFEST_INVALID, "duplicate catalog unit id")
    selected = []
    for month in range(1, 13):
        uid, pid = f"{normalized}-{year}-{month:02d}", f"{normalized}-{year}"
        meta, loc = md.get(uid), ld.get(uid)
        if not isinstance(meta, Mapping) or not isinstance(loc, Mapping):
            raise OrchestrationError(MANIFEST_INVALID, "pair-year must contain exactly 12 monthly units")
        identity = (uid, pid, normalized, year, month)
        if any((x.get("unit_id"), x.get("partition_id"), x.get("pair"), x.get("year"), x.get("month")) != identity for x in (meta, loc)):
            raise OrchestrationError(MANIFEST_INVALID, "cross-catalog pair-year-month mismatch")
        start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
        if meta.get("status") != "VALIDATED" or pd.Timestamp(meta.get("start_utc")) != start or pd.Timestamp(meta.get("end_utc")) != start + pd.offsets.MonthBegin(1):
            raise OrchestrationError(MANIFEST_INVALID, "monthly status or bounds mismatch")
        _sha256(meta.get("normalized_sha256"), "monthly normalized hash")
        locator_text = str(loc.get("normalized_path", ""))
        expected_stem = f"{normalized}_{start:%Y%m%dT%H%M%SZ}_{(start + pd.offsets.MonthBegin(1)):%Y%m%dT%H%M%SZ}_MT5_TICKS.parquet"
        normalized_locator = locator_text.replace("\\", "/")
        if not normalized_locator.endswith(f"/{normalized}/{year}/{expected_stem}"):
            raise OrchestrationError(DATA_ACCESS_GATE_DENIED, "locator escapes authorized monthly identity")
        selected.append((meta, loc))
    if any(sum(x.get("pair") == normalized and x.get("year") == year for x in units) != 12 for units in (mu, lu)):
        raise OrchestrationError(MANIFEST_INVALID, "pair-year has extra or missing units")
    frames, provenance = [], []
    for meta, loc in selected:
        payload = byte_reader(loc["normalized_path"])
        expected = str(meta["normalized_sha256"]).lower()
        if not isinstance(payload, bytes) or hashlib.sha256(payload).hexdigest() != expected:
            raise OrchestrationError(MANIFEST_INVALID, "monthly byte hash mismatch")
        frame = parser(payload)
        required = ["timestamp_utc_ns", "bid", "ask"]
        if not isinstance(frame, pd.DataFrame) or list(frame.columns) != required or [str(frame[x].dtype) for x in required] != ["int64", "float64", "float64"] or frame.isna().any().any():
            raise OrchestrationError(MANIFEST_INVALID, "monthly frame schema failure")
        times, bid, ask = (frame[x].to_numpy(copy=False) for x in required)
        start, end = pd.Timestamp(meta["start_utc"]).value, pd.Timestamp(meta["end_utc"]).value
        if (times < start).any() or (times >= end).any():
            raise OrchestrationError(DATA_ACCESS_GATE_DENIED, "timestamp outside authorized monthly unit")
        if not np.isfinite(bid).all() or not np.isfinite(ask).all() or (bid <= 0).any() or (ask <= 0).any() or (ask < bid).any():
            raise OrchestrationError(MANIFEST_INVALID, "invalid monthly quotes")
        frame = frame.copy()
        frame["source_unit_id"], frame["source_row_ordinal"] = meta["unit_id"], np.arange(len(frame), dtype=np.int64)
        record = {"unit_id": str(meta["unit_id"]), "sha256": expected, "locator_authorized": True, "bytes_read": len(payload), "hash_verified_before_parse": True, "parsed_rows": int(len(frame)), "start_utc": str(meta["start_utc"]), "end_utc": str(meta["end_utc"])}
        provenance.append(record)
        if frame_visitor is None: frames.append(frame)
        else: frame_visitor(frame, record)
    combined = (pd.concat(frames, ignore_index=True).sort_values(["timestamp_utc_ns", "source_unit_id", "source_row_ordinal"], kind="stable").reset_index(drop=True) if frames else pd.DataFrame(columns=["timestamp_utc_ns", "bid", "ask", "source_unit_id", "source_row_ordinal"]))
    return combined, provenance