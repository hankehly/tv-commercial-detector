# Making a recording

How to record Japanese TV on this Mac, picture and sound, while you keep using the computer for other things. The result is an MP4 file the benchmark ([#7](https://github.com/hankehly/tv-commercial-detector/issues/7)) can use as a recording.

In one line: the XIT stick receives the broadcast, the Xit Mobile app shows it in a window, and OBS records that one window and that one app's sound.

## What you need

| Part | Tested with (2026-11-01) |
|---|---|
| Tuner | Pixela Xit Stick **XIT-STK110** (USB ID `06b8:105a`) |
| Viewer | Xit Mobile 1.1.3, the newest version; Intel-only, runs through Rosetta 2 |
| Recorder | OBS Studio 33.0.1 |
| Mac | MacBook Pro (Apple silicon) on macOS 26.6.2, using its built-in display |

BlackHole and other audio routing are not needed. The old audio-only setup used them; OBS now takes the sound straight from Xit Mobile.

## What you can do while it records

Tested by doing each of these during short test recordings, plus a 30-minute recording, a 7.5-hour daytime run and a 9-hour overnight run, and then measuring the files (see the appendix).

| While recording, you… | Picture | Sound | OK? |
|---|---|---|---|
| Work in other apps in front of the Xit Mobile window | Recorded | Recorded | Yes |
| Leave the Mac alone for hours (awake and unlocked) | Recorded the whole time (tested for 7.5 hours by day and 9 hours overnight) | Recorded the whole time | Yes |
| Mute the Mac or set its volume to 0 | Recorded | Still recorded | Yes |
| Play other sounds (music, videos, alerts) | Not affected | Not recorded: only Xit Mobile's sound is | Yes |
| Put Xit Mobile in full screen | Recorded, with a 2-second freeze when leaving full screen | Recorded | Yes |
| Switch to another desktop (Space) | Kept recording while away, then froze on coming back | Recorded | Only if you click the Xit Mobile picture when you come back |
| Minimize Xit Mobile, or hide it (⌘H) | Frozen while minimized or hidden; moves again once shown | Recorded | No |
| Turn the display off (which also locked the screen) | Frozen until the display was woken | Recorded | No |
| Quit or restart Xit Mobile | Frozen on the last frame | Silent | No: pick the window again in OBS ("Every time", step 2) |

The rule of thumb: keep Xit Mobile open and on the desktop you work on (other windows can cover it), and keep the Mac awake and unlocked. If its picture ever stops moving, click the picture and it starts again.

## One-time setup

### 1. Xit Mobile

1. Install Xit Mobile from [Pixela's download page](https://jvcdl.pixela.co.jp/products/xit/stk110/download_mac.html) and finish its first-run setup (area and channel scan).
2. Show it on the Mac's built-in display. Pixela doesn't support showing the picture on an external display from an Apple silicon Mac, and doesn't support the Apple silicon Mac mini at all ([notice](https://jvcdl.pixela.co.jp/support/info/2021/m1_mac.html)).
3. Keep its window at least 960 points wide; the default 1028 × 607 is fine. OBS records the window at its size on screen (twice its size in points on a Retina display), so a smaller window gives a blurrier recording.

### 2. Let OBS record the screen

System Settings → Privacy & Security → **Screen & System Audio Recording** → turn on **OBS**, then quit and reopen OBS. If macOS asks again later, allow it.

### 3. OBS settings

These are all the recording settings in our OBS profile on 2026-11-01. Open them with OBS → Settings.

| Page | Setting | Value | Why |
|---|---|---|---|
| Output | Output Mode | Advanced | Shows the recording settings below |
| Output → Recording | Type | Standard | |
| Output → Recording | Recording Path | the `data/recordings/` folder at the root of this repository | git ignores `data/`; recordings are large and copyrighted |
| Output → Recording | Generate File Name without Space | On | Files are named like `2026-11-01_07-07-22.mp4` |
| Output → Recording | Recording Format | Hybrid MP4 (.mp4) | Plays like a normal MP4 but stays readable if OBS crashes |
| Output → Recording | Audio Track | 1 only | One stereo track |
| Output → Recording | Video Encoder | Apple VT H264 Hardware Encoder | Uses the Mac's video chip, so OBS needs only about 28% of one CPU core |
| Output → Recording | Audio Encoder | CoreAudio AAC | |
| Output → Recording | Rescale Output | Disabled | The canvas is already 1920×1080 |
| Output → Recording | Automatic File Splitting | Off | A split in the middle of a commercial break would cut its label in two |
| Output → Recording (encoder) | Rate Control, Bitrate | CBR, 6000 Kbps | Steady quality; about 2.8 GB per hour including sound |
| Output → Recording (encoder) | Keyframe Interval (0=auto) | 2 | A keyframe every 2 s, so a video player can jump to any point quickly while labeling |
| Output → Recording (encoder) | Profile | high | |
| Output → Recording (encoder) | Limit bitrate | Off | Other encoder settings are left at their defaults |
| Output → Audio | Track 1 Audio Bitrate | 160 | AAC stereo at 160 kbps |
| Output → Replay Buffer | Enable Replay Buffer | Off | Not used |
| Audio | Sample Rate | 48 kHz | Broadcast audio rate |
| Audio | Channels | Stereo | |
| Audio | Desktop Audio and Mic/Auxiliary Audio | Disabled | Otherwise the microphone or a second copy of the sound gets mixed in |
| Video | Base (Canvas) Resolution | 1920x1080 | Full HD |
| Video | Output (Scaled) Resolution | 1920x1080 | Same as the canvas, so no extra scaling |
| Video | Downscale Filter | Bicubic (Sharpened scaling, 16 samples) | Only matters if the two resolutions differ |
| Video | Common FPS Values | 29.97 | Japanese broadcast frame rate |
| Advanced | Recording → Filename Formatting | `%CCYY-%MM-%DD %hh-%mm-%ss` (the default) | Date and time the recording started |
| Advanced | Video → Color Format, Color Space, Color Range | NV12, Rec. 709, Limited | Standard HD video |

### 4. Add Xit Mobile as a source

Our scene collection has a single scene, `Scene`, with one source, `macOS Screen Capture`, and no filters.

1. With Xit Mobile open, click **+** under **Sources** → **macOS Screen Capture**, and set:

| Setting | Value | Why |
|---|---|---|
| Method | Window Capture | Records just the Xit Mobile window, wherever it is on the desktop and whatever covers it |
| Window | The Xit Mobile window | Pick it again on each Mac, and whenever Xit Mobile has restarted |
| Show fullscreen and hidden windows / applications | On | |

2. OBS 33 has no "Capture Audio" box: Window Capture records the app's sound by itself. The Audio Mixer should show a single meter, "macOS Screen Capture", moving with the TV sound. In Edit → Advanced Audio Properties, leave it at 0 dB, Sync Offset 0 ms, Audio Monitoring "Monitor Off", all Tracks ticked.
3. Select the source, then Edit → Transform → **Edit Transform…** (⌘E), and set:

| Field | Value | Why |
|---|---|---|
| Position | 0, 0 | |
| Alignment | Top Left | |
| Bounds Type | Fit | The picture keeps filling the 1920×1080 frame even if the window size changes |
| Bounds Alignment | Center | |
| Bounding Box Width / Height | 1920 / 1080 | |
| Crop Top | 56 (Left, Right and Bottom 0) | Removes Xit Mobile's 28-point title bar, recorded at 2× on a Retina display. What is left is the 16:9 picture |
| Crop Bounds | Off | |

Don't rely on "Fit to screen" (⌘F) alone: it scales once, for the window size at that moment.

### Moving to another Mac

Either set everything by hand from the tables above (the tables are the source of truth), or copy OBS's own files. Copying hasn't been tried yet:

1. On this Mac, use **Profile → Export Profile** and **Scene Collection → Export Scene Collection**.
2. The exported profile also holds the streaming settings, including the stream key (`service.json`). Delete that file from the export, and never commit the export to git.
3. On the new Mac, do the Xit Mobile setup and the screen recording permission above, then **Profile → Import Profile** and **Scene Collection → Import Scene Collection**, and choose both in the Profile and Scene Collection menus.
4. Then fix what is tied to this Mac: set **Recording Path** to the new repository's `data/recordings/` folder, and pick the Xit Mobile window again in the source. If the new display isn't Retina, use Crop Top 28 instead of 56.

## Every time

| Step | Do | Check |
|---|---|---|
| 1 | Open Xit Mobile and choose the channel from its 選局 menu | The picture moves |
| 2 | Open OBS | The preview shows the moving picture and the "macOS Screen Capture" meter moves. If the preview is black or frozen, double-click the source, pick the Xit Mobile window again (its ID changes whenever Xit Mobile restarts), and click OK |
| 3 | Click **Start Recording** | The recording timer at the bottom of OBS counts up |
| 4 | Carry on with other work. Leave Xit Mobile on the same desktop, covered by other windows if you like, and mute the Mac if you want quiet. Don't lock the screen or turn the display off | |
| 5 | Glance at Xit Mobile now and then, and always after switching desktops | If its picture is frozen, click the picture |
| 6 | Click **Stop Recording** | A new `.mp4` appears in `data/recordings/` |
| 7 | Check the recording ("Check a recording" below) | Both commands print nothing |

### Recording another channel

To record several channels in one sitting, give each channel its own file. Each switch leaves a short gap between the two files: 23 s to 75 s across four switches in testing.

| Step | Do | Check |
|---|---|---|
| 1 | Click **Stop Recording** | |
| 2 | In Xit Mobile's menu bar, choose 選局 → チャンネルダウン or チャンネルアップ. Each moves one channel, in channel-number order: in testing, チャンネルダウン went Fuji TV (8), TV Tokyo (7), TBS (6), TV Asahi (5), NTV (4) | Within 30 s the new channel's picture moves in OBS's preview. If Xit Mobile shows a message with コード：EC21 first, wait (see Troubleshooting) |
| 3 | Click **Start Recording** | The recording timer at the bottom of OBS counts up |
| 4 | Write down which channel the new file holds | File names only have the start time, and a channel logo isn't always on screen to tell later |

Xit Mobile keeps the same window when it changes channel, so there's no need to pick the window again in OBS.

## Check a recording

Run both from the repository root, replacing `FILE` with the recording's file name:

```bash
ffmpeg -hide_banner -nostats -i data/recordings/FILE.mp4 -vf "freezedetect=n=-50dB:d=10,blackdetect=d=5" -af "silencedetect=n=-60dB:d=5" -f null - 2>&1 | grep -E "freeze_start|black_start|silence_start"
```

```bash
ffprobe -v error -select_streams a:0 -show_entries packet=pts_time -of csv=p=0 data/recordings/FILE.mp4 | awk -F, 'NR > 1 && $1 - prev > 0.032 { print "audio gap at", prev, "s:", $1 - prev, "s" } { prev = $1 }'
```

No output from either command means the recording passed. Each line the first command prints names the problem and when it started, in seconds from the start of the recording:

| Output contains | Means | What to do |
|---|---|---|
| `freeze_start: T` | The picture didn't change for 10 s or more, starting at T | Watch from T. If Xit Mobile froze, cut that part or record again. Still graphics in the broadcast also cause this: in testing, a weather map and a painting each stayed on screen for about 11 s |
| `black_start:T` | The picture was black for 5 s or more (a black stretch of 10 s or more also shows up as a freeze) | Watch from T. If the picture comes back by itself and the sound plays throughout, it was a dark scene in the broadcast (a 7.6 s one in testing). If it stays black, the source lost the Xit Mobile window; see step 2 of "Every time" |
| `silence_start: T` | No sound for 5 s or more | Check the source's meter. The short silences around commercial breaks are too short to show up here |
| `audio gap at …` | Sound samples are missing (a jump of more than 32 ms, 1.5 × the 21.3 ms audio frame) | Record again. This didn't happen in testing |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| OBS preview is black but the meter moves | The source points at an old Xit Mobile window, or the transform is wrong | Pick the window again ("Every time", step 2), then redo Edit Transform (setup step 4) |
| Recording has a frozen picture but normal sound | Xit Mobile stopped redrawing after being minimized or hidden, after a desktop switch, or while the display was off | Click the Xit Mobile picture. Don't minimize or hide it, and keep the Mac awake |
| Recording has a frozen picture and no sound | Xit Mobile was quit or restarted, so OBS lost its window. Restarting OBS doesn't help | Pick the window again ("Every time", step 2) |
| Picture doesn't fill the frame, or is cut off | The transform was set with "Fit to screen" for a different window size | Redo Edit Transform with Bounds Type: Fit |
| Picture is black after editing OBS's scene file by hand | Recent OBS versions (33 here) also store relative `pos_rel`, `scale_rel` and `bounds_rel` values that override the absolute ones | Change transforms in OBS itself, not in the JSON file |
| Xit Mobile stops the picture with a message that a screen capture application was detected | Xit Mobile's copy protection noticed a recording app | Stop recording; see "Copy protection" below |
| After a channel change, Xit Mobile shows 「受信制御データが設定されていません。」 with コード：EC21 | Xit Mobile hasn't received the new channel's reception control data yet; the message says this can take up to 30 s | Wait. In testing it cleared by itself in under 30 s. Start recording only once the picture moves |

## Things to know

- **Copy protection.** Pixela's [XIT-STK110 Mac Q&A](https://jvcdl.pixela.co.jp/products/xit/stk110/qa_mac.html) says the TV picture can't be recorded as video, for copyright protection, and that Xit Mobile stops showing the picture when it detects a screen capture app. Its message begins 「画面キャプチャアプリケーションの起動を検出したため」. Xit Mobile didn't react to OBS in our testing, so this setup works because that check doesn't notice OBS, not because Pixela allows it. If Xit Mobile ever shows that message or blacks out its picture, stop there and don't try to hide OBS from it. Recordings are copyrighted broadcasts: keep them in the git-ignored `data/recordings/` folder and use them only for testing.
- **Why the picture freezes.** Xit Mobile draws the TV picture inside an embedded web page, and macOS probably pauses drawing it while the window is minimized, hidden or out of view. It usually starts again by itself once the window is visible; after a desktop switch it needed a click.
- **Keeping the Mac awake.** While recording, OBS and Xit Mobile both tell macOS to keep the display on (visible in `pmset -g assertions`), so the Mac doesn't go to sleep by itself. Running `caffeinate -di` alongside is optional.
- **Xit Mobile's own recorder is no substitute.** Pixela says its recordings play only inside Xit Mobile on the Mac that made them, so other tools can't read them.
- **No Apple silicon version, and support may end after macOS 27.** The newest Xit Mobile for Mac is 1.1.3, released 2024-04-22, and it is Intel-only. Pixela supports Apple silicon Macs through Rosetta 2. Its newest macOS support notice is for Ventura (13); this setup was tested on macOS 26.6.2, which Pixela doesn't list. Apple keeps Rosetta generally available only through macOS 27; from macOS 28 it will only cover a limited set of older games ([MacRumors](https://www.macrumors.com/2025/06/10/apple-to-phase-out-rosetta-2/)). Unless Pixela ships an Apple silicon version, expect this setup to stop working on macOS 28.
- **Computer load.** Xit Mobile uses about 75% of one CPU core and OBS about 28% of one, in the 30-minute test and through both long runs.
- **Recording overnight.** First open System Settings → General → Software Update → Automatic Updates and turn off **Install macOS updates**, then turn it back on in the morning. macOS can install a waiting update overnight and restart the Mac, which would end the recording. The overnight test ran this way, on a night when an update that needed a restart was waiting.
- **Not tested yet:** locking the screen while the display stays on, and recording to an external drive (macOS asks for permission the first time an app reads or writes one).

## Appendix: test results (2026-11-01 to 2026-11-02)

One 256-second recording with the setup above. The Mac was muted at volume 0 throughout. "Picture moving" counts frames whose brightness differs from the frame 0.5 s earlier by at least 0.6 on average (8-bit scale); sound is the median RMS level.

| Phase | Time in the recording | Picture moving | Sound |
|---|---|---|---|
| Xit Mobile in the background while working in other apps; another app played a 1 kHz beep at about 16–20 s | 0–120 s | 99% | −27 dBFS |
| Xit Mobile minimized | 120–139 s | 0% (frozen) | −26 dBFS |
| Restored from the Dock | 146–167 s | 100% | −27 dBFS |
| User on another desktop | 172–227 s | 81%, with no frozen stretch of 2 s or more | −28 dBFS |
| User back on the original desktop | 231–256 s | 0% (frozen from 229 s until the end) | −28 dBFS |

- **Other apps' sound:** around the beep, the 1 kHz share of the recorded sound never went above 0.04, with similar blips after the beep had ended. The beep file itself scores 1.00, so the beep was not recorded.
- **Gaps:** 12,000 audio frames covering 256.0 s with no gaps; 7,673 video frames at 29.97 fps with no gaps except at the moment recording stopped.
- **Check commands:** on this file they reported exactly the two frozen stretches (`freeze_start` at 119.3 s and 229.2 s) and nothing else. On a black test file they reported `black_start:0` (and `freeze_start: 0`).

Later the same day, one short recording per window event:

| Test | Picture | Sound | Notes |
|---|---|---|---|
| Quit Xit Mobile, reopen it after 14 s | Frozen on the last frame from the moment it quit until the end (66.5 s) | Digital silence from the same moment | OBS logged "Stream stopped as no capture source was not found". After restarting OBS it logged "Invalid target window ID" and showed black |
| Hide (⌘H) for 21 s | Frozen while hidden (a 20.0 s stretch) | −30 dBFS | Moving again as soon as it was shown, without a click |
| Full screen for 23 s | Moving 98% of the time | −28 dBFS | Frozen for 2.0 s right after leaving full screen, then moving again by itself |
| Display turned off for 62 s (the screen locked within 10 s) | Frozen for 51.5 s | −27 dBFS | Moving again as soon as the Mac was woken |

None of these files had gaps in their audio or video timestamps. Short "frozen" readings of a few seconds also showed up during still graphics in the program itself, which is why the check command only flags 10 s or more.

Then a 30-minute recording (30 min 45 s) with nobody at the Mac, which stayed awake and unlocked:

| Measure | Result |
|---|---|
| Check commands ("Check a recording") | No output: no freeze, black or silence, no audio gaps |
| Picture | Moving 80–100% of the time in every 5-minute block; no frozen stretch longer than 11 s (still graphics) |
| Sound | −27 to −28 dBFS in every 5-minute block |
| Frames | 55,284 video frames at 29.97 fps; OBS repeated 76 of them (0.1%) when its drawing loop ran late |
| Picture and sound lengths | 1844.64 s and 1844.59 s, 57 ms apart: no drift |
| Sound and picture in step | At 11 commercial boundaries the picture cut fell inside the 1-second silence, a median 0.11 s after its middle (0.00–0.22 s), the same early and late in the recording |
| File size | 1.42 GB, which is 2.77 GB per hour |
| CPU, median (peak) | Xit Mobile 72% (138%) of one core, OBS 28% (39%) |

Then a 7.5-hour run on three channels, again with nobody at the Mac, which stayed awake and unlocked (`caffeinate -dis` was running as well). The channel was changed twice, as in "Recording another channel": one step down from TBS reached TV Asahi, and one more reached NTV. While recording, the last 5 minutes of the file were also checked every 5 minutes. There, "picture moving" is the share of keyframe pairs, 2 s apart, whose brightness differs by at least 0.6 on average.

| Measure | TBS | TV Asahi | NTV |
|---|---|---|---|
| Recorded | 10:57–13:58 | 13:59–17:00 | 17:01–18:30 |
| Length and size | 3 h 01 min, 8.41 GB | 3 h 01 min, 8.38 GB | 1 h 29 min, 4.13 GB |
| Check commands | No audio gaps. Two `freeze_start` (10.7 s and 11.0 s: a still weather map and a still painting) and one `black_start` (7.6 s: a dark scene in a drama promo), all with the sound playing normally | No output | No output |
| Picture moving, lowest 5-minute check | 91% | 96% | 97% |
| Sound, average level per 5-minute check | −25 to −28 dBFS | −27 to −29 dBFS | −27 to −29 dBFS |
| Video frames | 326,305 at 29.97 fps | 325,250 at 29.97 fps | 160,112 at 29.97 fps |
| Picture and sound lengths | 62 ms apart | 60 ms apart | 57 ms apart |
| CPU, median (peak) | Xit Mobile 74% (118%), OBS 28% (36%) | Xit Mobile 77% (137%), OBS 28% (37%) | Xit Mobile 76% (131%), OBS 27% (36%) |

- **No drift over 3 hours:** picture and sound ended within about 60 ms of each other in every file, as in the 30-minute test.
- **No lagged frames:** OBS reported none for any of the three files.
- **Channel switches:** the gaps between files were 75 s and 51 s. After the first switch Xit Mobile showed the EC21 message for under 30 s; after the second, the picture was already moving when checked about 20 s later. Xit Mobile kept the same window both times and never showed its capture-detected message.
- **File size:** 2.78 GB per hour, about the same as in the 30-minute test.

Then a 9-hour run overnight on three channels, from 21:48 to 07:00 the next morning, set up like the daytime run: nobody at the Mac, which stayed awake and unlocked, with `caffeinate -dis` running and automatic macOS updates turned off. The channel was changed twice: one step down from Fuji TV reached TV Tokyo, and three more steps, through TBS and TV Asahi, reached NTV. The picture and sound figures come from the same 5-minute checks as in the daytime run.

| Measure | Fuji TV | TV Tokyo | NTV |
|---|---|---|---|
| Recorded | 21:48–01:00 | 01:00–04:00 | 04:01–07:00 |
| Length and size | 3 h 12 min, 8.89 GB | 3 h 00 min, 8.33 GB | 2 h 59 min, 8.30 GB |
| Check commands | No output | No output | No output |
| Picture moving, lowest 5-minute check | 94% | 92% | 86% |
| Sound, average level per 5-minute check | −26 to −29 dBFS | −26 to −29 dBFS | −25 to −29 dBFS |
| Video frames | 344,955 at 29.97 fps | 323,177 at 29.97 fps | 321,925 at 29.97 fps |
| Picture and sound lengths | 57 ms apart | 53 ms apart | 49 ms apart |
| CPU, median (peak) | Xit Mobile 73% (171%), OBS 28% (37%) | Xit Mobile 73% (135%), OBS 27% (36%) | Xit Mobile 80% (135%), OBS 27% (38%) |

- **No warnings all night:** the once-a-minute checks (both apps running, the screen awake and unlocked, the Xit Mobile window on screen, the file growing, at least 30 GB free) and the 5-minute picture and sound checks never raised one, and OBS reported no lagged frames.
- **No drift:** picture and sound ended 49–57 ms apart, as in the shorter runs.
- **Channel switches:** the gaps between files were 23 s and 52 s; the second took three menu presses. Xit Mobile never showed the EC21 message, kept the same window both times, and never showed its capture-detected message.
- **File size:** 2.78 GB per hour, the same as by day.
