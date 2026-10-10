"""P5 audit (2026-10-03) — extraction values that were read but never landed.

WHAT THESE PIN (all synthetic — invented names, numbers and addresses)
-----------------------------------------------------------------------
- **F1** — owner rule H1, "the first document fills empty fields": a field
  that is EMPTY in all but representation (`'—'`, `'null'`) is FILLED, never
  conflicted; and the data repair (`backfill_resolver_conflitos_pendentes`,
  run by resolve-on-read and the "Resolver conflitos" button) settles an
  EXISTING pending conflict whose on-file side is empty by applying the
  proposal — audited `resolvido_automatico`, `[vazio_preenchido]`, the
  document named as evidence.
- **B5** — an identity document (CNH / RG / CIN) whose transcription the
  seed flagged as incomplete still lands what it read, with provenance; an
  apply-side refusal is no longer hidden behind the seed's own aviso; a
  comprovante lands without a CEP and with a joint ("A E B") holder line.
- **F4** — a certidão de nascimento with no marriage evidence anywhere
  fills an empty estado civil with `solteiro` (machine-pending), live and
  for certidões read before the rule existed.
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.documents import (
    EnderecoLido,
    ExtractionConfidence,
    FakeIdentityExtractor,
    IdentityFields,
    TextSource,
)
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

BUCKET = "social-wiring-documentos"
ORG_UUID = UUID(ORG_ID)
A = ExtractionConfidence.ALTA
B = ExtractionConfidence.BAIXA

CPF_VALIDO = "390.533.447-05"
CPF_INVALIDO = "390.533.447-00"


async def _setup(scoped, *, tipo="rg", cliente=None, outros=(), docs=()):
    cid, did = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, **(cliente or {})), *outros])
    path = f"{ORG_ID}/clientes/{cid}/{did}"
    scoped.set_table_data("cliente_documentos", [{
        "id": did, "org_id": ORG_ID, "cliente_id": cid,
        "storage_path": path, "nome_original": f"{tipo}.pdf",
        "mime_type": "application/pdf", "tipo_documento": tipo,
        "deleted_at": None, "extracao_status": "pendente",
        "extracao_tentativas": 0, "extracao_descartada_em": None,
        "created_at": "2026-10-01T00:00:00+00:00",
    }, *[{**d, "cliente_id": d.get("cliente_id", cid)} for d in docs]])
    scoped.set_table_data("cliente_documento_acessos", [])
    scoped.set_table_data("cliente_campo_conflitos", [])
    storage = FakeStorageBackend()
    await storage.put(bucket=BUCKET, key=path, data=b"%PDF-1.4", content_type="application/pdf")
    return cid, did, storage


def _cliente(scoped, cid) -> dict:
    return next(r for r in scoped.table("clientes").select("*").execute().data if r["id"] == cid)


def _documento(scoped, did) -> dict:
    return next(
        r for r in scoped.table("cliente_documentos").select("*").execute().data if r["id"] == did
    )


def _conflitos(scoped) -> list[dict]:
    return scoped.table("cliente_campo_conflitos").select("*").execute().data


async def _extrair(scoped, storage, cid, did, fields):
    return await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=FakeIdentityExtractor(fields),
    )


# ─── F1 ──────────────────────────────────────────────────────────────────────


class TestF1PlaceholderIsEmpty:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("marcador", ["—", "null", " - "])
    async def test_a_placeholder_on_file_is_filled_not_conflicted(self, client, scoped, marcador):
        cid, did, storage = await _setup(
            scoped, cliente={"profissao": marcador, "profissao_origem": "ficha_cadastral"},
        )
        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="engenheiro", profissao_confianca=A, profissao_rotulo="PROFISSAO",
            source=TextSource.OCR,
        ))
        row = _cliente(scoped, cid)
        assert row["profissao"] == "engenheiro"
        assert row["profissao_origem"] == "rg"
        assert row["profissao_documento_id"] == did
        assert row.get("profissao_confirmado_em") is None
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_a_manually_typed_placeholder_is_not_a_clear(self, client, scoped):
        """`'—'` typed by a human says "unknown" — not the explicit clear
        (`origem='manual'`, blank) the machine must respect."""
        cid, did, storage = await _setup(
            scoped, cliente={"profissao": "—", "profissao_origem": "manual"},
        )
        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="engenheiro", profissao_confianca=A, source=TextSource.OCR,
        ))
        assert _cliente(scoped, cid)["profissao"] == "engenheiro"

    @pytest.mark.asyncio
    async def test_a_human_clear_is_still_respected(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, cliente={"profissao": None, "profissao_origem": "manual"},
        )
        await _extrair(scoped, storage, cid, did, IdentityFields(
            profissao="engenheiro", profissao_confianca=A, source=TextSource.OCR,
        ))
        assert _cliente(scoped, cid).get("profissao") is None


def _conflito(cid, campo, *, anterior=None, proposto, origem="rg", fonte=None, **over) -> dict:
    row = {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": campo,
        "valor_anterior": anterior, "origem_anterior": None,
        "valor_proposto": proposto, "origem_proposto": origem,
        "confianca_proposta": "baixa",
        "fonte_tabela": "cliente_documentos" if fonte else None,
        "fonte_id": fonte, "status": "pendente", "notificado_em": None,
        "decidido_por": None, "decidido_em": None,
        "created_at": "2026-10-02T00:00:00+00:00",
    }
    row.update(over)
    return row


class TestF1RepairExistingConflicts:
    def _seed(self, scoped, cliente, conflitos, docs=()):
        cid = cliente["id"]
        scoped.set_table_data("clientes", [cliente])
        scoped.set_table_data("cliente_documentos", list(docs))
        scoped.set_table_data("cliente_campo_conflitos", conflitos)
        return cid

    def test_a_conflict_against_an_empty_field_is_settled_by_filling_it(self, scoped):
        cid, did = str(uuid4()), str(uuid4())
        c = _conflito(cid, "profissao", proposto="engenheiro", fonte=did)
        self._seed(scoped, cliente_row(cid), [c], docs=[{
            "id": did, "org_id": ORG_ID, "cliente_id": cid, "tipo_documento": "rg",
            "deleted_at": None,
        }])
        out = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)

        row = _cliente(scoped, cid)
        assert row["profissao"] == "engenheiro"
        assert row["profissao_origem"] == "rg"
        assert row["profissao_documento_id"] == did
        assert row.get("profissao_confirmado_em") is None  # machine-pending
        (settled,) = _conflitos(scoped)
        assert settled["status"] == "resolvido_automatico"
        assert settled["decidido_por"] is None
        assert settled["motivo_resolucao"].startswith(f"[{svc.REGRA_VAZIO_PREENCHIDO}]")
        assert did in settled["motivo_resolucao"]
        assert [r["decisao_regra"] for r in out["resolvidos"]] == [svc.REGRA_VAZIO_PREENCHIDO]

    def test_an_empty_endereco_group_is_filled_from_the_conflict(self, scoped):
        cid, did = str(uuid4()), str(uuid4())
        proposto = json.dumps({
            "cep": "01454-011", "logradouro": "R EXEMPLO SINTETICO", "numero": "10",
            "complemento": None, "bairro": "BAIRRO TESTE", "cidade": "SAO PAULO", "uf": "SP",
            "titular": "PESSOA DE TESTE",
        })
        c = _conflito(cid, "endereco", proposto=proposto, origem="comprovante_endereco", fonte=did)
        self._seed(scoped, cliente_row(cid), [c])
        svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        row = _cliente(scoped, cid)
        assert (row["endereco_cep"], row["endereco_logradouro"], row["endereco_uf"]) == (
            "01454-011", "R EXEMPLO SINTETICO", "SP",
        )
        assert row["endereco_origem"] == "comprovante_endereco"
        assert row["endereco_documento_id"] == did
        assert _conflitos(scoped)[0]["status"] == "resolvido_automatico"

    def test_a_value_cleared_after_the_conflict_opened_is_a_human_matter(self, scoped):
        """The snapshot was a REAL value — not the F1 shape."""
        cid = str(uuid4())
        c = _conflito(cid, "profissao", anterior="advogado", proposto="engenheiro")
        self._seed(scoped, cliente_row(cid), [c])
        svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert _cliente(scoped, cid).get("profissao") is None
        assert not str(_conflitos(scoped)[0].get("motivo_resolucao") or "").startswith(
            f"[{svc.REGRA_VAZIO_PREENCHIDO}]"
        )

    def test_an_explicit_human_clear_is_not_refilled(self, scoped):
        cid = str(uuid4())
        c = _conflito(cid, "profissao", proposto="engenheiro")
        self._seed(scoped, cliente_row(cid, profissao=None, profissao_origem="manual"), [c])
        svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert _cliente(scoped, cid).get("profissao") is None

    def test_an_invalid_cpf_proposal_is_never_filled(self, scoped):
        cid = str(uuid4())
        c = _conflito(cid, "cpf", proposto=CPF_INVALIDO)
        self._seed(scoped, cliente_row(cid), [c])
        svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)
        assert _cliente(scoped, cid).get("cpf") is None

    def test_resolve_on_read_settles_it_through_the_listing_route(self, client, scoped):
        cid = str(uuid4())
        c = _conflito(cid, "profissao", proposto="engenheiro")
        self._seed(scoped, cliente_row(cid), [c])
        r = client.get("/api/clientes/conflitos", headers={"Authorization": "Bearer test-token"})
        assert r.status_code == 200, r.text
        assert r.json() == []
        assert _cliente(scoped, cid)["profissao"] == "engenheiro"


# ─── B5 ──────────────────────────────────────────────────────────────────────


class TestB5IdentityDocumentsLand:
    """The seed flags an incomplete transcription (`campos_nucleo_ausentes`)
    — NOT a compromised one. What WAS read must still land, per type."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tipo", ["cnh", "rg", "cin"])
    async def test_what_was_read_lands_with_provenance(self, client, scoped, tipo):
        cid, did, storage = await _setup(scoped, tipo=tipo)
        rg = CPF_VALIDO if tipo == "cin" else "30.128.742-9"
        orgao = "IIGDR" if tipo == "cin" else "SSP/SP"
        await _extrair(scoped, storage, cid, did, IdentityFields(
            nome="PESSOA SINTETICA DE TESTE", nome_confianca=B,
            cpf=CPF_VALIDO, cpf_confianca=B,
            rg=rg, rg_confianca=B, rg_orgao=orgao, rg_orgao_confianca=B,
            rg_rotulo="REGISTRO GERAL",
            aviso="campos_nucleo_ausentes", aviso_mensagem="Campos ausentes",
            source=TextSource.OCR,
        ))
        row = _cliente(scoped, cid)
        for campo in ("nome_oficial", "cpf", "rg", "rg_orgao_expedidor"):
            assert row.get(campo), campo
            assert row[f"{campo}_origem"] == tipo, campo
            assert row[f"{campo}_documento_id"] == did, campo
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_an_apply_refusal_is_not_hidden_behind_the_seed_aviso(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="rg")
        await _extrair(scoped, storage, cid, did, IdentityFields(
            cpf=CPF_INVALIDO, cpf_confianca=B,
            aviso="campos_nucleo_ausentes", aviso_mensagem="Campos ausentes",
            source=TextSource.OCR,
        ))
        doc = _documento(scoped, did)
        assert doc["extracao_aviso"] == "campos_nucleo_ausentes+cpf_invalido"
        assert _cliente(scoped, cid).get("cpf") is None

    @pytest.mark.asyncio
    async def test_a_comprovante_without_a_cep_still_fills_the_group(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="comprovante_endereco", cliente={"nome": "Pessoa Sintetica"},
        )
        await _extrair(scoped, storage, cid, did, IdentityFields(
            endereco=EnderecoLido(
                cep=None, logradouro="R EXEMPLO SINTETICO", numero="10", complemento=None,
                bairro="BAIRRO TESTE", cidade="SAO PAULO", uf="SP",
                titular=None, confianca="baixa", rotulo="ENDERECO",
            ),
            source=TextSource.OCR,
        ))
        row = _cliente(scoped, cid)
        assert row["endereco_logradouro"] == "R EXEMPLO SINTETICO"
        assert row.get("endereco_cep") is None
        assert row["endereco_origem"] == "comprovante_endereco"


# ─── F4 ──────────────────────────────────────────────────────────────────────


def _certidao_nascimento() -> IdentityFields:
    return IdentityFields(
        nome="PESSOA SINTETICA DE TESTE", nome_confianca=A, source=TextSource.TEXT_LAYER,
    )


class TestF4CertidaoNascimentoProvesSolteiro:
    @pytest.mark.asyncio
    async def test_no_averbacao_suggests_solteiro_but_never_writes_the_cliente(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="certidao_nascimento")
        await _extrair(scoped, storage, cid, did, _certidao_nascimento())
        row = _cliente(scoped, cid)
        assert row.get("estado_civil") is None
        assert row.get("estado_civil_origem") is None
        assert row.get("estado_civil_documento_id") is None
        sug = svc.sugestoes_pendentes(scoped, ORG_UUID, UUID(cid))
        assert sug["estado_civil"]["valor"] == svc.ESTADO_CIVIL_SOLTEIRO
        assert sug["estado_civil"]["rotulo"] == svc.ROTULO_SOLTEIRO_INFERIDO
        doc = _documento(scoped, did)
        assert doc["extracao_estado_civil"] == svc.ESTADO_CIVIL_SOLTEIRO
        assert doc["extracao_estado_civil_rotulo"] == svc.ROTULO_SOLTEIRO_INFERIDO

    @pytest.mark.asyncio
    async def test_a_certidao_de_casamento_on_the_card_blocks_it(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="certidao_nascimento", docs=[{
            "id": str(uuid4()), "org_id": ORG_ID, "tipo_documento": "certidao_casamento",
            "deleted_at": None, "extracao_descartada_em": None, "extracao_status": "ok",
            "created_at": "2026-09-01T00:00:00+00:00",
        }])
        await _extrair(scoped, storage, cid, did, _certidao_nascimento())
        assert _cliente(scoped, cid).get("estado_civil") is None

    @pytest.mark.asyncio
    async def test_a_spouse_link_blocks_it(self, client, scoped):
        conjuge = str(uuid4())
        cid, did, storage = await _setup(
            scoped, tipo="certidao_nascimento", cliente={"conjuge_cliente_id": conjuge},
            outros=[cliente_row(conjuge, nome="Conjuge Sintetico", conjuge_cliente_id=None)],
        )
        await _extrair(scoped, storage, cid, did, _certidao_nascimento())
        assert _cliente(scoped, cid).get("estado_civil") is None

    @pytest.mark.asyncio
    async def test_a_different_value_on_file_is_never_overwritten_nor_contested(self, client, scoped):
        cid, did, storage = await _setup(
            scoped, tipo="certidao_nascimento",
            cliente={"estado_civil": "casado", "estado_civil_origem": "manual"},
        )
        await _extrair(scoped, storage, cid, did, _certidao_nascimento())
        assert _cliente(scoped, cid)["estado_civil"] == "casado"
        # An inference never opens a conflict either (owner rule 2026-10-10).
        assert _conflitos(scoped) == []

    @pytest.mark.asyncio
    async def test_backfill_records_suggestion_only_and_never_writes_the_cliente(self, client, scoped):
        cid, did, storage = await _setup(scoped, tipo="certidao_nascimento")
        scoped.table("cliente_documentos").update({
            "extracao_status": "ok", "extracao_estado_civil": None, "extracao_aviso": None,
        }).eq("id", did).execute()
        assert svc.backfill_solteiro_por_certidao_nascimento(scoped, ORG_UUID) == 1
        row = _cliente(scoped, cid)
        assert row.get("estado_civil") is None
        assert row.get("estado_civil_documento_id") is None
        doc = _documento(scoped, did)
        assert doc["extracao_estado_civil"] == svc.ESTADO_CIVIL_SOLTEIRO
        assert doc["extracao_estado_civil_rotulo"] == svc.ROTULO_SOLTEIRO_INFERIDO
        # Idempotent — a second pass changes nothing and opens nothing.
        svc.inferir_solteiro_por_certidao_nascimento(scoped, ORG_UUID, UUID(cid))
        assert _cliente(scoped, cid).get("estado_civil") is None
        assert _conflitos(scoped) == []
