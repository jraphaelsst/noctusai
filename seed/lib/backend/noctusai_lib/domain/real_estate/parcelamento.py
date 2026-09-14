"""Even installment split — pure, `Decimal`-exact, remainder on the LAST one.

Split a total (or a remaining balance) across N equal installments so the
parts sum EXACTLY to the total. Every installment gets the same floored
amount except the last, which absorbs whatever is left over.

🔴 WHY THIS IS `Decimal`, UNLIKE ITS SIBLING IN erp-imobiliario
-----------------------------------------------------------------
``products/erp-imobiliario/backend/app/services/contratos_service.py``'s
``ContratosService.gerar_parcelas`` does the identical shape —
``valor_parcela = round(valor_financiado / num_parcelas, 2)``, last
installment absorbs the remainder — but in `float`. `float` cannot represent
centavos exactly, so a chain of `round(x / n, 2)` calls can be off by a
fraction of a centavo before the "remainder on the last" correction even
runs, and on some divisors it still leaves the sum a centavo short or over.
This module is the `Decimal`-exact version of the same idea, for a NEW
consumer (`social_wiring`'s negociação estruturada, migration 108) that
needs the guarantee to hold exactly. Porting `contratos_service.py` itself to
this helper is a separate, cross-product change — noted as a
scoped-improvement in the migration's delivery note rather than done here
(this module does not touch `erp-imobiliario`).

Lifted 2026-09-14 alongside migration 108's `atendimento_negociacao_parcelas`
table (`social_wiring` — contract-automation deal terms).
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

CENTAVO = Decimal("0.01")


def dividir_em_parcelas_iguais(valor_total: Decimal, num_parcelas: int) -> list[Decimal]:
    """Split `valor_total` into `num_parcelas` installments, largest first.

    Every installment but the last is `valor_total // num_parcelas`, floored
    to the centavo; the last one is whatever is left over — never
    independently rounded, so `sum(result) == valor_total` always, by
    construction rather than by coincidence.

    Raises `ValueError` for `num_parcelas <= 0` or `valor_total < 0` — both
    are caller bugs, not data this function can make sense of silently.
    """
    if num_parcelas <= 0:
        raise ValueError("num_parcelas deve ser um inteiro positivo")
    if valor_total < 0:
        raise ValueError("valor_total não pode ser negativo")

    if num_parcelas == 1:
        return [valor_total]

    valor_parcela = (valor_total / num_parcelas).quantize(CENTAVO, rounding=ROUND_DOWN)
    parcelas = [valor_parcela] * (num_parcelas - 1)
    valor_ultima = valor_total - (valor_parcela * (num_parcelas - 1))
    parcelas.append(valor_ultima)
    return parcelas


__all__ = ["CENTAVO", "dividir_em_parcelas_iguais"]
