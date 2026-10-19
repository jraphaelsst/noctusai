"""Qualification standard + deterministic engine (Julia v2 CONTRACT §3).

``imob-lead`` is ONE platform standard (owner decision 2026-10-19, Q2): no org
fork, no "Personalizar". The model only records criteria values through tools;
score and stage are COMPUTED here by pure functions (``engine.calcular``).

Layers (each importable on its own):

* ``models``    — frozen dataclasses (standard version, records, events, state).
* ``regras``    — the closed predicate DSL: evaluate, collect references, validate.
* ``engine``    — ``calcular`` / ``validar_valor``: pure, no IO.
* ``matcher``   — the ``trecho`` (literal quote) matcher: pure.
* ``store`` / ``lead_store`` — Protocol + Fake + Real + factory.
* ``service``   — the API the channel tools call (typed results, codes only).
"""
