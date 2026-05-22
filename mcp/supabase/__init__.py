"""Supabase Management API connector MCP package.

Imports as a TOP-LEVEL package `supabase` (the PyPI `mcp` package shadows
our `mcp/` dir, so `_kit.bootstrap.prepare_sys_path` puts `mcp/` on
`sys.path` and we import this as `supabase`, the kit as `_kit` — the same
trick every connector under `mcp/` uses). Mirrors `mcp/cloudflare`.
"""
