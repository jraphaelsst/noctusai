"""Vista CRM MCP server — typed Vista REST adapter exposed as MCP tools.

See `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` for the full Vista API
contract this package targets.

Package shape (Phase 1 — scaffold):
- settings.py      — per-tenant Vista config (VISTA_BASE_URL + VISTA_API_KEY)
- client.py        — typed VistaClient + 7-class error hierarchy + extract_items
- normalizers.py   — Vista payload → ShowcaseDTO mappers
- types.py         — Pydantic In/Out per tool + showcase DTOs
- calibration.py   — per-tenant field-set calibration routine (addresses §6)
- tools/           — vista.<service>.<action> MCP tools (hierarchical reg)
- server.py        — MCP stdio entry point
"""
__version__ = "0.1.0"
