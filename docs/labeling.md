# Labeling a recording

How to write the label file for one recording, so the benchmark ([#7](https://github.com/hankehly/tv-commercial-detector/issues/7)) knows where its commercial breaks are. What counts as a commercial break is set by the [glossary](../GLOSSARY.md) and [ADR 0002](adr/0002-what-counts-as-a-commercial-break.md): everything around the main program (commercials, promos, sponsor credits, station IDs, next-episode previews and coming-up-next cards). In-program advertising and whole-slot shopping programs count as program.

## Steps

1. Run `uv run tv-commercial-detector validate`. If the recording isn't in the list of recordings yet, the warning shows the row to add to `benchmark/recordings.csv`. Add it.
2. Create `benchmark/labels/<recording name>.toml`, for example `benchmark/labels/2026-11-01_10-56-55.toml`. The name is only for people. The benchmark matches the file to its recording by fingerprint.
3. Copy the recording's fingerprint from `benchmark/recordings.csv` into `recording`, write the channel, and list each commercial break's start and end while scrubbing through the video.
4. Run `validate` again and fix anything it reports.

## Example

```toml
recording = "a24b31a34ad5c13200e232abee93f71390f1b71d468464719e85f26221ed91fd"
channel = "TBS"
commercial_breaks = [
  { start = "00:12:03.2", end = "00:15:03" },
  { start = "00:27:45", end = "00:30:15.5" },
]
```

A recording with no commercial breaks is written `commercial_breaks = []`.

| Field | Required | What to write |
|---|---|---|
| `recording` | Yes | The recording's fingerprint, copied from the list of recordings |
| `channel` | Yes | The channel's name, written the same way in every label file (for example `TBS`, `TV Asahi`, `NTV`, `Fuji TV`, `TV Tokyo`). It also names the channel's logo file |
| `commercial_breaks` | No (empty when left out) | One `{ start = "…", end = "…" }` per commercial break, in any order |

Times are written `hh:mm:ss`, optionally with tenths (`00:12:03.2`), in quotes, counted from the start of the recording as a video player shows them. A commercial break still running when the recording ends ends at the recording's length, rounded up to the next tenth. Save the file as UTF-8, the default in most editors.

## What `validate` rejects

Each error names the label file and the commercial break (its number in the file and its times as written).

| Problem | Example |
|---|---|
| A time that can't be read | `"00:61:00"`, `"12:03"`, `"00:12:03.25"`, or a time without quotes |
| An end that isn't after its start | `{ start = "00:15:00", end = "00:15:00" }` |
| Commercial breaks that overlap, or touch (one ends exactly where the next starts) | Touching ones are one commercial break: join them |
| A time past the end of the recording | Checked against the length in the list of recordings, rounded up to the next tenth |
| A fingerprint that isn't in the list of recordings | Usually a copying mistake |
| Two label files with the same fingerprint | A recording has one label file |
| A missing or misspelled field | `commercial_break = [...]` instead of `commercial_breaks` |

A recording without a usable label file is skipped with a warning, so `validate` and `run` still work on a partly labeled set. Label files are checked even when the data folder is missing, for example while its drive is unplugged.

## Logo files

join_logo_scp needs one logo file per channel, made by hand from our own recordings. Put each in the data folder's `logos/` folder, named after the channel exactly as the label files write it, with the `.lgd` extension:

```
data/
├── recordings/
│   └── 2026-11-01_10-56-55.mp4
└── logos/
    ├── TBS.lgd
    └── TV Asahi.lgd
```

`validate` lists every labeled channel that has no logo file yet. A channel name can't contain `/` or `\`, or start or end with a space, since it is part of a file name.
