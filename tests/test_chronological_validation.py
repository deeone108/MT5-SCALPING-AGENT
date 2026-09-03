import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.run_chronological_validation import (
    ALL_STRATEGIES,
    _local_archive_dataset,
    _period_manifest,
    _validation_windows,
    first_monday,
    main,
    parse_arguments,
)


def test_first_monday_is_deterministic():
    assert first_monday(2019) == datetime(2019, 1, 7, tzinfo=UTC)
    assert first_monday(2024) == datetime(2024, 1, 1, tzinfo=UTC)
    assert first_monday(2024, 4) == datetime(2024, 4, 1, tzinfo=UTC)


def test_validation_covers_every_fixed_rule_baseline():
    assert len(ALL_STRATEGIES) == 14
    assert 'donchian_breakout' in ALL_STRATEGIES
    assert 'previous_day_range_breakout' in ALL_STRATEGIES
    assert 'new_york_bollinger_reentry' in ALL_STRATEGIES


def test_restart_requires_explicit_command_line_flag():
    args = parse_arguments(['--restart'])

    assert args.restart is True


def test_period_manifest_freezes_development_validation_and_eligibility():
    windows = _validation_windows([2023, 2024], [1], 28)
    periods = _period_manifest(windows, windows[:1])

    assert [window['year'] for window in periods['development_windows']] == [2023]
    assert [window['year'] for window in periods['validation_windows']] == [2024]
    assert periods['eligible_window_keys_at_run_start'] == [{'year': 2023, 'month': 1}]


def test_local_archive_dataset_hashes_each_relevant_annual_file(tmp_path: Path):
    archive_root = tmp_path / 'data'
    annual = archive_root / 'dukascopy_annual' / 'EURUSD_m1_2023.csv.gz'
    annual.parent.mkdir(parents=True)
    annual.write_bytes(b'fixed annual data')

    class Archive:
        @staticmethod
        def source_for_range(start: datetime, end: datetime) -> str:
            return 'dukascopy'

    dataset = _local_archive_dataset(
        archive_root, Archive(), 'EURUSD', _validation_windows([2023], [1], 28), tmp_path
    )

    assert dataset['kind'] == 'local_annual_m1_ohlcv_archive'
    assert dataset['identifier'].startswith('sha256:')
    segment = dataset['provider_segments'][0]
    assert segment['provider'] == 'dukascopy'
    assert segment['files'][0]['path'] == 'data/dukascopy_annual/EURUSD_m1_2023.csv.gz'
    assert segment['files'][0]['sha256'].startswith('sha256:')

def test_runner_writes_manifest_and_resumes_only_compatible_checkpoint(tmp_path: Path):
    report = tmp_path / 'future_summary.json'
    arguments = [
        '--years', '2099', '--months', '1', '--strategies', 'bollinger_mean_reversion',
        '--report-path', str(report),
    ]

    assert main(arguments) == 0
    manifest_path = report.with_suffix('.manifest.json')
    checkpoint_path = report.with_suffix('.checkpoint.json')
    first_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))

    assert first_manifest['experiments'][0]['strategy_name'] == 'bollinger_mean_reversion'
    assert checkpoint['manifest']['compatibility_hash'] == first_manifest['compatibility_hash']
    assert checkpoint['skipped_windows'][0]['year'] == 2099

    assert main(arguments) == 0
    resumed_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert resumed_manifest['execution_timestamp'] == first_manifest['execution_timestamp']


def test_runner_restart_explicitly_replaces_legacy_checkpoint(tmp_path: Path):
    report = tmp_path / 'future_summary.json'
    checkpoint_path = report.with_suffix('.checkpoint.json')
    checkpoint_path.write_text(json.dumps({'results': [], 'skipped_windows': []}), encoding='utf-8')
    arguments = [
        '--years', '2099', '--months', '1', '--strategies', 'bollinger_mean_reversion',
        '--report-path', str(report),
    ]

    from mt5_scalping_agent.research import CheckpointCompatibilityError
    import pytest

    with pytest.raises(CheckpointCompatibilityError, match='legacy or unsupported checkpoint'):
        main(arguments)

    assert main([*arguments, '--restart']) == 0
    checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
    assert checkpoint['checkpoint_schema_version'] == 2
    assert 'manifest' in checkpoint