"""`ficha_cadastral_service.aplicar_leitura` — the whole apply sequence for
a bank registration form naming several people.

WHAT THESE PIN
--------------
1. **Multi-person CPF attribution.** Every person the form names is matched
   to a party of the SAME atendimento by CPF (exact digits) and applied to
   THEIR OWN `clientes` row — never the uploading card's alone.
2. **Unmatched persons are ignored.** A CPF that matches nobody on this
   atendimento never creates a client and never writes anywhere.
3. **Tier ordering for address**: a household-propagated address
   (`conjuge_domicilio`, the weakest tier) is overwritten outright; a REAL
   address already on file (a comprovante) is never silently overwritten —
   a genuine disagreement opens a conflict instead.
4. **Identity fields are corroboration-only** — an empty `clientes.cpf`/
   `nome_oficial`/etc fills from the ficha exactly like any other source
   (D1), but a value already SET from a real identity document is never
   beaten (unmeasured `PRECISAO` — see `divergencia_resolucao.py`).

`extractor` is injected via `FakeFichaCadastralExtractor(result=...)`
(`tests/support/document_fakes.py`), per DI — never a monkeypatch.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import ficha_cadastral_service as ficha_svc
from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.matriculas.conftest import FakeNotificationService
from tests.support.document_fakes import (
    ALTA,
    BAIXA,
    FakeFichaCadastralExtractor,
    FichaCadastralLida,
    PessoaFichaCadastral,
)
from noctusai_lib.integrations.documents.address import EnderecoLido
from noctusai_lib.integrations.documents.types import TextSource

BUCKET = "social-wiring-documentos"
ORG_UUID = UUID(ORG_ID)

CPF_PROPONENTE = "412.954.238-98"
CPF_CONJUGE = "529.982.247-25"
CPF_TERCEIRO = "111.444.777-35"  # matches nobody on the atendimento


def _endereco(**over) -> EnderecoLido:
    base = dict(
        cep="01234-567", logradouro="Rua das Flores", numero="100",
        complemento=None, bairro="Centro", cidade="São Paulo", uf="SP",
        confianca="alta", rotulo="FICHA CADASTRAL",
    )
    base.update(over)
    return EnderecoLido(**base)


def _pessoa(**over) -> PessoaFichaCadastral:
    base = dict(
        # `"Ana"` matches `cliente_row`'s own default `nome` — the name-
        # fallback (`_resolver_destino`) needs the two to agree unless a
        # test overrides both together.
        papel="proponente", nome="Ana", nome_confianca=ALTA,
        cpf=CPF_PROPONENTE, cpf_confianca=ALTA,
        profissao="engenheiro", profissao_confianca=ALTA,
    )
    base.update(over)
    return PessoaFichaCadastral(**base)


async def _setup(scoped, *, cliente=None, outros=()):
    cid, did = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, **(cliente or {})), *outros])
    path = f"{ORG_ID}/clientes/{cid}/{did}"
    scoped.set_table_data("cliente_documentos", [{
        "id": did, "org_id": ORG_ID, "cliente_id": cid,
        "storage_path": path, "nome_original": "ficha.pdf",
        "mime_type": "application/pdf", "tipo_documento": "ficha_cadastral",
        "deleted_at": None, "extracao_status": "pendente",
        "extracao_tentativas": 0, "created_at": "2026-01-01T00:00:00+00:00",
    }])
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


async def _extrair(scoped, storage, cid, did, lida, notifier=None):
    return await svc.extrair_identidade(
        scoped, storage, ORG_UUID, UUID(cid), UUID(did),
        extractor=FakeFichaCadastralExtractor(result=lida),
        notification_service=notifier,
    )


class TestMultiPersonCpfAttribution:
    @pytest.mark.asyncio
    async def test_titular_and_spouse_each_apply_to_their_own_card(self, client, scoped):
        """The titular has NO cpf on file yet (matched by NAME — the
        fallback this feature exists for). The cônjuge's identity was
        already established by an earlier RG (matched by CPF — the
        brief's own primary rule); the ficha only corroborates it and
        fills their still-empty `profissao`."""
        conjuge_id = str(uuid4())
        cid, did, storage = await _setup(
            scoped,
            cliente={"nome": "Fulano", "cpf": None},
            outros=[cliente_row(conjuge_id, nome="Ciclana", cpf=CPF_CONJUGE, profissao=None)],
        )
        atd = str(uuid4())
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": conjuge_id, "papel": "conjuge", "ordem": 0},
        ])
        lida = FichaCadastralLida(
            pessoas=(
                _pessoa(papel="proponente", nome="FULANO", cpf=CPF_PROPONENTE),
                _pessoa(papel="conjuge", nome="CICLANA", cpf=CPF_CONJUGE, profissao="médica"),
            ),
            source=TextSource.TEXT_LAYER,
        )
        out = await _extrair(scoped, storage, cid, did, lida)
        assert out["status"] != "erro"

        titular = _cliente(scoped, cid)
        assert titular["cpf"] == CPF_PROPONENTE
        assert titular["cpf_origem"] == "ficha_cadastral"
        assert titular["profissao"] == "engenheiro"

        conjuge = _cliente(scoped, conjuge_id)
        assert conjuge["cpf"] == CPF_CONJUGE  # unchanged — same fact, no-op
        assert conjuge["profissao"] == "médica"
        assert conjuge["profissao_origem"] == "ficha_cadastral"

    @pytest.mark.asyncio
    async def test_unmatched_person_is_ignored_never_creates_a_client(self, client, scoped):
        cid, did, storage = await _setup(scoped, cliente={"cpf": None})
        antes = len(scoped.table("clientes").select("*").execute().data)
        lida = FichaCadastralLida(
            # Neither this CPF nor this name matches the uploading card (or
            # anyone else on its atendimento) — a misfiled/unrelated form.
            pessoas=(_pessoa(nome="TERCEIRO ESTRANHO", cpf=CPF_TERCEIRO),),
            source=TextSource.TEXT_LAYER,
        )
        out = await _extrair(scoped, storage, cid, did, lida)
        assert out["status"] != "erro"
        depois = scoped.table("clientes").select("*").execute().data
        assert len(depois) == antes
        assert _cliente(scoped, cid)["cpf"] is None

    @pytest.mark.asyncio
    async def test_no_people_is_sem_dados_not_an_error(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        out = await _extrair(scoped, storage, cid, did, FichaCadastralLida(pessoas=()))
        assert out["status"] == "sem_dados"
        doc = _documento(scoped, did)
        assert doc["extracao_ficha_cadastral"]["pessoas"] == []


class TestIdentityFieldsAreCorroborationOnly:
    @pytest.mark.asyncio
    async def test_an_empty_field_fills_from_the_ficha(self, client, scoped):
        cid, did, storage = await _setup(scoped, cliente={"cpf": None, "profissao": None})
        lida = FichaCadastralLida(pessoas=(_pessoa(),), source=TextSource.TEXT_LAYER)
        await _extrair(scoped, storage, cid, did, lida)
        row = _cliente(scoped, cid)
        assert row["cpf"] == CPF_PROPONENTE
        assert row["profissao"] == "engenheiro"

    @pytest.mark.asyncio
    async def test_a_value_already_set_by_an_identity_document_is_never_beaten(
        self, client, scoped
    ):
        """`divergencia_resolucao.PRECISAO` carries no `ficha_cadastral`
        cell — an unmeasured source can never win a tier fight, only open
        a conflict a human resolves."""
        cid, did, storage = await _setup(
            scoped, cliente={"profissao": "advogado", "profissao_origem": "cnh"},
        )
        notifier = FakeNotificationService()
        lida = FichaCadastralLida(
            pessoas=(_pessoa(profissao="corretor de imóveis"),), source=TextSource.TEXT_LAYER,
        )
        await _extrair(scoped, storage, cid, did, lida, notifier)
        assert _cliente(scoped, cid)["profissao"] == "advogado"
        assert [c["campo"] for c in _conflitos(scoped)] == ["profissao"]


class TestEnderecoTier:
    @pytest.mark.asyncio
    async def test_overwrites_a_household_propagated_address_outright(self, client, scoped):
        cid, did, storage = await _setup(
            scoped,
            cliente={
                "endereco_cep": "09999-999", "endereco_logradouro": "Rua Antiga",
                "endereco_numero": "1", "endereco_bairro": "Bairro Antigo",
                "endereco_cidade": "Cotia", "endereco_uf": "SP",
                "endereco_origem": "conjuge_domicilio",
            },
        )
        lida = FichaCadastralLida(
            pessoas=(_pessoa(endereco=_endereco()),), source=TextSource.TEXT_LAYER,
        )
        await _extrair(scoped, storage, cid, did, lida)
        row = _cliente(scoped, cid)
        assert row["endereco_cep"] == "01234-567"
        assert row["endereco_origem"] == "ficha_cadastral"

    @pytest.mark.asyncio
    async def test_never_silently_overwrites_a_real_documents_address(self, client, scoped):
        cid, did, storage = await _setup(
            scoped,
            cliente={
                "endereco_cep": "09999-999", "endereco_logradouro": "Rua do Comprovante",
                "endereco_numero": "1", "endereco_bairro": "Bairro Real",
                "endereco_cidade": "Cotia", "endereco_uf": "SP",
                "endereco_origem": "comprovante_endereco",
            },
        )
        notifier = FakeNotificationService()
        lida = FichaCadastralLida(
            pessoas=(_pessoa(endereco=_endereco()),), source=TextSource.TEXT_LAYER,
        )
        await _extrair(scoped, storage, cid, did, lida, notifier)
        row = _cliente(scoped, cid)
        # Untouched — a genuine disagreement opens a conflict, never a
        # silent overwrite (no measured tier makes ficha_cadastral outrank
        # the party's own comprovante).
        assert row["endereco_cep"] == "09999-999"
        assert row["endereco_origem"] == "comprovante_endereco"

    @pytest.mark.asyncio
    async def test_fills_an_empty_address(self, client, scoped):
        cid, did, storage = await _setup(scoped)
        lida = FichaCadastralLida(
            pessoas=(_pessoa(endereco=_endereco()),), source=TextSource.TEXT_LAYER,
        )
        await _extrair(scoped, storage, cid, did, lida)
        row = _cliente(scoped, cid)
        assert row["endereco_cep"] == "01234-567"
        assert row["endereco_origem"] == "ficha_cadastral"


class TestFichaLidaAntesDaIdentidade:
    """A bank form read BEFORE the other party's identity document stores
    that person unmatched; when their CPF lands the STORED reading is applied
    to them — zero model calls (it used to re-queue the whole form for a paid
    vision re-read, once per party whose CPF arrived later)."""

    async def _ficha_com_terceiro_nao_casado(self, scoped):
        outro_id = str(uuid4())
        cid, did, storage = await _setup(
            scoped, cliente={"nome": "Fulano", "cpf": None},
            outros=[cliente_row(outro_id, nome="Beltrano", cpf=None, profissao=None)],
        )
        atd = str(uuid4())
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": outro_id, "papel": "comprador", "ordem": 0},
        ])
        lida = FichaCadastralLida(
            pessoas=(
                _pessoa(papel="proponente", nome="FULANO", cpf=CPF_PROPONENTE),
                # Name differs from the registry and no CPF on file: unmatched.
                _pessoa(papel="conjuge", nome="B. DA SILVA", cpf=CPF_CONJUGE,
                        profissao="médico", endereco=_endereco()),
            ),
            source=TextSource.TEXT_LAYER,
        )
        await _extrair(scoped, storage, cid, did, lida)
        pessoas = _documento(scoped, did)["extracao_ficha_cadastral"]["pessoas"]
        assert pessoas[1]["cliente_id_aplicado"] is None
        return cid, did, outro_id, storage, lida

    @staticmethod
    def _gravar_cpf(scoped, pessoa_id, cpf):
        return svc.aplicar_campos_ao_cliente(
            scoped, ORG_UUID, UUID(pessoa_id), "rg",
            {"cpf": (cpf, "alta", "RG", True)},
            campos=(svc.CAMPO_POR_CHAVE["cpf"],), documento_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_cpf_arriving_later_applies_the_stored_reading_without_a_reread(
        self, client, scoped,
    ):
        cid, did, outro_id, storage, lida = await self._ficha_com_terceiro_nao_casado(scoped)

        self._gravar_cpf(scoped, outro_id, CPF_CONJUGE)

        # No paid re-read queued: the document stays terminal-ok…
        doc = _documento(scoped, did)
        assert doc["extracao_status"] != "pendente"
        # …and the person was attributed + applied from the STORED JSON.
        pessoas = doc["extracao_ficha_cadastral"]["pessoas"]
        assert pessoas[1]["cliente_id_aplicado"] == outro_id
        outro = _cliente(scoped, outro_id)
        assert outro["profissao"] == "médico"
        assert outro["profissao_origem"] == "ficha_cadastral"
        assert outro["endereco_cep"] == "01234-567"

    @pytest.mark.asyncio
    async def test_the_cpf_matches_in_any_spelling(self, client, scoped):
        _cid, did, outro_id, _storage, _lida = await self._ficha_com_terceiro_nao_casado(scoped)
        # The ficha stored `529.982.247-25`; the identity document read it bare.
        self._gravar_cpf(scoped, outro_id, "52998224725")
        assert _documento(scoped, did)["extracao_ficha_cadastral"]["pessoas"][1][
            "cliente_id_aplicado"
        ] == outro_id

    @pytest.mark.asyncio
    async def test_cpf_matching_nobody_applies_nothing(self, client, scoped):
        _cid, did, outro_id, _storage, _lida = await self._ficha_com_terceiro_nao_casado(scoped)
        self._gravar_cpf(scoped, outro_id, CPF_TERCEIRO)
        doc = _documento(scoped, did)
        assert doc["extracao_status"] != "pendente"
        assert doc["extracao_ficha_cadastral"]["pessoas"][1]["cliente_id_aplicado"] is None
        assert _cliente(scoped, outro_id)["profissao"] is None

    @pytest.mark.asyncio
    async def test_applying_twice_is_idempotent_and_never_loops(self, client, scoped):
        _cid, did, outro_id, _storage, _lida = await self._ficha_com_terceiro_nao_casado(scoped)
        self._gravar_cpf(scoped, outro_id, CPF_CONJUGE)
        primeiro = _cliente(scoped, outro_id)["profissao_em"]
        resultado = ficha_svc.reaplicar_fichas_pelo_cpf(
            scoped, ORG_UUID, UUID(outro_id), CPF_CONJUGE,
        )
        assert resultado["pessoas"] == 0 and resultado["documentos"] == []
        assert _cliente(scoped, outro_id)["profissao_em"] == primeiro
        assert _documento(scoped, did)["extracao_status"] != "pendente"


class TestNomeUnicoOutraParte:
    """Live 2026-10-01 (deal 871): a party whose ONLY CPF source is the bank
    form itself could never be matched by CPF. A UNIQUE strict name match
    against the other parties of the same atendimento now applies it; two
    compatible parties stay unmatched (ambiguous)."""

    async def _cenario(self, scoped, outros_nomes):
        ids = [str(uuid4()) for _ in outros_nomes]
        cid, did, storage = await _setup(
            scoped, cliente={"nome": "Fulano", "cpf": None},
            outros=[cliente_row(i, nome=n, nome_oficial=n, cpf=None, profissao=None)
                    for i, n in zip(ids, outros_nomes)],
        )
        atd = str(uuid4())
        scoped.set_table_data("atendimentos", [{"id": atd, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data("atendimento_partes", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atd,
             "cliente_id": i, "papel": "comprador", "ordem": k}
            for k, i in enumerate(ids)
        ])
        lida = FichaCadastralLida(
            pessoas=(
                _pessoa(papel="proponente", nome="FULANO", cpf=CPF_PROPONENTE),
                _pessoa(papel="conjuge", nome="BELTRANA MARIA DA SILVA", cpf=CPF_CONJUGE,
                        profissao="médica"),
            ),
            source=TextSource.TEXT_LAYER,
        )
        await _extrair(scoped, storage, cid, did, lida)
        return did, ids

    @pytest.mark.asyncio
    async def test_unique_name_match_applies(self, client, scoped):
        did, (outro,) = await self._cenario(scoped, ["Beltrana Maria da Silva"])
        pessoas = _documento(scoped, did)["extracao_ficha_cadastral"]["pessoas"]
        assert pessoas[1]["cliente_id_aplicado"] == outro
        assert _cliente(scoped, outro)["profissao"] == "médica"

    @pytest.mark.asyncio
    async def test_ambiguous_name_stays_unmatched(self, client, scoped):
        did, _ = await self._cenario(
            scoped, ["Beltrana Maria da Silva", "Beltrana Maria da Silva"],
        )
        pessoas = _documento(scoped, did)["extracao_ficha_cadastral"]["pessoas"]
        assert pessoas[1]["cliente_id_aplicado"] is None

