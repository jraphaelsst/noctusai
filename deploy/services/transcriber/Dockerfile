# noctus-transcriber — self-hosted faster-whisper worker (infrastructure, NOT a product).
# Contract: products/social-wiring/projects/core-studio/specs/transcription-contract.md §2.
#
# Build context = REPO ROOT (the worker imports noctusai_lib.integrations.transcription):
#   docker build -f deploy/services/transcriber/Dockerfile -t transcriber:local .
#
# Reproducibility: python deps are hash-locked (requirements.lock); the model is baked
# at a PINNED HF commit sha; runtime has NO egress and HF_HUB_OFFLINE=1.
FROM python:3.12-slim-bookworm

# Pinned model revision (bump deliberately; the CI tag embeds it). NB: the HF repo
# `mobiuslabsgmbh/faster-whisper-large-v3-turbo` now redirects to `dropbox-dash/...`;
# the sha resolves through the redirect.
ARG MODEL_REPO=mobiuslabsgmbh/faster-whisper-large-v3-turbo
ARG MODEL_REVISION=0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/services/transcriber/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

# Bake the model weights (build-time egress only).
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('${MODEL_REPO}', revision='${MODEL_REVISION}', local_dir='/models/large-v3-turbo')" \
    && rm -rf /root/.cache

COPY seed/lib/backend/noctusai_lib /app/noctusai_lib

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin transcriber

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    TRANSCRIBER_MODEL_PATH=/models/large-v3-turbo \
    PORT=9000

# Build-time smoke: the server package must import with only the locked deps.
RUN python -c "import noctusai_lib.integrations.transcription.server as s; import faster_whisper; print('import ok')"

USER 10001

LABEL org.opencontainers.image.source="https://github.com/jraphaelsst/noctusai" \
      org.opencontainers.image.description="noctus-transcriber (faster-whisper large-v3-turbo)"

EXPOSE 9000
# nice: a non-root process can only de-prioritize, which is what we want; cpu_shares does the real work.
ENTRYPOINT ["nice", "-n", "10", "python", "-m", "noctusai_lib.integrations.transcription.server"]
