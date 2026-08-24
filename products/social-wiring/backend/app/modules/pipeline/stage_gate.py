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

#: The checklist items an atendimento's titular must satisfy before the card
#: may leave its current stage.
#:
#: Deliberately a subset of `ITENS` and deliberately SMALL. The user's words:
#: "for now the only required fields are going to be name and celular […] I'll
#: refine that later, there will be more required fields." Growing this tuple
#: is the whole change — the gate, its error message and the frontend's
#: explanation all read from it.
#:
#: 🔴 `nome_completo`, not `nome`. The item requires something that LOOKS like
#: a full name (`looks_like_a_name` — two substantive words, no digits), so a
#: WhatsApp push name of "Ana" does NOT open the gate. That is the intended
#: strictness: the point of the requirement is that someone has actually
#: collected this person's details, and a channel-supplied first name is
#: evidence of the opposite.
CAMPOS_OBRIGATORIOS: tuple[str, ...] = ("nome_completo", "celular")


def pendencias(
    client: Any,
    org_id: str | UUID,
    cliente_id: Optional[str],
) -> list[dict[str, str]]:
    """Required items this cliente does not satisfy, as `{key, label}`.

    Empty list = the gate is open.

    A card with NO cliente at all is reported as missing everything rather
    than waved through. An atendimento without a person attached cannot have
    that person's name, and answering "nothing is missing" for it would be the
    silent-fallback shape — a gate that passes hardest exactly where the data
    is most absent.
    """
    itens_por_key = {i["key"]: i for i in checklist_svc.ITENS}
    if cliente_id is None:
        return [
            {"key": key, "label": itens_por_key[key]["label"]}
            for key in CAMPOS_OBRIGATORIOS
        ]

    estado = {
        item["key"]: item["concluido"]
        # Passed through as-is: `listar` stringifies its own arguments, so a
        # `UUID()` coercion here would add nothing except a crash path for an
        # id that is malformed rather than merely unknown.
        for item in checklist_svc.listar(client, org_id, cliente_id)["items"]
    }
    return [
        {"key": key, "label": itens_por_key[key]["label"]}
        for key in CAMPOS_OBRIGATORIOS
        if not estado.get(key, False)
    ]


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
