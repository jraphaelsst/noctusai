# Pinned to bookworm to get OpenSSL 3.0.x. The default `python:3.11-slim`
# tag tracks Debian trixie, which ships OpenSSL 3.5.x. OpenSSL 3.5's
# ML-KEM-768 post-quantum hybrid key exchange + Cloudflare's edge
# rollback produces mid-handshake EOFs and large-body
# RemoteProtocolErrors when calling OpenAI / Anthropic / any
# Cloudflare-fronted API from inside the container. See
# .promotions/openssl-tls-workaround.md for the full story.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System packages: gcc + libffi for cryptography (Fernet token encryption),
# curl for healthcheck, git for any git+ deps the seed packages may carry,
# ffmpeg for ffprobe (video aspect-ratio detection in gdrive folder classification).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libpq-dev \
        curl \
        git \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ─── Seed packages (from noc, via additional build context) ──────────────
# The workspace symlinks `seed/` into the noc repo. Docker COPY does not
# follow directory symlinks at build time, so we use Buildx's named
# additional-context (declared in docker-compose.yml as `noc`) to pull the
# real seed/ directory into the image. Editable install keeps imports
# resolvable to the absolute paths the volume mount preserves at runtime.
COPY --from=noc seed/lib/backend ./_seed/lib/backend
COPY --from=noc seed/framework/backend ./_seed/framework/backend
RUN pip install --no-cache-dir \
    -e ./_seed/lib/backend \
    -e ./_seed/framework/backend

# ─── Product backend dependencies ────────────────────────────────────────
# Two-pass install: requirements.txt has `-e seed/lib/backend` and
# `-e seed/framework/backend` lines that we already satisfied above; the
# pip resolver tolerates re-declarations as long as the project layout
# matches. We strip those lines from a tmp copy to keep the install clean.
COPY products/youtube-crawler/backend/requirements.txt /tmp/requirements.txt
RUN grep -v '^-e seed/' /tmp/requirements.txt > /tmp/requirements.clean.txt \
    && pip install --no-cache-dir -r /tmp/requirements.clean.txt

# Product code (mounted as volume in dev; copied here so the image is
# runnable standalone for staging / quick smoke tests).
COPY products/youtube-crawler/backend/app ./products/youtube-crawler/backend/app
COPY products/youtube-crawler/backend/migrations ./products/youtube-crawler/backend/migrations
COPY products/youtube-crawler/backend/tests ./products/youtube-crawler/backend/tests

EXPOSE 8010

# Health check uses the seed-provided /api/health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8010/api/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8010", \
     "--app-dir", "products/youtube-crawler/backend"]
