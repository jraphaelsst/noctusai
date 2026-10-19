"""The CEP restores a bairro the document printed truncated (deal 876).

The buyers' bank form (ficha cadastral) carries `ALPHAVILLE RESIDENCIAL` in
its AcroForm bairro field — cut off by the field — while CEP 06470-000 and
the signed contract both name `Alphaville Residencial Dois`. The shapes below
are that ficha's address as `ficha_cadastral_service` hands it to
`aplicar_endereco_ao_cliente` (`EnderecoLido.partes()`), with the address
itself replaced by a fixture.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from noctusai_lib.integrations.cep import CepEndereco, FakeCepLookupAdapter

from app.modules.card_hub import identidade_extracao_service as svc
from tests.modules.card_hub.conftest import cliente_row
from tests.modules.card_hub.test_identidade_d1_contrato import ORG_UUID, _cliente, _conflitos

CEP = "06470-000"


def _cep(bairro="Alphaville Residencial Dois") -> FakeCepLookupAdapter:
    return FakeCepLookupAdapter({
        CEP: CepEndereco(
            cep=CEP, cidade="Barueri", uf="SP", logradouro="Alameda Brasil", bairro=bairro,
        ),
    })


def _ficha(bairro="ALPHAVILLE RESIDENCIAL") -> dict:
    return {
        "cep": CEP, "logradouro": "AL BRASIL", "numero": "157", "complemento": None,
        "bairro": bairro, "cidade": "BARUERI", "uf": "SP",
    }


def _casal(scoped, *, comprador_extra=None) -> tuple[str, str]:
    """The buyer holds the ficha's (truncated) address; his wife inherited it
    (`conjuge_domicilio`) — the prod state before the fix."""
    fn, ci, ficha_doc = str(uuid4()), str(uuid4()), str(uuid4())
    endereco = {
        "endereco_cep": CEP, "endereco_logradouro": "AL BRASIL", "endereco_numero": "157",
        "endereco_complemento": None, "endereco_bairro": "ALPHAVILLE RESIDENCIAL",
        "endereco_cidade": "Barueri", "endereco_uf": "SP",
        "endereco_documento_id": ficha_doc,
    }
    scoped.set_table_data("clientes", [
        cliente_row(fn, nome="Fulano Comprador", conjuge_cliente_id=ci,
                    **{**endereco, "endereco_origem": "ficha_cadastral",
                       **(comprador_extra or {})}),
        cliente_row(ci, nome="Fulana Compradora", conjuge_cliente_id=fn,
                    endereco_origem=svc.ORIGEM_CONJUGE_DOMICILIO, **endereco),
    ])
    scoped.set_table_data("cliente_campo_conflitos", [])
    return fn, ci


class TestBairroCompletadoPeloCep:
    def test_a_fresh_ficha_address_is_written_with_the_restored_bairro(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Fulano Comprador")])
        scoped.set_table_data("cliente_campo_conflitos", [])

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "ficha_cadastral", _ficha(),
            documento_id=uuid4(), cep_lookup=_cep(),
        )

        row = _cliente(scoped, cid)
        assert aplicado and conflito is None
        assert row["endereco_bairro"] == "Alphaville Residencial Dois"
        assert row["endereco_bairro_origem"] == "cep"
        assert row["endereco_origem"] == "ficha_cadastral"

    def test_a_re_read_completes_the_stored_bairro_and_the_spouse_follows(self, client, scoped):
        fn, ci = _casal(scoped)
        doc_original = _cliente(scoped, fn)["endereco_documento_id"]

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(fn), "ficha_cadastral", _ficha(),
            documento_id=UUID(doc_original), cep_lookup=_cep(),
        )
        svc.propagar_endereco_domicilio(scoped, ORG_UUID, UUID(fn))

        comprador, conjuge = _cliente(scoped, fn), _cliente(scoped, ci)
        assert aplicado and conflito is None
        assert comprador["endereco_bairro"] == "Alphaville Residencial Dois"
        assert comprador["endereco_bairro_origem"] == "cep"
        # Only the bairro moved — the group's own source is untouched.
        assert comprador["endereco_origem"] == "ficha_cadastral"
        assert comprador["endereco_documento_id"] == doc_original
        assert conjuge["endereco_bairro"] == "Alphaville Residencial Dois"
        assert conjuge["endereco_origem"] == svc.ORIGEM_CONJUGE_DOMICILIO
        assert [c for c in _conflitos(scoped) if c["status"] == "pendente"] == []

    def test_a_cep_bairro_that_replaces_a_printed_word_is_never_applied(self, client, scoped):
        """`ALPHAVILLE RESIDENCIAL` vs CEP `Alphaville Comercial` — a
        disagreement, not a completion: the printed bairro stays."""
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Fulano Comprador")])
        scoped.set_table_data("cliente_campo_conflitos", [])

        svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "ficha_cadastral", _ficha(),
            documento_id=uuid4(), cep_lookup=_cep("Alphaville Comercial"),
        )

        row = _cliente(scoped, cid)
        assert row["endereco_bairro"] == "ALPHAVILLE RESIDENCIAL"
        assert row.get("endereco_bairro_origem") is None

    def test_a_single_printed_word_is_too_little_evidence_to_extend(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Fulano Comprador")])
        scoped.set_table_data("cliente_campo_conflitos", [])

        svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "ficha_cadastral", _ficha("ALPHAVILLE"),
            documento_id=uuid4(), cep_lookup=_cep(),
        )

        assert _cliente(scoped, cid)["endereco_bairro"] == "ALPHAVILLE"

    def test_a_human_confirmed_bairro_is_never_completed(self, client, scoped):
        fn, _ci = _casal(scoped, comprador_extra={
            "endereco_confirmado_por": str(uuid4()),
            "endereco_confirmado_em": "2026-10-15T00:00:00+00:00",
        })

        svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(fn), "ficha_cadastral", _ficha(),
            documento_id=uuid4(), cep_lookup=_cep(),
        )

        assert _cliente(scoped, fn)["endereco_bairro"] == "ALPHAVILLE RESIDENCIAL"

    def test_a_typed_address_is_never_completed(self, client, scoped):
        fn, _ci = _casal(scoped, comprador_extra={"endereco_origem": "manual"})

        svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(fn), "ficha_cadastral", _ficha(),
            documento_id=uuid4(), cep_lookup=_cep(),
        )

        assert _cliente(scoped, fn)["endereco_bairro"] == "ALPHAVILLE RESIDENCIAL"
