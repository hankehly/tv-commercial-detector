# syntax=docker/dockerfile:1

# The JoinLogoScpTrialSetLinux setup (jlse running chapter_exe, logoframe and
# join_logo_scp), for the benchmark's look-ahead detectors.
#
# Build:  docker build --platform linux/amd64 --tag tv-commercial-detector/join_logo_scp tools/join_logo_scp
# Run:    tools/jlse-docker RECORDING LOGO
#
# This is the setup's own docker/Dockerfile, with three changes:
#   - it fetches the setup itself, at a fixed commit, instead of needing a clone;
#   - it pins delogo-AviSynthPlus-Linux, which the setup clones at its newest commit;
#   - it installs Node.js 10 from Ubuntu 20.04 instead of NodeSource's setup_10.x
#     script, which no longer works: its package signatures can't be verified.
# The base image is built for linux/amd64 only.
#
# See docs/installing-comskip-and-join-logo-scp.md.

FROM ghcr.io/tobitti0/docker-avisynthplus:4.3.1-ubuntu2004 AS build

ENV DEBIAN_FRONTEND=noninteractive

# The newest commit of tobitti0/JoinLogoScpTrialSetLinux as of 2026-11-08,
# with its submodules: chapter_exe, logoframe, join_logo_scp 4.0.0,
# join_logo_scp_trial (jlse) and tsdivider.
ADD https://github.com/tobitti0/JoinLogoScpTrialSetLinux.git#aabb5054123008f514843056d0e229b278642b39 /tmp/setup

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        curl git make gcc g++ cmake libboost-all-dev \
    && rm -rf /var/lib/apt/lists/*

RUN cd /tmp/setup/modules/chapter_exe/src \
    && make \
    && mv chapter_exe /tmp/setup/modules/join_logo_scp_trial/bin/ \
    && cd /tmp/setup/modules/logoframe/src \
    && make \
    && mv logoframe /tmp/setup/modules/join_logo_scp_trial/bin/ \
    && cd /tmp/setup/modules/join_logo_scp/src \
    && make \
    && mv join_logo_scp /tmp/setup/modules/join_logo_scp_trial/bin/ \
    && mkdir /tmp/setup/modules/tsdivider/build \
    && cd /tmp/setup/modules/tsdivider/build \
    && cmake -DCMAKE_BUILD_TYPE=Release .. \
    && make \
    && mv tsdivider /tmp/setup/modules/join_logo_scp_trial/bin/ \
    && mv /tmp/setup/modules/join_logo_scp_trial /join_logo_scp_trial

# The newest commit of tobitti0/delogo-AviSynthPlus-Linux as of 2026-11-08.
ARG DELOGO_COMMIT=e55cfa2067f82ce8755b85d672eeba9c6dde9977

RUN git clone https://github.com/tobitti0/delogo-AviSynthPlus-Linux.git /tmp/delogo \
    && cd /tmp/delogo \
    && git checkout --quiet "$DELOGO_COMMIT" \
    && cd src \
    && make \
    && cp libdelogo.so /join_logo_scp_trial

FROM ghcr.io/tobitti0/docker-avisynthplus:4.3.1-ubuntu2004 AS release

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /join_logo_scp_trial

COPY --from=build /join_logo_scp_trial /join_logo_scp_trial

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        nodejs npm \
        libboost-filesystem-dev libboost-program-options-dev libboost-system-dev \
    && rm -rf /var/lib/apt/lists/* \
    && node -v \
    && npm --version \
    && mv libdelogo.so /usr/local/lib/avisynth \
    && npm install

ENTRYPOINT ["npm", "start", "--", "-i"]
CMD ["--help"]
