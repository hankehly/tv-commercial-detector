# TV commercial detection

Telling commercial breaks apart from programs in Japanese TV broadcasts, live or from recordings.

## Language

### Broadcast content

**Program**:
Everything on air that isn't a commercial break: the dramas, news, variety and other content listed in the TV guide, plus the short pieces around them such as next-episode previews (次回予告), sponsor credits and station IDs. In-program advertising and shopping programs that fill a whole time slot (通販番組) count as program too.
_Avoid_: show, main content

**Commercial**:
A single advertising spot, usually 15 or 30 seconds long. Includes spots from a program's sponsors (タイムCM), from other advertisers (スポットCM) and from public-service campaigns such as ACジャパン.
_Avoid_: ad, advert, CM, spot

**Commercial break**:
A continuous run of commercials and promos between two parts of a program, or between two programs.
_Avoid_: break, ad break, CM break

**Promo**:
A spot advertising the channel's other programs, events or films (番宣). Part of a commercial break.
_Avoid_: trailer, teaser

**Station ID**:
A short channel identification or jingle. Counts as program, even when it sits right next to a commercial break.
_Avoid_: ident, bumper

**Sponsor credit**:
A card naming a program's sponsors (提供クレジット, "この番組は…の提供でお送りします"). Counts as program, even when it sits right next to a commercial break.
_Avoid_: sponsor card, billboard

**In-program advertising**:
Advertising that is part of the program itself, such as a segment marked「PR」 or product placement. Counts as program.
_Avoid_: tie-up

### Detection

**State**:
What the detector reports is on air at a given moment: `COMMERCIAL_BREAK`, `PROGRAM`, or `UNKNOWN` when it can't tell yet.
_Avoid_: status, mode

### Benchmark

**Recording**:
A saved broadcast, with its audio and video, used only for testing. The detector reads it exactly as if it were a live broadcast.
_Avoid_: capture, clip

**Label**:
A human-marked start and end of one commercial break in a recording. Between them, a recording's labels say what was really on air at every moment.
_Avoid_: annotation, tag

**Candidate**:
A detector being scored as a possible live detector. It never looks ahead.

**Hindsight reference**:
An existing tool that judges each moment using the whole recording. Scored only for comparison and never used live.
_Avoid_: baseline

**Entry delay**:
The time from a commercial break's labeled start until the detector reports `COMMERCIAL_BREAK`, including all processing and network time.
_Avoid_: start delay

**Exit delay**:
The time from a commercial break's labeled end until the detector reports `PROGRAM`, counted the same way as entry delay.
_Avoid_: end delay

**Startup delay**:
The time from when the detector starts, or its input resumes, until it reports what the labels say is on air at that moment.

**Processing speed**:
How long the detector takes to process one second of broadcast, wherever it runs.

**Missed commercial break**:
A labeled commercial break during which the detector never reports `COMMERCIAL_BREAK`.

**False flip**:
A switch away from what the labels say, including a switch to `UNKNOWN`, that no labeled start or end caused. For example, reporting `COMMERCIAL_BREAK` in the middle of a program.
