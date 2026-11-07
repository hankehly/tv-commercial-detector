# What join_logo_scp counts as a commercial break

Research note for the benchmark in [#7](https://github.com/hankehly/tv-commercial-detector/issues/7). It compares join_logo_scp's idea of a commercial break with ours ([ADR 0002](adr/0002-what-counts-as-a-commercial-break.md), [glossary](../GLOSSARY.md)), and asks whether its output says enough for an adapter to convert its results to our definition.

Everything here comes from reading code, bundled docs and bundled settings. Nothing was run. The versions are the ones `jlse` runs: tobitti0/JoinLogoScpTrialSetLinux at `aabb505` builds join_logo_scp v4.0 from tobitti0's fork at `646a0fd`, and runs the `jlse` scripts, settings and JL command files from tobitti0/join_logo_scp_trial at `c38e970` ([TrialSet .gitmodules], [Dockerfile L12-29], [docker-compose.yml L12-17], [TrialSet README L21-27], [fork README L3-4]). Yobibi's current upstream (v5.1.1, `4107b3e`) has the same section kinds, the same keep-or-cut rule and the same defaults in `JL_標準.txt` ([upstream JlsDataset.cpp L3267-3290], [upstream JL_標準.txt L33-35]). No secondary sources were needed.

## TL;DR

- **To join_logo_scp, a commercial break is a stretch where the channel logo is off screen and that splits into 15-second blocks at silent scene changes.** Anything with the logo on screen is program. Separately, it looks for one sponsor credit near the start of the file, and one sponsor credit, one next-episode preview and one anime endcard near the end, and keeps those with or without the logo.
- **For ordinary commercials it agrees with us, down to the frame.** Its cuts start on the first frame of the first commercial and end on the first frame after the last one.
- **It differs from us in three main ways:**
  1. **Promos shown with the channel logo are kept.** We count every promo as part of the commercial break.
  2. **Sponsor credits, station IDs, previews and endcards are often kept.** They are kept whenever the logo is on screen, and so are one sponsor credit in the first 13½ minutes of the file and one sponsor credit, preview and endcard in the last 7 minutes, with or without the logo. We count them all as part of the commercial break. Without the logo and next to a commercial break, it cuts them when they last a whole multiple of 5 seconds, as we would.
  3. **Any logo-less stretch of 40 seconds or more is cut,** 15-second blocks or not. That catches a program or a shopping program shown without the logo.
- **It is built for one program per file.** Its default script is "tuned for 30-minute anime slots", it treats the first 12 to 30 s and the last 30.5 s of the file as recording margins it may cut, and its sponsor credit, preview and endcard handling only looks at the two ends of the file. Our 1.5 to 3 hour recordings hold several programs, so the program boundaries in the middle get none of that handling.
- **In the benchmark,** expect edge offsets the length of the piece involved (for example 10 s for a sponsor credit, 15 or 30 s for a promo) where a promo, sponsor credit, station ID or preview sits at the edge of a commercial break and join_logo_scp keeps it; extra false flips where a logo-bearing promo splits a commercial break or the logo vanishes for 40 s or more; and possible false flips in the first and last 30 s of each recording.
- **Its output names each section's kind** (`obs_jlscp.txt`: `CM`, `Nologo`, `L`, `Sponsor(add)`, `Trailer(add)` and so on). That is enough to explain most differences but not to convert to our definition: a logo-bearing promo, sponsor credit or preview in the middle of the file is just `L`, like program. Issue #7 also rules out adjusting tool output, so the kinds are for diagnosis only.
- **Setup:** `jlse` only accepts `.ts` files and picks settings and the logo from the file name. Our time-only names give every channel the default script `JL_標準.txt` and hand logoframe every logo in `jlse`'s `logo/` folder. So the adapter should present each recording under a `.ts` name, with a `logo/` folder holding only that channel's logo. Putting the channel in the file name instead would switch TBS to a different script, `JL_MBS.txt`.

## 1. Comparison with our definition

"Default" means `jlse` with our file names, which runs `JL_標準.txt` for every channel (section 4.1). The last column uses the benchmark's measures for look-ahead detectors from issue #7: missed commercial breaks, false flips and edge offsets.

| Our category | Ours | What join_logo_scp does by default | Same? | How it shows up in the benchmark |
|---|---|---|---|---|
| Commercial (タイムCM, スポットCM, ACジャパン) | Commercial break | Logo off, splits into 15-second blocks: `CM`, cut ([JlsAutoReform.cpp L1537-1541], [JlsAutoReform.cpp L3136-3176]). | Same | Nothing expected. Boundaries land on the same frames as ours (section 3.2). |
| Promo (番宣) without the logo | Commercial break | Treated like a commercial: `CM`, cut. | Same | Nothing expected. |
| Promo with the channel logo | Commercial break | Kept as program (`L`): 15-second blocks inside a logo stretch are not cut ([JL_標準.txt L22-23], [JlsAutoReform.cpp L2227-2251]). In the last 7 minutes, after a preview: 14 s or longer becomes `Trailer(cut-cancel)` and is kept; shorter becomes `Trailer(cut)` and is cut ([JlsAutoScript.cpp L1342-1351], [JL_標準.txt L34]). | Different | At the edge of a commercial break: edge offset (late start or early end by the promo's length). In the middle: the commercial break is reported in two pieces, one extra false flip. A commercial break made only of logo-bearing promos: missed commercial break. |
| Sponsor credit (提供クレジット) with the logo | Commercial break | Part of the logo stretch: kept. | Different | Edge offset of the credit's length, for example 10 s. Alone between two parts of a program: missed commercial break. |
| Sponsor credit without the logo, in the first 13:30 or last 7:00 of the file | Commercial break | Up to one per end, 5 to 13 s (or exactly 15 s with the logo on): `Sponsor(add)`, kept ([JL_標準.txt L79-104], [JL_標準.txt L211-215], [JL_標準.txt L282-286], [JlsAutoScript.cpp L151-160]). A second one in the same window is handled as in the next row. | Different | Edge offset of the credit's length. |
| Sponsor credit without the logo, anywhere else | Commercial break | Next to a commercial break, pulled into the cut when it lasts a whole multiple of 5 s (within 0.2 s) or of 15 s (within 1.2 s): `Nologo` or `CM` ([JlsAutoReform.cpp L3859-3934], [JlsAutoReform.cpp L5126-5156]). Otherwise kept. | Same when it lasts a whole multiple of 5 s | Otherwise an edge offset of the credit's length, for example 7 s. |
| Station ID | Commercial break | No kind of its own. With the logo: kept. Without it: like a logo-less sponsor credit. One between two runs of commercials is cut with them ([JlsAutoReform.cpp L189], [JlsAutoReform.cpp L2371-2396]). | Same between two runs of commercials, or without the logo and a whole multiple of 5 s | Otherwise an edge offset of about its length. |
| Next-episode preview (次回予告) in the last 7:00 of the file | Commercial break | One section after the last commercial break, up to 45 s, with or without the logo: `Trailer(add)`, kept. A logo stretch there longer than 2:10 counts as program instead ([JL_標準.txt L40-48], [JL_標準.txt L220-221], [JL_標準.txt L273], [Autocutメモ.txt L17-24]). | Different | Edge offset of the preview's length, up to 45 s. |
| Next-episode preview anywhere else | Commercial break | No special handling. With the logo: kept. Without it: cut if it forms 15-second blocks (`CM`), or as an edge piece (`Nologo`). | Same when shown without the logo | With the logo: edge offset of its length, or the commercial break reported in two pieces (one extra false flip) if it sits in the middle. |
| In-program advertising (「PR」 segment, product placement) | Program | With the logo on screen: kept. If the logo goes away: cut when it forms 15-second blocks or lasts 40 s or more ([JlsAutoReform.cpp L426-488]). | Same unless the logo is removed | False flip. |
| Whole-slot shopping program (通販番組) | Program | With the logo: kept. Without it: cut as `Nologo` or `CM`, since it lasts well over 40 s ([JL_標準.txt L132], [JlsAutoReform.cpp L426-488]). | Same unless shown without the logo | One long false flip, or large edge offsets if it merges with the commercial breaks around it. |
| Coming-up-next card (「このあとは」) | Commercial break | No kind of its own. With the logo: kept. Without it: like a logo-less sponsor credit. | Same without the logo and a whole multiple of 5 s, or between two runs of commercials | Otherwise an edge offset of about its length, usually 5 s. |
| Anime endcard (エンドカード) | Commercial break | In the last 7:00: `Endcard(add)`, kept ([JL_標準.txt L287-292]). Elsewhere: like a sponsor credit. | Different at the end; same elsewhere without the logo and a whole multiple of 5 s | Edge offset of about its length. |
| A program shown without the channel logo | Program | Any logo-less stretch of 40 s or more is cut. If the whole recording has under 20 s of logo, join_logo_scp ignores the logo and finds commercials from 15-second blocks alone (section 2.8). | Different | False flips. |
| Start of a recording that begins mid-program | Program | The first section is cut if it ends within 12 s, or within 30 s and before the logo first appears. Everything before the first logo is cut. A logo that ends within the first 500 frames (16.7 s) is ignored ([JlsAutoReform.cpp L1772-1819], [JL_標準.txt L10-12], [logoset.h L13-18]). | Different | A false flip in the first 30 s, or an edge offset on a commercial break that starts the recording. |
| End of a recording that stops mid-program | Program | The last section is cut if it starts within 30.5 s of the end. Everything after the last logo is cut unless kept as sponsor credit, preview or endcard. A logo that starts in the last 150 frames (5 s) is ignored ([JlsAutoReform.cpp L2155-2208], [JL_標準.txt L15-16], [logoset.h L13-18]). | Different | A false flip in the last 30.5 s. |

## 2. How it decides

### 2.1 The pipeline

`jlse` runs three tools in order ([jlse.js L109-124]):

1. **chapter_exe** finds silences and the scene changes inside them. `jlse` calls it with `-s 8 -e 4` ([chapterexe.js L7]). A silence is at least 8 frames (0.27 s) in which every 16-bit audio sample is at most 50 out of 32,767, about −56 dBFS. The scene change may sit up to 4 frames outside the silence ([chapter_exe.cpp L83-86], [chapter_exe.cpp L327-357], [改造版_読んでね.txt L47-50]).
2. **logoframe** finds when the channel logo is on screen, using the channel's logo file ([logoframe.js L42-58]).
3. **join_logo_scp** reads both and runs a JL command file to decide what to cut ([readme.txt L8-11], [join_logo_frame.js L15-35]). For our recordings that file is `JL_標準.txt` (section 4.1). Its own readme says of it: 「３０分枠アニメのCMカットでチューニングしてありますが汎用的に使えると思います」 ("tuned for cutting commercials out of 30-minute anime slots, but I think it can be used generally") ([readme.txt L24-26]).

### 2.2 Logo off marks a candidate commercial break

The command doc says: 「ロゴ表示終了から補正した場所がCMカット開始位置、次のロゴ表示開始から補正した場所がCMカット終了位置となる」 ("the cut starts where the logo disappears and ends where the logo next appears, each adjusted to a nearby position") ([全般.txt L9-12]). The code searches each logo-off gap for commercials, with the logo's disappearance as the start of the search and its reappearance as the end ([JlsAutoReform.cpp L179-225], [JlsAutoReform.cpp L1537-1541]). A position that never gets decided is not cut: 「カット位置が最後まで確定しなかった所はCMカットを行わない」 ("places whose cut position is never decided are not cut") ([全般.txt L9-12]).

### 2.3 15-second blocks between silent scene changes

Every section join_logo_scp works with runs from one silent scene change to the next. Inside a logo-off gap it looks for sections whose length rounds to a whole multiple of 15 s, up to 120 s each, with the end points allowed to sit 2.5 s off the 15-second grid. Those become `CM` ([JlsAutoReform.cpp L3136-3176], [JlsDataset.cpp L90-96]). Lengths of 10, 15, 30, 45, 60, 90 and 120 s, within 0.4 s, count as the strongest evidence ([JlsAutoReform.cpp L5084-5115]). Where a silence falls on the 15-second grid but chapter_exe found no scene change in it, join_logo_scp may add a boundary at that silent frame ([JlsAutoReform.cpp L3185-3213]). When one logo-off gap holds several runs of 15-second blocks, everything between the first and the last is cut too: 「複数のCM構成では間もCM」 ("with several commercial sections, what lies between them is commercial too") ([JlsAutoReform.cpp L189], [JlsAutoReform.cpp L2371-2396]). The readme describes its analysis output as made 「CMが基本15秒単位であることを前提に」 ("assuming commercials basically come in 15-second units") ([readme.txt L90-98]).

`logo_level 6` sets how far it trusts the logo: 「ロゴ優先度=中 15秒単位構成を認識。5秒単位構成を追加認識。」 ("logo priority medium: recognizes 15-second sections, and 5-second sections as well") ([JL_標準.txt L22-23], [補助解説.txt L213-223]).

### 2.4 Long logo-less stretches are cut anyway

`logo_revise 23` includes "+20": 「ロゴ外部のCM認識していない広域構成をCM化」 ("wide stretches outside the logo that weren't recognized as commercials are made commercials") ([JL_標準.txt L22-23], [補助解説.txt L225-233]). In the code, a logo-off gap of at least `param_wlogo_cmmin`, 40 s, that is still treated as program is switched to cut ([JL_標準.txt L132], [JlsAutoReform.cpp L426-488]). Setting `param_adduc 1` would turn this off ([JL_標準.txt L33-35], [JlsDataset.cpp L121-160]).

### 2.5 Logo on means program, even in 15-second blocks

The "+10" part of `logo_revise` (「ロゴ内部の複数15秒単位構成を認識してCM化」, "runs of 15-second sections inside the logo are made commercials") is not in the default 23 ([補助解説.txt L225-233]). So the code skips the search for commercials inside logo stretches ([JlsDataset.cpp L121-160], [JlsAutoReform.cpp L2227-2251]), and a logo-bearing promo is kept.

When a logo-bearing promo sits between two logo-off runs of commercials, each run is found on its own and the promo between them stays a logo section ([JlsAutoReform.cpp L179-225]). The exception is a logo stretch shorter than 20 s (`param_wlogo_lgmin`) right after a logo-off gap in which no commercials were found: the next search then spans it, and it can be swallowed into the cut ([JlsAutoReform.cpp L218-222], [JL_標準.txt L131], [JlsAutoReform.cpp L2371-2396]).

The tool's own per-title settings note logo-bearing promos at program starts and around mid-program commercial breaks, such as 「開始時にロゴ付番宣あり」 ("logo-bearing promo at the start") and 「途中のCM直後にロゴ付番宣あり」 ("logo-bearing promo right after the mid-program commercial break"), and handle them with per-title flags such as `HCCM` and `SC15` rather than by default ([JLparam_set2.csv L8], [JLparam_set2.csv L22-23], [設定内容.txt L95], [設定内容.txt L150-151]). Those rows also note logo-less sponsor credits on some programs ([JLparam_set2.csv L3], [JLparam_set2.csv L10]). These are per-title examples for anime slots, one block of them headed 「関西（2014Q4以降動作未確認）」 ("Kansai, not checked since late 2014") ([JLparam_set2.csv L13]), so they prove the cases exist, not how common they are on our channels today.

### 2.6 Short pieces at the edges of a commercial break

After finding the 15-second blocks, join_logo_scp looks at what sits between the outermost block and the logo edge. The piece moves to the cut side when both of these hold ([JlsAutoReform.cpp L3703-3764], [JlsAutoReform.cpp L3782-3793], [JlsAutoReform.cpp L3859-3934]):

| Condition | Value | Source |
|---|---|---|
| A silent scene change lies near the logo edge | within 1.2 s | [JlsAutoReform.cpp L3782-3793], [JlsDataset.cpp L90-96] |
| The piece's length is a whole multiple of 5 s | within 0.2 s, up to 30 s | [JlsAutoReform.cpp L5126-5156] |
| or a whole multiple of 15 s | within 1.2 s, up to 180 s | [JlsAutoReform.cpp L5126-5156] |

The 5-second rule applies because `logo_level` is 6 ([JlsAutoReform.cpp L3719-3731]). A piece that fits neither, say 7 s, stays on the program side. This is how a 10-second sponsor credit or 5-second station ID shown without the logo ends up inside the cut.

### 2.7 Built for one program per file

| Assumption | What the code does by default | Effect on our recordings |
|---|---|---|
| A file is one program, recorded with a margin at the start | The first section is cut if it ends within 12 s (`param_lgcut_first`), or within 30 s (`param_wcomp_first`) and before the logo first appears. Everything before the first logo is cut. A logo still on from the previous program may be cut: `cutbaselogo 1`, 「前番組から続くロゴ（0:制御なし 1:カット許可）」 ("logo continuing from the previous program: 1 = may cut") ([JL_標準.txt L10-12], [JL_標準.txt L137-140], [JlsAutoReform.cpp L1661-1671], [JlsAutoReform.cpp L1772-1819]). | A recording that starts in a program may lose its first 12 to 30 s. |
| A file is one program, recorded with a margin at the end | The last section is cut if it starts within 30.5 s of the end (`param_wcomp_last`). Everything after the last logo is cut ([JL_標準.txt L15-16], [JlsAutoReform.cpp L2016-2020], [JlsAutoReform.cpp L2155-2208]). | A recording that stops in a program may lose its last 30.5 s. |
| The ends of the file are noisy | logoframe ignores a logo that ends before frame 500 (16.7 s) or starts in the last 150 frames (5 s) ([logoset.h L13-18]). | Adds to the two rows above. |
| The sponsor credit is near the start of the program | `AutoAdd SP` only looks from the file start to 13 min 30 s (`fhead_ed`), never past the midpoint between the first logo start and the last logo end, and adds at most one ([JL_標準.txt L197-199], [JL_標準.txt L211-215], [全般.txt L390-400], [JlsScriptLimit.cpp L115-159], [Autocutメモ.txt L168-171]). | Only a sponsor credit of the first program, near the file start, can be recognized. |
| The preview, closing sponsor credit and endcard are near the end of the program | `AutoCut TR`, `AutoAdd SP`, `AutoAdd EC` and `AutoCut EC` only look at the last 7 minutes (`ftail_ed`), at most one of each, and treat a logo stretch longer than 2 min 10 s there as program (`param_wlogo_trmax`) ([JL_標準.txt L264-265], [JL_標準.txt L273], [JL_標準.txt L282-292], [Autocutメモ.txt L296-299], [JlsAutoScript.cpp L1143-1152]). | Only fires when a recording ends soon after a program. Program boundaries in the middle of a recording get none of it. |
| Settings depend on the program | `jlse` picks the script and flags from the channel and title in the file name: 「対象ファイル名に含まれる放送局やタイトルによって、join_logo_scpの動作を変更する」 ("changes join_logo_scp's behavior by the channel and title in the file name") ([設定内容.txt L3-4], [param.js L10-12], [param.js L57-69]). | Per-title settings can't fit a file with several programs. With our names nothing matches (section 4.1). |
| Multi-episode files come in fixed 30-minute blocks | The one bundled multi-episode script, `JL_構成30分単位.txt`, splits the file into 30-minute blocks counted from the file start and runs the default logic in each. `jlse` uses it only for ANIMAX titles that match an episode-range pattern ([JL_構成30分単位.txt L9-14], [JLparam_set1.csv L9]). | Our recordings start at arbitrary times, so 30-minute blocks wouldn't line up with program boundaries. |

### 2.8 When there is no logo

If logoframe finds no logo, or the logo is on screen for less than 20 s in total (`param_wlogo_summin`), join_logo_scp treats the recording as logo-less ([JL_標準.txt L130], [JlsScript.cpp L1294-1320], [JlsReformData.cpp L836-847]), and its Auto commands stop using the logo at all ([JlsScript.cpp L2015-2030]). Commercials are then found from 15-second blocks alone. `autocm_code 6` means 「15秒単位2〜3構成以上をCM」 ("two to three or more 15-second sections in a row are commercials"), and with `autocm_maxprd 60` no single section over 60 s counts ([JL_標準.txt L26], [JL_標準.txt L187-190], [補助解説.txt L235-245], [Autocutメモ.txt L236-250]). This matters for us because our logo files are hand-made from app-window recordings (issue #7), so logo detection may be patchy.

### 2.9 Thresholds at a glance

| What | Default | Setting | Source |
|---|---|---|---|
| Shortest silence | 8 frames (0.27 s) | chapter_exe `-s`, set by `jlse` | [chapterexe.js L7] |
| Silence level | every sample ≤ 50 of 32,767 (about −56 dBFS) | chapter_exe `-m`, left at its default | [chapter_exe.cpp L83-86], [chapter_exe.cpp L327-357] |
| Scene change search around a silence | 4 frames each side | chapter_exe `-e`, set by `jlse` | [chapterexe.js L7], [改造版_読んでね.txt L47-50] |
| Frames for the logo to count as switched on or off | 25 (0.83 s) | logoframe `-onwidth` | [logoset.h L13-18] |
| One commercial section | whole multiple of 15 s, up to 120 s, ends within 2.5 s of the grid | built in | [JlsAutoReform.cpp L3136-3176] |
| Logo-less stretch cut without 15-second blocks | 40 s or more | `param_wlogo_cmmin` | [JL_標準.txt L132] |
| Edge piece pulled into the cut | whole multiple of 5 s (±0.2 s, up to 30 s) or 15 s (±1.2 s) | `logo_level 6` | [JlsAutoReform.cpp L3719-3731], [JlsAutoReform.cpp L5126-5156] |
| Total logo time below which the logo is ignored | 20 s | `param_wlogo_summin` | [JL_標準.txt L130] |
| Start margin | first section ≤ 12 s, or ≤ 30 s before the first logo | `param_lgcut_first`, `param_wcomp_first` | [JL_標準.txt L10-12], [JL_標準.txt L137-140] |
| End margin | last section ≤ 30.5 s | `param_wcomp_last` | [JL_標準.txt L15-16] |
| Sponsor credit | 6 to 13 s (some codes add 5 s, or exactly 15 s with the logo); one in the first 13:30, one in the last 7:00 | `addsph_code1`-`5`, `addspt_code1`-`5`, `fhead_ed`, `ftail_ed` | [JL_標準.txt L79-104], [JlsAutoScript.cpp L151-160] |
| Next-episode preview | first section ≤ 45 s; a logo stretch over 2:10, or a section over 1:10, counts as program instead | `cuttr_tr1stprd`, `param_wlogo_trmax`, `param_wcomp_trmax` | [JL_標準.txt L127-128], [JL_標準.txt L220-221], [Autocutメモ.txt L296-299] |
| Logo-on piece after the preview | 14 s or longer kept, shorter cut | `param_cuttr 0` | [JlsAutoScript.cpp L1342-1351], [JL_標準.txt L34] |
| Logo ignored near the file ends | ends before frame 500; starts in the last 150 frames | logoframe `-mrgleft`, `-mrgright` | [logoset.h L13-18] |

## 3. Section kinds and output files

### 3.1 Section kinds

`obs_jlscp.txt` ends each line with one of these names ([JlsDataset.cpp L2383-2459]). Whether a section is kept follows from its kind alone ([JlsDataset.cpp L1520-1587]); upstream v5.1.1 states the same rule name by name ([upstream JlsDataset.cpp L3267-3290], [upstream JlsDataset.cpp L3292-3370]). The meanings come from the code comments on each internal state ([JlsNameSpace.hpp L37-75]) and the command docs.

| Kind, as printed | Internal state | What it is | Default | Where it appears by default |
|---|---|---|---|---|
| `CM` | `SCP_AR_N_UNIT`, `SCP_AR_N_AUNIT`, `SCP_AR_N_BUNIT` | Logo off, a 15-second block, or pieces that add up to one | Cut | Anywhere |
| `Nologo` | `SCP_AR_N_OTHER` | Logo off, not a 15-second block. Includes logo-less stretches of 40 s or more, the start and end margins, and short edge pieces | Cut | Anywhere |
| `L` | `SCP_AR_L_UNIT`, `SCP_AR_L_OTHER` | Logo on | Kept | Anywhere |
| `Mix` | `SCP_AR_L_MIXED` | Logo on, with logo-off moments that have no silent scene change to split on ([upstream 全般.txt L1012-1013]) | Kept | Anywhere |
| `Border15s`, `Border` | `SCP_AR_B_UNIT`, `SCP_AR_B_OTHER` | Section right next to a logo edge where the logo changes without a silent scene change ([upstream 全般.txt L1012-1013]) | Kept | Anywhere; `AutoBorder`, which could cut them, isn't in `JL_標準.txt` |
| `Sponsor(add)` | `SCP_AREXT_L_SP` with `CutSP` 0 | Sponsor credit (番組提供) | Kept | First 13:30 and last 7:00 of the file, at most one each |
| `Sponsor(cut)` | same, with `CutSP` 1 | Sponsor credit | Cut | Only if `param_cutsp 1` |
| `Trailer(add)` | `SCP_AREXT_L_TRKEEP`, 「残す予告」 | Next-episode preview (予告) | Kept | Last 7:00 |
| `Trailer` | `SCP_AREXT_L_TRRAW`, 「エンドカード判断前」 | Section after the preview, not yet decided ("before the endcard decision") | Kept | Last 7:00 |
| `Trailer(cut-cancel)` | `SCP_AREXT_L_TRCUT` with `CutTR` 0, 「カット番宣」 | Logo-on section of 14 s or more after the preview, that is a logo-bearing promo, cut cancelled | Kept | Last 7:00 |
| `Trailer(cut)` | `SCP_AREXT_L_ECCUT`, or `SCP_AREXT_L_TRCUT` with `CutTR` 1 | Logo-on section after the preview cut as a promo; by default only short ones (under 14 s) that aren't a recognized endcard or sponsor credit ([JlsAutoScript.cpp L1342-1351], [JlsAutoScript.cpp L1410-1468]) | Cut | Last 7:00 |
| `Endcard(add)` | `SCP_AREXT_L_EC` | Anime endcard (エンドカード) | Kept | Last 7:00 |
| `Nologo(cut)` | `SCP_AREXT_N_TRCUT`, 「ロゴ無 カット番宣」 | Logo-off section in the cut zone after the preview | Cut | Last 7:00 |
| `L-Edge(cut)`, `L-Edge(add)` | `SCP_AREXT_L_LGCUT`, `SCP_AREXT_L_LGADD` | Short piece at the inside edge of a logo stretch, cut or kept by `AutoEdge` | Cut, Kept | Not produced: the `AutoEdge` codes are 0 ([JL_標準.txt L109-116], [JlsAutoScript.cpp L2976-2986]) |
| `N-Edge(cut)`, `N-Edge(add)` | `SCP_AREXT_N_LGCUT`, `SCP_AREXT_N_LGADD` | The same on the logo-off side | Cut, Kept | Not produced, as above |
| nothing after the `:` | `SCP_AR_UNKNOWN` | Not classified | Cut | Should be rare |

Two naming traps:

- join_logo_scp's `Trailer` kinds mean the **next-episode preview** and what follows it, not promos: 「SP=番組提供、EC=エンドカード、TR=予告」 ("SP = sponsor credit, EC = endcard, TR = next-episode preview") ([Autocutメモ.txt L81-84]). The promos it cuts after the preview are also printed as `Trailer(cut)`.
- `CutTR` decides `Trailer(cut)` versus `Trailer(cut-cancel)`, and `CutSP` decides `Sponsor(cut)` versus `Sponsor(add)` ([JlsDataset.cpp L1556-1571], [JlsDataset.cpp L2421-2436]). `JL_標準.txt` sets both to 0, keep ([JL_標準.txt L33-35], [JL_標準.txt L148-149]), overriding the program's built-in `CutTR` 1 ([JlsDataset.cpp L42-43]).

### 3.2 Where boundaries go

- chapter_exe reports each scene change as `SCPos:<after> <before>`: the first frame of the new picture and the last frame of the old one, 「シーンチェンジ直後に加え、直前のフレーム番号を出力」 ("outputs the frame just before the scene change as well as the one just after") ([改造版_読んでね.txt L11-13], [chapter_exe.cpp L791], [JlsIF.cpp L442-450]).
- A kept part starts on an `<after>` frame and ends on a `<before>` frame ([JlsDataset.hpp L22-36], [JlsDataset.cpp L870-908], [JlsDataset.cpp L2311-2318]). It is written as AviSynth `Trim(start,end)`, which includes both end frames ([JlsIF.cpp L560-581]). `jlse`'s own chapter writer adds 1 to the end for that reason: 「開始位置を表すため終了位置では＋１する」 ("adds 1 to the end position so that it marks a start") ([chapter_jls.js L37-56]).
- So a commercial break runs from the frame after one `Trim`'s end to the next `Trim`'s start. Its first frame is the first frame of the first cut picture, and its end is the first frame of the next kept picture. That is exactly our convention.
- No margin or offset is added to the output. `-CutMrgIn` and `-CutMrgOut`, detected automatically by default, only describe how far the logo edge may lag the scene change when the two are matched ([readme.txt L56-72], [readme.txt L121-122], [JL_標準.txt L121-122], [JlsReformData.cpp L34-146]).
- join_logo_scp assumes 29.97 fps (30000/1001). The function to change it is marked unused ([CnvStrTime.cpp L13-15], [CnvStrTime.cpp L146-152]), and `jlse`'s chapter files assume the same ([chapter_jls.js L344-347]). This matches our recordings. It reports no frame rate of its own, so the adapter should use the recording's rate from the media probe, as issue #7 already allows.

For an adapter: given `Trim(a1,b1) ++ Trim(a2,b2) ++ … ++ Trim(aN,bN)`, the commercial breaks in frames are `[b1+1, a2)`, `[b2+1, a3)` and so on, plus `[0, a1)` when `a1 > 0` and `[bN+1, last frame + 1)` when the last `Trim` stops early. Divide by 30000/1001 for seconds.

### 3.3 Output files

`jlse` writes into `result/<file name without extension>/` ([settings.js L21-45], [TrialSet README L21-27]). Its README lists the main ones ([trial README L52-64]).

| File | Written by | What it holds | Format |
|---|---|---|---|
| `obs_cut.avs` | join_logo_scp `-o` | The parts it keeps; the commercial breaks are the gaps. `jlse`'s README calls it 「CMカットフレーム位置」 ("frame positions for the commercial cut") | One line, `Trim(a,b) ++ Trim(c,d) ++ …`, frames counted from 0 ([JlsIF.cpp L560-581]) |
| `obs_jlscp.txt` | join_logo_scp `-oscp` | Every section and its kind, 「番組構成解析結果」 ("program structure analysis") | One line per section: start frame, end frame, length in whole seconds, frames off the whole second, seconds with the logo on, then `:<kind>` ([readme.txt L90-98], [JlsDataset.cpp L2339-2378]) |
| `obs_logoframe.txt` | logoframe `-oa` | When the logo was on screen | Pairs of lines: frame, `S` or `E`, fade frames, `ALL`/`TOP`/`BTM`, earliest and latest possible frame ([logoframe_det.c L3896-3902]) |
| `obs_chapterexe.txt` | chapter_exe `-o` | Silences and the scene changes in them | `CHAPTERnn=hh:mm:ss.sss` at the silence start, then `CHAPTERnnNAME=<n>フレーム <mark> SCPos:<after> <before>`; the last line is `# SCPos:<last frame> <last frame>` ([chapter_exe.cpp L37-49], [chapter_exe.cpp L791], [chapter_exe.cpp L363]) |
| `obs_param.txt` | `jlse` | The script, flags and channel it picked | JSON ([param.js L73-101]) |
| `obs_chapter_org.chapter.txt`, `obs_chapter_cut.chapter.txt`, `obs_chapter_tvtplay.chapter` | `jlse` | Chapters for video players, built by matching `Trim` positions to `obs_jlscp.txt` lines within 30 frames | Chapter names start with `X` for cut parts (`XCM` where the kind was `CM`) and with a letter `A`, `B`, … for kept parts; a `<n>Sec` suffix marks a standalone section such as a sponsor credit or preview ([chapter_jls.js L4-30], [chapter_jls.js L89-91], [chapter_jls.js L381-451]) |
| `in_org.avs`, `in_cutcm.avs`, `in_cutcm_logo.avs`, `obs_logo_erase.avs` | `jlse`, logoframe `-o` | AviSynth scripts to play or encode the result | AviSynth |
| `ffmpeg.filter` | `jlse`, only with `-f` | ffmpeg filter for the kept parts | Text |

### 3.4 Can an adapter convert its results to our definition?

Not reliably.

- **What it can do:** `obs_cut.avs` says exactly what was cut. `obs_jlscp.txt` gives each section's start, end and kind, and the kind alone decides keep or cut (section 3.1), so the two files agree.
- **What is missing:** the sections where join_logo_scp and we disagree have no kind of their own. A logo-bearing promo, sponsor credit, station ID or preview in the middle of a recording is `L`, like program. Only near the file ends do `Sponsor(add)`, `Trailer(add)`, `Trailer(cut-cancel)` and `Endcard(add)` say more, and join_logo_scp keeps all four while we count them as part of the commercial break.
- **So:** the kinds can explain a score, for example a false flip that is a `Nologo` stretch of 40 s or more, or an edge offset that equals a kept `Sponsor(add)` or `Trailer(add)` section. Converting them would mean guessing. Issue #7 says tool output is never adjusted, so the adapter should read `obs_cut.avs` only and keep `obs_jlscp.txt` and `obs_logoframe.txt` as raw output for diagnosis.

## 4. Settings that change the outcome

The benchmark keeps detection settings at their defaults (issue #7). This section records what those defaults are, and what would change them.

### 4.1 What `jlse` picks for our five channels

`jlse` reads the channel from the file name using `setting/ChList.csv` ([channel.js L14-33]). With a time-only name such as `2026-11-01_10-56-55`, nothing matches and it returns no channel ([channel.js L68]). It then looks for the channel `__normal` in `JLparam_set1.csv` and `JLparam_set2.csv`, matches nothing, and falls back to the first row: `JL_標準.txt` with no flags or options ([param.js L10-12], [param.js L57-69], [JLparam_set1.csv L1-2]).

For the logo, `jlse` looks for `logo/<channel name>.lgd` or `.lgd2` under each of the channel's names. With no channel it passes the whole `logo/` folder to logoframe, 「ロゴファイルすべてを入力します」 ("inputs all logo files") ([logoframe.js L25-40], [trial README L82]), and logoframe reads every `.lgd` in that folder ([logoframe_mul.c L177-213]).

| Channel | `ChList.csv` names | Rows that would apply if the file name held the channel | Script then | Script with our file names |
|---|---|---|---|---|
| NTV | `日テレ`, `NTV` | none (only a title-specific row) | `JL_標準.txt` | `JL_標準.txt` |
| TBS | `TBS`, `TBS` | `TBS,,JL_MBS.txt` | `JL_MBS.txt` | `JL_標準.txt` |
| Fuji TV | `フジテレビ`, `CX` | none (only title-specific rows) | `JL_標準.txt` | `JL_標準.txt` |
| TV Asahi | `テレビ朝日`, `EX` | none (only a title-specific row) | `JL_標準.txt` | `JL_標準.txt` |
| TV Tokyo | `テレビ東京`, `TX` | none | `JL_標準.txt` | `JL_標準.txt` |

Sources: [ChList.csv L25-29], [JLparam_set1.csv L13], [JLparam_set2.csv L3-11]. Upstream's own channel data maps TBS the same way ([upstream ChParamJL1.csv L13]).

`JL_MBS.txt` is described as 「予告直後のロゴ付き１５秒構成は番組提供ではなく他番組宣伝としてカット」 ("the logo-bearing 15-second section right after the preview is cut as a promo for another program, not kept as a sponsor credit"). It sets `param_cuttr 1`, narrows the sponsor credit search, raises `param_wlogo_trmax` to 2:50, and then runs `JL_フラグ指定.txt`, whose defaults match `JL_標準.txt` ([JL_MBS.txt L1-12], [JL_MBS.txt L41-46]).

What this means for the adapter:

- **Logo:** to give `jlse` the right logo without changing any setting, mount a `logo/` folder that holds only that channel's logo ([docker-compose.yml L12-17]). Naming the input after the channel, for example `TBS_…`, would also find the logo, but it switches TBS recordings to `JL_MBS.txt`, so the five channels would no longer run the same defaults.
- **File type:** `jlse` rejects any input whose extension isn't `.ts` ([jlse.js L57-62]). Its AviSynth input opens the file with L-SMASH Works and takes stream index 1 as the audio ([jlse.js L74-86]). Whether that works on our MP4 under a `.ts` name is untested (section 5).

### 4.2 Settings in the JL command file

These live in `JL_標準.txt` and can be overridden per run with `-set <name> <value>` or `-flags`, which `jlse` passes through from the `JLOGO_OPT1`, `JLOGO_OPT2` and `JL_FLAGS` columns of its CSV files ([readme.txt L74-84], [設定内容.txt L61-79], [join_logo_frame.js L15-35]). A `Default` line only applies when the name isn't set yet, so `-set` wins ([全般.txt L78-81]).

| Setting | Default | What it controls | Effect of changing it |
|---|---|---|---|
| `param_cuttr` (`CutTR`) [JL_標準.txt L33-35] | 0 | Logo-on sections of 14 s or more after the preview, last 7:00 only | 1 cuts them as `Trailer(cut)`: closer to our definition for promos at the file end |
| `param_cutsp` (`CutSP`) [JL_標準.txt L33-35] | 0 | Recognized sponsor credits | 1 cuts them as `Sponsor(cut)`: closer to our definition |
| `param_adduc` (`AddUC`) [JL_標準.txt L33-35] | 0 | Long logo-less sections that aren't 15-second blocks | 1 keeps them and turns off the 40-second rule ([JlsDataset.cpp L121-160]) |
| `logo_revise` [JL_標準.txt L22-23] | 23 | Last digit: how hard to cut at logo edges. +10: cut runs of 15-second sections inside the logo. +20: cut wide logo-less stretches | +10 would cut runs of two or more logo-on 15-second sections totalling a multiple of 30 s, which catches some logo-bearing promos mid-recording ([JlsAutoReform.cpp L2284-2298]) |
| `logo_level` [JL_標準.txt L22-23] | 6 | How far the logo is trusted; the 5-second edge rule | 7 uses whole-second edge pieces, 4 only 15-second ones ([JlsAutoReform.cpp L3719-3731]) |
| `param_wlogo_cmmin` [JL_標準.txt L127-140] | 40 s | Logo-less stretch cut without 15-second blocks | Shorter cuts more short logo-less program |
| `param_wlogo_summin` [JL_標準.txt L127-140] | 20 s | Total logo time below which the logo is ignored | |
| `param_lgcut_first`, `param_wcomp_first`, `cutbaselogo`, `base` [JL_標準.txt L10-12], [JL_標準.txt L137-140] | 12 s, 30 s, 1, −1 | Start margin | |
| `param_wcomp_last`, `param_zone_last` [JL_標準.txt L15-16] | 30.5 s, 0 | End margin | |
| `fhead_ed`, `ftail_ed` [JL_標準.txt L197-199], [JL_標準.txt L264-265] | 13:30, 7:00 | Windows for sponsor credit, preview and endcard | |
| `cuttr_code`, `cuttr_limit`, `cutec_code`, `addsph_code1`-`5`, `addspt_code1`-`5`, `addec_code1`-`5` [JL_標準.txt L40-48], [JL_標準.txt L79-104] | see file | What counts as preview, sponsor credit and endcard at the file ends | |
| `edgest_code`, `edgeed_code`, `cut1st_code` [JL_標準.txt L109-116] | 0 | Cutting a fixed piece at every logo edge (`L-Edge`, `N-Edge`) | Non-zero adds these cuts |
| `-flags` (`JL_FLAGS`) | none | Named options in `JL_フラグ指定.txt`, for example `SC15` and `EC15` (cut a 15-second piece after or before a mid-program logo edge), `HCCM` and `TCCM` (file starts or ends with a logo-bearing promo to cut), `ASPN` (no sponsor credit) ([設定内容.txt L81-153]) | Only take effect with `JL_フラグ指定.txt` or `JL_MBS.txt` |
| `-CutMrgIn`, `-CutMrgOut` [readme.txt L56-72] | detected automatically | Logo-edge lag behind the scene change | Changes matching only, not output frames |

Outside the JL command file, `jlse` fixes chapter_exe's `-s 8 -e 4` ([chapterexe.js L7]), and logoframe runs with its built-in defaults ([logoset.h L13-18]).

### 4.3 Where the docs and the code disagree

The code wins in each case.

| Topic | Docs say | Code does |
|---|---|---|
| Sponsor credit length | `JL_MBS.txt` comments: 「期間6-14秒」 (6 to 14 s) ([JL_MBS.txt L28]) | 6 to 13 s ([JlsAutoScript.cpp L151-160]), as recorded in the v3.0 change log, 「デフォルト14秒以下の所を13秒以下に変更」 ("changed the default from 14 s or less to 13 s or less") ([修正内容.txt L125]) |
| Blank rows in `jlse`'s CSV files | 「記載なければ無条件で一致扱い」 ("a blank column always matches") ([設定内容.txt L47-49]) | The blank first row is only used when no other row matched ([param.js L57-69]). With our file names that is every channel, so the result is the same: `JL_標準.txt` with no flags |
| Missing logo | 「ロゴ期間がない場合は全フレームがロゴ表示とみなします」 ("with no logo periods, every frame counts as logo") ([readme.txt L42-44]) | It does build one whole-file logo stretch, but also marks the recording as logo-less ([JlsReformData.cpp L836-847]), and the Auto commands in `JL_標準.txt` then ignore the logo and cut by 15-second blocks ([JlsScript.cpp L2015-2030], [JL_標準.txt L187-190]). So a recording where logoframe finds no logo is not left uncut |

## 5. Open questions for a real run

| Question | Why it matters | Where a run answers it |
|---|---|---|
| Does each channel keep its logo on screen during promos, sponsor credits, station IDs and next-episode previews? | Decides most of the differences in section 1. | `obs_logoframe.txt` against the labels. Issue #7 already asks to note whether each channel's logo disappears during commercial breaks. |
| Does logoframe find our hand-made logos on app-window recordings throughout? | Under 20 s of logo in total switches to the 15-second-block fallback; dropouts of 40 s or more are cut as `Nologo`. | `obs_logoframe.txt`; no `L` sections in `obs_jlscp.txt`. |
| Is the gap between commercials still digital silence after the Xit Mobile app, macOS and OBS's AAC encoding? | chapter_exe only counts frames where every sample is ≤ 50 (about −56 dBFS) for at least 8 frames. Without those there are no boundaries and no 15-second blocks. | `obs_chapterexe.txt`: `SCPos` lines and `★` marks (15-second spacing) per labeled commercial break ([改造版_読んでね.txt L72-74]). |
| Does `jlse` read our MP4 under a `.ts` name, is stream index 1 the audio track, and can L-SMASH Works write its index file next to the input? | `jlse` refuses other extensions; a wrong audio stream would mean no silences. | A trial run on one recording. |
| How often do the start and end margins cut program? | Possible false flips in the first 12 to 30 s and the last 30.5 s of each recording. | The first and last `Trim` against the labels. |
| Does the end-of-file preview logic fire on recordings that end soon after a program? | It may keep long logo-bearing promos (`Trailer(cut-cancel)`) and cut short logo-on sections (`Trailer(cut)`, `Nologo(cut)`). | Kinds in the last 7 minutes of `obs_jlscp.txt`. |
| How long are sponsor credits, station IDs and endcards on our channels, and are they whole multiples of 5 s? | Logo-less ones next to a commercial break are cut only when they are. | Labels, plus the seconds column of `obs_jlscp.txt`. |
| Are whole-slot shopping programs, or any other programs, shown without the logo? | Any logo-less stretch of 40 s or more is cut. | `obs_logoframe.txt`. |
| How do very short commercial breaks (one or two commercials) and very long ones fare? | The code accepts a single 15-second block between logo stretches, but nothing was run. | Missed commercial breaks by length. |

## Sources

All links are permalinks at these commits:

- [tobitti0/JoinLogoScpTrialSetLinux@aabb505](https://github.com/tobitti0/JoinLogoScpTrialSetLinux/tree/aabb5054123008f514843056d0e229b278642b39): the Docker setup behind `jlse` and its submodule list.
- [tobitti0/join_logo_scp_trial@c38e970](https://github.com/tobitti0/join_logo_scp_trial/tree/c38e970a2ca52644f060ca8510040cc4ab4c413a): `jlse` itself (`src/`), its per-channel settings (`setting/`) and the JL command files it mounts (`JL/`).
- [tobitti0/join_logo_scp@646a0fd](https://github.com/tobitti0/join_logo_scp/tree/646a0fd9c0e1a1badeac826412873126cd3bc589): the join_logo_scp v4.0 source `jlse` builds, its readme and its command docs (`JL/doc/JLコマンド説明_全般.txt`, `JLコマンド説明_Autocutメモ.txt`, `JLコマンド説明_補助解説.txt`, cited below as 全般.txt, Autocutメモ.txt and 補助解説.txt).
- [tobitti0/logoframe@c93aec0](https://github.com/tobitti0/logoframe/tree/c93aec0c89838e9b4dd3a9a3d5496dfaaa41311d): logo detection.
- [tobitti0/chapter_exe@d74f65f](https://github.com/tobitti0/chapter_exe/tree/d74f65ffa6c08066425a1aaa6464f6936ff7254b): silence and scene change detection. Its `改造版_読んでね.txt` is Shift-JIS, so GitHub may not display it legibly.
- [yobibi/join_logo_scp@4107b3e](https://github.com/yobibi/join_logo_scp/tree/4107b3e0e1a798287603b76b8d6d734c9c01396a): current upstream (v5.1.1), checked for differences.

[TrialSet .gitmodules]: https://github.com/tobitti0/JoinLogoScpTrialSetLinux/blob/aabb5054123008f514843056d0e229b278642b39/.gitmodules#L1-L15
[TrialSet README L21-27]: https://github.com/tobitti0/JoinLogoScpTrialSetLinux/blob/aabb5054123008f514843056d0e229b278642b39/README.md#L21-L27
[Dockerfile L12-29]: https://github.com/tobitti0/JoinLogoScpTrialSetLinux/blob/aabb5054123008f514843056d0e229b278642b39/docker/Dockerfile#L12-L29
[docker-compose.yml L12-17]: https://github.com/tobitti0/JoinLogoScpTrialSetLinux/blob/aabb5054123008f514843056d0e229b278642b39/docker-compose.yml#L12-L17

[trial README L52-64]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/README.md#L52-L64
[trial README L82]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/README.md#L82
[jlse.js L57-62]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/jlse.js#L57-L62
[jlse.js L74-86]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/jlse.js#L74-L86
[jlse.js L109-124]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/jlse.js#L109-L124
[settings.js L21-45]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/settings.js#L21-L45
[channel.js L14-33]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/channel.js#L14-L33
[channel.js L68]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/channel.js#L68
[param.js L10-12]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/param.js#L10-L12
[param.js L57-69]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/param.js#L57-L69
[param.js L73-101]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/param.js#L73-L101
[logoframe.js L25-40]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/command/logoframe.js#L25-L40
[logoframe.js L42-58]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/command/logoframe.js#L42-L58
[chapterexe.js L7]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/command/chapterexe.js#L7
[join_logo_frame.js L15-35]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/command/join_logo_frame.js#L15-L35
[chapter_jls.js L4-30]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/output/chapter_jls.js#L4-L30
[chapter_jls.js L37-56]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/output/chapter_jls.js#L37-L56
[chapter_jls.js L89-91]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/output/chapter_jls.js#L89-L91
[chapter_jls.js L344-347]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/output/chapter_jls.js#L344-L347
[chapter_jls.js L381-451]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/src/output/chapter_jls.js#L381-L451
[ChList.csv L25-29]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/ChList.csv#L25-L29
[JLparam_set1.csv L1-2]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/JLparam_set1.csv#L1-L2
[JLparam_set1.csv L9]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/JLparam_set1.csv#L9
[JLparam_set1.csv L13]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/JLparam_set1.csv#L13
[JLparam_set2.csv L3]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/JLparam_set2.csv#L3
[JLparam_set2.csv L3-11]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/JLparam_set2.csv#L3-L11
[JLparam_set2.csv L8]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/JLparam_set2.csv#L8
[JLparam_set2.csv L10]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/JLparam_set2.csv#L10
[JLparam_set2.csv L13]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/JLparam_set2.csv#L13
[JLparam_set2.csv L22-23]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/JLparam_set2.csv#L22-L23
[設定内容.txt L3-4]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/%E8%A8%AD%E5%AE%9A%E5%86%85%E5%AE%B9.txt#L3-L4
[設定内容.txt L47-49]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/%E8%A8%AD%E5%AE%9A%E5%86%85%E5%AE%B9.txt#L47-L49
[設定内容.txt L61-79]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/%E8%A8%AD%E5%AE%9A%E5%86%85%E5%AE%B9.txt#L61-L79
[設定内容.txt L81-153]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/%E8%A8%AD%E5%AE%9A%E5%86%85%E5%AE%B9.txt#L81-L153
[設定内容.txt L95]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/%E8%A8%AD%E5%AE%9A%E5%86%85%E5%AE%B9.txt#L95
[設定内容.txt L150-151]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/setting/%E8%A8%AD%E5%AE%9A%E5%86%85%E5%AE%B9.txt#L150-L151
[JL_標準.txt L10-12]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L10-L12
[JL_標準.txt L15-16]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L15-L16
[JL_標準.txt L22-23]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L22-L23
[JL_標準.txt L26]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L26
[JL_標準.txt L33-35]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L33-L35
[JL_標準.txt L34]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L34
[JL_標準.txt L40-48]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L40-L48
[JL_標準.txt L79-104]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L79-L104
[JL_標準.txt L109-116]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L109-L116
[JL_標準.txt L121-122]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L121-L122
[JL_標準.txt L127-128]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L127-L128
[JL_標準.txt L127-140]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L127-L140
[JL_標準.txt L130]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L130
[JL_標準.txt L131]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L131
[JL_標準.txt L132]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L132
[JL_標準.txt L137-140]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L137-L140
[JL_標準.txt L148-149]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L148-L149
[JL_標準.txt L187-190]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L187-L190
[JL_標準.txt L197-199]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L197-L199
[JL_標準.txt L211-215]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L211-L215
[JL_標準.txt L220-221]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L220-L221
[JL_標準.txt L264-265]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L264-L265
[JL_標準.txt L273]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L273
[JL_標準.txt L282-286]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L282-L286
[JL_標準.txt L282-292]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L282-L292
[JL_標準.txt L287-292]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A8%99%E6%BA%96.txt#L287-L292
[JL_MBS.txt L1-12]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_MBS.txt#L1-L12
[JL_MBS.txt L28]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_MBS.txt#L28
[JL_MBS.txt L41-46]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_MBS.txt#L41-L46
[JL_構成30分単位.txt L9-14]: https://github.com/tobitti0/join_logo_scp_trial/blob/c38e970a2ca52644f060ca8510040cc4ab4c413a/JL/JL_%E6%A7%8B%E6%88%9030%E5%88%86%E5%8D%98%E4%BD%8D.txt#L9-L14

[fork README L3-4]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/README.md#L3-L4
[readme.txt L8-11]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/readme.txt#L8-L11
[readme.txt L24-26]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/readme.txt#L24-L26
[readme.txt L42-44]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/readme.txt#L42-L44
[readme.txt L56-72]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/readme.txt#L56-L72
[readme.txt L74-84]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/readme.txt#L74-L84
[readme.txt L90-98]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/readme.txt#L90-L98
[readme.txt L121-122]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/readme.txt#L121-L122
[修正内容.txt L125]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/%E4%BF%AE%E6%AD%A3%E5%86%85%E5%AE%B9.txt#L125
[全般.txt L9-12]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_%E5%85%A8%E8%88%AC.txt#L9-L12
[全般.txt L78-81]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_%E5%85%A8%E8%88%AC.txt#L78-L81
[全般.txt L390-400]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_%E5%85%A8%E8%88%AC.txt#L390-L400
[Autocutメモ.txt L17-24]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_Autocut%E3%83%A1%E3%83%A2.txt#L17-L24
[Autocutメモ.txt L81-84]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_Autocut%E3%83%A1%E3%83%A2.txt#L81-L84
[Autocutメモ.txt L168-171]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_Autocut%E3%83%A1%E3%83%A2.txt#L168-L171
[Autocutメモ.txt L236-250]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_Autocut%E3%83%A1%E3%83%A2.txt#L236-L250
[Autocutメモ.txt L296-299]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_Autocut%E3%83%A1%E3%83%A2.txt#L296-L299
[補助解説.txt L213-223]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_%E8%A3%9C%E5%8A%A9%E8%A7%A3%E8%AA%AC.txt#L213-L223
[補助解説.txt L225-233]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_%E8%A3%9C%E5%8A%A9%E8%A7%A3%E8%AA%AC.txt#L225-L233
[補助解説.txt L235-245]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_%E8%A3%9C%E5%8A%A9%E8%A7%A3%E8%AA%AC.txt#L235-L245
[JlsIF.cpp L442-450]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsIF.cpp#L442-L450
[JlsIF.cpp L560-581]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsIF.cpp#L560-L581
[JlsDataset.hpp L22-36]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.hpp#L22-L36
[JlsDataset.cpp L42-43]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L42-L43
[JlsDataset.cpp L90-96]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L90-L96
[JlsDataset.cpp L121-160]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L121-L160
[JlsDataset.cpp L870-908]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L870-L908
[JlsDataset.cpp L1520-1587]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L1520-L1587
[JlsDataset.cpp L1556-1571]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L1556-L1571
[JlsDataset.cpp L2311-2318]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L2311-L2318
[JlsDataset.cpp L2339-2378]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L2339-L2378
[JlsDataset.cpp L2383-2459]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L2383-L2459
[JlsDataset.cpp L2421-2436]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsDataset.cpp#L2421-L2436
[JlsNameSpace.hpp L37-75]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsNameSpace.hpp#L37-L75
[JlsAutoReform.cpp L179-225]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L179-L225
[JlsAutoReform.cpp L189]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L189
[JlsAutoReform.cpp L218-222]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L218-L222
[JlsAutoReform.cpp L426-488]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L426-L488
[JlsAutoReform.cpp L1537-1541]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L1537-L1541
[JlsAutoReform.cpp L1661-1671]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L1661-L1671
[JlsAutoReform.cpp L1772-1819]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L1772-L1819
[JlsAutoReform.cpp L2016-2020]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L2016-L2020
[JlsAutoReform.cpp L2155-2208]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L2155-L2208
[JlsAutoReform.cpp L2227-2251]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L2227-L2251
[JlsAutoReform.cpp L2284-2298]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L2284-L2298
[JlsAutoReform.cpp L2371-2396]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L2371-L2396
[JlsAutoReform.cpp L3136-3176]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L3136-L3176
[JlsAutoReform.cpp L3185-3213]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L3185-L3213
[JlsAutoReform.cpp L3703-3764]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L3703-L3764
[JlsAutoReform.cpp L3719-3731]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L3719-L3731
[JlsAutoReform.cpp L3782-3793]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L3782-L3793
[JlsAutoReform.cpp L3859-3934]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L3859-L3934
[JlsAutoReform.cpp L5084-5115]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L5084-L5115
[JlsAutoReform.cpp L5126-5156]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoReform.cpp#L5126-L5156
[JlsAutoScript.cpp L151-160]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoScript.cpp#L151-L160
[JlsAutoScript.cpp L1143-1152]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoScript.cpp#L1143-L1152
[JlsAutoScript.cpp L1342-1351]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoScript.cpp#L1342-L1351
[JlsAutoScript.cpp L1410-1468]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoScript.cpp#L1410-L1468
[JlsAutoScript.cpp L2976-2986]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsAutoScript.cpp#L2976-L2986
[JlsScriptLimit.cpp L115-159]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsScriptLimit.cpp#L115-L159
[JlsScript.cpp L1294-1320]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsScript.cpp#L1294-L1320
[JlsScript.cpp L2015-2030]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsScript.cpp#L2015-L2030
[JlsReformData.cpp L34-146]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsReformData.cpp#L34-L146
[JlsReformData.cpp L836-847]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/JlsReformData.cpp#L836-L847
[CnvStrTime.cpp L13-15]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/CnvStrTime.cpp#L13-L15
[CnvStrTime.cpp L146-152]: https://github.com/tobitti0/join_logo_scp/blob/646a0fd9c0e1a1badeac826412873126cd3bc589/src/CnvStrTime.cpp#L146-L152

[logoset.h L13-18]: https://github.com/tobitti0/logoframe/blob/c93aec0c89838e9b4dd3a9a3d5496dfaaa41311d/src/logoset.h#L13-L18
[logoframe_mul.c L177-213]: https://github.com/tobitti0/logoframe/blob/c93aec0c89838e9b4dd3a9a3d5496dfaaa41311d/src/logoframe_mul.c#L177-L213
[logoframe_det.c L3896-3902]: https://github.com/tobitti0/logoframe/blob/c93aec0c89838e9b4dd3a9a3d5496dfaaa41311d/src/logoframe_det.c#L3896-L3902

[chapter_exe.cpp L37-49]: https://github.com/tobitti0/chapter_exe/blob/d74f65ffa6c08066425a1aaa6464f6936ff7254b/src/chapter_exe.cpp#L37-L49
[chapter_exe.cpp L83-86]: https://github.com/tobitti0/chapter_exe/blob/d74f65ffa6c08066425a1aaa6464f6936ff7254b/src/chapter_exe.cpp#L83-L86
[chapter_exe.cpp L327-357]: https://github.com/tobitti0/chapter_exe/blob/d74f65ffa6c08066425a1aaa6464f6936ff7254b/src/chapter_exe.cpp#L327-L357
[chapter_exe.cpp L363]: https://github.com/tobitti0/chapter_exe/blob/d74f65ffa6c08066425a1aaa6464f6936ff7254b/src/chapter_exe.cpp#L363
[chapter_exe.cpp L791]: https://github.com/tobitti0/chapter_exe/blob/d74f65ffa6c08066425a1aaa6464f6936ff7254b/src/chapter_exe.cpp#L791
[改造版_読んでね.txt L11-13]: https://github.com/tobitti0/chapter_exe/blob/d74f65ffa6c08066425a1aaa6464f6936ff7254b/%E6%94%B9%E9%80%A0%E7%89%88_%E8%AA%AD%E3%82%93%E3%81%A7%E3%81%AD.txt#L11-L13
[改造版_読んでね.txt L47-50]: https://github.com/tobitti0/chapter_exe/blob/d74f65ffa6c08066425a1aaa6464f6936ff7254b/%E6%94%B9%E9%80%A0%E7%89%88_%E8%AA%AD%E3%82%93%E3%81%A7%E3%81%AD.txt#L47-L50
[改造版_読んでね.txt L72-74]: https://github.com/tobitti0/chapter_exe/blob/d74f65ffa6c08066425a1aaa6464f6936ff7254b/%E6%94%B9%E9%80%A0%E7%89%88_%E8%AA%AD%E3%82%93%E3%81%A7%E3%81%AD.txt#L72-L74

[upstream JlsDataset.cpp L3267-3290]: https://github.com/yobibi/join_logo_scp/blob/4107b3e0e1a798287603b76b8d6d734c9c01396a/src/JlsDataset.cpp#L3267-L3290
[upstream JlsDataset.cpp L3292-3370]: https://github.com/yobibi/join_logo_scp/blob/4107b3e0e1a798287603b76b8d6d734c9c01396a/src/JlsDataset.cpp#L3292-L3370
[upstream JL_標準.txt L33-35]: https://github.com/yobibi/join_logo_scp/blob/4107b3e0e1a798287603b76b8d6d734c9c01396a/JL/JL_%E6%A8%99%E6%BA%96.txt#L33-L35
[upstream 全般.txt L1012-1013]: https://github.com/yobibi/join_logo_scp/blob/4107b3e0e1a798287603b76b8d6d734c9c01396a/JL/doc/JL%E3%82%B3%E3%83%9E%E3%83%B3%E3%83%89%E8%AA%AC%E6%98%8E_%E5%85%A8%E8%88%AC.txt#L1012-L1013
[upstream ChParamJL1.csv L13]: https://github.com/yobibi/join_logo_scp/blob/4107b3e0e1a798287603b76b8d6d734c9c01396a/JL/data/ChParamJL1.csv#L13
