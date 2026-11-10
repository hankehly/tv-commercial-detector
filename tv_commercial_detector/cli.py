"""The command-line entry point and its subcommands."""

import argparse
from datetime import datetime
from pathlib import Path

from loguru import logger

from tv_commercial_detector import benchmark, settings
from tv_commercial_detector.comskip import ComskipAdapter
from tv_commercial_detector.detectors import Candidate, LookAheadDetector
from tv_commercial_detector.external_tool import ExternalTool
from tv_commercial_detector.media_probe import Ffprobe
from tv_commercial_detector.recording_set import ValidationReport, logo_file, validate
from tv_commercial_detector.scorecard import format_tables


def main(argv: list[str] | None = None) -> int:
    """Run the command line.

    Parameters
    ----------
    argv : list[str] | None
        The arguments after the program name; ``sys.argv`` when ``None``.

    Returns
    -------
    int
        The exit code: 0 on success, 1 when errors were found.
    """
    parser = argparse.ArgumentParser(prog="tv-commercial-detector")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "validate", help="Check the recording set without running any detector."
    )
    run_parser = subcommands.add_parser(
        "run",
        help="Score the detectors on every labeled recording and save a scorecard.",
    )
    run_parser.add_argument(
        "--rerun",
        action="store_true",
        help="Run every tool afresh instead of reusing its saved output, for "
        "example after remaking a logo file.",
    )
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(rerun=args.rerun)
    return _validate()


def look_ahead_detectors(data_folder: Path, rerun: bool) -> list[LookAheadDetector]:
    """Return the look-ahead detectors that ``run`` scores.

    Parameters
    ----------
    data_folder : Path
        The data folder, where tools' output is saved.
    rerun : bool
        Whether tools analyze every recording afresh instead of reusing their
        saved output.

    Returns
    -------
    list[LookAheadDetector]
        Comskip, run with the command its setting names. The join_logo_scp
        adapter is still to come.
    """
    return [
        ExternalTool(
            name="comskip",
            command=settings.comskip_command(),
            adapter=ComskipAdapter(),
            data_folder=data_folder,
            rerun=rerun,
        )
    ]


def candidates() -> list[Candidate]:
    """Return the candidates that ``run`` scores.

    Returns
    -------
    list[Candidate]
        None yet: no candidate ships in this milestone.
    """
    return []


def _run(rerun: bool) -> int:
    """Validate the recording set, score the detectors and log the scorecard.

    Parameters
    ----------
    rerun : bool
        Whether tools analyze every recording afresh instead of reusing their
        saved output.

    Returns
    -------
    int
        The exit code: 0 if the run found no errors; 1 if the recording set has
        errors, so nothing was run, or a detector failed on a recording.
    """
    data_folder = _log_locations()
    detectors = [*look_ahead_detectors(data_folder, rerun), *candidates()]
    if not detectors:
        logger.warning("No detectors to run yet.")
    result = benchmark.run(
        data_folder,
        settings.RECORDING_LIST,
        settings.LABELS_FOLDER,
        Ffprobe(),
        detectors,
        datetime.now().astimezone(),
    )
    _log_problems(result.validation)
    if result.scorecard is None:
        logger.error("Fix the errors above before running the benchmark.")
        return 1

    scorecard = result.scorecard
    logger.info(
        f"Scored {len(scorecard.recordings)} recordings: "
        f"{scorecard.hours:.1f} hours, "
        f"{scorecard.commercial_break_count} labeled commercial breaks"
    )
    for line in format_tables(scorecard):
        logger.info(line)
    failures = [
        (detector.name, file_name, message)
        for detector in scorecard.detectors
        for file_name, message in detector.errors.items()
    ]
    for name, file_name, message in failures:
        logger.error(f"{name} on {file_name}: {message}")
    logger.info(f"Saved the scorecard to {result.scorecard_path}")
    return 1 if failures else 0


def _log_locations() -> Path:
    """Log where the recordings, the list and the label files are read from.

    Returns
    -------
    Path
        The data folder.
    """
    data_folder = settings.data_folder()
    logger.info(f"Checking recordings in {data_folder / 'recordings'}")
    logger.info(f"Against the list of recordings in {settings.RECORDING_LIST}")
    logger.info(f"And the label files in {settings.LABELS_FOLDER}")
    return data_folder


def _log_problems(report: ValidationReport) -> None:
    """Log every warning and error validation found.

    Parameters
    ----------
    report : ValidationReport
        The validation report.
    """
    for warning in report.warnings:
        logger.warning(f"{warning.subject}: {warning.message}")
    for error in report.errors:
        logger.error(f"{error.subject}: {error.message}")


def _validate() -> int:
    """Validate the recording set and log what was found.

    Returns
    -------
    int
        The exit code: 0 if no errors were found, otherwise 1.
    """
    data_folder = _log_locations()
    report = validate(
        data_folder, settings.RECORDING_LIST, settings.LABELS_FOLDER, Ffprobe()
    )
    _log_problems(report)
    hours, minutes = divmod(round(report.total_length_seconds / 60), 60)
    logger.info(
        f"Checked {report.recording_count} listed recordings: "
        f"{report.hours:.1f} hours ({hours} h {minutes} min). "
        f"Skipped {report.skipped_count} not in the list, "
        f"errors {len(report.errors)}."
    )
    logger.info(
        f"Labeled {report.commercial_break_count} commercial breaks on "
        f"{len(report.channels)} channels: {', '.join(report.channels) or 'none'}. "
        f"Skipped {report.unlabeled_count} without a usable label file."
    )
    if report.channels_without_logo:
        logger.warning(
            "No logo file for join_logo_scp on these channels: "
            f"{', '.join(report.channels_without_logo)}. "
            f"Save each as {logo_file(data_folder, '<channel>')}."
        )
    return 1 if report.errors else 0
