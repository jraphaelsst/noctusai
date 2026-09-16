"""W7 — learning rules (`/regras`), contract §7.

Manual create is auto-approved (writing it down IS the approval); "archive"
reuses `POST /{id}/rejeitar` — the same only-platform-admin-may-override
authority `decide_rule` already enforces for AI-proposed rules. The
effective-guide view composes live (never mutates from a GET's failure
mode) and lists per-org history.
"""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.domain.photo_editing import JobType, RuleStatus

from .conftest import ORG, OTHER_ORG


def _propor_jobs(edicao):
    return [j for j in edicao.ports.jobs._jobs.values() if j.type == JobType.PROPOR_REGRAS]


def test_manual_create_is_auto_approved(edicao) -> None:
    edicao.as_user("admin")
    resp = edicao.http.post("/api/edicao-fotos/regras", json={"texto": "  Não escurecer céu  "})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["texto"] == "Não escurecer céu"
    assert body["status"] == "aprovada"
    assert body["decidido_por"] is not None and body["override_platform_admin"] is False


def test_corretor_cannot_create(edicao) -> None:
    resp = edicao.as_user("corretor").http.post("/api/edicao-fotos/regras", json={"texto": "Não X"})
    assert resp.status_code == 403


def test_other_org_admin_creates_into_their_own_org_only(edicao) -> None:
    """`org_id` is always the CALLER's own org (never a body field) — an
    agency admin of another org can create, but only inside THEIR org; it
    never shows up in `ORG`'s list (same "R1 stays inside your own org"
    shape as every other route here)."""
    theirs = edicao.as_user("outra_admin").http.post(
        "/api/edicao-fotos/regras", json={"texto": "Regra de outra org"}
    )
    assert theirs.status_code == 201
    mine = edicao.as_user("admin").http.get("/api/edicao-fotos/regras").json()
    assert mine["items"] == []


def test_duplicate_manual_rule_is_refused(edicao) -> None:
    edicao.as_user("admin")
    edicao.http.post("/api/edicao-fotos/regras", json={"texto": "Não escurecer"})
    dup = edicao.http.post("/api/edicao-fotos/regras", json={"texto": "não ESCURECER "})
    assert dup.status_code == 409 and dup.json()["code"] == "regra_duplicada"


def test_list_filters_by_status_and_stays_org_scoped(edicao) -> None:
    edicao.as_user("admin")
    created = edicao.http.post("/api/edicao-fotos/regras", json={"texto": "Não X"}).json()
    edicao.run(edicao.repo.add_rule(org_id=OTHER_ORG, texto="Regra de outra org", origem_comentarios=()))

    all_items = edicao.http.get("/api/edicao-fotos/regras").json()
    assert [r["id"] for r in all_items["items"]] == [created["id"]]

    approved = edicao.http.get("/api/edicao-fotos/regras", params={"status": "aprovada"}).json()
    assert [r["id"] for r in approved["items"]] == [created["id"]]
    pending = edicao.http.get("/api/edicao-fotos/regras", params={"status": "proposta"}).json()
    assert pending["items"] == []

    bad = edicao.http.get("/api/edicao-fotos/regras", params={"status": "nao-existe"})
    assert bad.status_code == 422 and bad.json()["code"] == "status_invalido"


def test_edit_authority_and_frozen_after_archive(edicao) -> None:
    edicao.as_user("admin")
    created = edicao.http.post("/api/edicao-fotos/regras", json={"texto": "Não X"}).json()
    regra_id = created["id"]

    denied = edicao.as_user("corretor").http.put(
        f"/api/edicao-fotos/regras/{regra_id}", json={"texto": "tentativa"}
    )
    assert denied.status_code == 403

    edited = edicao.as_user("admin").http.put(
        f"/api/edicao-fotos/regras/{regra_id}", json={"texto": "  Não X revisado  "}
    )
    assert edited.status_code == 200 and edited.json()["texto"] == "Não X revisado"

    # The SAME agency admin who wrote it cannot archive (flip a decided
    # rule) — only the platform admin can override.
    self_archive = edicao.http.post(f"/api/edicao-fotos/regras/{regra_id}/rejeitar")
    assert self_archive.status_code == 403

    archived = edicao.as_user("plataforma").http.post(f"/api/edicao-fotos/regras/{regra_id}/rejeitar")
    assert archived.status_code == 200 and archived.json()["status"] == "rejeitada"

    frozen = edicao.http.put(f"/api/edicao-fotos/regras/{regra_id}", json={"texto": "pos-arquivo"})
    assert frozen.status_code == 422 and frozen.json()["code"] == "regra_arquivada"


def test_approve_and_override_authority_ai_proposed_rule(edicao) -> None:
    proposta = edicao.run(edicao.repo.add_rule(org_id=ORG, texto="Não Y", origem_comentarios=()))

    edicao.as_user("corretor")
    denied = edicao.http.post(f"/api/edicao-fotos/regras/{proposta.id}/aprovar")
    assert denied.status_code == 403

    edicao.as_user("admin")
    approved = edicao.http.post(f"/api/edicao-fotos/regras/{proposta.id}/aprovar")
    assert approved.status_code == 200 and approved.json()["status"] == "aprovada"

    reapprove_is_idempotent = edicao.http.post(f"/api/edicao-fotos/regras/{proposta.id}/aprovar")
    assert reapprove_is_idempotent.status_code == 200

    cannot_flip = edicao.http.post(f"/api/edicao-fotos/regras/{proposta.id}/rejeitar")
    assert cannot_flip.status_code == 403

    flipped = edicao.as_user("plataforma").http.post(f"/api/edicao-fotos/regras/{proposta.id}/rejeitar")
    assert flipped.status_code == 200
    assert (flipped.json()["status"], flipped.json()["override_platform_admin"]) == ("rejeitada", True)


def test_unknown_rule_is_404(edicao) -> None:
    edicao.as_user("admin")
    for resp in (
        edicao.http.put(f"/api/edicao-fotos/regras/{uuid4()}", json={"texto": "x"}),
        edicao.http.post(f"/api/edicao-fotos/regras/{uuid4()}/aprovar"),
        edicao.http.post(f"/api/edicao-fotos/regras/{uuid4()}/rejeitar"),
    ):
        assert resp.status_code == 404 and resp.json()["code"] == "regra_nao_encontrada"


def test_propor_agora_enqueues_a_manual_job(edicao) -> None:
    edicao.as_user("admin")
    resp = edicao.http.post("/api/edicao-fotos/regras/propor-agora")
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] and body["status"]
    jobs = _propor_jobs(edicao)
    assert len(jobs) == 1 and jobs[0].payload["manual"] is True and jobs[0].payload["org_id"] == ORG
    # `scheduled_for` is `None` (run now) — unlike the debounced automatic path.
    assert jobs[0].scheduled_for is None


def test_guia_efetivo_view_and_history(edicao) -> None:
    edicao.as_user("admin")
    none_yet = edicao.http.get("/api/edicao-fotos/regras/guia-efetivo")
    assert none_yet.status_code == 200
    assert none_yet.json()["atual"] is None
    assert none_yet.json()["historico"]["total"] == 0

    edicao.activate_guide()
    first = edicao.http.get("/api/edicao-fotos/regras/guia-efetivo").json()
    assert first["atual"] is not None and first["historico"]["total"] == 1
    primeiro_sha = first["atual"]["sha256"]

    created = edicao.http.post("/api/edicao-fotos/regras", json={"texto": "Não X"}).json()
    assert created["status"] == "aprovada"
    second = edicao.http.get("/api/edicao-fotos/regras/guia-efetivo").json()
    assert second["atual"]["sha256"] != primeiro_sha
    assert second["historico"]["total"] == 2
    assert "Não X" in second["atual"]["texto"]

    # Idempotent — no new row for an unchanged effective guide.
    third = edicao.http.get("/api/edicao-fotos/regras/guia-efetivo").json()
    assert third["atual"]["id"] == second["atual"]["id"]
    assert third["historico"]["total"] == 2
