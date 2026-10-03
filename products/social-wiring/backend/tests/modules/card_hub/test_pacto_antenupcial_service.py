"""`pacto_antenupcial_service.aplicar_leitura` — the couple's regime de bens
off a pacto antenupcial, through `extrair_identidade`'s dispatch.

WHAT THESE PIN
--------------
1. Both spouses the pacto names get `regime_bens` on THEIR OWN record
   (matched by CPF / by the uploading card's name), origem
   `pacto_antenupcial`.
2. An existing DIFFERENT regime is never overwritten — a conflict opens.
3. The escritura's own facts ride on `extracao_pacto_antenupcial` with the
   field names the contract generator reads.
4. Unmatched spouses are recorded (`cliente_id_aplicado: None`), never
   created.

All identifiers are synthetic (checksum-valid documentation CPFs). The
extractor is injected (`FakePactoAntenupcialExtractor(result=...)`), never
monkeypatched.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import identidade_extracao_service as svc
from app.modules.card_hub.proveniencia import fontes
from noctusai_lib.integrations.documents.pacto_antenupcial import (
    ConjugePacto,
    FakePactoAntenupcialExtractor,
    PactoAntenupcialLido,
    RegistroPacto,
)
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.matriculas.conftest import FakeNotificationService

BUCKET = "social-wiring-documentos"
ORG_UUID = UUID(ORG_ID)
CPF_A = "41295423898"
CPF_B = "52998224725"
CPF_ESTRANHO = "11144477735"


def _lida(**over) -> PactoAntenupcialLido:
    base = dict(
        regime_bens="separacao_total",
        regime_bens_confianca=ExtractionConfidence.MEDIA,
        data_escritura=date(2019, 1, 10),
        tabelionato="7º Tabelião de Notas desta Capital",
        livro="1234",
        folhas="056",
        registro=RegistroPacto(numero="4.321", livro="3 - Registro Auxiliar",
                               cartorio="1º Oficial de Registro de Imóveis",
                               data=date(2019, 3, 15)),
        data_casamento=date(2019, 2, 2),
        conjuges=(ConjugePacto(nome="ANA EXEMPLO", cpf=CPF_A),
                  ConjugePacto(nome="BRUNO EXEMPLO", cpf=CPF_B)),
        source=TextSource.OCR,
    )
    base.update(over)
    return PactoAntenupcialLido(**base)


async def _setup(scoped, *, titular=None, conjuge=None):
    cid, conj_id, did = str(uuid4()), str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [
        cliente_row(cid, **({"nome": "Ana Exemplo", "cpf": CPF_A} | (titular or {}))),
        cliente_row(conj_id, **({"nome": "Bruno Exemplo", "cpf": CPF_B} | (conjuge or {}))),
    ])
    atd = str(uuid4())
    scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
    scoped.set_table_data("atendimento_partes", [
        {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
         "cliente_id": conj_id, "papel": "conjuge", "ordem": 0},
    ])
    path = f"{ORG_ID}/clientes/{cid}/{did}"
    scoped.set_table_data("cliente_documentos", [{
        "id": did, "org_id": ORG_ID, "cliente_id": cid,
        "storage_path": path, "nome_original": "pacto.pdf",
        "mime_type": "application/pdf", "tipo_documento": "pacto_antenupcial",
        "deleted_at": None, "extracao_status": "pendente",
        "extracao_tentativas": 0, "created_at": "2026-01-01T00:00:00+00:00",
    }])
    scoped.set_table_data("cliente_documento_acessos", [])
    scoped.set_table_data("cliente_campo_conflitos", [])
    storage = FakeStorageBackend()
    await storage.put(bucket=BUCKET, key=path, data=b"%PDF-1.4", content_type="application/pdf")
    return cid, conj_id, did, storage


def _row(scoped, table, rid) -> dict:
    return next(r for r in scoped.table(table).select("*").execute().data if r["id"] == rid)


async def _extrair(scoped, storage, cid, did, lida, notifier=None):
    return await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=FakePactoAntenupcialExtractor(result=lida),
        notification_service=notifier,
    )


class TestRegimeDoCasal:
    @pytest.mark.asyncio
    async def test_os_dois_conjuges_recebem_o_regime(self, client, scoped):
        cid, conj_id, did, storage = await _setup(scoped)
        out = await _extrair(scoped, storage, cid, did, _lida())
        assert out["status"] == "ok"
        for rid in (cid, conj_id):
            row = _row(scoped, "clientes", rid)
            assert row["regime_bens"] == "separacao_total"
            assert row["regime_bens_origem"] == "pacto_antenupcial"

    @pytest.mark.asyncio
    async def test_regime_diferente_ja_gravado_vira_conflito_nunca_sobrescreve(
        self, client, scoped
    ):
        cid, conj_id, did, storage = await _setup(
            scoped,
            titular={"regime_bens": "comunhao_parcial",
                     "regime_bens_origem": "certidao_casamento"},
        )
        await _extrair(scoped, storage, cid, did, _lida(), FakeNotificationService())
        assert _row(scoped, "clientes", cid)["regime_bens"] == "comunhao_parcial"
        conflitos = scoped.table("cliente_campo_conflitos").select("*").execute().data
        assert [c["campo"] for c in conflitos] == ["regime_bens"]
        assert _row(scoped, "clientes", conj_id)["regime_bens"] == "separacao_total"

    @pytest.mark.asyncio
    async def test_fatos_da_escritura_ficam_no_documento(self, client, scoped):
        cid, conj_id, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, _lida())
        lido = _row(scoped, "cliente_documentos", did)["extracao_pacto_antenupcial"]
        assert lido["regime_bens"] == "separacao_total"
        assert (lido["data_escritura"], lido["tabelionato"], lido["livro"], lido["folhas"]) == (
            "2019-01-10", "7º Tabelião de Notas desta Capital", "1234", "056",
        )
        assert lido["registro"] == {
            "numero": "4.321", "livro": "3 - Registro Auxiliar",
            "cartorio": "1º Oficial de Registro de Imóveis", "data": "2019-03-15",
        }
        assert lido["data_casamento"] == "2019-02-02"
        assert [c["cliente_id_aplicado"] for c in lido["conjuges"]] == [cid, conj_id]

    @pytest.mark.asyncio
    async def test_conjuge_desconhecido_e_registrado_nunca_criado(self, client, scoped):
        cid, conj_id, did, storage = await _setup(scoped)
        antes = len(scoped.table("clientes").select("*").execute().data)
        lida = _lida(conjuges=(ConjugePacto(nome="ANA EXEMPLO", cpf=CPF_A),
                               ConjugePacto(nome="CARLOS ESTRANHO", cpf=CPF_ESTRANHO)))
        await _extrair(scoped, storage, cid, did, lida)
        assert len(scoped.table("clientes").select("*").execute().data) == antes
        lido = _row(scoped, "cliente_documentos", did)["extracao_pacto_antenupcial"]
        assert [c["cliente_id_aplicado"] for c in lido["conjuges"]] == [cid, None]
        assert _row(scoped, "clientes", conj_id).get("regime_bens") in (None, "")

    @pytest.mark.asyncio
    async def test_leitura_vazia_e_sem_dados(self, client, scoped):
        cid, _conj, did, storage = await _setup(scoped)
        out = await _extrair(scoped, storage, cid, did, PactoAntenupcialLido())
        assert out["status"] == "sem_dados"


class TestCitacaoDaEscritura:
    """Migration 193 — the escritura's citation (data, tabelionato, livro,
    folha) lands on BOTH spouses' `clientes.pacto_antenupcial_*` through the
    same D1 path: fill empty machine-pending, conflict on a different value,
    never overwrite. The contract generator prints it from there."""

    @pytest.mark.asyncio
    async def test_os_dois_conjuges_recebem_a_citacao_pendente_de_confirmacao(self, client, scoped):
        cid, conj_id, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, _lida())
        for rid in (cid, conj_id):
            row = _row(scoped, "clientes", rid)
            assert (
                str(row["pacto_antenupcial_data"])[:10], row["pacto_antenupcial_tabelionato"],
                row["pacto_antenupcial_livro"], row["pacto_antenupcial_folha"],
            ) == ("2019-01-10", "7º Tabelião de Notas desta Capital", "1234", "056")
            assert row["pacto_antenupcial_livro_origem"] == "pacto_antenupcial"
            assert row["pacto_antenupcial_livro_documento_id"] == did
            assert row.get("pacto_antenupcial_livro_confirmado_em") is None

    @pytest.mark.asyncio
    async def test_livro_diferente_ja_gravado_vira_conflito_nunca_sobrescreve(self, client, scoped):
        cid, conj_id, did, storage = await _setup(
            scoped,
            titular={"pacto_antenupcial_livro": "999", "pacto_antenupcial_livro_origem": "manual"},
        )
        await _extrair(scoped, storage, cid, did, _lida(), FakeNotificationService())
        assert _row(scoped, "clientes", cid)["pacto_antenupcial_livro"] == "999"
        campos = [c["campo"] for c in scoped.table("cliente_campo_conflitos").select("*").execute().data]
        assert campos == ["pacto_antenupcial_livro"]
        assert _row(scoped, "clientes", conj_id)["pacto_antenupcial_livro"] == "1234"

    @pytest.mark.asyncio
    async def test_citacao_sem_regime_ainda_e_gravada(self, client, scoped):
        cid, _conj, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, _lida(regime_bens=None,
                       regime_bens_confianca=ExtractionConfidence.NENHUMA))
        row = _row(scoped, "clientes", cid)
        assert row["pacto_antenupcial_folha"] == "056"
        assert row.get("regime_bens") in (None, "")

    def test_um_conflito_de_pacto_e_decidivel_pelo_admin(self):
        # `resolver_conflito` is generic over CAMPO_POR_CHAVE.
        for parte in ("data", "tabelionato", "livro", "folha"):
            assert f"pacto_antenupcial_{parte}" in svc.CAMPO_POR_CHAVE

    @pytest.mark.asyncio
    async def test_o_contrato_le_a_citacao_gravada(self, client, scoped):
        from app.modules.card_hub.contrato_gerador.carregador import _pacto

        cid, _conj, did, storage = await _setup(scoped)
        await _extrair(scoped, storage, cid, did, _lida())
        pacto = _pacto(_row(scoped, "clientes", cid))
        assert pacto is not None
        assert (pacto.data, pacto.livro, pacto.folha) == (date(2019, 1, 10), "1234", "056")


def test_tipo_registrado_no_catalogo_de_fontes():
    fonte = fontes.FONTES["pacto_antenupcial"]
    assert fonte.dominio == "cliente" and fonte.campos == frozenset({
        "regime_bens", "pacto_antenupcial_data", "pacto_antenupcial_tabelionato",
        "pacto_antenupcial_livro", "pacto_antenupcial_folha",
    })
    assert svc.deve_extrair("pacto_antenupcial")
