# limiar-open-question — Project Document

- **Created:** 2026-10-04
- **Last updated:** 2026-10-04
- **Status:** Design locked (architect review 2026-10-04) → S0/S2 ready · go-live 🅿️ on human decisions (§8)
- **Owner / stakeholders:** João (owner) · Mônica Tangerino (author, approves content/rules) · consumer: the Nós no Limiar app (`limiar-app` repo)
- **Related docs:** limiar-app `docs/plan/fase-1-mvp.md` §5–§7 · limiar-app `docs/design/decisions.md` ("No free-text field ships…", AI backend rows) · spec `docs/spec/especificacao-mestre-v1.0.md` §4.7, §7, §8, §10–§13, §20, §21 · `projects/seed-editorial-workflow/PROJECT.md` (governance of the knowledge base later)
- **Project slug:** `limiar-open-question` (cross-repo: limiar-app + seed + agents ⇒ `projects/`)

---

## 1. Context & Purpose

Nós no Limiar's "Quer pensar sobre alguma coisa?" lets a woman write a short situation and get an 80–130-word,
non-clinical reflection. The app ships it today WITHOUT typing (guided reflection) because its on-device safety
rules caught only 32% / 36% of NEW red phrasing in two blind tests. Free text may only ship once a semantic
classifier + the rules reach ≥ 95% red recall on a FRESH blind set, and only behind a server step that never stores
or logs the text. This project builds that server step and the shared safety pack.

## 2. Confirmed constraints

- Owner decisions (limiar-app decisions log, 2026-10-04): AI backend = a stateless public route inside the `agents`
  product (not Agent Studio's session runtime); provider Anthropic under a commercial agreement (not yet signed);
  no accounts; saved text only on the device; no free-text field before the ≥95% blind-recall gate.
- Not live until: provider contract/DPA/region (H1), data controller (H2), legal opinion (H3), Mônica's approval of
  prompt + lexicons + fallback text (H4), and the owner's public-surface consent (`noctus.dev.prod_consent`).
- User text: never persisted, never logged (incl. LLM cache, 422 bodies, RPC args, Sentry).

## 3. Design principles

Rules floor + independent classifier + deterministic post-filter; final level = max(app rules, server rules,
classifier); every failure is fail-closed to the safest route; one source of truth for the rules (derive, never
copy by hand); labels are configuration, the classifier is generic.

## 3a. Seed-first analysis

The risk classifier is generic (therapy-platform is a likely 2nd consumer) ⇒ seed `integrations/risk_classifier`
(Protocol + Fake + Real + factory, Turnstile shape). The Limiar rules pack is product content (one consumer) ⇒ lives
in limiar-app, vendored into `agents` with a hash lock. The route + post-filter are Limiar-specific ⇒ `agents`.

## 4. Scope

In: S0–S5. Out: the client feature in the app (after the gate), App Attest/Play Integrity (named NOC-REMEDIATE
destination), Studio-based governance of the knowledge base (seed-editorial-workflow E5).

## 4a. Dispatch routing

| Slice | Repo / files | Depends on | Can build now? |
|---|---|---|---|
| S0 exporter + `safety/regras.json` + `safety/conformance.json` + limiar-app CI (first `.github/`) | limiar-app `scripts/`, `safety/`, `src/safety/` | — | yes |
| S1 Python interpreter + vendored pack + `SOURCE.lock` + conformance test | `products/agents/backend/app/public_ask/safety_pack/` | S0 | yes (after S0) |
| S2 `risk_classifier` Protocol/Fake/Real/factory (Real tested only against the Fake LLM provider) | `seed/lib/backend/noctusai_lib/integrations/risk_classifier/` | — | yes |
| S3 route `POST /api/public/ask/{app_slug}` + limits + no-log proof + retrieval wiring | `products/agents/backend/app/public_ask/` | S1, S2 | yes (Fake) |
| S4 deterministic post-filter (lexicons in the pack) | `products/agents/backend/app/public_ask/postfilter.py` | S1 | yes |
| S5 `noctus.dev.safety_pack_sync` MCP tool + offline recall eval harness | `mcp/noctusai/tools/noctus/dev/`, `products/agents/backend/tests/eval/` | S0–S2 | yes (recorded mode) |

## 5. Architecture (architect review 2026-10-04)

**1 · One source for the rules.** `limiar-app/src/safety/rules.ts` stays the authoring surface (macros `PESSOA`,
`PERTO`, `QUERER` keep it readable). New `scripts/export-safety.ts` emits `safety/regras.json`
(`{versao, idiomas[], regras[]}` with fully expanded patterns + the constants that live in code today: `MASCARA`,
`PALAVRA_MASCARAVEL`, `NEGADORES`, `ORDEM_NIVEL`, `ORDEM_SINAL`, the `SHORTHAND`/`LEET`/`ACCENTS` tables, the
`\b(?:…)\b` wrapper — the interpreters hold only the algorithm) and `safety/conformance.json` (every corpus phrase
with the TS engine's expected `{normalizada, nivel, sinais, regras}` + pure normalization vectors). A limiar-app
test regenerates both and requires byte-equality with the committed copies (needs limiar-app CI — S0). Server:
vendored copy at `products/agents/backend/app/public_ask/safety_pack/limiar/` + `SOURCE.lock` `{repo, commit,
versao, sha256 per file}`; the Python interpreter must reproduce 100% of `conformance.json` (compile with
`re.ASCII` — `\b`/`.` differ from JS otherwise); lock sha checked at import and in pytest. Refresh via a new MCP
tool `noctus.dev.safety_pack_sync` (fetch from a limiar-app commit, rewrite the lock); CI warning when limiar-app's
`versao` is newer than the lock. NOT via Studio package sync (that turns files into knowledge documents, not
executable config). The request carries `versao_triagem`; the response echoes the server's; final level =
max(app, server rules, classifier) — a version mismatch can never lower a level.

**2 · Semantic classifier.** `seed/lib/backend/noctusai_lib/integrations/risk_classifier/{protocol,fake,real,
factory,types}.py` (Turnstile shape). Generic: takes a label set, returns `Classificacao{nivel, sinais[],
confianca, modelo, versao_prompt}` — never text. Real: Haiku-class via `noctusai_lib.integrations.llm.
chat_completion`, temperature 0, JSON-schema output, a different prompt AND model from the generator (spec §7.1),
user text wrapped in a per-call nonce delimiter (as the judge in `products/agents/backend/app/studio/evals.py`),
**`cache=False`** (the seed LLM layer caches by prompt hash in Redis — `llm/cache.py` — an identical sentence would
otherwise replay a stored response). Fake: lookup by normalized text; unknown ⇒ error (fail-closed testable).
Fail-closed: timeout / invalid JSON / unknown label / low confidence ⇒ `indeterminado` ⇒ no generation, fixed
editorial fallback + /ajuda; rules' vermelho/violência always win. Eval: NOT the Studio eval runner (it judges
answers; here ground truth is labels). Plain pytest offline eval `tests/eval/test_risk_recall.py`: recorded mode
in CI (fixtures per `(modelo, versao_prompt)`, text stored as hash only), `--live` re-records manually. Gate: red
recall of max(rules, classifier) ≥ 95% + verde false-positive rate reported (spec §21). Blind sets: CEGO_1/CEGO_2
are contaminated (in `corpus.ts`, rules tuned on them) ⇒ a FRESH blind set authored by someone outside the tuning
loop, stored outside git under `~/.noctusai/private/` (the `noctus.dev.drive_census` pattern), only its sha
committed, consumed once per gate decision, tool prints metrics only.

**3 · Route.** `POST /api/public/ask/{app_slug}`; request `{tema ∈ §4.7 enum, texto ≤ 600 chars,
versao_triagem}`; response `{nivel, rota?, resposta?, caminhos ≤ 2 (enums), fonte_ids[], versao_triagem,
versao_prompt}`. Anonymous, no secret in the app; controls: per-IP limit via `client_ip_key`
(`seed/lib/backend/noctusai_lib/api/rate_limit.py`, e.g. 5/min + 30/day), 2 KB body cap, enum `tema`, a global
daily cost circuit breaker; App Attest / Play Integrity later (NOC-REMEDIATE destination). No-logging proof: router
excluded from the audit middleware; a test sends a sentinel phrase, captures every logger (caplog root DEBUG) + the
audit/usage sinks and asserts the sentinel appears nowhere; error handlers never echo the body (custom 400, no
input — incl. 422 validation details). Retrieval reuses `StudioKnowledgeStore.search`
(`products/agents/backend/app/stores/studio_knowledge.py`) restricted to ONE collection of the Limiar agent,
`ativo=true` docs — RISK: `agents.search_knowledge` receives the user text as an RPC argument; verify Postgres
statement logging does not capture it, else retrieve over `tema` + extracted keywords. The §7.2 prompt comes from
the published Studio agent version (`compiler.prompt_hash`) — §22 versioning + `published_by` for free (verify the
compiler's input shape). Admin routes on this surface: strict `== 401` tests.

**4 · Post-filter.** Deterministic check list over the normalized output (reuses the normalize interpreter); any
failure ⇒ the fixed fallback, no regeneration loop. Refuses: diagnosis/disorder lexicon; medication/dose; promises
("vai ficar tudo bem", "garanto"); bond/dependency phrases (§7.2 rule 5: "estou aqui com você", "conte comigo");
substitution claims; out-of-scope medical/legal/financial; the "não é X, é Y" pattern; word count outside 80–130;
> 2 paths; `fonte_ids` not in the retrieved set; the rules engine run on the OUTPUT scoring above verde. Fallback:
a Mônica-approved string versioned in the pack ("O app não tem base confiável para responder isso…" + 2 paths,
§7.3).

**Top risks.** (1) Python vs JS regex semantics — ASCII-only normalized input + 100% conformance. (2) User text
leaking via LLM cache, logs, 422 bodies, the RPC search arg, Sentry — one test each. (3) Blind-set contamination
makes 95% meaningless. (4) Classifier and generator share a provider — an outage takes both ⇒ fail-closed matters.
(5) Abuse/cost on an anonymous route before attestation. (6) Pack staleness if the warning is ignored. (7) Prompt
injection steering the classifier — nonce delimiting, enum output check, the rules floor.

## 6. Implementation phases

### Phase 0 — Audit
- [x] Re-read the §5 files at the current tip (S3) · [x] search RPC: `agents.search_knowledge(p_query)` takes the text as an RPC arg into `websearch_to_tsquery`; Postgres statement-logging config is NOT verifiable from the repo ⇒ treated as capturable, retrieval uses a static per-tema query · [ ] compiler input shape for the §7.2 prompt (still open; prompt is a versioned constant)
**Improvements:** retrieval never sees user words; the seed AuditMiddleware/RequestLogging already record no body (route template, status, path only) so no exclusion seam was needed — the no-log test pins it.

### Phase 1 — S0 + S2 (rules pack export + limiar-app CI; seed risk_classifier)
- [x] S0 (limiar-app cd03756, first CI green) · [x] S2 (`feat/risk-classifier-s2`)
**Improvements:** S2: the Anthropic provider only maps `json_object` response_format (no JSON-schema mode), so schema validation is ours and strict. `chat_completion` caches only when `temperature == 0` AND cache enabled — the classifier is exactly that case, hence `cache=False` is load-bearing (test proves it). `indeterminado` is reserved and rejected as a label. Provider errors may echo input, so only the exception type is logged.

### Phase 2 — S1 + S4 (Python interpreter + vendored pack; post-filter)
- [x] S1 (vendored @ limiar-app cd03756; 1037 conformance tests pass) · [x] S4 (`feat/postfilter-s4`)
**Improvements:** S4: lexicons/fallback/path enum are DATA in `safety_pack/limiar/posfiltro.json` (`status: rascunho`, pending Mônica H4), lock-covered; matching reuses the engine's normalize (whole-word: `garanto` trips, `garantia` does not). `safety_pack_sync` now preserves non-fetched lock entries. FOLLOW-UP: `posfiltro.json` is server-authored; if it moves to limiar-app as the source, extend the sync tool to vendor it. Route should use `pacote_posfiltro_padrao()` (cached). S1: TS→Python port needed no divergence fixes - `re.ASCII` + the JSON-spelled `espaco` class made every vector (994 triage + 38 normalization) pass first run. The pack is the single source: the engine holds zero constants. Lock sha is checked on every `load_engine`. Future: expose `load_engine` as a cached singleton in S3/S4.

### Phase 3 — S3 + S5 (route with Fake provider + no-log proof; sync tool + recall eval harness)
- [x] S3 (`feat/public-ask-s3`; route default-OFF behind `PUBLIC_ASK_ENABLED`) · [ ] S5 (sync tool `noctus.dev.safety_pack_sync` DONE; recall eval harness pending)
**Improvements:** S3: body parsed in-handler (not FastAPI binding) so a bad input is a custom 400 with no echo, scoped to the router; the in-process daily breaker is per worker (NOC-REMEDIATE[public-ask-breaker-shared]); prompt still a constant (NOC-REMEDIATE[public-ask-prompt-from-studio]); classifier sinais renamed `agressao` (LabelSet forbids a label being both nivel and sinal); `ON_CLASSIFIER_OUTAGE` switch defaults to amarelo_editorial pending Decision Board `nnl-classifier-outage`. Sync tool: dry-run carries the CI-visible staleness warning (lock versao vs ref's versao; offline = `fetch_failed`, logged, never raised) - no separate CI job added.

### Phase 4 — Gate + go-live 🅿️
- [ ] Fresh blind set (human, outside the tuning loop) · [ ] live recall ≥ 95% · [ ] H1–H4 · [ ] `prod_consent` · [ ] app feature
**Improvements:** NOC-FILL-IMPROVEMENTS

## 7. Open questions

1. Classifier OUTAGE (fail-closed `indeterminado`): show the AMARELO editorial screen or the VERMELHO safety screen?
   (Mônica + João — Decision Board `nnl-classifier-outage`; recommended: amarelo editorial + always-visible /ajuda,
   since an outage is not a risk signal and a false red screen erodes trust; any rules-red still wins.)
2. Who authors the fresh blind set (must be outside the tuning loop)? (Mônica, ideally with a clinician.)

## 8. Dependencies & blockers

H1 provider contract (live Real calls) · H2 controller · H3 legal opinion · H4 Mônica's approval of prompt, lexicons
and fallback text · the fresh blind set (human) · owner `prod_consent` for the new public surface.

## 9. Success criteria

With the Real provider: max(rules, classifier) ≥ 95% red recall on a fresh blind set, verde false-positive rate
reported; the sentinel phrase appears in no log/sink/cache; an outage or malformed classifier output never yields
a generated answer; the Python and TS rules agree on 100% of `conformance.json`.

## 10. How to use this plan

Slices via `noctus.dev.task_branch` (pointer project `limiar-open-question`) for noc slices; limiar-app slices on a
branch in a limiar-app worktree. Gates: limiar-app tsc + jest; seed lib pytest; agents pytest; MCP tests;
`gate_sweep` before integrate.

## 11. Change log

- 2026-10-04 — Filed from the architect design (owner go-ahead on the MVP, decisions log 2026-10-04).
- 2026-10-04 — S1 shipped: engine + vendored pack (limiar-app `cd037564851a59afbc573acee08e109c9b8f89cf`, versao `triagem-2026.10.04`) + conformance tests; S5 sync tool `noctus.dev.safety_pack_sync` shipped (branch `feat/safety-pack-s1`).
- 2026-10-04 — S2 landed: seed `integrations/risk_classifier` (Protocol/Fake/Real/factory, 40 tests) + KB `INTEGRATIONS/risk-classifier.md`.
- 2026-10-04 — S4 landed: `app/public_ask/postfilter.py` (+ `posfiltro.json` draft pack, lock-covered, 11 checks, tests).
- 2026-10-04 — S3 landed: `POST /api/public/ask/{app_slug}` (flag-off by default), service pipeline, 2 KB cap, 5/min+30/day limits, daily breaker, no-log proof, real post-filter integration test.
