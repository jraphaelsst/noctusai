# `mcp/google` — Google connector MCP server

Thin connector MCP exposing the four seed Google integration libs as
`google.<service>.<action>` tools. Composes `mcp/_kit` (shared
connector boilerplate) exactly like `mcp/vista`.

**No connector logic lives here.** Value objects, adapter selection,
the Google v3 mappings, OAuth credential kinds, and the YouTube quota
math all ship in `noctusai_lib.integrations.{google_calendar,
google_maps,youtube,google_drive}`. This package only (1) parses the
Pydantic input, (2) picks Fake vs Real via the lib factory, (3)
enforces the confirm-gate + audit log on writes, (4) shapes the output.

## Package shape

```
mcp/google/
  server.py        # _kit.bootstrap composition (stdio entry point)
  settings.py      # GoogleConnectorSettings(ConnectorSettings) — 5 env/.env fields
  schemas.py       # Pydantic In/Out per tool (named `schemas`, NOT `types` — see below)
  conftest.py      # pytest sys.path wiring (the `google` name collision — see below)
  pytest.ini       # --import-mode=importlib (same collision)
  tools/
    __init__.py    # build_registry(LEAF_MODULES)
    calendar.py    # google.calendar.{create_event,list_events}
    maps.py        # google.maps.travel_estimate
    youtube.py     # google.youtube.{get_channel,list_channel_videos,get_video,upload_video}
    drive.py       # google.drive.{parse_url,get_metadata,download,search,read_file}
  tests/test_smoke.py
  .env.example
```

### The `google` package-name collision (structural note)

Unlike `vista`, the directory name `google` collides with the PyPI
`google.*` **namespace package** shipped by `google-api-python-client`
/ `google-auth`. So this connector does NOT import its modules as a
`google.` package (that resolves to site-packages and fails). Instead —
exactly like `mcp/noctusai` — it puts its own dir on `sys.path` and
imports `tools` / `settings` / `schemas` as **top-level** modules.
`server.py` inserts two paths (order matters): `mcp/` (for `_kit`) then
`mcp/google/` (for the flat modules). Tests get the same wiring from
`conftest.py` + `--import-mode=importlib` (via `pytest.ini`'s `addopts`,
consumed before conftest collection).

The schema module is `schemas.py`, not `types.py`: a top-level
`types.py` cannot win over the already-loaded stdlib `types` module
under this flat-import strategy.

## Settings

Five fields, env or co-located `mcp/google/.env` (env wins; `.env`
gitignored — see `.env.example`):

| Field | Env var | Used by |
|---|---|---|
| `api_key` | `GOOGLE_API_KEY` | Drive (public files), YouTube read |
| `maps_api_key` | `GOOGLE_MAPS_API_KEY` | `maps.travel_estimate` |
| `oauth_client_id` | `GOOGLE_OAUTH_CLIENT_ID` | Calendar write, YouTube upload |
| `oauth_client_secret` | `GOOGLE_OAUTH_CLIENT_SECRET` | ″ |
| `oauth_refresh_token` | `GOOGLE_OAUTH_REFRESH_TOKEN` | ″ |

Deferred-config: the server starts with NONE set. Read tools then
resolve against the seed-lib Fakes (`adapter: "fake"` / `"static"`);
OAuth-only writes return a typed error.

## Tools (12)

| Tool | Kind | Notes |
|---|---|---|
| `google.calendar.create_event` | WRITE | required `confirm=true` gate + structured audit log; OAuth adapter when configured, else Fake |
| `google.calendar.list_events` | read | no gate |
| `google.maps.travel_estimate` | read | Routes API v2 or Static fallback |
| `google.youtube.get_channel` | read | quota: 1 unit |
| `google.youtube.list_channel_videos` | read | quota: ~2 units / 50 videos — **~50× cheaper than `search.list`**; prefer for channel browsing |
| `google.youtube.get_video` | read | quota: 1 unit |
| `google.youtube.upload_video` | WRITE | `confirm=true` gate + OAuth-trio check + audit; **REAL** against `YoutubeClient.upload_video` (resumable `videos.insert`, **1600 quota**); no OAuth ⇒ typed `PermissionError`, never a faked success |
| `google.drive.parse_url` | pure | URL/id → file id (≥20-char id contract) |
| `google.drive.get_metadata` | read | null ⇒ missing OR inaccessible (Drive 404s both) |
| `google.drive.download` | read | streams bytes to a local path |
| `google.drive.search` | read | `DriveReader` name+full-text search; hits carry `capabilities` + IMMUTABLE `web_view_link` |
| `google.drive.read_file` | read | `DriveReader` export/stream + `stats` from `compute_content_stats` — the LLM-recount-trap defense; binary types deferred to the media seam |

Every tool renders failures through `_kit.errors.typed_error`
(`{error_class, message, status}`).

## Confirm-then-execute (write safety)

`calendar.create_event` and `youtube.upload_video` require an explicit
`confirm: true`. Omitted/false ⇒ the side-effect is refused with a
typed `PermissionError` and Google state is left untouched
(`KB § PATTERNS/llm-bot-security.md`). Both also emit a structured
`google.audit` log line on the attempt + outcome.

## Seed-lib coverage (verified 2026-05-18, post-absorption base)

All 12 tools are REAL against shipped `noctusai_lib.integrations.*`
Fake+Real+factory surfaces — no stubs, no `NotImplementedError`:

1. **YouTube upload is real.** The seed `YoutubeClient.upload_video`
   (Protocol + `FakeYoutubeClient` recording `.uploaded` +
   `RealYoutubeClient` resumable `videos.insert` + `make_youtube_client`
   factory) ships on this base. `google.youtube.upload_video` keeps the
   WRITE contract — `confirm=true` gate → OAuth-trio check → build the
   `google.oauth2.credentials.Credentials`-backed client → upload →
   shape — and emits `google.audit` lines on attempt + outcome. No
   OAuth ⇒ typed `PermissionError` (an API key cannot authorize
   uploads); NEVER a faked success.

2. **Drive reader is real.** The sibling `DriveReader` surface
   (`make_drive_reader` / `FakeDriveReader` / `DriveReader` /
   `DriveSearchResult` / `DriveFileContent` / `compute_content_stats`,
   added 2026-05-16 by the social-wiring absorption Wave 1.E3) backs
   `google.drive.search` + `google.drive.read_file`. `read_file`
   attaches `compute_content_stats(...)` as `stats` (the
   LLM-recount-trap defense; binary types are NOT decoded — deferred to
   the media seam). The download surface (`parse_url` / `get_metadata`
   / `download`) is the other sibling Protocol, untouched.

`gmail` is explicitly out of scope (no seed lib) and was not built.

### In-tree `noctusai_lib` resolution (structural note)

A repo-wide editable install (`pip install -e seed/lib/backend`)
registers a `_EditableFinder` on `sys.meta_path` that hard-pins
`noctusai_lib` to whatever worktree it was last installed from — which,
in a multi-worktree agent setup, may be a *different* (now-stale)
`.claude/worktrees/agent-*` tree missing a freshly-added seed symbol.
`sys.meta_path` is consulted BEFORE `sys.path`, so a plain
`sys.path.insert` cannot override it. `server.py` and `conftest.py`
therefore call the shared `_kit.seed_pin.pin_in_tree_seed` primitive,
which evicts any editable finder whose pinned `noctusai_lib` path is
OUTSIDE this tree, drops stale cached `noctusai_lib*` modules, and
prepends this tree's `seed/lib/backend`. (This was hand-rolled inline
until the N=2 dedup wave landed it in `_kit.seed_pin`; both files now
compose the shared helper.) Pure import wiring — same category as the
`google`-namespace flat-import trick; touches no product code. A
connector must run/test against the seed in its own tree.

## Run

```
python mcp/google/server.py                 # stdio server
python -m pytest mcp/google/tests/ -q       # 27 tests, deterministic, no network
```
