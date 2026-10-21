"""Month-precision parcela deadline (Migration 294): "prazo máximo de
pagamento até maio de 2027". Synthetic data only."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from datetime import date

from noctusai_lib.domain.texto_ptbr import mes_ano_por_extenso
from noctusai_lib.testing.migrations import migration_path

from app.modules.card_hub.contrato_gerador import derivacao, frases
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.test_negociacao_estruturada import _auth, _seed

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


def _base(cid: str) -> str:
    return f"/api/clientes/{cid}/negociacao"


class TestRouter:
    def test_month_precision_is_normalised_to_the_1st_and_round_trips(self, client, scoped):
        cid, _ = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"{_base(cid)}/parcelas",
            json={"tipo": "direta", "valor": "100.00", "vencimento": "2027-05-31",
                  "vencimento_precisao": "mes"},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        p = r.json()["parcelas"][0]
        assert (p["vencimento"], p["vencimento_precisao"]) == ("2027-05-01", "mes")

    def test_default_is_an_exact_day(self, client, scoped):
        cid, _ = _seed(scoped, com_negociacao=True)
        p = client.post(
            f"{_base(cid)}/parcelas",
            json={"tipo": "direta", "valor": "100.00", "vencimento": "2027-05-31"},
            headers=_auth(),
        ).json()["parcelas"][0]
        assert (p["vencimento"], p["vencimento_precisao"]) == ("2027-05-31", "dia")

    def test_month_precision_without_a_date_is_refused_naming_the_field(self, client, scoped):
        cid, _ = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"{_base(cid)}/parcelas",
            json={"tipo": "direta", "valor": "100.00", "vencimento_precisao": "mes"},
            headers=_auth(),
        )
        assert r.status_code in (400, 422), r.text
        assert "vencimento" in r.text

    def test_patch_a_new_date_alone_resets_to_exact_day(self, client, scoped):
        cid, _ = _seed(scoped, com_negociacao=True)
        p = client.post(
            f"{_base(cid)}/parcelas",
            json={"tipo": "direta", "valor": "100.00", "vencimento": "2027-05-01",
                  "vencimento_precisao": "mes"},
            headers=_auth(),
        ).json()["parcelas"][0]
        r = client.patch(
            f"{_base(cid)}/parcelas/{p['id']}", json={"vencimento": "2027-06-15"}, headers=_auth(),
        )
        assert r.status_code == 200, r.text
        q = r.json()["parcelas"][0]
        assert (q["vencimento"], q["vencimento_precisao"]) == ("2027-06-15", "dia")

    def test_invalid_precision_is_rejected(self, client, scoped):
        cid, _ = _seed(scoped, com_negociacao=True)
        r = client.post(
            f"{_base(cid)}/parcelas",
            json={"tipo": "direta", "valor": "100.00", "vencimento": "2027-05-01",
                  "vencimento_precisao": "ano"},
            headers=_auth(),
        )
        assert r.status_code == 422


class TestGerador:
    def _momento(self, **extra):
        p = fx.parcela("p2", "direta", "1000.00", 2, **extra)
        return frases._momento_parcela(p, tem_financiamento=False, ref_financiamento="03")

    def test_month_precision_prints_the_prazo_maximo_wording(self):
        m = self._momento(vencimento=date(2027, 5, 1), vencimento_precisao="mes")
        assert m == "com prazo máximo de pagamento até maio de 2027"

    def test_exact_date_keeps_the_current_text(self):
        assert self._momento(vencimento=date(2027, 5, 31)) == "com vencimento em 31/05/2027"

    def test_month_name_helper(self):
        assert mes_ano_por_extenso(date(2027, 3, 1)) == "março de 2027"

    def test_end_of_month_is_the_limit_for_ordering(self):
        p = fx.parcela("p", "direta", "1.00", 1, vencimento=date(2027, 2, 1), vencimento_precisao="mes")
        assert p.vencimento_limite == date(2027, 2, 28)

    def test_a_month_parcela_is_ready_and_orders_against_exact_dates(self):
        d = fx.variante(1)
        sem_venc = [replace(p, vencimento=None, evento=p.evento or "no ato") for p in d.parcelas]
        ps = list(sem_venc)
        ps[0] = replace(ps[0], vencimento=date(2027, 5, 15))
        ps[1] = replace(ps[1], vencimento=date(2027, 5, 1), vencimento_precisao="mes")
        d2 = replace(d, parcelas=ps)
        pol = fx.politica_variante(1)
        sw = derivacao.derivar_switches(d2, pol, fx.REFERENCIA)
        av = derivacao.avaliar(d2, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
        # "até maio de 2027" (limit 31/05) after 15/05: ordered, no ORDER blocker.
        assert not any(b.codigo == "VENCIMENTOS_FORA_DE_ORDEM" for b in av.bloqueios), av.bloqueios


def test_migration_294_is_additive_and_idempotent():
    sql = migration_path(MIGRATIONS, "parcela_vencimento_precisao").read_text()
    assert "ADD COLUMN IF NOT EXISTS vencimento_precisao" in sql
    assert "DEFAULT 'dia'" in sql
