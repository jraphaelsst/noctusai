"""Vista CRM integration tests — Fake + factory + normalizer round-trip.

The Real `VistaClient` HTTP behavior is already covered by the ERP
showcase router/service suites; this module covers the seed additions
made by `social-wiring-absorption` Wave 1:

- `FakeVistaClient` — config leniency, typed-error injection, call
  recording, signature parity with `VistaClient`.
- `make_vista_client` — Fake/Real routing, leniency preserved.
- **Validated-shape round-trip** — feed the Fake a real
  `/imoveis/detalhes`-shaped payload (the One Consultoria ONE10121
  shape from the validated workspace) and assert the *real*
  `vista_imovel_detalhes_to_showcase` normalizer produces the
  expected `ShowcaseImovelDetalhes` — proving the Fake exercises the
  same mapping code path as the Real client.

Network-free: the Fake never touches httpx or the filesystem.
"""
from __future__ import annotations

import json

import httpx
import pytest

from noctusai_lib.integrations.vista import (
    KEY_REDACTION_PLACEHOLDER,
    VISTA_ENDPOINT_BASELINE,
    VISTA_PROBE_PATHS,
    FakeVistaClient,
    VistaCallResult,
    VistaConfigError,
    VistaPermissionDenied,
    make_vista_client,
    redact_api_key,
    vista_imovel_detalhes_to_showcase,
)
from noctusai_lib.integrations.vista.client import VistaClient


# ============================================================================
# FakeVistaClient
# ============================================================================


@pytest.mark.asyncio
async def test_fake_returns_seeded_payload() -> None:
    fake = FakeVistaClient(
        responses={"/imoveis/detalhes": {"Codigo": "ONE10121"}}
    )
    result = await fake.detalhes_imovel("ONE10121", fields=["Codigo"])
    assert isinstance(result, VistaCallResult)
    assert result.status == 200
    assert result.data == {"Codigo": "ONE10121"}
    assert fake.calls == [("/imoveis/detalhes", ["imovel", "key", "pesquisa"])]


@pytest.mark.asyncio
async def test_fake_empty_when_unseeded() -> None:
    fake = FakeVistaClient()
    result = await fake.listar_imoveis(fields=["Codigo"])
    assert result.data == {}
    assert result.status == 200


@pytest.mark.asyncio
async def test_fake_unconfigured_raises_config_error_at_call_time() -> None:
    fake = FakeVistaClient(configured=False)
    assert fake.configured is False
    with pytest.raises(VistaConfigError):
        await fake.detalhes_imovel("ONE1", fields=["Codigo"])


@pytest.mark.asyncio
async def test_fake_injects_typed_error() -> None:
    err = VistaPermissionDenied(401, "{}", "/clientes/listar")
    fake = FakeVistaClient(errors={"/clientes/listar": err})
    with pytest.raises(VistaPermissionDenied):
        await fake.listar_clientes(fields=["Codigo"])


@pytest.mark.asyncio
async def test_fake_probe_never_raises() -> None:
    fake = FakeVistaClient(
        errors={"/x": VistaPermissionDenied(401, "{}", "/x")}
    )
    row = await fake.probe("/x")
    assert row["endpoint"] == "/x"
    assert row["status"] == "error"
    assert row["http_status"] == 401


def test_fake_base_url_parity() -> None:
    fake = FakeVistaClient(base_url="https://t.example/")
    assert fake.base_url == "https://t.example"


# ============================================================================
# Factory
# ============================================================================


def test_factory_returns_fake_when_use_fake_true() -> None:
    client = make_vista_client(use_fake=True)
    assert isinstance(client, FakeVistaClient)


def test_factory_returns_real_when_use_fake_false() -> None:
    client = make_vista_client(use_fake=False, base_url="https://v", api_key="k")
    assert isinstance(client, VistaClient)
    assert client.configured is True


def test_factory_real_leniency_no_raise_without_credentials() -> None:
    # Leniency contract: missing creds must NOT raise at build time.
    client = make_vista_client(use_fake=False)
    assert isinstance(client, VistaClient)
    assert client.configured is False


def test_factory_pre_seeds_fake() -> None:
    client = make_vista_client(
        use_fake=True, fake_responses={"/imoveis/detalhes": {"Codigo": "X"}}
    )
    assert isinstance(client, FakeVistaClient)


# ============================================================================
# Validated-shape round-trip through the Fake
# ============================================================================


@pytest.mark.asyncio
async def test_fake_detalhes_round_trips_through_real_normalizer() -> None:
    """ONE10121-shaped detalhes payload (validated workspace shape) →
    Fake → real normalizer → expected ShowcaseImovelDetalhes."""
    detalhes_payload = {
        "Codigo": "ONE10121",
        "TituloSite": "Casa com 2 dormitórios para locação - Granja Viana - Cotia - SP",
        "Categoria": "Casa em Condomínio",
        "Finalidade": "Locação",
        "Cidade": "Cotia",
        "Bairro": "Granja Viana",
        "UF": "SP",  # per-tenant: oneconsu-rest exposes UF, not Estado
        "ValorLocacao": "4500,00",  # comma decimal — coercion path
        "AreaTotal": "180.00",
        "Dormitorios": "2",
        "BanheiroSocial": "2",  # Banheiros denied on this tenant
        "Caracteristicas": {"Piscina": "Sim", "Churrasqueira": "Sim"},
        "Corretor": {"103": {"Nome": "Fernanda"}},
    }
    fake = FakeVistaClient(responses={"/imoveis/detalhes": detalhes_payload})
    result = await fake.detalhes_imovel("ONE10121", fields=["Codigo"])

    showcase = vista_imovel_detalhes_to_showcase(result.data)
    assert showcase.codigo == "ONE10121"
    assert showcase.base.finalidade == "Locação"
    assert showcase.base.estado == "SP"  # UF fallback
    assert showcase.base.valor_locacao == 4500.0  # comma → dot
    assert showcase.base.banheiros == 2  # BanheiroSocial fallback
    assert showcase.base.corretor_nome == "Fernanda"  # dict-keyed Corretor
    assert showcase.caracteristicas == {"Piscina": "Sim", "Churrasqueira": "Sim"}


# ============================================================================
# Credential hygiene — Vista echoes the API key back at us (vista.md § 3)
# ============================================================================
#
# Confirmed live 2026-08-05 against oneconsu-rest.vistahost.com.br: the 401
# body for a permission-gated method contains the raw key verbatim, and httpx
# renders the full ?key=<secret> URL inside transport errors. Both land in
# VistaUpstreamError.body / str(exc), and from there in the MCP's
# typed_error.message — which is read straight into an agent's context.
# These tests are the regression guard on that boundary.

# A DUMMY key, shaped like a real one (32 hex chars) but never issued.
# Never put the live tenant key in a tracked file — that is the same leak
# this module exists to prevent, just via git instead of via a log line.
SECRET = "00000000deadbeef0000000000000000"


def test_redact_api_key_removes_the_secret() -> None:
    body = f'{{"status":401,"message":"Permissão Negada: \\"{SECRET}\\" Método: clientes/listar"}}'
    out = redact_api_key(body, SECRET)
    assert SECRET not in out
    assert KEY_REDACTION_PLACEHOLDER in out
    # The diagnostic value must survive — we still want to know WHICH method.
    assert "clientes/listar" in out


def test_redact_api_key_is_a_noop_without_a_key() -> None:
    # An unconfigured client must not rewrite arbitrary text (an empty
    # needle would otherwise splice the placeholder between every char).
    assert redact_api_key("anything at all", "") == "anything at all"
    assert redact_api_key("", SECRET) == ""


@pytest.mark.asyncio
async def test_401_body_reaches_the_caller_redacted() -> None:
    """The end-to-end guarantee: a real 401 never carries the key outward."""
    leaky = f'{{"status":401,"message":"Permissão Negada: \\"{SECRET}\\" Método: clientes/listar"}}'
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, text=leaky)
    )
    async with httpx.AsyncClient(transport=transport) as http:
        client = VistaClient("https://t.example.com", SECRET, http_client=http)
        with pytest.raises(VistaPermissionDenied) as exc_info:
            await client.listar_clientes(fields=["Codigo"])

    exc = exc_info.value
    assert SECRET not in str(exc), "API key leaked via str(exc)"
    assert SECRET not in exc.body, "API key leaked via .body"
    assert exc.status == 401


@pytest.mark.asyncio
async def test_transport_error_url_reaches_the_caller_redacted() -> None:
    """httpx renders the full URL — including ?key= — on a transport error."""
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed connecting to {request.url}")

    transport = httpx.MockTransport(_boom)
    async with httpx.AsyncClient(transport=transport) as http:
        client = VistaClient("https://t.example.com", SECRET, http_client=http)
        with pytest.raises(Exception) as exc_info:
            await client.listar_imoveis(fields=["Codigo"])

    assert SECRET not in str(exc_info.value), "API key leaked via transport error"


# ============================================================================
# Endpoint baseline — seed-canonical, consumed by MCP + ERP (vista.md § 5.3)
# ============================================================================


def test_probe_paths_derive_from_the_baseline() -> None:
    assert VISTA_PROBE_PATHS == tuple(row[0] for row in VISTA_ENDPOINT_BASELINE)


def test_baseline_records_non_200_expectations() -> None:
    """A bare GET is 400/401/405 by design on several routes.

    Encoding the expectation is the whole point: it lets the probe tell
    "this tenant drifted" apart from "this endpoint always answers that way".
    """
    expected = {row[0]: row[1] for row in VISTA_ENDPOINT_BASELINE}
    # Needs a `pesquisa` param — a bare GET is 400, not a fault.
    assert expected["/imoveis/listarConteudo"] == 400
    # Route exists; this tenant's key lacks the per-method grant.
    assert expected["/clientes/listar"] == 401
    # Write-only upload route — GET is 405, NOT the 404 we used to claim.
    assert expected["/imoveis/fotos"] == 405


def test_baseline_distinguishes_gated_from_absent() -> None:
    """The actionable split: only permission_gated is unlocked by a request."""
    status = {row[0]: row[2] for row in VISTA_ENDPOINT_BASELINE}
    assert status["/clientes/listar"] == "permission_gated"
    assert status["/imoveis/fotos"] == "write_only"
    assert status["/imoveis/listar"] == "live_probed"


# ============================================================================
# 🔒 Gated families — parity with the ungated surface (vista.md § 4.2 / § 4.5)
#
# Added 2026-08-19 alongside the gated-surface refinement. Every test below
# fails against the pre-refinement code; they exist because the gated half had
# silently drifted from the working half while waiting for a Vista grant.
# ============================================================================


def _capture() -> tuple[list[httpx.Request], httpx.MockTransport]:
    """A transport that records every request and answers 200 with an empty body."""
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    return seen, httpx.MockTransport(_handler)


@pytest.mark.asyncio
async def test_listar_clientes_forwards_pagination_to_the_wire() -> None:
    """The silent-drop regression: page/page_size must REACH Vista.

    `vista.clientes.list` declared both parameters while `listar_clientes`
    accepted neither, so a host asking for page 2 silently received page 1 —
    a wrong answer delivered with full confidence.
    """
    seen, transport = _capture()
    async with httpx.AsyncClient(transport=transport) as http:
        client = VistaClient("https://t.example.com", SECRET, http_client=http)
        await client.listar_clientes(fields=["Codigo"], page=3, page_size=25)

    pesquisa = json.loads(seen[0].url.params["pesquisa"])
    assert pesquisa["paginacao"] == {"pagina": 3, "quantidade": 25}
    assert seen[0].url.params["showtotal"] == "1"


@pytest.mark.asyncio
async def test_listar_clientes_respects_the_server_side_50_cap() -> None:
    """Vista caps `quantidade` at 50 server-side; the client clamps to match."""
    seen, transport = _capture()
    async with httpx.AsyncClient(transport=transport) as http:
        client = VistaClient("https://t.example.com", SECRET, http_client=http)
        await client.listar_clientes(fields=["Codigo"], page=1, page_size=500)

    pesquisa = json.loads(seen[0].url.params["pesquisa"])
    assert pesquisa["paginacao"]["quantidade"] == 50


@pytest.mark.asyncio
async def test_listar_corretores_forwards_pagination_to_the_wire() -> None:
    seen, transport = _capture()
    async with httpx.AsyncClient(transport=transport) as http:
        client = VistaClient("https://t.example.com", SECRET, http_client=http)
        await client.listar_corretores(fields=["Codigo"], page=2, page_size=10)

    pesquisa = json.loads(seen[0].url.params["pesquisa"])
    assert pesquisa["paginacao"] == {"pagina": 2, "quantidade": 10}


@pytest.mark.asyncio
async def test_detalhes_cliente_sends_cliente_at_the_TOP_level() -> None:
    """`cliente=` is a top-level param, NOT a key inside `pesquisa`.

    Same shape as `/imoveis/detalhes?imovel=` (vista.md § 2). Putting the id
    inside `pesquisa` yields a 400 that reads like a field error, which is a
    genuinely confusing way to fail.
    """
    seen, transport = _capture()
    async with httpx.AsyncClient(transport=transport) as http:
        client = VistaClient("https://t.example.com", SECRET, http_client=http)
        await client.detalhes_cliente("C123", fields=["Codigo", "Nome"])

    params = seen[0].url.params
    assert params["cliente"] == "C123"
    assert "cliente" not in json.loads(params["pesquisa"])


@pytest.mark.asyncio
async def test_calibration_does_NOT_cache_a_permission_denial() -> None:
    """A 401 must leave the calibrator un-armed, not cache the full candidate set.

    `VistaPermissionDenied` subclasses `VistaUpstreamError`, so the generic
    handler used to swallow it and cache every candidate field as "safe" for
    the process lifetime. The day Vista granted the permission, the first
    live call would then ship that un-narrowed superset and 400 on the first
    field the tenant does not expose — with no way back short of a restart.
    """
    from noctusai_lib.integrations.vista.calibration import (
        FLOOR_FIELDS,
        Calibrator,
    )

    calib = Calibrator()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            401, json={"status": 401, "message": "Permissão Negada"}
        )
    )
    async with httpx.AsyncClient(transport=transport) as http:
        client = VistaClient("https://t.example.com", SECRET, http_client=http)
        fields = await calib.get_cliente_fields(client)

    assert fields == FLOOR_FIELDS
    assert "clientes" not in calib.snapshot(), (
        "a permission denial was cached — the grant would land on a stale, "
        "un-narrowed field set"
    )


@pytest.mark.asyncio
async def test_calibration_re_arms_once_the_grant_lands() -> None:
    """The other half of the contract: after a 401, a later 200 calibrates."""
    from noctusai_lib.integrations.vista.calibration import Calibrator

    calib = Calibrator()
    denied = httpx.MockTransport(lambda r: httpx.Response(401, json={"status": 401}))
    granted = httpx.MockTransport(lambda r: httpx.Response(200, json={}))

    async with httpx.AsyncClient(transport=denied) as http:
        client = VistaClient("https://t.example.com", SECRET, http_client=http)
        await calib.get_cliente_fields(client)

    async with httpx.AsyncClient(transport=granted) as http:
        client = VistaClient("https://t.example.com", SECRET, http_client=http)
        fields = await calib.get_cliente_fields(client)

    assert "clientes" in calib.snapshot(), "grant landed but calibration stayed un-armed"
    assert len(fields) > 1, "expected the candidate set, not the floor"


def test_fake_client_and_real_client_signatures_agree() -> None:
    """Mechanical Fake↔Real parity for the CLIENT (the adapter already has one).

    `FakeVistaClient`'s docstring claimed signature parity with `VistaClient`
    and nothing enforced it — so when `listar_clientes` gained pagination on
    the Real side, the Fake kept the old signature and any consumer that
    passed `page=` would work in production and TypeError in tests. A claim
    in a docstring is not a guarantee; this is.
    """
    import inspect

    for name in (
        "listar_imoveis",
        "detalhes_imovel",
        "listar_conteudo_imoveis",
        "listar_usuarios",
        "listar_agencias",
        "listar_clientes",
        "detalhes_cliente",
        "listar_corretores",
    ):
        real = getattr(VistaClient, name, None)
        fake = getattr(FakeVistaClient, name, None)
        assert real is not None, f"VistaClient is missing {name}"
        assert fake is not None, f"FakeVistaClient is missing {name} — Fake/Real drift"
        assert inspect.signature(fake) == inspect.signature(real), (
            f"{name}: Fake and Real signatures diverged"
        )
