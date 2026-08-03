"""Vista CRM MCP server — typed Vista REST adapter exposed as MCP tools.

See `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` for the full Vista API
contract this package targets.

Package shape:
- settings.py      — per-tenant Vista config (VISTA_BASE_URL + VISTA_API_KEY)
- types.py         — Pydantic In/Out per tool
- tools/           — vista.<service>.<action> MCP tools (hierarchical reg)
- server.py        — MCP stdio entry point

Imported from the seed, never forked here — `noctusai_lib.integrations.vista`
owns the transport and the domain mapping:
- `VistaClient` + the 7-class error hierarchy + `extract_items`
- `vista_*_to_showcase` normalizers + the `Showcase*` DTOs
- `calibrator` — per-tenant field-set calibration (vista.md § 6)

`client.py` / `normalizers.py` moved to the seed in `b3e0b10f`;
`calibration.py` followed 2026-08-03 so backend consumers could calibrate
too (roadmap `social-wiring-imoveis-vista-2026-08`, P2.0a).
"""
__version__ = "0.1.0"
