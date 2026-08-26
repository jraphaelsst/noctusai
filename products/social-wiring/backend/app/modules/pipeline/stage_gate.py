"""What an atendimento must know about its titular before it can move stages.

WHY THIS IS A GATE AND NOT A WARNING
------------------------------------
The funil's stages describe a real process — a lead that reaches "negociação"
is one somebody is actively working. Letting a card advance while nobody knows
the person's name or how to phone them produces a pipeline that reports work
in progress on records that cannot be worked, and the discovery happens at the
worst possible moment: when someone tries to call.

So this is enforced server-side, on the move itself. The frontend disables the
drag and says why, but that is a courtesy — the API is the gate, because the
drag is not the only way a card moves (the board, the card dialog, and any
future automation all reach the same endpoint).

🔴 WHY IT ASKS THE CHECKLIST INSTEAD OF READING COLUMNS
-------------------------------------------------------
The tempting implementation is two column reads: `nome` non-empty, phone
non-empty. It is wrong for a reason that has already bitten this module's
neighbours twice.

"Does this person have a phone?" is genuinely subtle here — the number lives in
`celular` for some clientes and in `chave_canonica` for others, gated by
`chave_tipo`, and an email-keyed cliente's `chave_canonica` is not a phone at
all. `documento_checklist_service` already answers exactly that question, is
already tested for it, and is already what the operator SEES on the card.

Two implementations of one question drift, and when they do the failure is
maximally confusing: the checkbox on the Documentos tab is ticked and the card
still refuses to move, with no way for the user to tell which one is lying. So
there is one definition, and this module is a second reader of it.

A consequence worth stating plainly: a HUMAN OVERRIDE on the checklist opens
the gate. That is deliberate and consistent — the override exists for "I
confirmed this by other means", and a methodology that lets a person assert
completeness on the card but not act on it would just teach them to fill the
column with a placeholder instead.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.modules.card_hub import documento_checklist_service as checklist_svc

#: What an atendimento's titular must have before the card may leave its stage.
#:
#: 🔴 `nome`, NOT `nome_completo` — corrected 2026-08-24 after the first cut of
#: this gate was too strict.
#:
#: The first version required the checklist's "Nome Completo" item, which
#: demands something that LOOKS like a full name. That refused to move a lead
#: called "Ana" — and "Ana" is precisely what a WhatsApp push name looks like,
#: i.e. what almost every lead arrives as. The product owner's rule is the
#: workflow one: whatever name the channel supplied is accepted and is
#: REQUIRED, and the legal full name arrives later off the uploaded RG. A gate
#: that blocks the normal first move of a normal lead is not a quality gate,
#: it is an outage.
#:
#: So the two requirements are not both checklist items, and that asymmetry is
#: why this is a list of RULES rather than a tuple of item keys:
#:
#: - ``item``  — delegate to the checklist, which already answers it. `celular`
#:               is genuinely subtle (the number lives in `celular` for some
#:               clientes and in `chave_canonica` for others, gated by
#:               `chave_tipo`), so it MUST NOT be re-derived here; a second
#:               implementation would drift from the checkbox the operator
#:               sees, and then a ticked box would sit next to a card that
#:               refuses to move with no way to tell which is lying.
#: - ``campos`` — any of these `clientes` columns being non-empty satisfies it.
#:               Used for `nome`, which is deliberately NOT a checklist item:
#:               the checklist asks the stricter "do we hold a real full name?"
#:               question, and this gate asks the weaker "do we know what to
#:               call them?" one. Two different questions, honestly named.
EXIGENCIAS: tuple[dict, ...] = (
    {
        "key": "nome",
        "label": "Nome",
        "campos": ("nome", "nome_completo", "nome_oficial"),
    },
    {"key": "celular", "label": "Celular", "item": "celular"},
)

#: Kept as the flat key tuple earlier readers referenced. Derived, so it can
#: never disagree with the rules above.
CAMPOS_OBRIGATORIOS: tuple[str, ...] = tuple(e["key"] for e in EXIGENCIAS)


def _tem_algum_campo(cliente: Optional[dict], colunas: tuple[str, ...]) -> bool:
    """Is any of these columns non-empty?

    Whitespace-only is empty, matching `documento_checklist_service._preenchido`
    — a name of "   " satisfies a NOT NULL check and satisfies nobody else, and
    letting it open the gate would be the same false-completeness the checklist
    exists to prevent.
    """
    cliente = cliente or {}
    for col in colunas:
        valor = cliente.get(col)
        if valor is None:
            continue
        if isinstance(valor, str) and not valor.strip():
            continue
        return True
    return False


def pendencias(
    client: Any,
    org_id: str | UUID,
    cliente_id: Optional[str],
) -> list[dict[str, str]]:
    """Requirements this cliente does not satisfy, as `{key, label}`.

    Empty list = the gate is open.

    A card with NO cliente at all is reported as missing everything rather
    than waved through. An atendimento without a person attached cannot have
    that person's name, and answering "nothing is missing" for it would be the
    silent-fallback shape — a gate that passes hardest exactly where the data
    is most absent.
    """
    faltando = [{"key": e["key"], "label": e["label"]} for e in EXIGENCIAS]
    if cliente_id is None:
        return faltando

    cliente = checklist_svc.cliente_para_derivacao(client, org_id, cliente_id)
    estado = {
        item["key"]: item["concluido"]
        for item in checklist_svc.listar(client, org_id, cliente_id)["items"]
    }

    pendentes: list[dict[str, str]] = []
    for regra in EXIGENCIAS:
        if "item" in regra:
            ok = estado.get(regra["item"], False)
        else:
            ok = _tem_algum_campo(cliente, regra["campos"])
        if not ok:
            pendentes.append({"key": regra["key"], "label": regra["label"]})
    return pendentes


def mensagem(pendentes: list[dict[str, str]]) -> str:
    """The refusal, naming every missing field rather than just the first.

    One field at a time turns a two-field gap into two failed attempts, and the
    operator learns the requirement by trial and error instead of being told
    it.
    """
    faltando = ", ".join(p["label"] for p in pendentes)
    return (
        f"Não é possível mover este atendimento: {faltando} "
        f"{'é obrigatório' if len(pendentes) == 1 else 'são obrigatórios'} "
        "e ainda não consta no cadastro."
    )


__all__ = ["CAMPOS_OBRIGATORIOS", "pendencias", "mensagem"]
