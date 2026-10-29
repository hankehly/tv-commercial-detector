# Commercial detection: research notes

Summary of a ChatGPT discussion ([share link](https://chatgpt.com/share/6ae28ad3-4bdc-83ee-92c2-4ad92d412d6d), 2026-10-25 to 2026-10-27) about where to take this repository. Claims, numbers and recommendations below are ChatGPT's, not independently verified.

## TL;DR

- **Reframe the goal from identification to detection.** The question is no longer "which commercial is this?" but "is a commercial playing right now?", so downstream actions (lower the volume, notify, log) can react.
- **Keep the repo, rewrite the implementation.** Rename it (done: `tv-commercial-detector`) and tag the old fingerprinting code (suggested tag: `audio-fingerprinting-poc`) so it stays recoverable from git history.
- **Recommended technical path:**
  1. Benchmark existing detectors (Comskip, pycommflag).
  2. Train a lightweight classifier (LightGBM) on synchronized audio and video features over short windows.
  3. Smooth its output with a state machine that emits `commercial_started` / `commercial_ended` events.
- **Run locally first.** Cloud processing is possible, but getting the broadcast into the cloud is the hard part, and it should not block progress.

## 1. Detection vs identification

| | Original project | New direction |
|---|---|---|
| Question | Which commercial is playing? | Is a commercial playing? |
| Problem type | Content identification | Binary classification over time |
| Main technique | Audio fingerprint matching | Audiovisual classification |
| Needs a database of known ads? | Yes | No |
| Output | Commercial ID | `COMMERCIAL` / `PROGRAM` state |
| Example action | Log an ad airing | Lower the TV volume |

Detection has to work on ads the system has never seen, so fingerprinting stops being the core technique.

## 2. Assessment of the existing code

Current pipeline: XIT stick → BlackHole → FFmpeg → `silencedetect` → candidate segments filtered by duration (roughly 10 to 60 s) → Dejavu fingerprints in PostgreSQL, with Celery running export and fingerprint tasks.

Limitations ChatGPT pointed out:

- Silence is only a boundary heuristic. It can't tell whether a segment is an ad, and some transitions have no clean silence.
- Treating a 15 or 30 s duration as evidence of an ad causes false positives.
- The README describes live matching, but the code implements only segmentation and fingerprint storage. There is no live recognition loop.

| Component | Recommendation | Reason |
|---|---|---|
| FFmpeg audio capture | Keep | Still needed |
| Silence detection | Keep, repurpose | Useful as one feature among many |
| Audio segmentation | Refactor | Move to continuous fixed-window processing |
| Dejavu fingerprinting | Remove from core | Not needed to detect unseen ads |
| PostgreSQL | Optional | Detection works without a database |
| Celery / RabbitMQ | Drop for v1 | A single streaming process is enough |
| Video processing | Add | Needed for audiovisual features |
| Classifier | Add | New core |
| Detection state machine | Add | Needed to drive actions reliably |

## 3. Approaches surveyed

### Identification approaches (known ads, now out of scope)

Covered in the first answer, before the focus narrowed to detection. Kept here for reference:

- **Audio fingerprinting** (spectrogram peak hashing with temporal alignment): [audfprint](https://github.com/dpwe/audfprint), [Panako](https://github.com/JorenSix/Panako) (robust to time-stretch and pitch-shift), [Chromaprint](https://github.com/acoustid/chromaprint). Suggested matching overlapping sliding windows (e.g. 5 s windows with a 1 s hop) instead of relying on silence-based segmentation.
- **Video perceptual hashing**: pHash on frames sampled at 1 to 2 fps, confirmed by matching sequences of frames rather than single frames. [Meta's vPDQ](https://github.com/facebook/ThreatExchange/blob/main/vpdq/README.md) supports matching subsequences of longer videos.
- **Repetition-based discovery**: ads repeat, so recurring segments can be clustered into a self-built catalog. The hard part is filtering out station IDs, news intros and promos.
- **Neural embeddings** ([DINOv2](https://github.com/facebookresearch/dinov2) for video, [CLAP](https://github.com/LAION-AI/CLAP) for audio) with vector search. Good for near-duplicates, but may rate two different car ads as similar.
- **OCR, Japanese ASR and logo recognition**: enrich unknown clips with advertiser and product information.

### Detection approaches (the focus)

Ordered from cheapest to most expensive:

1. **Rule-based audiovisual heuristics.** Silence, black frames, scene cuts and channel logo disappearance. [Comskip](https://www.comskip.org/) is the long-standing example ([tuning manual](https://www.kaashoek.com/files/manual.htm)) and needs no training data.
2. **Feature-based ML (recommended start).** Extract features per short window and classify with LightGBM or XGBoost. [pycommflag](https://github.com/b-pass/pycommflag) is close to this design: Python, logo, black-frame, frame-diff, audio-level and speech/music/noise features fed to an LSTM, with label editing and retraining.
3. **Deep audiovisual model.** For example, a 5 s log-mel spectrogram plus downsampled frames, separate encoders, and an LSTM or Transformer fusion layer that outputs P(commercial). See the [WACV 2023 paper](https://openaccess.thecvf.com/content/WACV2023/html/Liu_A_Deep_Neural_Framework_To_Detect_Individual_Advertisement_Ad_From_WACV_2023_paper.html). More flexible, but needs more labels and compute.

Candidate features:

| Feature | Why it matters |
|---|---|
| Channel logo presence | Some channels hide the logo during ads (verify per Japanese channel) |
| Audio discontinuities and silence | Transitions often coincide with audio changes |
| Black or solid-color frames | Often mark boundaries |
| Scene-cut frequency | Ads tend to have faster editing |
| Short-term loudness and its dynamics | Ad audio often differs from program audio |
| Speech/music proportion, MFCC stats, spectral centroid | Distinguish dialogue from ad audio patterns |
| Brightness, contrast, motion intensity | General visual style differences |
| 15 and 30 s duration patterns | Standard Japanese ad lengths ([KTV broadcast standards](https://www.ktv.jp/corp/standard/)); use as soft priors, not hard rules |

No single feature is reliable on its own; the classifier learns their combinations. A [2025 IEEE paper](https://ieeexplore.ieee.org/abstract/document/10929855) reported 99.79% accuracy with audio-only features and conventional ML. That is encouraging for lightweight models, but it was not measured on Japanese broadcasts.

### Temporal modeling

Per-window probabilities are noisy (e.g. a dip from 95% to 73% in the middle of an ad). Stabilize them before acting:

- **Hysteresis**: different thresholds for entering and leaving commercial mode.
- **HMM**: model the likelihood of staying in the same state.
- **LSTM or Transformer** over neighboring windows.

For live use, the model can only see past and current windows. Looking ahead improves boundary accuracy at the cost of added output delay.

### Ad-break detection vs individual-ad segmentation

- **Ad-break detection** outputs one interval covering the whole break. A two-state classifier is enough. This is what volume control needs.
- **Individual-ad segmentation** finds the boundary of every ad within a break. It needs an additional change-point detector.

## 4. Proposed architecture

```
TV audio/video stream
        │
        ▼
Feature extraction      (loudness, silence, logo presence, scene cuts, ...)
        │
        ▼
Detection model         (P(commercial) per window)
        │
        ▼
State machine           PROGRAM ⇄ COMMERCIAL
        │  emits commercial_started / commercial_ended
        ▼
Actions                 adjust volume │ notify │ log
```

- Keep the detection engine independent of downstream actions so models can be swapped without touching the rest.
- Keep capture behind its own interface so it can accept local audio, local video or a remote stream.
- No Celery, RabbitMQ or PostgreSQL in the first version.

## 5. Experiment plan and evaluation

| Experiment | Method | Purpose |
|---|---|---|
| Baseline A | Existing silence rules | Measure current performance |
| Baseline B | Comskip | Established audiovisual heuristics |
| Baseline C | pycommflag | Existing ML-based detector |
| D | LightGBM, audio features only | Establish how much video adds |
| E | LightGBM, audio and video features | Multimodal feature engineering |
| F | Audiovisual neural network | Check whether learned features beat engineered ones |

**Dataset:** annotate several hours of Japanese TV across different channels, programs and dates. Split train and test by program and date so near-identical adjacent windows don't leak across the split and inflate results. Check that the model isn't learning channel or program quirks instead of ad characteristics.

**Metrics:**

| Metric | What it tells you |
|---|---|
| Detection precision and recall | Whether ads are found without too many false alarms |
| False alarms per hour | How disruptive mistakes would be in practice |
| Boundary error (s) | How accurately start and end are found |
| Detection latency | Seconds into an ad before the state flips |
| CPU/GPU utilization | Whether the system can run continuously |

## 6. Cloud capture

A cloud VM can't receive terrestrial broadcasts (地デジ) on its own; something has to supply the signal in digital form.

| Approach | Local hardware | Practicality |
|---|---|---|
| XIT stick → cloud | Required | High |
| Network TV tuner → cloud | Required | High |
| Official online stream (TVer) | None | Limited by coverage and terms of service |
| Licensed IP broadcast feed | None | Mainly commercial and costly |
| Tuner hosted in a data center | Remote hardware | Possible but complex |

**Hybrid option:** XIT stick → FFmpeg or OBS → SRT over the internet → [MediaMTX](https://github.com/bluenviron/mediamtx) on a VM → detector → events → local TV controller. Example publish command (with file input as a stand-in):

```bash
ffmpeg -i input.mp4 \
  -c:v libx264 -preset veryfast -b:v 1000k \
  -c:a aac -b:a 96k \
  -f mpegts \
  "srt://CLOUD_VM_IP:8890?streamid=publish:tv&pkt_size=1316"
```

Lock down the SRT endpoint with authentication, encryption and network ACLs.

**Caveats:**

- **XIT-STK100 video capture.** Pixela's [Mac Q&A](https://jvcdl.pixela.co.jp/products/xit/stk100/qa_mac.html) and [spec page](https://jvcdl.pixela.co.jp/products/xit/stk100/spec.html) say screen capture isn't supported because of copy protection, and recordings can't be converted or played elsewhere. Working audio capture through BlackHole doesn't mean video capture will work. This affects the audiovisual plan locally too, not just in the cloud.
- **TVer** has no ingestion API, doesn't carry every channel, may show different ads with different timing than broadcast, and its [terms prohibit capture and download](https://help.tver.jp/hc/ja/articles/5106719268761). Not a viable feed.
- **Licensed feeds** would work technically. Google Cloud's [Live Stream API](https://docs.cloud.google.com/livestream/docs/overview) accepts SRT and RTMP, but it only ingests and transcodes; it doesn't supply channels. Broadcast rights are complex; see [A-PAB's cloud recording rules](https://www.apab.or.jp/business/cloud-rec/).
- **Latency and sync.** What matters is the delay between an ad starting and the volume changing. The analyzed feed must match the channel and timing of the TV being controlled; a feed running 10 s behind defeats even a perfect classifier.

**Where to run inference:**

| Pattern | Pros | Cons |
|---|---|---|
| Fully local | Most responsive, no network dependency | Needs local compute |
| Local capture, cloud inference | Central ML, easier remote experiments | Streaming delay, cloud cost |
| Local feature extraction, cloud inference | Far less bandwidth, scales to many channels | Still network-dependent; still needs local video access |

On Google Cloud, Compute Engine is the simplest fit for a long-lived stream consumer. Cloud Run services have a [60-minute request timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout), which makes standard request-driven services awkward for this.

**Recommendation:** keep capture separate from detection, build a local prototype and measure latency first, then try cloud inference (on a full stream or on extracted features). Keep volume control local, with fallback behavior for when connectivity or detection fails. Eliminating the tuner entirely is a much harder problem (finding a legitimate, low-latency IP source of Japanese TV) than moving inference to the cloud.

## 7. Repository naming (resolved)

Candidates included `tv-commercial-detection`, `tv-ad-detector`, `tv-ad-detection`, `tv-commercial-monitor`, `adbreak` and others. The final choice was between `tv-commercial-detector` and `tv-ad-detector`. ChatGPT picked **`tv-commercial-detector`** because "commercial" specifically means broadcast ad spots, while "ad detection" collides with web ads and ad-blocking in search results. The rename is done (commit `4eeac70`).

Suggested repo description:

> Real-time detection of TV commercials in audio and video streams, enabling automated actions such as volume control.

## 8. Open questions

- **Can we get a decoded video feed at all?** See the XIT-STK100 caveat above. If not, start with audio-only (experiment D), or find a different tuner or capture path for video.
- Do Japanese channels actually hide their on-screen logo during ads? This needs checking per channel before relying on it as a feature.
- How much labeled data do we need, and what's the cheapest way to annotate it?
- What detection latency is acceptable for volume control? This decides whether look-ahead smoothing is affordable.

## References

**Tools**

- [Comskip](https://www.comskip.org/) and its [tuning manual](https://www.kaashoek.com/files/manual.htm)
- [pycommflag](https://github.com/b-pass/pycommflag)
- [audfprint](https://github.com/dpwe/audfprint), [Panako](https://github.com/JorenSix/Panako), [Chromaprint](https://github.com/acoustid/chromaprint)
- [vPDQ](https://github.com/facebook/ThreatExchange/blob/main/vpdq/README.md) ([ThreatExchange](https://github.com/facebook/ThreatExchange))
- [DINOv2](https://github.com/facebookresearch/dinov2), [CLAP](https://github.com/LAION-AI/CLAP)
- [MediaMTX](https://github.com/bluenviron/mediamtx) ([FFmpeg publishing](https://github.com/bluenviron/mediamtx/blob/main/docs/3-publish/17-ffmpeg.md), [SRT reading](https://github.com/bluenviron/mediamtx/blob/main/docs/4-read/02-srt.md))

**Papers**

- Liu et al., [A Deep Neural Framework to Detect Individual Advertisement (Ad) From Videos](https://openaccess.thecvf.com/content/WACV2023/html/Liu_A_Deep_Neural_Framework_To_Detect_Individual_Advertisement_Ad_From_WACV_2023_paper.html), WACV 2023
- [Real-Time Detection of Free-to-Air Television Commercials in Audio Using Feature Extraction and Machine Learning](https://ieeexplore.ieee.org/abstract/document/10929855), IEEE 2025
- [Automatic TV Logo Identification for Advertisement Detection without Prior Data](https://www.mdpi.com/2076-3417/11/16/7494), Applied Sciences 2021
- [Fusing Audio-Visual Fingerprint to Detect TV Commercial Advertisement](https://www.sciencedirect.com/science/article/pii/S0045790611001194), 2011
- Manson, [Automatic TV Broadcast Structuring](https://onlinelibrary.wiley.com/doi/10.1155/2010/153160), 2010 (repetition-based detection)
- [An intelligent subtitle detection model for locating television commercials](https://pubmed.ncbi.nlm.nih.gov/17416175/)

**Japan-specific and infrastructure**

- [KTV broadcast standards (放送基準)](https://www.ktv.jp/corp/standard/)
- Pixela XIT-STK100: [Mac Q&A](https://jvcdl.pixela.co.jp/products/xit/stk100/qa_mac.html), [spec](https://jvcdl.pixela.co.jp/products/xit/stk100/spec.html)
- TVer help: [What is TVer](https://help.tver.jp/hc/ja/articles/5105308992281), [live streaming](https://help.tver.jp/hc/ja/articles/5108288440473), [download and copy policy](https://help.tver.jp/hc/ja/articles/5106719268761)
- [A-PAB: cloud recording support for receivers](https://www.apab.or.jp/business/cloud-rec/)
- Google Cloud: [Live Stream API](https://docs.cloud.google.com/livestream/docs/overview), [Cloud Run request timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout)
- GitHub: [Renaming a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)
