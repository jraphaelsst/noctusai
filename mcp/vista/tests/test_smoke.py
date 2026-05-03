"""Smoke tests — verify the package imports cleanly and tools register.

These do NOT touch the Vista network. Live-probe tests belong in Phase 5
(keeper-side; see PROJECT.md §6).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from vista.X import ...` resolves. Same trick
# `mcp/noctusai/tests/*.py` uses for its `from tools.X import Y` imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest


def test_package_imports():
    from vista import types, calibration, settings  # noqa: F401
    # Vista client + normalizers live in noctusai_lib.integrations.vista (FORMALIZED 2026-05-03)
    from noctusai_lib.integrations import vista as vista_seed  # noqa: F401


def test_client_lenient_construction_with_no_config():
    """Per vista.md § 1: __init__ must not raise on missing config."""
    from noctusai_lib.integrations.vista import VistaClient

    c = VistaClient(None, None)
    assert c.configured is False
    assert c.base_url == ""


def test_extract_items_handles_non_dict():
    from noctusai_lib.integrations.vista import extract_items

    items, pag = extract_items("not a dict")  # type: ignore[arg-type]
    assert items == []
    assert pag == {}


def test_extract_items_splits_envelope_correctly():
    from noctusai_lib.integrations.vista import extract_items

    payload = {
        "CA2830": {"Codigo": "CA2830", "Cidade": "Cotia"},
        "TE0080": {"Codigo": "TE0080", "Cidade": "Cotia"},
        "total": 1783,
        "paginas": 595,
        "pagina": 1,
        "quantidade": 2,
    }
    items, pag = extract_items(payload)
    assert len(items) == 2
    assert pag == {"total": 1783, "paginas": 595, "pagina": 1, "quantidade": 2}


def test_error_hierarchy_inheritance():
    """Catch-order rule (vista.md § 3) requires correct inheritance."""
    from noctusai_lib.integrations.vista import (
        VistaError,
        VistaConfigError,
        VistaUpstreamError,
        VistaPermissionDenied,
        VistaNotFound,
        VistaFieldNotAvailable,
        VistaTimeout,
    )

    assert issubclass(VistaConfigError, VistaError)
    assert issubclass(VistaTimeout, VistaError)
    assert issubclass(VistaUpstreamError, VistaError)
    assert issubclass(VistaPermissionDenied, VistaUpstreamError)
    assert issubclass(VistaNotFound, VistaUpstreamError)
    assert issubclass(VistaFieldNotAvailable, VistaUpstreamError)


def test_first_corretor_nome_walks_both_shapes():
    from noctusai_lib.integrations.vista.normalizers import _first_corretor_nome

    nested = {"Corretor": {"103": {"Nome": "Fernanda"}, "104": {"Nome": "Elisa"}}}
    assert _first_corretor_nome(nested) == "Fernanda"

    flat = {"Corretor": {"Nome": "Solo"}}
    assert _first_corretor_nome(flat) == "Solo"

    missing = {"Corretor": None}
    assert _first_corretor_nome(missing) is None


def test_normalizer_uses_per_tenant_fallbacks():
    """vista.md § 5.2: estado falls back UF→Estado, foto_url falls back Foto→FotoDestaque."""
    from noctusai_lib.integrations.vista import vista_imovel_to_showcase

    payload = {
        "Codigo": "X1",
        "UF": "SP",
        "BanheiroSocial": "Sim",
        "FotoDestaque": "https://example.com/photo.jpg",
    }
    dto = vista_imovel_to_showcase(payload)
    assert dto.estado == "SP"
    # `BanheiroSocial="Sim"` does NOT parse to int — the int coercer returns None
    # (Vista has tenants where `Banheiros` is a count int and others where
    # `BanheiroSocial` is a Sim/Nao boolean shape; we accept both at request
    # time but the int coercion only fires on a numeric value).
    assert dto.banheiros is None
    assert dto.foto_url == "https://example.com/photo.jpg"


def test_to_float_collapses_zero_and_empty():
    """vista.md § 5.2 type-coercion rules: empty/None → None; 0/'0' → 0.0."""
    from noctusai_lib.integrations.vista.normalizers import _to_float

    assert _to_float(None) is None
    assert _to_float("") is None
    assert _to_float("0") == 0.0
    assert _to_float(0) == 0.0
    assert _to_float("250000,50") == 250000.50  # comma decimal separator
    assert _to_float("not a number") is None


def test_all_handlers_aggregates_every_leaf():
    """Every tool advertised in tool_descriptors() must have a handler."""
    from vista.tools import all_descriptors, all_handlers

    descriptors = all_descriptors()
    handlers = all_handlers()
    descriptor_names = {d.name for d in descriptors}
    handler_names = set(handlers.keys())
    assert descriptor_names == handler_names, (
        f"mismatch — descriptors only: {descriptor_names - handler_names}; "
        f"handlers only: {handler_names - descriptor_names}"
    )


def test_dotted_naming_convention():
    """KB § PATTERNS/mcp-tool-conventions.md § 1: 3-segment dotted names."""
    from vista.tools import all_handlers

    for name in all_handlers().keys():
        parts = name.split(".")
        assert len(parts) == 3, f"tool {name!r} not 3-segment dotted"
        assert parts[0] == "vista", f"tool {name!r} not under vista.* umbrella"


def test_detect_unavailable_field_handles_json_escaped_body():
    """Regression: Vista's wire body uses unicode escapes for non-ASCII
    chars (`n\\u00e3o est\\u00e1 dispon\\u00edvel`). A naive substring
    match against the raw body misses every real 400 — must JSON-parse
    first. See vista.md § 3.3 + the 2026-05-03 live-check finding."""
    from noctusai_lib.integrations.vista.client import _detect_unavailable_field

    # Real Vista 400 body, array-shaped message, JSON-escaped:
    body = (
        '{"status":400,"message":["Campo Estado n\\u00e3o est\\u00e1 '
        'dispon\\u00edvel. Consulte a documenta\\u00e7\\u00e3o..."]}'
    )
    matched, field = _detect_unavailable_field(body)
    assert matched is True
    assert field == "Estado"

    # String-shaped message (other Vista endpoints):
    body2 = '{"status":400,"message":"Campo Slug n\\u00e3o est\\u00e1 dispon\\u00edvel"}'
    matched2, field2 = _detect_unavailable_field(body2)
    assert matched2 is True
    assert field2 == "Slug"

    # Plain-text body (defensive fallback):
    body3 = "Campo Foto não está disponível para este tenant"
    matched3, field3 = _detect_unavailable_field(body3)
    assert matched3 is True
    assert field3 == "Foto"

    # Negative — different 400, e.g. listarConteudo "filter by code" error:
    body4 = '{"status":400,"message":"N\\u00e3o \\u00e9 poss\\u00edvel filtrar por c\\u00f3digo nesse endpoint."}'
    matched4, _ = _detect_unavailable_field(body4)
    assert matched4 is False


def test_calibrator_returns_floor_when_unconfigured():
    """No-config probe should fall back to FLOOR_FIELDS, not crash."""
    import asyncio
    from vista.calibration import calibrator, FLOOR_FIELDS
    from noctusai_lib.integrations.vista import VistaClient

    calibrator.reset()
    client = VistaClient(None, None)
    fields = asyncio.run(calibrator.get_imovel_list_fields(client))
    assert fields == FLOOR_FIELDS
    # Should NOT have cached the floor result (so the next call after
    # config is added re-probes properly).
    assert calibrator.snapshot() == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
