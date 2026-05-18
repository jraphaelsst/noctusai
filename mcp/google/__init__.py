"""Google connector MCP server — thin wrappers over the seed Google
integration libs (`noctusai_lib.integrations.{google_calendar,
google_maps,youtube,google_drive}`) exposed as MCP tools.

NO connector logic lives in this package — value objects, adapter
selection, the Google v3 mappings, and the quota math all ship in the
seed lib. This package only composes `_kit` plumbing + the lib factories.

Package shape (mirrors mcp/vista; flat-imported, NOT a `google.`
package — the name collides with the PyPI `google.*` namespace so
modules resolve top-level via `mcp/google/` on sys.path, like
mcp/noctusai):
- settings.py      — GoogleConnectorSettings (5 env/.env fields)
- schemas.py       — Pydantic In/Out per tool (named `schemas`, not
                     `types`, to avoid shadowing the stdlib `types`)
- tools/           — google.<service>.<action> tools (calendar/maps/youtube/drive)
- server.py        — MCP stdio entry point (composes _kit.bootstrap)

Lib gaps surfaced at build time (Wave-3 seed-lib follow-ups):
- youtube: seed client ships no `upload_video` (read methods only).
- drive: seed ships only the downloader surface — no reader
  (`make_drive_reader` / `read_file` / `search` / `compute_content_stats`).
See README.md for detail.
"""
__version__ = "0.1.0"
