"""Template rendering for reminders -- pure, no IO. Variables are `{nome}`-style, pt-BR defaults below."""
from __future__ import annotations

import re
from datetime import date
from typing import Mapping, Optional

from ..errors import invalid
from .types import TEMPLATE_VARIABLES, ReminderContact

_VAR = re.compile(r"\{(\w+)\}")
_LONE_VAR = re.compile(r"^\s*\{(\w+)\}\s*$")


def format_brl(cents: int) -> str:
    whole, frac = divmod(int(cents), 100)
    return f"R$ {whole:,}".replace(",", ".") + f",{frac:02d}"


def validate_template(template: str, *, field: str = "template") -> None:
    if not str(template or "").strip():
        raise invalid(field, "Informe o texto da mensagem.")
    unknown = sorted({v for v in _VAR.findall(template) if v not in TEMPLATE_VARIABLES})
    if unknown:
        raise invalid(field, f"Variáveis desconhecidas: {', '.join('{' + u + '}' for u in unknown)}.", code="variavel_desconhecida")


def variables_for(contact: ReminderContact, *, amount_cents: int, due: date, days_overdue: int) -> Mapping[str, str]:
    nome = contact.nome or contact.nome_fantasia or contact.razao_social or ""
    return {
        "nome": nome,
        "razao_social": contact.razao_social or contact.nome_fantasia or nome,
        "nome_fantasia": contact.nome_fantasia or contact.razao_social or nome,
        "valor": format_brl(amount_cents),
        "vencimento": due.strftime("%d/%m/%Y"),
        "link_pagamento": contact.link_pagamento or "",
        "pix_copia_cola": contact.pix_copia_cola or "",
        "dias_atraso": str(max(days_overdue, 0)),
    }


def render(template: str, values: Mapping[str, str]) -> str:
    """Substitute variables. A line that is ONLY a variable which resolved empty (no payment link) is dropped."""
    out: list[str] = []
    for line in template.split("\n"):
        lone = _LONE_VAR.match(line)
        if lone and not values.get(lone.group(1), ""):
            continue
        out.append(_VAR.sub(lambda m: values.get(m.group(1), m.group(0)), line))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


#: (offset_days, template) -- the sensible pt-BR default ladder: 3 days before, on the day, 1 and 7 days late.
DEFAULT_RULES: tuple[tuple[int, str], ...] = (
    (-3, "Olá, {nome}! Passando para lembrar que sua cobrança de {valor} vence em {vencimento}.\n"
         "Link para pagamento:\n{link_pagamento}\n{pix_copia_cola}"),
    (0, "Olá, {nome}! Sua cobrança de {valor} vence hoje ({vencimento}).\n"
        "Link para pagamento:\n{link_pagamento}\n{pix_copia_cola}"),
    (1, "Olá, {nome}. Não identificamos o pagamento de {valor}, com vencimento em {vencimento}. "
        "Se já pagou, desconsidere esta mensagem.\n{link_pagamento}\n{pix_copia_cola}"),
    (7, "Olá, {nome}. Sua cobrança de {valor} (vencida em {vencimento}) está com {dias_atraso} dias de atraso. "
        "Podemos ajudar a regularizar?\n{link_pagamento}\n{pix_copia_cola}"),
)


def sample_values(contact: Optional[ReminderContact] = None) -> Mapping[str, str]:
    """Example values for the rules UI preview."""
    c = contact or ReminderContact(
        nome="Maria", razao_social="Maria Silva LTDA", nome_fantasia="Studio Maria",
        link_pagamento="https://pagamento.exemplo/abc", pix_copia_cola="00020126...",
    )
    return variables_for(c, amount_cents=150000, due=date(2026, 10, 20), days_overdue=3)
