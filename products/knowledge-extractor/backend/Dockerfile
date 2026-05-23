# syntax=docker/dockerfile:1.7
# knowledge-extractor — BACKEND-ONLY house container (single uvicorn, no SPA).
#
# `FROM noctus-seed-backend-base` IS the named seam (inherit-and-extend, never
# fork) — the Docker analog of create_product_app. This product has NO frontend,
# so (unlike the canonical products/seed/ Dockerfile) there is no frontend-build
# stage, no node, and no SERVE_SPA_DIR — uvicorn serves the API only.
# `check_product_container_shape` gates the SPA markers on a `frontend/` dir, so
# this backend-only shape is house-conformant.
#
# Build context: repo root. Prereq: noctus-seed-backend-base:dev exists
# (scripts/infra/build-base-images.sh; start.sh orders it first).
ARG GIT_SHA=dev

# ── runtime: API on one port (the slim, shippable image) ────────────────
FROM noctus-seed-backend-base:dev AS runtime
ARG GIT_SHA
LABEL org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="noctus-knowledge-extractor"
WORKDIR /app

# ffmpeg — SYSTEM dep for audio extraction/chunking
# (app/integrations/media/audio.py). Not a pip package.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Product-specific Python deps (seed lib/framework already in the base venv;
# strip the `-e seed/` editable lines — they're inherited).
COPY products/knowledge-extractor/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/req.clean.txt \
    && pip install -r /tmp/req.clean.txt

# Product backend code (no SPA to copy).
COPY products/knowledge-extractor/backend/ ./products/knowledge-extractor/backend/

# Non-root user — created LAST (pip ran as root above). chown ONLY /app, never
# the inherited /opt/venv base layer (anti-pattern: a `chown -R` on the shared
# base rewrites ~276MB into an unshared per-product layer — see products/seed).
RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app
USER noctus

EXPOSE 8012
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8012/api/health || exit 1
# Slim runtime CMD = plain uvicorn over the baked code (deploy/CI run as-is).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", \
     "--port", "8012", "--app-dir", "products/knowledge-extractor/backend"]

# ── runtime-watch: SAME single container, local live-reload ─────────────
# ONE container, ONE shape (`./start.sh`). The local compose builds THIS
# target + bind-mounts source. Backend-only ⇒ no vite/node/local-watch — just
# `uvicorn --reload` (it watches the bind-mounted .py). Deploy uses the slim
# `runtime` above. Source is bind-mounted at run, so this target is
# intentionally not a shippable artifact — `runtime` is.
FROM runtime AS runtime-watch
USER noctus
ENV PRODUCT_SLUG=knowledge-extractor PRODUCT_PORT=8012
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8012", \
     "--app-dir", "products/knowledge-extractor/backend", "--reload"]
