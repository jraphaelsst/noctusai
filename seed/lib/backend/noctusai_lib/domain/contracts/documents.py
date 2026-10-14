"""Document rendering: the contract text from a `{{placeholder}}` template -- pure, no I/O.

`render_contract_text(contract, lines, template)` fills the template with the contract's own data
(party, dates, billing model in words, lines table, notice / penalty clauses). Unknown placeholders
are kept visibly (`[[campo]]`) rather than silently blanked, so a typo in a template shows in the
document instead of shipping an empty clause. The PDF is the HOST's: `DocumentRenderer`
(`(title, body) -> (bytes, mime)`) turns the text into the file sent for signature;
`plain_text_document` is the dependency-free default.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Optional

from ._common import iso, to_date
from .types import BillingFrequency, BillingModel

DocumentRenderer = Callable[[str, str], tuple[bytes, str]]

_FREQ_PT = {BillingFrequency.MONTHLY.value: "mensal", BillingFrequency.QUARTERLY.value: "trimestral",
            BillingFrequency.YEARLY.value: "anual"}

DEFAULT_TEMPLATE = """CONTRATO {{numero}} — {{titulo}}

CONTRATANTE: {{parte_nome}} {{parte_documento}}

OBJETO
{{linhas}}

VIGÊNCIA: {{vigencia}}

PREÇO E FORMA DE PAGAMENTO
{{cobranca}}

REAJUSTE
{{reajuste}}

RESCISÃO
{{rescisao}}

{{observacoes}}"""


def brl(cents: Any) -> str:
    """`123456` -> `R$ 1.234,56` (integer cents in, pt-BR out)."""
    n = int(cents or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    reais, cent = divmod(n, 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{cent:02d}"


def _date_pt(value: Any) -> str:
    d = to_date(value)
    return d.strftime("%d/%m/%Y") if d else "—"


def _billing_text(c: Mapping[str, Any]) -> str:
    model, amount = c["billing_model"], brl(c.get("amount_cents"))
    due_day = c.get("due_day")
    if model == BillingModel.ONE_TIME.value:
        return f"Pagamento único de {amount}, com vencimento em {_date_pt(c.get('first_due_date'))}."
    if model == BillingModel.INSTALLMENTS.value:
        n = int(c.get("installments_count") or 1)
        return f"{amount} em {n} parcelas mensais, a primeira com vencimento em {_date_pt(c.get('first_due_date'))}."
    day = f", todo dia {due_day}" if due_day else ""
    if model == BillingModel.RETAINER.value:
        hours = int(c.get("retainer_minutes") or 0) // 60
        return (f"Honorário mensal de {amount}{day}, incluindo {hours}h mensais. Horas excedentes: "
                f"{brl(c.get('excess_rate_cents'))} por hora, faturadas no mês seguinte.")
    return f"{amount} ({_FREQ_PT.get(c.get('frequency') or 'monthly', 'mensal')}){day}."


def _readjust_text(c: Mapping[str, Any]) -> str:
    idx = c.get("readjustment_index")
    if idx in (None, "none"):
        return "Sem reajuste previsto."
    every = int(c.get("readjustment_every_months") or 12)
    return f"Reajuste a cada {every} meses pelo índice {idx}."


def _termination_text(c: Mapping[str, Any]) -> str:
    notice = int(c.get("notice_days") or 0)
    parts = [f"Rescisão mediante aviso prévio de {notice} dias." if notice else "Rescisão sem aviso prévio."]
    pen = int(c.get("penalty_cents") or 0)
    bp = int(c.get("penalty_bp") or 0)
    if pen or bp:
        extra = f" e {bp / 100:.2f}% do saldo remanescente".replace(".", ",") if bp else ""
        parts.append(f"Rescisão antecipada: multa de {brl(pen)}{extra}.")
    return " ".join(parts)


def _lines_text(lines: list[Mapping[str, Any]], c: Mapping[str, Any]) -> str:
    if not lines:
        return str(c.get("title") or "")
    return "\n".join(f"- {ln['description']} — {ln['quantity']} x {brl(ln['unit_price_cents'])} = "
                     f"{brl(int(ln['quantity']) * int(ln['unit_price_cents']))}" for ln in lines)


def placeholders(c: Mapping[str, Any], lines: Optional[list[Mapping[str, Any]]] = None) -> dict[str, str]:
    start, end = c.get("start_date"), c.get("end_date")
    vigencia = f"a partir de {_date_pt(start)}" + (f" até {_date_pt(end)}" if end else ", por prazo indeterminado")
    if c.get("auto_renew") and end:
        vigencia += f", renovando-se automaticamente por {int(c.get('renewal_months') or 12)} meses"
    return {
        "numero": str(c.get("number") or "s/n"), "titulo": str(c.get("title") or ""), "parte_nome": str(c.get("party_name") or "—"),
        "parte_documento": f"({c['party_doc']})" if c.get("party_doc") else "", "linhas": _lines_text(lines or [], c),
        "vigencia": vigencia, "cobranca": _billing_text(c), "reajuste": _readjust_text(c), "rescisao": _termination_text(c),
        "observacoes": str(c.get("notes") or ""), "valor": brl(c.get("amount_cents")), "inicio": _date_pt(start),
        "fim": _date_pt(end), "primeiro_vencimento": _date_pt(c.get("first_due_date")),
    }


def render_contract_text(c: Mapping[str, Any], lines: Optional[list[Mapping[str, Any]]] = None, template: Optional[str] = None) -> str:
    values = placeholders(c, lines)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: values.get(m.group(1), f"[[{m.group(1)}]]"), template or DEFAULT_TEMPLATE).strip()


def plain_text_document(title: str, body: str) -> tuple[bytes, str]:
    """Dependency-free default `DocumentRenderer` (UTF-8 text). A host wanting a PDF passes its own renderer."""
    return body.encode("utf-8"), "text/plain"


__all__ = ["DEFAULT_TEMPLATE", "DocumentRenderer", "brl", "placeholders", "plain_text_document", "render_contract_text"]
