"""Integrations — external-service clients + boundaries.

**Layer contract.** Anything in `integrations/` MUST:
- Wrap a specific external service (Supabase, OpenAI, Anthropic,
  Google GenAI, Resend, Stripe, WhatsApp, etc.).
- Expose a stable internal API regardless of the provider's SDK
  surface — products import `from noctusai_lib.integrations.<x>`,
  never the underlying SDK directly.
- May import from `primitives/`, `config/`.
- MUST NOT import from `api/` or `domain/` — integrations are
  consumed by those layers, not the reverse.

**Why a layer.** Today external clients are scattered: `llm/` is at
the seed-lib top level, `email/` is also at the top level, `database.py`
is at the top level. Future additions (Stripe wrapper, WhatsApp
gateway) would land in the same flat namespace. Centralizing means
"where do we talk to the outside world?" has one answer.

**Planned occupants** (Phase 4 step 2):
- `llm/` — multi-provider chat / embeddings / audio / vision / budget
- `email/` — Resend client + digest + templates
- `database.py` — Supabase client factories (singletons, schema-scoped)

See `KB § PATTERNS/seed-lib-layout.md` for the full layer model.
"""
