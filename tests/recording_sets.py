"""A small recording set in temporary folders, for tests that drive ``run``.

It holds placeholder recordings, a list of recordings, label files and a fake
media probe, so a test can run the benchmark as a whole and read back the
scorecard it saves.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tv_commercial_detector.benchmark import run
from tv_commercial_detector.detectors import LookAheadDetector
from tv_commercial_detector.media_probe import ProbeResult

STARTED_AT = datetime(2026, 11, 8, 14, 3, 22, tzinfo=timezone(timedelta(hours=9)))


class FakeProbe:
    """Media probe that finds both tracks and the listed length in every recording."""

    def __init__(
        self, lengths: dict[str, float], frame_rates: dict[str, float] | None = None
    ) -> None:
        self.lengths = lengths
        self.frame_rates = frame_rates or {}

    def probe(self, path: Path) -> ProbeResult:
        """Return both tracks and the length and frame rate scripted for a recording.

        Parameters
        ----------
        path : Path
            The recording; only its file name is used.

        Returns
        -------
        ProbeResult
            Both tracks, the scripted length, and the scripted frame rate or
            none.
        """
        return ProbeResult(
            has_video=True,
            has_audio=True,
            length_seconds=self.lengths[path.name],
            frame_rate=self.frame_rates.get(path.name),
        )


@dataclass
class RecordingSet:
    """A recording set in temporary folders, built up one recording at a time."""

    root: Path
    data_folder_name: str = "data"
    lengths: dict[str, float] = field(default_factory=dict)
    frame_rates: dict[str, float] = field(default_factory=dict)

    @property
    def data_folder(self) -> Path:
        """The data folder."""
        return self.root / self.data_folder_name

    @property
    def recording_list(self) -> Path:
        """The list of recordings."""
        return self.root / "recordings.csv"

    @property
    def labels_folder(self) -> Path:
        """The folder of label files."""
        return self.root / "labels"

    def add(
        self,
        name: str,
        length_seconds: float,
        commercial_breaks: list[tuple[str, str]],
        channel: str = "TBS",
        frame_rate: float | None = None,
        content: bytes | None = None,
    ) -> None:
        """Add a placeholder recording, its row in the list and its label file.

        Parameters
        ----------
        name : str
            The recording's file name.
        length_seconds : float
            Its length, as listed and as the fake media probe reports it.
        commercial_breaks : list[tuple[str, str]]
            Its labeled commercial breaks, as written start and end times.
        channel : str
            Its channel.
        frame_rate : float | None
            Its frame rate as the fake media probe reports it, or ``None`` for
            a probe that can't tell.
        content : bytes | None
            The placeholder's bytes, which give its fingerprint; its file name
            when ``None``.
        """
        content = name.encode() if content is None else content
        fingerprint = hashlib.sha256(content).hexdigest()
        (self.data_folder / "recordings").mkdir(parents=True, exist_ok=True)
        (self.data_folder / "recordings" / name).write_bytes(content)
        if not self.recording_list.exists():
            self.recording_list.write_text(
                "file_name,size_bytes,fingerprint,length_seconds\n"
            )
        with self.recording_list.open("a") as f:
            f.write(f"{name},{len(content)},{fingerprint},{length_seconds}\n")
        self.labels_folder.mkdir(exist_ok=True)
        entries = ", ".join(
            f'{{ start = "{start}", end = "{end}" }}'
            for start, end in commercial_breaks
        )
        (self.labels_folder / f"{Path(name).stem}.toml").write_text(
            f'recording = "{fingerprint}"\n'
            f'channel = "{channel}"\n'
            f"commercial_breaks = [{entries}]\n"
        )
        self.lengths[name] = length_seconds
        if frame_rate is not None:
            self.frame_rates[name] = frame_rate

    def probe(self) -> FakeProbe:
        """Return a fake media probe that knows this set's recordings.

        Returns
        -------
        FakeProbe
            Reports both tracks and each recording's length and frame rate.
        """
        return FakeProbe(self.lengths, self.frame_rates)

    def run(
        self, *detectors: LookAheadDetector, started_at: datetime = STARTED_AT
    ) -> dict:
        """Run the benchmark and return the scorecard it saved.

        Parameters
        ----------
        *detectors : LookAheadDetector
            The detectors to score.
        started_at : datetime
            When the run starts.

        Returns
        -------
        dict
            The saved scorecard, read back from its JSON file.
        """
        result = run(
            self.data_folder,
            self.recording_list,
            self.labels_folder,
            self.probe(),
            list(detectors),
            started_at,
        )
        assert result.validation.errors == []
        assert result.scorecard_path is not None
        return json.loads(result.scorecard_path.read_text())
