# The detector needs both audio and video

The detector always uses both the audio and the video track; audio-only or video-only input is not supported for now. Both tracks carry useful signs of a commercial break (the channel logo and editing on screen, loudness and silence in the sound), and supporting a single-track fallback would mean building and scoring a second detector. The earlier version of this project was audio-only, so a reader may expect audio-only input to work; revisit this if a live source can only supply one track.
