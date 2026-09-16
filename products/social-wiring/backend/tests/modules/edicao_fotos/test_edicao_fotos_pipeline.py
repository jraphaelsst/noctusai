"""Route-level behaviour: create → upload / Vista → submit → (seed Worker)
→ review → decide → zip, plus every refusal the contract names.

`route-exists ≠ wired`: the pipeline test drives the REAL seed engine and
Worker over the same ports the routes use, and asserts the writes."""
from __future__ import annotations

import io
import zipfile

from noctusai_lib.domain.photo_editing import PhotoStatus, Speed
from noctusai_lib.domain.real_estate.imovel import ImovelFoto

from app.modules.edicao_fotos.routers.lotes import (
    MAX_FILES_PER_REQUEST,
    UPLOAD_ROUTE_MAX_BODY_BYTES,
)

from .conftest import JPEG, ORG, OTHER_ORG, USERS


def _create(edicao, nome="Casa Azul", **extra):
    return edicao.http.post("/api/edicao-fotos/lotes", json={"nome": nome, **extra})


# --- create -------------------------------------------------------------


def test_create_is_blocked_without_model_or_edit_types(edicao) -> None:
    edicao.as_user("corretor")
    resp = _create(edicao)
    assert resp.status_code == 422 and resp.json()["code"] == "modelo_nao_configurado"
    edicao.configure_org(tipos_edicao_ativos=())
    resp = _create(edicao)
    assert resp.status_code == 422 and resp.json()["code"] == "sem_tipos_edicao"


def test_create_refuses_economico_with_the_contract_code(edicao) -> None:
    edicao.configure_org(velocidade_override=Speed.ECONOMICO)
    resp = _create(edicao.as_user("corretor"))
    assert resp.status_code == 422
    assert resp.json()["code"] == "economico_indisponivel"
    assert edicao.repo.batches == {}


def test_create_records_creator_org_speed_and_imovel(edicao) -> None:
    edicao.configure_org()
    resp = _create(edicao.as_user("corretor"), imovel={"org_id": ORG, "codigo": "CA2830"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    batch = edicao.repo.batches[body["id"]]
    assert (batch.org_id, batch.criado_por) == (ORG, USERS["corretor"].id)
    assert batch.velocidade is Speed.URGENTE and batch.origem == "vista"
    assert body["imovel"] == {"org_id": ORG, "codigo": "CA2830"}
    assert body["total_fotos"] == 0


def test_create_refuses_an_imovel_of_another_org(edicao) -> None:
    edicao.configure_org()
    resp = _create(edicao.as_user("corretor"), imovel={"org_id": OTHER_ORG, "codigo": "X1"})
    assert resp.status_code == 422 and resp.json()["code"] == "imovel_outra_organizacao"


def test_create_rejects_unknown_fields(edicao) -> None:
    edicao.configure_org()
    resp = _create(edicao.as_user("corretor"), velocidade="economico")
    assert resp.status_code == 422
    assert edicao.repo.batches == {}


def test_list_is_own_for_corretor_and_org_wide_for_admins(edicao) -> None:
    a = edicao.make_batch("corretor", nome="a")
    b = edicao.make_batch("corretor2", nome="b")
    own = edicao.as_user("corretor").http.get("/api/edicao-fotos/lotes").json()
    assert [i["id"] for i in own["items"]] == [a] and own["total"] == 1
    for admin in ("admin", "gerente", "plataforma"):
        page = edicao.as_user(admin).http.get("/api/edicao-fotos/lotes?page_size=1").json()
        assert page["total"] == 2 and page["page_size"] == 1 and len(page["items"]) == 1
        assert page["items"][0]["id"] in {a, b}


# --- upload -------------------------------------------------------------


def test_upload_stores_photos_and_enqueues_ingest(edicao) -> None:
    edicao.configure_org()
    lote = edicao.make_batch("corretor")
    resp = edicao.as_user("corretor").upload(lote, 3)
    assert resp.status_code == 201, resp.text
    fotos = resp.json()["fotos"]
    assert [f["ordem"] for f in fotos] == [1, 2, 3]
    assert all(f["estado"] == "recebida" and f["url_antes"] for f in fotos)
    keys = edicao.run(edicao.backend.list_keys(bucket="edicao-fotos", prefix=f"{ORG}/{lote}/"))
    assert len(keys) == 3
    assert edicao.drain() == 3  # one ingest job per photo
    detail = edicao.http.get(f"/api/edicao-fotos/lotes/{lote}").json()
    assert [f["estado"] for f in detail["fotos"]] == ["pronta"] * 3
    assert (detail["total_fotos"], detail["estado_agregado"]) == (3, "rascunho")


def test_upload_limits(edicao) -> None:
    edicao.configure_org(limite_bytes_por_foto=10, limite_fotos_por_lote=2)
    lote = edicao.make_batch("corretor")
    edicao.as_user("corretor")
    too_big = edicao.upload(lote, 1, data=b"x" * 11)
    assert too_big.status_code == 413 and too_big.json()["code"] == "arquivo_grande_demais"
    too_many = edicao.upload(lote, 3, data=b"x")
    assert too_many.status_code == 409 and too_many.json()["code"] == "lote_cheio"
    bad_ext = edicao.upload(lote, 1, name="foto.gif", data=b"x")
    assert bad_ext.status_code == 415 and bad_ext.json()["code"] == "formato_nao_suportado"
    no_ext = edicao.http.post(
        f"/api/edicao-fotos/lotes/{lote}/fotos", files=[("fotos", ("semextensao", b"x", "image/jpeg"))]
    )
    assert no_ext.status_code == 415
    assert edicao.repo.photos == {}  # nothing half-stored


def test_upload_per_request_cap_and_body_ceiling_agree(edicao) -> None:
    from app.main import _MAX_BODY_PATH_OVERRIDES
    from noctusai_lib.domain.photo_editing.types import MAX_BYTES_PER_PHOTO

    assert _MAX_BODY_PATH_OVERRIDES["/api/edicao-fotos/lotes/*/fotos"] == UPLOAD_ROUTE_MAX_BODY_BYTES
    assert MAX_FILES_PER_REQUEST * MAX_BYTES_PER_PHOTO < UPLOAD_ROUTE_MAX_BODY_BYTES
    edicao.configure_org()
    lote = edicao.make_batch("corretor")
    resp = edicao.as_user("corretor").upload(lote, MAX_FILES_PER_REQUEST + 1)
    assert resp.status_code == 422 and resp.json()["code"] == "muitos_arquivos"


def test_upload_after_submit_is_409(edicao) -> None:
    edicao.configure_org()
    edicao.activate_guide()
    lote = edicao.make_batch("corretor")
    edicao.add_photo(lote)
    edicao.as_user("corretor")
    assert edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/submeter").status_code == 200
    resp = edicao.upload(lote, 1)
    assert resp.status_code == 409 and resp.json()["code"] == "lote_ja_submetido"


# --- Vista --------------------------------------------------------------


def test_vista_pull_orders_destaque_first_and_is_idempotent(edicao) -> None:
    edicao.configure_org()
    lote = edicao.make_batch("corretor")
    edicao.vista.galleries["CA2830"] = [
        ImovelFoto(codigo="12", url="https://cdn/12.jpg"),
        ImovelFoto(codigo="3", url="https://cdn/3.jpg"),
        ImovelFoto(codigo="7", url="https://cdn/7.jpg", destaque=True),
        ImovelFoto(codigo="9", url=None),
    ]
    edicao.vista.failing_urls.add("https://cdn/3.jpg")
    edicao.as_user("corretor")
    first = edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/vista", json={"codigo": "CA2830"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["encontradas"] == 3 and body["adicionadas"] == 2
    assert body["falhas"] == [{"codigo": "3", "motivo": "HTTP 404"}]
    photos = edicao.run(edicao.repo.list_photos(lote))
    assert [(p.ordem, p.vista_codigo) for p in photos] == [(1, "7"), (2, "12")]
    again = edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/vista", json={"codigo": "CA2830"}).json()
    assert again["adicionadas"] == 0 and again["ja_no_lote"] == 2


def test_vista_pull_stops_at_the_batch_limit(edicao) -> None:
    edicao.configure_org(limite_fotos_por_lote=1)
    lote = edicao.make_batch("corretor")
    edicao.vista.galleries["X"] = [ImovelFoto(codigo=str(i), url=f"https://cdn/{i}.jpg") for i in (1, 2)]
    body = edicao.as_user("corretor").http.post(
        f"/api/edicao-fotos/lotes/{lote}/vista", json={"codigo": "X"}
    ).json()
    assert body["adicionadas"] == 1 and body["interrompido"] == "lote_cheio"


def test_vista_pull_with_no_gallery_is_404(edicao) -> None:
    lote = edicao.make_batch("corretor")
    resp = edicao.as_user("corretor").http.post(
        f"/api/edicao-fotos/lotes/{lote}/vista", json={"codigo": "NADA"}
    )
    assert resp.status_code == 404 and resp.json()["code"] == "imovel_sem_fotos"


def test_vista_unconfigured_is_503(edicao, override_settings) -> None:
    from app.modules.edicao_fotos.deps import get_vista_photo_source

    edicao.app.dependency_overrides.pop(get_vista_photo_source)
    override_settings(crm_base_url="", crm_api_key="")
    lote = edicao.make_batch("corretor")
    resp = edicao.as_user("corretor").http.post(
        f"/api/edicao-fotos/lotes/{lote}/vista", json={"codigo": "CA1"}
    )
    assert resp.status_code == 503 and resp.json()["code"] == "vista_nao_configurado"


# --- submit + full pipeline + review + zip -------------------------------


def test_submit_without_active_guide_is_409(edicao) -> None:
    edicao.configure_org()
    lote = edicao.make_batch("corretor")
    edicao.add_photo(lote)
    resp = edicao.as_user("corretor").http.post(f"/api/edicao-fotos/lotes/{lote}/submeter")
    assert resp.status_code == 409 and resp.json()["code"] == "guia_nao_ativo"


def test_submit_empty_batch_is_409(edicao) -> None:
    edicao.configure_org()
    edicao.activate_guide()
    lote = edicao.make_batch("corretor")
    resp = edicao.as_user("corretor").http.post(f"/api/edicao-fotos/lotes/{lote}/submeter")
    assert resp.status_code == 409 and resp.json()["code"] == "lote_vazio"


def test_submit_refuses_economico_batch(edicao) -> None:
    edicao.configure_org()
    edicao.activate_guide()
    lote = edicao.make_batch("corretor")
    edicao.add_photo(lote)
    edicao.repo.batches[lote] = edicao.repo.batches[lote].__class__(
        **{**edicao.repo.batches[lote].__dict__, "velocidade": Speed.ECONOMICO}
    )
    resp = edicao.as_user("corretor").http.post(f"/api/edicao-fotos/lotes/{lote}/submeter")
    assert resp.status_code == 422 and resp.json()["code"] == "economico_indisponivel"


def test_full_run_review_decide_and_zip(edicao) -> None:
    edicao.configure_org()
    edicao.activate_guide()
    edicao.as_user("corretor")
    lote = _create(edicao, nome="Casa/Azul").json()["id"]
    assert edicao.upload(lote, 2).status_code == 201
    submitted = edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/submeter")
    assert submitted.status_code == 200 and submitted.json()["status"] == "submetido"
    edicao.drain()
    photos = edicao.run(edicao.repo.list_photos(lote))
    assert {p.status for p in photos} == {PhotoStatus.AGUARDANDO_DECISAO}
    assert edicao.repo.batches[lote].status.value == "pronto"
    [notice] = edicao.notifier.notices
    assert notice.criado_por == USERS["corretor"].id and notice.aguardando_decisao == 2

    # zip is refused until every photo is decided
    early = edicao.http.get(f"/api/edicao-fotos/lotes/{lote}/zip")
    assert early.status_code == 409 and early.json()["code"] == "lote_nao_decidido"

    listed = edicao.http.get("/api/edicao-fotos/lotes").json()["items"]
    assert [(i["estado_agregado"], i["total_fotos"], i["fotos_decididas"]) for i in listed] == [
        ("aguardando_revisao", 2, 0)
    ]
    review = edicao.http.get(f"/api/edicao-fotos/revisao/{lote}").json()
    assert len(review) == 2
    for item in review:
        assert "avaliacao" not in item  # absent, not null
        assert item["url_antes"] and item["url_depois"]
        assert item["decisao"] is None and item["estado"] == "aguardando_decisao"
    first, second = (i["id"] for i in review)

    no_comment = edicao.http.post(
        f"/api/edicao-fotos/revisao/{lote}/fotos/{second}/decisao", json={"decisao": "rejeitar"}
    )
    assert no_comment.status_code == 422 and no_comment.json()["code"] == "comentario_obrigatorio"

    ok = edicao.http.post(f"/api/edicao-fotos/revisao/{lote}/fotos/{first}/decisao", json={"decisao": "aprovar"})
    assert ok.status_code == 200 and ok.json()["estado"] == "aprovada"
    rej = edicao.http.post(
        f"/api/edicao-fotos/revisao/{lote}/fotos/{second}/decisao",
        json={"decisao": "rejeitar", "comentario": "Céu artificial demais"},
    )
    assert rej.status_code == 200 and rej.json()["comentario"] == "Céu artificial demais"
    assert rej.json()["decisao"] == "rejeitar"
    assert len(edicao.repo.decisions) == 2 and len(edicao.repo.dataset) == 2

    zipped = edicao.http.get(f"/api/edicao-fotos/lotes/{lote}/zip")
    assert zipped.status_code == 200, zipped.text
    assert zipped.headers["content-type"] == "application/zip"
    assert "Casa-Azul.zip" in zipped.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(zipped.content)).namelist()
    assert len(names) == 1 and names[0].startswith("01")

    # decisions stay changeable after download; the next zip reflects it
    flip = edicao.http.post(f"/api/edicao-fotos/revisao/{lote}/fotos/{second}/decisao", json={"decisao": "aprovar"})
    assert flip.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(edicao.http.get(f"/api/edicao-fotos/lotes/{lote}/zip").content)).namelist()
    assert len(names) == 2
    done = edicao.http.get("/api/edicao-fotos/lotes").json()["items"][0]
    assert (done["estado_agregado"], done["fotos_decididas"]) == ("concluido", 2)


def test_admin_review_carries_the_verdict(edicao) -> None:
    edicao.configure_org()
    edicao.activate_guide()
    lote = edicao.make_batch("corretor")
    edicao.add_photo(lote)
    edicao.as_user("corretor").http.post(f"/api/edicao-fotos/lotes/{lote}/submeter")
    edicao.drain()
    for admin in ("admin", "plataforma"):
        review = edicao.as_user(admin).http.get(f"/api/edicao-fotos/revisao/{lote}").json()
        assert review[0]["avaliacao"] == {"veredito": "aprovar", "score": 8.5, "motivo": "Cores naturais."}
        detail = edicao.http.get(f"/api/edicao-fotos/lotes/{lote}").json()
        assert detail["fotos"][0]["avaliacao"]["veredito"] == "aprovar"


def test_deciding_a_photo_not_yet_reviewable_is_409(edicao) -> None:
    lote = edicao.make_batch("corretor")
    foto = edicao.add_photo(lote)
    resp = edicao.as_user("corretor").http.post(
        f"/api/edicao-fotos/revisao/{lote}/fotos/{foto}/decisao", json={"decisao": "aprovar"}
    )
    assert resp.status_code == 409 and resp.json()["code"] == "foto_nao_decidivel"


def test_zip_with_nothing_approved_is_409(edicao) -> None:
    edicao.configure_org()
    edicao.activate_guide()
    lote = edicao.make_batch("corretor")
    foto = edicao.add_photo(lote)
    edicao.as_user("corretor").http.post(f"/api/edicao-fotos/lotes/{lote}/submeter")
    edicao.drain()
    edicao.http.post(
        f"/api/edicao-fotos/revisao/{lote}/fotos/{foto}/decisao",
        json={"decisao": "rejeitar", "comentario": "não"},
    )
    resp = edicao.http.get(f"/api/edicao-fotos/lotes/{lote}/zip")
    assert resp.status_code == 409 and resp.json()["code"] == "nenhuma_foto_aprovada"


def test_retry_only_for_failed_photos(edicao) -> None:
    edicao.configure_org()
    lote = edicao.make_batch("corretor")
    foto = edicao.add_photo(lote)
    edicao.as_user("corretor")
    refused = edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/fotos/{foto}/retentar")
    assert refused.status_code == 409 and refused.json()["code"] == "foto_nao_falhou"
    edicao.run(edicao.repo.transition_photo(foto, PhotoStatus.FALHOU, detalhe={"motivo": "teste"}))
    ok = edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/fotos/{foto}/retentar")
    assert ok.status_code == 200 and ok.json()["estado"] == "recebida"
    assert ok.json()["tentativas"] == 1
