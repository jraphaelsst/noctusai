"""Biblioteca de virais -- creator opt-out registry (BE-OPTOUT): platform-admin endpoints, the
cross-org purge, registration/verify/sync enforcement and idempotency.

Contract: ``geracao-contract.md`` 2.3, 3.3, 9.2, 9.3. The migration is found by NAME, never by number.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import anyio
import pytest

from noctusai_lib.testing.migrations import migration_path

from app.modules.media_creation.services import biblioteca_ingestao as ing
from app.modules.media_creation.services import biblioteca_optout as optout

from .test_geracao_biblioteca_api import (  # noqa: F401 - `bib` is the shared fixture
    BASE,
    FOREIGN_PERFIL,
    MARCA,
    ORG,
    P1,
    V1,
    bib,
)
from .test_geracao_biblioteca_ingestao import PID, _adapter, _db, _page, _ports, _sync

ADMIN = f"{BASE}/admin/optouts"
OTHER_ORG = "other-org"
MSG = "Este perfil pediu para não ser monitorado."
SQL = migration_path(Path(__file__).resolve().parents[3], "cs_biblioteca_optouts").read_text(encoding="utf-8")


class TestMigration:
    def test_platform_wide_unique_handle_and_service_role_only(self):
        assert re.search(r"CREATE UNIQUE INDEX IF NOT EXISTS cs_biblioteca_optouts_handle_uq\s+ON social_wiring\.cs_biblioteca_optouts \(handle\)", SQL)
        assert "org_id" not in SQL.split("CREATE TABLE", 1)[1].split(");", 1)[0]
        assert "ENABLE ROW LEVEL SECURITY" in SQL
        assert "REVOKE ALL ON social_wiring.cs_biblioteca_optouts FROM authenticated, anon" in SQL
        assert "TO authenticated" not in SQL and "TO anon" not in SQL
        assert re.search(r"origem\s+TEXT NOT NULL CHECK \(origem IN \('email', 'dpo', 'admin'\)\)", SQL)


class TestAuth:
    @pytest.mark.parametrize("method,path,kw", [
        ("get", "/admin/optouts", {}),
        ("post", "/admin/optouts", {"json": {"handle": "x", "origem": "email"}}),
        ("delete", f"/admin/optouts/{uuid.uuid4()}", {}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)

    @pytest.mark.parametrize("method,path,kw", [
        ("get", "/admin/optouts", {}),
        ("post", "/admin/optouts", {"json": {"handle": "alvo1", "origem": "email"}}),
        ("delete", f"/admin/optouts/{uuid.uuid4()}", {}),
    ])
    def test_non_admin_member_is_403_and_nothing_changes(self, bib, client, method, path, kw):
        r = getattr(client, method)(BASE + path, **kw)
        assert r.status_code == 403, (path, r.status_code, r.text)
        assert bib.db.from_("cs_biblioteca_optouts").select("*").execute().data == []
        assert bib.db.from_("cs_perfis_monitorados").select("id").eq("id", P1).execute().data


def _seed_second_org(bib):
    """The same creator is monitored by BOTH orgs: P1 (alvo1, ORG) and a copy in OTHER_ORG."""
    pid2, vid2 = str(uuid.uuid4()), str(uuid.uuid4())
    db = bib.db
    db.from_("cs_perfis_monitorados").insert({
        "id": pid2, "org_id": OTHER_ORG, "rede": "instagram", "handle": "alvo1", "status": "ativo",
        "foto_path": f"{OTHER_ORG}/{pid2}/foto.jpg",
    }).execute()
    db.from_("cs_virais").insert({
        "id": vid2, "org_id": OTHER_ORG, "perfil_id": pid2, "ig_media_id": "z", "thumbnail_path": f"{OTHER_ORG}/{pid2}/{vid2}.jpg",
        "e_viral": True, "transcricao_status": "concluida", "classificacao_status": "concluida",
    }).execute()
    db.from_("transcricoes").insert({
        "id": str(uuid.uuid4()), "org_id": OTHER_ORG, "contexto_tipo": "biblioteca_viral", "contexto_ref": vid2,
        "status": "concluida",
    }).execute()
    db.from_("cs_biblioteca_referencias").insert({
        "id": str(uuid.uuid4()), "org_id": OTHER_ORG, "marca_id": str(uuid.uuid4()), "modo": "perfil", "perfil_id": pid2,
        "auto_atualizar": True,
    }).execute()
    db.from_("cs_biblioteca_referencias").insert({
        "id": str(uuid.uuid4()), "org_id": OTHER_ORG, "marca_id": str(uuid.uuid4()), "modo": "video", "viral_id": vid2,
        "auto_atualizar": True,
    }).execute()
    for key in (f"{OTHER_ORG}/{pid2}/{vid2}.jpg", f"{OTHER_ORG}/{pid2}/foto.jpg", f"{ORG}/{P1}/{V1}.jpg"):
        anyio.run(lambda k=key: bib.storage.put(bucket="sw-biblioteca", key=k, data=b"x", content_type="image/jpeg"))
    return pid2, vid2


def _count(bib, table, **eq):
    q = bib.db.from_(table).select("id")
    for k, v in eq.items():
        q = q.eq(k, v)
    return len(q.execute().data)


class TestPurgeAcrossOrgs:
    def test_registering_purges_every_org_and_returns_counts(self, bib, client):
        bib.admin = True
        pid2, vid2 = _seed_second_org(bib)
        r = client.post(ADMIN, json={"handle": "@Alvo1", "motivo": "pedido por e-mail", "origem": "email"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["criado"] is True and d["optout"]["handle"] == "alvo1" and d["optout"]["origem"] == "email"
        assert d["purgados"] == {"perfis": 2, "virais": 2, "blobs_falhos": 0}
        for pid in (P1, pid2):
            assert _count(bib, "cs_perfis_monitorados", id=pid) == 0
        assert _count(bib, "cs_virais", perfil_id=P1) == 0 and _count(bib, "cs_virais", perfil_id=pid2) == 0
        assert _count(bib, "cs_biblioteca_referencias", perfil_id=P1) == 0
        assert _count(bib, "cs_biblioteca_referencias", perfil_id=pid2) == 0
        assert _count(bib, "cs_biblioteca_referencias", viral_id=vid2) == 0
        assert _count(bib, "transcricoes", contexto_ref=vid2) == 0
        assert anyio.run(lambda: bib.storage.list_keys(bucket="sw-biblioteca", prefix="", limit=100)) == []
        # an unrelated creator is untouched
        assert _count(bib, "cs_perfis_monitorados", id=FOREIGN_PERFIL) == 1

    def test_re_adding_the_same_handle_is_idempotent(self, bib, client):
        bib.admin = True
        first = client.post(ADMIN, json={"handle": "alvo1", "origem": "dpo"}).json()["data"]
        again = client.post(ADMIN, json={"handle": "https://instagram.com/Alvo1/", "motivo": "outro", "origem": "admin"})
        assert again.status_code == 200
        d = again.json()["data"]
        assert d["criado"] is False and d["optout"]["id"] == first["optout"]["id"] and d["optout"]["origem"] == "dpo"
        assert d["purgados"] == {"perfis": 0, "virais": 0, "blobs_falhos": 0}
        assert _count(bib, "cs_biblioteca_optouts") == 1

    def test_a_handle_nobody_monitors_is_still_registered(self, bib, client):
        bib.admin = True
        d = client.post(ADMIN, json={"handle": "ninguem", "origem": "admin"}).json()["data"]
        assert d["criado"] is True and d["purgados"]["perfis"] == 0

    @pytest.mark.parametrize("body", [
        {"handle": "alvo1", "origem": "telefone"},
        {"handle": "alvo1"},
        {"handle": "!!", "origem": "email"},
        {"handle": "alvo1", "origem": "email", "extra": 1},
    ])
    def test_invalid_bodies_are_422(self, bib, client, body):
        bib.admin = True
        assert client.post(ADMIN, json=body).status_code == 422


class TestListAndUnblock:
    def test_list_and_delete(self, bib, client):
        bib.admin = True
        oid = client.post(ADMIN, json={"handle": "alvo1", "origem": "email"}).json()["data"]["optout"]["id"]
        rows = client.get(ADMIN).json()["data"]
        assert [r["handle"] for r in rows] == ["alvo1"]
        assert client.delete(f"{ADMIN}/{oid}").status_code == 204
        assert client.get(ADMIN).json()["data"] == []
        assert client.delete(f"{ADMIN}/{oid}").status_code == 404

    def test_unblocking_lets_the_handle_be_registered_again(self, bib, client):
        bib.admin = True
        oid = client.post(ADMIN, json={"handle": "novo.alvo", "origem": "email"}).json()["data"]["optout"]["id"]
        bib.admin = False
        assert client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "novo.alvo"}).status_code == 422
        bib.admin = True
        client.delete(f"{ADMIN}/{oid}")
        bib.admin = False
        assert client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "novo.alvo"}).status_code == 201


class TestEnforcement:
    def _block(self, bib, client, handle):
        bib.admin = True
        assert client.post(ADMIN, json={"handle": handle, "origem": "email"}).status_code == 200
        bib.admin = False

    def test_registration_is_refused_with_the_optout_code(self, bib, client):
        self._block(bib, client, "bloqueado")
        r = client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "@Bloqueado"})
        assert r.status_code == 422
        assert r.json()["detail"] == MSG and r.json()["code"] == "perfil_optout"
        assert _count(bib, "cs_perfis_monitorados", handle="bloqueado") == 0
        assert bib.queued("biblioteca.sync_perfil") == []

    def test_verificar_is_refused_too(self, bib, client):
        self._block(bib, client, "bloqueado")
        r = client.get(f"{BASE}/perfis/verificar?handle=https://instagram.com/bloqueado/")
        assert r.status_code == 422 and r.json()["code"] == "perfil_optout"
        assert client.get(f"{BASE}/perfis/verificar?handle=livre").status_code == 200

    def test_sync_skips_and_purges_a_surviving_row(self):
        db = _db(perfil_status="ativo")
        db.from_(optout.OPTOUTS).insert({"handle": "alvo", "origem": "dpo"}).execute()
        ports = _ports(db)
        _sync(ports)
        assert db.from_("cs_perfis_monitorados").select("id").eq("id", PID).execute().data == []

    def test_sync_is_untouched_for_a_handle_that_did_not_opt_out(self):
        db = _db(perfil_status="ativo")
        db.from_(optout.OPTOUTS).insert({"handle": "outro", "origem": "dpo"}).execute()
        _sync(_ports(db, adapter=_adapter(_page([]))))
        assert db.from_("cs_perfis_monitorados").select("id").eq("id", PID).execute().data


def test_ingestao_checks_the_registry_before_any_vendor_call():
    src = Path(ing.__file__).read_text()
    body = src.split("async def sync_perfil", 1)[1]
    assert body.index("esta_bloqueado") < body.index("adapter_factory")
