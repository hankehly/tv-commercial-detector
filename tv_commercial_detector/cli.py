"""The command-line entry point and its subcommands."""

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
from loguru import logger

from tv_commercial_detector import benchmark, settings
from tv_commercial_detector.comskip import ComskipAdapter
from tv_commercial_detector.detectors import Candidate, LookAheadDetector
from tv_commercial_detector.external_tool import ExternalTool
from tv_commercial_detector.frame_sampler import sample_corner
from tv_commercial_detector.labels import channel_problem
from tv_commercial_detector.logo_file import write_logo_file
from tv_commercial_detector.logo_maker import (
    Box,
    LogoError,
    measure_logo,
    still_pictures,
)
from tv_commercial_detector.media_probe import Ffprobe
from tv_commercial_detector.pictures import logo_preview, with_rulers, write_png
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
    logo_parser = subcommands.add_parser(
        "make-logo",
        help="Make a channel's logo file for join_logo_scp from our recordings.",
        description="Make a channel's logo file for join_logo_scp. Run it first "
        "without --box: it saves a picture of what stays put in the top right "
        "corner. Find the logo in that picture, then run it again with --box.",
    )
    logo_parser.add_argument(
        "channel", help="The channel, written as in the label files."
    )
    logo_parser.add_argument(
        "recordings",
        nargs="+",
        metavar="recording",
        help="A recording of the channel: a path, or the name of a file in the "
        "data folder's recordings folder.",
    )
    logo_parser.add_argument(
        "--box",
        type=_box,
        metavar="X,Y,WIDTH,HEIGHT",
        help="A box around the logo with some room to spare, in pixels of the "
        "picture, holding nothing else that stays on screen.",
    )
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(rerun=args.rerun)
    if args.command == "make-logo":
        return _make_logo(args.channel, args.recordings, args.box)
    return _validate()


def _box(value: str) -> Box:
    """Read ``--box``.

    Parameters
    ----------
    value : str
        The box as typed: ``X,Y,WIDTH,HEIGHT``.

    Returns
    -------
    Box
        The box.

    Raises
    ------
    argparse.ArgumentTypeError
        If it isn't four whole numbers separated by commas.
    """
    try:
        x, y, width, height = (int(number) for number in value.split(","))
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            "--box takes four whole numbers: X,Y,WIDTH,HEIGHT"
        ) from e
    return Box(x, y, width, height)


def _make_logo(channel: str, recordings: list[str], box: Box | None) -> int:
    """Make a channel's logo file, or the picture to find its logo in.

    Parameters
    ----------
    channel : str
        The channel, written as in the label files.
    recordings : list[str]
        Recordings of the channel, as paths or as names of files in the data
        folder's recordings folder.
    box : Box | None
        A box drawn around the logo, or ``None`` to save the picture that
        shows where the logo is.

    Returns
    -------
    int
        The exit code: 0 if the picture or the logo file was saved, otherwise
        1.
    """
    data_folder = settings.data_folder()
    problem = channel_problem(channel)
    if problem:
        logger.error(problem)
        return 1
    found = []
    for name in recordings:
        in_folder = data_folder / "recordings" / name
        path = Path(name) if Path(name).is_file() else in_folder
        if not path.is_file():
            logger.error(
                f"no such recording: {name} (also looked in {in_folder.parent})"
            )
            return 1
        found.append(path)

    path = logo_file(data_folder, channel)
    try:
        frames = sample_corner(found)
        if box is None:
            picture = path.with_suffix(".still.png")
            path.parent.mkdir(parents=True, exist_ok=True)
            usually, when_calm = still_pictures(frames)
            write_png(
                picture,
                np.vstack(
                    [
                        with_rulers(usually, frames.x, frames.y),
                        with_rulers(when_calm, frames.x, frames.y),
                    ]
                ),
            )
            logger.info(f"Saved a picture of what stays put in the corner to {picture}")
            logger.info(
                "Its top half shows what is there in most frames, its bottom "
                "half what is there over calm scenes"
            )
            logger.info(
                "Find the logo in it, read a box around it off the rulers, and "
                "run this again with --box X,Y,WIDTH,HEIGHT"
            )
            return 0
        measured = measure_logo(channel, frames, box)
    except LogoError as e:
        logger.error(str(e))
        return 1

    logo = measured.logo
    logger.info(
        f"Measured the logo from {measured.frames_used} frames that show it over "
        "plain surroundings"
    )
    logger.info(
        f"Their backgrounds run from level {measured.darkest:.0f} to "
        f"{measured.brightest:.0f} (16 is black, 235 white)"
    )
    logger.info(
        f"Its box is {Box(logo.x, logo.y, logo.width, logo.height)} "
        f"(x,y,width,height) and it is up to {logo.opacity.max():.0%} opaque"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_logo_file(path, logo)
    logger.info(f"Saved the logo file to {path}")
    preview = path.with_suffix(".png")
    write_png(preview, logo_preview(logo))
    logger.info(
        f"Saved a picture of it to {preview}: check that it shows the channel's "
        "whole logo and nothing else"
    )
    return 0


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
            "Make each with the make-logo command, which saves it as "
            f"{logo_file(data_folder, '<channel>')}."
        )
    return 1 if report.errors else 0
