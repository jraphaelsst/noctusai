# LLM Provider Selection — the fleet-wide vendor map, the manual switch, and the blast radius

**What it is.** The complete map of every chat / vision / embedding / audio
call site's LLM vendor dependency across products, seed lib, and the MCP dev
toolkit; the lightweight `resolve_llm_provider` manual switch that moves a
call site off OpenAI without a new UI or credential store; and the classified
list of what is genuinely **stuck on OpenAI** (a capability gap) versus what
is merely **unwired** (the mechanism exists, nobody flipped it).

**Status**: born 2026-09-18, from the `llm-provider-dependency-sweep` slice.

## 2026-09-22 — DOCUMENT reads default to Claude (seed canonical)

Owner directive: "OpenAI has no credit — swap the mechanism fully to Claude,
the cheapest one that does the job." Every DOCUMENT read now defaults to
Anthropic at the seed level, not by per-org rows:

- **One place per rung** — `noctusai_lib.integrations.documents.providers`:
  `DEFAULT_DOCUMENT_PROVIDER = "anthropic"`, `OCR_MODELS` (vision
  transcription) and `DOCUMENT_ANALYSIS_MODELS` (chat over a document's text).
  Both Anthropic pins = `claude-haiku-4-5`, chosen by measurement (synthetic
  scans: Haiku 42/42 + 10/10 fields vs Opus 5 42/42 + 10/10, ~1/11th the OCR
  cost; table in that module's docstring). Real-document re-measurement is
  still owed.
- **Consumers**: `LadderDocumentTranscriber` (`DEFAULT_VISION_PROVIDER` aliases
  it), `RealMediaResolver` (`provider=None` → the document default, image +
  PDF paths), social-wiring's `llm_vision_provider` / `llm_chat_provider` spec
  defaults and `certidoes.service.ANALYSIS_MODELS` (now the seed object).
- **Not a fallback**: an org that saved "openai"/"gemini" keeps it; a missing
  or blank key for the selected vendor is `missing_credentials` (the
  transcriber pre-check, `LLMNotConfigured` from the call, and the media
  resolver all name it) — never a silent swap.
- **Unchanged**: the process-wide `LLMConfig.default_provider` ("openai") for
  non-document chat, embeddings (Anthropic has none), audio (Whisper), and
  erp-imobiliario (inativo) — whose `resolve_llm_provider(..., default="openai")`
  and own `ANALYSIS_MODELS` copy still read openai.

## Why

On 2026-09-17 the platform OpenAI key hit `insufficient_quota` (429). A large
slice of the platform stopped working, and a slice of THAT stopped working
**silently** — `noctus.dev.kb_search` / `code_search` returned empty results
that read as "no matches" rather than "the provider is dead." Nobody had a
map of what depends on OpenAI, so nobody could tell which failures were the
provider dying and which were genuinely "no results."

The org-level fix already applied — `social-wiring`'s `llm_vision_provider` +
`llm_chat_provider` flipped to `anthropic` in `public.org_settings` for org
`6dd73140-74a4-41c6-aeff-bc94b5312b53`, verified working (a matrícula
transcribed through Anthropic vision) — is the proof this lever works. It
also revealed the actual mechanism: `resolve_credential(key, org_id)` reads a
**generic** `(org_id, key)` row from `public.org_settings` — it is not
`social-wiring`-specific plumbing, it is the platform's 3-tier credential
chain every product already inherits. `social-wiring`'s own
`app/services/api_keys_store.py` wraps that same chain with a per-product
UI, an encrypted local key store, and three named switches
(`llm_vision_provider` / `llm_chat_provider` / `llm_embedding_provider`) —
proving the *shape* a manual, non-failover, per-capability switch needs. This
doc generalises that shape to every OTHER product's bare `chat_completion()`
/ `analyze_image()` calls, which had no lever at all.

## Established facts (do not re-litigate)

- `AnthropicProvider.generate_embedding` raises `ProviderNotImplemented` —
  embeddings genuinely do not exist on that API
  (`seed/lib/backend/noctusai_lib/integrations/llm/providers/anthropic_provider.py:147-159`).
- `AnthropicProvider.transcribe_audio` raises `ProviderNotImplemented` —
  transcription genuinely does not exist on that API (same file, 161-173).
- `GeminiProvider` DOES implement all four capabilities
  (`gemini_provider.py`) — chat, vision, embeddings (with
  `output_dimensionality` truncation to match a 1536-wide pgvector column),
  and best-effort audio transcription via multimodal `generate_content`.
- `GEMINI_API_KEY` is absent from `.env`; `ANTHROPIC_API_KEY` and
  `OPENAI_API_KEY` are both present.
- The 8 keeper-mirror caches split into structural (no provider:
  keeper-patterns, agent-context) and embedding-dependent (kb / code /
  memory / corpus-embeddings, plus `auto-improvement` clustering and
  `noc-graph`'s `SEMANTIC_NEIGHBOR` edges).

## Deliverable A — the fleet-wide dependency map

Every call site below resolves its vendor from
`noctusai_lib.integrations.llm.client.get_llm_config().default_provider`
unless a `provider=` kwarg is shown. That default is **"openai"** everywhere
in the fleet — set once, process-wide, in
`seed/framework/backend/noctusai_seed/llm_defaults.py::default_llm_config()`
(`"default_provider": "openai"`), which every product inherits via
`create_product_app()` unless it passes its own `llm_config=` (none do — see
"How the default propagates" below). **There is no direct `from openai
import` anywhere in product/seed/mcp code** — the §1 rule holds; every call
goes through the seed's provider registry.

### How the default propagates (verified, not assumed)

`create_product_app(..., llm_config: Optional[LLMConfig] = None)` — when
`llm_config` is omitted, `noctusai_seed/app.py:252` does
`effective_llm_config = llm_config or default_llm_config(...)`. Every
product's `main.py` was checked; **none pass `llm_config=`** except
`seed` / `igig` / `orbity` / `community`, which pass
`default_llm_config(default_chat_model="gpt-4o")` — overriding the MODEL,
not the PROVIDER. `social-wiring` also does not pass `llm_config=` (its
`main.py` explains why: doing so would discard the Redis cache / usage-sink
wiring `create_product_app` derives from `settings`) and instead layers
per-call `provider=` overrides on top of the unchanged "openai" default.

### Chat (`chat_completion(...)`)

| Product | File | Provider switch? |
|---|---|---|
| erp-imobiliario | `services/certidoes_service.py::_analyze_with_ai` | **Switched this slice** — `resolve_llm_provider("chat", ...)`, `ANALYSIS_MODELS` map |
| erp-imobiliario | `services/ai_service.py::_dispatch_chat` (9 features: descriptions, lead scoring, pricing, WhatsApp intent, certidões score, metas coach tip, photo compliance, search relevance, follow-up draft) | Not switched — needs a per-provider model map across 9 call sites first (see "Proposed, not done") |
| knowledge-extractor | `services/summary_service.py::summarize_transcript` | Not switched |
| therapy-platform | `services/summary_service.py`, `services/longitudinal_service.py` (LGPD `cache=False`, clinical text) | Not switched |
| daily-life | `services/daily_brief_service.py`, `services/ai_service.py` | Not switched |
| community | `services/moderacao_ai_service.py::avaliar_mensagem` | Not switched — **see the silent-failure flag below** |
| personal-finance | `services/ai_service.py` (2 call sites) | Not switched |
| social-wiring | `modules/certidoes/service.py` (×2), `modules/imovel_hub/documentos_service.py:512` | **Already switched** (pre-existing) via `resolve_chat_provider` / inline `provider` param + `ANALYSIS_MODELS` |
| social-wiring | `modules/media_creation/services/generation_service.py::_call_llm`, `modules/email_marketing/services/ai_service.py` (×5: subject lines, template draft, re-engagement, deliverability review, translation), `modules/email_marketing/services/segmentation_service.py` (chat call) | **Gap in an already-switch-capable product** — `resolve_chat_provider` exists in this same product's `api_keys_store.py` and is simply not wired to these 8 call sites |
| seed lib (shared) | `noctusai_lib/domain/digest/narrative.py::narrative()` — consumed by **core** (`audit_digest_service`), **social-wiring** (`campaign_debrief_service`), **daily-life** (`weekly_review_service`), **personal-finance** (`monthly_narrative_service`) | Not switched — **highest-leverage single fix**: one seed function, 4 products, but `model` is a required per-caller param so needs the same per-provider model-map treatment |
| seed / igig / orbity | `app/main.py` module docstring | Doc example only, not live code — excluded from counts |

### Vision (`analyze_image(...)` / `make_document_transcriber(...)`)

| Product | File | Provider switch? |
|---|---|---|
| erp-imobiliario | `services/matricula_service.py::processar_extracao` | **Switched this slice** — `resolve_llm_provider("vision", ..., allowed=tuple(OCR_MODELS))` |
| erp-imobiliario | `services/certidoes_service.py::_extract_pdf_text` | Inert today — called with `max_vision_pages=0` (vision rung never fires; the free text-layer rung is all this path uses), so a provider switch here is a no-op. Left unwired deliberately; flagged so it is not mistaken for an oversight. |
| therapy-platform | `services/attachment_service.py` (image branch, `model="gpt-4o"` hardcoded) | Not switched — needs a vision-model map first (a bare provider swap with `model="gpt-4o"` sent to Anthropic 404s) |
| social-wiring | `modules/certidoes/service.py`, `modules/matriculas/deps.py`, `modules/imovel_hub/documentos_service.py` | **Already switched** (pre-existing) via `resolve_vision_provider` + seed `OCR_MODELS` |
| MCP dev toolkit | `noctus.dev.llm_vision_analyze` (`mcp/noctusai/tools/llm/vision/analyze.py`) | **Already has an operator `provider` param, unused today.** `analyze(payload)` forwards `payload.provider` straight to `analyze_image(...)`; `ANTHROPIC_API_KEY` is present, so `provider="anthropic"` **works right now** with zero code change — an agent hitting a dead OpenAI key on a vision call just needs to pass it. |

### Embeddings (`generate_embedding(...)` / `generate_embeddings_batch(...)`)

**Anthropic is never offered for this capability anywhere — correctly.**

| Surface | File | Provider switch? |
|---|---|---|
| erp-imobiliario | `services/embedding_service.py` | Not switched — even if wired, blocked on `GEMINI_API_KEY` (credential gap, not capability) |
| therapy-platform | `services/therapy_embedding_service.py` | Not switched — same credential gap |
| social-wiring | `modules/permutas/embeddings.py` | **Already switched** (pre-existing) via `resolve_embedding_provider`, `allowed=("openai","gemini")` |
| social-wiring | `modules/email_marketing/services/segmentation_service.py` (contact-segmentation embedding loop, line ~284) | **Gap in an already-switch-capable product** — `resolve_embedding_provider` exists two files over and is not wired here |
| MCP dev toolkit | `_embedding_corpus.py::embed_sync` (backs kb / memory / corpus-embeddings), `code_embeddings.py::search`/refresh, `vectorize.py`, `noctus.dev.vector_embed` | **No switch mechanism exists at all** — see "The MCP toolkit is a harder case" below. This is the single most severe SPOF in the fleet. |

### Audio (`transcribe_audio(...)`) — never movable to Anthropic

| Surface | File | Notes |
|---|---|---|
| therapy-platform | `services/attachment_service.py` (audio branch), `services/transcription_service.py` | `model="whisper-1"` hardcoded |
| knowledge-extractor | `services/transcription_service.py::transcribe_file` | bare call |
| social-wiring | `services/media_service.py` (×2), `routers/chat_router.py` | WhatsApp inbound voice notes |
| seed lib (shared) | `noctusai_lib/integrations/media/real_adapter.py` (×2) — the WhatsApp `ResolvedMedia` pipeline every chatbot-enabled product consumes | Widest blast radius of any audio site — one seed adapter, many products |
| MCP dev toolkit | `noctus.dev.llm_audio_transcribe` | Has a `provider` param, but `provider="anthropic"` raises `ProviderNotImplemented`; `provider="gemini"` would work in principle but `GEMINI_API_KEY` is absent |

## The MCP toolkit is a harder case than any product

The dev-toolkit's own LLM bootstrap
(`mcp/noctusai/tools/noctus/dev/_llm_bootstrap.py::ensure_llm_configured`)
builds its `LLMConfig` with **no `default_provider=` override** — so it
inherits the dataclass default `"openai"` (`llm/config.py:40`) — and its
`key_provider` reads **only `os.environ[f"{provider.upper()}_API_KEY"]`**,
never the `org_settings` / `platform_settings` chain products use. This is
NOT the same gap as a product's unwired switch: **the mechanism itself does
not exist here.** There is no `provider=` parameter anywhere in
`_embedding_corpus.py` / `code_embeddings.py` / `vectorize.py` for an agent
or operator to set, and even if there were, embeddings cannot route to
Anthropic and `GEMINI_API_KEY` is unset — so today, an OpenAI outage takes
every embedding-backed MCP tool down with **zero available lever**, not even
a manual one. `noctus.dev.llm_vision_analyze` / `llm_audio_transcribe` are
the exception: their `provider` param already exists (documented in the
vision table above) because those tools pass it straight through to
`analyze_image` / `transcribe_audio`, whose signatures already carry it.

## Deliverable B — what moved, what didn't, and why

### Moved this slice

1. **New seed helper**: `noctusai_lib.integrations.llm.provider_choice.resolve_llm_provider(capability, org_id, *, allowed, default="openai", resolver=resolve_credential)`
   — the lightweight manual switch. Reads `llm_<capability>_provider` through
   the SAME `org_settings → platform_settings → env` chain `resolve_credential`
   already implements, under the SAME setting names `social-wiring`'s spec
   already established (`llm_chat_provider` / `llm_vision_provider` /
   `llm_embedding_provider`), so a value an operator sets for one product is
   discoverable under the same name for another. Exported from
   `noctusai_lib.integrations.llm` (`from noctusai_lib.integrations.llm import
   resolve_llm_provider`). 🔴 Manual, not a fallback — identical posture to
   `social-wiring`'s three switches: nothing here retries on a different
   vendor; the operator picks, the pick is a single `org_settings` row.
   Tested in `seed/lib/backend/tests/integrations/llm/test_provider_choice.py`
   (10 cases: unset→default, saved choice honoured, whitespace-tolerant,
   org-less call, unknown value degrades loudly with the capability + key
   named in the log, embeddings never resolve to `"anthropic"`, a
   `default` outside `allowed` is asserted as a call-site bug).

2. **erp-imobiliario vision**: `services/matricula_service.py::processar_extracao`
   now resolves `provider = provider_resolver("vision", org_id,
   allowed=tuple(OCR_MODELS))` before building the real transcriber, and
   passes it to `make_document_transcriber(provider=...)` (a parameter the
   seed factory already accepted — this call was the last one in the fleet
   still leaving it at `None`). `provider_resolver` and a new
   `transcriber_factory` parameter are DI seams (bound defaults, never
   patched — `KB § PATTERNS/backend/di-test-seam.md`). **Behaviour-preserving**:
   no org has an `llm_vision_provider` row today, so every extraction still
   resolves to `"openai"`, byte-identical to before.

3. **erp-imobiliario chat/analysis**: `services/certidoes_service.py::_analyze_with_ai`
   now resolves a provider the same way, added its own `ANALYSIS_MODELS`
   map (identical values to `social-wiring`'s already-production-proven
   map: `openai→gpt-4.1-mini`, `anthropic→claude-opus-5`,
   `gemini→gemini-2.0-flash`), and its missing-credential message now names
   the SELECTED vendor instead of a hardcoded "OpenAI" (the pre-existing
   message would have told an operator who switched to Anthropic that
   "OpenAI API Key não configurada" — false, and pointing at the wrong
   settings field).

Both changes give erp-imobiliario's document-transcription and
certidão-analysis surfaces — the exact domain `social-wiring` had already
proven the fix for — the same operator lever: **one `org_settings` row**
(`llm_vision_provider` / `llm_chat_provider` = `"anthropic"`) moves this
product's second-largest OpenAI dependency off a dead key, with no code
change and no default flipped.

### Identified, NOT wired — proposed for a follow-up slice

Every other bare call site in the chat/vision tables above. They were
deliberately left untouched because a safe `provider=` override requires a
**per-provider model map** at that exact call site (`gpt-4o-mini` /
`gpt-4o` sent to Anthropic or Gemini is a 404, not a graceful failure — the
mismatch reads to an operator like a broken key). Inventing eight new,
unvalidated model maps under one incident-response slice is itself the
"quick fix at the wrong level" this platform's methodology forbids — each
one deserves the same scrutiny `ANALYSIS_MODELS` / `OCR_MODELS` got
(picking a model that is actually good at the task, not just "the first one
that answers"). Recommended order, highest leverage first:

1. `noctusai_lib.domain.digest.narrative()` — one seed function, unlocks
   core + social-wiring + daily-life + personal-finance simultaneously.
2. `social-wiring`'s own 8 unwired chat/embedding call sites — the
   switches (`resolve_chat_provider`, `resolve_embedding_provider`) and the
   settings UI already exist in this product; this is pure wiring, not new
   UI.
3. `community/moderacao_ai_service.py` — see the silent-fail-open flag
   below; this one has a correctness argument for urgency beyond "OpenAI
   might die again."
4. The MCP toolkit's embedding funnel — needs `GEMINI_API_KEY` provisioned
   AND a `provider=` parameter added to `ensure_llm_configured` /
   `embed_sync` / `code_embeddings.search` before it can move at all. This
   is the largest lift (new mechanism, not just wiring) and the highest-risk
   surface to leave unaddressed (see blast radius below).

### Explicitly NOT done

- No auto-failover was added anywhere. Every switch introduced or proposed
  is read-once-per-call from a setting the operator sets; none retries a
  different vendor on error.
- No product's `default_provider` / `default_chat_model` / effective
  behaviour changed for an org that has not opted in. Every wired call site
  was verified (via the erp-imobiliario test suite, 2189 passed) to resolve
  to `"openai"` byte-identically to its pre-slice behaviour when no
  `org_settings` row exists.
- Anthropic was not offered on any embedding or audio call site.
- No production database write was made. `org_settings` rows are the
  owner's to set, same as the social-wiring flip already was.

## Deliverable C.3 — strictly OpenAI-pinned, and why (two different reasons)

**Capability does not exist on the alternative vendor at all** (buying a
different key changes nothing):

- Every audio-transcription call site → Anthropic. `AnthropicProvider.
  transcribe_audio` raises `ProviderNotImplemented`.
- Every embedding call site → Anthropic. `AnthropicProvider.
  generate_embedding` raises `ProviderNotImplemented`.

**Capability exists; only the switch — or the credential — is missing**
(the owner can unblock this by decision, not by waiting on a vendor):

- Chat and vision → Anthropic, on every product EXCEPT erp-imobiliario
  (this slice) and social-wiring (pre-existing): the `AnthropicProvider`
  fully implements both, `ANTHROPIC_API_KEY` is already in `.env`, and
  `noctus.dev.llm_vision_analyze` proves the plumbing works today. These
  are unwired, not unsupported.
- Embeddings and audio → Gemini, everywhere: `GeminiProvider` implements
  both. This is a **missing credential** (`GEMINI_API_KEY`), distinct from
  the audio/embeddings-on-Anthropic case above, which is a missing
  **capability**. Buying/adding a Gemini key does not help Anthropic gain
  an embeddings endpoint; it DOES unblock every Gemini-capable path listed
  in this doc (embeddings fleet-wide, MCP embedding caches, best-effort
  audio).
- The MCP embedding toolkit specifically also lacks the **mechanism**
  (no `provider=` parameter exists in the funnel at all) — a third,
  narrower reason than "unconfigured": even with a Gemini key in hand,
  `ensure_llm_configured` needs code changed before it could use it.

## Deliverable C.4 — blast radius if the OpenAI key dies tomorrow

**Degrades loudly** (an exception reaches a caller who can act on it):
every product's `chat_completion` / `analyze_image` / `transcribe_audio` /
`generate_embedding` raises `LLMAPIError` on a 429; most services catch it
narrowly and either return a stated PT-BR marker (erp-imobiliario,
social-wiring's certidões/matrículas paths — "Análise IA não disponível") or
let it propagate to a 500. Either way the failure is VISIBLE.

**Degrades gracefully AND loudly-in-logs** (a designed fallback, not a
crash, but not silent either): `noctusai_lib.domain.digest.narrative()`
catches any exception, logs a WARNING naming the exception, and returns a
caller-supplied deterministic fallback string — used by core / social-wiring
/ daily-life / personal-finance's digest and narrative features. The
recipient gets a usable (if generic) digest, not an error page, and an
operator reading logs sees exactly why.

**Degrades silently** (the dangerous class — a dead provider looks like a
legitimate empty/negative result):

1. 🔴 `mcp/noctusai/tools/noctus/dev/_embedding_corpus.py::search_markdown_corpus`
   (backs `noctus.dev.kb_search`, `memory_search`, `corpus_search`) — line
   ~959-963: `try: q_vec = embed_sync(query); except Exception: return []`.
   A 429 and "genuinely no matching docs" are indistinguishable to the
   caller. **This is the exact incident** the WHY section describes,
   reproduced live while writing this doc: `noctus.dev.kb_recurrence_radar`
   returned `{"hits": [], "message": "embedding provider unreachable —
   consult skipped."}` for the CURRENT dead key — notably, THAT tool is
   honest about it (see the next point); `kb_search` / `memory_search` /
   `corpus_search` are not.
2. 🔴 `mcp/noctusai/tools/noctus/dev/code_embeddings.py::search` — the
   identical `try/except Exception: return []` pattern around its own
   `embed_sync(query)` call (~line 435), backing `noctus.dev.code_search`,
   `code_similar_to_text`, `find_reusable_component`.
3. Everything that composes those two inherits the silence:
   `noctus.dev.unified_query`, `code_neighbors`, `component_bundle`'s
   fallback path. **Not every MCP tool has this defect** —
   `noctus.dev.kb_recurrence_radar` and `noctus.dev.vector_calibration_analyze`
   surface `"embedding provider unreachable"` explicitly; the fix pattern
   already exists in this codebase, it is just not applied to the two
   highest-traffic search entry points.
4. 🔴 `noc_graph_cache.py`'s `SEMANTIC_NEIGHBOR` edge injection
   (`refresh(...)`, ~line 934) catches any exception and logs a WARNING,
   then continues — the graph builds "successfully" with zero semantic
   edges and nothing in the tool's RETURN VALUE says so; an agent has to
   separately check logs to notice the degradation.
5. 🔴🔴 **`community/services/moderacao_ai_service.py::avaliar_mensagem`** —
   the most severe finding in this sweep. The function returns `None` both
   when a message is legitimately not flagged (the documented, normal case)
   AND when `chat_completion` raises for ANY reason (bare `except
   Exception`, ~line 84). During an OpenAI outage, **every inbound message
   in this product is silently treated as "not flagged" — moderation
   fail-open** — logged only at WARNING with no operator-visible signal.
   This is not a "search returns empty" inconvenience; it is a content-
   moderation bypass with no symptom. Flagged here as the highest-priority
   item in this report, independent of the LLM-provider-selection topic.

**Keeps working unchanged:** anything already switched to a live
provider (`ANTHROPIC_API_KEY` present) — erp-imobiliario's and
social-wiring's document-transcription/certidão-analysis paths, once an
operator sets the `org_settings` row; `noctus.dev.llm_vision_analyze` called
with `provider="anthropic"` explicitly, today, with no further change.

## Deliverable C.5 — silent-failure call sites (flagged for fix-on-contact)

See the five 🔴 items in "Degrades silently" above. Recommended remediation
shape for #1/#2 (mirrors what #3's siblings already do): replace the bare
`except Exception: return []` with a result envelope that distinguishes
`{"hits": [], "reason": "no_match"}` from `{"hits": [], "reason":
"provider_unreachable", "detail": str(exc)}` — the SAME shape
`kb_recurrence_radar` already returns. Filed as a `scoped-improvement:` in
this report's footer rather than fixed in this slice (it touches the two
highest-traffic MCP search tools' return contract, which is a breaking
change for every caller pattern-matching on a bare list today — needs its
own dispatch).

## API / surface

```python
from noctusai_lib.integrations.llm import resolve_llm_provider

provider = resolve_llm_provider(
    "chat",  # or "vision" / "embedding"
    org_id,
    allowed=("openai", "anthropic", "gemini"),  # NEVER "anthropic" for "embedding"
    default="openai",                            # must be a member of allowed
)
# provider is always a member of `allowed`; reads `llm_<capability>_provider`
# from org_settings -> platform_settings -> env via resolve_credential.
```

## Anti-patterns

- **DON'T** pass a `provider=` override to `chat_completion` / `analyze_image`
  without ALSO selecting that provider's model via a per-provider map
  (`ANALYSIS_MODELS`, `OCR_MODELS`-shaped) — a mismatched model+vendor pair
  404s in a way that reads like a broken key, not a config error.
- **DON'T** offer `"anthropic"` in an `allowed` tuple for capability
  `"embedding"` — the API has no embeddings endpoint; the failure surfaces
  far from the config that caused it.
- **DON'T** build a full `ApiKeySpec` + encrypted-store + settings-page
  mechanism (`noctusai_lib.security.api_keys`) when a product just needs a
  switch — `resolve_llm_provider` is the lighter path for a product with no
  existing operator-facing settings surface for LLM keys.
- **DON'T** auto-failover on a provider error. Every switch in this fleet
  is manual-read-once; a silent vendor swap changes which model answered a
  request with nobody told.
- **DON'T** let a query/search function's `except Exception: return []`
  around an embedding call stand unflagged — a dead provider must never be
  indistinguishable from "no results" (see Deliverable C.5).

## Composes with

- `KB § PATTERNS/backend/seed-fake-real-adapter.md` — the Protocol+Fake+Real
  shape every LLM provider (openai/anthropic/gemini/fake) already follows.
- `KB § PATTERNS/backend/di-test-seam.md` — the `provider_resolver` /
  `transcriber_factory` bound-default seams this slice's tests use.
- `KB § PATTERNS/common/cache-as-agent-tool.md` — the keeper-mirror caches
  whose silent-empty failure mode this doc documents.
- `KB § CONTEXT/backend/05-AI-FEATURES.md` — per-product AI feature catalog;
  its "Anthropic + Gemini guarded stubs" line was stale (both are real,
  working providers with two narrow capability gaps) and was corrected the
  same commit as this doc, per the gate↔methodology-sync rule.
- `products/social-wiring/backend/app/services/api_keys_store.py` — the
  fuller (UI + encrypted store + 3 named switches) sibling mechanism this
  doc's lightweight switch generalises from.

## History

- 2026-09-18: authored from the `llm-provider-dependency-sweep` slice,
  triggered by the 2026-09-17 OpenAI `insufficient_quota` incident. New
  seed helper `resolve_llm_provider` shipped + wired into erp-imobiliario's
  vision and chat/analysis surfaces; the remaining ~20 chat/vision/embedding
  call sites across 8 more products + the MCP toolkit mapped and classified
  but deliberately left unwired pending per-provider model maps (see
  "Proposed, not done").
