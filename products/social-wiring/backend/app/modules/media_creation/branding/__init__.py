"""Branding — the richer brand-kit model (database only).

A *branding* is a ``mc_brand_kits`` row that carries a whole design system:
structured ``tokens`` (the ``tokens.json`` shape), the brand book (markdown),
extra markdown ``sections``, ``mc_brand_components`` (guideline markdown +
sandboxed preview HTML) and uploaded assets (logos / post models / fonts, kept
in a PRIVATE bucket and listed through ``mc_brand_references``).

There is NO repo catalog: the former ``catalog/`` directory, its loader and the
``seed-catalog`` endpoint were deleted (owner decision 2026-10-05) — brandings
live in the database, edited in the app or imported from a design-system folder
(:mod:`.bundle`). Owners are BRANDS: a branding links to ``social_wiring.marcas``.

Modules
-------
* :mod:`.tokens_schema` — validates the ``tokens`` object server-side.
* :mod:`.html_guard`    — rejects unsafe component preview HTML on write.
* :mod:`.bundle`        — parses a design-system folder (files) into a bundle.
"""
