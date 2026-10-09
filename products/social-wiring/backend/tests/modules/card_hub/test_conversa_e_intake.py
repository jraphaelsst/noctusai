"""CONTRACT §2 (S2): chat<->card link, conversation read, "Pedir documentos",
WhatsApp media intake and the triage path. The network download and the vision
read are the only fakes (boundaries); our own services run for real."""
from __future__ import annotations

import asyncio
import functools
import io
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import conversa_service
from app.modules.card_hub.extracao import registry
from app.services import chat_cliente_link, documento_intake_service as intake
from noctusai_lib.integrations.documents import FakeIdentityExtractor
from noctusai_lib.integrations.storage import FakeStorageBackend

from tests.modules.card_hub.conftest import ORG_ID

ORG = UUID(ORG_ID)
CHAT = "5511974693365@c.us"


def sync(fn):
    """Run an async test on its own loop (no async plugin in every venv)."""
    @functools.wraps(fn)
    def wrapper(*a, **k):
        return asyncio.run(fn(*a, **k))
    return wrapper


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _cliente(scoped, **over) -> str:
    cid = str(uuid4())
    row = {
        "id": cid, "org_id": ORG_ID, "nome": "maria souza", "chave_canonica": "+5511974693365",
        "chave_tipo": "telefone", "celular": "+5511974693365", "ativo": True,
    }
    row.update(over)
    existing = scoped.table("clientes").select("*").execute().data or []
    scoped.set_table_data("clientes", [*existing, row])
    return cid


def _chat(scoped, cliente_id, connection_id=None, chat_id=CHAT) -> str:
    cx = str(connection_id or uuid4())
    scoped.set_table_data("whatsapp_chats", [{
        "connection_id": cx, "chat_id": chat_id, "org_id": ORG_ID,
        "cliente_id": cliente_id, "last_message_at": "2026-10-09T10:00:00Z",
    }])
    return cx


# ─── auth boundary (strict 401) ──────────────────────────────────────────

_ROUTES = (
    ("get", "/api/clientes/{c}/conversa", None),
    ("post", "/api/clientes/{c}/conversa/pedir-documentos", {}),
    ("get", "/api/clientes/{c}/documentos/a-classificar", None),
    ("post", "/api/clientes/{c}/documentos/{d}/classificar", {"tipo_documento": "rg"}),
)


def test_every_route_is_a_strict_401_unauthenticated(anon_client):
    for method, path, body in _ROUTES:
        url = path.format(c=uuid4(), d=uuid4())
        kw = {} if body is None else {"json": body}
        assert getattr(anon_client, method)(url, **kw).status_code == 401, (method, url)


def test_the_routes_are_actually_mounted():
    from app.modules.card_hub import register

    mounted = {
        (m.lower(), r.path) for router in register().routers for r in router.routes
        for m in getattr(r, "methods", set())
    }
    for method, path, _ in _ROUTES:
        key = path.replace("{c}", "{cliente_id}").replace("{d}", "{documento_id}")
        assert (method, key) in mounted, key


# ─── chat <-> card link ──────────────────────────────────────────────────


def test_telefone_do_chat_rules():
    assert chat_cliente_link.telefone_do_chat(CHAT) == "+5511974693365"
    assert chat_cliente_link.telefone_do_chat("120363001234567890@g.us") is None
    assert chat_cliente_link.telefone_do_chat("182364311425240@lid") is None


def test_vincular_chat_stores_the_cliente(client, scoped):
    cid = _cliente(scoped)
    cx = _chat(scoped, None)
    achado = chat_cliente_link.vincular_chat(scoped, ORG, cx, CHAT)
    assert achado == cid
    row = scoped.table("whatsapp_chats").select("*").execute().data[0]
    assert row["cliente_id"] == cid


def test_a_miss_never_overwrites_an_existing_link(client, scoped):
    cid = _cliente(scoped, chave_canonica="+5511000000000")
    cx = _chat(scoped, cid)
    assert chat_cliente_link.vincular_chat(scoped, ORG, cx, CHAT) is None
    assert scoped.table("whatsapp_chats").select("*").execute().data[0]["cliente_id"] == cid


def test_a_new_cliente_claims_the_chats_of_its_phone(client, scoped):
    cx = _chat(scoped, None)
    cid = _cliente(scoped)
    assert chat_cliente_link.vincular_chats_do_cliente(scoped, ORG, cid, "+5511974693365") == 1
    assert scoped.table("whatsapp_chats").select("*").execute().data[0]["cliente_id"] == cid


def test_merge_repoints_the_chat_to_the_survivor(client, scoped):
    absorvido, sobrevivente = _cliente(scoped), _cliente(scoped, chave_canonica="+5511999999999")
    _chat(scoped, absorvido)
    chat_cliente_link.reapontar_chats(scoped, ORG, absorvido, sobrevivente)
    assert scoped.table("whatsapp_chats").select("*").execute().data[0]["cliente_id"] == sobrevivente


# ─── GET conversa ────────────────────────────────────────────────────────


def test_conversa_without_a_chat_is_empty(client, scoped):
    cid = _cliente(scoped)
    r = client.get(f"/api/clientes/{cid}/conversa", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json() == {"chat_id": None, "connection_id": None, "mensagens": []}


def test_conversa_returns_messages_with_the_attachment(client, scoped):
    cid = _cliente(scoped)
    cx = _chat(scoped, cid)
    doc = str(uuid4())
    scoped.set_table_data("conversation_messages", [
        {"id": str(uuid4()), "org_id": ORG_ID, "chat_id": CHAT, "direction": "outbound",
         "body": "oi", "created_at": "2026-10-09T10:00:00Z", "structured_payload": None},
        {"id": str(uuid4()), "org_id": ORG_ID, "chat_id": CHAT, "direction": "inbound",
         "body": "[Anexo recebido]", "created_at": "2026-10-09T10:01:00Z",
         "structured_payload": '{"anexo":{"mime":"image/jpeg","nome":"a.jpg","documento_id":"%s"}}' % doc},
    ])
    body = client.get(f"/api/clientes/{cid}/conversa", headers=_auth()).json()
    assert body["chat_id"] == CHAT and body["connection_id"] == cx
    assert [m["direcao"] for m in body["mensagens"]] == ["out", "in"]
    assert body["mensagens"][0]["anexo"] is None
    assert body["mensagens"][1]["anexo"] == {"mime": "image/jpeg", "nome": "a.jpg", "documento_id": doc}


# ─── pedir-documentos ────────────────────────────────────────────────────


def test_texto_is_built_from_the_pending_checklist(client, scoped):
    cid = _cliente(scoped)
    itens = conversa_service.itens_pendentes(scoped, ORG, UUID(cid))
    assert any("RG/CPF" in i and "CNH" in i and "CIN" in i for i in itens), itens
    assert not any("Serasa" in i for i in itens)
    texto = conversa_service.montar_texto("maria souza", itens)
    assert texto.startswith("Olá Maria, para seguirmos precisamos de: ")
    assert itens[0] in texto


def test_sem_conversa_is_a_409_when_there_is_no_chat_and_no_phone(client, scoped):
    cid = _cliente(scoped, chave_canonica=None, chave_tipo=None, celular=None)
    r = client.post(f"/api/clientes/{cid}/conversa/pedir-documentos", json={}, headers=_auth())
    assert r.status_code == 409, r.text
    assert "sem_conversa" in r.text, r.text


class _Store:
    def __init__(self, conn_id):
        self._rec = SimpleNamespace(id=conn_id, org_id=ORG, api_key="k", base_url="http://w",
                                    session_name="default")

    def get_connection(self, **_):
        return self._rec

    def list_connections(self, **_):
        return [self._rec]


class _Waha:
    def __init__(self):
        self.sent = []

    async def send_text(self, chat_id, text):
        self.sent.append((chat_id, text))
        return {"id": "false_x_ABC"}


class _MsgStore:
    def __init__(self, scoped):
        self._s = scoped

    def record(self, **kw):
        row = {"id": str(uuid4()), "org_id": ORG_ID, "structured_payload": None,
               "body": kw["body"], "direction": kw["direction"], "chat_id": kw["chat_id"],
               "created_at": "2026-10-09T11:00:00Z"}
        self._s.table("conversation_messages").insert(row).execute()
        return SimpleNamespace(id=row["id"], provider_message_id=kw.get("provider_message_id"),
                               as_message_dto=lambda: row)


class _ChatStore:
    def record_message(self, **kw):
        return SimpleNamespace(as_dict=lambda: {"chat_id": kw["chat_id"]})


@pytest.fixture
def wa_fakes(client, scoped):
    from app.dependencies import get_settings
    from app.main import app
    from app.routers import whatsapp_connections_router as wa

    conn, waha = uuid4(), _Waha()
    overrides = {
        wa.get_connection_store: lambda: _Store(conn),
        wa.get_waha_client_factory: lambda: (lambda *a, **k: waha),
        wa.get_message_store_factory: lambda: (lambda org: _MsgStore(scoped)),
        wa.get_chat_store_factory: lambda: (lambda org: _ChatStore()),
        wa.get_settings: lambda: SimpleNamespace(redis_url=""),
    }
    app.dependency_overrides.update(overrides)
    yield SimpleNamespace(conn=conn, waha=waha)
    for k in overrides:
        app.dependency_overrides.pop(k, None)


def test_pedir_documentos_sends_the_checklist_text_and_records_the_event(client, scoped, wa_fakes):
    cid = _cliente(scoped)
    _chat(scoped, cid, connection_id=wa_fakes.conn)
    r = client.post(f"/api/clientes/{cid}/conversa/pedir-documentos", json={}, headers=_auth())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["itens_solicitados"] and body["mensagem_id"]
    (chat_id, texto), = wa_fakes.waha.sent
    assert chat_id == CHAT and texto.startswith("Olá Maria, para seguirmos precisamos de: ")
    eventos = conversa_service.eventos_documentos_solicitados(scoped, ORG, UUID(cid))
    assert len(eventos) == 1 and eventos[0]["payload"]["evento"] == "documentos_solicitados"


def test_pedir_documentos_uses_the_given_text(client, scoped, wa_fakes):
    cid = _cliente(scoped)
    _chat(scoped, cid, connection_id=wa_fakes.conn)
    r = client.post(f"/api/clientes/{cid}/conversa/pedir-documentos",
                    json={"texto": "Manda o RG, por favor"}, headers=_auth())
    assert r.status_code == 201, r.text
    assert wa_fakes.waha.sent[0][1] == "Manda o RG, por favor"


def test_pedir_documentos_with_a_phone_and_no_chat_opens_one(client, scoped, wa_fakes):
    cid = _cliente(scoped)
    r = client.post(f"/api/clientes/{cid}/conversa/pedir-documentos", json={}, headers=_auth())
    assert r.status_code == 201, r.text
    assert wa_fakes.waha.sent[0][0] == CHAT


# ─── intake ──────────────────────────────────────────────────────────────


def _png() -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(out, format="PNG")
    return out.getvalue()


def _fields(**kw):
    from noctusai_lib.integrations.documents import IdentityFields

    return IdentityFields(**kw)


class _Reader:
    """Boundary fake: the vision read. `tipo_provavel` is what the content
    classifier (`classificar_tipo_provavel`) concluded."""

    def __init__(self, tipo_provavel=None, error=None):
        self.calls = []
        self._f = _fields(tipo_provavel=tipo_provavel, error=error)

    async def extract(self, content, **kw):
        self.calls.append(kw)
        return self._f


def _tipos(scoped) -> None:
    scoped.set_table_data("cliente_documento_tipos", [
        {"tipo_documento": t, "categoria_lgpd": "identidade", "ativo": True, "identidade": t != "a_classificar"}
        for t in ("a_classificar", "rg", "cnh", "outro")
    ])


async def _run(scoped, reader, *, mime="image/png", dados=None, media_url="http://waha/x", tipo=None):
    _tipos(scoped)
    cid = UUID(_cliente(scoped))
    storage = FakeStorageBackend()
    msg_id = str(uuid4())
    scoped.set_table_data("conversation_messages", [{
        "id": msg_id, "org_id": ORG_ID, "chat_id": CHAT, "direction": "inbound", "body": "[Anexo recebido]",
        "created_at": "2026-10-09T10:00:00Z", "structured_payload": None}])

    async def baixar(url):
        return dados if dados is not None else _png()

    out = await intake.processar_midia(
        scoped, storage, ORG, cid, mensagem_id=msg_id, media_url=media_url, mimetype=mime,
        filename="foto.png", downloader=baixar, extractor_factory=lambda org, t: reader,
    )
    return cid, msg_id, out


@sync
async def test_confident_media_is_typed_inserted_and_extracted(client, scoped):
    reader = _Reader(tipo_provavel="cnh")
    cid, msg_id, out = await _run(scoped, reader)
    assert out["status"] == "extraido" and out["tipo_documento"] == "cnh"
    doc = scoped.table("cliente_documentos").select("*").execute().data[0]
    assert doc["origem_entrada"] == "whatsapp" and doc["tipo_documento"] == "cnh"
    assert doc["classificacao_confianca"] == "alta" and doc["classificacao_tipo_provavel"] == "cnh"
    # classification read + the registry's extraction read both went through the reader
    assert len(reader.calls) == 2
    msg = conversa_service.conversa(scoped, ORG, cid)
    anexo = [m for m in _msgs(scoped, msg_id)][0]
    assert anexo["documento_id"] == doc["id"]


def _msgs(scoped, msg_id):
    import json

    row = [r for r in scoped.table("conversation_messages").select("*").execute().data if r["id"] == msg_id][0]
    sp = row["structured_payload"]
    return [json.loads(sp)["anexo"]] if isinstance(sp, str) else [sp["anexo"]]


@sync
async def test_unknown_media_waits_in_a_classificar_and_is_not_extracted(client, scoped):
    reader = _Reader(tipo_provavel=None)
    cid, _, out = await _run(scoped, reader)
    assert out["status"] == "a_classificar"
    doc = scoped.table("cliente_documentos").select("*").execute().data[0]
    assert doc["tipo_documento"] == "a_classificar" and doc["classificacao_confianca"] == "nenhuma"
    assert len(reader.calls) == 1  # only the classification read
    assert [d["id"] for d in intake.a_classificar(scoped, ORG, cid)] == [doc["id"]]


@sync
async def test_a_failed_classification_read_still_keeps_the_media(client, scoped):
    cid, _, out = await _run(scoped, _Reader(error="boom"))
    assert out["status"] == "a_classificar"
    assert scoped.table("cliente_documentos").select("*").execute().data[0]["classificacao_confianca"] == "baixa"


@sync
async def test_a_refused_media_is_recorded_on_the_message_not_dropped(client, scoped):
    cid, msg_id, out = await _run(scoped, _Reader(), mime="video/mp4", dados=b"\x00\x01")
    assert out["status"] == "recusado"
    assert scoped.table("cliente_documentos").select("*").execute().data == []
    assert _msgs(scoped, msg_id)[0]["motivo"] == "tipo_ou_tamanho_nao_aceito"


@sync
async def test_download_failure_is_recorded(client, scoped):
    _tipos(scoped)
    cid = UUID(_cliente(scoped))

    async def quebra(url):
        raise OSError("down")

    out = await intake.processar_midia(
        scoped, FakeStorageBackend(), ORG, cid, mensagem_id=None, media_url="http://x",
        mimetype="image/png", filename="a.png", downloader=quebra,
        extractor_factory=lambda o, t: _Reader(),
    )
    assert out["status"] == "erro" and out["motivo"] == "download_falhou"


@sync
async def test_heic_is_converted_to_jpeg(client, scoped):
    from PIL import Image
    from pillow_heif import from_pillow  # noqa: F401  (registers encoder via pillow_heif)
    import pillow_heif

    heic = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (8, 8), "red")).save(heic)
    cid, _, out = await _run(scoped, _Reader(), mime="image/heic", dados=heic.getvalue())
    assert out["status"] == "a_classificar"
    doc = scoped.table("cliente_documentos").select("*").execute().data[0]
    assert doc["mime_type"] == "image/jpeg" and doc["nome_original"].endswith(".jpg")


@sync
async def test_classificar_manualmente_types_the_doc_and_queues_extraction(client, scoped):
    reader = _Reader()
    cid, _, _ = await _run(scoped, reader)
    doc_id = UUID(scoped.table("cliente_documentos").select("*").execute().data[0]["id"])
    out = intake.classificar_manualmente(scoped, ORG, cid, doc_id, "rg")
    assert out["tipo_documento"] == "rg" and out["extracao_status"] == "pendente"
    row = scoped.table("cliente_documentos").select("*").execute().data[0]
    assert row["tipo_documento"] == "rg" and row["extracao_status"] == "pendente"
    from noctusai_lib.primitives.exceptions import ValidationError_

    with pytest.raises(ValidationError_):  # already typed
        intake.classificar_manualmente(scoped, ORG, cid, doc_id, "cnh")


def test_classificar_route_refuses_an_unextractable_type(client, scoped, fake_storage, fake_identity_extractor):
    _tipos(scoped)
    cid = _cliente(scoped)
    scoped.set_table_data("cliente_documentos", [{
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "tipo_documento": "a_classificar",
        "storage_path": "p", "nome_original": "a.png", "mime_type": "image/png", "tamanho_bytes": 1,
        "categoria_lgpd": "identidade", "deleted_at": None}])
    did = scoped.table("cliente_documentos").select("*").execute().data[0]["id"]
    r = client.post(f"/api/clientes/{cid}/documentos/{did}/classificar",
                    json={"tipo_documento": "outro"}, headers=_auth())
    assert r.status_code == 400, r.text


# ─── the single extraction seam ──────────────────────────────────────────


def test_registry_covers_every_extractable_type_and_refuses_the_rest():
    from app.modules.card_hub import identidade_extracao_service as svc

    for tipo in svc.TIPOS_EXTRAIVEIS:
        assert callable(registry.extrator_para(tipo))
    for tipo in ("a_classificar", "outro"):
        with pytest.raises(registry.TipoNaoExtraivel):
            registry.extrator_para(tipo)


def test_registry_replacement_is_honoured_for_one_type_only():
    async def parser(*a, **k):
        return {"via": "parser"}

    registry.registrar("rg", parser)
    try:
        assert registry.extrator_para("rg") is parser
        assert registry.extrator_para("cnh") is not parser
    finally:
        registry._REGISTRO.pop("rg", None)


def test_a_person_cannot_file_an_upload_under_a_classificar(client, scoped, fake_storage, fake_identity_extractor):
    _tipos(scoped)
    cid = _cliente(scoped)
    r = client.post(
        f"/api/clientes/{cid}/documentos",
        files={"file": ("a.png", _png(), "image/png")},
        data={"tipo_documento": "a_classificar"},
        headers=_auth(),
    )
    assert r.status_code == 400, r.text
