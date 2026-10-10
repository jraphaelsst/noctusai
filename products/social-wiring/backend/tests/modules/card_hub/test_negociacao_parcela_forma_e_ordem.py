"""Parcela `forma_pagamento` has no 50-char ceiling, and parcelas can be
re-ordered atomically (owner, 2026-10-03).

1. **forma_pagamento is prose.** A 65-char financing forma was refused by the
   negociação schemas' `max_length=50` (60 on the aditivo twin) while both DB
   columns were already unbounded TEXT (108/190). The bound is now the house
   free-text cap (`FORMA_PAGAMENTO_MAX_LENGTH`, 2000) on every write path —
   create, patch, dividir-saldo, aditivo — and the contract generator renders a
   long forma lint-clean without lower-casing its proper nouns.
2. **Reorder.** `PUT .../negociacao/parcelas/ordem` takes the FULL ordered id
   list and rewrites `ordem` 0..N-1 through migration 195's SQL function (one
   transaction); a partial / stale / repeated list is a 400 and writes nothing.

All data synthetic. Auth: `test_auth_boundary_negociacao_estruturada.py`.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from noctusai_lib.testing.migrations import migration_path

import pytest
from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento, lint
from app.modules.card_hub.contrato_gerador.frases import _forma
from app.modules.card_hub.schemas import FORMA_PAGAMENTO_MAX_LENGTH
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.test_negociacao_estruturada import _auth, _seed

#: 65 chars — the live shape that was refused (synthetic wording).
FORMA_LONGA = "Transferência bancária com recursos do financiamento Banco Exemplo"
assert len(FORMA_LONGA) > 60


def _base(cid: str) -> str:
    return f"/api/clientes/{cid}/negociacao"


class TestFormaPagamentoSemTetoDe50:
    def test_a_long_forma_round_trips_on_create(self, client, scoped):
        cid, _aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"{_base(cid)}/parcelas",
            json={"tipo": "financiamento", "valor": "400000.00", "forma_pagamento": FORMA_LONGA},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        assert r.json()["parcelas"][0]["forma_pagamento"] == FORMA_LONGA

    def test_a_long_forma_round_trips_on_patch(self, client, scoped):
        cid, _aid = _seed(scoped, com_negociacao=True)
        p = client.post(
            f"{_base(cid)}/parcelas", json={"tipo": "sinal", "valor": "50000.00"}, headers=_auth(),
        ).json()["parcelas"][0]
        r = client.patch(
            f"{_base(cid)}/parcelas/{p['id']}", json={"forma_pagamento": FORMA_LONGA}, headers=_auth(),
        )
        assert r.status_code == 200, r.text
        assert r.json()["parcelas"][0]["forma_pagamento"] == FORMA_LONGA

    def test_a_long_forma_round_trips_on_dividir_saldo(self, client, scoped):
        cid, _aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"{_base(cid)}/parcelas/dividir-saldo",
            json={"num_parcelas": 2, "forma_pagamento": FORMA_LONGA},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        assert {p["forma_pagamento"] for p in r.json()["parcelas"]} == {FORMA_LONGA}

    def test_the_bound_is_the_house_free_text_cap_and_names_the_field(self, client, scoped):
        cid, _aid = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"{_base(cid)}/parcelas",
            json={"tipo": "sinal", "valor": "1.00", "forma_pagamento": "x" * (FORMA_PAGAMENTO_MAX_LENGTH + 1)},
            headers=_auth(),
        )
        assert r.status_code == 422
        assert "forma_pagamento" in r.json()["error"]["message"]

    def test_the_aditivo_twin_shares_the_same_bound(self):
        from app.modules.card_hub.contrato_aditivo.schemas import ParcelaAditivoIn

        campo = ParcelaAditivoIn.model_fields["forma_pagamento"]
        limites = [m.max_length for m in campo.metadata if hasattr(m, "max_length")]
        assert limites == [FORMA_PAGAMENTO_MAX_LENGTH]
        ParcelaAditivoIn(tipo="financiamento", valor="400000.00", forma_pagamento=FORMA_LONGA)


class TestFormaNoContrato:
    def test_a_vocabulary_label_reads_lower_case_acronyms_kept(self):
        assert _forma("Transferência") == "transferência"
        assert _forma("Cartão de Crédito") == "cartão de crédito"
        assert _forma("PIX") == "PIX"

    def test_free_prose_keeps_its_proper_nouns(self):
        assert _forma(FORMA_LONGA) == (
            "transferência bancária com recursos do financiamento Banco Exemplo"
        )
        assert _forma("TED  para a  conta do vendedor") == "TED para a conta do vendedor"

    def test_a_long_forma_renders_lint_clean(self):
        d = fx.variante(1)
        p0 = replace(d.parcelas[0], forma_pagamento=FORMA_LONGA)
        d = replace(d, parcelas=[p0] + d.parcelas[1:])
        pol = fx.politica_variante(1)
        sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
        av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
        assert av.pronto, (av.faltando, av.bloqueios)
        r = documento.renderizar(
            get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA, fx.REFERENCIA,
        )
        assert lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas) == []
        assert any(
            "por meio de transferência bancária com recursos do financiamento Banco Exemplo" in p
            for p in r.paragrafos
        )


def _criar(client, cid: str, tipo: str, valor: str) -> dict:
    corpo = client.post(
        f"{_base(cid)}/parcelas", json={"tipo": tipo, "valor": valor}, headers=_auth(),
    ).json()
    return next(p for p in corpo["parcelas"] if p["tipo"] == tipo)


class TestReordenarParcelas:
    def test_a_sinal_created_last_moves_to_the_front(self, client, scoped):
        cid, _aid = _seed(scoped, com_negociacao=True)
        _criar(client, cid, "financiamento", "400000.00")
        _criar(client, cid, "intermediaria", "50000.00")
        sinal = _criar(client, cid, "sinal", "50000.00")
        antes = client.get(f"{_base(cid)}/estruturada", headers=_auth()).json()["parcelas"]
        assert antes[-1]["id"] == sinal["id"]  # created last ⇒ printed last
        nova = [sinal["id"]] + [p["id"] for p in antes[:-1]]

        r = client.put(
            f"{_base(cid)}/parcelas/ordem", json={"parcela_ids": nova}, headers=_auth(),
        )
        assert r.status_code == 200, r.text
        ordens = {p["id"]: p["ordem"] for p in r.json()["parcelas"]}
        assert ordens == {pid: i for i, pid in enumerate(nova)}
        # Persisted, not just echoed: a fresh GET reads the same order.
        lido = client.get(f"{_base(cid)}/estruturada", headers=_auth()).json()["parcelas"]
        assert [p["id"] for p in lido] == nova

    @pytest.mark.parametrize("forma", ["parcial", "repetida", "estranha"])
    def test_a_list_that_is_not_exactly_the_current_set_is_refused_and_writes_nothing(
        self, client, scoped, forma,
    ):
        cid, _aid = _seed(scoped, com_negociacao=True)
        a = _criar(client, cid, "sinal", "50000.00")
        b = _criar(client, cid, "saldo", "450000.00")
        ids = {
            "parcial": [b["id"]],
            "repetida": [b["id"], b["id"]],
            "estranha": [b["id"], a["id"], "00000000-0000-0000-0000-000000000099"],
        }[forma]

        r = client.put(f"{_base(cid)}/parcelas/ordem", json={"parcela_ids": ids}, headers=_auth())
        assert r.status_code == 400, r.text
        linhas = scoped.table("atendimento_negociacao_parcelas").select("*").execute().data
        assert {x["id"]: x["ordem"] for x in linhas} == {a["id"]: 0, b["id"]: 1}

    def test_the_body_is_strict(self, client, scoped):
        cid, _aid = _seed(scoped, com_negociacao=True)
        r = client.put(
            f"{_base(cid)}/parcelas/ordem", json={"parcela_ids": [], "x": 1}, headers=_auth(),
        )
        assert r.status_code == 422


MIGRATION = migration_path(Path(__file__).resolve().parents[3], "reordenar_negociacao_parcelas")


class TestMigration195:
    @pytest.fixture(scope="class")
    def flat(self) -> str:
        sql = MIGRATION.read_text(encoding="utf-8")
        code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
        return " ".join(code.split())

    def test_parses(self):
        pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
        assert pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))

    def test_one_org_scoped_invoker_update_refusing_any_other_set(self, flat: str):
        assert "CREATE OR REPLACE FUNCTION social_wiring.reordenar_negociacao_parcelas(" in flat
        assert "SECURITY INVOKER" in flat and "SECURITY DEFINER" not in flat
        assert "SET search_path = social_wiring, public" in flat
        assert "FOR UPDATE" in flat
        assert "USING ERRCODE = '22023'" in flat
        assert "SET ordem = (t.pos - 1)::INTEGER" in flat
        assert "unnest(p_parcela_ids) WITH ORDINALITY AS t(id, pos)" in flat
        assert "p.org_id = p_org_id AND p.atendimento_id = p_atendimento_id" in flat

    def test_only_service_role_can_execute(self, flat: str):
        sig = "social_wiring.reordenar_negociacao_parcelas(UUID, UUID, UUID[], UUID)"
        assert f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC" in flat
        assert f"REVOKE ALL ON FUNCTION {sig} FROM anon, authenticated" in flat
        assert f"GRANT EXECUTE ON FUNCTION {sig} TO service_role" in flat

    def test_no_ddl_on_any_table(self, flat: str):
        for forbidden in ("ALTER TABLE", "CREATE TABLE", "DROP ", "INSERT ", "DELETE "):
            assert forbidden not in flat
