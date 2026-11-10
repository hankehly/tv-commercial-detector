# Installing Comskip and join_logo_scp

How to set up Comskip and join_logo_scp on this Mac, so the benchmark ([#7](https://github.com/hankehly/tv-commercial-detector/issues/7)) can run them on our recordings. It's a one-time step, outside the project's Python environment.

In one line: both tools run in Docker, each behind a small command in `tools/` that the benchmark's settings point to.

## What you need

| Part | Tested with (2026-11-08) |
|---|---|
| Mac | MacBook Pro, Apple M1 Pro, 32 GB, macOS 27.2 |
| Docker | Docker Desktop 4.97.0 (Docker Engine 29.9.2) |
| Docker setting | **Use Rosetta for x86_64/amd64 emulation on Apple Silicon** turned on (Settings → General), because join_logo_scp's setup is only built for Intel processors |

Nothing is installed with Homebrew, and the Python environment isn't touched.

## One-time setup

From the repository root:

1. Build Comskip's image. It takes a minute or two.

   ```bash
   docker build --tag tv-commercial-detector/comskip tools/comskip
   ```

2. Build join_logo_scp's image. It takes about 5 minutes, plus downloading its base image, since it is built for Intel processors and runs through Rosetta.

   ```bash
   docker build --platform linux/amd64 --tag tv-commercial-detector/join_logo_scp tools/join_logo_scp
   ```

3. Point the benchmark at the two commands, for example in your shell profile. Use full paths, so they work from any folder:

   ```bash
   export TV_COMMERCIAL_DETECTOR_COMSKIP_COMMAND="$HOME/Projects/tv-commercial-detector/tools/comskip-docker"
   export TV_COMMERCIAL_DETECTOR_JOIN_LOGO_SCP_COMMAND="$HOME/Projects/tv-commercial-detector/tools/jlse-docker"
   ```

Docker Desktop must be running whenever the benchmark runs a tool. The version of each tool is fixed in its Dockerfile; to change it, edit the Dockerfile and build again with the same command.

## The two commands

join_logo_scp is three programs run in turn by a script called jlse, which comes with its Linux setup: chapter_exe finds silences and scene changes, logoframe finds when the channel's logo is on screen, and join_logo_scp decides the cuts.

| Command | Takes | Writes |
|---|---|---|
| `tools/comskip-docker` | The same arguments as `comskip` | What Comskip would write if it were installed here: `<recording>.txt` and any other output files, in the folder given by `--output=`, or else next to the recording |
| `tools/jlse-docker` | A recording and its channel's logo file: `jlse-docker RECORDING LOGO` | jlse's results, in the current folder. `obs_cut.avs` lists the frames join_logo_scp keeps, and `obs_logoframe.txt` when the logo was on screen |

- **comskip-docker** shows Comskip the current folder, and the folder of every file named in its arguments, at the same paths they have on the Mac. If a file is a symbolic link, it also shows the folder of each file the link leads to. So anything that works with Comskip installed here works with `comskip-docker`, with one exception: a relative link that climbs out, with `..`, of the linked folder it sits in.
- **jlse-docker** runs all three programs with their default settings. It exits with an error naming the program if any of them wrote no output, or if chapter_exe stopped before the end of the recording.
- Both run their tool without network access, and remove the container when it finishes. If Docker Desktop isn't running, or an image isn't built, both stop straight away and say so.

Comskip's exit code says whether it found anything, so a successful run doesn't always end with 0:

| Exit code | Comskip on macOS or Linux | Its `.txt` file |
|---|---|---|
| 0 | Found at least one commercial break | Complete |
| 1 | Found no commercial breaks | Complete |
| 255 | Couldn't open the recording | Empty |

On Windows, 0 and 1 are the other way round. The benchmark's Comskip adapter ([#24](https://github.com/hankehly/tv-commercial-detector/issues/24)) accepts 0 and 1, and then reads the `.txt` file; if that file isn't complete, the run is recorded as an error and tried again next time. Any other exit code is an error.

## Check that it works

Run each command from an empty folder, since both write their results there, giving the full path of a recording in the data folder:

| Run | You should see |
|---|---|
| `"$TV_COMMERCIAL_DETECTOR_COMSKIP_COMMAND" --output="$PWD" RECORDING` | A file named after the recording, ending `.txt`, whose first line starts `FILE PROCESSING COMPLETE`, and exit code 0 or 1 (see above) |
| `"$TV_COMMERCIAL_DETECTOR_JOIN_LOGO_SCP_COMMAND" RECORDING LOGO` | Without a real logo file, the run stops at logoframe with `logoframe wrote no obs_logoframe.txt`. With one, it should end with `obs_cut.avs` and exit code 0; that hasn't been tried yet, as no logo file exists yet ([#22](https://github.com/hankehly/tv-commercial-detector/issues/22)) |

How long the tools took on the 89-minute pilot recording `2026-11-01_17-01-22.mp4`:

| Tool | Time | Notes |
|---|---|---|
| Comskip | 11 minutes | 355 frames a second. It went through the recording three times: by default Comskip starts again from the beginning once it has found the channel's logo, and once more if that logo then disappears for over 12 minutes |
| join_logo_scp, up to logoframe | 1.5 minutes | Reading the recording and finding its silences. logoframe's pass over every frame, which needs a real logo file, isn't timed yet |

## What didn't work as the guides say

| The guides say | What happened | What we do instead |
|---|---|---|
| Build join_logo_scp's setup with `docker-compose up --build` | The build fails at its last step. NodeSource's `setup_10.x` script, which installs Node.js 10, is retired, and its package signatures no longer verify | The same Dockerfile, but with Node.js 10.19 from Ubuntu 20.04's own packages (`tools/join_logo_scp/Dockerfile`) |
| Run `jlse -i FILE.ts` | jlse refuses any file whose name doesn't end `.ts`: `invalid file extension .mp4.` | `jlse-docker` shows the recording to jlse as `recording.ts`. jlse's video reader (L-SMASH Works) recognizes an MP4 file by its content, not its name, and reads its picture and sound correctly |
| jlse picks the channel's logo, and settings tuned for some channels, from the channel name in the file name | Our file names hold only the start time | `jlse-docker` puts the given logo file alone in jlse's logo folder, which jlse then uses as a whole. With no channel in the name, jlse always uses its default settings (`JL_標準.txt`). Of our channels, only TBS has settings of its own (`JL_MBS.txt`), which it doesn't get |
| — | jlse runs each program even when the one before it failed. When logoframe failed, join_logo_scp still wrote a cut list from silences and scene changes alone, which looks like a real result: on the 89-minute pilot recording it cut 11 commercial breaks. jlse only exited with an error because it then crashed on a file logoframe should have written. And chapter_exe writes its results as it goes, so if it stops partway, the programs after it carry on with part of them: with chapter_exe stopped 18 minutes into the pilot recording, join_logo_scp kept only those 18 minutes | `jlse-docker` checks that each program wrote its output, and that chapter_exe's ends with the `# SCPos:` line it writes only once it has read the whole recording. It exits with an error naming the first program that didn't finish |

### Why Comskip runs in Docker too

Comskip's guide builds it on the Mac from source, with its dependencies from Homebrew. That wasn't tried. Comskip has no Homebrew formula of its own, and its macOS builds are only checked against FFmpeg 5 to 7, which Homebrew still offers as `ffmpeg@6` and `ffmpeg@7` beside its default 9.0. Building it in an Ubuntu 24.04 image instead, the way Comskip's own Linux checks do, keeps its build tools off the Mac and sets both tools up the same way.

## Appendix: versions

| Part | Version |
|---|---|
| Comskip | 0.83.001: [erikkaashoek/Comskip](https://github.com/erikkaashoek/Comskip) at `a140b6a` (2025-04-18), the newest commit, built against FFmpeg 6.1.1 on Ubuntu 24.04 |
| JoinLogoScpTrialSetLinux | [tobitti0/JoinLogoScpTrialSetLinux](https://github.com/tobitti0/JoinLogoScpTrialSetLinux) at `aabb505` (2026-03-02), the newest commit |
| join_logo_scp | 4.0.0, tobitti0's fork at `646a0fd` |
| jlse (join_logo_scp_trial) | `c38e970` |
| chapter_exe | `d74f65f` |
| logoframe | 1.20, `c93aec0` |
| tsdivider | 0.3.1, `a16dbcb` (not used with the default settings) |
| delogo-AviSynthPlus-Linux | `e55cfa2` (only used to encode, which the benchmark doesn't) |
| AviSynth+, L-SMASH Works, FFmpeg | From the setup's base image, `ghcr.io/tobitti0/docker-avisynthplus:4.3.1-ubuntu2004`: AviSynth+ 3.6.1, FFmpeg 4.3.1 |
| Node.js | 10.19.0, npm 6.14.4 |
