"""Which label introduces a value, and whether that label is somebody else's.

Extracted at N=3. `birthdate`, `gender`, `cpf` and `rg` all answer the same
question — "looking backwards from where I found this value, what field is it
part of?" — and all four had begun to answer it slightly differently. This is
the one implementation.

🔴 WHAT THE THREE COPIES GOT WRONG, AND WHY IT MATTERED
--------------------------------------------------------
The original rule was "nearest label wins". It has two failure modes, both of
which produce a confident wrong answer rather than an obvious one:

1. **A substring label wins over the real one.** `IDENTIDADE` sits inside
   `CARTEIRA DE IDENTIDADE` and starts twelve characters later, so
   position-only comparison reports the short form. The value is right and the
   audit trail understates what the parser saw.

2. **A block opener is out-ranged by a label inside its own block.**
   `FILIACAO MARIA DE TAL CPF 412.954.238-98` — `CPF` is nearer than
   `FILIACAO`, so nearest-wins accepts a *parent's* CPF as the holder's, at
   high confidence, and writes it unattended. This was live in `gender.py`
   before this module existed.

WHAT REPLACES IT
----------------
Two kinds of decoy, because they are two different mistakes:

- **Block openers** (`FILIACAO`, `PAI`, `MAE`, `CONJUGE`, `RESPONSAVEL`) start
  a region belonging to a *different person*. A real label inside that region
  does not clear it — but it does not necessarily belong to the parent either,
  because the block may simply have ended. That is genuinely ambiguous from
  text alone, so the reading survives and is DEMOTED. The consumer contract
  already says only `alta` is written unattended, so a demoted value lands in
  the confirm queue where a human resolves it. Rejecting outright would drop
  real holder data; accepting would write a parent's.

- **Value-type decoys** (`CNPJ`, `MATRICULA`, `PIS`) label a *different kind of
  number* for the same person. There is nothing ambiguous about them: if one is
  nearest, the value is not ours. Rejected.

Matching prefers the label that ENDS latest, then the longest — which is what
fixes (1) without special-casing any particular pair.
"""
from __future__ import annotations

from typing import Optional, Sequence

#: How far back from a value to look for its label.
#:
#: 48 characters, the window every sibling already used. It is about one line
#: of a normalised ID layout: far enough to cross `SEXO: ` or `CPF ` plus
#: whitespace, short enough that the previous field's label is out of reach.
LABEL_WINDOW = 48


class Achado:
    """The label bound to one value, and what it means for confidence.

    Three states rather than a bool, because "reject" and "demote" are
    different answers and collapsing them is exactly the bug this module was
    extracted to fix.
    """

    __slots__ = ("rotulo", "rejeitado", "rebaixado")

    def __init__(
        self,
        rotulo: Optional[str],
        *,
        rejeitado: bool = False,
        rebaixado: bool = False,
    ) -> None:
        #: The matched label, verbatim, or None when the value was unlabelled.
        self.rotulo = rotulo
        #: The value belongs to a different FIELD. Drop it.
        self.rejeitado = rejeitado
        #: The value may belong to a different PERSON. Keep it, demote it.
        self.rebaixado = rebaixado

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Achado(rotulo={self.rotulo!r}, rejeitado={self.rejeitado}, "
            f"rebaixado={self.rebaixado})"
        )


def _melhor(window: str, rotulos: Sequence[str]) -> tuple[Optional[str], int]:
    """The best-matching label in `window`, and where it ends.

    "Best" is the one that ends latest — nearest to the value — with the
    longest winning a tie. See failure mode (1) in the module docstring.
    """
    melhor: Optional[str] = None
    melhor_fim = -1
    for rotulo in rotulos:
        pos = window.rfind(rotulo)
        if pos < 0:
            continue
        fim = pos + len(rotulo)
        if fim > melhor_fim or (fim == melhor_fim and len(rotulo) > len(melhor or "")):
            melhor_fim = fim
            melhor = rotulo
    return (melhor, melhor_fim)


def label_before(
    haystack: str,
    at: int,
    *,
    labels: Sequence[str],
    blocos: Sequence[str] = (),
    valores: Sequence[str] = (),
    window: int = LABEL_WINDOW,
) -> Achado:
    """Classify the value found at `at` by the labels preceding it.

    `labels`   — labels that genuinely introduce this field for the holder.
    `blocos`   — block openers naming a different person (`FILIACAO`, `MAE`).
    `valores`  — labels naming a different kind of value (`CNPJ`, `MATRICULA`).

    All three are matched against the same backwards window; the caller passes
    already-normalised (upper-cased, accent-stripped) text, as every parser in
    this package works on.
    """
    janela = haystack[max(0, at - window) : at]

    rotulo, fim_rotulo = _melhor(janela, labels)
    _, fim_valor = _melhor(janela, valores)
    _, fim_bloco = _melhor(janela, blocos)

    # A different KIND of value, closer than our own label. Not ours.
    if fim_valor > fim_rotulo:
        return Achado(None, rejeitado=True)

    # A block opener with no real label after it: squarely inside somebody
    # else's region.
    if fim_bloco > fim_rotulo:
        return Achado(None, rejeitado=True)

    # A block opener EARLIER in the window, with our label after it. The block
    # may have ended, or the label may belong to it. Ambiguous from text — keep
    # the value, make a human confirm.
    if fim_bloco >= 0 and rotulo is not None:
        return Achado(rotulo, rebaixado=True)

    if rotulo is None:
        # Unlabelled, but still inside a block region.
        if fim_bloco >= 0:
            return Achado(None, rejeitado=True)
        return Achado(None)

    return Achado(rotulo)


__all__ = ["Achado", "LABEL_WINDOW", "label_before"]
