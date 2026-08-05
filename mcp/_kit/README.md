# `mcp/_kit` — shared connector-MCP boilerplate

## What this is

The platform's **connector MCP servers** — `mcp/vista` today, `mcp/meta`
and `mcp/google` next — all share the same stdio bootstrap, per-tenant
settings pattern, tool-registry aggregation, and error envelope. Three
connectors sharing one boilerplate is N=3 ⇒ formalized here (DRY
recurrence rule) so the 3rd connector **composes the kit** instead of
copy-pasting vista.

`mcp/_kit` is a connector-MCP support package. It is **not** a product,
**not** part of `noctusai_lib`, and **not** the `mcp/noctusai` dev
toolkit — it is private plumbing shared only by the `mcp/<vendor>`
connector servers.

## Public surface (`from _kit import ...`)

| Symbol | From | Job |
|---|---|---|
| `ConnectorSettings` | `_kit.settings` | Marker base for a connector's frozen-dataclass settings carrier. |
| `make_get_settings(cls, *, dotenv_dir, env_map)` | `_kit.settings` | Builds the process-cached `get_settings()` (env wins over co-located `.env`). |
| `build_registry(leaf_modules)` | `_kit.registry` | `(all_handlers, all_descriptors, register_all)` from the leaf-module contract. |
| `typed_error(e)` | `_kit.errors` | 3-key JSON error payload `{error_class, message, status}` for tool-handler internals. |
| `confirmation_required_message(action, effect="", *, noun="write action")` | `_kit.errors` | The standard confirm-then-execute message; each connector keeps its own `ConfirmationRequiredError` subclass but builds the message here. |
| `request_json(method, url, *, auth_header, user_agent, params, body, timeout, error_cls, empty_result, label, on_http_error)` | `_kit.transport` | The shared stdlib-`urllib` HTTP boundary — connectors delegate transport mechanics here (see § Shared HTTP transport seam). |
| `normalize_base_url(raw)` | `_kit.transport` | Trim trailing slashes; connectors needing a path suffix (n8n's `/api/v1`) wrap it. |
| `BROWSER_USER_AGENT` / `DEFAULT_USER_AGENT` | `_kit.transport` | Browser UA (clears the Cloudflare WAF on WAF-fronted hosts) / the plain default UA. |
| `ConnectorHttpError` | `_kit.transport` | Default typed error for the seam; a connector passes its OWN `<Vendor>ApiError` as `error_cls`. |
| `prepare_sys_path(server_file)` | `_kit.bootstrap` | Inserts `mcp/` on `sys.path` (PyPI-`mcp`-shadow trick) **then** pins the in-tree seed. |
| `pin_in_tree_seed(start)` | `_kit.seed_pin` | Evicts stale editable-install `noctusai_lib` pins; prepends this worktree's `seed/lib/backend`. |
| `configure_stderr_logging(name)` | `_kit.bootstrap` | stderr logging (stdout is JSON-RPC); returns the logger. |
| `run_stdio_server(name, descriptors, handlers, logger)` | `_kit.bootstrap` | The `Server` + `@list_tools` + `@call_tool` + run loop. |

## The canonical connector-MCP shape

A connector MCP `mcp/<vendor>/` is:

```
mcp/<vendor>/
  server.py            # bare sys.path insert → _kit bootstrap composition
  settings.py          # frozen <Vendor>Settings(ConnectorSettings) + make_get_settings
  tools/
    __init__.py        # build_registry(LEAF_MODULES)
    <resource>.py      # HANDLERS / tool_descriptors() / register(server)
  tests/test_smoke.py  # package imports + registry trio coherence
  README.md
```

Each **leaf tool module** must export the uniform contract:
- `HANDLERS: dict[str, async-handler]` — keys are `vendor.<service>.<action>` (3-segment dotted).
- `tool_descriptors() -> list[Tool]`.
- `register(server) -> ...` — compatibility hook (servers use the aggregated handlers/descriptors).

Vendor-private logic (vista's `calibration.py`, per-resource normalizers)
stays connector-side — the kit only owns the *generic* plumbing.

## How a new `mcp/<vendor>` composes the kit

**1. `settings.py`**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from _kit.settings import ConnectorSettings, make_get_settings

@dataclass(frozen=True)
class MetaSettings(ConnectorSettings):
    access_token: Optional[str] = None
    app_secret: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.access_token)

get_settings = make_get_settings(
    MetaSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={"access_token": "META_ACCESS_TOKEN", "app_secret": "META_APP_SECRET"},
)
```

`env_map` only lists fields read from env/`.env`; fields with pure
dataclass defaults (e.g. vista's `timeout_seconds`) are omitted and keep
their default. Resolution per field: `os.environ.get(ENV) or dot.get(ENV)`.

**2. `tools/__init__.py`**

```python
from _kit.registry import build_registry
from . import resource_a, resource_b

LEAF_MODULES = (resource_a, resource_b)
all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)
__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
```

**3. `server.py`**

```python
import asyncio, sys
from pathlib import Path

# Bare insert FIRST — before any `_kit` / `<vendor>` import. (PyPI `mcp`
# shadows our `mcp/` dir; we import the package as top-level instead.)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _kit.bootstrap import configure_stderr_logging, run_stdio_server
logger = configure_stderr_logging("<vendor>-mcp")

from <vendor>.tools import all_descriptors, all_handlers
_DESCRIPTORS = all_descriptors()
_HANDLERS = all_handlers()

async def _main():
    await run_stdio_server("<vendor>", _DESCRIPTORS, _HANDLERS, logger)

if __name__ == "__main__":
    asyncio.run(_main())
```

The bare `sys.path.insert` must precede the first `_kit` import (the
script's own dir is `sys.path[0]` when run as `python mcp/<vendor>/server.py`,
not `mcp/`). `_kit.bootstrap.prepare_sys_path(server_file)` is the same
insert as a reusable primitive for connectors whose entrypoint differs.

## Error envelope contract

`typed_error(e)` is the **3-key** payload `{error_class, message,
status}` used INSIDE tool handlers (nested as `{"error": typed_error(e)}`
in the tool's own result). The **server-level** catch-all inside
`run_stdio_server` deliberately emits the **2-key** shape
`{error_class, message}` — this matches vista's original server-level
behavior exactly (zero-behavior-change contract). Do not collapse the
two; they are different surfaces with different consumers.

## Shared HTTP transport seam (`_kit.transport.request_json`)

### Why

Five connectors (`n8n`, `waha`, `hostinger`, `cloudflare`, `supabase`)
each hand-rolled a near-identical stdlib-`urllib` `request_json`
(params-encode → header-build → `urlopen` → `HTTPError`/`URLError`/
`TimeoutError`/non-JSON typing). **N=5 ⇒ formalized** here per the DRY
recurrence rule, so a connector's `api.py` shrinks to: its own
`<Vendor>ApiError` type + the not-configured (424) gate + base-URL
normalizer + (rarely) response-envelope handling — and **delegates the
urllib mechanics** to `_kit.transport.request_json`.

Named `transport` (NOT `http`) on purpose: a module called `http.py`
shadows the stdlib `http` package the moment `mcp/_kit/` lands on
`sys.path` (urllib's `import http.client` then finds it → circular
import).

### The per-connector consume recipe (proven across 4 connectors)

A connector's `api.py` `request_json` wrapper:

```python
from _kit.errors import confirmation_required_message
from _kit.transport import request_json as _http_request_json
# + `from _kit.transport import BROWSER_USER_AGENT` if the host is WAF-fronted

def request_json(method, path, *, <creds>, base_url="", params=None, body=None, timeout=20.0):
    if not <creds>:                       # the connector-specific 424 gate stays here
        raise <Vendor>ApiError("... not configured ...", status=424)
    url = f"{normalize_base_url(base_url)}{path}"   # connector's own normalizer
    return _http_request_json(
        method, url,
        auth_header=("Authorization", f"Bearer {tok}"),   # or ("X-Api-Key", key) / ("X-N8N-API-KEY", key)
        user_agent=BROWSER_USER_AGENT,    # omit (defaults) for non-WAF hosts
        params=params, body=body, timeout=timeout,
        error_cls=<Vendor>ApiError,       # your typed error — raised (with status) on ANY failure
        empty_result={},                  # {} (n8n/waha/hostinger) or None (supabase) on an empty 2xx body
        label=f"<Vendor> API {method.upper()} {path}",
    )
```

`ConfirmationRequiredError(action[, effect])` builds its message via
`confirmation_required_message(action, effect, noun=...)` (the connector
keeps its own subclass so its `<Vendor>ApiError` identity + the 412
status are preserved).

**Test seam.** Tests that mock the *wrapper* patch
`"<vendor>.api.request_json"` (zero churn). Tests that inspect the
*Request* (headers / URL / HTTP-error typing) patch the shared boundary
`"_kit.transport.urlopen"` — an external-boundary patch (sanctioned by
`CLAUDE.md §1`); our own code is never patched.

### Vendor error-body hook — `on_http_error` (the N=2 formalization)

`on_http_error(status, body, tag) -> Exception | None` is called on an
`HTTPError` **before** the default raise. Return an exception to raise it
instead; return `None` to fall through to `error_cls(...)`. Default
`None` ⇒ byte-for-byte prior behavior for connectors that don't pass it.

It exists because two vendors carry their real error identity in the
response *body*, not the status:

```python
# mcp/omie/api.py — Omie answers failures with {"faultstring", "faultcode"}
on_http_error=lambda st, bd, tg: fault_from_body(bd, http_status=st, tag=tg)
```

**History.** cloudflare was N=1 and was accepted-with-rationale below;
omie's `faultstring`/`faultcode` is **N=2**, which this README named as
the revisit trigger — so the hook is now formalized here rather than
hand-rolled a second time.

### The remaining exception — cloudflare

`mcp/cloudflare/api.py` still keeps its **own** transport (does NOT
delegate). Its `request_envelope` extracts the Cloudflare
`errors[0].code` from the HTTP-error body and attaches it as a typed
`CloudflareApiError.cf_code` — the exact need `on_http_error` now serves.

> **Open follow-up.** With the hook in place cloudflare can fold onto the
> shared seam, which would close its entry in
> `KB § PATTERNS/accept-with-rationale.md`. Not done in the omie branch
> deliberately — it touches a fleet-facing connector and deserves its own
> slice with its own regression run.

## In-tree seed pin (`_kit.seed_pin.pin_in_tree_seed`)

### Why

The repo installs `noctusai_lib` editable
(`pip install -e seed/lib/backend`). An editable install registers an
`_EditableFinder` on `sys.meta_path` that **hard-pins** `noctusai_lib`
to whatever worktree `pip install -e` last ran in. In a multi-agent
setup that pinned path is frequently a *different, now-stale*
`.claude/worktrees/agent-*` tree — one predating a post-absorption
package (e.g. `noctusai_lib.integrations.meta`). Because `sys.meta_path`
finders are consulted **before** `sys.path`, a plain
`sys.path.insert(0, <in-tree seed>)` **cannot** override the stale pin:
imports silently resolve against the wrong tree and fail on
freshly-added symbols.

This was hand-rolled independently by two connectors (`mcp/google`'s
`conftest.py` + `server.py`; `mcp/meta`'s `tests/test_smoke.py`).
**N=2 → DRY recurrence rule → formalized** as `_kit.seed_pin` so vista
and every future connector inherit the fix by construction.

### Connector servers/tests get it FREE via `_kit`

`prepare_sys_path(server_file)` (called by every connector `server.py`
as step 1) now also calls `pin_in_tree_seed(server_file)` **after** the
`mcp/` insert and **before** any `noctusai_lib` import. So a connector
that composes the kit does **nothing** — the pin is automatic. Do not
re-hand-roll it; do not import `noctusai_lib` ahead of `prepare_sys_path`.

`pin_in_tree_seed(start)` walks up from `start` to the worktree root
(marker: a dir with both `.git` and `seed/lib/backend`), evicts any
meta-path finder whose resolved `noctusai_lib` location is **outside**
that root (editable-mapping inspection, with an `_EditableFinder`-by-name
fallback), purges cached `noctusai_lib*` / `noctusai_seed*` modules, and
prepends the in-tree `seed/lib/backend`. Idempotent; logs at DEBUG;
returns the resolved seed path. The standalone helper **raises** if no
in-tree seed exists (the caller asserted one must); `prepare_sys_path`
wraps it and degrades to a **WARNING** (no seed ⇒ nothing to pin ⇒
not an error) so the kit stays usable in seed-less layouts.

It is **not** a monkeypatch — no function/class is replaced; it corrects
a mis-pointed package *locator* (the "codebase is source of truth" rule
applied to import resolution).

> **Cleanup wave — DONE (branch `seed-pin-dedup`, 2026-05-18).** The
> per-connector hand-rolled copies in `mcp/google/{server.py,conftest.py}`
> and `mcp/meta/tests/test_smoke.py` are **removed**; all three sites now
> compose `from _kit.seed_pin import pin_in_tree_seed`. No connector
> retains a local copy of this logic. (Triage flipped `[A]→[F]` in
> `KB § PATTERNS/accept-with-rationale.md`.)

## Namespace-collision recipe (when `mcp/<vendor>` shadows an installed package)

Most connectors (`vista`, `meta`) only contend with the PyPI `mcp`
package shadowing our `mcp/` dir — solved by the single bare
`sys.path.insert(0, .../mcp)` so the connector imports as a clean
top-level package (`vista`, `meta`).

`mcp/google` hit a **second** collision: the dir name `google` collides
with the PyPI `google.*` **namespace package** (shipped by
`google-api-python-client` / `google-auth`). When a `mcp/<vendor>` dir
name collides with an installed top-level OR namespace package, follow
the `mcp/google` recipe:

1. **Dual `sys.path` inserts** — `mcp/` (for `_kit`) **and** `mcp/<vendor>/`
   (so the connector's own `tools` / `settings` / `schemas` resolve as
   **flat top-level** modules, NOT as a `<vendor>.` package that would
   resolve to site-packages).
2. **Flat top-level imports inside the connector** — `from tools import …`,
   `from settings import …` (never `from google.tools import …`), same
   self-dir-on-path strategy `mcp/noctusai` uses.
3. **`--import-mode=importlib`** in the connector's `pytest.ini` — stops
   pytest's default prepend import-mode from synthesizing the colliding
   `<vendor>.tests.test_*` package path for test files.
4. **Avoid stdlib-shadowing module names** — never name a connector
   module `types.py` / `json.py` / etc. when it sits on `sys.path[0]` as
   a flat top-level dir (it would shadow the stdlib for the whole
   process). `mcp/google` uses `schemas.py`, not `types.py`, for exactly
   this reason (contrast `mcp/vista/types.py`, safe because vista is
   imported as the `vista.` package, not flat).

`mcp/google/conftest.py` + `pytest.ini` are the reference implementation.

## Tests

`mcp/_kit/tests/test_kit.py` — settings env-vs-dotenv precedence +
caching, registry trio aggregation, `typed_error` shape, bootstrap
importability without the PyPI `mcp` package, and `seed_pin`
(out-of-tree finder eviction / in-tree finder kept / cached-module
purge / idempotency / no-mapping name-fallback). Run:

```
cd mcp && python -m pytest _kit/tests/ -q
```

`mcp/_kit/tests/test_http.py` — the shared transport seam: auth-header
injection, browser-vs-default UA, `None`-param dropping, `empty_result`
on an empty 2xx body, and the typed-error mapping (`HTTPError` →
upstream status; `URLError`/`TimeoutError`/non-JSON → 502) — patching
`_kit.transport.urlopen`.

Each connector additionally keeps its own `tests/test_smoke.py` proving
the composition resolves (`mcp/vista/tests/` is the reference).
