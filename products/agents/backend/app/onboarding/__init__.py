"""Client onboarding by interview (owner decision 2026-11-17): the checklist, the answer import, the apply step, and the
live interviewer.

Pure modules (``checklist``, ``importar``, ``aplicar``) plus the social-wiring settings port (``sw_settings``). The
interviewer (``onboarding-imob``) is conversational: ``entrevista`` holds its gates and per-item state (a fold of the
append-only ``onboarding_eventos`` ledger), ``ferramentas`` its four tools, ``fabrica`` the per-turn wiring, ``servico`` the
one apply entry point it shares with the staff route.

Human-readable checklist: ``products/agents/projects/onboarding/CHECKLIST.md``.
"""
