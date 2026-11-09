# Retrieval organ — the one shared RAG layer (`noctusai_lib.integrations.retrieval`)

> **One-line statement.** Products never hand-roll chunking, pgvector search or an answer cache: they use the seed's retrieval organ — chunking, embeddings via the shared `generate_embedding(s_batch)`, a per-(namespace, org) pgvector store, top-k search with a score threshold, and a semantic cache that honours the LGPD opt-out. Protocol + Fake + Real + factory (`KB § PATTERNS/backend/seed-fake-real-adapter.md`).

## Why it exists

About five local copies existed (social-wiring permutas `embeddings.py`, social-wiring `segmentation_service.py`, erp-imobiliario `embedding_service.py` + `matching.py`, knowledge-extractor `supabase_adapter.py`, agents Studio lexical `agents.search_knowledge`) while help-chat stuffed a whole markdown file into every prompt. N≥3 ⇒ formalize (`KB § PATTERNS/architect/project-execution.md`).

## Shape

| Piece | Where |
|---|---|
| `chunk_markdown` — heading-path aware, fenced code never split, packed to `max_chars`, oversized paragraphs window-split with overlap | `retrieval/chunking.py` |
| `Embedder` (`LLMEmbedder` Real = `generate_embedding(s_batch)`; `FakeEmbedder` deterministic hashing) | `embedder.py` / `fake.py` |
| `RetrievalStore` (sync Protocol) · `SupabaseRetrievalStore` Real (RPC) · `InMemoryRetrievalStore` Fake | `protocol.py` / `real.py` / `fake.py` |
| `Retriever.index_text` (skips when the stored corpus hash matches: no embedding spend; model/chunking change re-indexes) · `.search(k, min_score)` | `service.py` |
| `SemanticCache.lookup/put` | `semantic_cache.py` |
| `configure_retrieval_store(make_retrieval_store(get_core_client))`, `make_retriever`, `make_semantic_cache` | `factory.py` |

## Where the tables live

Core `public` (migration `products/core/backend/migrations/115_retrieval_organ.sql`): `retrieval_chunks`, `retrieval_cache` and `retrieval_*` RPCs, reached through the service-role core client — the same route as `help_chat_*`, `spend_reservations`, the prompt registry. So a product needs NO tables of its own; a product that wants a corpus picks a `namespace` (`"<organ-or-feature>:<product>"`). Both tables are tier `service` (`COMMENT ON TABLE … 'tier:service'`, RLS on, no policy for anon/authenticated, grants revoked) — isolation is the exact `(namespace, org_id)` predicate inside every function, never RLS (the service role bypasses it).

## Isolation + LGPD (by construction, tested)

- Scope is EXACT: `org_id=None` is the platform scope (e.g. a product's own docs); an org-scoped corpus is never visible to another org nor to the platform scope, and the platform corpus never appears in an org search. There is no cross-org read method. `meter_org_id` only attributes embedding spend.
- Cache: a hit needs the same scope AND `prompt_version` AND cosine ≥ `min_score` (default 0.93: a wrong hit is a confident wrong answer) AND unexpired. Only a hash of the question is stored.
- `cache=False` is the LGPD opt-out and is total: nothing embedded, read or stored (same gate as `integrations/llm/cache.py`). Cache-layer failure is a logged miss, never an exception and never silent.
- `purge_org(org_id)` erases every chunk + cache row of an org (LGPD erasure; also `ON DELETE CASCADE` on the org FK).
- Vectors are `vector(1536)` (OpenAI `text-embedding-3-small`); the Real store refuses another width before any RPC. A different model = migration + full re-index.

## First consumer — help-chat

`HelpChatKnowledgeSelector` (`domain/help_chat/service.py`): lazily indexes the product knowledge under `help_chat:<product>` (platform scope), then returns the top-k chunks for the last 3 user turns (a bare "sim" keeps its topic). Never silent: index failure / retrieval error (WARNING) and "nothing relevant" (INFO) fall back to the WHOLE file, logged with `reason=`. `load_knowledge` stays the mount-time fail-loud check and the fallback text.

## Local copies still to fold in (named destination `NOC-REMEDIATE[retrieval-organ]`)

permutas `embeddings.py` stores vectors ON the domain row (`permuta_ativos.embedding` + `embedding_interesses`, bilateral profile↔interest scoring), not a chunk corpus — not behaviour-identical to this organ, so it keeps its marker. Same for `segmentation_service.py`, knowledge-extractor `supabase_adapter.py` and agents `search_knowledge` (lexical full-text, deliberately not vector). erp-imobiliario is inactive: prior art only.

## Anti-patterns

Swallowing a retrieval exception into an empty list (the selector falls back AND logs). Embedding per chunk in a loop (use `embed_many`). Caching a multi-turn answer by its last question. Adding a per-product vector table instead of a namespace. Changing the embedding model without re-indexing.

## Composes-with

`KB § PATTERNS/ai/ai-engineering-canon.md` § 7 · `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `KB § PATTERNS/security/access-tiers.md` · `KB § PATTERNS/backend/llm-usage.md` · `KB § PATTERNS/backend/postgres-craft.md`.
