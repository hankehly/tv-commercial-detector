# Comskip, built from source, for the benchmark's look-ahead detectors.
#
# Build:  docker build --tag tv-commercial-detector/comskip tools/comskip
# Run:    tools/comskip-docker, which takes the same arguments as comskip.
#
# See docs/installing-comskip-and-join-logo-scp.md.

FROM ubuntu:24.04 AS build

# The newest commit on Comskip's master branch as of 2026-11-08 (0.83.001).
ARG COMSKIP_COMMIT=a140b6ac8bc8f596729e9052819affc779c3b377

# The packages Comskip's own Linux CI installs, without SDL: that only adds the GUI.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        autoconf automake build-essential ca-certificates git \
        libargtable2-dev libavformat-dev libswscale-dev libtool pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/erikkaashoek/Comskip.git /src \
    && cd /src \
    && git checkout --quiet "$COMSKIP_COMMIT" \
    && ./autogen.sh \
    && ./configure \
    && make \
    && make install

FROM ubuntu:24.04

# The ffmpeg package brings the same FFmpeg libraries Comskip was built against.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg libargtable2-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local/bin/comskip /usr/local/bin/comskip

ENTRYPOINT ["comskip"]
