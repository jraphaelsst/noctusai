"""Agreement engine — the ONLY source of articles and gendered words (spec §2.0).

Contracts 03/04/06/07/08 all carry gender drift ("legítima proprietária" for
a man, "em favor da VENDEDOR"). The cause is hand-typed agreement; the cure is
that no template line spells an article: it asks `V`/`C` (or a person's `g`).

A group is plural when it has more than one person, otherwise it takes that
person's gender. A mixed-gender group is plural and therefore masculine
plural by construction ("VENDEDORES").
"""
from __future__ import annotations

from typing import Optional, Sequence


def normalizar_genero(valor: Optional[str]) -> Optional[str]:
    """`clientes.genero` is unconstrained TEXT (068); the card writes
    "Masculino"/"Feminino" and certidões use "M"/"F". Anything else is None —
    the gate reports it, nothing here guesses."""
    s = (valor or "").strip().lower()
    if s.startswith("f"):
        return "f"
    if s.startswith("m"):
        return "m"
    return None


class Concordancia:
    """Agreement tokens for one person or one side of the deal."""

    def __init__(
        self,
        generos: Sequence[str],
        nome_singular_m: str = "",
        nome_singular_f: str = "",
        nome_plural: str = "",
    ) -> None:
        if not generos:
            raise ValueError("Concordancia precisa de ao menos uma pessoa")
        self.plural = len(generos) > 1
        self.feminino = not self.plural and generos[0] == "f"
        self._nomes = (nome_singular_m, nome_singular_f, nome_plural)

    def _f(self, m: str, f: str, p: str) -> str:
        if self.plural:
            return p
        return f if self.feminino else m

    def g(self, m: str, f: str, p: Optional[str] = None) -> str:
        return self._f(m, f, p if p is not None else m)

    def pl(self, singular: str, plural: str) -> str:
        return plural if self.plural else singular

    @property
    def NOME(self) -> str:  # noqa: N802 — template token, spec §2.0
        return self._f(*self._nomes)

    @property
    def ART(self) -> str:  # noqa: N802
        return self._f("O", "A", "Os")

    @property
    def art(self) -> str:
        return self._f("o", "a", "os")

    @property
    def aos(self) -> str:
        return self._f("ao", "à", "aos")

    @property
    def dos(self) -> str:
        return self._f("do", "da", "dos")

    @property
    def pelos(self) -> str:
        return self._f("pelo", "pela", "pelos")

    @property
    def estes(self) -> str:
        return self._f("este", "esta", "estes")


def lado(generos: Sequence[str], lado_nome: str) -> Concordancia:
    """`lado_nome` is "vendedor" or "comprador"."""
    base = lado_nome.upper()
    return Concordancia(generos, base, base + "A", base + "ES")


def pessoa(genero: str) -> Concordancia:
    return Concordancia([genero])


__all__ = ["Concordancia", "lado", "normalizar_genero", "pessoa"]
