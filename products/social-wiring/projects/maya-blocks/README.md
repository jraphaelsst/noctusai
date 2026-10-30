# maya-blocks — the atendimento as blocks, supervised by Maya

The owner's model (2026-10-19): the real-estate atendimento is split into blocks — `sdr`
(Julia, studio agent `lead-imob`), `atendimento` (the broker), `negociacao`, `juridico`,
`financeiro`, `contador` — each with one accountable specialist (an agent or humans). A
handoff records the moment a lead/card crosses from one block to the next. Maya watches every
block, scores each specialist daily, and reports to the owner.

- **Contract:** [CONTRACT.md](CONTRACT.md) — blocks + default stage map, handoff schema/status
  machine/triggers, scorecard metrics with formulas and sources, API shapes, safety rules.
- **Schema:** `backend/migrations/286_atendimento_blocos_supervisao.sql` (page rows promoted to `producao` by `311_status_pagina_leftovers.sql`).
- **Guards:** `_SW_MAYA_BLOCOS_PROBES` in `mcp/noctusai/tools/noctus/dev/verify_db_guards.py`,
  proven on the real chain by `mcp/noctusai/tests/test_sw_maya_blocos_probes_on_replay.py`.

Status: S0 (contract), S1 (schema), S2 (backend `backend/app/modules/atendimento_blocos/`), S3 (jobs + owner routes, `backend/app/modules/supervisao/`) and S4 (FE pages `/atendimento-blocos` + `/supervisao`) are done. Everything is OFF by
default and nothing here sends anything to a lead.
