"""Vista write surface — photo upload, lead submission, write-permission probe.

Every wire shape asserted here was established against Vista's public sandbox
(`sandbox-rest.vistahost.com.br`) or by a non-mutating probe of production,
2026-09-16 (vista.md § 4.7). Network-free: httpx.MockTransport only.
"""
from __future__ import annotations

import json

import httpx
import pytest

from noctusai_lib.integrations.vista import (
    VISTA_WRITE_PERMISSION_BASELINE,
    WRITE_ABSENT,
    WRITE_DENIED,
    WRITE_PERMITTED,
    WRITE_UNKNOWN,
    FakeVistaClient,
    VistaMissingParameter,
    VistaPermissionDenied,
)
from noctusai_lib.integrations.vista.client import VistaClient

KEY = "0123456789abcdef0123456789ab644c"

# Real bodies, JSON-escaped exactly as Vista sends them.
DENIED_401 = '{"status":401,"message":"Permiss\\u00e3o Negada: \\"%s\\" M\\u00e9todo: imoveis\\/fotos"}' % KEY
MISSING_401 = '{"status":401,"message":"Voc\\u00ea deve informar os dados em json no par\\u00e2metro \\"cadastro\\""}'
FORMAT_400 = '{"status":400,"message":"O formato dos dados n\\u00e3o est\\u00e1 correto. \\u00c9 necess\\u00e1rio informar um JSON String."}'
OWNER_403 = '{"status":403,"message":"A chave de API n\\u00e3o possui as permiss\\u00f5es necess\\u00e1rias para acessar os dados do propriet\\u00e1rio."}'


def _client(status: int, body: str, seen: list[httpx.Request] | None = None) -> VistaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, text=body)

    return VistaClient(
        "https://t-rest.vistahost.com.br",
        KEY,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


# ─── 401 / 403 classification — read the MESSAGE, not the status ──────────


@pytest.mark.asyncio
async def test_missing_parameter_401_is_not_a_permission_denial() -> None:
    client = _client(401, MISSING_401)
    with pytest.raises(VistaMissingParameter) as exc:
        await client.listar_usuarios(fields=["Codigo"])
    assert not isinstance(exc.value, VistaPermissionDenied)
    assert exc.value.status == 401


@pytest.mark.asyncio
async def test_permission_denied_401_stays_a_denial_and_is_redacted() -> None:
    client = _client(401, DENIED_401)
    with pytest.raises(VistaPermissionDenied) as exc:
        await client.listar_usuarios(fields=["Codigo"])
    assert KEY not in str(exc.value)


@pytest.mark.asyncio
async def test_field_level_403_is_a_permission_denial() -> None:
    client = _client(403, OWNER_403)
    with pytest.raises(VistaPermissionDenied) as exc:
        await client.detalhes_imovel("CA2830", fields=[{"proprietarios": ["Nome"]}])
    assert exc.value.status == 403


# ─── POST /imoveis/fotos ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_photo_upload_wire_shape() -> None:
    seen: list[httpx.Request] = []
    client = _client(200, '{"Fotos":{"foto1":{"CodigoFoto":1}}}', seen)
    result = await client.cadastrar_fotos_imovel("CA2830", {"foto1": "https://cdn.example/a.jpg"})

    (req,) = seen
    assert req.method == "POST"
    assert req.url.path == "/imoveis/fotos"
    assert req.content == b""
    # `imovel` is TOP-LEVEL; the photos ride in `cadastro.fields` as a keyed object.
    assert req.url.params["imovel"] == "CA2830"
    assert json.loads(req.url.params["cadastro"]) == {"fields": {"foto1": "https://cdn.example/a.jpg"}}
    assert "pesquisa" not in req.url.params
    assert result.status == 200


@pytest.mark.asyncio
async def test_photo_upload_partial_207_is_returned_not_raised() -> None:
    body = '{"Fotos":{"foto1":["Erro ao resgatar imagem https://x.invalid/a.jpg (http_code: 0)"]}}'
    result = await _client(207, body).cadastrar_fotos_imovel("CA2830", {"foto1": "https://x.invalid/a.jpg"})
    assert result.status == 207
    assert "Erro ao resgatar" in result.data["Fotos"]["foto1"][0]


@pytest.mark.asyncio
async def test_photo_upload_denied_raises_permission_denied() -> None:
    with pytest.raises(VistaPermissionDenied):
        await _client(401, DENIED_401).cadastrar_fotos_imovel("CA2830", {"f": "https://a/b.jpg"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "codigo,fotos",
    [
        ("", {"f": "https://a/b.jpg"}),
        ("CA2830", {}),
        ("CA2830", {"f": "data:image/jpeg;base64,AAAA"}),  # base64 is rejected by Vista
        ("CA2830", {"f": "/local/path.jpg"}),
    ],
)
async def test_photo_upload_rejects_what_vista_would_before_any_request(codigo, fotos) -> None:
    for client in (_client(200, "{}", seen := []), FakeVistaClient()):
        with pytest.raises(ValueError):
            await client.cadastrar_fotos_imovel(codigo, fotos)
    assert seen == []


# ─── POST /lead ──────────────────────────────────────────────────────────

LEAD = {"nome": "Ana", "mensagem": "Quero visitar", "veiculo": "Site", "fone": "11999990000"}


@pytest.mark.asyncio
async def test_lead_wire_shape() -> None:
    seen: list[httpx.Request] = []
    client = _client(200, '{"status":200,"message":"Ok.","Codigo":54129,"Corretor":1}', seen)
    result = await client.enviar_lead({**LEAD, "anuncio": "CA2830"})

    (req,) = seen
    assert req.method == "POST"
    assert req.url.path == "/lead"  # top level — `/clientes/lead` is 404
    assert json.loads(req.url.params["cadastro"]) == {"lead": {**LEAD, "anuncio": "CA2830"}}
    assert result.data["Codigo"] == 54129


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing",
    ["nome", "mensagem", "veiculo"],
)
async def test_lead_requires_vistas_mandatory_fields(missing) -> None:
    lead = {k: v for k, v in LEAD.items() if k != missing}
    for client in (_client(200, "{}", seen := []), FakeVistaClient()):
        with pytest.raises(ValueError, match=missing):
            await client.enviar_lead(lead)
    assert seen == []


@pytest.mark.asyncio
async def test_lead_needs_email_or_fone() -> None:
    lead = {k: v for k, v in LEAD.items() if k != "fone"}
    with pytest.raises(ValueError, match="email|fone"):
        await _client(200, "{}").enviar_lead(lead)
    # either one satisfies it
    await _client(200, "{}").enviar_lead({**lead, "email": "a@b.co"})


# ─── Non-mutating write-permission probe ─────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,verdict",
    [
        (401, DENIED_401, WRITE_DENIED),
        (401, MISSING_401, WRITE_PERMITTED),  # auth passed, then params checked
        (400, FORMAT_400, WRITE_PERMITTED),  # /clientes/anexos on a permitted key
        (404, '{"status":404,"message":"No route found"}', WRITE_ABSENT),
        (500, "boom", WRITE_UNKNOWN),
        (200, "{}", WRITE_UNKNOWN),  # an empty write must never "succeed"
    ],
)
async def test_probe_write_permission_verdicts(status, body, verdict) -> None:
    row = await _client(status, body).probe_write_permission("/imoveis/fotos")
    assert row == {"endpoint": "/imoveis/fotos", "verdict": verdict, "http_status": status}


@pytest.mark.asyncio
async def test_probe_write_permission_sends_no_payload() -> None:
    """The safety property: with no `cadastro`, Vista has nothing to create."""
    seen: list[httpx.Request] = []
    await _client(401, MISSING_401, seen).probe_write_permission("/lead")
    (req,) = seen
    assert req.method == "POST"
    assert set(req.url.params.keys()) == {"key"}
    assert req.content == b""


@pytest.mark.asyncio
async def test_probe_write_permission_unconfigured() -> None:
    row = await VistaClient(None, None).probe_write_permission("/lead")
    assert row["verdict"] == "not_configured"


def test_write_baseline_records_the_2026_10_26_verdicts() -> None:
    verdicts = {path: verdict for path, verdict, _ in VISTA_WRITE_PERMISSION_BASELINE}
    # Flipped only on a live probe that read `permitted` (2026-10-26, re-read
    # 2026-10-27): `/imoveis/fotos` answers the missing-`cadastro` 401 and
    # `/clientes/anexos` the format 400 — both past the auth check. A
    # `denied` from here on is a grant ROLLBACK.
    assert verdicts["/imoveis/fotos"] == WRITE_PERMITTED
    assert verdicts["/lead"] == WRITE_PERMITTED
    assert verdicts["/clientes/anexos"] == WRITE_PERMITTED


@pytest.mark.asyncio
async def test_fake_probe_reads_seeded_denials() -> None:
    fake = FakeVistaClient(
        errors={"/imoveis/fotos": VistaPermissionDenied(401, "{}", "/imoveis/fotos")}
    )
    assert (await fake.probe_write_permission("/imoveis/fotos"))["verdict"] == WRITE_DENIED
    assert (await fake.probe_write_permission("/lead"))["verdict"] == WRITE_PERMITTED
    with pytest.raises(VistaPermissionDenied):
        await fake.cadastrar_fotos_imovel("CA2830", {"f": "https://a/b.jpg"})


# ─── Imóvel update: PUT /imoveis/detalhes (probe 2026-11-04, vista.md § 4.8) ──

OBS = "Lote 1 Quadra 2\nMPM 0000\n\n10/10/26 Parceiro informa Venda SUSPENSA. (Ana)\n01/09/26 Ana informa alterações de valores. (Bia)"
UPD = dict(motivo="proprietário confirmou o novo preço", autor="NoctusAI", canal="WhatsApp Julia", fonte="Proprietário",
           conversa_url="https://sw.test/julia/conversas?contato=jc-1", rotulos={"ValorVenda": "valor de venda"})


def _client_rw(seen: list[httpx.Request], *, obs: str = OBS, leitura: int = 200, escrita: int = 200) -> VistaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            body = json.dumps({"Codigo": "CA2830", "ValorVenda": "900000", "ObsVenda": obs})
            return httpx.Response(leitura, text=body if leitura == 200 else "boom")
        return httpx.Response(escrita, text="{}" if escrita == 200 else DENIED_401)

    return VistaClient("https://t-rest.vistahost.com.br", KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_atualizar_imovel_is_a_put_on_detalhes_that_carries_the_fields_and_the_note_in_the_same_call() -> None:
    """`PUT /imoveis/detalhes?imovel=` (NOT `/imoveis/alterar`, 404) with `cadastro={"fields":…}`; ObsVenda gets our dated line
    BEFORE the first dated line, the header untouched; the CURRENT field is read right before the write."""
    seen: list[httpx.Request] = []
    linha = await _client_rw(seen).atualizar_imovel("CA2830", {"ValorVenda": "850000"}, **UPD)
    assert [r.method for r in seen] == ["GET", "PUT"]
    put = seen[1]
    assert put.url.path == "/imoveis/detalhes" and put.url.params["imovel"] == "CA2830"
    fields = json.loads(put.url.params["cadastro"])["fields"]
    assert fields["ValorVenda"] == "850000"
    linhas = fields["ObsVenda"].split("\n")
    assert linhas[:3] == ["Lote 1 Quadra 2", "MPM 0000", ""] and linhas[3] == linha and linhas[4].startswith("10/10/26")
    assert linha.endswith("Conversa: https://sw.test/julia/conversas?contato=jc-1 (NoctusAI)")
    assert "Proprietário informa via WhatsApp Julia: valor de venda 900000 → 850000. proprietário confirmou o novo preço." in linha
    assert "\n" not in linha


@pytest.mark.asyncio
@pytest.mark.parametrize("motivo,autor", [("", "x"), ("   ", "x"), (None, "x"), ("porque sim", ""), ("porque sim", None)])
async def test_atualizar_imovel_refuses_without_a_reason_and_an_author_before_any_call(motivo, autor) -> None:
    seen: list[httpx.Request] = []
    for client in (_client_rw(seen), FakeVistaClient()):
        with pytest.raises(ValueError):
            await client.atualizar_imovel("CA2830", {"ValorVenda": "1"}, motivo=motivo, autor=autor)
    assert seen == []


@pytest.mark.asyncio
async def test_atualizar_imovel_refuses_an_empty_update() -> None:
    for client in (_client_rw([]), FakeVistaClient()):
        with pytest.raises(ValueError):
            await client.atualizar_imovel("CA2830", {}, **UPD)


@pytest.mark.asyncio
async def test_a_failed_read_of_the_current_note_writes_nothing() -> None:
    seen: list[httpx.Request] = []
    with pytest.raises(Exception):
        await _client_rw(seen, leitura=500).atualizar_imovel("CA2830", {"ValorVenda": "1"}, **UPD)
    # the shared Vista pacer retries a READ on 5xx (bounded), so there may be several GETs -- but never a PUT
    assert seen and {r.method for r in seen} == {"GET"}
    fake = FakeVistaClient(errors={"/imoveis/detalhes": VistaPermissionDenied(401, "{}", "/imoveis/detalhes")})
    with pytest.raises(VistaPermissionDenied):
        await fake.atualizar_imovel("CA2830", {"ValorVenda": "1"}, **UPD)
    assert fake.updates == []


@pytest.mark.asyncio
async def test_atualizar_imovel_denied_never_leaks_the_key() -> None:
    with pytest.raises(VistaPermissionDenied) as exc:
        await _client_rw([], escrita=401).atualizar_imovel("CA2830", {"ValorVenda": "1"}, **UPD)
    assert KEY not in str(exc.value) and KEY not in exc.value.body


@pytest.mark.asyncio
async def test_probe_put_on_detalhes_is_non_mutating_and_reads_the_2026_11_04_verdict() -> None:
    """An empty PUT on a non-existent code: 'deve informar … cadastro' = permitted; no `cadastro` is ever sent."""
    seen: list[httpx.Request] = []
    row = await _client(401, MISSING_401, seen).probe_write_permission("/imoveis/detalhes", method="PUT", extra_params={"imovel": "ZZ0"})
    assert row["verdict"] == WRITE_PERMITTED
    (req,) = seen
    assert req.method == "PUT" and "cadastro" not in req.url.params and req.content == b""
    assert (await _client(401, DENIED_401).probe_write_permission("/imoveis/detalhes", method="PUT"))["verdict"] == WRITE_DENIED


@pytest.mark.asyncio
async def test_fake_client_records_the_update_with_the_note_and_raises_what_it_is_seeded_with() -> None:
    fake = FakeVistaClient(responses={"/imoveis/detalhes": {"Codigo": "CA2830", "ObsVenda": OBS}})
    linha = await fake.atualizar_imovel("CA2830", {"ValorVenda": 1}, **UPD)
    [(cod, campos)] = fake.updates
    assert cod == "CA2830" and campos["ValorVenda"] == 1 and linha in campos["ObsVenda"].split("\n")
    denied = FakeVistaClient(responses={"/imoveis/detalhes": {"Codigo": "CA2830"}}, errors={"PUT /imoveis/detalhes": VistaPermissionDenied(401, "{}", "/imoveis/detalhes")})
    with pytest.raises(VistaPermissionDenied):
        await denied.atualizar_imovel("CA2830", {"ValorVenda": 1}, **UPD)
    assert denied.updates == []


@pytest.mark.asyncio
async def test_the_edit_goes_through_the_shared_pacer_a_5xx_write_is_never_retried_a_429_is() -> None:
    """The edit has no pacer of its own: it is `VistaClient._request`, so it inherits the shared `vista` bucket's policy (canon 4/5)
    -- a 5xx on the PUT has an unknown outcome and is NOT retried; a 429 means it was not processed and IS retried after the hint."""
    puts: list[httpx.Request] = []

    def handler_5xx(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=json.dumps({"Codigo": "CA2830", "ValorVenda": "900000", "ObsVenda": OBS}))
        puts.append(request)
        return httpx.Response(503, text="down")

    cliente = VistaClient("https://t-rest.vistahost.com.br", KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler_5xx)))
    with pytest.raises(Exception):
        await cliente.atualizar_imovel("CA2830", {"ValorVenda": "1"}, **UPD)
    assert len(puts) == 1  # exactly one PUT: never blind-retried

    puts.clear()

    def handler_429(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=json.dumps({"Codigo": "CA2830", "ValorVenda": "900000", "ObsVenda": OBS}))
        puts.append(request)
        return httpx.Response(429, headers={"Retry-After": "1"}, text="slow") if len(puts) == 1 else httpx.Response(200, text="{}")

    cliente = VistaClient("https://t-rest.vistahost.com.br", KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler_429)))
    await cliente.atualizar_imovel("CA2830", {"ValorVenda": "1"}, **UPD)
    assert len(puts) == 2
