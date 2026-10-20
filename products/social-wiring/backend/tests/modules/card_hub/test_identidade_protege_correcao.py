"""A re-read never overwrites an OWNER CORRECTION (owner order 2026-10-20).

Prod deal 876: the owner corrected the seller's profissão "aposentanda" (a
typo printed on the ficha cadastral itself) to "aposentada"; a later re-read
of that SAME ficha put the typo back with no conflict row, and the contract
gate then refused the deal. The rule (`identidade_extracao_service.
correcao_do_dono`): a value a person typed (`origem='manual'`, not an
unchanged form re-save) is never replaced by a reading — a disagreeing
reading opens a `pendente` conflict flagged `protege_correcao` (migration
291). Approve -> the document's value, with its document provenance; reject
-> the owner's stays and the same proposal is never raised again.

Every state below is built through the app's own write paths
(`clientes_service.update_cliente`, `aplicar_campos_ao_cliente`,
`resolver_conflito`) — a hand-seeded `manual` would prove nothing about
whether a UI edit is recognisable as a correction.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub import identidade_extracao_service as svc
from app.services import clientes_service
from tests.modules.card_hub.conftest import cliente_row
from tests.modules.card_hub.test_identidade_d1_contrato import ORG_ID, ORG_UUID, _cliente, _conflitos

DONO = uuid4()
FICHA = uuid4()
TIPICO = "APOSENTANDA"  # what the ficha prints
CORRIGIDO = "aposentada"  # what the owner typed


def _lidos(confianca: str = "media", rotulo: str = "PROFISSÃO", **campos):
    base = svc._lidos_vazios()
    base.update({k: (v, confianca, rotulo, True) for k, v in campos.items()})
    return base


def _ler_ficha(scoped, cid, documento_id=FICHA, **kw):
    """The ficha cadastral, as `ficha_cadastral_service` applies a person's
    reading (same origem, same document provenance)."""
    lidos = kw.pop("lidos", None) or _lidos(profissao=TIPICO)
    return svc.aplicar_campos_ao_cliente(
        scoped, ORG_UUID, UUID(cid), "ficha_cadastral", lidos,
        documento_id=documento_id, fonte_tabela=svc.DOCUMENTOS_TABLE,
        fonte_id=documento_id, **kw,
    )


def _cilene_lida_da_ficha(scoped) -> str:
    """The seller after the FIRST ficha read: the typo, machine-pending."""
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Cilene Teste")])
    scoped.set_table_data("cliente_campo_conflitos", [])
    _ler_ficha(scoped, cid)
    row = _cliente(scoped, cid)
    assert (row["profissao"], row["profissao_origem"]) == (TIPICO, "ficha_cadastral")
    return cid


def _dono_corrige(scoped, cid, **campos):
    """The owner's edit through the form's own PATCH path."""
    return clientes_service.update_cliente(
        scoped, ORG_UUID, UUID(cid), acting_user_id=DONO, is_admin=True, **campos
    )


def _corrigida(scoped) -> str:
    cid = _cilene_lida_da_ficha(scoped)
    _dono_corrige(scoped, cid, profissao=CORRIGIDO)
    return cid


def _pendentes(scoped) -> list[dict]:
    return [c for c in _conflitos(scoped) if c["status"] == "pendente"]


class TestUiEditIsACorrection:
    def test_an_owner_edit_is_recognised_as_a_correction(self, client, scoped):
        cid = _corrigida(scoped)
        row = _cliente(scoped, cid)
        assert (row["profissao"], row["profissao_origem"]) == (CORRIGIDO, "manual")
        assert svc.correcao_do_dono(
            scoped, ORG_UUID, UUID(cid), "profissao",
            origem_atual=row["profissao_origem"],
            confirmado_em_atual=row.get("profissao_confirmado_em"),
            presente=row["profissao"],
        ) is True

    def test_an_unchanged_save_is_not_a_correction(self, client, scoped):
        cid = _cilene_lida_da_ficha(scoped)
        _dono_corrige(scoped, cid, profissao=TIPICO)  # saved as-is
        row = _cliente(scoped, cid)
        assert row["profissao_origem"] == "ficha_cadastral"
        assert not svc.correcao_do_dono(
            scoped, ORG_UUID, UUID(cid), "profissao",
            origem_atual=row["profissao_origem"],
            confirmado_em_atual=None, presente=row["profissao"],
        )


class TestRereadMeetsACorrection:
    def test_the_same_ficha_reread_opens_a_protection_conflict_value_unchanged(self, client, scoped):
        cid = _corrigida(scoped)

        _, abertos = _ler_ficha(scoped, cid)

        row = _cliente(scoped, cid)
        assert (row["profissao"], row["profissao_origem"]) == (CORRIGIDO, "manual")
        [conflito] = _pendentes(scoped)
        assert abertos == [conflito]
        assert conflito["campo"] == "profissao"
        assert conflito["protege_correcao"] is True
        assert (conflito["valor_anterior"], conflito["origem_anterior"]) == (CORRIGIDO, "manual")
        assert (conflito["valor_proposto"], conflito["origem_proposto"]) == (TIPICO, "ficha_cadastral")
        assert (conflito["fonte_tabela"], conflito["fonte_id"]) == (svc.DOCUMENTOS_TABLE, str(FICHA))

    def test_another_document_disagreeing_is_protected_too(self, client, scoped):
        cid = _corrigida(scoped)
        svc.aplicar_campos_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "certidao_casamento",
            _lidos(confianca="alta", profissao="do lar"), documento_id=uuid4(),
        )
        assert _cliente(scoped, cid)["profissao"] == CORRIGIDO
        [conflito] = _pendentes(scoped)
        assert conflito["protege_correcao"] is True

    def test_a_second_identical_reread_does_not_duplicate_the_warning(self, client, scoped):
        cid = _corrigida(scoped)
        _ler_ficha(scoped, cid)
        _, abertos = _ler_ficha(scoped, cid)
        assert abertos == []
        assert len(_pendentes(scoped)) == 1

    def test_a_reread_stating_the_corrected_value_changes_nothing(self, client, scoped):
        cid = _corrigida(scoped)
        antes = len(_conflitos(scoped))

        _, abertos = _ler_ficha(scoped, cid, lidos=_lidos(profissao="Aposentada"))

        row = _cliente(scoped, cid)
        assert (row["profissao"], row["profissao_origem"]) == (CORRIGIDO, "manual")
        assert abertos == [] and len(_conflitos(scoped)) == antes

    def test_a_low_confidence_reading_does_not_contest_the_correction(self, client, scoped):
        cid = _corrigida(scoped)
        _, abertos = _ler_ficha(scoped, cid, lidos=_lidos(confianca="baixa", profissao=TIPICO))
        assert abertos == [] and _pendentes(scoped) == []
        assert _cliente(scoped, cid)["profissao"] == CORRIGIDO
        [auditoria] = [c for c in _conflitos(scoped) if c["status"] == "resolvido_automatico"]
        assert svc.REGRA_CORRECAO_DO_DONO in auditoria["motivo_resolucao"]

    def test_every_extracted_person_field_is_protected(self, client, scoped):
        """Not a profissão special case: the predicate guards the single
        write chokepoint every person field funnels through."""
        cid = _cilene_lida_da_ficha(scoped)
        _ler_ficha(scoped, cid, lidos=_lidos(nacionalidade="brasileira", estado_civil="solteiro"))
        _dono_corrige(scoped, cid, nacionalidade="portuguesa", estado_civil="casado")

        _ler_ficha(scoped, cid, lidos=_lidos(nacionalidade="brasileira", estado_civil="solteiro"))

        row = _cliente(scoped, cid)
        assert (row["nacionalidade"], row["estado_civil"]) == ("portuguesa", "casado")
        assert {c["campo"] for c in _pendentes(scoped) if c["protege_correcao"]} == {
            "nacionalidade", "estado_civil",
        }


class TestOwnerDecides:
    def _conflito(self, scoped) -> tuple[str, dict]:
        cid = _corrigida(scoped)
        _ler_ficha(scoped, cid)
        [conflito] = _pendentes(scoped)
        return cid, conflito

    def test_approve_applies_the_document_value_with_its_provenance(self, client, scoped):
        cid, conflito = self._conflito(scoped)

        svc.resolver_conflito(scoped, ORG_UUID, UUID(conflito["id"]), aceitar=True, decidido_por=DONO)

        row = _cliente(scoped, cid)
        assert (row["profissao"], row["profissao_origem"]) == (TIPICO, "ficha_cadastral")
        assert row["profissao_documento_id"] == str(FICHA)
        assert row["profissao_confirmado_por"] == str(DONO)

    def test_reject_keeps_the_correction_and_the_reread_never_raises_it_again(self, client, scoped):
        cid, conflito = self._conflito(scoped)

        svc.resolver_conflito(scoped, ORG_UUID, UUID(conflito["id"]), aceitar=False, decidido_por=DONO)
        _, abertos = _ler_ficha(scoped, cid)

        assert abertos == [] and _pendentes(scoped) == []
        assert _cliente(scoped, cid)["profissao"] == CORRIGIDO

    def test_the_resolver_backfill_never_decides_a_protection_conflict(self, client, scoped):
        cid, conflito = self._conflito(scoped)

        resultado = svc.backfill_resolver_conflitos_pendentes(scoped, ORG_UUID)

        assert [r["id"] for r in resultado["ainda_pendentes"]] == [conflito["id"]]
        assert _cliente(scoped, cid)["profissao"] == CORRIGIDO


class TestPhantomManualUnchanged:
    """The 2026-10-19 rule stays: a `manual` left by a form re-saved
    unchanged over a document (the audit trail proves it) is NOT a
    correction — a same-value reading hands the provenance back."""

    def test_a_phantom_manual_is_healed_not_protected(self, client, scoped):
        cid = str(uuid4())
        salvo = "2026-10-12T02:39:32+00:00"
        scoped.set_table_data("clientes", [cliente_row(
            cid, profissao=TIPICO, profissao_origem="manual", profissao_em=salvo,
        )])
        scoped.set_table_data("cliente_campo_conflitos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": "profissao",
            "valor_anterior": TIPICO, "origem_anterior": "ficha_cadastral",
            "valor_proposto": TIPICO, "origem_proposto": "manual", "confianca_proposta": None,
            "fonte_tabela": None, "fonte_id": None, "status": "aceito",
            "decidido_por": str(DONO), "decidido_em": salvo, "created_at": salvo,
        }])
        row = _cliente(scoped, cid)
        assert not svc.correcao_do_dono(
            scoped, ORG_UUID, UUID(cid), "profissao",
            origem_atual="manual", confirmado_em_atual=None, presente=row["profissao"],
        )

        _ler_ficha(scoped, cid)

        row = _cliente(scoped, cid)
        assert (row["profissao"], row["profissao_origem"]) == (TIPICO, "ficha_cadastral")
        assert _pendentes(scoped) == []


class TestAddressCorrection:
    def test_a_typed_address_is_protected_from_a_comprovante(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Cilene Teste")])
        scoped.set_table_data("cliente_campo_conflitos", [])
        _dono_corrige(
            scoped, cid, endereco_cep="06711-020", endereco_logradouro="Alameda Liverpool",
            endereco_numero="81", endereco_cidade="Cotia", endereco_uf="SP",
        )

        aplicado, conflito = svc.aplicar_endereco_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "comprovante_endereco",
            {"cep": "01310-100", "logradouro": "Avenida Paulista", "numero": "1000",
             "cidade": "São Paulo", "uf": "SP"},
            confianca="alta", documento_id=uuid4(),
        )

        assert aplicado is False
        assert conflito is not None and conflito["protege_correcao"] is True
        assert _cliente(scoped, cid)["endereco_logradouro"] == "Alameda Liverpool"


class TestProvenInvalidIsNotProtected:
    def test_a_typed_cpf_failing_its_check_digit_still_loses_to_a_valid_reading(self, client, scoped):
        """The 2026-09-29 pin coexists: objective proof (`validador`) that
        the on-file value is not a CPF at all is no correction to protect."""
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Cilene Teste")])
        scoped.set_table_data("cliente_campo_conflitos", [])
        _dono_corrige(scoped, cid, cpf="111.111.111-12")

        svc.aplicar_campos_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "rg",
            _lidos(confianca="alta", cpf="412.954.238-98"), documento_id=uuid4(),
        )

        assert _cliente(scoped, cid)["cpf"] == "412.954.238-98"
        assert _pendentes(scoped) == []
