"""Agreement engine — the ONLY source of articles and gendered words (spec §2.0).

Contracts 03/04/06/07/08 all carry gender drift ("legítima proprietária" for
a man, "em favor da VENDEDOR"). The cause is hand-typed agreement; the cure is
that no template line spells an article: it asks `V`/`C` (or a person's `g`).

A group is plural when it has more than one person, otherwise it takes that
person's gender. A plural group is feminine only when EVERY member is a
woman ("as COMPRADORAS", "denominadas") — a mixed-gender group is masculine
plural by construction ("VENDEDORES"). [Deal 799 replay, 2026-10-24] two
women married to each other printed "Os COMPRADORES … casados …"
everywhere; the signed contract reads "as COMPRADORAS … casadas". The rule
is the one `frases.denominacao_anuentes` / `frases.antigo_proprietario_texto`
already applied to their own groups.
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


def genero_exigido(valor: Optional[str], quem: str = "") -> str:
    """The gender of a person the contract PRINTS — 'm' | 'f', never guessed.

    🔴 There is no default. Every printed person's gender is a `faltando`
    in `derivacao` (`qualificacao.genero`), so by the time a template asks
    for it the value is there; one that is not means gate and template
    disagree about who is printed, and inventing "m" would put a woman in a
    signed deed as "o VENDEDOR". Refuse instead — a loud 500 beats a
    silently mis-gendered contract."""
    g = normalizar_genero(valor)
    if g is None:
        raise ValueError(
            f"genero_exigido: gênero ausente ou desconhecido{f' — {quem}' if quem else ''}; "
            "o gate (derivacao) deveria ter recusado a geração."
        )
    return g


def plural_feminino(m: str, f: str, p: str) -> str:
    """The feminine plural a template did not spell out, from its forms.

    A gender-invariant word ("ciente", "responsável": `m == f`) takes the
    plural as given ("cientes", "responsáveis"). Otherwise each word of the
    feminine singular that ends in "a" takes an "s" ("legítima proprietária"
    -> "legítimas proprietárias", "denominada" -> "denominadas", "desta" ->
    "destas"); any other word stays as it is. A form this rule cannot reach
    is passed explicitly as `pf`."""
    if m == f:
        return p
    return " ".join(w + "s" if w.endswith("a") else w for w in f.split(" "))


class Concordancia:
    """Agreement tokens for one person or one side of the deal."""

    def __init__(
        self,
        generos: Sequence[str],
        nome_singular_m: str = "",
        nome_singular_f: str = "",
        nome_plural: str = "",
        nome_plural_f: str = "",
    ) -> None:
        if not generos:
            raise ValueError("Concordancia precisa de ao menos uma pessoa")
        self.plural = len(generos) > 1
        #: Singular: that person's gender. Plural: True only when EVERY
        #: member is a woman (Portuguese agreement — one man makes it "os").
        self.feminino = all(g == "f" for g in generos)
        self._nomes = (nome_singular_m, nome_singular_f, nome_plural, nome_plural_f)

    def _f(self, m: str, f: str, p: str, pf: Optional[str] = None) -> str:
        if self.plural:
            if self.feminino:
                return pf if pf is not None else plural_feminino(m, f, p)
            return p
        return f if self.feminino else m

    def g(self, m: str, f: str, p: Optional[str] = None, pf: Optional[str] = None) -> str:
        """`m`/`f` singular, `p` masculine plural, `pf` feminine plural
        (derived by `plural_feminino` when omitted)."""
        return self._f(m, f, p if p is not None else m, pf)

    def pl(self, singular: str, plural: str) -> str:
        return plural if self.plural else singular

    @property
    def NOME(self) -> str:  # noqa: N802 — template token, spec §2.0
        return self._f(*self._nomes)

    @property
    def ART(self) -> str:  # noqa: N802
        return self._f("O", "A", "Os", "As")

    @property
    def art(self) -> str:
        return self._f("o", "a", "os", "as")

    @property
    def aos(self) -> str:
        return self._f("ao", "à", "aos", "às")

    @property
    def dos(self) -> str:
        return self._f("do", "da", "dos", "das")

    @property
    def pelos(self) -> str:
        return self._f("pelo", "pela", "pelos", "pelas")

    @property
    def estes(self) -> str:
        return self._f("este", "esta", "estes", "estas")


def lado(generos: Sequence[str], lado_nome: str) -> Concordancia:
    """`lado_nome` is "vendedor" or "comprador"."""
    base = lado_nome.upper()
    return Concordancia(generos, base, base + "A", base + "ES", base + "AS")


def pessoa(genero: str) -> Concordancia:
    return Concordancia([genero])


__all__ = ["Concordancia", "genero_exigido", "lado", "normalizar_genero", "pessoa", "plural_feminino"]
