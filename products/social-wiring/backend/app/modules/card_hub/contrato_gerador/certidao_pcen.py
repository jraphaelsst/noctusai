"""The Receita "positiva com efeitos de negativa" 2ª-via rule — ONE place.

Owner decision A (2026-10-01): when the Receita (`cnd_federal`) certidão is a
valid 2ª via of a "positiva com efeitos de negativa" (PCEN), the contract gate
judges it by its PRINTED validity (`validade_ate >= data de assinatura`), not
by emission age (`politica.certidao_max_dias`). The PGFN cannot issue a NEW
certidão while the old one is valid, so the 2ª via carries the ORIGINAL (old)
emission date by design.

Amendment (same day): an operator may not know that difference, so the
exception is never a silent pass — it is an ACKNOWLEDGMENT the operator gives
per resultado ("Entendi — seguir com esta certidão") or turns into a support
question ("Tenho dúvida"). `derivacao._certidoes` raises it as a
`confirmacao`; `Avaliacao.pronto` stays False until it is acknowledged.

This module is pure (no app imports) and is imported by the three places that
must agree: the contract gate (`derivacao`), the per-party certidões cell
(`certidoes_partes_service`) and the party summary (`partes_service`).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

#: Marker `certidoes.service` stamps into `certidao_resultados.api_response`
#: when the certidão came from the 2ª-via retry (the machine-readable twin of
#: the visible note).
MARCA_SEGUNDA_VIA = "noctus_segunda_via"
RESULTADO_PCEN = "positiva_com_efeito_de_negativa"
CODIGO_CONFIRMACAO = "CERTIDAO_PCEN_SEGUNDA_VIA"

TITULO = "Certidão da Receita Federal: positiva com efeitos de negativa"
ACAO_ENTENDI = "Entendi — seguir com esta certidão"
ACAO_DUVIDA = "Tenho dúvida — falar com o suporte"


def e_segunda_via(api_response: Any) -> bool:
    return isinstance(api_response, dict) and bool(api_response.get(MARCA_SEGUNDA_VIA))


def excecao_aplica(*, resultado: Any, segunda_via: bool, validade_ate: Optional[date]) -> bool:
    """The exception is precise and narrow: PCEN ∧ it came via 2ª via ∧ the
    printed validity was parsed. Any other tipo / case keeps the 30-day rule."""
    return bool(resultado == RESULTADO_PCEN and segunda_via and validade_ate is not None)


def esta_vencida(*, emitida_em: Optional[date], validade_ate: Optional[date],
                 referencia: date, max_dias: int, excecao: bool) -> bool:
    """The cell's `stale_para_contrato`. Exception → the printed validity
    decides (`validade_ate < referencia`); everything else → emission age
    (`>= max_dias`), exactly as before. The gate calls the same exception
    test and then applies the same two comparisons."""
    if excecao:
        return validade_ate is not None and validade_ate < referencia
    return emitida_em is not None and (referencia - emitida_em).days >= max_dias


def br(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def aviso(emitida_em: Optional[date], validade_ate: date) -> str:
    return (
        "Receita: certidão positiva com efeitos de negativa — 2ª via emitida em "
        f"{br(emitida_em)}, válida até {br(validade_ate)} "
        "(a PGFN não emite nova enquanto esta for válida)"
    )


def explicacao(emitida_em: Optional[date], validade_ate: date) -> list[str]:
    """The educational copy shown to the operator (readiness screen AND the
    certidões tab) — plain pt-BR."""
    return [
        "Esta certidão da Receita Federal/PGFN é do tipo \"positiva com efeitos de "
        "negativa\": existem débitos, mas eles estão parcelados, garantidos ou com a "
        "cobrança suspensa. Enquanto estiver dentro do prazo, ela vale como uma "
        "certidão negativa.",
        "A PGFN não consegue emitir uma certidão nova para quem já tem uma positiva com "
        "efeitos de negativa em vigor. Por isso o sistema buscou a 2ª via da certidão "
        "original — segundo a documentação da InfoSimples, o efeito prático é o mesmo "
        "de uma emissão nova.",
        f"É por isso que a data de emissão ({br(emitida_em)}) parece antiga: é a data da "
        f"certidão original, e não um defeito. O que vale é a validade impressa no "
        f"documento — até {br(validade_ate)}, que cobre a data de assinatura.",
        "O que fazer: confira no PDF se a validade impressa cobre a data de assinatura. "
        f"Se você já conhecia essa situação, clique em \"{ACAO_ENTENDI}\". Se tiver qualquer "
        f"dúvida, clique em \"{ACAO_DUVIDA}\" antes de gerar o contrato.",
    ]


def ciente_vale(*, ciente_em: Any, ciente_validade: Optional[date], validade_ate: Optional[date]) -> bool:
    """An acknowledgment holds only for the validity it was given on — a
    different printed validity is a different certidão and needs a new one."""
    return bool(ciente_em) and ciente_validade is not None and ciente_validade == validade_ate
