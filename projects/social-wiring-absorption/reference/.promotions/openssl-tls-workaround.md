---
slug: openssl-tls-workaround
origin:
  - conf/openssl-tls12.cnf
  - docker-compose.yml (OPENSSL_CONF env + bind mount + MTU 1450 network)
intended_noc_destination: templates/seed-workspace-docker/conf/openssl-tls12.cnf + docker-compose.yml MTU+OPENSSL_CONF pattern
layer_rationale: |
  Infrastructure carve-out belonging in the seed's Docker workspace
  template. Solves a transport-layer issue that affects ANY noc
  product whose backend calls Cloudflare-fronted APIs (OpenAI,
  Anthropic, Stripe, many fintech APIs) from inside a Docker
  container built on a Python 3.11 image with OpenSSL 3.5.
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Every product using AI APIs
  hits this from Docker. Affects all current chatbot products and
  any future LLM integration.
  Q2 — Variance? None. The fix is identical regardless of which
  Cloudflare-fronted API is being called.
  Q3 — Existing seed coverage? None.
  Q4 — Fake+Real? N/A (infrastructure).
  Q5 — Migration cost? Low. Copy 2 files + edit template
  docker-compose.yml.
  Q6 — Premature lift risk? Medium. Better long-term solution is
  to switch the Python base image to one with OpenSSL 3.0 or 3.1.
  This carve-out is a tactical fix; track the strategic one.
dependencies_on_other_additions: []
promoted_on: not-yet
---

## Why this addition exists

While validating live Meta integration end-to-end on 2026-05-13, the
chatbot's OpenAI API calls started failing with two distinct TLS-
layer errors:

1. **TLS handshake EOF** — `unexpected eof while reading` during
   ClientHello. Affected ALL Cloudflare-fronted endpoints from
   inside the container, but worked fine from the macOS host with
   the same network. The error fingerprints to **OpenSSL 3.5 +
   Cloudflare ML-KEM-768 post-quantum hybrid key exchange**
   negotiation — Cloudflare initially supported it then rolled
   back in some regions.

2. **Server disconnects mid-response** for large payloads
   (~16-20 KB). Persists even after capping TLS at 1.2. Smaller
   requests (~1 KB) succeed. Symptom is `httpx.RemoteProtocolError:
   Server disconnected without sending a response`.

## What this manifest ships

### `conf/openssl-tls12.cnf`

Minimal OpenSSL config that caps `MaxProtocol = TLSv1.2`. Loaded
via the `OPENSSL_CONF` env var on the `app` service. Mitigates
issue #1 (TLS 1.3 handshake EOF). Python's ssl module honors this;
curl in the same container doesn't (uses a different OpenSSL init
path) but our backend traffic goes through Python httpx.

### `docker-compose.yml` MTU override

```yaml
networks:
  default:
    driver: bridge
    driver_opts:
      com.docker.network.driver.mtu: "1450"
```

Reduces the bridge network's MTU from 1500 to 1450. Mitigates
issue #1 in a different way (Docker Desktop macOS vpnkit's MTU
issue). Worth keeping even after switching to a different OpenSSL
since the vpnkit issue is independent.

## What this DOESN'T fix

**Issue #2 (large-body disconnects) is still present.** The
chatbot's full request payload (8 KB system prompt + 22 tool
definitions = ~20 KB) triggers Cloudflare to drop the connection
mid-response. Smaller requests work.

**Real fix:** rebuild the container image with a Python base that
ships OpenSSL 3.0 or 3.1 instead of 3.5. Suggested:

```dockerfile
# Was: FROM python:3.11-slim (OpenSSL 3.5.x as of 2026)
# Try: FROM python:3.11-slim-bookworm (Debian's OpenSSL 3.0.x)
# Or:  FROM python:3.12-slim       (OpenSSL 3.1.x — may also work)
```

Track this in `.promotions/openssl-3.5-image-rebuild.md` (TBD).

## Integration notes for noc-side

1. **Add `conf/openssl-tls12.cnf` to**
   `templates/seed-workspace-docker/conf/openssl-tls12.cnf` and
   reference it from the template's docker-compose.yml the same
   way our product does.

2. **Add the MTU 1450 network config** to the template's
   docker-compose.yml. Comment the rationale.

3. **Document in `KB § PATTERNS/containerization.md`** the
   OpenSSL 3.5 + Cloudflare known issue and the two-layer fix. Add
   a note recommending OpenSSL 3.0/3.1 base images for any product
   making heavy LLM API calls until the OpenSSL upstream
   stabilizes.

4. **Open question:** should the seed's `noctusai_lib.integrations.llm`
   module wrap httpx with an explicit TLS context override (max
   v1.2, disabled ML-KEM groups) so individual products don't have
   to inherit this carve-out? Tradeoff: cleaner per-product setup
   vs. less observable workaround.

## Failure modes catalog (for the noc-side runbook)

| Symptom | Layer | Likely cause |
|---|---|---|
| `curl: (35) ... unexpected eof while reading` from inside container | TLS handshake | OpenSSL 3.5 ML-KEM vs Cloudflare. Apply OPENSSL_CONF fix |
| `httpx.ConnectError: ...UNEXPECTED_EOF_WHILE_READING` | Python httpx, same layer | Same. OPENSSL_CONF fix applies |
| `httpx.RemoteProtocolError: Server disconnected without sending a response` (small request) | HTTP layer | Transient. Retry. |
| Same error on **every** request to Cloudflare-fronted API regardless of payload | HTTP layer | Sign of cipher mismatch (ML-KEM still being negotiated). Verify OPENSSL_CONF env var made it into the process: `cat /proc/PID/environ \| tr '\0' '\n' \| grep OPENSSL` |
| Same error ONLY on large requests (>10 KB body) | HTTP/transport | Issue #2. Requires base image change. Not solved by OPENSSL_CONF alone. |
| Error appears intermittently | Cloudflare edge | Likely region-specific PQ rollback. Wait or retry. |
