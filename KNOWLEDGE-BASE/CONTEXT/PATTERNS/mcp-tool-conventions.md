# MCP tool conventions

> Conventions for authoring tools in `mcp/noctusai/`. Lands during
> `projects/mcp-server-expansion/` Phase 3 (naming + Pydantic) and Phase 6
> (the principle); `noctusai_lib`-side patterns referenced inline.
>
> **Status:** active. Backward-compat flat aliases (`noctusai_<x>`)
> were retired 2026-05-03 by `projects/mcp-tool-name-deprecation/` —
> dotted `noctus.dev.<x>` is the sole canonical form. The "Backward-compat
> aliases" section below is historical reference only.

---

## 0. The MCP server is a living organism

Like a project, the MCP server **evolves over phases** — it doesn't ship in
one batch and stop growing. The 24-tool dev branch (`noctus.dev.*`) was the
first branch; vendor adapters (`google.*`, `openai.*`, `vista.*`),
business-logic primitives (`noctus.business.*`), and future umbrellas are
subsequent branches that land as the substrate matures.

User direction (established 2026-05-03 during the FastMCP-switch session):
*"the mcp server is also a living organism that grows and evolves over time
… we got devtools, but why not expand for other utilities as well?"* — and,
on opportunity-spotting: *"we actively search for improvements ops for our
projects, why wouldn't we do the same for the great connector and tooler we
have?"*

**Implications for future agents:**

- **Assume growth.** Treat new umbrellas as welcome (not a violation) when
  they earn their place — a second consumer + a substrate that exists
  (in `noctusai_lib` or vendor SDK).
- **Apply the same active-improvement lens** the project workflow uses
  (`KB § 01-PHILOSOPHY.md § Flag MCP-first / AST-first opportunities`):
  while working anywhere in the codebase, if you see a missed branch /
  missed exposure, surface it in the work output's improvements block —
  don't silently move on.
- **Branches over sprawl.** New tools follow the existing `<umbrella>.<service>.<action>`
  contract (§1) — growth doesn't mean ad-hoc additions; it means new
  branches that share the trunk's design discipline.

**How to spot a missing branch:**

- A capability used by 2+ products with no shared abstraction →
  candidate for `noctus.business.*` (or formalize into `noctusai_lib`
  first, then expose).
- A vendor SDK called from products with bespoke wiring → candidate
  for vendor umbrella (`google.*`, `openai.*`, `vista.*`).
- A pattern that **agents** (Claude Code, future bots) would benefit
  from — even before products use it — → candidate for new dev sub-branch
  under `noctus.dev.*` or its own dev sibling.

The dev branch is **one face of a wide-purpose toolkit, not the entire
identity**. Future projects scoped against this server should plan in
that frame — phases, branches, growth — not as one-off tool dumps.

---

## 1. Naming — three dotted segments

`<umbrella>.<service>.<action>` — three segments, no exceptions.

- **`noctus.dev.*`** — the platform dev toolkit (validate, review,
  analyze_patterns, scan_recurrence, …). The "what we currently have."
- **`noctus.business.*`** — business-logic primitives any agent can
  compose (scheduling, appointments, users, whatsapp). Lands in Phase 5
  of `projects/mcp-server-expansion/` after `noctusai_lib` substrate
  ships.
- **`google.*`** — Google-vendor APIs (calendar, maps).
- **`openai.*`** — OpenAI-vendor APIs (audio, vision).
- Future namespaces by analogy (`anthropic.*`, `apple.calendar.*`,
  `mapbox.maps.*`, `vista.*`, etc.).

Rule of thumb for `noctus.*` vs `<vendor>.*`: a tool lives under a
vendor namespace when the **capability itself** is vendor-specific
(Google Calendar IDs, OAuth scopes, OpenAI completions API). Tools we
*own* that happen to call out to a vendor under the hood live under
`noctus.*` — the vendor is an implementation detail.

### Backward-compat aliases (HISTORICAL — retired 2026-05-03)

> Retired by `projects/mcp-tool-name-deprecation/` on 2026-05-03. The
> dual-name pattern is no longer in use; every dev tool registers under
> `noctus.dev.<action>` only. Section preserved for historical context;
> see git history at commits `dc5de6a` (mcp-server-fastmcp-switch close)
> and the `mcp-tool-name-deprecation` close commit for the migration.

During mcp-server-expansion Phase 3 (originally) every `noctusai_<action>`
flat tool kept working alongside a newly added dotted `noctus.dev.<action>`
alias — both names dispatched to the same handler. After the FastMCP
per-file `register()` switch (Phase 4 of mcp-server-fastmcp-switch),
adding the dotted alias became a one-line addition per tool file. The
2026-05-03 retirement removed the flat-name registrations once every
consumer surface (KB, project docs, CLAUDE.md, templates, tests, READMEs)
referenced the dotted form.

---

## 2. Pydantic In/Out per tool

New tools land with `XxxInput(BaseModel)` and `XxxOutput(BaseModel)`
classes **inside the tool file itself**. The shape is:

```python
# tools/<area>/<action>.py (Phase 4 hierarchical layout)
# or tools/<flat>.py (current layout)
from pydantic import BaseModel, Field

class XxxInput(BaseModel):
    foo: str = Field(description="What this is for.")

class XxxOutput(BaseModel):
    result: dict[str, Any] = Field(description="Tighten as call sites stabilize.")
```

`server.py`'s `_tool(name, desc, model=XxxInput)` auto-generates the
JSON schema via `Model.model_json_schema()`. No hand-coded property
dicts.

**Rules:**
- New tools: Pydantic In + Out from day one.
- Existing tools: migrate **opportunistically** when touched (don't
  mass-migrate for its own sake).
- Output models start minimal (`dict[str, Any]` for dynamic surface)
  and tighten as the shape stabilizes. The README documents the
  pattern as deliberate, not lazy.

### Worked examples (Phase 2 landing)

The first 5 migrated tools each carry both classes:
- `tools/context.py` — `AgentContextInput`/`Output`,
  `ProductContextInput`/`Output`.
- `tools/compliance.py` — `ValidateInput`/`Output`, `ValidateIssue`.
- `tools/analyzers.py` — `AnalyzePatternsInput`/`Output`,
  `DuplicatedFunction`, `InlineHookIssue`.
- `tools/review.py` — `ReviewInput`/`Output`, `ReviewMode`.
- `tools/catalog.py` — `CatalogInput`/`Output`.

---

## 3. Hierarchical registration (lands in Phase 4)

Each leaf module exports `register(server)`; sub-umbrella `__init__.py`
calls every leaf's `register`; the top-level `tools/__init__.py`
exposes `register_all(server)` that the FastMCP server calls once at
startup.

```python
# tools/noctus/dev/validate.py (Phase 4 target shape, post-2026-05-03)
def register(server):
    server.tool(name="noctus.dev.validate", description=...)(validate)
```

This replaces the flat dispatch map at `server.py:282-399`. Phase 4
also updates `cli.py` import lines (the CLI does NOT share dispatch —
it imports tool modules directly).

---

## 4. Lazy `NoctusContext`-style container — **only for business-logic tools**

Dev tools stay stateless (filesystem + subprocess). Business-logic
tools get a `NoctusContext` lazy-dep container so they're trivially
callable from three modes:

1. **From the MCP server** — FastMCP creates a context, calls the
   tool, closes.
2. **In-process from a product** — the product creates a context with
   its own DB session.
3. **From tests** — tests construct a context with fakes/mocks
   injected.

The dual-callable shape:

```python
def my_tool(payload: MyInput, ctx: NoctusContext | None = None) -> MyOutput:
    if ctx is not None:
        return _impl(payload, ctx)
    with noctus_context() as owned_ctx:
        return _impl(payload, owned_ctx)
```

Two registration models coexist — that's fine; forcing dev tools into a
context would over-engineer the dev surface.

---

## 5. Settings shim

`mcp/noctusai/settings.py` re-exports `BaseAppSettings` from
`noctusai_lib.config.settings` as `Settings`, plus a local
`lru_cache(maxsize=1)`-backed `get_settings()` singleton. The lib
**doesn't ship a global factory by design** — per-product
`Settings(BaseAppSettings)` is the documented pattern, and a
lib-level singleton would force every consumer to share one across
processes. The MCP-scoped factory in the shim is the right shape.

When the MCP gets extracted to its own repo, this shim becomes the
source — every consumer (the platform, future bots, …) reads its own
`.env` against the same shape.

### Path constants — `REPO_ROOT` and `PRODUCTS_DIR` live in settings.py

Every tool module that needs the noc repo root imports from settings:

```python
from settings import REPO_ROOT, PRODUCTS_DIR
```

Internally, settings.py delegates to
`workspace.get_noctusai_home()` — the canonical marker-file-based
resolver in `mcp/noctusai/workspace.py` — which already handles
primary-vs-seed-workspace resolution correctly. PRODUCTS_DIR is
`REPO_ROOT / "products"`.

**Forbidden** in tool modules: re-deriving the path locally via
`Path(__file__).resolve().parents[N]`. This was the canonical pattern
across 18 of 24 dev tools until mcp-server-fastmcp-switch Phase 3 had
to bump every `parents[3]` to `parents[5]` (the file relocation
changed the depth). Rule: **path constants are framework-level; tools
import, never compute.**

### Write tools resolve the caller's root via `resolve_caller_root`

**Rule.** Every MCP tool that writes to the filesystem (creates dirs,
writes files, runs `git mv`, mutates compose / start.sh / migrations,
…) accepts an explicit `worktree_path: str | Path | None = None`
argument and resolves the target root via
`workspace.resolve_caller_root(worktree_path)`. Module-level
`REPO_ROOT`/`PRODUCTS_DIR` is the **default** (used when
`worktree_path is None`), not the only resolution path.

**Why.** The MCP server is a single long-running stdio process. It
boots with one fixed CWD (typically noc main) and `os.getcwd()`
inside any tool returns the SERVER's CWD, NOT the caller's. The
MCP protocol does not transmit caller-CWD per call. Therefore tools
that need caller-aware paths MUST receive the worktree root as an
explicit argument — auto-detection from server-side state is
fundamentally impossible.

**Background.** Filed by
`projects/mcp-worktree-path-resolution/` (2026-05-10) after
Engineer E's `imobi-scheduling-bot-creation` Phase 0+1 close
surfaced the bug: `scaffold_product` wrote 58+ files to noc's
filesystem from inside Engineer E's isolated worktree because
`REPO_ROOT` was bound at server startup. Engineer E worked around
via `cp -r` + hand-mirror; the fix lives at the seed level.

**Helper contract** (`mcp/noctusai/workspace.py`):

```python
def resolve_caller_root(worktree_path: str | Path | None = None) -> Path:
    """When worktree_path is None → returns noc_home (back-compat).
    When set → validates path (must be a dir containing both `.git`
    AND `.noctusai-workspace`); returns the resolved Path.
    Raises ValueError on invalid input — no silent fallback to noc.
    """
```

**Resolution priority** in every write tool:

1. Explicit test seam (`products_dir=` / `repo_root=` / `ledger_path=`) wins.
2. `worktree_path` arg → `resolve_caller_root(worktree_path)`.
3. Module-level `REPO_ROOT` / `PRODUCTS_DIR` fallback (server-startup default).

This ordering preserves test seams while letting production code thread
the new arg through. Tests calling the function directly omit
`worktree_path`; engineers in worktrees pass it; architects on main
omit it.

**Adopters** (current state, 2026-05-11 — Phase 4 closed):

Wave 1 — Engineer K Phase 1-2 (2026-05-10):
- `noctus.dev.scaffold_product` / `noctus.dev.delete_product` / `noctus.dev.available_ports`
- `noctus.dev.scaffold_migration`
- `noctus.dev.archive`
- `noctus.dev.file_proposal`
- `noctus.dev.lgpd_flag` / `noctus.dev.lgpd_list`
- `noctus.dev.history_record`

Wave 2 — Engineer M Phase 4 rollout (2026-05-10):
- `noctus.dev.verify_master_prompt`
- `noctus.dev.improvements`
- `noctus.dev.review`
- `noctus.seed.absorb_file`
- `noctus.dev.promote_from_seed_workspace` / `noctus.dev.list_promotions`
- `noctus.dev.build_products`
- `noctus.dev.catalog`
- `noctus.dev.check_three_way_sync`

Wave 3 — Engineer RRR Phase 4 close (2026-05-11, recurrence N=7+ this session):
- `noctus.dev.set_proposal_status` (residual write-tool gap)

**18 total write tools adopt the pattern.** Phase 4 rollout complete.

**Documented exemption:** `phase_learnings.py` (log_learning / query_learnings / consume_learning) writes to a centralized gitignored SQLite at `mcp/noctusai/data/phase_learnings.db` — by design local-only / per-machine. The Fake-vs-Real exemption test applies: a fake here would not exercise different code than the real, and the data store is intentionally session-local.

**No silent fallback.** Passing an invalid `worktree_path`
(non-directory, missing `.git`, missing `.noctusai-workspace`) MUST
raise `ValueError` — the whole point of the arg is to surface
worktree-bypass slips. Silent fallback to noc home would defeat the
guard.

**Regression tests live in** `mcp/noctusai/tests/test_workspace.py`
(`TestResolveCallerRoot`) + per-tool test files
(`TestWorktreeAwarePathResolution` in `test_scaffold.py`,
`test_archive.py`, `test_scaffold_migration.py`) +
`test_worktree_rollout_phase4.py` (30 tests covering all
Wave 2 + Wave 3 adopters).

---

## 6. CLI dual-entrypoint stays

Sibling business-logic MCPs are MCP-only. We keep the CLI alongside the
MCP because the CLI is a real consumer (humans + scripts +
pre-commit hooks all use it). Both entrypoints share tool functions,
not the dispatch map.

---

## 7. MCP-first principle

When we want to expose a capability to agents (Claude Code, future
bots, future Vista CRM agents), the **default surface is MCP**. AST-first
is its sibling principle (CLAUDE.md §1, KB § PATTERNS/ast.md): mechanical
edits go through AST tools; agent-exposable capabilities go through MCP
tools.

This rule is in CLAUDE.md §1 (memory: `feedback_mcp_first.md`); this doc
is its depth pointer.

---

## 8. Coexistence rules

- **Backward-compatible during expansion phases (historical).** During
  mcp-server-expansion Phase 3 and the FastMCP switch, flat tool names
  kept working alongside dotted aliases. The
  `mcp-tool-name-deprecation` project completed retirement on
  2026-05-03 — flat `noctusai_<x>` is no longer registered.
- **Hierarchical registration replaces the flat dispatch map only when
  ≥1 namespace exists.** First namespace candidate: `noctus.dev.*` (the
  existing toolkit). Adding sibling vendor/platform groups
  (`google.*`, `openai.*`, `noctus.business.*`) drives the payoff.
- **Future renames stage through dotted aliases.** Any future rename
  follows the same protocol the 2026-05-03 retirement codified: add
  the new name as a dual registration, migrate every consumer surface,
  then delete the old registration. No "rename + retire in one commit"
  for in-use names.

---

## 9. Filter-proxy tools — dodging external tool-result caps

Some external MCP servers (notably Supabase MCP) return responses that
overflow Anthropic's tool-result cap on real product data — a typical
`get_advisors` call on an active schema lands 138KB-393KB on the wire,
and the caller can't even see the result. Wrapping the external call
inside a noc-side MCP tool that **filters server-side before returning**
is the cap-dodge pattern.

**Canonical adopter:** `noctus.dev.supabase_advisors` — wraps Supabase
MCP `get_advisors` with `schema=` / `severity=` / `type=` filters. Shrinks
real-world dumps ~30x by dropping rows the caller doesn't need, returning
≤10KB even for big-product schemas.

**Design rule.** A filter-proxy tool does NOT recursively call another
MCP server — noc has no MCP-to-MCP client infrastructure, and adding
one for a single tool inverts the cost/value. Instead the proxy accepts
the raw dump as input (two shapes):

- `<dump>_jsonl_path=` — caller saves the upstream output to disk first
  (via shell pipe `mcp__claude_ai_X__get_Y | tee file`), then calls the
  proxy with the file path. The dump traverses the filesystem rather
  than the tool-result channel.
- `<dump>_raw=` — inline list[dict] for direct programmatic use (smoke
  tests, fixtures, future MCP-from-MCP wiring if it ever lands).

**Required contract:**
- Exactly one of the two input shapes — `ValueError` if both/neither.
- All filters fire **server-side before serializing the return value**.
- Per-row tolerance — malformed rows log + skip, don't kill the batch.
- `worktree_path=` for relative file-path inputs (same shape as the
  caller-root resolution in §5).
- Pydantic-validated output dict per row, never raw upstream shape (the
  whole point is normalization + scope-tightening).

**When NOT to use this pattern.** When the upstream response is already
small (<20KB) — wrapping a tiny call just adds dispatch surface. The
trigger is **observed overflow** (Engineer Z's 138KB+393KB on imobi P3),
not theoretical concern.

**Adopters** (current state, 2026-05-10):

- `noctus.dev.supabase_advisors` — Supabase MCP `get_advisors`.

Future candidates: any upstream MCP whose typical response exceeds the
tool-result cap on real data. File a filter-proxy follow-up project when
an in-flight project hits the cap (the symmetric of how
`projects/noctus-supabase-advisors-proxy/` was filed).
