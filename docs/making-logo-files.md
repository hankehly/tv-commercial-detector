# Making a logo file

How to make the logo file join_logo_scp needs for a channel, on this Mac, from our own recordings, so the benchmark ([#7](https://github.com/hankehly/tv-commercial-detector/issues/7)) can run join_logo_scp on that channel. One logo file per channel; a new channel takes about five minutes.

In one line: the `make-logo` command samples a recording, shows you where the logo sits, and measures the logo from the moments when the picture around it is plain.

## Why we make our own

join_logo_scp tells program from commercials partly by whether the channel's logo is on screen. To spot the logo it needs a logo file: where the logo sits, its shape, and how see-through it is.

| Usual way to get one | Why it doesn't work for us |
|---|---|
| Make it with AviUtl's logo plugin or with Amatsukaze | Both are Windows programs. The Linux setup guides for join_logo_scp point to them and offer nothing else |
| Download one that someone else made | They are made from the broadcast itself, 1440×1080. Our recordings come from the Xit Mobile app's window, which shows the picture slightly zoomed in, so the logo sits about 15 pixels further right and 8 pixels higher than a downloaded file says (see the appendix) |

So `make-logo` measures the logo straight from our recordings. It needs only ffmpeg, which the benchmark already uses.

## Steps

All commands run from the repository root. The examples make TV Asahi's logo file.

1. **Get a picture of the corner.** Give the channel, written exactly as in the label files, and one or more recordings of it. A recording is a path, or just the name of a file in the data folder's `recordings/` folder.

   ```bash
   uv run tv-commercial-detector make-logo "TV Asahi" 2026-11-01_13-59-38.mp4
   ```

   It takes about a minute and a half for a three-hour recording, and saves `data/logos/TV Asahi.still.png`.

2. **Find the logo in that picture.** The picture shows the top right corner of the screen twice, with rulers along the top and left that count in pixels of the whole 1920×1080 picture:

   | Half | Bright lines show | Good for |
   |---|---|---|
   | Top | Outlines that are there in most frames | A logo that is nearly always on, such as NTV's. Captions a long program keeps on screen show up here too |
   | Bottom | Outlines that are there whenever the corner is otherwise calm and dark | A logo on a channel whose programs fill the corner with captions, such as TV Asahi's. Captions shown over commercials, such as 意見広告, show up here too |

   The logo is the shape you recognise as the channel's. It may show in one half only.

3. **Read a box around the logo off the rulers**, as `X,Y,WIDTH,HEIGHT`: the left and top of the box, then its size. Leave 10 to 20 pixels of room on every side, and keep anything else that stays on screen out of the box. The box doesn't need to be exact: the command trims it to the logo.

4. **Make the logo file** by running the same command again with the box:

   ```bash
   uv run tv-commercial-detector make-logo "TV Asahi" 2026-11-01_13-59-38.mp4 --box 1715,35,135,83
   ```

   It saves `data/logos/TV Asahi.lgd`, replacing any logo file already there, and a picture of the result, `data/logos/TV Asahi.png`.

5. **Look at `data/logos/TV Asahi.png`.** It shows the measured logo over black, grey and white. It should show the channel's whole logo and nothing else. If part of the logo is missing or something else is in it, go back to step 3 with a better box.

6. **Run `uv run tv-commercial-detector validate`.** The channel is no longer listed as having no logo file. If join_logo_scp has already run on the channel's recordings, run the benchmark with `--rerun` so it uses the new logo file.

## When the command says no

`make-logo` refuses to save a logo it can't measure properly. Each message says what to do; these are the rules behind them.

| It stops when | Threshold | What to do |
|---|---|---|
| Too few frames show something in the box while the picture around the box is plain | Fewer than 30 frames | Check the box is around the logo. If it is, give more recordings of the channel in the same command |
| Those frames don't agree on what is in the box | The typical frame strays from the others by more than 2 brightness levels (out of 255) | Something else is in the box, or the box isn't on the logo. Draw it again |
| Those frames are all about as bright as each other | Their backgrounds span less than 40 brightness levels | Give more recordings, so there are both dark and bright scenes behind the logo |
| Nothing in the box is opaque enough to be a logo | No pixel is 4% opaque or more | The box isn't on the logo. Draw it again |
| The logo reaches the edge of the box | A logo pixel within 2 pixels of an edge | Make the box bigger on the side the message names |
| The box isn't inside the sampled corner | The corner is the top right 512×256 pixels of the picture | Check the numbers were read off the rulers |

A logo that is in the picture but outside the top right corner can't be made with this command yet. None of the pilot channels needs that.

## The pilot channels

Made on 2026-11-14 from the six pilot recordings.

| Channel | Recordings used | Box given | Box in the logo file | Most opaque pixel | Frames used |
|---|---|---|---|---|---|
| TBS | `2026-11-01_10-56-55.mp4` | 1755,13,130,75 | 1764,22,112,58 | 21% | 388 |
| TV Asahi | `2026-11-01_13-59-38.mp4` | 1715,35,135,83 | 1724,40,118,72 | 31% | 32 |
| NTV | `2026-11-01_17-01-22.mp4`, `2026-11-02_04-01-26.mp4` | 1770,10,130,97 | 1780,20,112,78 | 22% | 129 |
| Fuji TV | `2026-11-01_21-48-37.mp4` | 1810,5,92,95 | 1820,12,74,80 | 16% | 244 |
| TV Tokyo | `2026-11-02_01-00-51.mp4` | 1758,25,137,63 | 1768,34,116,46 | 10% | 477 |

- Each run took 80 to 90 seconds for one three-hour recording, and about two minutes for NTV's two recordings.
- "Frames used" are the frames that showed the logo over plain surroundings, out of about 5,600 sampled per three-hour recording.
- TV Asahi's logo rests on only 32 frames, just over the limit of 30: that afternoon's programs kept captions in the corner nearly all the time. Its logo came out clean, but the next TV Asahi recording is worth adding to the command to firm it up.
- TV Asahi's logo is the slanted bar and the words "tv asahi" under it. The 意見広告 caption that shows in the same place belongs to commercials, not to the logo.

<!-- PILOT-CHECK -->

## How it works

A broadcaster blends its logo over the picture. At each pixel of the logo:

```
what you see = background × (1 − opacity) + logo brightness × opacity
```

The opacity and the logo's brightness are what the logo file holds, for every pixel. The background is the problem: it is hidden behind the logo.

`make-logo` uses the moments when it isn't hidden. If the picture all around the box is plain (a dark scene, a wall, a sky), then the picture inside the box would be the same plain background, were the logo not there. Over many such frames, with dark backgrounds and bright ones, each pixel's brightness plotted against its background falls on a straight line. The line's slope gives the pixel's opacity, and its height gives the logo's brightness.

| Step | What happens |
|---|---|
| Sample | ffmpeg reads the top right 512×256 pixels of every keyframe: one frame every two seconds or so, a few thousand per recording |
| Keep plain frames | A frame is kept if the 12-pixel band around the box fits an evenly lit surface to within 1.5 brightness levels, and that surface tilts by less than 12 levels from side to side. The outermost 4 pixels of the picture are ignored: a window capture leaves them dark |
| Drop frames with nothing in the box | Frames without the logo, such as commercials, look plain inside the box too. A frame is kept only if at least 2% of the box differs from its background by more than 4 levels |
| Fit, and drop frames that disagree | Each pixel's line is fitted. Frames that stray from the lines, such as a caption passing through the box, are dropped, and the lines fitted again until the same frames stay |
| Trim and save | Pixels less than 2% opaque are written as empty. The box is trimmed to the logo plus 6 pixels on every side and saved as a logo file |

Only brightness is measured. A logo file also has room for the logo's colour, which join_logo_scp doesn't read, so `make-logo` leaves it empty. The files are therefore no good for erasing a logo from a recording, which this project doesn't do.

## Appendix: logo files others have made

Logo files for Japanese channels are shared online. A collection with all five pilot channels is [lgdファイル置き場](http://namihe.s223.xrea.com/lgd/), made from 1440×1080 broadcasts. They were compared with ours on 2026-11-14, and can't be used as they are:

| Channel | Public file (its date) | Where its logo would be in a 1920-wide picture | Where the logo is in our recordings | Most opaque pixel: public, ours |
|---|---|---|---|---|
| TBS | `TBS_2021-10-09` | x 1756–1852, y 38–81 | x 1771–1868, y 28–72 | 22%, 21% |
| TV Asahi | `EX_2021-09-06` | x 1717–1819, y 56–110 | x 1731–1835, y 48–103 | 34%, 32% |
| NTV | `NTV_2021-10-16` | x 1772–1867, y 35–99 | x 1786–1884, y 26–91 | 24%, 22% |
| Fuji TV | `CX_2025-07-04` | x 1811–1871, y 27–92 | x 1827–1885, y 19–85 | 17%, 16% |
| TV Tokyo | `TX_2023-11-14` | x 1757–1862, y 47–80 | x 1774–1878, y 40–72 | 11%, 10% |

- **Position:** on every channel the logo sits about 15 pixels further right and 8 pixels higher in our recordings. That is what a picture zoomed in by about 2% around its centre looks like: the Xit Mobile app doesn't show the outer 1% or so of the broadcast on each side.
- **Shape and opacity:** once a public logo is stretched to 1920 wide, zoomed and shifted to fit, it matches ours closely: a correlation of 0.96 to 0.99 on every channel, with ours 2 to 12% less opaque. Two measurements made in different ways agreeing this well is the main evidence that `make-logo` measures the right thing.
- **Brightness:** the public files give the logos a brightness of 229 to 234, close to video white (235). In our recordings they measure 208 to 218. Our recordings squeeze the broadcast's brightness: their black sits near level 30, not 16, as if each level v had become 16 + v × 219 ÷ 255. That would turn 232 into 215, which fits.
- **Why not convert the public files instead?** <!-- PUBLIC-VERDICT -->

The public files aren't in the repository or the data folder. The page states no terms of use.

## Appendix: the logo file format

A logo file (`.lgd`) is the format of AviUtl's logo plugin, version 0.1. This is the layout that join_logo_scp's logoframe reads (`logo.h` in its source):

| Bytes | Holds |
|---|---|
| 28 | The text `<logo data file ver0.1>`, padded with zero bytes |
| 4 | The number of logos in the file, most significant byte first. We always write 1 |
| 32 | The logo's name, in Shift_JIS, padded with zero bytes. We write the channel |
| 16 | Eight 16-bit numbers: x, y, height, width, then four that logoframe ignores (fades and start and end frames), written as 0 |
| 12 per pixel | Row by row, six 16-bit numbers for each pixel: opacity and value for brightness, then the same for each of the two colour channels |

Every number after the count is written least significant byte first. Opacity runs from 0 to 1000. Brightness runs from 0 for video black (level 16) to 4096 for video white (level 235).
