"""Omie connector tests — package coherence, safety guards, catalog truth.

No network. The one external boundary (`_kit.transport.urlopen`) is
patched where a request path is exercised — our own code is never patched
(CLAUDE.md §1).

The load-bearing test here is `test_curated_methods_exist_in_catalog`:
every method name in `resources.RESOURCES` is verified against the
harvested catalog, so a typo or an upstream rename fails the suite
instead of failing live in a user's face.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Put `mcp/` on sys.path so `from omie.X import ...` and `from _kit.X import
# ...` resolve — same trick as mcp/vista/tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest


# --- package / registry coherence ------------------------------------------


def test_package_imports():
    from omie import api, catalog, errors, ratelimit, settings  # noqa: F401
    from omie.tools import all_descriptors, all_handlers  # noqa: F401


def test_registry_trio_is_coherent():
    """Every advertised tool has a handler, and vice versa."""
    from omie.tools import all_descriptors, all_handlers

    handlers = all_handlers()
    names = [d.name for d in all_descriptors()]
    assert len(names) == len(set(names)), "duplicate tool names"
    # Every advertised tool must be callable. (Handlers may be a superset —
    # the `core` profile narrows what is advertised, never what works.)
    assert not set(names) - set(handlers), set(names) - set(handlers)
    assert all(n.startswith("omie.") and n.count(".") == 2 for n in names), names


def test_core_profile_narrows_advertising_not_capability(monkeypatch):
    from omie import settings
    from omie.tools import all_descriptors, all_handlers

    monkeypatch.setattr(settings, "_DOTENV_DIR", Path("/nonexistent"))
    monkeypatch.setenv("OMIE_TOOL_PROFILE", "core")
    settings.get_settings.cache_clear()
    try:
        core = {d.name for d in all_descriptors()}
        assert core and all(
            n.split(".")[1] in {"environments", "catalog", "call", "diagnostics"}
            for n in core
        ), core
        # Capability is untouched: curated handlers remain callable.
        assert "omie.clientes.list" in all_handlers()
        assert "omie.call.invoke" in core  # all 461 methods still reachable
    finally:
        settings.get_settings.cache_clear()


def test_invalid_tool_profile_is_rejected(monkeypatch):
    from omie import settings
    from omie.errors import OmieConfigError

    monkeypatch.setattr(settings, "_DOTENV_DIR", Path("/nonexistent"))
    monkeypatch.setenv("OMIE_TOOL_PROFILE", "medium")
    settings.get_settings.cache_clear()
    try:
        with pytest.raises(OmieConfigError):
            settings.get_settings()
    finally:
        settings.get_settings.cache_clear()


def test_every_tool_advertises_environment_except_catalog():
    """Anything that can touch Omie must let the caller pick the company."""
    from omie.tools import all_descriptors

    for d in all_descriptors():
        if d.name.startswith("omie.catalog.") or d.name == "omie.environments.list":
            continue
        if d.name.startswith("omie.diagnostics."):
            continue
        assert "environment" in (d.inputSchema.get("properties") or {}), d.name


def test_write_tools_require_confirm():
    from omie.tools import all_descriptors

    for d in all_descriptors():
        if d.name.endswith((".upsert", ".delete")) or d.name == "omie.call.invoke":
            props = d.inputSchema.get("properties") or {}
            assert "confirm" in props, f"{d.name} missing confirm guard"


# --- catalog truth ----------------------------------------------------------


def test_catalog_loads_with_expected_shape():
    from omie import catalog

    s = catalog.status()
    assert s["endpoints"] == 134
    assert s["methods"] > 400
    assert s["complex_types"] > 1000
    assert set(s["families"]) == {
        "contador", "crm", "estoque", "financas", "geral", "produtos", "servicos"
    }


def test_catalog_paths_are_relative_to_base_url():
    """A path carrying `/api/v1` would double against base_url at request time."""
    from omie import catalog

    for ep in catalog.load()["endpoints"]:
        assert ep["path"].startswith("/"), ep["path"]
        assert not ep["path"].startswith("/api/"), ep["path"]
        assert ep["path"].endswith("/"), ep["path"]


def test_curated_methods_exist_in_catalog():
    """Every hand-declared curated method must be a real Omie method."""
    from omie import catalog
    from omie.tools import resources

    missing = []
    for r in resources.RESOURCES:
        known = {m["call"] for m in catalog.endpoint_methods(r.path)}
        for call in (r.list_call, r.get_call, r.upsert_call, r.delete_call, *r.extra):
            if call and call not in known:
                missing.append(f"{r.ns}: {call} not on {r.path}")
    assert not missing, "curated methods absent from catalog:\n" + "\n".join(missing)


def test_describe_method_resolves_schema_and_example():
    from omie import catalog

    d = catalog.describe_method("ListarClientes")
    assert d["endpoint"] == "/geral/clientes/"
    assert d["url"] == "https://app.omie.com.br/api/v1/geral/clientes/"
    assert d["mutating"] is False
    assert d["example_param"]["pagina"] == 1
    assert d["params"] and d["params"][0]["schema"]["fields"]


def test_describe_unknown_method_suggests_alternatives():
    from omie import catalog

    with pytest.raises(KeyError) as ei:
        catalog.describe_method("ListarCliente")  # singular typo
    assert "ListarClientes" in str(ei.value)


def test_search_finds_by_portuguese_and_resource():
    from omie import catalog

    assert any(h["call"] == "ListarContasReceber"
               for h in catalog.search("contas receber"))
    assert any(h["family"] == "estoque" for h in catalog.search("estoque"))


# --- mutation classification -----------------------------------------------


@pytest.mark.parametrize("call,mutating", [
    ("ListarClientes", False), ("ConsultarCliente", False),
    ("ObterPix", False), ("PesquisarPedCompra", False), ("VerificarConta", False),
    ("IncluirCliente", True), ("AlterarCliente", True), ("ExcluirCliente", True),
    ("UpsertCliente", True), ("CancelarPix", True), ("LancarRecebimento", True),
    ("TotalmenteNovoVerbo", True),  # unknown verb ⇒ fail-safe to mutating
])
def test_is_mutating_classification(call, mutating):
    from omie.api import is_mutating

    assert is_mutating(call) is mutating


@pytest.mark.parametrize("raw,expected", [
    ("geral/clientes", "/geral/clientes/"),
    ("/geral/clientes/", "/geral/clientes/"),
    ("api/v1/geral/clientes", "/geral/clientes/"),
    ("https://app.omie.com.br/api/v1/geral/clientes/", "/geral/clientes/"),
])
def test_normalize_path(raw, expected):
    from omie.api import normalize_path

    assert normalize_path(raw) == expected


# --- fault classification ---------------------------------------------------


def test_classify_invalid_key_as_auth_error():
    """Verified live 2026-08-05: HTTP 403 + this faultstring."""
    from omie.errors import OmieAuthError, classify_fault

    e = classify_fault(
        "A chave de acesso não está preenchida ou não é válida.", http_status=403
    )
    assert isinstance(e, OmieAuthError)
    assert e.status == 401


def test_classify_end_of_pages_as_empty_page():
    from omie.errors import OmieEmptyPage, classify_fault

    assert isinstance(
        classify_fault("Não existem registros para a página [3]!"), OmieEmptyPage
    )


@pytest.mark.parametrize("fault,cls_name", [
    ("Cliente não cadastrado!", "OmieNotFound"),
    ("O campo razao_social é de preenchimento obrigatório.", "OmieValidationError"),
    ("Too many requests", "OmieRateLimited"),
])
def test_classify_common_faults(fault, cls_name):
    from omie.errors import classify_fault

    assert type(classify_fault(fault)).__name__ == cls_name


def test_unrecognised_fault_stays_honest():
    """An unknown fault is reported as-is, never re-labelled a success."""
    from omie.errors import OmieApiError, classify_fault

    e = classify_fault("Algo totalmente inesperado", http_status=500)
    assert type(e) is OmieApiError
    assert e.status == 500
    assert e.faultstring == "Algo totalmente inesperado"


def test_fault_from_body_ignores_non_fault_bodies():
    from omie.errors import fault_from_body

    assert fault_from_body('{"clientes_cadastro": []}', http_status=200, tag="t") is None
    assert fault_from_body("<html>", http_status=500, tag="t") is None
    assert fault_from_body("", http_status=500, tag="t") is None


def test_http_425_maps_to_rate_limited_block():
    from omie.errors import OmieRateLimited, classify_fault

    e = classify_fault("blocked", http_status=425)
    assert isinstance(e, OmieRateLimited)
    assert e.retry_after == 1800.0


# --- settings / environments ------------------------------------------------


def _fresh_settings(monkeypatch, env: dict):
    from omie import settings

    for k in list(sys.modules):
        pass
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(settings, "_DOTENV_DIR", Path("/nonexistent"))
    settings.get_settings.cache_clear()
    return settings.get_settings()


def test_single_company_shorthand(monkeypatch):
    s = _fresh_settings(monkeypatch, {"OMIE_APP_KEY": "k123456", "OMIE_APP_SECRET": "s"})
    assert s.names() == ["default"]
    assert s.get(None).name == "default"
    assert s.configured is True


def test_environments_json_blob_and_readonly(monkeypatch):
    blob = json.dumps({
        "acme-prod": {"app_key": "kprod01", "app_secret": "sp",
                      "label": "Acme", "readonly": True},
        "acme-test": {"app_key": "ktest01", "app_secret": "st"},
    })
    s = _fresh_settings(monkeypatch, {
        "OMIE_ENVIRONMENTS": blob, "OMIE_DEFAULT_ENVIRONMENT": "acme-test",
    })
    assert sorted(s.names()) == ["acme-prod", "acme-test"]
    assert s.get("acme-prod").readonly is True
    assert s.get(None).name == "acme-test"


def test_flat_per_environment_vars(monkeypatch):
    s = _fresh_settings(monkeypatch, {
        "OMIE_ENV__ACME_PROD__APP_KEY": "k1",
        "OMIE_ENV__ACME_PROD__APP_SECRET": "s1",
        "OMIE_ENV__ACME_PROD__READONLY": "true",
    })
    assert s.names() == ["acme-prod"]
    assert s.get("acme-prod").readonly is True


def test_redacted_never_leaks_secret(monkeypatch):
    s = _fresh_settings(monkeypatch, {
        "OMIE_APP_KEY": "abcdef123456", "OMIE_APP_SECRET": "supersecret"})
    r = s.get(None).redacted()
    blob = json.dumps(r)
    assert "supersecret" not in blob
    assert "abcdef123456" not in blob
    assert r["app_key_suffix"] == "…3456"
    assert r["app_secret_set"] is True


def test_ambiguous_default_refuses_to_guess(monkeypatch):
    from omie.errors import OmieConfigError

    blob = json.dumps({"a": {"app_key": "k", "app_secret": "s"},
                       "b": {"app_key": "k", "app_secret": "s"}})
    s = _fresh_settings(monkeypatch, {"OMIE_ENVIRONMENTS": blob})
    with pytest.raises(OmieConfigError) as ei:
        s.get(None)
    assert "none is named 'default'" in str(ei.value)


def test_unknown_environment_names_the_configured_ones(monkeypatch):
    from omie.errors import OmieConfigError

    s = _fresh_settings(monkeypatch, {"OMIE_APP_KEY": "k", "OMIE_APP_SECRET": "s"})
    with pytest.raises(OmieConfigError) as ei:
        s.get("nope")
    assert "['default']" in str(ei.value)


def test_malformed_environments_blob_raises(monkeypatch):
    from omie.errors import OmieConfigError

    with pytest.raises(OmieConfigError):
        _fresh_settings(monkeypatch, {"OMIE_ENVIRONMENTS": "{not json"})


def test_no_config_reports_typed_error(monkeypatch):
    from omie.errors import OmieConfigError

    from omie import settings

    monkeypatch.setattr(settings, "_DOTENV_DIR", Path("/nonexistent"))
    for k in ("OMIE_APP_KEY", "OMIE_APP_SECRET", "OMIE_ENVIRONMENTS"):
        monkeypatch.delenv(k, raising=False)
    settings.get_settings.cache_clear()
    with pytest.raises(OmieConfigError):
        settings.get_settings().get(None)


# --- write guards (the safety contract) -------------------------------------


def _env(name="acme", readonly=False):
    from omie.settings import OmieEnvironment

    return OmieEnvironment(name=name, app_key="k123456", app_secret="s",
                           readonly=readonly)


@pytest.mark.asyncio
async def test_mutating_call_without_confirm_is_refused_before_any_request():
    from omie.api import OmieClient
    from omie.errors import ConfirmationRequiredError

    c = OmieClient(_env())
    with patch("_kit.transport.urlopen") as m:
        with pytest.raises(ConfirmationRequiredError) as ei:
            await c.call("/geral/clientes/", "ExcluirCliente", {"codigo_cliente_omie": 1})
    m.assert_not_called()  # no side-effect, and no request spent
    assert ei.value.status == 412


@pytest.mark.asyncio
async def test_readonly_environment_refuses_write_even_with_confirm():
    from omie.api import OmieClient
    from omie.errors import OmieReadOnlyEnvironment

    c = OmieClient(_env(readonly=True))
    with patch("_kit.transport.urlopen") as m:
        with pytest.raises(OmieReadOnlyEnvironment):
            await c.call("/geral/clientes/", "ExcluirCliente",
                         {"codigo_cliente_omie": 1}, confirm=True)
    m.assert_not_called()


@pytest.mark.asyncio
async def test_readonly_environment_still_allows_reads():
    from omie.api import OmieClient

    c = OmieClient(_env(readonly=True))
    with patch("omie.api._http_request_json", return_value={"total_de_registros": 0}):
        out = await c.call("/geral/clientes/", "ListarClientes", {"pagina": 1})
    assert out == {"total_de_registros": 0}


@pytest.mark.asyncio
async def test_fault_in_a_200_body_still_raises():
    """Omie can report a failure with HTTP 200 — the success path must check."""
    from omie.api import OmieClient
    from omie.errors import OmieNotFound

    c = OmieClient(_env())
    body = {"faultstring": "Cliente não cadastrado!", "faultcode": "SOAP-ENV:Server"}
    with patch("omie.api._http_request_json", return_value=body):
        with pytest.raises(OmieNotFound):
            await c.call("/geral/clientes/", "ConsultarCliente", {"codigo_cliente_omie": 1})


@pytest.mark.asyncio
async def test_envelope_shape_sent_to_omie():
    """The wire format is the whole contract — assert it exactly."""
    from omie.api import OmieClient

    seen = {}

    def fake(method, url, **kw):
        seen.update({"method": method, "url": url, **kw})
        return {"ok": 1}

    c = OmieClient(_env())
    with patch("omie.api._http_request_json", side_effect=fake):
        await c.call("geral/clientes", "ListarClientes", {"pagina": 2})

    assert seen["method"] == "POST"
    assert seen["url"] == "https://app.omie.com.br/api/v1/geral/clientes/"
    assert seen["body"] == {
        "call": "ListarClientes", "app_key": "k123456", "app_secret": "s",
        "param": [{"pagina": 2}],
    }


# --- pagination -------------------------------------------------------------


@pytest.mark.asyncio
async def test_paginate_walks_pages_and_stops_at_total():
    from omie.api import OmieClient

    pages = {
        1: {"pagina": 1, "total_de_paginas": 2, "total_de_registros": 3,
            "clientes_cadastro": [{"i": 1}, {"i": 2}]},
        2: {"pagina": 2, "total_de_paginas": 2, "total_de_registros": 3,
            "clientes_cadastro": [{"i": 3}]},
    }

    def fake(method, url, *, body, **kw):
        return pages[body["param"][0]["pagina"]]

    c = OmieClient(_env())
    with patch("omie.api._http_request_json", side_effect=fake):
        out = await c.paginate("/geral/clientes/", "ListarClientes")

    assert out["count"] == 3
    assert out["records_key"] == "clientes_cadastro"
    assert out["pages_fetched"] == 2
    assert out["truncated"] is False


@pytest.mark.asyncio
async def test_paginate_stops_cleanly_on_end_of_data_fault():
    """Omie signals end-of-data as a fault; that is a stop, not a failure."""
    from omie.api import OmieClient

    def fake(method, url, *, body, **kw):
        if body["param"][0]["pagina"] == 1:
            return {"clientes_cadastro": [{"i": 1}]}
        return {"faultstring": "Não existem registros para a página [2]!"}

    c = OmieClient(_env())
    with patch("omie.api._http_request_json", side_effect=fake):
        out = await c.paginate("/geral/clientes/", "ListarClientes")

    assert out["count"] == 1
    assert out["truncated"] is False


@pytest.mark.asyncio
async def test_paginate_reports_truncation_honestly():
    from omie.api import OmieClient

    def fake(method, url, *, body, **kw):
        return {"pagina": body["param"][0]["pagina"], "total_de_paginas": 99,
                "clientes_cadastro": [{"i": 1}]}

    c = OmieClient(_env())
    with patch("omie.api._http_request_json", side_effect=fake):
        out = await c.paginate("/geral/clientes/", "ListarClientes", max_pages=2)

    assert out["truncated"] is True
    assert out["next_page"] == 3
    assert out["pages_fetched"] == 2


@pytest.mark.asyncio
async def test_paginate_caps_page_size_at_omie_limit():
    from omie.api import OmieClient

    seen = []

    def fake(method, url, *, body, **kw):
        seen.append(body["param"][0]["registros_por_pagina"])
        return {"clientes_cadastro": []}

    c = OmieClient(_env())
    with patch("omie.api._http_request_json", side_effect=fake):
        await c.paginate("/geral/clientes/", "ListarClientes", page_size=5000)
    assert seen == [100]


# --- generic call seam validation -------------------------------------------


@pytest.mark.asyncio
async def test_invoke_rejects_unknown_method_without_spending_a_request():
    from omie.tools.call import invoke

    with patch("_kit.transport.urlopen") as m:
        out = await invoke({"call": "ListarClienteZ", "param": {}})
    m.assert_not_called()
    assert out["ok"] is False
    assert out["error"]["status"] == 422
    assert "ListarClientes" in out["error"]["message"]


@pytest.mark.asyncio
async def test_invoke_rejects_method_not_on_named_endpoint():
    from omie.tools.call import invoke

    out = await invoke({"call": "ListarClientes", "endpoint": "/geral/produtos/"})
    assert out["ok"] is False
    assert out["error"]["status"] == 422


@pytest.mark.asyncio
async def test_paginate_tool_refuses_a_mutating_call():
    from omie.tools.call import paginate

    out = await paginate({"call": "ExcluirCliente"})
    assert out["ok"] is False
    assert "not a read method" in out["error"]["message"]


# --- rate limiting ----------------------------------------------------------


def test_sliding_window_delays_once_full():
    from omie.ratelimit import _SlidingWindow

    w = _SlidingWindow(10)  # effective limit 9 (90% safety)
    for _ in range(w.limit):
        w.record()
    assert w.delay() > 0


def test_circuit_opens_after_failure_streak():
    from omie.ratelimit import FAILURE_STREAK_OPEN, OmieRateLimiter

    lim = OmieRateLimiter()
    key = lim.key("appkey", "/geral/clientes/", "ListarClientes")
    assert lim.circuit_block(key) is None
    for _ in range(FAILURE_STREAK_OPEN):
        lim.record_failure(key)
    assert lim.circuit_block(key) > 0


def test_success_resets_failure_streak():
    from omie.ratelimit import OmieRateLimiter

    lim = OmieRateLimiter()
    key = lim.key("appkey", "/p/", "ListarX")
    lim.record_failure(key)
    lim.record_success(key)
    assert lim.snapshot()["failure_streaks"] == {}


@pytest.mark.asyncio
async def test_open_circuit_blocks_before_sending():
    from omie.api import OmieClient
    from omie.errors import OmieRateLimited
    from omie.ratelimit import FAILURE_STREAK_OPEN, limiter

    c = OmieClient(_env())
    key = limiter.key("k123456", "/geral/clientes/", "ListarClientes")
    for _ in range(FAILURE_STREAK_OPEN):
        limiter.record_failure(key)
    try:
        with patch("_kit.transport.urlopen") as m:
            with pytest.raises(OmieRateLimited):
                await c.call("/geral/clientes/", "ListarClientes", {})
        m.assert_not_called()
    finally:
        limiter._open_until.clear()
        limiter._failures.clear()


# --- the shared _kit seam extension ----------------------------------------


def test_transport_hook_defaults_to_prior_behavior():
    """`on_http_error=None` must leave the other 5 connectors untouched."""
    import urllib.error
    from io import BytesIO

    from _kit.transport import ConnectorHttpError, request_json

    err = urllib.error.HTTPError("u", 500, "boom", {}, BytesIO(b"body"))
    with patch("_kit.transport.urlopen", side_effect=err):
        with pytest.raises(ConnectorHttpError) as ei:
            request_json("GET", "https://x/y")
    assert ei.value.status == 500


def test_transport_hook_returning_none_falls_through():
    import urllib.error
    from io import BytesIO

    from _kit.transport import ConnectorHttpError, request_json

    err = urllib.error.HTTPError("u", 500, "boom", {}, BytesIO(b"body"))
    with patch("_kit.transport.urlopen", side_effect=err):
        with pytest.raises(ConnectorHttpError):
            request_json("GET", "https://x/y", on_http_error=lambda s, b, t: None)
