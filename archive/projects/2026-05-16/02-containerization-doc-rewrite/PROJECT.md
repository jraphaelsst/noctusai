# Containerization KB doc rewrite — Project Document

> Living document. Named follow-up referenced by `KB § PATTERNS/containerization.md` top banner.

- **Created:** 2026-05-16
- **Last updated:** 2026-05-16
- **Status:** Filed (not started) — unblocks after `containerization-single-container` closes
- **Owner / stakeholders:** joaoraphaelsst
- **Related docs:** `KB § PATTERNS/containerization.md` · `projects/containerization-single-container/PROJECT.md`
- **Project slug:** `containerization-doc-rewrite` (`projects/`; intent: `refactor` — documentation)

---

## 1. Context & Purpose

`containerization-single-container` migrated the platform to one container per product (shared seed base images + thin per-product Dockerfiles, two compose projects, external `noctus-net`, single-port API+SPA). The **rule-bearing** sections of `KB § PATTERNS/containerization.md` (§1 mental model, §2 file layout, §4 networks, §5 ops, §11a) + a prominent top banner were corrected in that project's Phase 6 (doc-code coherence — rules must not lie).

The **didactic walkthrough** sections (~§3 Dockerfile walkthrough, §6 build process, §7 image footprint, §8 adding a product, §9 troubleshooting, §10 native-vs-docker, §11 backlog) are ~40k tokens of legacy 2-container prose: stale but **not rule-lying** (the banner explicitly supersedes them). This project rewrites them to the single-container architecture so the whole doc is internally consistent.

---

## 2. Confirmed constraints

- **Banner is authoritative until this lands** — the top-of-doc banner in `containerization.md` already states the current architecture + the §4 `external:true` inversion; readers are not misled on *rules*. *(Rules out urgency; this is consistency/quality debt, not a correctness lie.)*
- **Source of truth = `containerization-single-container` PROJECT.md + findings.md** — the migration's decisions/rationale are recorded there; this project transcribes them into didactic KB prose.

---

## 3. Design principles

1. Rewrite section-by-section against the *actual* shipped artifacts (`products/seed/`, `seed/docker/`, `scripts/propagate-*.sh`, `start.sh`), not from memory.
2. Symbol-first authoring (dense KB doc — `KB § PATTERNS/doc-symbology.md`).
3. Delete legacy 2-container prose rather than annotate it (the banner already bridges; in-body relics confuse).

---

## 3a. Seed-first analysis

Pure documentation; no code/seed surface. §3a confirmed N/A — correctly doc-bounded.

---

## 4. Scope

**In scope:** rewrite the didactic sections of `KB § PATTERNS/containerization.md` to single-container; remove the superseding banner once the body is consistent; refresh ASCII diagrams; update `KB § INDEX.md` scope line if the title/desc changed.

**Also in scope (added 2026-05-16):** the legacy body still references `docker-compose.override.yml` / `./start.sh dev <slug>` / Vite-HMR sidecar — all **removed** by the follow-on `containerization-single-env` change (ONE container, ONE shape: Dockerfile `runtime-watch` target = `vite build --watch` + `uvicorn --reload`, no override, no `dev` command). The rewrite must reflect single-env, not the interim dev-sidecar design.

**Out of scope:** any code change (both migrations are done); `docker-compose.prod.yml` strategy (separate `containerization-prod-deploy` candidate).

---

## 6. Implementation phases

### Phase 1 — Rewrite §1–§5 body + diagrams
- [ ] §1 mental model, §2 file layout, §3 Dockerfile (base+thin), §4 networks (external), §5 ops (two projects + new start.sh modes), diagrams.

### Phase 2 — Rewrite §6–§11 + retire banner
- [ ] §6 build, §7 footprint, §8 add-a-product, §9 troubleshooting, §10 native-vs-docker, §11 backlog/anti-patterns; remove the top banner once body is consistent; `verify-kb-sync.sh` green.

---

## 9. Success criteria

- No legacy "2-container / backend+frontend pair / `<slug>-net` / `NOT external:true`" prose remains except as explicitly-marked history.
- Banner removed; whole doc internally consistent with the shipped artifacts.
- `bash scripts/verify-kb-sync.sh` + `python scripts/update-kb-counts.py --check` green.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-16 | Filed as the named follow-up from `containerization-single-container` Phase 6 (rule-bearing sections + banner fixed there; didactic-prose rewrite deferred here) | Claude Opus 4.7 |
