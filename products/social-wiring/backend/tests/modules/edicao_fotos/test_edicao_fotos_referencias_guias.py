"""W6 — reference pool (`/referencias`) + style guides (`/guias`), contract §5–§6.

Asserted on WRITES (what landed in the repo / bucket / job queue), not only on
status codes. The R1 unblock is pinned end-to-end: an admin writes a guide by
hand, activates it, and `POST /lotes/{id}/submeter` stops answering 409
`guia_nao_ativo` — no AI builder involved.
"""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.domain.photo_editing import GuideStatus, JobType

from .conftest import OTHER_ORG, USERS

REF_BUCKET = "edicao-fotos-referencias"


def _regen_jobs(edicao):
    return [j for j in edicao.ports.jobs._jobs.values() if j.type == JobType.REGEN_GUIA]


def _ref_keys(edicao) -> set[str]:
    return set(edicao.run(edicao.backend.list_keys(bucket=REF_BUCKET, prefix="", limit=1000)))


# --- reference pool ---------------------------------------------------------


def test_upload_stores_the_pair_and_schedules_the_rebuild(edicao) -> None:
    resp = edicao.as_user("plataforma").upload_referencia(tipos=("ceu", "cor_luz", "ceu"))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["comodo"], body["tipos_edicao"], body["nota"]) == ("sala", ["ceu", "cor_luz"], "céu limpo")
    assert body["arquivada_em"] is None and body["criado_por"] == USERS["plataforma"].id

    [pair] = edicao.repo.references.values()
    # The row stores PRIVATE keys; the wire carries signed URLs, never the key.
    assert pair.antes_url.startswith("referencias/") and pair.antes_url in _ref_keys(edicao)
    assert pair.depois_url in _ref_keys(edicao)
    assert body["antes_url"] != pair.antes_url and pair.antes_url in body["antes_url"]
    assert len(_regen_jobs(edicao)) == 1  # debounced rebuild queued


def test_curator_without_org_role_manages_the_pool(edicao) -> None:
    edicao.as_user("curador")
    created = edicao.upload_referencia(nota=None)
    assert created.status_code == 201, created.text
    assert created.json()["nota"] is None
    listed = edicao.http.get("/api/edicao-fotos/referencias").json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == created.json()["id"]
    assert edicao.http.delete(f"/api/edicao-fotos/referencias/{created.json()['id']}").status_code == 200


def test_list_reports_pool_state_and_the_fixed_vocabularies(edicao) -> None:
    edicao.as_user("plataforma")
    edicao.upload_referencia()
    body = edicao.http.get("/api/edicao-fotos/referencias").json()
    assert (body["page"], body["page_size"], body["total"]) == (1, 50, 1)
    assert body["pool"] == {"pares_ativos": 1, "limite_pares": None, "cheio": False}
    assert "sala" in body["opcoes"]["comodos"] and "outro" in body["opcoes"]["comodos"]
    assert body["opcoes"]["tipos_edicao"] == ["cor_luz", "ceu", "declutter", "staging_virtual"]


def test_limit_in_pairs_blocks_uploads_and_archive_frees_a_slot(edicao) -> None:
    edicao.as_user("plataforma")
    put = edicao.http.put(
        "/api/edicao-fotos/configuracoes/plataforma",
        json={"velocidade_default": "urgente", "limite_pares_referencia": 1},
    )
    assert put.status_code == 200 and put.json()["limite_pares_referencia"] == 1
    first = edicao.upload_referencia()
    assert first.status_code == 201
    keys_before = _ref_keys(edicao)

    full = edicao.upload_referencia()
    assert full.status_code == 409 and full.json()["code"] == "pool_cheio"
    assert _ref_keys(edicao) == keys_before  # nothing stored for the refused pair
    assert edicao.http.get("/api/edicao-fotos/referencias").json()["pool"]["cheio"] is True

    archived = edicao.http.delete(f"/api/edicao-fotos/referencias/{first.json()['id']}")
    assert archived.status_code == 200 and archived.json()["arquivada_em"] is not None
    assert edicao.upload_referencia().status_code == 201  # archived pairs do not count

    listing = edicao.http.get("/api/edicao-fotos/referencias").json()
    assert listing["total"] == 1 and listing["pool"]["pares_ativos"] == 1
    history = edicao.http.get(
        "/api/edicao-fotos/referencias", params={"incluir_arquivadas": "true"}
    ).json()
    assert history["total"] == 2  # archive keeps history


def test_zero_or_blank_limit_is_unlimited_and_omitting_it_keeps_it(edicao) -> None:
    edicao.as_user("plataforma")
    url = "/api/edicao-fotos/configuracoes/plataforma"
    edicao.http.put(url, json={"velocidade_default": "urgente", "limite_pares_referencia": 3})
    # An older client that does not send the field must not reset it.
    kept = edicao.http.put(url, json={"velocidade_default": "urgente"})
    assert kept.json()["limite_pares_referencia"] == 3
    assert edicao.run(edicao.repo.get_platform_settings()).limite_pares_referencia == 3
    for blank in (0, None):
        resp = edicao.http.put(url, json={"velocidade_default": "urgente", "limite_pares_referencia": blank})
        assert resp.json()["limite_pares_referencia"] is None
        assert edicao.run(edicao.repo.get_platform_settings()).limite_pares_referencia is None
    negative = edicao.http.put(url, json={"velocidade_default": "urgente", "limite_pares_referencia": -1})
    assert negative.status_code == 422


def test_upload_validation(edicao) -> None:
    edicao.as_user("plataforma")
    assert edicao.upload_referencia(comodo="garagem").status_code == 422  # fixed room list
    assert edicao.upload_referencia(tipos=("filtro",)).status_code == 422  # fixed edit types
    empty = edicao.upload_referencia(depois=b"")
    assert empty.status_code == 422 and empty.json()["code"] == "arquivo_vazio"
    only_one = edicao.http.post(
        "/api/edicao-fotos/referencias",
        data={"comodo": "sala"},
        files=[("antes", ("a.jpg", b"\xff\xd8x", "image/jpeg"))],
    )
    assert only_one.status_code == 422
    assert edicao.repo.references == {} and _ref_keys(edicao) == set()


def test_archive_is_idempotent_and_unknown_is_404(edicao) -> None:
    edicao.as_user("plataforma")
    ref = edicao.upload_referencia().json()["id"]
    first = edicao.http.delete(f"/api/edicao-fotos/referencias/{ref}").json()
    jobs = len(edicao.ports.jobs._jobs)
    again = edicao.http.delete(f"/api/edicao-fotos/referencias/{ref}")
    assert again.status_code == 200 and again.json()["arquivada_em"] == first["arquivada_em"]
    assert len(edicao.ports.jobs._jobs) == jobs
    missing = edicao.http.delete(f"/api/edicao-fotos/referencias/{uuid4()}")
    assert missing.status_code == 404 and missing.json()["code"] == "referencia_nao_encontrada"


def test_pool_is_platform_scope_not_org_scope(edicao) -> None:
    """Pairs carry no org: a curator's pair is the same pool every platform
    admin sees, whatever org their session is in — and an agency admin of any
    org (here: another org's owner) is refused, never shown an 'empty' pool."""
    created = edicao.as_user("curador").upload_referencia().json()
    platform = edicao.as_user("plataforma").http.get("/api/edicao-fotos/referencias").json()
    assert [i["id"] for i in platform["items"]] == [created["id"]]
    other = edicao.as_user("outra_admin").http.get("/api/edicao-fotos/referencias")
    assert other.status_code == 403 and other.json()["code"] == "restrito_curadoria"
    assert USERS["outra_admin"].org == OTHER_ORG


# --- style guides -----------------------------------------------------------


def test_manual_guide_unblocks_submission_without_the_ai_builder(edicao) -> None:
    """The R1 path with no OpenAI credits."""
    edicao.configure_org()
    lote = edicao.make_batch("corretor")
    edicao.add_photo(lote)
    blocked = edicao.as_user("corretor").http.post(f"/api/edicao-fotos/lotes/{lote}/submeter")
    assert blocked.status_code == 409 and blocked.json()["code"] == "guia_nao_ativo"

    edicao.as_user("plataforma")
    draft = edicao.http.post("/api/edicao-fotos/guias", json={"texto": "- Luz natural\r\n- Sem HDR  "})
    assert draft.status_code == 201, draft.text
    body = draft.json()
    assert (body["versao"], body["status"], body["origem"]) == (1, "rascunho", "manual")
    assert body["texto"] == "- Luz natural\n- Sem HDR\n"  # normalized by the engine
    assert edicao.run(edicao.repo.get_active_guide()) is None  # a draft is not active

    active = edicao.http.post("/api/edicao-fotos/guias/1/ativar")
    assert active.status_code == 200
    assert active.json()["status"] == "ativa" and active.json()["ativado_por"] == USERS["plataforma"].id
    assert edicao.llm_calls() == []  # no AI anywhere on this path

    submitted = edicao.as_user("corretor").http.post(f"/api/edicao-fotos/lotes/{lote}/submeter")
    assert submitted.status_code == 200, submitted.text
    batch = edicao.run(edicao.repo.get_batch(lote))
    assert batch.guia_efetivo_sha256  # the guide was snapshotted at submit


def test_list_versions_restore_and_activation_swap(edicao) -> None:
    edicao.as_user("curador")
    for texto in ("um", "dois"):
        assert edicao.http.post("/api/edicao-fotos/guias", json={"texto": texto}).status_code == 201
    assert edicao.http.post("/api/edicao-fotos/guias/1/ativar").status_code == 200
    assert edicao.http.post("/api/edicao-fotos/guias/2/ativar").status_code == 200

    restored = edicao.http.post("/api/edicao-fotos/guias/1/restaurar")
    assert restored.status_code == 201
    r = restored.json()
    assert (r["versao"], r["status"], r["gerado_de_versao"], r["texto"], r["origem"]) == (
        3, "rascunho", 1, "um\n", "restaurada")

    listing = edicao.http.get("/api/edicao-fotos/guias").json()
    assert listing["versao_ativa"] == 2 and listing["total"] == 3
    assert [(g["versao"], g["status"]) for g in listing["items"]] == [
        (3, "rascunho"), (2, "ativa"), (1, "substituida")]
    # Versions are immutable: the original v1 row is untouched by the restore.
    assert edicao.run(edicao.repo.get_guide(1)).status is GuideStatus.SUBSTITUIDA
    paged = edicao.http.get("/api/edicao-fotos/guias", params={"page": 2, "page_size": 2}).json()
    assert [g["versao"] for g in paged["items"]] == [1]


def test_unknown_version_is_404(edicao) -> None:
    edicao.as_user("plataforma")
    for action in ("ativar", "restaurar"):
        resp = edicao.http.post(f"/api/edicao-fotos/guias/99/{action}")
        assert resp.status_code == 404 and resp.json()["code"] == "guia_versao_inexistente"


def test_manual_guide_body_is_strict(edicao) -> None:
    edicao.as_user("plataforma")
    assert edicao.http.post("/api/edicao-fotos/guias", json={"texto": ""}).status_code == 422
    assert edicao.http.post(
        "/api/edicao-fotos/guias", json={"texto": "x", "status": "ativa"}
    ).status_code == 422  # extra="forbid": a draft cannot be created active
    assert edicao.repo.guides == {}


def test_regenerate_enqueues_a_manual_job_and_the_worker_writes_a_draft(edicao) -> None:
    edicao.as_user("plataforma")
    empty = edicao.http.post("/api/edicao-fotos/guias/regenerar")
    assert empty.status_code == 409 and empty.json()["code"] == "pool_vazio"

    edicao.upload_referencia()
    resp = edicao.http.post("/api/edicao-fotos/guias/regenerar")
    assert resp.status_code == 202, resp.text
    again = edicao.http.post("/api/edicao-fotos/guias/regenerar")
    assert again.json()["job_id"] == resp.json()["job_id"]  # double click = one job
    manual = [j for j in _regen_jobs(edicao) if j.payload.get("manual")]
    assert len(manual) == 1 and manual[0].payload["por"] == USERS["plataforma"].id

    edicao.drain()
    listing = edicao.http.get("/api/edicao-fotos/guias").json()
    assert listing["total"] == 1 and listing["versao_ativa"] is None  # never auto-activated
    draft = listing["items"][0]
    assert (draft["status"], draft["origem"]) == ("rascunho", "ia")
    [call] = [c for c in edicao.llm_calls() if c["schema_name"] == "guia_estilo"]
    # The builder received the pair's BYTES from the private bucket, not a key.
    assert len(call["images"]) == 2 and all(isinstance(i, bytes) for i in call["images"])
