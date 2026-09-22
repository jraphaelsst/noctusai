"""Documents, LGPD-complete — ported from social-wiring's
`tests/modules/card_hub/test_documentos.py`. Storage is ALWAYS the hub's
`FakeStorageBackend` (the factory's `get_storage` seam)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from noctusai_lib.domain.card_hub import DocumentoPolicy, documentos as docs
from noctusai_lib.domain.card_hub.documentos import (
    format_bytes_human,
    register_retention_sweep,
    run_retention_sweep,
    run_retention_sweep_all_orgs,
)
from noctusai_lib.primitives.exceptions import ValidationError_
from tests.domain.card_hub.conftest import AUTH, ORG_ID, USER_ID, build_hub


def _upload(hub, eid, *, nome="contrato.pdf", conteudo=b"%PDF-1.4 fake bytes", mime="application/pdf", tipo="contrato"):
    return hub.client.post(
        hub.url(eid, "/documentos"),
        files={"file": (nome, conteudo, mime)},
        data={"tipo_documento": tipo},
        headers=AUTH,
    )


class TestUpload:
    def test_upload_roundtrip(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documento_tipos, [hub.documento_tipo_row("contrato", retencao_dias=30)])

        resp = _upload(hub, eid)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert list(body) == [
            "id", "nome_original", "mime_type", "tamanho_bytes", "tipo_documento", "enviado_por", "created_at",
            "categoria_lgpd", "retencao_ate", "thumbnail_url",
        ]
        assert body["nome_original"] == "contrato.pdf"
        assert body["categoria_lgpd"] == "contratual"
        assert body["enviado_por"] == {"id": USER_ID, "nome": "Rapha"}
        assert body["thumbnail_url"] is None
        # UTC today, the same clock the sweep uses.
        hoje_utc = datetime.now(timezone.utc).date()
        assert body["retencao_ate"] == (hoje_utc + timedelta(days=30)).isoformat()

        stored = hub.rows(hub.cfg.tables.documentos)
        assert len(stored) == 1
        # Object key is org_id-first (object RLS keys on the first segment).
        key = stored[0]["storage_path"]
        assert key == f"{ORG_ID}/{hub.cfg.storage_segment}/{eid}/{body['id']}"
        assert asyncio.run(hub.storage.get(bucket=hub.cfg.bucket, key=key)).data == b"%PDF-1.4 fake bytes"

    def test_sw_storage_layout_is_the_existing_one(self, lead_schema_cache):
        """Social-wiring's existing objects live at `{org}/clientes/{id}/{doc}`
        in `social-wiring-documentos` — the default segment must reproduce it."""
        hub = build_hub("sw")
        assert (hub.cfg.bucket, hub.cfg.storage_segment) == ("social-wiring-documentos", "clientes")

    def test_a_null_retention_keeps_indefinitely(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documento_tipos, [hub.documento_tipo_row("contrato", retencao_dias=None)])
        assert _upload(hub, eid).json()["retencao_ate"] is None

    def test_rejects_disallowed_mime_type(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documento_tipos, [hub.documento_tipo_row("contrato")])
        resp = _upload(hub, eid, nome="script.exe", conteudo=b"MZ", mime="application/x-msdownload")
        assert resp.status_code == 400, resp.text
        assert "Tipo de arquivo não permitido" in resp.json()["error"]["message"]
        assert hub.rows(hub.cfg.tables.documentos) == []

    def test_rejects_oversized_file_naming_a_real_mb_number(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documento_tipos, [hub.documento_tipo_row("contrato")])
        oversized = b"0" * (hub.cfg.documentos.max_upload_bytes + 1)
        resp = _upload(hub, eid, conteudo=oversized)
        assert resp.status_code == 400, resp.text
        message = resp.json()["error"]["message"]
        assert "25.0MB" in message
        assert "limite de 0MB" not in message

    def test_a_sub_megabyte_cap_names_kb_not_zero_mb(self, hub):
        """The legacy 800 KB cap once formatted as "0MB". Exercised through the
        `max_bytes` PARAMETER — never by patching the configured value."""
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documento_tipos, [hub.documento_tipo_row("contrato")])
        cap = 800 * 1024
        with pytest.raises(ValidationError_) as exc:
            asyncio.run(docs.upload_documento(
                hub.cfg, hub.db, hub.storage, ORG_ID, eid, filename="g.pdf", content_type="application/pdf",
                data=b"0" * (cap + 1), tipo_documento="contrato", enviado_por=None, max_bytes=cap,
            ))
        assert "800KB" in exc.value.message
        assert "0MB" not in exc.value.message
        assert format_bytes_human(cap) == "800KB"

    def test_rejects_withheld_identity_document_type(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documento_tipos, [
            hub.documento_tipo_row("rg", categoria="identidade", ativo=False, identidade=True)
        ])
        resp = _upload(hub, eid, nome="rg.pdf", tipo="rg")
        assert resp.status_code == 400, resp.text
        assert "não está habilitado" in resp.json()["error"]["message"]

    def test_rejects_unknown_tipo_documento(self, hub):
        eid = hub.new_entity()
        resp = _upload(hub, eid, tipo="nao_existe")
        assert resp.status_code == 400
        assert resp.json()["error"]["details"]["field"] == "tipo_documento"


class TestPolicyHooks:
    def test_retention_hook_wins_over_the_catalogue(self, lead_schema_cache):
        """A product that moved retention onto an editable policy table (SW
        migration 079) plugs its resolver; the catalogue's value is ignored."""
        calls = []

        def resolver(db, org_id, tipo, tipo_row):
            calls.append((str(org_id), tipo, tipo_row["retencao_dias"]))
            return 10

        hub = build_hub("lead", cfg_transform=lambda c: replace(c, documentos=DocumentoPolicy(retention_days=resolver)))
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documento_tipos, [hub.documento_tipo_row("contrato", retencao_dias=1825)])
        body = _upload(hub, eid).json()
        assert calls == [(ORG_ID, "contrato", 1825)]
        assert body["retencao_ate"] == (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()

    def test_extra_fields_ride_the_insert_and_trail_the_output(self, lead_schema_cache):
        """Social-wiring's extraction state, as a product would plug it."""
        policy = DocumentoPolicy(
            extra_insert_fields=lambda tipo: {"extracao_status": "pendente" if tipo == "rg" else None},
            extra_out_fields=lambda row: {"extracao_status": row.get("extracao_status"), "extracao_erro": row.get("extracao_erro")},
        )
        hub = build_hub("sw", cfg_transform=lambda c: replace(c, documentos=policy))
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documento_tipos, [hub.documento_tipo_row("contrato")])
        body = _upload(hub, eid).json()
        assert list(body)[-3:] == ["thumbnail_url", "extracao_status", "extracao_erro"]
        assert "extracao_status" in hub.rows(hub.cfg.tables.documentos)[0]

    def test_upload_hook_runs_after_a_successful_upload(self, lead_schema_cache):
        seen = []

        def hook_dependency():
            def hook(background, ctx, storage, entity_id, documento, tipo_documento):
                background.add_task(seen.append, (str(ctx.org_id), str(entity_id), documento["id"], tipo_documento))
            return hook

        hub = build_hub("lead", upload_hook=hook_dependency)
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documento_tipos, [hub.documento_tipo_row("contrato")])
        body = _upload(hub, eid).json()
        assert seen == [(ORG_ID, eid, body["id"], "contrato")]

    def test_upload_hook_does_not_run_on_a_refused_upload(self, lead_schema_cache):
        seen = []
        hub = build_hub("lead", upload_hook=lambda: (lambda *a: seen.append(a)))
        eid = hub.new_entity()
        assert _upload(hub, eid, tipo="nao_existe").status_code == 400
        assert seen == []


class TestListAndUrlAndDelete:
    def test_list_excludes_deleted_newest_first(self, hub):
        eid = hub.new_entity()
        old = hub.documento_row(str(uuid4()), eid, created_at="2026-01-01T00:00:00+00:00")
        new = hub.documento_row(str(uuid4()), eid, created_at="2026-02-01T00:00:00+00:00")
        deleted = hub.documento_row(str(uuid4()), eid, deleted_at="2026-01-01T00:00:00+00:00")
        hub.seed(hub.cfg.tables.documentos, [old, deleted, new])

        resp = hub.client.get(hub.url(eid, "/documentos"), headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert [d["id"] for d in resp.json()["items"]] == [new["id"], old["id"]]
        assert resp.json()["total"] == 2

    def test_get_url_mints_and_logs_view(self, hub):
        eid = hub.new_entity()
        doc = hub.documento_row(str(uuid4()), eid)
        hub.seed(hub.cfg.tables.documentos, [doc])
        asyncio.run(hub.storage.put(bucket=hub.cfg.bucket, key=doc["storage_path"], data=b"x", content_type="application/pdf"))

        resp = hub.client.get(hub.url(eid, f"/documentos/{doc['id']}/url"), headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert set(resp.json()) == {"url", "expires_at"}
        assert resp.json()["url"]

        acessos = hub.rows(hub.cfg.tables.documento_acessos)
        assert [(a["acao"], a["documento_id"], a["usuario_id"]) for a in acessos] == [("view", doc["id"], USER_ID)]

    def test_download_intent_logs_download_and_a_bad_intent_422s(self, hub):
        eid = hub.new_entity()
        doc = hub.documento_row(str(uuid4()), eid)
        hub.seed(hub.cfg.tables.documentos, [doc])
        asyncio.run(hub.storage.put(bucket=hub.cfg.bucket, key=doc["storage_path"], data=b"x", content_type="application/pdf"))

        resp = hub.client.get(hub.url(eid, f"/documentos/{doc['id']}/url?intent=download"), headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert hub.rows(hub.cfg.tables.documento_acessos)[0]["acao"] == "download"
        assert hub.client.get(hub.url(eid, f"/documentos/{doc['id']}/url?intent=print"), headers=AUTH).status_code == 422

    def test_delete_requires_motivo_as_query_param(self, hub):
        eid = hub.new_entity()
        doc = hub.documento_row(str(uuid4()), eid)
        hub.seed(hub.cfg.tables.documentos, [doc])

        assert hub.client.delete(hub.url(eid, f"/documentos/{doc['id']}"), headers=AUTH).status_code == 422
        assert hub.client.delete(hub.url(eid, f"/documentos/{doc['id']}?motivo="), headers=AUTH).status_code == 422

        resp = hub.client.delete(hub.url(eid, f"/documentos/{doc['id']}?motivo=solicitação%20do%20cliente"), headers=AUTH)
        assert resp.status_code == 204, resp.text

        stored = hub.rows(hub.cfg.tables.documentos)[0]
        assert stored["deleted_at"] is not None
        assert stored["delete_motivo"] == "solicitação do cliente"
        assert stored["delete_solicitado_por"] == USER_ID
        assert [a["acao"] for a in hub.rows(hub.cfg.tables.documento_acessos)] == ["delete"]

        assert hub.client.get(hub.url(eid, "/documentos"), headers=AUTH).json()["items"] == []
        assert hub.client.get(hub.url(eid, f"/documentos/{doc['id']}/url"), headers=AUTH).status_code == 404

    def test_acessos_log_survives_the_documents_own_delete(self, hub):
        eid = hub.new_entity()
        doc = hub.documento_row(str(uuid4()), eid)
        hub.seed(hub.cfg.tables.documentos, [doc])
        hub.client.delete(hub.url(eid, f"/documentos/{doc['id']}?motivo=x"), headers=AUTH)

        resp = hub.client.get(hub.url(eid, f"/documentos/{doc['id']}/acessos"), headers=AUTH)
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert list(item) == ["id", "usuario", "acao", "created_at"]
        assert item["usuario"] == {"id": USER_ID, "nome": "Rapha"}
        assert resp.json()["total"] == 1

    def test_acessos_of_another_entitys_document_404s(self, hub):
        eid, other = hub.new_entity(), hub.new_entity()
        doc = hub.documento_row(str(uuid4()), eid)
        hub.seed(hub.cfg.tables.documentos, [doc])
        assert hub.client.get(hub.url(other, f"/documentos/{doc['id']}/acessos"), headers=AUTH).status_code == 404

    def test_unknown_documento_404s(self, hub):
        eid = hub.new_entity()
        resp = hub.client.get(hub.url(eid, f"/documentos/{uuid4()}/url"), headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["error"]["details"]["resource"] == hub.cfg.tables.documentos


class TestAccessLogIsAppendOnly:
    def test_no_mutation_route_exists_for_acessos(self, hub):
        methods = {
            m.lower()
            for r in hub.app.routes
            if getattr(r, "path", "") == f"{hub.prefix}/{{{hub.cfg.id_param}}}/documentos/{{documento_id}}/acessos"
            for m in r.methods
        }
        assert methods == {"get"}


class TestTiposCatalogue:
    def test_lists_only_active_types_sorted(self, hub):
        hub.seed(hub.cfg.tables.documento_tipos, [
            hub.documento_tipo_row("proposta"),
            hub.documento_tipo_row("contrato"),
            hub.documento_tipo_row("rg", categoria="identidade", ativo=False, identidade=True),
        ])
        resp = hub.client.get(f"{hub.prefix}/documentos/tipos", headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert [t["tipo_documento"] for t in resp.json()["items"]] == ["contrato", "proposta"]
        assert list(resp.json()["items"][0]) == ["tipo_documento", "categoria_lgpd", "descricao", "identidade"]


class TestRetentionSweep:
    def test_sweep_soft_deletes_past_retention_and_logs_as_system(self, hub):
        eid = hub.new_entity()
        expired = hub.documento_row(str(uuid4()), eid, retencao_ate=(date.today() - timedelta(days=1)).isoformat())
        fresh = hub.documento_row(str(uuid4()), eid, retencao_ate=(date.today() + timedelta(days=30)).isoformat())
        hub.seed(hub.cfg.tables.documentos, [expired, fresh])

        assert run_retention_sweep(hub.cfg, hub.db, ORG_ID) == 1

        rows = {r["id"]: r for r in hub.rows(hub.cfg.tables.documentos)}
        assert rows[expired["id"]]["deleted_at"] is not None
        assert rows[expired["id"]]["delete_motivo"] == "retenção expirada (sweep automático)"
        assert rows[fresh["id"]]["deleted_at"] is None
        acessos = hub.rows(hub.cfg.tables.documento_acessos)
        assert [(a["acao"], a["usuario_id"], a["documento_id"]) for a in acessos] == [("delete", None, expired["id"])]

    def test_all_orgs_pass_walks_every_org_with_documents(self, hub):
        eid = hub.new_entity()
        other_org = str(uuid4())
        past = (date.today() - timedelta(days=1)).isoformat()
        mine = hub.documento_row(str(uuid4()), eid, retencao_ate=past)
        theirs = {**hub.documento_row(str(uuid4()), eid, retencao_ate=past), "org_id": other_org}
        hub.seed(hub.cfg.tables.documentos, [mine, theirs])
        assert run_retention_sweep_all_orgs(hub.cfg, hub.db) == 2


class _RecordingScheduler:
    def __init__(self):
        self.jobs: dict = {}

    def register(self, name, fn, **kwargs):
        self.jobs[name] = (fn, kwargs)


class TestRetentionRegistration:
    def test_registration_is_explicit_and_named(self, hub):
        sched = _RecordingScheduler()
        job_id = register_retention_sweep(hub.cfg, get_db=lambda: hub.db, scheduler=sched)
        assert job_id == f"card_hub_{hub.cfg.entity_kind}_documento_retention_sweep"
        assert sched.jobs[job_id][1] == {"hours": 24}

    def test_a_shipped_job_id_is_kept_verbatim(self, hub):
        """Social-wiring's job has run as `card_hub_documento_retention_sweep`
        since 2026-08; re-registering under a new id would double the sweep."""
        sched = _RecordingScheduler()
        register_retention_sweep(hub.cfg, get_db=lambda: hub.db, scheduler=sched,
                                 job_id="card_hub_documento_retention_sweep")
        register_retention_sweep(hub.cfg, get_db=lambda: hub.db, scheduler=sched,
                                 job_id="card_hub_documento_retention_sweep")
        assert list(sched.jobs) == ["card_hub_documento_retention_sweep"]

    def test_the_job_runs_the_sweep_through_get_db(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documentos, [
            hub.documento_row(str(uuid4()), eid, retencao_ate=(date.today() - timedelta(days=2)).isoformat())
        ])
        sched = _RecordingScheduler()
        job_id = register_retention_sweep(hub.cfg, get_db=lambda: hub.db, scheduler=sched)
        sched.jobs[job_id][0]()
        assert hub.rows(hub.cfg.tables.documentos)[0]["deleted_at"] is not None

    def test_a_failing_run_is_logged_not_raised(self, hub, caplog):
        def boom():
            raise RuntimeError("db down")

        sched = _RecordingScheduler()
        job_id = register_retention_sweep(hub.cfg, get_db=lambda: hub.db, scheduler=sched, run_fn=boom)
        with caplog.at_level(logging.ERROR, logger="noctusai_lib.domain.card_hub.documentos"):
            sched.jobs[job_id][0]()
        assert any("retention sweep" in r.message and r.exc_info for r in caplog.records)

    def test_importing_the_package_registers_nothing(self):
        from noctusai_lib.api import scheduler as seed_scheduler

        ids = {j.id for j in seed_scheduler.scheduler.get_jobs()}
        assert not any("documento_retention_sweep" in i for i in ids)


def test_uuid_ids_roundtrip_through_the_service_layer(hub):
    """Services accept `UUID` or `str` ids alike (the router passes UUIDs)."""
    eid = hub.new_entity()
    assert docs.list_documentos(hub.cfg, hub.db, UUID(ORG_ID), UUID(eid)) == {"items": [], "total": 0}
