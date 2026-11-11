# TV commercial detection

Telling commercial breaks apart from programs in Japanese TV broadcasts, live or from recordings.

## Language

### Broadcast content

**Program**:
The main program on air: the dramas, news, variety and other content listed in the TV guide, from its opening to the end of its own ending (theme song and ending credits). In-program advertising and shopping programs that fill a whole time slot (通販番組) count as program too. Everything else on air is part of a commercial break.
_Avoid_: show, main content

**Commercial**:
A single advertising spot, usually 15 or 30 seconds long. Includes spots from a program's sponsors (タイムCM), from other advertisers (スポットCM) and from public-service campaigns such as ACジャパン.
_Avoid_: ad, advert, CM, spot

**Commercial break**:
A continuous run of everything on air between two parts of a program, or between two programs: commercials, promos, sponsor credits, station IDs, next-episode previews and coming-up-next cards.
_Avoid_: break, ad break, CM break, non-program

**Promo**:
A spot advertising the channel's other programs, events or films (番宣). Part of a commercial break.
_Avoid_: trailer, teaser

**Station ID**:
A short channel identification or jingle. Part of a commercial break, wherever it sits.
_Avoid_: ident, bumper

**Sponsor credit**:
A card naming a program's sponsors (提供クレジット, "この番組は…の提供でお送りします"). Part of a commercial break whenever it is on screen, even when it is laid over the program.
_Avoid_: sponsor card, billboard

**Next-episode preview**:
A short look at the program's next episode (次回予告), shown after the program has ended. Part of a commercial break.
_Avoid_: trailer

**Coming-up-next card**:
A short card announcing the program that starts next (「このあとは」). Part of a commercial break.

**In-program advertising**:
Advertising that is part of the program itself, such as a segment marked「PR」 or product placement. Counts as program.
_Avoid_: tie-up

### Detection

**Detector**:
Anything that watches a recording or broadcast and reports when commercial breaks happen. Comes in two kinds: candidates and look-ahead detectors.
_Avoid_: entrant, model

**State**:
What a detector reports is on air at a given moment: `COMMERCIAL_BREAK`, `PROGRAM`, or `UNKNOWN` when it can't tell yet.
_Avoid_: status, mode

### Benchmark

**Recording**:
A saved broadcast, with its audio and video, used only for testing. The detector reads it exactly as if it were a live broadcast.
_Avoid_: capture, clip

**Fingerprint**:
A hash of a recording file's contents that identifies the recording whatever its file name. A recording that changes after labeling gets a new fingerprint, so its labels no longer match it.
_Avoid_: checksum, hash, recording ID

**Data folder**:
The folder, kept out of version control, that holds the benchmark's local and private files: recordings, logo files and saved tool output.
_Avoid_: data directory, media folder

**Label**:
A human-marked start and end of one commercial break in a recording. Between them, a recording's labels say what was really on air at every moment.
_Avoid_: annotation, tag

**Label file**:
The file in the repository holding one recording's labels and its channel. It belongs to its recording by fingerprint, not by file name.
_Avoid_: annotation file

**Logo file**:
An image of one channel's on-screen logo, made by hand from our own recordings, that join_logo_scp uses to tell when the logo is on screen.
_Avoid_: logo data

**Candidate**:
A detector being scored as a possible live detector. It never looks ahead.

**Look-ahead detector**:
A detector, usually an existing tool, that judges each moment using the whole recording, including what comes after that moment. Scored only for comparison and never used live.
_Avoid_: hindsight reference, baseline

**Entry delay**:
The time from a commercial break's labeled start until the detector reports `COMMERCIAL_BREAK`, including all processing and network time.
_Avoid_: start delay

**Exit delay**:
The time from a commercial break's labeled end until the detector reports `PROGRAM`, counted the same way as entry delay.
_Avoid_: end delay

**Startup delay**:
The time from when the detector starts, or its input resumes, until it reports what the labels say is on air at that moment.

**Test start**:
A moment in a recording where the benchmark starts a candidate cold to measure its startup delay: the middle of a long commercial break, or a moment inside a program away from any labeled edge. Every run picks the same ones.
_Avoid_: starting point, probe point

**Trial run**:
A short run of a candidate over the 15 s of broadcast from a test start, as opposed to its full run over the whole recording.

**Processing speed**:
How long the detector takes to process one second of broadcast, wherever it runs.

**Missed commercial break**:
A labeled commercial break during which the detector never reports `COMMERCIAL_BREAK`.

**False flip**:
A switch away from what the labels say, including a switch to `UNKNOWN`, that no labeled start or end caused. For example, reporting `COMMERCIAL_BREAK` in the middle of a program.
