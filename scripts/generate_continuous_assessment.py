"""Generate deterministic JSON and Markdown diagnoses from a completed report."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from mt5_scalping_agent.research import write_json_atomic
from mt5_scalping_agent.research.continuous_assessment import (
    ContinuousAssessmentError,
    build_continuous_assessment,
    load_completed_continuous_report,
)


LOGGER = logging.getLogger(__name__)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose a completed 2019-2023 continuous evaluation report."
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    json_output = args.json_output or args.report.with_name(
        f"{args.report.stem}_assessment.json"
    )
    markdown_output = args.markdown_output or args.report.with_name(
        f"{args.report.stem}_assessment.md"
    )
    try:
        _validate_output_paths(args.report, json_output, markdown_output)
        report = load_completed_continuous_report(args.report)
        machine, markdown = build_continuous_assessment(
            report, source_label=args.report.as_posix()
        )
        write_json_atomic(json_output, machine)
        _write_text_atomic(markdown_output, markdown)
    except (ContinuousAssessmentError, OSError, RuntimeError, ValueError) as error:
        LOGGER.error("Continuous assessment failed: %s", error)
        return 1
    print(f"Assessment JSON: {json_output}")
    print(f"Assessment Markdown: {markdown_output}")
    return 0


def _validate_output_paths(report: Path, json_output: Path, markdown_output: Path) -> None:
    source = report.resolve()
    destinations = (json_output.resolve(), markdown_output.resolve())
    if source in destinations:
        raise ContinuousAssessmentError("assessment output cannot overwrite its source report")
    if destinations[0] == destinations[1]:
        raise ContinuousAssessmentError("JSON and Markdown outputs must be different files")


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
