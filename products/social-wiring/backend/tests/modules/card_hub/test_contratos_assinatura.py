"""E-signature envelopes for a contract version — migration 134.

Contract: `projects/signature-integration-CONTRACT.md` §3.1-§3.4.

WHAT THESE PIN
--------------
- every row of §3.1's error table, with its exact `codigo`;
- 201's exact body shape — the E2E-shape check `noc-contract-first`
  mandates, asserting the precise keys the FE destructures;
- state-after (§3.1 point 3): `atendimento_contratos.status` is ALREADY
  `enviado_assinatura` when POST returns, never set by the FE;
- GET never calls the provider (`fake_signature_adapter.calls` stays empty
  across a GET) — the webhook is the source of truth, not a page render;
- cancel puts the contract back in `em_revisao` and refuses (409) once the
  provider reports `concluido`;
- the webhook: unknown `external_id` -> 200 ignorado + no side effects;
  invalid signature -> strict 401, never 200; `concluido` stores the signed
  PDF as a NEW version (`origem='assinado'`) and flips the contract to
  `assinado`; replaying the identical event is a no-op (idempotent).

Auth is NOT re-tested here — `test_auth_boundary_assinatura.py` enumerates
every org-scoped route and asserts a strict 401 on each.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from uuid import uuid4

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub.deps import BUCKET
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

CPF_VALIDO = "52998224725"
CPF_INVALIDO = "12345678901"  # fails mod-11


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _atendimento(aid: str, cliente_id: str) -> dict:
    return {
        "id": aid,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "lead_id": None,
        "meta_ads_lead_id": None,
        "status": "aberta",
        "substituida_por": None,
        "arquivado": False,
        "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None,
    }


def _seed(scoped) -> tuple[str, str]:
    cid, aid = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("atendimento_contratos", [])
    scoped.set_table_data("atendimento_contrato_versoes", [])
    scoped.set_table_data("atendimento_contrato_versao_acessos", [])
    scoped.set_table_data("atendimento_contrato_assinaturas", [])
    return cid, aid


def _contrato_row(contrato_id: str, aid: str, *, status: str = "em_revisao") -> dict:
    return {
        "id": contrato_id, "org_id": ORG_ID, "atendimento_id": aid,
        "titulo": "Contrato gerado", "modelo": "compra_venda", "status": status,
        "status_em": None, "status_por": None, "origem": "gerado", "criado_por": None,
        "deleted_at": None, "delete_motivo": None, "delete_solicitado_por": None,
        "created_at": "2026-09-16T00:00:00+00:00", "updated_at": None,
        "assinatura_data": None, "prazo_pendencias_dias": None,
    }


def _versao_gerada_row(versao_id: str, contrato_id: str, pdf_path: str) -> dict:
    return {
        "id": versao_id, "org_id": ORG_ID, "contrato_id": contrato_id,
        "storage_path": pdf_path, "nome_original": "contrato-gerado-v1.pdf",
        "mime_type": "application/pdf", "tamanho_bytes": 13,
        "tipo_documento": contratos_svc.TIPO_VERSAO, "numero": 1, "rotulo": None,
        "origem": "gerado", "enviado_por": None, "deleted_at": None,
        "delete_motivo": None, "delete_solicitado_por": None,
        "created_at": "2026-09-16T00:00:00+00:00",
        "contexto_sha256": "a" * 64,
        "docx_storage_path": f"{pdf_path}.docx", "docx_tamanho_bytes": 18,
    }


def _seed_versao_gerada(scoped, fake_storage, aid: str, *, status: str = "em_revisao") -> dict:
    """A contract with ONE `origem='gerado'` PDF version — ready to be sent
    for signature. Mirrors `test_contratos.py::_seed_gerado`."""
    contrato_id, versao_id = str(uuid4()), str(uuid4())
    pdf_path = f"{ORG_ID}/contratos/{contrato_id}/{versao_id}"
    asyncio.run(
        fake_storage.put(bucket=BUCKET, key=pdf_path, data=b"%PDF-1.7 fake", content_type="application/pdf")
    )
    asyncio.run(
        fake_storage.put(bucket=BUCKET, key=f"{pdf_path}.docx", data=b"PK\x03\x04 fake docx", content_type=contratos_svc.MIME_DOCX)
    )
    scoped.set_table_data("atendimento_contratos", [_contrato_row(contrato_id, aid, status=status)])
    scoped.set_table_data("atendimento_contrato_versoes", [_versao_gerada_row(versao_id, contrato_id, pdf_path)])
    return {"contrato_id": contrato_id, "versao_id": versao_id}


def _signatario(**over) -> dict:
    base = {
        "nome": "Ana Compradora",
        "email": "ana@example.com",
        "cpf": CPF_VALIDO,
        "papel": "comprador",
        "ordem": 0,
    }
    base.update(over)
    return base


def _enviar(client, cid, contrato_id, *, versao_id, signatarios=None, mensagem=None):
    body: dict = {
        "versao_id": versao_id,
        "signatarios": signatarios if signatarios is not None else [_signatario()],
    }
    if mensagem is not None:
        body["mensagem"] = mensagem
    return client.post(
        f"/api/clientes/{cid}/contratos/{contrato_id}/assinatura",
        json=body,
        headers=_auth(),
    )


def _get(client, cid, contrato_id):
    return client.get(
        f"/api/clientes/{cid}/contratos/{contrato_id}/assinatura", headers=_auth()
    )


def _cancelar(client, cid, contrato_id, *, motivo="mudança de plano"):
    return client.post(
        f"/api/clientes/{cid}/contratos/{contrato_id}/assinatura/cancelar",
        json={"motivo": motivo},
        headers=_auth(),
    )


class TestErrorTaxonomy:
    def test_empty_signatarios_is_400(self, client, scoped, fake_storage, fake_signature_adapter):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"], signatarios=[])
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "ASSINATURA_SEM_SIGNATARIOS"

    def test_bad_email_is_400(self, client, scoped, fake_storage, fake_signature_adapter):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r = _enviar(
            client, cid, ids["contrato_id"], versao_id=ids["versao_id"],
            signatarios=[_signatario(email="not-an-email")],
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "ASSINATURA_SIGNATARIO_INVALIDO"

    def test_bad_cpf_is_400(self, client, scoped, fake_storage, fake_signature_adapter):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r = _enviar(
            client, cid, ids["contrato_id"], versao_id=ids["versao_id"],
            signatarios=[_signatario(cpf=CPF_INVALIDO)],
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "ASSINATURA_SIGNATARIO_INVALIDO"

    def test_unknown_contrato_is_404(self, client, scoped, fake_storage, fake_signature_adapter):
        cid, aid = _seed(scoped)
        r = _enviar(client, cid, str(uuid4()), versao_id=str(uuid4()))
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "CONTRATO_NAO_ENCONTRADO"

    def test_unknown_versao_is_404(self, client, scoped, fake_storage, fake_signature_adapter):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r = _enviar(client, cid, ids["contrato_id"], versao_id=str(uuid4()))
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "VERSAO_NAO_ENCONTRADA"

    def test_a_version_not_gerado_is_422(self, client, scoped, fake_storage, fake_signature_adapter):
        cid, aid = _seed(scoped)
        contrato_id, versao_id = str(uuid4()), str(uuid4())
        pdf_path = f"{ORG_ID}/contratos/{contrato_id}/{versao_id}"
        asyncio.run(fake_storage.put(bucket=BUCKET, key=pdf_path, data=b"%PDF fake", content_type="application/pdf"))
        scoped.set_table_data("atendimento_contratos", [_contrato_row(contrato_id, aid)])
        row = _versao_gerada_row(versao_id, contrato_id, pdf_path)
        row.update({"origem": "upload", "docx_storage_path": None, "docx_tamanho_bytes": None, "contexto_sha256": None})
        scoped.set_table_data("atendimento_contrato_versoes", [row])

        r = _enviar(client, cid, contrato_id, versao_id=versao_id)
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "ASSINATURA_VERSAO_NAO_GERADA"

    def test_already_sent_is_409(self, client, scoped, fake_storage, fake_signature_adapter):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r1 = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        assert r1.status_code == 201, r1.text

        r2 = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "ASSINATURA_JA_ENVIADA"

    def test_provedor_nao_configurado_is_422_naming_the_missing_credentials(
        self, client, scoped, fake_storage
    ):
        """No `fake_signature_adapter` override here — the real factory
        (`make_signature_adapter(real=True, ...)`) runs against an
        unconfigured environment, so it raises `ProvedorNaoConfigurado`
        naming every missing D4Sign credential."""
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        assert r.status_code == 422
        body = r.json()
        assert body["error"]["code"] == "ASSINATURA_PROVEDOR_NAO_CONFIGURADO"
        faltando = body["error"]["details"]["faltando"]
        assert "d4sign_api_token" in faltando
        assert "d4sign_crypt_key" in faltando
        assert "d4sign_safe_uuid" in faltando

    def test_no_2xx_ever_carries_a_mocked_envelope(self, client, scoped, fake_storage):
        """F1's rule, asserted structurally: an unconfigured provider NEVER
        produces a 2xx — it is always the typed 422 above, never a fake
        envelope dressed up as a real send."""
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        assert r.status_code < 200 or r.status_code >= 300


class TestSendingSucceeds:
    def test_the_e2e_shape_the_frontend_destructures(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        """§6's mandated E2E-shape check: hit the real route with the Fake
        injected, assert the EXACT §3.1 201 body."""
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        assert r.status_code == 201, r.text
        body = r.json()
        assert set(body.keys()) == {
            "assinatura_id", "external_id", "link_assinatura", "provedor",
            "status", "signatarios", "enviado_em",
        }
        assert body["provedor"] == "d4sign"
        assert body["status"] == "pendente"
        assert body["external_id"]
        assert body["link_assinatura"].startswith("https://")
        assert body["signatarios"] == [
            {"email": "ana@example.com", "external_id": body["signatarios"][0]["external_id"], "assinado_em": None}
        ]

    def test_the_contract_is_already_enviado_assinatura(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        contrato = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()["contratos"][0]
        assert contrato["status"] == "enviado_assinatura"

    def test_the_version_content_read_is_lgpd_logged(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        acessos = scoped.table("atendimento_contrato_versao_acessos").select("*").execute().data
        assert any(a["documento_id"] == ids["versao_id"] for a in acessos)


class TestTestemunhaWiring:
    """`org_testemunhas` (migration 108/143/168) is the org's witness
    registry — `assinatura_service.enviar` resolves a papel='testemunha'
    signatário's e-mail/cpf/nome from it BY `testemunha_id` (migration 168 —
    supersedes the old nome match), authoritatively over whatever this one
    request happened to submit inline."""

    def test_the_registrys_email_wins_over_a_stale_inline_value(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        testemunha_id = str(uuid4())
        scoped.set_table_data("org_testemunhas", [{
            "id": testemunha_id, "org_id": ORG_ID, "nome": "Maria Testemunha",
            "rg": "12.345.678-9", "cpf": CPF_VALIDO,
            "email": "maria.testemunha@exemplo.test",
            "created_at": "2026-09-16T00:00:00+00:00", "updated_at": None,
        }])

        r = _enviar(
            client, cid, ids["contrato_id"], versao_id=ids["versao_id"],
            signatarios=[
                _signatario(),
                _signatario(
                    nome="Maria Testemunha", email="stale@example.com",
                    cpf=CPF_VALIDO, papel="testemunha", testemunha_id=testemunha_id,
                ),
            ],
        )
        assert r.status_code == 201, r.text
        emails = {s["email"] for s in r.json()["signatarios"]}
        assert "maria.testemunha@exemplo.test" in emails
        assert "stale@example.com" not in emails

    def test_a_nome_match_no_longer_resolves_anything(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        """[Migration 168] A registry row with the SAME nome but no
        `testemunha_id` on the signatário is NOT matched — the resolver
        keys strictly on id now, not nome."""
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        scoped.set_table_data("org_testemunhas", [{
            "id": str(uuid4()), "org_id": ORG_ID, "nome": "Maria Testemunha",
            "rg": None, "cpf": CPF_VALIDO,
            "email": "maria.testemunha@exemplo.test",
            "created_at": "2026-09-16T00:00:00+00:00", "updated_at": None,
        }])

        r = _enviar(
            client, cid, ids["contrato_id"], versao_id=ids["versao_id"],
            signatarios=[
                _signatario(
                    nome="Maria Testemunha", email="inline@example.com",
                    cpf=CPF_VALIDO, papel="testemunha",
                ),
            ],
        )
        assert r.status_code == 201, r.text
        assert r.json()["signatarios"][0]["email"] == "inline@example.com"

    def test_an_unregistered_witness_is_left_as_submitted(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        """No `testemunha_id` at all — the inline value is the only one
        there is, and still sendable when it's valid."""
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        scoped.set_table_data("org_testemunhas", [])

        r = _enviar(
            client, cid, ids["contrato_id"], versao_id=ids["versao_id"],
            signatarios=[
                _signatario(
                    nome="Não Cadastrada", email="avulsa@example.com",
                    cpf=CPF_VALIDO, papel="testemunha",
                ),
            ],
        )
        assert r.status_code == 201, r.text
        assert r.json()["signatarios"][0]["email"] == "avulsa@example.com"

    def test_a_testemunha_id_that_does_not_resolve_is_left_as_submitted(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        """A `testemunha_id` from another org (or a deleted row) resolves to
        nothing — same "left as submitted" posture as no id at all, never a
        500 or a silent cross-org read."""
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        scoped.set_table_data("org_testemunhas", [])

        r = _enviar(
            client, cid, ids["contrato_id"], versao_id=ids["versao_id"],
            signatarios=[
                _signatario(
                    nome="Fantasma", email="fantasma@example.com",
                    cpf=CPF_VALIDO, papel="testemunha", testemunha_id=str(uuid4()),
                ),
            ],
        )
        assert r.status_code == 201, r.text
        assert r.json()["signatarios"][0]["email"] == "fantasma@example.com"


class TestGetting:
    def test_no_envelope_is_404(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r = _get(client, cid, ids["contrato_id"])
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "ASSINATURA_NAO_ENCONTRADA"

    def test_get_never_calls_the_provider(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        fake_signature_adapter.calls.clear()

        r = _get(client, cid, ids["contrato_id"])
        assert r.status_code == 200
        assert fake_signature_adapter.calls == []

    def test_get_after_send_carries_the_detail_fields(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        r = _get(client, cid, ids["contrato_id"])
        body = r.json()
        assert body["status"] == "pendente"
        assert body["concluido_em"] is None
        assert body["versao_assinada_id"] is None
        assert body["cancelado_motivo"] is None

    def test_unknown_contrato_is_404(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        r = _get(client, cid, str(uuid4()))
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "CONTRATO_NAO_ENCONTRADO"


class TestCancelling:
    def test_cancel_returns_the_contract_to_em_revisao(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])

        r = _cancelar(client, cid, ids["contrato_id"], motivo="mudança de plano")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "cancelado"
        assert body["cancelado_motivo"] == "mudança de plano"

        contrato = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()["contratos"][0]
        assert contrato["status"] == "em_revisao"

    def test_cancelling_a_concluded_envelope_is_409(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r_env = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        external_id = r_env.json()["external_id"]
        fake_signature_adapter.marcar_assinado(external_id, "ana@example.com")
        # Sync the row's status the same way the webhook would — directly,
        # since this test targets the CANCEL refusal, not the webhook path.
        scoped.table("atendimento_contrato_assinaturas").update(
            {"status": "concluido"}
        ).eq("external_id", external_id).execute()

        r = _cancelar(client, cid, ids["contrato_id"])
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "ASSINATURA_NAO_CANCELAVEL"

    def test_no_envelope_is_404(self, client, scoped, fake_storage, fake_signature_adapter):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r = _cancelar(client, cid, ids["contrato_id"])
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "ASSINATURA_NAO_ENCONTRADA"

    def test_motivo_is_required(self, client, scoped, fake_storage, fake_signature_adapter):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        r = client.post(
            f"/api/clientes/{cid}/contratos/{ids['contrato_id']}/assinatura/cancelar",
            json={},
            headers=_auth(),
        )
        assert r.status_code == 422


def _fake_webhook_headers(body: bytes) -> dict:
    return {"x-fake-signature": hashlib.sha256(body).hexdigest()}


def _post_webhook(client, provedor: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        f"/api/webhooks/assinatura/{provedor}",
        content=body,
        headers=_fake_webhook_headers(body),
    )


class TestWebhook:
    def test_invalid_signature_is_strict_401(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        body = json.dumps({"external_id": "whatever", "status": "concluido"}).encode()
        r = client.post(
            "/api/webhooks/assinatura/d4sign",
            content=body,
            headers={"x-fake-signature": "0" * 64},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "WEBHOOK_ASSINATURA_INVALIDA"

    def test_absent_signature_is_strict_401(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        body = json.dumps({"external_id": "whatever", "status": "concluido"}).encode()
        r = client.post("/api/webhooks/assinatura/d4sign", content=body)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "WEBHOOK_ASSINATURA_INVALIDA"

    def test_unknown_external_id_is_a_quiet_200(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        r = _post_webhook(client, "d4sign", {"external_id": "not-tracked", "status": "concluido"})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "ignorado": True}

    def test_concluido_stores_a_signed_version_and_flips_the_contract(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r_env = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        external_id = r_env.json()["external_id"]

        fake_signature_adapter.marcar_assinado(external_id, "ana@example.com")
        r = _post_webhook(client, "d4sign", {"external_id": external_id, "status": "concluido"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        contrato = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()["contratos"][0]
        assert contrato["status"] == "assinado"
        versoes = contrato["versoes"]
        assinada = [v for v in versoes if v["origem"] == "assinado"]
        assert len(assinada) == 1
        assert assinada[0]["numero"] == 2

        assinatura = _get(client, cid, ids["contrato_id"]).json()
        assert assinatura["status"] == "concluido"
        assert assinatura["concluido_em"] is not None
        assert assinatura["versao_assinada_id"] == assinada[0]["id"]

    def test_replaying_the_identical_event_is_idempotent(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r_env = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        external_id = r_env.json()["external_id"]
        fake_signature_adapter.marcar_assinado(external_id, "ana@example.com")

        r1 = _post_webhook(client, "d4sign", {"external_id": external_id, "status": "concluido"})
        assert r1.status_code == 200
        r2 = _post_webhook(client, "d4sign", {"external_id": external_id, "status": "concluido"})
        assert r2.status_code == 200

        contrato = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()["contratos"][0]
        assinadas = [v for v in contrato["versoes"] if v["origem"] == "assinado"]
        # A replay must NOT double-process — exactly one signed version, not two.
        assert len(assinadas) == 1

    def test_a_replayed_cancelado_after_concluido_is_refused_not_applied(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        """2026-09-20 wiring audit, task 4: a webhook body carries no
        nonce/timestamp, so a captured `cancelado` delivery replayed AFTER
        `concluido` already landed must not regress the contract back to
        cancelled — `is_forward_transition` refuses it."""
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        r_env = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        external_id = r_env.json()["external_id"]

        fake_signature_adapter.marcar_assinado(external_id, "ana@example.com")
        r_concluido = _post_webhook(client, "d4sign", {"external_id": external_id, "status": "concluido"})
        assert r_concluido.status_code == 200
        assert r_concluido.json() == {"ok": True}

        r_replay = _post_webhook(client, "d4sign", {"external_id": external_id, "status": "cancelado"})
        assert r_replay.status_code == 200
        assert r_replay.json() == {"ok": True, "ignorado": True, "motivo": "transicao_regressiva"}

        assinatura = _get(client, cid, ids["contrato_id"]).json()
        assert assinatura["status"] == "concluido"

        contrato = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()["contratos"][0]
        assert contrato["status"] == "assinado"
