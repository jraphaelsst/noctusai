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


def test_write_baseline_records_the_2026_09_16_verdicts() -> None:
    verdicts = {path: verdict for path, verdict, _ in VISTA_WRITE_PERMISSION_BASELINE}
    # Vista said the grant was resolved; the probe says photo write is STILL
    # denied on …644c. Flip this only on a probe that reads `permitted`.
    assert verdicts["/imoveis/fotos"] == WRITE_DENIED
    assert verdicts["/lead"] == WRITE_PERMITTED
    assert verdicts["/clientes/anexos"] == WRITE_DENIED


@pytest.mark.asyncio
async def test_fake_probe_reads_seeded_denials() -> None:
    fake = FakeVistaClient(
        errors={"/imoveis/fotos": VistaPermissionDenied(401, "{}", "/imoveis/fotos")}
    )
    assert (await fake.probe_write_permission("/imoveis/fotos"))["verdict"] == WRITE_DENIED
    assert (await fake.probe_write_permission("/lead"))["verdict"] == WRITE_PERMITTED
    with pytest.raises(VistaPermissionDenied):
        await fake.cadastrar_fotos_imovel("CA2830", {"f": "https://a/b.jpg"})
