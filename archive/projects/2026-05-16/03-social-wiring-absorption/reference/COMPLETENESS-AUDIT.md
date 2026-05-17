# Completeness Audit — social-wiring Absorption (Wave 0.2)

> **Durable, self-contained.** Refers to every artifact by its in-home
> `projects/social-wiring-absorption/reference/...` path. No originating-workspace
> path string appears here (the originating workspace is transient and the user
> retires it manually). Dated facts only.

- **Audit date:** 2026-05-16
- **Engineer:** BRING-HOME (chunk W0.2)
- **Purpose:** Confirm every useful artifact from the originating seed-workspace
  is either (a) ported as product source by a later Wave, or (b) mapped by a
  promotion manifest, or (c) copied in-home here, or (d) surfaced below as
  UNMAPPED-useful — and produce the user's "safe-to-delete" sign-off.
- **Originating-workspace state at audit time:** snapshot-committed (a
  `snapshot/pre-noc-absorption-2026-05-16` branch with the in-flight validated
  work was created in W0.1; HEAD = `snapshot: preserve in-flight validated work
  before noc absorption`). The two-other-Slice caveats noted in the
  `whatsapp-connection-page` / `whatsapp-intake-monitor` manifests
  (`standard_routers=["whatsapp_admin"]` opt-in line + `Intake*` DTOs +
  `app/main.py` router registration) are captured in that snapshot branch.

---

## (a) Coverage table — manifest slug → workspace code surface → covered?

14 promotion manifests are copied to `reference/.promotions/`. The
`reference/PROMOTIONS.md` index `## Pending` list is **stale** (lists only 7 of
14 entries — `drive-api-client`, `google-scope-discovery`, `meta-integrations`,
`openssl-tls-workaround`, `production-deploy-tooling`, `recreate-script`,
`whatsapp-connection-page`, `whatsapp-intake-monitor` exist as full manifests
but are not all in the index). **The 14 `.promotions/*.md` files are the
authoritative map**, not the index. (Finding logged — see project findings.md.)

| # | Manifest slug | Workspace code surface it maps | Seed/product destination | Covered? |
|---|---|---|---|---|
| 1 | `whatsapp-chatbot-service` | `services/whatsapp_chatbot_service.py` | `noctusai_lib/domain/chatbot/openai_orchestrator.py` | ✅ mapped (superseded by #7 platform-chat-agent — surface-agnostic) |
| 2 | `waha-response-registry` | `services/waha_response_registry.py` + SQLite `waha_response_samples` migration in `apply_sqlite_migrations.py` | `noctusai_lib/integrations/whatsapp/response_registry.py` | ✅ mapped |
| 3 | `platform-chat-agent` | `services/chatbot_service.py`, `routers/chat_router.py`, `tests/services/test_chatbot_service.py`, `frontend/pages/Chat.tsx`, `frontend/hooks/useChat.ts` | `noctusai_lib/domain/chatbot/openai_orchestrator.py` + `noctusai_lib/api/chat_router.py` + `noctusai_lib/frontend/components/Chat` | ✅ mapped (Wave 1.E1 + Wave 2) |
| 4 | `multimodal-stack` | `services/media_service.py`, `services/message_store.py`, `migrations/007_conversation_messages.sql` | `noctusai_lib/integrations/media/inbound_resolver.py` + `noctusai_lib/domain/chatbot/message_store.py` (+migration) | ✅ mapped (Wave 1.E5 + E1) |
| 5 | `single-url-tunnel` | `proxy/nginx.conf`, `frontend/nginx/default.conf`, `frontend/src/lib/apiBase.ts` | seed-workspace-docker template + product-seed frontend + `noctusai_lib/frontend/lib/apiBase.ts` | ✅ mapped — infra copied to `reference/proxy/nginx.conf` (Open Q #2: largely redundant under house single-container model; decide W1.E7/W6) |
| 6 | `google-integrations` | `services/calendar/`, `services/routing/`, `routers/calendar_router.py` | `noctusai_lib/integrations/google/{calendar,routing}/` + `noctusai_lib/api/calendar_router.py` | ✅ mapped (Wave 1.E3) |
| 7 | `drive-api-client` | `services/drive_api/` | `noctusai_lib/integrations/google/drive/` | ✅ mapped (Wave 1.E3) |
| 8 | `google-scope-discovery` | `services/google_scopes.py`, `routers/google_router.py`, `tests/services/test_google_scopes.py` | `noctusai_lib/integrations/google/scopes/` | ✅ mapped (Wave 1.E3) |
| 9 | `meta-integrations` | `services/meta/`, `routers/meta_router.py`, `tests/services/test_meta_integration.py`, `docs/integrations/META_API_REFERENCE.md` | `noctusai_lib/integrations/meta/` (+ KB INTEGRATIONS/meta.md) | ✅ mapped (Wave 1.E4); doc copied to `reference/docs/integrations/META_API_REFERENCE.md` |
| 10 | `openssl-tls-workaround` | `conf/openssl-tls12.cnf`, `docker-compose.yml` MTU/OPENSSL_CONF pattern | seed-workspace-docker template conf + compose pattern | ✅ mapped — copied to `reference/conf/openssl-tls12.cnf` + `reference/docker-compose.yml` (Wave 6 container refactor; note manifest's own caveat: tactical fix, strategic fix = OpenSSL 3.0/3.1 base image) |
| 11 | `production-deploy-tooling` | `scripts/deploy/{01,02,03}*.sh` + `scripts/deploy/DEPLOY.md` | seed-workspace-docker template `scripts/deploy/` | ✅ mapped — copied to `reference/scripts/deploy/` (Wave 5/6) |
| 12 | `recreate-script` | `scripts/recreate.sh` | seed-workspace-docker template `scripts/recreate.sh` | ✅ mapped — copied to `reference/scripts/recreate.sh` (Wave 5/6) |
| 13 | `whatsapp-connection-page` | `frontend/pages/Conexao.tsx`, `frontend/hooks/useWhatsAppConnection.ts` | **none** — product-local skin; reusable seam ALREADY in noc seed (commit `d81d88e`, `whatsapp_admin` router + `createWhatsAppConnectionHooks`) | ✅ mapped (Wave 2 — product skin ports with the product) |
| 14 | `whatsapp-intake-monitor` | `routers/intake_monitor_router.py`, `tests/routers/test_intake_monitor_router.py` | **none yet** — product-local; revisit seed-lift at N=2 | ✅ mapped (Wave 2 — ports with product; accept-with-rationale at N=1) |

**Root handoff-note cross-reference** (all already in-home at noc root, *not* in
the workspace — they were filed into noc by earlier sessions):

- `SESSION-NOTES_chatbot-multichannel-2026-05-12.md` → corroborates #1/#3/#4 (Wave 1.E1/E5).
- `SESSION-NOTES_google-integrations-2026-05-12.md` → corroborates #6 (Wave 1.E3).
- `SESSION-NOTES_drive-api-2026-05-13.md` → corroborates #7 (Wave 1.E3).
- `SESSION-NOTES_google-scope-discovery-2026-05-13.md` → corroborates #8 (Wave 1.E3).
- `SESSION-NOTES_meta-integration-2026-05-13.md` → corroborates #9 (Wave 1.E4).
- `SESSION-NOTES_vite-supabase-build-arg-2026-05-16.md` → seed fix (Wave 1.E7: vite-supabase-build-arg). **NOT one of the "5" the brief named — extra, recent, in-scope.**
- `SESSION-NOTES_seed-frontend-standalone-drift-2026-05-16.md` → seed fix (Wave 1.E7: standalone-frontend degradation). **NOT one of the "5" — extra, recent, in-scope.**
- `OAUTH-PATTERNS-FOR-NOC.md` → corroborates #6/#7/#8/#9 OAuth credential-bundle reconciliation (Wave 1.E3/E4).
- `SEED-NEEDS-DEV-AUTH-AND-SQLITE.md` → Wave 1.E7 dev-auth + SQLite pre-wired seed fix.

> **Discrepancy note (for the architect, not a blocker):** PROJECT.md §3
> and the W0.2 brief reference "**5** root SESSION-NOTES". There are in fact
> **7** `SESSION-NOTES_*.md` at the noc root; the 2 extra
> (`vite-supabase-build-arg`, `seed-frontend-standalone-drift`, both
> 2026-05-16) are the newest and are already accounted for by PROJECT.md §5
> Wave 1.E7 ("vite-supabase-build-arg + standalone-frontend degradation"), so
> coverage is intact — only the *count* in the prose is stale. PROJECT.md §3
> wording could be updated "5 → 7" by the architect.

**Product source code itself** (backend `app/` 70 .py files across
routers/services/schemas + 8 migrations + `apply_sqlite_migrations.py` +
`requirements.txt`; frontend `src/` 14 pages + hooks + components) is **NOT
copied here by design** — per the W0.2 brief it is ported as `social-wiring`
product source in **Wave 2** directly from the snapshot-committed workspace
state. W0.2 copies the MAP + docs + infra only. This is intentional, not a gap.

---

## (b) UNMAPPED-useful list

Items of value NOT covered by a manifest/handoff-note. Each: in-home path (or
precise description) + 1-line value + recommended absorption destination.

1. **`reference/AGENT.md`** — 28 KB authoritative chatbot system-prompt /
   capability spec + tool catalog. Value: the live-validated source of truth for
   what the chatbot can/can't do and exact tool descriptions. Destination: feed
   into Wave 1.E1 (orchestrator system-prompt constructor-arg) + Wave 2 product
   chatbot wiring; harvest neutral tool copy for `noctusai_lib`.
2. **`reference/SYSTEM-ARCHITECTURE.md`** (30 KB) + **`reference/PLAN.md`**
   (40 KB) + **`reference/CHECKLIST.md`** + **`reference/ANALYSIS.md`** —
   end-to-end architecture/plan/checklist/analysis of the validated stack.
   Value: design rationale not captured in any single manifest. Destination:
   Wave 5 absorption-playbook source material; keep in `reference/` as durable
   design record.
3. **`reference/WORKSPACE-findings.md`** (30 KB) — the workspace's own
   slips/lessons/knowledge log. Value: live-validation learnings (TLS, WAHA
   drift, OAuth gotchas). Destination: mine into project `findings.md` + Wave 5
   playbook; durable in `reference/`.
4. **`reference/WORKSPACE-README.md`** — workspace onboarding doc. Value: quick
   orientation. Destination: reference only; superseded by social-wiring README
   authored in Wave 2.
5. **`reference/SETUP_META.md`** + **`reference/CF_TUNNEL.md`** — operator setup
   runbooks (Meta app creation, Cloudflare tunnel). Value: operator-facing
   how-to. Destination: Meta → fold into KB INTEGRATIONS/meta.md (Wave 1.E4 /
   Wave 5); CF tunnel → KB containerization pattern (Wave 6).
6. **`reference/docs/integrations/META_API_REFERENCE.md`** — full internal Meta
   Graph API reference. Value: single source for Meta app + connect. Destination:
   `KB § INTEGRATIONS/meta.md` (called out by `meta-integrations` manifest §6).
7. **`reference/scripts/sync_waha_webhook.sh`** — WAHA webhook-sync helper.
   Value: operator ergonomics for re-pointing WAHA webhook after URL change.
   **Not covered by any manifest.** Destination: seed-workspace-docker template
   `scripts/` alongside `recreate.sh` (Wave 5/6) — small N=1, accept-with-
   rationale until a 2nd WAHA consumer, or fold into the `whatsapp_admin` seam.
8. **`reference/refresh_cf_tunnel.sh`** + **`reference/start.sh`** +
   **`reference/stop.sh`** — workspace ops scripts. Value: the workspace's
   2-container ops loop (divergent from noc house single-container model).
   Destination: **reference-only**; noc house `start.sh`/`stop.sh` already exist;
   used by Wave 6 only to confirm nothing operationally unique is lost in the
   container refactor (divergent-arch rule — refactor to house model, do not
   port the 2-container shape).
9. **`reference/Dockerfile.frontend`** + **`reference/proxy/nginx.conf`** —
   the divergent 2-container backend+nginx+proxy topology. Value: documents the
   architecture being *refactored away* (Open Q #2 / divergent-arch rule).
   Destination: reference-only input to Wave 6; the house single-container
   `serve_spa` seam replaces it.
10. **Backend `WAHA_RESPONSE_FORMATS.md`** (in workspace at
    `products/youtube-crawler/backend/WAHA_RESPONSE_FORMATS.md`, ~4 KB —
    **NOT copied here**; travels with Wave 2 product port). Value: documented
    WAHA response-shape variants — companion to the `waha-response-registry`
    manifest (#2). Destination: alongside `noctusai_lib/integrations/whatsapp/
    response_registry.py` (Wave 1.E2) as the seed module's drift-doc. **Flag
    for Wave 1.E2 / Wave 2 engineer** so it is not left behind with the deleted
    product tree.
11. **`reference/.env.example`** (12 KB) — every env var the validated stack
    reads (OpenAI/Google/Meta/WAHA/Vista/Supabase/Fernet). Value: authoritative
    env contract for the consolidated product. Destination: basis for
    `products/social-wiring/.env.example` (Wave 2) + Wave 6 compose env wiring.
12. **`reference/scripts/deploy/DEPLOY.md`** + `01/02/03*.sh` — production
    VPS+Cloudflare-Tunnel deploy automation (mapped by `production-deploy-
    tooling` #11, listed here for the explicit Wave 5 KB pattern
    `KB § PATTERNS/production-deployment.md` the manifest requests — ensure that
    KB pattern doc is actually authored, not just the template copy).

**Explicitly NOT useful / NOT copied (correctly excluded):**
`node_modules`, `frontend/dist`, `.git`, `__pycache__`, `.venv`,
`.noctusai-state`, `tmp/dev.sqlite3` (regenerable dev DB), `secrets/*.json`
(real Google OAuth client secrets — **must NOT be promoted**; per-deployment
operator-supplied), `.env` / `.env.bak.*` (live secrets), `oauth-url.txt` /
`test_user.txt` (transient dev scratch), `.githooks/pre-commit` (workspace's
symlinked noc hook — already in noc), `CLAUDE.md`/`CLAUDE`/`KNOWLEDGE-BASE`/
`mcp`/`seed`/`templates`/`.claude` (symlinks back into noc — already in-home).

> ⚠️ **Security note for the user:** the originating workspace contains live
> credentials (`.env`, `.env.bak.*`, `secrets/*.json`, `oauth-url.txt`). These
> were intentionally NOT copied in-home. They are not needed for absorption
> (code+schema only). They ARE a reason to delete the workspace promptly after
> sign-off rather than leave it lying around.

---

## (c) SAFE-TO-DELETE checklist (user-walkable)

Walk this before manually deleting the originating workspace. Every line is
verifiable from in-home paths only.

- [ ] **Snapshot exists.** A `snapshot/pre-noc-absorption-2026-05-16` git
      branch was created in W0.1 capturing the validated in-flight work
      (including the two entangled-Slice caveats). If you want belt-and-braces,
      `git -C <workspace> bundle create ~/social-wiring-snapshot.bundle --all`
      before deleting — but this is optional; all *useful* content is in-home.
- [ ] **14 promotion manifests in-home.** `ls
      projects/social-wiring-absorption/reference/.promotions/` shows 14 `.md`
      files (the migration map). `reference/PROMOTIONS.md` index copied too
      (note: its index list is stale — manifests are authoritative).
- [ ] **All workspace docs in-home.** `reference/AGENT.md`,
      `SYSTEM-ARCHITECTURE.md`, `PLAN.md`, `CHECKLIST.md`, `ANALYSIS.md`,
      `SETUP_META.md`, `CF_TUNNEL.md`, `WORKSPACE-findings.md`,
      `WORKSPACE-README.md`, `docs/integrations/META_API_REFERENCE.md` all
      present (10 docs).
- [ ] **All infra references in-home.** `reference/docker-compose.yml`,
      `Dockerfile`, `Dockerfile.frontend`, `proxy/nginx.conf`,
      `conf/openssl-tls12.cnf`, `start.sh`, `stop.sh`,
      `refresh_cf_tunnel.sh`, `.env.example`, `scripts/` (6 files incl.
      `deploy/`, `recreate.sh`, `sync_waha_webhook.sh`) all present.
- [ ] **Product source ported (Wave 2 gate, NOT W0.2).** Before deleting,
      confirm Wave 2 has ported the backend `app/` (routers/services/schemas/
      8 migrations/`apply_sqlite_migrations.py`/`requirements.txt`) and frontend
      `src/` into `products/social-wiring/`. **W0.2 deliberately did not copy
      product source** — it is lifted live from the snapshot in Wave 2. *Do not
      delete the workspace until Wave 2 has consumed it OR you have the snapshot
      branch/bundle.*
- [ ] **`WAHA_RESPONSE_FORMATS.md` not orphaned.** Confirm the Wave 1.E2 /
      Wave 2 engineer has carried `backend/WAHA_RESPONSE_FORMATS.md` alongside
      the `whatsapp/response_registry` seed module (UNMAPPED item #10) — it
      lives only in the product tree, not in `reference/`.
- [ ] **Secrets accounted for.** You (the user) have, or can re-supply, the
      Google OAuth client-secret JSONs and `.env` values — these were
      deliberately NOT copied in-home (security). No absorption step needs them;
      they are operator-supplied per deployment.
- [ ] **Nothing else of value.** This audit's UNMAPPED list (section b) is
      exhaustive vs. the workspace tree as of 2026-05-16. No loose script,
      half-finished feature, or bespoke doc was found outside it.

---

## Sign-off verdict

**READY for the user to manually delete the originating workspace — with ONE
explicit precondition:**

> The originating workspace must NOT be deleted until **Wave 2 has ported the
> product source code** (backend `app/` + migrations + frontend `src/` +
> `WAHA_RESPONSE_FORMATS.md`) into `products/social-wiring/`, **OR** the user
> retains the `snapshot/pre-noc-absorption-2026-05-16` branch / a `git bundle`.

Rationale: W0.2 (by design) brings in-home the **map + docs + infra**, not the
product source — the source is lifted live in Wave 2. The map (14 manifests),
all workspace docs, all infra references, and all handoff notes ARE fully
in-home now. The only thing not yet duplicated outside the workspace/snapshot is
the product *source tree*, which Wave 2 consumes directly. As long as the
snapshot branch exists (it does — W0.1) **the workspace is already safe to
delete today** without data loss; deleting *before* Wave 2 just means Wave 2
must port from the snapshot branch instead of the working tree (functionally
equivalent).

**Net:** all useful, non-secret content is in-home or in the W0.1 snapshot. No
unmapped value is at risk. Verdict: **READY** (precondition above is a
sequencing note, not missing content).
