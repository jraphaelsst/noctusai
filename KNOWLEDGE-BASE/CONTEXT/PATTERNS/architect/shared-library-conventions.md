# Shared-Library Conventions

> Naming, absorption, and privatization rules enforced by the catalog tool.
> Run `python mcp/noctusai/cli.py --catalog` to see current state.
> These conventions apply to `seed/lib/backend/` (`noctusai_lib`) and
> `seed/framework/backend/` (`noctusai_seed`). Frontend equivalents
> (`@noctusai/lib`, `@noctusai/seed`) follow the same rules.

---

## 1. Orphan → privatize rule

An **orphan** is a public lib symbol with zero importers across all products
and no lib-internal consumer. The catalog tool (`mcp/noctusai/tools/catalog.py`)
reports them under `## Orphans`.

**Decision flow:**

1. Is the symbol a **return type of a public factory** (e.g. `DatabaseModule`
   returned by `create_database_module()`)? → **Keep public.** Users need it
   for type annotations. This is an intentional false-positive.
2. Is the symbol **infrastructure that shipped but was never wired up** (e.g.
   typed exceptions, role helpers, pagination helpers)? → **Keep public AND
   wire it up.** Open a backfill task. Don't privatize code whose reason for
   existing is "every product should eventually use this."
3. Is the symbol an **implementation detail** that leaked into the public API
   (e.g. internal constants, helper classes only called by functions in the
   same module)? → **Privatize.** Prefix with `_` (`FROM_EMAIL` → `_FROM_EMAIL`).
4. Is the symbol **dead code** (was used, isn't anymore, no backfill plan)?
   → **Delete.** Don't leave it to rot. Confirm with the owner first.

**Examples applied (2026-04-18):**

| Symbol | Decision | Reason |
|---|---|---|
| `noctusai_lib.email_templates.FROM_EMAIL` | privatize → `_FROM_EMAIL` | only used inside the module |
| `noctusai_lib.logging_config.JSONFormatter` | privatize → `_JSONFormatter` | only used by `configure_logging()` |
| `noctusai_lib.logging_config.HumanReadableFormatter` | privatize → `_HumanReadableFormatter` | only used by `configure_logging()` |
| `noctusai_lib.notifications.NOTIFICATION_FIELD_MAP_TO_PT` | privatize | only used by the public mappers |
| `noctusai_lib.notifications.NOTIFICATION_FIELD_MAP_FROM_PT` | privatize | only used by the public mappers |
| `noctusai_lib.auth.get_current_user` | privatize → `_get_current_user` | meant to be wrapped by `make_get_current_user`, never imported directly |
| `noctusai_lib.exceptions.{NotFoundError, ...}` | keep public, BACKFILL | typed hierarchy; products still raise raw `HTTPException` — replace at call sites |
| `noctusai_lib.roles.{can_manage_team, ...}` | keep public, BACKFILL | products still hand-roll role checks |
| `noctusai_seed.database.DatabaseModule` | keep public | return type of a factory — users need it for annotations |

---

## 2. Duplicate detection → categorize, then act

The catalog's `## Duplication candidates` section flags public top-level
functions/classes with the **same name** in 2+ products that **aren't** in
the shared lib.

Every flagged pair goes into exactly one of three buckets:

### ABSORB — same intention, same shape
Same OpenAI call, same pagination helper, same signed-token generator.
Implementations may differ in superficial details (which settings table they
read from, what the schema name is) but the core logic is identical.

**Action**: extract to `noctusai_lib` (or an appropriate submodule). Parameterize
the differences — inject via `LLMConfig`-style config, pass the schema name,
supply a key-provider callable. The shared function stays ignorant of
product-specific plumbing.

**Example**: `generate_embedding` in ERP + Therapy — same `text-embedding-3-small`
call, only the API-key resolution differs. Lands in `noctusai_lib.llm.embeddings`
with an injectable key provider.

### RENAME — different domains, same name by accident
Two products each have a `criar_meta` or a `login` or a `generate_token`, and
they mean **genuinely different things** (sales target vs. habit goal vs.
savings goal; B2B auth vs. clinical auth; unsubscribe token vs. LiveKit token).
Merging would force a fake abstraction.

**Action**: rename to **`<product>_<domain>_<original>`**. Both axes are
required:

- **`<product>`** — disambiguates at the platform level. A `sales` domain in
  PF would still collide with ERP's `sales` domain without the product prefix.
- **`<domain>`** — the semantic domain, not the router filename. `metas` as a
  domain doesn't help when all three products have a `metas` router; the real
  domains are `sales` / `savings` / `habit`.
- **`<original>`** — the verb + resource from the original function name,
  unchanged.

**Examples** (from the 2026-04-18 pass):

| Original | Product | Domain | New name |
|---|---|---|---|
| `criar_meta` | ERP | sales | `erp_sales_criar_meta` |
| `criar_meta` | PF | savings | `pf_savings_criar_meta` |
| `criar_meta` | Daily Life | habit | `dailylife_habit_criar_meta` |
| `login` | AdConnect | b2b | `adconnect_b2b_login` |
| `login` | Therapy | clinical | `therapy_clinical_login` |
| `generate_token` | Mailing | unsubscribe | `mailing_unsubscribe_generate_token` |
| `generate_token` | Therapy | livekit | `therapy_livekit_generate_token` |

### ALREADY-DIFFERENT — same domain, implementations diverged
Same name, same domain, but the bodies diverged too much to share without a
significant refactor (different schemas, different side effects, different
services called). Example: ERP `criar_ativo` (triggers embedding re-gen and
match re-computation) vs. PF `criar_ativo` (pure CRUD).

**Action**: apply the **same `<product>_<domain>_<original>` rename**. These
still produce catalog noise if left un-renamed, and the rename signals
"these are parallel, not shared" — so when the domains eventually converge
(or diverge permanently), the rename doesn't stand in the way.

**Do not** create an ignore-list file to silence these in the catalog — that
violates the "No workarounds" rule. Fix at the source.

---

## 3. Workaround prohibition

When the catalog produces signal you don't like, the answer is **never** to
mask it. Specifically:

- ❌ No `.catalog-ignore` / `.drift-ignore` / allowlist files.
- ❌ No heuristics that hide specific function-name patterns.
- ❌ No "just rename the function to a private name to hide it from the
  duplicates list" (that breaks its actual public API).

Instead:

- ✅ Rename the colliding names at the source (RENAME rule above).
- ✅ Absorb truly-shared logic into the lib (ABSORB rule above).
- ✅ Accept informational signals (single-consumer lib symbols are not warnings).
- ✅ If the tool's heuristic produces genuine false positives at scale, fix
  the **heuristic** (improve the detection), not the codebase's honesty.

Rationale: the catalog is a living observation layer. Silencing it teaches
future agents that the drift doesn't exist. Renaming at the source teaches
them that drift has a name and a fix.

---

## 4. Catalog tool reference

- **Run manually**: `python mcp/noctusai/cli.py --catalog`
- **Output**: `mcp/noctusai/catalog.md` (auto-regenerated; do not edit by hand)
- **Source**: `mcp/noctusai/tools/catalog.py`
- **Config**: `LIB_ROOTS` dict at the top of `catalog.py` — update when the
  namespace rename to `noctusai.lib` / `noctusai.seed` happens.

**When to run**:
- Before opening a PR that touches `seed/lib/backend/` or
  `seed/framework/backend/`.
- After any rename, to verify the rename didn't silently break import paths.
- During `--review` (future wiring) as a drift check.

**What to look at**:
- `## Orphans` — apply §1 rule.
- `## Duplication candidates` — apply §2 rule.
- `## Single-consumer symbols` — informational only, do not warn.
