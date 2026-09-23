"""Migration 157 — `modalidade_assinatura`: digital (e-signature) | física.

WHAT THESE PIN
--------------
- the DIGITAL instrument is byte-identical to the pre-157 one: the rendered
  `word/document.xml` and the ABNT PDF's extracted text hash to the values
  captured from `origin/dev` BEFORE this change, for all six spec variants
  (if you change the template's wording ON PURPOSE, regenerate these hashes
  from the new render and say so in the commit — a silent change here is
  exactly what this test exists to catch);
- the FÍSICA instrument: no DA ASSINATURA DIGITAL clause, clause numbers
  re-flow (every later clause shifts down one, references included), the
  closing names the vias, and a signature line sits above EVERY signer
  (name + CPF) and EVERY witness (name + CPF/RG) — no e-mail anywhere;
- the gate: a física contract never needs the signing platform configured,
  nor witness/party e-mails;
- the API gates: PATCH read/write of the field; 409
  `CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO` going física under a live
  envelope; 409 `CONTRATO_FISICO_SEM_ASSINATURA_DIGITAL` on `enviar`; and the
  physical close-out `POST .../assinatura-fisica` (status + stamps + the
  optional scanned PDF as an `origem='assinado'` version, LGPD-logged store).
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import replace
from uuid import uuid4

import fitz
import pytest

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub.contrato_gerador import derivacao, documento, frases, lint
from app.modules.card_hub.deps import BUCKET
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

LINHA = "______________________________"

#: [Owner directive, 2026-09-23] Re-pinned: the base fixture now carries
#: witness e-mails (a witness's e-mail moved from aviso to a hard
#: `faltando`) and a matrícula-derived `Matricula.comarca` (the DA
#: ELEIÇÃO DO FORO clause no longer silently computes the comarca from
#: the imóvel address) — both real, intended content changes, not drift.
#: Variants 1..6 of `contrato_gerador_fixtures`: sha256(word/document.xml),
#: sha256(PDF text via PyMuPDF).
_DIGITAL_GOLDEN: dict[int, tuple[str, str]] = {
    1: ("a8b83886b035ad96ce221f444b65d6ef59363e506ed30b1c3c5b0aad0c18a9ea",
        "e1a2c89cb443fdc768c313805c2d882067d5adfef9f6f531f0aea336d19c7103"),
    2: ("0895a928325c856a8daa4acaf35fcf60b7dadc5772e4bdf196796749d3635596",
        "79ee973a69ff4a683aef319ddac3081306dfe19c7010c939ef3dfd9b8bb55d4b"),
    3: ("c8d351dbcda9e5ada05ac4de76dec42c1da36403044637e0d6782ab55e4bba6b",
        "d7ed933fe5a1fa24cc38b3fb8836147bc5e3b2549669760b3fd64e66b78978e7"),
    4: ("654d76006fe6779078a53848aa6832f56c599e7f37beb33cd8a0c3b7ff0f67f8",
        "d2009718bb6cffe8cac0311bc040e0470d4654b78b6f24c8c5079b45e25dad26"),
    5: ("fc06fae5f648559dc525b3eba639774e8ec9780bd094240adeba689cd16df35e",
        "a6b1e153d6c1675fe74237a993fc32b594263242566cd73ec6f7c41bc9b9b427"),
    6: ("1cfd315c7099754f3d7d604df03d47b8991a12397b79eb19e09125f652d38534",
        "63146523a1ade8e3cbed8a1af76a45c23ee935a0850f434b26eef7eb11a5e136"),
}


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _fisica(d):
    return replace(d, modalidade_assinatura="fisica")


def _avaliar(n: int, d=None):
    d = d if d is not None else fx.variante(n)
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol)
    return d, pol, sw, derivacao.avaliar(d, sw, pol, fx.ASSINATURA)


def _render(n: int, d=None):
    d, pol, sw, av = _avaliar(n, d)
    assert av.pronto, (av.faltando, av.bloqueios)
    return documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA)


def _pdf_texto(docx: bytes) -> str:
    pdf = documento.gerar_pdf(docx)
    return "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))


def _clausulas(paragrafos):
    return [p for p in paragrafos if p.startswith("CLÁUSULA ")]


# ─── template ──────────────────────────────────────────────────────────────


class TestDigitalIsByteIdentical:
    @pytest.mark.parametrize("n", range(1, 7))
    def test_default_contract_renders_the_pre_157_instrument(self, n):
        d = fx.variante(n)
        assert d.modalidade_assinatura == "digital"
        r = _render(n, d)
        xml_sha, pdf_sha = _DIGITAL_GOLDEN[n]
        assert _sha(documento.document_xml(r.docx)) == xml_sha
        assert _sha(_pdf_texto(r.docx)) == pdf_sha

    def test_digital_switch_is_on(self):
        _d, _pol, sw, _av = _avaliar(1)
        assert sw["tem_assinatura_digital"] is True


class TestFisicaTemplate:
    @pytest.mark.parametrize("n", range(1, 7))
    def test_the_digital_clause_is_gone_and_numbering_reflows(self, n):
        digital, fisica = _render(n), _render(n, _fisica(fx.variante(n)))
        assert "assinatura_digital" in digital.clausulas
        assert "assinatura_digital" not in fisica.clausulas
        assert not any("DA ASSINATURA DIGITAL" in p for p in fisica.paragrafos)
        assert not any("plataforma" in p.lower() for p in fisica.paragrafos)

        corte = digital.clausulas["assinatura_digital"]
        for chave, numero in digital.clausulas.items():
            if chave == "assinatura_digital":
                continue
            esperado = numero - 1 if numero > corte else numero
            assert fisica.clausulas[chave] == esperado, chave
        ordinais = [c.split(" – ")[0].split(" - ")[0] for c in _clausulas(fisica.paragrafos)]
        assert len(ordinais) == len(_clausulas(digital.paragrafos)) - 1
        assert lint.lint(fisica.paragrafos, referencias=fisica.referencias, clausulas=fisica.clausulas) == []

    def test_closing_names_the_vias(self):
        r = _render(1, _fisica(fx.variante(1)))
        assert (
            "E, por estarem assim justos e contratados, os contraentes assinam o presente "
            "instrumento em 02 (duas) vias de igual teor e forma, na presença das testemunhas "
            "abaixo identificadas."
        ) in r.paragrafos
        assert not any("de forma digital" in p for p in r.paragrafos)

    def test_vias_follow_the_number_of_signers(self):
        d = fx.variante(1)
        outra = fx.pessoa("c2", "comprador", "comprador", "Ciclana Segunda", "Feminino", "555666777", "77.777.777-7")
        d = _fisica(replace(d, compradores=[*d.compradores, outra]))
        r = _render(1, d)
        assert any("em 03 (três) vias de igual teor" in p for p in r.paragrafos)
        assert LINHA in r.paragrafos
        assert "CICLANA SEGUNDA" in r.paragrafos

    def test_a_signature_line_above_every_signer_and_witness(self):
        d = _fisica(fx.variante(1))
        r = _render(1, d)
        ps = r.paragrafos
        fim = ps.index("TESTEMUNHAS:")
        inicio = next(i for i, p in enumerate(ps) if p.startswith("E, por estarem assim"))
        bloco_partes, bloco_testemunhas = ps[inicio:fim], ps[fim:]

        # One line per signer, each directly followed by NAME then CPF.
        pares = [(bloco_partes[i + 1], bloco_partes[i + 2]) for i, p in enumerate(bloco_partes) if p == LINHA]
        assert pares == [
            ("FULANO DE TAL", f"CPF {frases.documento(d.vendedores[0].cpf)[1]}"),
            ("BELTRANA EXEMPLO", f"CPF {frases.documento(d.compradores[0].cpf)[1]}"),
        ]
        # One line per witness: NAME then CPF / RG.
        t1, t2 = d.testemunhas
        pares_t = [(bloco_testemunhas[i + 1], bloco_testemunhas[i + 2])
                   for i, p in enumerate(bloco_testemunhas) if p == LINHA]
        assert pares_t == [
            ("TESTEMUNHA UM", f"CPF {frases.documento(t1.cpf)[1]} / RG 33.333.333-3"),
            ("TESTEMUNHA DOIS", f"CPF {frases.documento(t2.cpf)[1]} / RG 44.444.444-4"),
        ]
        # Nothing is e-mailed for a física contract — no e-mail is printed.
        assert not any(re.search(r"@\S+\.\S+", p) for p in ps[inicio:])

    def test_a_witness_without_cpf_prints_only_the_rg(self):
        d = fx.variante(1)
        t1, t2 = d.testemunhas
        d = _fisica(replace(d, testemunhas=[replace(t1, cpf=None), t2]))
        r = _render(1, d)
        i = r.paragrafos.index("TESTEMUNHA UM")
        assert r.paragrafos[i - 1] == LINHA
        assert r.paragrafos[i + 1] == "RG 33.333.333-3"

    def test_the_fisica_pdf_renders(self):
        texto = _pdf_texto(_render(5, _fisica(fx.variante(5))).docx)
        assert LINHA in texto
        assert "DA ASSINATURA DIGITAL" not in texto


class TestFisicaGate:
    def test_no_platform_is_needed_for_a_fisica_contract(self):
        d = fx.variante(1)
        sem_plataforma = replace(
            d.imobiliaria, plataforma_assinatura_nome=None, plataforma_assinatura_url=None
        )
        _d, _pol, _sw, av_digital = _avaliar(1, replace(d, imobiliaria=sem_plataforma))
        assert "imobiliaria.plataforma_assinatura" in {f["campo"] for f in av_digital.faltando}

        _d, _pol, sw, av_fisica = _avaliar(1, _fisica(replace(d, imobiliaria=sem_plataforma)))
        assert sw["tem_assinatura_digital"] is False
        assert av_fisica.pronto, (av_fisica.faltando, av_fisica.bloqueios)

    def test_missing_emails_are_gated_only_for_a_digital_contract(self):
        """🔴 [Owner directive, 2026-09-23 — supersedes the 2026-09-22
        TESTEMUNHA_SEM_EMAIL aviso] A missing witness e-mail now BLOCKS a
        digital contract (`imobiliaria.testemunha.N.email`, same footing
        as nome/RG) instead of only warning; the comprador's own missing
        e-mail (`PARTE_SEM_EMAIL`) is unaffected — still an aviso. Neither
        gate applies at all to a física contract (migration 157)."""
        d = fx.variante(1)
        t1, t2 = d.testemunhas
        d = replace(
            d,
            testemunhas=[replace(t1, email=None), replace(t2, email=None)],
            compradores=[replace(d.compradores[0], email=None)],
        )
        _d, _pol, _sw, av_digital = _avaliar(1, d)
        assert {"imobiliaria.testemunha.1.email", "imobiliaria.testemunha.2.email"} <= {
            f["campo"] for f in av_digital.faltando
        }
        assert "PARTE_SEM_EMAIL" in {a["codigo"] for a in av_digital.avisos}

        _d, _pol, _sw, av_fisica = _avaliar(1, _fisica(d))
        assert not any(f["campo"].startswith("imobiliaria.testemunha.") for f in av_fisica.faltando)
        assert "PARTE_SEM_EMAIL" not in {a["codigo"] for a in av_fisica.avisos}


# ─── API ──────────────────────────────────────────────────────────────────

CPF_VALIDO = "52998224725"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed(scoped, *, modalidade: str | None = None, status: str = "em_revisao",
          com_versao: bool = True, fake_storage=None) -> dict:
    cid, aid, contrato_id, versao_id = (str(uuid4()) for _ in range(4))
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [{
        "id": aid, "org_id": ORG_ID, "cliente_id": cid, "lead_id": None, "meta_ads_lead_id": None,
        "status": "aberta", "substituida_por": None, "arquivado": False, "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00", "closed_at": None,
    }])
    contrato = {
        "id": contrato_id, "org_id": ORG_ID, "atendimento_id": aid,
        "titulo": "Contrato gerado", "modelo": "compra_venda", "status": status,
        "status_em": None, "status_por": None, "origem": "gerado", "criado_por": None,
        "deleted_at": None, "delete_motivo": None, "delete_solicitado_por": None,
        "created_at": "2026-09-16T00:00:00+00:00", "updated_at": None,
        "assinatura_data": None, "prazo_pendencias_dias": None,
    }
    if modalidade is not None:
        contrato["modalidade_assinatura"] = modalidade
    scoped.set_table_data("atendimento_contratos", [contrato])
    versoes = []
    if com_versao:
        pdf_path = f"{ORG_ID}/contratos/{contrato_id}/{versao_id}"
        if fake_storage is not None:
            asyncio.run(fake_storage.put(bucket=BUCKET, key=pdf_path, data=b"%PDF-1.7 fake",
                                         content_type="application/pdf"))
            asyncio.run(fake_storage.put(bucket=BUCKET, key=f"{pdf_path}.docx", data=b"PK fake",
                                         content_type=contratos_svc.MIME_DOCX))
        versoes.append({
            "id": versao_id, "org_id": ORG_ID, "contrato_id": contrato_id,
            "storage_path": pdf_path, "nome_original": "contrato-gerado-v1.pdf",
            "mime_type": "application/pdf", "tamanho_bytes": 13,
            "tipo_documento": contratos_svc.TIPO_VERSAO, "numero": 1, "rotulo": None,
            "origem": "gerado", "enviado_por": None, "deleted_at": None,
            "delete_motivo": None, "delete_solicitado_por": None,
            "created_at": "2026-09-16T00:00:00+00:00", "contexto_sha256": "a" * 64,
            "docx_storage_path": f"{pdf_path}.docx", "docx_tamanho_bytes": 7,
        })
    scoped.set_table_data("atendimento_contrato_versoes", versoes)
    scoped.set_table_data("atendimento_contrato_versao_acessos", [])
    scoped.set_table_data("atendimento_contrato_assinaturas", [])
    return {"cliente": cid, "contrato": contrato_id, "versao": versao_id}


def _url(ids: dict, sufixo: str = "") -> str:
    return f"/api/clientes/{ids['cliente']}/contratos/{ids['contrato']}{sufixo}"


def _contrato(client, ids) -> dict:
    return client.get(f"/api/clientes/{ids['cliente']}/contratos", headers=_auth()).json()["contratos"][0]


def _envelope_vivo(scoped, ids, status: str = "pendente") -> None:
    scoped.set_table_data("atendimento_contrato_assinaturas", [{
        "id": str(uuid4()), "org_id": ORG_ID, "contrato_id": ids["contrato"],
        "versao_id": ids["versao"], "provedor": "d4sign", "external_id": "ext-1",
        "link_assinatura": "https://x.test", "status": status, "signatarios": [],
        "enviado_em": "2026-09-16T00:00:00+00:00", "enviado_por": None, "concluido_em": None,
        "versao_assinada_id": None, "cancelado_motivo": None,
        "created_at": "2026-09-16T00:00:00+00:00", "updated_at": None,
    }])


class TestCampoNoContrato:
    def test_a_pre_157_row_reads_as_digital(self, client, scoped):
        ids = _seed(scoped)
        assert _contrato(client, ids)["modalidade_assinatura"] == "digital"

    def test_patch_switches_to_fisica_and_back(self, client, scoped):
        ids = _seed(scoped, modalidade="digital")
        r = client.patch(_url(ids), json={"modalidade_assinatura": "fisica"}, headers=_auth())
        assert r.status_code == 200, r.text
        assert r.json()["modalidade_assinatura"] == "fisica"
        assert _contrato(client, ids)["modalidade_assinatura"] == "fisica"

        r = client.patch(_url(ids), json={"modalidade_assinatura": "digital"}, headers=_auth())
        assert r.status_code == 200, r.text
        assert r.json()["modalidade_assinatura"] == "digital"

    def test_an_unknown_value_is_refused(self, client, scoped):
        ids = _seed(scoped)
        r = client.patch(_url(ids), json={"modalidade_assinatura": "fax"}, headers=_auth())
        assert r.status_code == 422

    @pytest.mark.parametrize("status_envelope", ["pendente", "parcial"])
    def test_going_fisica_under_a_live_envelope_is_409(self, client, scoped, status_envelope):
        ids = _seed(scoped, modalidade="digital", status="enviado_assinatura")
        _envelope_vivo(scoped, ids, status_envelope)
        r = client.patch(_url(ids), json={"modalidade_assinatura": "fisica"}, headers=_auth())
        assert r.status_code == 409
        erro = r.json()["error"]
        assert erro["code"] == "CONTRATO_COM_ASSINATURA_DIGITAL_EM_ANDAMENTO"
        assert "Cancele" in erro["message"]
        assert _contrato(client, ids)["modalidade_assinatura"] == "digital"

    def test_a_finished_envelope_does_not_block_the_switch(self, client, scoped):
        ids = _seed(scoped, modalidade="digital")
        _envelope_vivo(scoped, ids, "cancelado")
        r = client.patch(_url(ids), json={"modalidade_assinatura": "fisica"}, headers=_auth())
        assert r.status_code == 200, r.text


class TestEnviarGate:
    def test_enviar_on_a_fisica_contract_is_409_and_never_reaches_the_provider(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        ids = _seed(scoped, modalidade="fisica", fake_storage=fake_storage)
        r = client.post(_url(ids, "/assinatura"), json={
            "versao_id": ids["versao"],
            "signatarios": [{"nome": "Ana", "email": "ana@example.com", "cpf": CPF_VALIDO,
                             "papel": "comprador", "ordem": 0}],
        }, headers=_auth())
        assert r.status_code == 409
        erro = r.json()["error"]
        assert erro["code"] == "CONTRATO_FISICO_SEM_ASSINATURA_DIGITAL"
        assert "assinatura física" in erro["message"]
        assert fake_signature_adapter.calls == []
        assert scoped.table("atendimento_contrato_assinaturas").select("*").execute().data == []

    def test_enviar_on_a_digital_contract_still_sends(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        ids = _seed(scoped, modalidade="digital", fake_storage=fake_storage)
        r = client.post(_url(ids, "/assinatura"), json={
            "versao_id": ids["versao"],
            "signatarios": [{"nome": "Ana", "email": "ana@example.com", "cpf": CPF_VALIDO,
                             "papel": "comprador", "ordem": 0}],
        }, headers=_auth())
        assert r.status_code == 201, r.text


class TestAssinaturaFisica:
    def _marcar(self, client, ids, arquivo=None):
        files = {"file": arquivo} if arquivo is not None else None
        return client.post(_url(ids, "/assinatura-fisica"), files=files, headers=_auth())

    def test_marks_signed_with_stamps_and_no_file(self, client, scoped, fake_storage):
        ids = _seed(scoped, modalidade="fisica")
        r = self._marcar(client, ids)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "assinado"
        assert body["status_em"]
        linha = scoped.table("atendimento_contratos").select("*").execute().data[0]
        assert linha["status"] == "assinado" and linha["status_por"]
        assert len(body["versoes"]) == 1  # nothing uploaded

    def test_the_scanned_pdf_becomes_an_assinado_version(self, client, scoped, fake_storage):
        ids = _seed(scoped, modalidade="fisica")
        r = self._marcar(client, ids, ("assinado.pdf", b"%PDF-1.7 scan", "application/pdf"))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "assinado"
        assert body["versao_atual"]["origem"] == "assinado"
        assert body["versao_atual"]["numero"] == 2
        assert body["versao_atual"]["enviado_por"] is not None
        nova = [v for v in scoped.table("atendimento_contrato_versoes").select("*").execute().data
                if v["origem"] == "assinado"][0]
        blob = asyncio.run(fake_storage.get(bucket=BUCKET, key=nova["storage_path"]))
        assert blob is not None and blob.data == b"%PDF-1.7 scan"

    def test_a_scan_can_arrive_after_the_contract_was_marked(self, client, scoped, fake_storage):
        ids = _seed(scoped, modalidade="fisica")
        assert self._marcar(client, ids).status_code == 200
        antes = scoped.table("atendimento_contratos").select("*").execute().data[0]
        r = self._marcar(client, ids, ("assinado.pdf", b"%PDF-1.7 scan", "application/pdf"))
        assert r.status_code == 200, r.text
        depois = scoped.table("atendimento_contratos").select("*").execute().data[0]
        assert depois["status_em"] == antes["status_em"]  # who/when marked it stays
        assert r.json()["versao_atual"]["origem"] == "assinado"

    def test_marking_twice_without_a_file_is_409(self, client, scoped, fake_storage):
        ids = _seed(scoped, modalidade="fisica")
        assert self._marcar(client, ids).status_code == 200
        r = self._marcar(client, ids)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "CONTRATO_JA_ASSINADO"

    def test_a_digital_contract_cannot_be_marked_by_hand(self, client, scoped, fake_storage):
        ids = _seed(scoped, modalidade="digital")
        r = self._marcar(client, ids)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "CONTRATO_NAO_E_FISICO"

    def test_a_non_pdf_scan_is_400(self, client, scoped, fake_storage):
        ids = _seed(scoped, modalidade="fisica")
        r = self._marcar(client, ids, ("assinado.docx", b"PK", contratos_svc.MIME_DOCX))
        assert r.status_code == 400
        assert scoped.table("atendimento_contratos").select("*").execute().data[0]["status"] == "em_revisao"

    def test_a_cancelled_contract_is_409(self, client, scoped, fake_storage):
        ids = _seed(scoped, modalidade="fisica", status="cancelado")
        r = self._marcar(client, ids)
        assert r.status_code == 409

    def test_unknown_contract_is_404(self, client, scoped, fake_storage):
        ids = _seed(scoped, modalidade="fisica")
        r = self._marcar(client, {**ids, "contrato": str(uuid4())})
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "CONTRATO_NAO_ENCONTRADO"
