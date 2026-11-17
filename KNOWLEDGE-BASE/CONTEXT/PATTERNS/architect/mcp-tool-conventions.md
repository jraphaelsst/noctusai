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

### 5a. READ / verify tools are ALSO tree-dependent — the convention has no write-only exemption

**The bug class is not write-specific.** Any tool whose answer depends on
tree CONTENTS — not just where it writes — silently answers about the
PRIMARY when called from a worktree without `worktree_path`. This is
**worse** than the write-side miss: a bad write is often visible via
`git status` somewhere; a read/verify tool that answers wrong looks
**plausible** — there is no error, no diff, nothing to notice. Confirmed
live 2026-07-16 → 2026-07-20 (three sessions, same root cause):

- `noctus.dev.register_organ` / `noctus.dev.find_reusable_component`
  (2026-07-16) — an engineer's worktree-only organ returned
  `bundle-not-found` because the scan ran against the primary.
- `noctus.dev.pytest` (2026-07-20) — reported **"689 passed" from the
  primary** while the worktree's actual suite was never run. **This is a
  false-green generator** — an engineer could ship on a test result that
  never exercised their code. The single most dangerous instance found.
- `noctus.dev.auto_improvement_refresh` (2026-07-20) — refreshed the
  primary's ndjson and reported a false `in-sync`, missing staleness the
  worktree's own pre-commit hook correctly flagged as blocking.

All three are fixed (2026-07-20) the same way: `worktree_path: str | None
= None` → `resolve_caller_root(worktree_path)` when given, else the
pre-existing module-level constant (unchanged default — see `testing.py`
`_products_dir_for`, `auto_improvement.py` `_ledger_path_for`,
`find_reusable_component.py` `_resolve_root`). The CACHE a tool writes to
is frequently **Tier-1 shared** (`<git-common-dir>/noctusai/cache/` — see
`KB § PATTERNS/common/cache-portable-architecture.md`) and therefore
identical regardless of caller tree; `worktree_path` only changes which
SOURCE file/tree is read/hashed/tested — never where the cache lives.

**Refuse-vs-silent-default — the decision (2026-07-20), and why it stays
default-to-primary.** The obvious-looking fix — make `worktree_path`
REQUIRED, refuse (raise) when absent — was considered and **rejected** for
this convention. Reasoning:

1. **The majority of legitimate callers genuinely want the primary.** The
   orchestrator/tech-lead runs `noctus.dev.pytest()` / `refresh()` /
   `find_reusable_component()` constantly from the primary tree (pre-release
   checks, cross-cutting consults, non-worktree sessions). Refusing on
   `None` would break every one of those call sites for a benefit only the
   worktree-caller case needs.
2. **Consistency beats local optimization.** 18+ tools already ship the
   `None → primary` default (the Wave 1-3 adopters above); a DIFFERENT
   default semantics on a handful of newer tools would be its own silent
   footgun — "wait, does THIS one refuse or default?" is exactly the kind
   of per-tool special-casing this convention exists to eliminate. Brief
   discipline for this fix explicitly required "mirror the existing
   pattern... do not invent a new one."
3. **The actual failure is invisibility, not the default value.** A
   primary-default answer is CORRECT for the majority caller and
   RECOVERABLE for the worktree caller — IF the caller can tell which tree
   answered. The default was never the problem; the silence was.

**What ships instead: mandatory transparency.** Every tree-dependent
tool's response now carries the resolved root it actually operated
against — `resolved_root` (`testing.py`, `find_reusable_component.py`
`register_organ`) or `resolved_ledger_path` (`auto_improvement.py`,
which resolves a file, not a directory). `find_reusable_component` itself
returns a plain list (not a dict) — its shape cannot carry the field
without a breaking change, so it stays undocumented at the call site;
callers needing tree-provenance for organs should read it off the
companion `register_organ` call. **New tree-dependent tools MUST return
their resolved root/tree** — omitting `worktree_path` is a legitimate
default; omitting the *proof of which tree answered* is the actual bug
this closes. A refuse-on-`None` posture remains the right call ONLY for a
tool with **no legitimate primary-default caller at all** — none of the
tools audited in this pass qualified; if one is ever found, refuse there
specifically rather than reopening this convention-wide.

**Known further instances, NOT yet fixed (found by grep, not triaged
one-by-one — do not assume this list is exhaustive or that every entry is
a real bug):** any tool file under `mcp/noctusai/tools/` importing
`REPO_ROOT`/`PRODUCTS_DIR` from `settings` with zero `worktree_path`
occurrence in the file. As of 2026-07-20 that is ~55 files. Some already
carry the SAME `repo_root or REPO_ROOT` shape `register_organ` had
pre-fix and are straightforward follow-ups: `refs.py`,
`component_bundle.py`, `component_list.py`. Some resolve a RELATIVE path
argument against `REPO_ROOT` unconditionally, so an absolute-path caller
is unaffected but a relative-path caller from a worktree is not:
`outline_python.py`, `outline_typescript.py`. Many are legitimately
primary-only by design — shared ledgers/registries the tool explicitly
pushes to `origin/dev` regardless of caller tree (`branch_pointer.py`,
`dispatch_budget.py`, `vector_costs.py`, `brief_ledger.py`, `release.py`)
— these are NOT bugs and should not be "fixed" into worktree-scoping.
Triaging the full list is future work; do not silently assume it has been
done.

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
is its sibling principle (CLAUDE.md §1, KB § PATTERNS/common/ast.md): mechanical
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

---

## 10. Node toolchain — ONE resolver (`node_toolchain.resolve`)

The toolkit node dir's `node_modules` is gitignored, so every fresh worktree and scrubbed export lacks it and each ts-morph / PGlite keeper
failed on its own (N>=4 on 2026-11-14/15: the silent-refusal scanner refused two merge commits, polling-budget went red on a never-installed primary).
Do not resolve it per keeper. `mcp/noctusai/node_toolchain.py` (stdlib only) is the single answer:

1. the worktree's own `node_modules` when it carries every required package (`require=`, default `ts-morph`);
2. else another checkout's install (the primary via git-common-dir, the checkout owning the interpreter's venv, this toolkit's own tree, or explicit `sources=`) **only when its `package-lock.json` is byte-identical** - symlinked in (gitignored) or, if the link cannot be made, borrowed through `Toolchain.invocation`;
3. else a loud `Toolchain.reason` naming the exact `npm ci --prefix <worktree>/mcp/noctusai/node`. The caller reports UNMEASURED or refuses with it; a mismatched install is never borrowed silently.

Consumers: the four `compliance.py` AST scans (silent-refusal, motion-import, lying-loading Mode B, module-page-keys) and `polling_request_budget` via
`node_toolchain.run_files_scan`; `ts_ast_edit`, `migration_replay` (`require=@electric-sql/pglite`) and `release_steward.link_pglite` via `resolve`;
`task_branch` `wire_env` refuses to link a toolkit install whose lockfile differs (`node_toolchain.lockfile_verdict`). A new node-backed keeper calls the resolver; a hand-rolled `subprocess.run(["node", ...])` is the shape this section retires (test: `test_node_toolchain.py::TestEveryKeeperUsesTheSharedResolver`).


### 10a. Fresh worktrees are provisioned by construction; tool output is capped by construction (2026-11-15)

- **Node toolchain.** `node_toolchain.provision` = `resolve` + a LOUD `npm ci --prefix` when there is no lockfile-identical install to link (a `node_modules` symlink is removed first - `npm ci` would otherwise wipe the primary's install through it). `task_branch` `wire_env` plans a `node_install` spec instead of skipping; the harness's agent worktrees get the same via `scripts/hooks/claude-wire-worktree-toolchain.py` (SessionStart + SubagentStart; link-only for sibling trees). Closes `NOC-REMEDIATE[worktree-pglite-node-modules]`.
- **`NOC_REQUIRE_REAL_PG=1` fails, never skips.** Every PGlite fixture path goes through `noctusai_lib.testing.pglite` (`pglite_available`, `pglite_replay_skipif`, `real_pg_required`); a module that drives `replay.mjs` directly uses `pytest.mark.skipif(**pglite_replay_skipif())`, never a hand-rolled `shutil.which` expression.
- **Stale pre-push.** The hook carries `# NOC-HOOK-STAMP` / `# NOC-HOOK-LEGS`; an installed copy older than the tree's hands the push to the tree's hook (once) or prints `NOC-REMEDIATE[hook-leg-absent-loud]` naming the absent legs. Bump the stamp with every new leg. Closes `NOC-REMEDIATE[hook-leg-absent-loud]`.
- **Output cap.** `tool_output_cap.install_output_cap(server)` (after `install_strict_tool_arguments`): a result over ~50k chars becomes a summary + `full_output_path` (full JSON under `~/.noctus/tool-output`, newest 50 kept). `session_end_sweep` also returns a compact form itself (`verbose=true` for the raw). Closes `NOC-REMEDIATE[tool-output-cap]`.

## 11. Every outbound HTTP call has a timeout - ONE helper (`tools/noctus/dev/_http.py`)

A per-socket timeout bounds one `recv`, never the call: a peer that dribbles bytes or holds a half-closed (CLOSE_WAIT) socket resets it forever.
`migrate_product --confirm` hung 45 min that way after applying its DDL and died before writing `migrations-applied.json` (N=2; N=1 2026-11-13 held a
heavy slot 80 min). The construction, not a reminder:

- `_http.urlopen_read(req, call_site=...)` (urllib) and `_http.client_timeout()` (httpx) give explicit connect/read timeouts (env `NOC_HTTP_CONNECT_TIMEOUT_S` 10,
  `NOC_HTTP_READ_TIMEOUT_S` 60), a **total** deadline per attempt (`NOC_HTTP_TOTAL_DEADLINE_S` 120; the caller is released with `HttpDeadlineExceeded`, a `TimeoutError`),
  and ONE bounded retry on timeout / 502-504 / 429 (`idempotent=False` retries only provably-unsent failures; `retries=0` for liveness probes).
  A longer budget is declared at the call site (`read=`, `total=`), never by dropping the bound.
- A non-idempotent write whose response is lost is never re-sent blindly: re-READ the state, then decide (`migrate_product` confirms its ledger row by a SELECT
  before it reports `ledger_record_failed` with the exact `record_applied_migrations` command).
- Telemetry: every timeout / retry / terminal transport failure is one `kind=http-timeout` event (host, call site, elapsed, outcome) in the guard event log.
- `_http.py` is stdlib-only at import time (`prod_watchdog` / `mq_watchdog` run in CI with no pip).
- Backstop: keeper `check_http_call_without_timeout` (`--check-http-call-without-timeout`, AST, ratchet `mcp/noctusai/tests/http_timeout_baseline.json`, shrink-only;
  suppress with `# noc-allow: http-timeout -- <reason>`).

- **One GitHub-call seam (2026-11-16).** Repo code reaches GitHub only through `ci_verdict.RealGithubClient` (call counting, free `rate_limit` guard, ETag polling, 403 -> `RateLimited`); never `gh run watch` (it re-fetches run + jobs + annotations every tick and helped exhaust the shared REST quota). Keeper `check_gh_calls_via_seam`. Methodology: GitHub first, local slot when it is out of quota. -> `KB § PATTERNS/devops/hardware-admission-budget.md`
