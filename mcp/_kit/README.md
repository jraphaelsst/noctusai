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
| `prepare_sys_path(server_file)` | `_kit.bootstrap` | Inserts `mcp/` on `sys.path` (the PyPI-`mcp`-shadow trick). |
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

## Tests

`mcp/_kit/tests/test_kit.py` — settings env-vs-dotenv precedence +
caching, registry trio aggregation, `typed_error` shape, bootstrap
importability without the PyPI `mcp` package. Run:

```
cd mcp && python -m pytest _kit/tests/ -q
```

Each connector additionally keeps its own `tests/test_smoke.py` proving
the composition resolves (`mcp/vista/tests/` is the reference).
