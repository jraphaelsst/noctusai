# mcp-connector-expansion — Project Document

> Living document. Architect-owned. Engineers build chunks; this file is the dashboard.

- **Created:** 2026-05-17
- **Last updated:** 2026-05-17
- **Status:** Implementation COMPLETE (architect-inline finish) — 15 commits on `mcp-connector-expansion`; all connector MCP suites green (_kit 19 · vista 12 · meta 28 · google 31). Pending: user-gated phased push integration→main; R1–R7 KB-depth codification residual (specs in §6); engineer-default.md R6 edit needs explicit user auth (harness-blocked self-modification).
- **Owner / stakeholders:** joaoraphaelsst (architect: Claude Opus 4.7) · engineers (subagents)
- **Related docs:** `KB § PATTERNS/mcp-tool-conventions.md` · `KB § INTEGRATIONS/vista.md` · `KB § INTEGRATIONS/oauth-patterns.md` · `KB § PATTERNS/whatsapp-chatbot-seed.md` · `mcp/vista/` (canonical connector-MCP shape)
- **Project slug:** `mcp-connector-expansion` — cross-product / platform-infra ⇒ `projects/mcp-connector-expansion/` (`expansion` intent)

---

## 1. Context & Purpose

The `social-wiring` product was developed in a separate repo and absorbed (project `social-wiring-absorption`, archived 2026-05-16). That absorption did **#1 of two absorptions**: the connector capabilities were lifted into the shared library `seed/lib/backend/noctusai_lib/integrations/` — so products consume them by import + factory wiring. That side is **substantially done**: `meta`, `whatsapp`, `vista`, `google_calendar`, `google_maps`, `youtube`, `google_drive`, `email`, `llm` all ship the canonical Protocol+Fake+Real+factory shape; `domain/chatbot/` ships the buffer/worker/dispatcher.

This project is **absorption #2**: expose those already-lib-ified connectors as **LLM-callable MCP tools**, so an agent (this CLI, a product agent loop, the dev-team, a future personal assistant) gets a real tool-belt — "post/read on IG, reply on WhatsApp, check the calendar, pull a Drive doc, push a Vista listing." Because absorption #1 is done, absorption #2 is **thin**: each connector MCP is a few hundred lines wrapping the lib's Real adapters — `mcp/vista` proves the shape (it wraps `noctusai_lib.integrations.vista`; tools are shells).

The win: a vendor-grouped connector-MCP fleet (`mcp/vista` live + `mcp/meta` + `mcp/google`) on a shared connector-kit, fully documented in KB, registration left opt-in per the MCP keep-list discipline. This is step one toward an LLM personal assistant (tool-belt + knowledge/memory + loop).

---

## 2. Confirmed constraints

- **Two absorptions, distinct** — #1 = lib (products consume funcs; *done* by `social-wiring-absorption`); #2 = connector MCP servers (LLM executes tasks). *(This project is strictly #2 + the KB-doc gap of #1.)*
- **Grouping = per vendor** — `mcp/meta` (`meta.facebook.*`/`meta.instagram.*`/`meta.whatsapp.*`, future `meta.ads.*`), `mcp/google` (`google.calendar.*`/`google.maps.*`/`google.youtube.*`/`google.drive.*`), improve `mcp/vista`. *(User chose per-vendor over per-service; matches lib package boundaries + OAuth bundles + the `<vendor>.<service>.<action>` convention. Rules out `mcp/instagram`+`mcp/facebook`+… sprawl.)*
- **All connectors, ordered simplest→complex** — not a single pilot. *(Wave order encodes the gradient: vista-refactor < meta < google.)*
- **Full-speed dispatch; architect coordinates** — user: *"act like the brain coordinating teams of devs … you're on the spotlight."* Parallel agent done. *(Branching-first; engineers in isolated worktrees; architect stays with user.)*
- **Personal-assistant trajectory confirmed** — user: *"a first ('maybe' not first hehehe) step on developing a personal assistant with knowledge and automated processes."* *(Shapes credential model toward single-operator, not multi-tenant.)*

---

## 3. Design principles

1. **Thin wrappers, never re-implementations.** A connector MCP tool calls `noctusai_lib.integrations.<vendor>` Real adapters/factories and serializes the result. Zero connector logic in `mcp/`. The lib is the substrate; the MCP is the agent-facing face. (Mirrors `mcp/vista/tools/imoveis.py`.)
2. **Deferred-config, always boots.** Server starts cleanly with no creds (vista rule); tool calls return typed-error envelopes when unconfigured. No import-time credential reads.
3. **Single-operator credential model for v1.** This MCP serves the operator/assistant, not per-tenant orgs. Creds resolve from co-located `.env` / env (system-user token / api_key / OAuth refresh) → lib factory. Multi-tenant org-scoped resolution stays a *product* concern (the lib already supports it via resolvers; the MCP just doesn't need it). Recorded so a future agent doesn't bolt org-routing onto the assistant MCP.
4. **Convention-strict naming.** `<vendor>.<service>.<action>`, Pydantic In/Out per tool, hierarchical `register(server)` + `all_handlers()`/`all_descriptors()` aggregation — exactly the `mcp/vista` shape.
5. **Verify-the-seed-ships-it gates scope.** A tool ships only for a capability the lib's *Real* adapter actually implements. Read-only-v1 / missing surfaces are named out-of-scope with a destination, never silently stubbed.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every consumer?** YES — every connector MCP shares: stdio bootstrap, `mcp/` sys.path trick, deferred-config settings (frozen dataclass + `lru_cache` + co-located `.env`), typed-error envelope, `LEAF_MODULES`→`all_handlers`/`all_descriptors` aggregation, Pydantic-In/Out registration.
2. **Is the data source consumer-specific?** NO for the kit (uniform bootstrap); YES per vendor for the tool bodies (each wraps its own lib package — correctly vendor-bound).
3. **Is the placement consumer-specific?** NO — all live under `mcp/<vendor>/`, a uniform platform location.
4. **Is the visibility / permission rule the same?** YES — uniform deferred-config + typed-error; per-vendor auth differences (api-key vs system-user-token vs OAuth) are absorbed by the *lib factory*, not re-expressed in `mcp/`.
5. **Does the seam already exist?** PARTIAL — `mcp/vista` *embodies* the shape but vista-privately (its `server.py` boilerplate, `settings.py` pattern, `tools/__init__.py` aggregation). **N=2** (vista + meta) ⇒ triage; **N=3** (vista + meta + google) ⇒ **MUST formalize**. ⇒ extract a shared `mcp/_kit/` connector-kit; refactor vista onto it as the proof (vista tests are the unchanged-behavior oracle).
6. **Default-on or opt-in?** OPT-IN at the registration boundary (`.mcp.json`) — per the MCP keep-list discipline (CLAUDE.md §1: noctusai+supabase only without explicit approval). Servers are built+runnable+documented; live registration is a user decision (§7 Q1). The *kit* itself is default-shape for any future connector MCP.

**Litmus — per-vendor/per-product code count:** **0 per-product lines.** Connector MCPs are platform infra, not product code. The shared kit is the seed-first formalization. **No replication framing in §6** — phases work in `mcp/_kit/` + per-vendor servers that compose it, not "repeat the boilerplate 3×."

---

## 4. Scope

**In scope:**
- `mcp/_kit/` — shared connector-MCP kit (bootstrap, settings base, typed-error envelope, registry aggregation, Pydantic-In/Out helper).
- `mcp/vista` — refactor onto `_kit` (behavior unchanged; tests green = oracle). Finally land its `.mcp.json` registration recommendation.
- `mcp/meta` — `meta.facebook.*` (pages/posts/insights — read-only v1), `meta.instagram.*` (accounts/media/insights — read-only v1), `meta.whatsapp.*` (send_text + inbound inspect, via WAHA client), `meta.diagnostics.*` (connection status / scope discovery). Wraps `noctusai_lib.integrations.{meta,whatsapp}`.
- `mcp/google` — `google.calendar.*`, `google.maps.*`, `google.youtube.*` (incl. upload — lib ships it), `google.drive.*` (download + reader). Wraps the 4 lib factories.
- KB integration docs, **two-part per vendor**: **(A) consume-side recipe** — how a product wires `noctusai_lib.integrations.<vendor>` via named seams (import → factory → credential-resolver injection → router mount). This is OVERDUE absorption-#1 debt (`social-wiring-absorption` lifted the code but never shipped these docs); independent of the MCP waves ⇒ pulled forward to **Wave 1b (parallel to Wave 1)**. **(B) MCP-side surface** — the `mcp/<vendor>` tool list; appended in Wave 3 after the servers exist. Both + INDEX.md + CLAUDE.md routing pointers + memory three-way sync.
- Per-server `README.md` + tests mirroring `mcp/vista/tests/`.

**Now IN scope (user directive 2026-05-18 "defer ≠ resolve / implement all of them" — the filed-deferral was the slip; resolvable-now gaps resolve now):**
- **Gmail** — `noctusai_lib.integrations.gmail` canonical Protocol+Fake+Real+factory built NOW (Engineer GMAIL-LIB); `gmail-seed-lift` filed-stub **removed** (folded into this project); `google.gmail.*` MCP tools land in the wave-gated MCP-write-surface step.
- **Meta posting / IG publish / `meta.ads.*`** — lib `meta` extended write-capable NOW (Engineer META-WRITE-LIB), App-Review-gated with typed-error honesty (mirrors `youtube.upload`), then `meta.{facebook,instagram,ads}.*` MCP tools in the same wave-gated step.
- **Live `.mcp.json` registration of vista/meta/google** — user now explicitly approves (overrides the keep-list default); architect registers at project-close consolidation.

**Out of scope (genuinely — distinct from the slip above; needs a decision OR different domain):**
- **Multi-tenant org-scoped credential routing in the MCP** — design principle #3; lib supports it product-side, assistant-MCP intentionally single-operator.
- **social-wiring RLS/`standard_routers` compliance (93/100)** — GOOG-2 surfaced `email_marketing/scheduler.py` admin `.table()` on `campaigns`/`automation_enrollments` lacking `service_role_bypass` policies + `main.py` non-literal `standard_routers`. *Legitimate* out-of-scope (different domain — social-wiring product RLS, unrelated to connectors; needs a schema decision = the fix-on-contact "needs-a-decision" exception). Destination: surfaced to user (below) + social-wiring-owner / an RLS-migration follow-up. NOT the gmail-type slip — this is not resolvable within connector scope.
- **`crm_service`/`dashboard_service`** — product-internal orchestration, not a vendor connector; revisit post-fleet.
- **`crm_service`/`dashboard_service`/other social-wiring product services as MCP** — product-internal orchestration, not a vendor connector; revisit after the vendor fleet lands.

---

## 5. Architecture

```
mcp/
  _kit/                      ← NEW (Wave 1) — shared connector-MCP kit
    __init__.py              ← exports: run_stdio_server, ConnectorSettings,
                                typed_error, build_registry, ToolSpec
    bootstrap.py             ← sys.path trick + stderr logging + stdio_server run loop
                                (extracted verbatim-equivalent from mcp/vista/server.py)
    settings.py              ← ConnectorSettings base: frozen dataclass + lru_cache
                                + co-located .env loader (generalize mcp/vista/settings.py)
    registry.py              ← LEAF_MODULES→all_handlers/all_descriptors helper
    errors.py                ← typed_error(e) envelope (generalize vista _typed_error)
    tests/                   ← kit unit tests
  vista/                     ← REFACTOR (Wave 1) onto _kit; behavior unchanged
  meta/                      ← NEW (Wave 2) — server.py + settings.py + tools/{facebook,
                                instagram,whatsapp,diagnostics}.py + types.py + tests + README
  google/                    ← NEW (Wave 2) — server.py + settings.py + tools/{calendar,
                                maps,youtube,drive}.py + types.py + tests + README
```

Lib symbols engineers wrap (verified shipped — `__init__.py` read at dispatch):
- **meta**: `get_meta_adapter`, `FakeMetaAdapter`, `MetaOAuthAdapter`, `MetaCredentialResolver`, `OAuthMetaCredentials`, `MetaGraphError`, value objects (`FacebookPage`/`InstagramAccount`/`FacebookPost`/`InstagramMedia`/`PostInsights`/`MetaConnectionStatus`), `discover_app_permissions`, `resolve_oauth_scopes`.
- **whatsapp**: `get_whatsapp_client`, `WahaClient`, `FakeWahaClient`, `parse_waha_inbound_message`, `build_send_text_body`, `WhatsAppSettings`.
- **google_calendar**: `get_calendar_adapter`, `FakeCalendarAdapter`, `EventInput`, `CreatedEvent`. **google_maps**: `get_routing_adapter`, `Coordinates`, `TravelEstimate`. **youtube**: `make_youtube_client`, `FakeYoutubeClient`, `Channel`/`Video`/`Playlist`. **google_drive**: `make_drive_downloader`, `make_drive_reader`, `parse_drive_url`, `compute_content_stats`.
- **vista**: `VistaClient`, `FakeVistaClient`, `make_vista_client`, error hierarchy (already wired).

Canonical shape reference (every engineer reads first): `mcp/vista/server.py`, `mcp/vista/tools/__init__.py`, `mcp/vista/tools/imoveis.py`, `mcp/vista/settings.py`.

---

## 6. Implementation phases / waves

Wave N+1 dispatches only after every Wave N chunk **FF-merges** (not just engineer-reports). Engineers stage + return notes; architect reviews diff, commits, FF-merges.

### Wave 1 — Shared connector-kit + vista refactor (the proof) ✅ (913bcf1, 2026-05-17)
*1 engineer (KIT). Established the canonical shape + satisfied the recurrence rule before N=3.*
- [x] Extract `mcp/_kit/` from `mcp/vista` generic parts (bootstrap, settings base, registry, typed-error)
- [x] Refactor `mcp/vista` onto `_kit` — vista-private calibration stays vista-side
- [x] `mcp/vista/tests/` 12→12 + new `mcp/_kit/tests/` 13 green (unchanged vista behavior = oracle)
- [x] findings.md transcribed (KIT S1/L1/K1/I1)

### Wave 1b — Consume-side KB docs (OVERDUE absorption-#1 debt; parallel to Wave 2; KB-only, no `_kit` dep) ⏳
*1 engineer (DOCS-CONSUME). Independent of all `mcp/` work — describes product→lib wiring, already stable. User-flagged as owed at absorption time.*
- [ ] `KB § INTEGRATIONS/{meta,whatsapp,google}.md` **Part A** — consume recipe (import → factory → credential-resolver injection → router mount via named seams), per-vendor lib symbols verified from `__init__.py`
- [ ] INDEX.md + `KB § INTEGRATIONS` map + CLAUDE.md Situation→read pointer + memory entries + MEMORY.md index (three-way sync)
- [ ] File follow-up `gmail-seed-lift` project (out-of-scope destination)

### Wave 2 — `mcp/meta` ∥ `mcp/google` (gate satisfied: integration branch `mcp-connector-expansion` @ 913bcf1) ⏳
*2 engineers (META, GOOG) dispatched in ONE turn — independent vendors, file-disjoint (`mcp/meta` vs `mcp/google`), both `git merge mcp-connector-expansion` first to obtain `mcp/_kit`.*
- [ ] **META**: `mcp/meta` on `_kit` — facebook/instagram (read-only) + whatsapp (send confirm-gated + inbound) + diagnostics; deferred-config; tests + README
- [ ] **GOOG**: `mcp/google` on `_kit` — calendar/maps/youtube/drive; deferred-config; tests + README
- [ ] *(architect, inline post-Wave-2 merge)* Collapse vista's N=5 inline `_typed_error` → `from _kit.errors import typed_error` (W1-KIT-K1; validates shared home against meta+google as consumers #2/#3; zero behavior change)

### Methodology rule surfaced 2026-05-17 (user-flagged — codify so it cannot recur)

> **RULE (spec for the Wave 3 codification below — durable home is KB+CLAUDE.md+memory, NOT this file):**
> **An absorption is not complete until its consume-side KB integration docs ship — in the SAME project that lifts the code.** When externally-developed code is absorbed into the seed library (`noctusai_lib.integrations.*` / `domain.*`), code-lifted-but-undocumented is **silent debt**: products cannot discover or consume the seam, and the next agent re-derives or re-forks it. The consume-side `KB § INTEGRATIONS/<x>.md` (what-ships · consume recipe via named seams · auth modes · gaps) is a **required absorption deliverable**, not a follow-up. This is the *documentation sibling* of the established absorption insight "*an absorption is a methodology-epoch merge — reconcile the derived surfaces*" (mcp introspection tests, compliance baseline, dep pins were that lesson's surfaces; **consume-docs is the same shape for the docs surface**). Evidence: `social-wiring-absorption` lifted meta/whatsapp/google connectors into the seed lib but shipped zero `KB § INTEGRATIONS` consume docs — surfaced only when the user asked "shouldn't products consume the func?" weeks later.

### Wave 3 — Docs + three-way sync + registration recommendation + methodology codification 
*1 engineer (DOCS) after Wave 2 FF. KB-first.*
- [ ] `KB § INTEGRATIONS/{meta,google,whatsapp}.md` + INDEX.md + `KB § INTEGRATIONS` map
- [ ] CLAUDE.md routing pointers + memory entries + MEMORY.md index (three-way sync)
- [ ] `.mcp.json` registration *recommendation* documented (NOT auto-applied — §7 Q1)
- [ ] File follow-up `gmail-seed-lift` project (out-of-scope destination) — *(may be done early by DOCS-CONSUME; Wave 3 verifies)*
- [ ] **Codify 3 methodology rules (three-way sync; KB-first → CLAUDE.md pointer → memory + MEMORY.md), executed on the reconciled corrected base (post-merge — avoids clobbering DOCS-CONSUME's staged CLAUDE.md/memory + the parallel agent's committed edits):**
  - **(R1) Absorption ships consume-docs.** Explicit gate in `KB § GUIDES/absorb-seed-workspace.md` (10-gate procedure) + `KB § PATTERNS/project-execution.md` cross-ref + CLAUDE.md §1 pointer + memory `feedback_absorption_ships_consume_docs`. Spec'd in the rule block above this Wave.
  - **(R2) verify-the-seed-ships-it-at-dispatch-time binds to the engineers' FORK BASE, not the architect's working tree.** *Spec:* before dispatching any brief that wraps/consumes a seed symbol, the architect runs `git ls-tree origin/main -- <path>` (the base Agent worktree isolation forks from) — NOT `ls` in the working tree. Unmerged feature-branch lifts are invisible to engineers. **Amend** existing memory `feedback_verify_seed_ships_it_at_dispatch_time` + its KB/CLAUDE.md surface + add the base-check line to `.claude/agents/engineer-default.md` worktree-base preamble (highest-leverage surface — every dispatch reads it). Evidence: W2-BASE-E1 (findings).
  - **(R3) Agent worktrees ship no `.venv`.** *Spec:* engineer briefs touching pytest MUST state the interpreter (`/opt/homebrew/bin/python3.11`) + `pip install 'mcp>=1.0'` fallback. Codify into `.claude/agents/engineer-default.md` (verification section) so every future engineer inherits it by construction, not by per-brief rediscovery. Evidence: W1-KIT-I1.
  - **(R4) Phased-push policy for large commit backlogs (user-directed 2026-05-17, frustration-flagged "bumped into it more times than I can count").** *Problem:* long-lived feature branches accumulate huge unmerged-to-`main` backlogs (`feat/social-wiring-absorption` = 50+ commits / ≥11 closed projects unmerged); engineers' Agent-worktrees fork stale `origin/main` → recurring base-mismatch (W2-BASE-E1, the entire Wave-2 re-dispatch cost). *Policy:* (a) feature-branch work merges/pushes to `main` in **phased increments at project/wave-close boundaries** — never one massive N-projects push; (b) a push happens **only when 100% sure** = full verification green for that increment (touched-product builds + pytest + `verify-kb-sync` + the increment's own success criteria); (c) backlog is **bounded** — accumulating ≥1 *closed* project unmerged is the signal to phase-push, not "later"; (d) **merge-debt monitor** (custodial sibling of disk-usage-monitor / `mole` / `hound`): a script emitting `origin/main`-behind-by N-commits / M-closed-projects + a `next_action`, wired as a **pre-dispatch gate** (architect won't dispatch into a tree whose fork-base is N closed-projects stale without a conscious decision) + a **project-close gate**. *Doc home:* `KB § PATTERNS/branching-and-merging.md` (merging methodology — the phased-push section) + `KB § PATTERNS/project-execution.md` §2.10 (project-close push gate amendment) + CLAUDE.md §1 pointer + memory `feedback_phased_push_policy` + MEMORY.md. *Implement:* `scripts/merge-debt-monitor.sh` (bash 3.x-compatible per the mole lesson) + pre-dispatch/close wiring. **Phased-push protocol (human-gated, user-directed 2026-05-18 — "present me the push and i give it a go or not. Doc this"):** the architect FF-pushes `main` to verified checkpoints **one increment at a time**; for EACH increment the architect **PRESENTS** {exact `git push` command + the commit range/content + verification evidence (FF-safety ancestor check ∧ `verify-kb-sync` ∧ closed/archived-project provenance ∧ seed-lib collect-clean)} and the **USER gives explicit go/no-go**; the user never executes git themselves; the architect executes the push only on an explicit "go" for that specific increment. **A direct-to-`main` push without a presented+approved per-increment gate is forbidden** (harness-classifier-enforced ∧ policy — general delegation ≠ per-push authorization; confirmed when a single 59-commit FF was correctly blocked 2026-05-18). **This is the structural fix for the root cause that has cost this project two full re-dispatch waves.**
  - **(R5) A follow-up project filed for work already inside the active project's explicit scope is a deferral slip, not a triage outcome.** *Spec:* the recurrence/triage register (formalize/refactor/accept) + "file a follow-up project" is for **newly-discovered cross-cutting** work — NOT for de-scoping the active brief. Filing in-scope work as a parked stub is a scope-shrink dressed as triage = silent-error shape one level up (the deliverable becomes a stub instead of shipped work). Test: *"was this in the user's original explicit ask / the project's stated scope?"* → if yes, resolve in-project, never file. Evidence: `gmail-seed-lift` filed 2026-05-17 for Gmail though "google = …+gmail+…" was the original ask; user flagged it; resolved + stub removed. Doc home: `KB § PATTERNS/project-execution.md` (triage section) + CLAUDE.md §1 (sharpens the recurrence/triage rule) + memory `feedback_defer_is_not_resolve`. Sibling of R1 (absorption-ships-consume-docs) — both are "completeness ≠ deferral."
  - **Dependency/sequencing:** all five touch CLAUDE.md / KB / memory / engineer-default.md — surfaces DOCS-CONSUME staged and the parallel agent committed on feat. Execute AFTER Wave 1b + Wave 2 re-dispatches FF-merge, reconciling against the then-current files (no stale-base codification). R4's monitor script is net-new (no collision) — may land earlier as its own micro-wave.

### Wave 4 — Project close
- [ ] Full verify: `cd mcp/<each> && pytest`; `python mcp/noctusai/cli.py --verify-kb-sync`
- [ ] Architect commits + pushes; archive via `noctus.dev.archive`

---

## 7. Open questions

1. **Live `.mcp.json` registration** — needs answer before Wave 3 close / decided by **user**. *Recommendation:* keep meta/google/vista **opt-in** — built, tested, documented with exact run command; user adds to `.mcp.json` when they want the assistant tool-belt active in-session (respects the noctusai+supabase keep-list; auto-registering 3 servers inflates every session's context + tool surface). Vista's never-registered state confirms "built ≠ wired" is the existing norm.
2. **WhatsApp send confirm-then-execute** — Wave 2 / architect-decided. *Recommendation:* `meta.whatsapp.send_text` is a real outbound side-effect; gate it behind an explicit `confirm=true` arg + structured audit log (mirrors `KB § PATTERNS/llm-bot-security.md` confirm-then-execute). Read/inbound tools unguarded.
3. **`google` server split** — Wave 2 / discover during build. *Recommendation:* one engineer GOOG owns all 4 google services; only split calendar+maps / youtube+drive into two engineers if the brief exceeds ~600 LoC (split-over-combine, §18).

---

## 8. Dependencies & blockers

- **Wave 2 ⊥ Wave 1** — meta/google compose `mcp/_kit`; cannot dispatch until Wave 1 FF-merges to the orchestration branch.
- **Gmail** — `google.gmail.*` blocked on a non-existent lib package; explicitly out-of-scope v1 with `gmail-seed-lift` destination (not a blocker for this project's scope).
- **Parallel-agent staged work** — ~50 files + `SESSION-NOTES…2026-05-17.md` staged on `feat/social-wiring-absorption`. NOT this project's to commit (commit-only-own-work); engineer worktrees fork from `main` so unaffected. Surfaced to user; their/operator's decision.

---

## 9. Success criteria

- `mcp/_kit` exists; `mcp/vista` composes it with **zero behavior change** (vista tests green).
- `mcp/meta` + `mcp/google` boot deferred-config, expose convention-named tools wrapping lib Real adapters, tests green mirroring vista.
- KB integration docs for meta/google/whatsapp exist; three-way sync (KB↔CLAUDE.md↔memory) verified by `--verify-kb-sync`.
- An LLM given the registered servers can: list/read IG+FB, send a WhatsApp message (confirm-gated), create a calendar event, read a Drive file, list Vista properties — end-to-end against Fakes in tests.
- Out-of-scope items each have a filed destination (no silent gaps).

---

## 10. How to use this plan

- Architect-owned dashboard; live-tick `- [ ]`→`- [x]`; flip wave icon only when all sub-tasks ticked.
- Wave-gated: Wave N+1 after Wave N FF-merge.
- Engineers stage + return notes; architect reviews diff, commits per wave, pushes at project close.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-17 | Initial project drafted after user interrogation (per-vendor grouping; all connectors simplest→complex; full-speed dispatch). Grounded in tree: lib integrations `__init__` surfaces read, `mcp/vista` canonical shape read, `.mcp.json` registration state verified. Wave 1 dispatched. | Claude Opus 4.7 (architect) |
| 2026-05-17 | Wave 1 ✅ FF (913bcf1) on integration branch `mcp-connector-expansion` (off origin/main 92b35d1; disjoint from parallel-agent staged set). User raised consume-side docs as overdue absorption-#1 debt → split into Wave 1b, pulled parallel-forward. Wave 2 (META∥GOOG) + Wave 1b (DOCS-CONSUME) dispatched. | Claude Opus 4.7 (architect) |
| 2026-05-18 | GOOG-2 ✅ (0d63d39 — 12 tools all real, YT-upload+Drive-reader wired, stale-finder fixed). User "implement all / defer≠resolve": gmail+meta-write+.mcp.json moved out-of-scope→in-scope. Parallel batch dispatched: GMAIL-LIB, META-WRITE-LIB, KIT-SEEDPIN (N=2 seed-pin formalize), SW-RLS (routed fix-on-contact, not deferred). 4 engineers in flight, file-disjoint. | Claude Opus 4.7 (architect) |
| 2026-05-18 | **Phased-push protocol executed end-to-end** (present→user-go→execute per increment): main caught up A(3463c43)→B(7137af0)→C(ef35a62)→D(008c234) via 4 verified FFs. `origin/main`=008c234, backlog 0, monitor OK. **W2-BASE-E1 permanently fixed** — origin/main now ships the connector lib; integration-branch base == origin/main. R4 protocol proven on first real use. | Claude Opus 4.7 (architect) |
| 2026-05-18 | Wave 1b ✅ (8875798 — consume-docs, kb-sync green, gmail-seed-lift filed) + Wave 2 META ✅ (b873ffa — full Graph surface, 25 tests) salvaged onto integration branch. GOOG-2 finishing. Phase A push **presented, awaiting user go** (nothing pushed). 2 harness/env incidents surfaced+recovered by engineers (stale editable-install finder; overlay⊥worktree divergence post-resync) → architect follow-up: generalize test-bootstrap into `_kit` (DRY N=2). | Claude Opus 4.7 (architect) |
| 2026-05-18 | **W2-BASE-E1 corrected.** origin/main is pre-absorption; rebuilt `mcp-connector-expansion` = feat HEAD (008c234, has meta/media lib) + cherry-pick Wave1 `_kit` (b3e0b10) + salvage META-wa (6a0c7b7) + salvage GOOG (306c18d). Re-dispatched META-2/DOCS-2/GOOG-2 on corrected base — zero engineer work lost. R4 phased-push policy spec'd; **MERGEDEBT monitor implemented** (`scripts/merge-debt-monitor.sh` + 10 tests; live = 59 ahead / 1 closed unmerged / WARNING) — staged in primary tree (worktree-isolation deviation, safe). Branch-topology consolidation pending user trunk decision. | Claude Opus 4.7 (architect) |
