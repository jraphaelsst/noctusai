"""Re-read a STORED atendimento document (guia ITBI, proposta, ...).

An improved reader never reached rows already read — the slot offered
view/discard only. `POST …/financiamento/documentos/{id}/reler` and the
card-level `POST …/negociacao/documentos/reler` re-run
`negociacao_extracao_service.extrair` on the bytes already in the bucket.
Auth (strict 401) is enumerated by `test_auth_boundary.py`; the explicit one
here pins the two new routes by name.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from app.modules.card_hub import financiamento_service as fin
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_financiamento import _atendimento, _auth

BLOB = b"%PDF-1.7 guia-itbi-sintetica"


def _doc(aid, tipo, *, status="sem_dados", storage_path="k", did=None, **extra):
    return {
        "id": did or str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
        "tipo_documento": tipo, "storage_path": storage_path,
        "nome_original": "x.pdf", "mime_type": "application/pdf",
        "extracao_status": status, "extracao_tentativas": 2,
        "deleted_at": None, "created_at": "2026-01-01T00:00:00+00:00", **extra,
    }


def _seed(scoped, docs_fn):
    cid, aid = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("atendimento_financiamento", [])
    scoped.set_table_data("atendimento_documento_acessos", [])
    docs = docs_fn(aid)
    scoped.set_table_data("atendimento_documentos", docs)
    return cid, aid, docs


def _put(storage, key):
    asyncio.run(storage.put(bucket=fin.STORE.bucket, key=key, data=BLOB))


def _row(scoped, did):
    return next(r for r in scoped.table("atendimento_documentos").select("*").execute().data if r["id"] == did)


class TestReler:
    def test_sem_token_401(self, anon_client):
        assert anon_client.post(
            f"/api/clientes/{uuid4()}/financiamento/documentos/{uuid4()}/reler"
        ).status_code == 401
        assert anon_client.post(
            f"/api/clientes/{uuid4()}/negociacao/documentos/reler"
        ).status_code == 401

    def test_rele_o_arquivo_guardado_sem_novo_objeto(
        self, client, scoped, fake_storage, fake_identity_extractor,
    ):
        _put(fake_storage, "k1")
        cid, aid, (doc,) = _seed(scoped, lambda a: [_doc(a, "guia_itbi", storage_path="k1")])
        antes = dict(fake_storage._objects) if hasattr(fake_storage, "_objects") else None

        r = client.post(f"/api/clientes/{cid}/financiamento/documentos/{doc['id']}/reler", headers=_auth())

        assert r.status_code == 200, r.text
        assert r.json()["extracao_status"] == "pendente"
        # the background job ran on the STORED bytes
        assert [c[0] for c in fake_identity_extractor.calls] == [len(BLOB)]
        assert _row(scoped, doc["id"])["storage_path"] == "k1"
        if antes is not None:
            assert dict(fake_storage._objects) == antes

    def test_409_quando_ja_em_processamento(self, client, scoped, fake_storage, fake_identity_extractor):
        cid, aid, (doc,) = _seed(scoped, lambda a: [_doc(a, "guia_itbi", status="processando")])
        r = client.post(f"/api/clientes/{cid}/financiamento/documentos/{doc['id']}/reler", headers=_auth())
        assert r.status_code == 409
        assert fake_identity_extractor.calls == []

    def test_409_sem_arquivo_guardado(self, client, scoped, fake_storage, fake_identity_extractor):
        cid, aid, (doc,) = _seed(scoped, lambda a: [_doc(a, "guia_itbi", storage_path=None)])
        r = client.post(f"/api/clientes/{cid}/financiamento/documentos/{doc['id']}/reler", headers=_auth())
        assert r.status_code == 409

    def test_404_documento_de_outro_card(self, client, scoped, fake_storage, fake_identity_extractor):
        cid, aid, _ = _seed(scoped, lambda a: [])
        outro = _doc(str(uuid4()), "guia_itbi")
        scoped.set_table_data("atendimento_documentos", [outro])
        r = client.post(f"/api/clientes/{cid}/financiamento/documentos/{outro['id']}/reler", headers=_auth())
        assert r.status_code == 404


class TestRelerCard:
    def test_conta_e_agenda_so_os_extraiveis(self, client, scoped, fake_storage, fake_identity_extractor):
        _put(fake_storage, "k1")
        _put(fake_storage, "k2")
        cid, aid, docs = _seed(scoped, lambda a: [
            _doc(a, "guia_itbi", storage_path="k1"),
            _doc(a, "proposta_financiamento", status="ok", storage_path="k2"),
            _doc(a, "contrato_financiamento", status="pendente"),
            _doc(a, "contrato_financiamento", storage_path=None),
            _doc(a, "comprovante_itbi", storage_path="k1"),  # archive-only: not extractable
        ])

        r = client.post(f"/api/clientes/{cid}/negociacao/documentos/reler", headers=_auth())

        assert r.status_code == 200, r.text
        assert r.json() == {"relidos": 2, "sem_arquivo": 1, "em_andamento": 1, "erros": 0}
        assert len(fake_identity_extractor.calls) == 2
        assert _row(scoped, docs[4]["id"])["extracao_status"] == "sem_dados"  # untouched

    def test_card_sem_documentos_tudo_zero(self, client, scoped, fake_storage, fake_identity_extractor):
        cid, aid, _ = _seed(scoped, lambda a: [])
        r = client.post(f"/api/clientes/{cid}/negociacao/documentos/reler", headers=_auth())
        assert r.json() == {"relidos": 0, "sem_arquivo": 0, "em_andamento": 0, "erros": 0}
