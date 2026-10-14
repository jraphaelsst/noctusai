"""`GET /accountant-checklist` (CONTRACT §10.4): what to hand a contador.

Every PROVISIONAL choice of this store (from `fin_dre_settings`, with its current value and confirmation state),
the open questions only an accountant can answer (content of `projects/commerce-seed-p4/ACCOUNTANT-QUESTIONS.md`,
each with its sources), and the export links (DRE CSV, entries CSV, ledger OFX). The software prepares, classifies
and exports; it never signs, files or chooses a regime (`KB § PATTERNS/finance/dre-structure.md §7`).
"""
from __future__ import annotations

from typing import Any, Optional

from . import dre_settings as settings_svc
from ._common import Scope, now_iso

DISCLAIMER = (
    "Este sistema prepara, classifica e exporta; não assina, não entrega obrigações e não escolhe regime tributário. "
    "A escrituração contábil é responsabilidade de um contador (CRC) — Código Civil art. 1.182; ME/EPP: livro-caixa no mínimo, LC 123 art. 26 §2."
)

#: choice name -> the question to ask, why it is open, the options with their sources.
CHOICE_QUESTIONS: dict[str, dict[str, Any]] = {
    "gateway_fee_line": {
        "id": "Q1",
        "question": "A taxa do gateway/cartão (MDR) é despesa com vendas ou despesa financeira?",
        "why": "Não há norma; a prática se divide. Para o imposto, a comissão não pode ser excluída da base do Simples (SC Cosit 143/2021).",
        "options": {"selling_expenses": "Despesas com vendas (padrão)", "financial_expenses": "Despesas financeiras"},
        "sources": ["KB § PATTERNS/finance/dre-structure.md §4(a)", "Solução de Consulta Cosit 143/2021"],
    },
    "anticipation_fee_line": {
        "id": "Q1b",
        "question": "A antecipação de recebíveis é despesa financeira?",
        "why": "Consenso de prática: é o custo do dinheiro, não da venda.",
        "options": {"financial_expenses": "Despesas financeiras (padrão)", "selling_expenses": "Despesas com vendas"},
        "sources": ["KB § PATTERNS/finance/dre-structure.md §4(b)"],
    },
    "chargeback_line": {
        "id": "Q3",
        "question": "O chargeback perdido é dedução da receita ou perda operacional? E ele reduz a base do Simples?",
        "why": "Nenhuma fonte brasileira encontrada. A LC 123 art. 3 §1 fala em 'vendas canceladas', sem tratar de chargeback.",
        "options": {"deductions": "Deduções da receita (padrão)", "other_operating": "Outras despesas operacionais"},
        "sources": ["KB § PATTERNS/finance/dre-structure.md §4(e)", "LC 123/2006 art. 3 §1"],
    },
    "chargeback_fee_line": {
        "id": "Q3b",
        "question": "A tarifa cobrada por um chargeback é despesa com vendas?",
        "why": "Escolha de prática; a tarifa nasce da venda.",
        "options": {"selling_expenses": "Despesas com vendas (padrão)", "financial_expenses": "Despesas financeiras"},
        "sources": ["KB § PATTERNS/finance/dre-structure.md §4(e)"],
    },
    "installment_interest_line": {
        "id": "Q2",
        "question": "Os juros de parcelamento pagos pelo comprador são receita bruta ou receita financeira?",
        "why": "Para o imposto são receita bruta (SC Cosit 94/2025); para a contabilidade, em aberto (NBC TG 1002 §23.2 x §25.1).",
        "options": {"gross_revenue": "Receita bruta (padrão)", "financial_revenue": "Receitas financeiras"},
        "sources": ["KB § PATTERNS/finance/dre-structure.md §4(h)", "Solução de Consulta Cosit 94/2025", "NBC TG 1002 §11.3, §23.2, §25.1"],
    },
}

OPEN_QUESTIONS: tuple[dict[str, Any], ...] = (
    {"id": "Q4", "question": "Divisão do DAS: tudo em Deduções (padrão do produto) ou separar a parcela de IRPJ/CSLL?",
     "context": "NBC TG 1002 §29.3 admite ambos; a ITG 1000 (revogada) exigia a dedução. A divisão usa o percentual de repartição do seu anexo.",
     "sources": ["NBC TG 1002 §29.3", "NBC TG 1001 §29.3(b)", "ITG 1000 Anexo 3"]},
    {"id": "Q5", "question": "Custo das vendas = compras do mês é aceitável sem controle de estoque?",
     "context": "A linha vem do NBC TG 1002 §5.1(d); a aproximação é nossa e está em aberto.", "sources": ["NBC TG 1002 §5.1(d)"]},
    {"id": "Q6", "question": "Livro-caixa ou contabilidade completa?",
     "context": "Importa para distribuir lucro acima do presumido sem imposto (LC 123 art. 14 §2).", "sources": ["LC 123/2006 arts. 14, 26, 27", "CGSN 140 art. 63"]},
    {"id": "Q7", "question": "IBS/CBS ficam dentro ou fora do DAS a partir de 2027, e como apresentá-los?",
     "context": "Res. CGSN 190/2026 art. 5 XVI permite pagá-los fora do DAS; sem fonte sobre a apresentação.", "sources": ["Res. CGSN 190/2026 art. 5 XVI"]},
    {"id": "Q8", "question": "MEI: o que manter a partir de 2027?",
     "context": "A exigência do relatório mensal de receitas muda em 2027-01-01.", "sources": ["Res. CGSN 190/2026", "CGSN 140 art. 106 §1"]},
    {"id": "Q9", "question": "Lucro Presumido: a dispensa de ECD continua válida?",
     "context": "IN RFB 2.003/2021 art. 3 §1 V e §3.", "sources": ["IN RFB 2.003/2021"]},
    {"id": "Q10", "question": "Retirada de lucro / pró-labore do sócio: é movimento de patrimônio, não linha da DRE — confirmar.",
     "context": "Em aberto no desenho (CONTRACT §10.5.7).", "sources": ["KB § PATTERNS/finance/dre-structure.md"]},
)


def build_checklist(
    s: Scope, *, export_links: Optional[dict[str, str]] = None, regime_prefill: Optional[str] = None
) -> dict:
    settings = settings_svc.get_settings(s, regime_prefill=regime_prefill)
    provisional = []
    confirmed = []
    for name, state in settings["choices"].items():
        meta = CHOICE_QUESTIONS[name]
        item = {
            "choice": name,
            "question_id": meta["id"],
            "question": meta["question"],
            "why_open": meta["why"],
            "options": meta["options"],
            "current_value": state["value"],
            "default_value": state["default"],
            "provisional": state["provisional"],
            "confirmed_by": state["confirmed_by"],
            "confirmed_at": state["confirmed_at"],
            "note": state["note"],
            "sources": meta["sources"],
        }
        (provisional if state["provisional"] else confirmed).append(item)
    return {
        "generated_at": now_iso(),
        "tax_regime": settings["tax_regime"],
        "tax_regime_informed": settings["tax_regime"] != "unknown",
        "das_split_irpj_csll": settings["das_split_irpj_csll"],
        "provisional_choices": provisional,
        "confirmed_choices": confirmed,
        "open_questions": list(OPEN_QUESTIONS),
        "exports": [{"name": k, "path": v} for k, v in (export_links or {}).items()],
        "disclaimer": DISCLAIMER,
    }


__all__ = ["CHOICE_QUESTIONS", "DISCLAIMER", "OPEN_QUESTIONS", "build_checklist"]
