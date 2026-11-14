"""ImobShotAI backend v1 — IMOBSHOTAI-CONTRACT.md §1-§6 (routes, gate, D6, etapa projection, events).

DI seams only (`harness.imobshot` = the in-memory card store joined to the photo engine's in-memory repository,
`harness.imovel_lookup` = the imóvel registry double): nothing of ours is monkey-patched."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from noctusai_lib.domain.jobs import Worker
from noctusai_lib.domain.photo_editing import PhotoStatus, build_handlers

from app.modules.imobshotai.etapa import derivar_etapa
from app.modules.imobshotai.worker_hook import wrap_lote_pronto

from .conftest import ORG, USERS

P = PhotoStatus
_ID = str(uuid4())


def _iniciar(edicao, codigo="ONE8990", **extra):
    return edicao.http.post("/api/imobshotai/lotes", json={"imovel_codigo": codigo, **extra})


def _ready(edicao) -> None:
    edicao.configure_org()
    edicao.activate_guide()


def _eventos(edicao, card_id: str) -> list[str]:
    return [e.tipo for cid, e in edicao.imobshot.events if cid == card_id]


def _hook_drain(edicao) -> None:
    """Drain the queue with the SAME handler wrapping the production worker uses."""
    worker = Worker(
        edicao.ports.jobs,
        worker_id="test-worker",
        handlers=wrap_lote_pronto(build_handlers(edicao.ports), edicao.ports, lambda: edicao.imobshot),
        retry_policy=edicao.ports.config.retry_policy(),
        poll_interval_seconds=0.0,
    )

    async def _go() -> None:
        for _ in range(500):
            if not await worker.run_once():
                return

    asyncio.run(_go())


def _enviar_e_processar(edicao, owner="corretor", codigo="ONE8990") -> tuple[str, str, str]:
    """Create via ImobShotAI, upload one photo, submit, run the pipeline. Returns (card_id, lote_id, foto_id)."""
    edicao.as_user(owner)
    body = _iniciar(edicao, codigo).json()
    lote_id = body["lote"]["id"]
    foto_id = edicao.add_photo(lote_id)
    assert edicao.http.post(f"/api/edicao-fotos/lotes/{lote_id}/submeter").status_code == 200
    _hook_drain(edicao)
    return body["card"]["id"], lote_id, foto_id


# --- auth + role ---------------------------------------------------------

_ROTAS = [
    ("post", "/api/imobshotai/lotes", {"imovel_codigo": "ONE1"}),
    ("get", "/api/imobshotai/cards", None),
    ("get", f"/api/imobshotai/cards/{_ID}", None),
]


def test_every_route_is_mounted_and_listed() -> None:
    from app.modules.imobshotai import register

    mounted = {
        (m.lower(), r.path)
        for router in register().routers for r in router.routes for m in getattr(r, "methods", set())
    }
    assert mounted == {("post", "/api/imobshotai/lotes"), ("get", "/api/imobshotai/cards"),
                       ("get", "/api/imobshotai/cards/{card_id}")}


@pytest.mark.parametrize("method,path,body", _ROTAS, ids=lambda v: str(v))
def test_unauthenticated_is_strictly_401(anon_client, method, path, body) -> None:
    resp = getattr(anon_client, method)(path, **({"json": body} if body else {}))
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path,body", _ROTAS, ids=lambda v: str(v))
def test_non_member_is_403(edicao, method, path, body) -> None:
    edicao.as_user("viewer")
    resp = getattr(edicao.http, method)(path, **({"json": body} if body else {}))
    assert resp.status_code == 403 and resp.json()["code"] == "sem_acesso_edicao_fotos"


def test_unknown_body_field_is_422(edicao) -> None:
    _ready(edicao)
    assert _iniciar(edicao.as_user("corretor"), extra="x").status_code == 422


# --- §1 / §2: imóvel existence ------------------------------------------


def test_iniciar_refuses_an_unknown_imovel_and_leaves_nothing_behind(edicao) -> None:
    _ready(edicao)
    resp = _iniciar(edicao.as_user("corretor"), "naoexiste")
    assert resp.status_code == 422 and resp.json()["code"] == "imovel_inexistente"
    assert edicao.imobshot.cards == {} and edicao.repo.batches == {}


def test_plain_lote_route_also_refuses_an_unknown_imovel(edicao) -> None:
    _ready(edicao)
    resp = edicao.as_user("corretor").http.post(
        "/api/edicao-fotos/lotes", json={"nome": "x", "imovel": {"org_id": ORG, "codigo": "NAOEXISTE"}}
    )
    assert resp.status_code == 422 and resp.json()["code"] == "imovel_inexistente"
    assert edicao.repo.batches == {}


def test_plain_lote_route_without_imovel_is_unchanged(edicao) -> None:
    _ready(edicao)
    resp = edicao.as_user("corretor").http.post("/api/edicao-fotos/lotes", json={"nome": "x"})
    assert resp.status_code == 201


def test_iniciar_keeps_the_lote_route_errors(edicao) -> None:
    edicao.as_user("corretor")
    resp = _iniciar(edicao)
    assert resp.status_code == 422 and resp.json()["code"] == "modelo_nao_configurado"
    assert edicao.imobshot.cards == {}


# --- §1: get-or-create ----------------------------------------------------


def test_iniciar_twice_is_one_card_two_lotes_one_card_criado(edicao) -> None:
    _ready(edicao)
    edicao.as_user("corretor")
    a, b = _iniciar(edicao, "one8990"), _iniciar(edicao, " ONE8990 ", nome="Segunda rodada")
    assert a.status_code == b.status_code == 201, (a.text, b.text)
    assert a.json()["card"]["id"] == b.json()["card"]["id"]
    assert a.json()["card"]["imovel"]["codigo"] == "ONE8990"
    assert len(edicao.imobshot.cards) == 1 and len(edicao.repo.batches) == 2
    card_id = a.json()["card"]["id"]
    assert _eventos(edicao, card_id) == ["card_criado", "lote_vinculado", "lote_vinculado"]
    assert all(edicao.imobshot.card_id_do_lote(l) == card_id for l in edicao.repo.batches)
    lote = a.json()["lote"]
    assert lote["imovel"] == {"org_id": ORG, "codigo": "ONE8990"} and lote["status"] == "rascunho"
    assert a.json()["card"]["etapa"] == "fotos_enviadas"
    assert edicao.repo.batches[lote["id"]].origem == "vista"


def test_default_name_uses_the_codigo(edicao) -> None:
    _ready(edicao)
    nome = _iniciar(edicao.as_user("corretor")).json()["lote"]["nome"]
    assert nome.startswith("Fotos ONE8990 ")


# --- §6: the etapa table --------------------------------------------------


@pytest.mark.parametrize(
    "lotes,esperada",
    [
        ([], "fotos_enviadas"),
        ([("rascunho", [])], "fotos_enviadas"),
        ([("rascunho", [P.RECEBIDA, P.PRONTA])], "fotos_enviadas"),
        ([("submetido", [P.RECEBIDA])], "fotos_em_edicao"),
        ([("processando", [P.EDITANDO, P.AGUARDANDO_DECISAO])], "fotos_em_edicao"),
        ([("processando", [P.EM_LOTE_OPENAI])], "fotos_em_edicao"),
        ([("submetido", [])], "fotos_em_edicao"),
        ([("pronto", [P.AGUARDANDO_DECISAO, P.APROVADA])], "fotos_em_revisao"),
        ([("pronto", [P.AGUARDANDO_DECISAO, P.FALHOU])], "fotos_em_revisao"),
        ([("pronto", [P.APROVADA, P.REJEITADA, P.FALHOU])], "fotos_aprovadas"),
        ([("pronto", [P.APROVADA]), ("rascunho", [P.RECEBIDA])], "fotos_aprovadas"),
        ([("pronto", [P.APROVADA]), ("submetido", [P.RECEBIDA])], "fotos_em_edicao"),
        ([("pronto", [P.REJEITADA, P.FALHOU])], "fotos_enviadas"),
    ],
)
def test_etapa_table(lotes, esperada) -> None:
    assert derivar_etapa(lotes) == esperada


def test_etapa_follows_the_real_pipeline_and_records_each_change_once(edicao) -> None:
    _ready(edicao)
    card_id, lote_id, foto_id = _enviar_e_processar(edicao)
    card = edicao.imobshot.cards[card_id]
    assert card.etapa == "fotos_em_revisao"
    assert _eventos(edicao, card_id) == ["card_criado", "lote_vinculado", "etapa_mudou", "etapa_mudou"]
    muda = [e for cid, e in edicao.imobshot.events if cid == card_id and e.tipo == "etapa_mudou"]
    assert [(e.etapa_de, e.etapa_para) for e in muda] == [
        ("fotos_enviadas", "fotos_em_edicao"), ("fotos_em_edicao", "fotos_em_revisao")]

    edicao.as_user("admin")
    resp = edicao.http.post(
        f"/api/edicao-fotos/revisao/{lote_id}/fotos/{foto_id}/decisao", json={"decisao": "aprovar"})
    assert resp.status_code == 200, resp.text
    card = edicao.imobshot.cards[card_id]
    assert card.etapa == "fotos_aprovadas" and card.fotos_concluidas_at is not None
    assert card.capa_foto_id == foto_id
    assert _eventos(edicao, card_id)[-1] == "etapa_mudou"

    # Nothing changed: a re-sync writes no event.
    antes = len(edicao.imobshot.events)
    from app.modules.imobshotai.service import sincronizar_etapa

    assert asyncio.run(sincronizar_etapa(edicao.imobshot, edicao.ports, card_id, ator_id=None)) is False
    assert len(edicao.imobshot.events) == antes

    # Changing the decision re-projects: rejecting the only photo drops the card back.
    resp = edicao.http.post(
        f"/api/edicao-fotos/revisao/{lote_id}/fotos/{foto_id}/decisao",
        json={"decisao": "rejeitar", "comentario": "ruim"})
    assert resp.status_code == 200
    assert edicao.imobshot.cards[card_id].etapa == "fotos_enviadas"
    assert edicao.imobshot.cards[card_id].capa_foto_id is None


def test_retry_resyncs_the_card(edicao) -> None:
    _ready(edicao)
    card_id, lote_id, foto_id = _enviar_e_processar(edicao)
    # Arrange the in-memory table (the retry route only accepts `falhou`; the state machine has no path there from
    # here), then let the route move the photo back into the pipeline.
    import dataclasses

    edicao.repo.photos[foto_id] = dataclasses.replace(edicao.repo.photos[foto_id], status=PhotoStatus.FALHOU)
    edicao.as_user("corretor")
    resp = edicao.http.post(f"/api/edicao-fotos/lotes/{lote_id}/fotos/{foto_id}/retentar")
    assert resp.status_code == 200, resp.text
    assert edicao.imobshot.cards[card_id].etapa == "fotos_em_edicao"


def test_a_plain_lote_never_creates_card_events(edicao) -> None:
    _ready(edicao)
    lote = edicao.make_batch("corretor")
    edicao.add_photo(lote)
    edicao.as_user("corretor")
    assert edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/submeter").status_code == 200
    assert edicao.imobshot.cards == {} and edicao.imobshot.events == []


# --- §5 D6 ----------------------------------------------------------------


def test_corretor_cannot_decide_on_a_card_lote_but_admin_can(edicao) -> None:
    _ready(edicao)
    card_id, lote_id, foto_id = _enviar_e_processar(edicao, owner="corretor")
    url = f"/api/edicao-fotos/revisao/{lote_id}/fotos/{foto_id}/decisao"
    resp = edicao.as_user("corretor").http.post(url, json={"decisao": "aprovar"})
    assert resp.status_code == 403 and resp.json()["code"] == "restrito_admin_organizacao"
    assert edicao.imobshot.cards[card_id].etapa == "fotos_em_revisao"
    assert edicao.as_user("admin").http.post(url, json={"decisao": "aprovar"}).status_code == 200


def test_corretor_still_decides_on_a_plain_lote(edicao) -> None:
    _ready(edicao)
    lote = edicao.make_batch("corretor")
    foto = edicao.add_photo(lote)
    edicao.as_user("corretor")
    edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/submeter")
    edicao.drain()
    resp = edicao.http.post(f"/api/edicao-fotos/revisao/{lote}/fotos/{foto}/decisao", json={"decisao": "aprovar"})
    assert resp.status_code == 200


# --- §3 / §4: reads --------------------------------------------------------


def test_404_for_a_card_of_another_org_and_for_a_corretor_who_cannot_see_it(edicao) -> None:
    _ready(edicao)
    card_id = _iniciar(edicao.as_user("corretor")).json()["card"]["id"]
    for who in ("outra_admin", "corretor2"):
        resp = edicao.as_user(who).http.get(f"/api/imobshotai/cards/{card_id}")
        assert resp.status_code == 404 and resp.json()["code"] == "card_nao_encontrado", who
    assert edicao.as_user("admin").http.get(f"/api/imobshotai/cards/{card_id}").status_code == 200
    assert edicao.as_user("corretor").http.get(f"/api/imobshotai/cards/{card_id}").status_code == 200
    assert edicao.http.get(f"/api/imobshotai/cards/{uuid4()}").status_code == 404


def test_board_visibility_filters_and_paging(edicao) -> None:
    _ready(edicao)
    _iniciar(edicao.as_user("corretor"), "ONE1")
    _iniciar(edicao.as_user("corretor2"), "ONE2")
    _iniciar(edicao.as_user("corretor2"), "XYZ9")

    lista = lambda **q: edicao.http.get("/api/imobshotai/cards", params=q).json()  # noqa: E731
    edicao.as_user("corretor")
    assert {c["imovel"]["codigo"] for c in lista()["items"]} == {"ONE1"}  # corretor: own only
    assert {c["imovel"]["codigo"] for c in edicao.as_user("corretor2").http.get("/api/imobshotai/cards").json()["items"]} == {"ONE2", "XYZ9"}
    edicao.as_user("admin")
    todos = lista()
    assert todos["total"] == 3 and todos["page"] == 1 and todos["page_size"] == 50
    assert {c["imovel"]["codigo"] for c in lista(q="one")["items"]} == {"ONE1", "ONE2"}
    assert lista(etapa="fotos_aprovadas")["items"] == []
    pg = lista(page_size=2, page=2)
    assert len(pg["items"]) == 1 and pg["total"] == 3
    assert edicao.http.get("/api/imobshotai/cards", params={"etapa": "nope"}).status_code == 422
    assert edicao.http.get("/api/imobshotai/cards", params={"page_size": 101}).status_code == 422
    item = todos["items"][0]
    assert set(item) == {"id", "imovel", "etapa", "etapa_desde", "capa_url", "total_fotos", "fotos_aprovadas",
                         "total_videos", "criado_em", "atualizado_em"}
    assert item["imovel"] == {"org_id": ORG, "codigo": item["imovel"]["codigo"],
                              "titulo": f"Imóvel {item['imovel']['codigo']}", "bairro": "Centro"}


def test_board_reads_are_batched_not_n_plus_one(edicao) -> None:
    _ready(edicao)
    for i in range(4):
        _iniciar(edicao.as_user("admin"), f"ONE{i}")
    chamadas: list[list[str]] = []
    original = edicao.imovel_lookup

    def contado(org, codigos):
        chamadas.append(codigos)
        return original(org, codigos)

    from app.main import app
    from app.modules.edicao_fotos.deps import get_imovel_lookup

    app.dependency_overrides[get_imovel_lookup] = lambda: contado
    try:
        assert edicao.http.get("/api/imobshotai/cards").json()["total"] == 4
    finally:
        app.dependency_overrides[get_imovel_lookup] = lambda: edicao.imovel_lookup
    assert len(chamadas) == 1 and sorted(chamadas[0]) == ["ONE0", "ONE1", "ONE2", "ONE3"]


def test_detail_shape_lists_lotes_fotos_and_events_newest_first(edicao) -> None:
    _ready(edicao)
    card_id, lote_id, foto_id = _enviar_e_processar(edicao)
    edicao.as_user("admin")
    edicao.http.post(f"/api/edicao-fotos/revisao/{lote_id}/fotos/{foto_id}/decisao", json={"decisao": "aprovar"})
    segundo = _iniciar(edicao, nome="Segunda").json()["lote"]["id"]
    body = edicao.http.get(f"/api/imobshotai/cards/{card_id}").json()
    assert body["id"] == card_id and body["videos"] == []
    assert [l["id"] for l in body["lotes"]] == [segundo, lote_id]
    assert body["total_fotos"] == 1 and body["fotos_aprovadas"] == 1
    [foto] = body["fotos"]
    assert set(foto) == {"id", "lote_id", "comodo", "status", "original_url", "editada_url"}
    assert foto["id"] == foto_id and foto["status"] == "aprovada" and foto["comodo"] is None
    assert foto["original_url"] and foto["editada_url"] and body["capa_url"] == foto["editada_url"]
    tipos = [e["tipo"] for e in body["eventos"]]
    assert tipos[0] == "lote_vinculado" and tipos[-1] == "card_criado" and len(tipos) <= 50
    assert set(body["eventos"][0]) == {"tipo", "etapa_de", "etapa_para", "ator_id", "em", "detalhe"}
    assert body["eventos"][0]["detalhe"] == {"lote_id": segundo}


# --- the production worker hook -------------------------------------------


def test_lote_pronto_job_syncs_the_card_and_a_sync_failure_does_not_fail_the_job(edicao) -> None:
    _ready(edicao)
    edicao.as_user("corretor")
    body = _iniciar(edicao).json()
    lote_id, card_id = body["lote"]["id"], body["card"]["id"]
    edicao.add_photo(lote_id)
    # Submit through the engine (not the route), so ONLY the worker hook can move the card.
    from noctusai_lib.domain.photo_editing import submit_batch

    asyncio.run(submit_batch(edicao.ports, lote_id, submitted_by=USERS["corretor"].id))
    assert edicao.imobshot.cards[card_id].etapa == "fotos_enviadas"
    _hook_drain(edicao)
    assert edicao.imobshot.cards[card_id].etapa == "fotos_em_revisao"


def test_sync_failure_is_contained_by_the_call_sites(edicao) -> None:
    _ready(edicao)
    lote = _iniciar(edicao.as_user("corretor")).json()["lote"]["id"]
    edicao.add_photo(lote)

    class Quebrado:
        def card_id_do_lote(self, lote_id):
            raise RuntimeError("db down")

    from app.modules.imobshotai.service import sincronizar_do_lote

    assert asyncio.run(sincronizar_do_lote(Quebrado(), edicao.ports, lote, ator_id=None)) is False


# --- contract E2E shape (IMOBSHOTAI-CONTRACT.md §1, §3, §4) -----------------

_CARD_RESUMO = {"id", "imovel", "etapa", "etapa_desde", "capa_url", "total_fotos", "fotos_aprovadas",
                "total_videos", "criado_em", "atualizado_em"}
_IMOVEL = {"org_id", "codigo", "titulo", "bairro"}
_LOTE_RESUMO = {"id", "nome", "criado_em", "imovel", "velocidade", "estado_agregado", "total_fotos",
                "fotos_decididas", "status"}
_FOTO = {"id", "lote_id", "comodo", "status", "original_url", "editada_url"}
_EVENTO = {"tipo", "etapa_de", "etapa_para", "ator_id", "em", "detalhe"}


def test_contract_shapes_through_the_app(edicao) -> None:
    _ready(edicao)
    card_id, lote_id, foto_id = _enviar_e_processar(edicao)
    edicao.as_user("admin")
    edicao.http.post(f"/api/edicao-fotos/revisao/{lote_id}/fotos/{foto_id}/decisao", json={"decisao": "aprovar"})

    # §1  POST /lotes -> {card, lote}
    novo = _iniciar(edicao, "ONE8990", nome="Terceira")
    assert novo.status_code == 201
    body = novo.json()
    assert set(body) == {"card", "lote"}
    assert set(body["card"]) == _CARD_RESUMO and set(body["card"]["imovel"]) == _IMOVEL
    assert set(body["lote"]) == _LOTE_RESUMO and set(body["lote"]["imovel"]) == {"org_id", "codigo"}

    # §3  GET /cards -> page_out of CardResumo
    page = edicao.http.get("/api/imobshotai/cards").json()
    assert set(page) == {"items", "page", "page_size", "total"}
    assert page["items"] and all(set(i) == _CARD_RESUMO and set(i["imovel"]) == _IMOVEL for i in page["items"])

    # §4  GET /cards/{id} -> CardDetalhe (CardResumo + lotes/fotos/videos/eventos)
    det = edicao.http.get(f"/api/imobshotai/cards/{card_id}").json()
    assert set(det) == _CARD_RESUMO | {"lotes", "fotos", "videos", "eventos"}
    assert set(det["imovel"]) == _IMOVEL and det["videos"] == []
    assert det["lotes"] and all(set(l) == _LOTE_RESUMO for l in det["lotes"])
    assert det["fotos"] and all(set(f) == _FOTO for f in det["fotos"])
    assert det["eventos"] and all(set(e) == _EVENTO for e in det["eventos"])


def test_error_body_shape_for_imovel_inexistente(edicao) -> None:
    _ready(edicao)
    resp = _iniciar(edicao.as_user("corretor"), "naoexiste")
    assert resp.status_code == 422
    # `api_error` raises HTTPException(detail={"detail": msg, "code": code}); the seed's http_exception_handler passes
    # a machine-error dict through verbatim, so on the wire the body is FLAT: {"detail": "<pt-BR>", "code": "..."}.
    # (IMOBSHOTAI-CONTRACT.md §0 writes it nested under an outer "detail"; the FE reads `code` from the body root.)
    assert resp.json() == {"detail": "Nenhum imóvel com esse código.", "code": "imovel_inexistente"}
