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
    drive.py       # google.drive.{parse_url,get_metadata,download}
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

## Tools (10)

| Tool | Kind | Notes |
|---|---|---|
| `google.calendar.create_event` | WRITE | required `confirm=true` gate + structured audit log; OAuth adapter when configured, else Fake |
| `google.calendar.list_events` | read | no gate |
| `google.maps.travel_estimate` | read | Routes API v2 or Static fallback |
| `google.youtube.get_channel` | read | quota: 1 unit |
| `google.youtube.list_channel_videos` | read | quota: ~2 units / 50 videos — **~50× cheaper than `search.list`**; prefer for channel browsing |
| `google.youtube.get_video` | read | quota: 1 unit |
| `google.youtube.upload_video` | WRITE | `confirm=true` gate + audit; OAuth-only; **lib gap, see below** |
| `google.drive.parse_url` | pure | URL/id → file id (≥20-char id contract) |
| `google.drive.get_metadata` | read | null ⇒ missing OR inaccessible (Drive 404s both) |
| `google.drive.download` | read | streams bytes to a local path |

Every tool renders failures through `_kit.errors.typed_error`
(`{error_class, message, status}`).

## Confirm-then-execute (write safety)

`calendar.create_event` and `youtube.upload_video` require an explicit
`confirm: true`. Omitted/false ⇒ the side-effect is refused with a
typed `PermissionError` and Google state is left untouched
(`KB § PATTERNS/llm-bot-security.md`). Both also emit a structured
`google.audit` log line on the attempt + outcome.

## Seed-lib gaps surfaced at build (Wave-3 follow-ups)

Verified 2026-05-17 against `noctusai_lib.integrations.*` (`__init__`
exports + every adapter module):

1. **YouTube has no uploader.** The seed `YoutubeClient`
   Protocol / `FakeYoutubeClient` / `make_youtube_client` ship
   `get_channel` / `list_channel_videos` / `get_video` / `search`
   only — no upload method. `google.youtube.upload_video` is registered
   with the full WRITE contract (confirm gate + OAuth check + audit)
   but, once those pass, returns a typed `NotImplementedError` pointing
   at the gap. It NEVER fakes an upload success (no-silent-error). A
   real resumable-upload adapter (1600-quota `MediaFileUpload`) belongs
   in the seed lib, not in `mcp/` (no-connector-logic rule).

2. **Drive ships only the downloader, no reader.** The brief specified
   `google.drive.search` + `google.drive.read_file` via
   `make_drive_reader` (+ `compute_content_stats` for the LLM-recount
   trap) and `FakeDriveReader`. None of `make_drive_reader` /
   `FakeDriveReader` / `DriveReader` / `compute_content_stats` /
   `read_file` / `search` exist anywhere in
   `noctusai_lib.integrations.google_drive` — the `DriveDownloader`
   Protocol docstring itself states list/read are "explicitly out of
   scope until the second consumer arrives". Those two tools are
   therefore NOT registered (registering them would force a
   connector-side reader fork — wrong layer). `parse_url` /
   `get_metadata` / `download` ARE real and complete against the
   shipped Fake+Real downloader surface.

`gmail` is explicitly out of scope (no seed lib) and was not built.

## Run

```
python mcp/google/server.py                 # stdio server
python -m pytest mcp/google/tests/ -q       # 22 tests, deterministic, no network
```
